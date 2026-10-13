#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MossView - Leitor, Analisador, Simulador e Visualizador de Espectros Mössbauer (.MOS e .JOB)
Engenharia Reversa dos Executáveis Legados (NORMOS: MBPLOT, READMCS, WCONVERT, WDIST, WSITE, WSIMDATA, P)
Implementação 100% interpretada em Python nativo com NumPy e Matplotlib.
"""

import sys
import os
import re
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import matplotlib.pyplot as plt


# ==============================================================================
# 1. RESOLUÇÃO DE ARQUIVOS E LOCALIZAÇÃO DE PARES (.JOB / .MOS)
# ==============================================================================

def resolve_file_path(input_path_str: str) -> Path:
    """
    Resolve o caminho do arquivo de entrada usando as regras:
    1. Se o caminho absoluto existir, retorna-o.
    2. Se existir no diretório atual de trabalho (CWD), retorna-o.
    3. Se existir no diretório do script Python, retorna-o.
    """
    path = Path(input_path_str)

    if path.is_absolute() and path.exists():
        return path.resolve()

    if path.exists():
        return path.resolve()

    script_dir = Path(__file__).parent.resolve()
    script_relative_path = script_dir / input_path_str
    if script_relative_path.exists():
        return script_relative_path.resolve()

    return path.resolve()


def parse_job_file(job_path: Path) -> dict:
    """
    Lê o arquivo .JOB do NORMOS e extrai metadados completos de &DATA, &PARAM,
    tabelas de resultados físicos e parâmetros de ajuste.
    """
    info = {
        'mos_filename': None,
        'title': '',
        'vmax': 10.0,
        'nd': None,
        'triang': True,
        'bkg': None,
        'chi2': None,
        'sites': [],
        'distribution': None,
        'raw_content': ''
    }

    try:
        with open(job_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            info['raw_content'] = content
            lines = [line.strip() for line in content.splitlines() if line.strip()]

        # Localiza o nome do arquivo .MOS referenciado
        for line in lines[:8]:
            if line.lower().endswith('.mos'):
                info['mos_filename'] = line
                break

        # Título do espectro (linhas com *)
        title_lines = []
        for line in lines:
            if line.startswith('*'):
                cleaned = line.strip('*').strip()
                if cleaned:
                    title_lines.append(cleaned)
        if title_lines:
            info['title'] = " | ".join(title_lines)

        # Bloco &DATA ... &END
        data_match = re.search(r'&DATA(.*?)&END', content, re.DOTALL | re.IGNORECASE)
        if data_match:
            data_block = data_match.group(1)

            vmax_m = re.search(r'VMAX\s*=\s*([+-]?\d+\.?\d*)', data_block, re.IGNORECASE)
            if vmax_m:
                raw_vmax = float(vmax_m.group(1))
                info['vmax'] = abs(raw_vmax)
                info['vmax_raw'] = raw_vmax

            nd_m = re.search(r'ND\s*=\s*(\d+)', data_block, re.IGNORECASE)
            if nd_m:
                info['nd'] = int(nd_m.group(1))

            triang_m = re.search(r'TRIANG\s*=\s*\.?(TRUE|FALSE|T|F)\.?', data_block, re.IGNORECASE)
            if triang_m:
                val = triang_m.group(1).upper()
                info['triang'] = val in ('TRUE', 'T')

        # Baseline (BKG) da tabela de parâmetros ou &PARAM
        bkg_m = re.search(r'^\s*\d+\s+BKG(?:\(\d+\))?\s+[+-]?\d+\.?\d*\s+([+-]?\d+\.?\d*)', content, re.MULTILINE | re.IGNORECASE)
        if bkg_m:
            info['bkg'] = float(bkg_m.group(1))
        else:
            bkg_p = re.search(r'BKG(?:\(1\))?\s*=\s*([+-]?\d+\.?\d*)', content, re.IGNORECASE)
            if bkg_p:
                info['bkg'] = float(bkg_p.group(1))

        # Chi-quadrado
        chi2_m = re.search(r'Chi-square\s*(?:\(normalized\))?\s*=\s*([+-]?\d+\.?\d*)', content, re.IGNORECASE)
        if chi2_m:
            info['chi2'] = float(chi2_m.group(1))

        # Extração de sítios cristalinos discretos (NXLS / WSITE)
        nxls_m = re.search(r'NXLS\s*=\s*(\d+)', content, re.IGNORECASE)
        nxls = int(nxls_m.group(1)) if nxls_m else 0

        # Mapeamento de áreas relativas se existirem na tabela 'Sub. #Lines'
        rel_areas = {}
        if "Sub. #Lines" in content:
            sub_block = content.split("Sub. #Lines")[1].split("...")[0]
            pat_sub = re.compile(r'^\s*(\d+)\s+(\d+)\s+([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s+([+-]?\d+\.?\d*)?\s+([+-]?\d+\.?\d*)?', re.MULTILINE)
            for sm in pat_sub.finditer(sub_block):
                idx = int(sm.group(1))
                rel_total = float(sm.group(5)) if sm.group(5) else None
                rel_areas[idx] = rel_total

        sites = []
        for i in range(1, max(nxls + 1, 2)):
            nxll_m = re.search(rf'NXLL\({i}\)\s*=\s*(\d+)', content, re.IGNORECASE)
            arx_m = re.search(rf'ARX\({i}\)\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)', content, re.IGNORECASE)
            isx_m = re.search(rf'ISX\({i}\)\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)', content, re.IGNORECASE)
            wix_m = re.search(rf'WIX\({i}\)\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)', content, re.IGNORECASE)
            qux_m = re.search(rf'QUX\({i}\)\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)', content, re.IGNORECASE)
            bhx_m = re.search(rf'BHX\({i}\)\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)', content, re.IGNORECASE)

            if nxll_m or arx_m or isx_m:
                sites.append({
                    'index': i,
                    'lines': int(nxll_m.group(1)) if nxll_m else 2,
                    'area': float(arx_m.group(1)) if arx_m else 0.08,
                    'is': float(isx_m.group(1)) if isx_m else 0.0,
                    'fwhm': float(wix_m.group(1)) if wix_m else 0.3,
                    'qs': float(qux_m.group(1)) if qux_m else 0.0,
                    'bhf': float(bhx_m.group(1)) if bhx_m else 0.0,
                    'rel_area': rel_areas.get(i)
                })
        info['sites'] = sites

        # Extração de distribuição de campo hiperfino (WDIST)
        dist_m = re.search(r'DISTRI\s*=\s*(\d+)|DISTRI\(1\)\s*=\s*(\d+)', content, re.IGNORECASE)
        if dist_m or "Total distribution area" in content:
            dist_info = {
                'active': True,
                'bhf_start': 0.0,
                'nsb': 38,
                'dtb': 0.9,
                'wid': 0.28,
                'iso': 0.0,
                'qua': 0.0,
                'area': 0.1,
                'bhf_avg': 30.0,
                'bhf_std': 5.0,
                'rel_area_pct': None
            }

            b_start_m = re.search(r'BHF\s*=\s*([+-]?\d+\.?\d*)|BHF\(1\)\s*=\s*([+-]?\d+\.?\d*)', content, re.IGNORECASE)
            if b_start_m:
                val = b_start_m.group(1) or b_start_m.group(2)
                dist_info['bhf_start'] = float(val)

            nsb_m = re.search(r'NSB\s*=\s*(\d+)|NSB\(1\)\s*=\s*(\d+)', content, re.IGNORECASE)
            if nsb_m:
                val = nsb_m.group(1) or nsb_m.group(2)
                dist_info['nsb'] = int(val)

            dtb_m = re.search(r'DTB\s*=\s*([+-]?\d+\.?\d*)|DTB\(1\)\s*=\s*([+-]?\d+\.?\d*)', content, re.IGNORECASE)
            if dtb_m:
                val = dtb_m.group(1) or dtb_m.group(2)
                dist_info['dtb'] = float(val)

            wid_m = re.search(r'WID\s*=\s*([+-]?\d+\.?\d*)|WID\(1\)\s*=\s*([+-]?\d+\.?\d*)', content, re.IGNORECASE)
            if wid_m:
                val = wid_m.group(1) or wid_m.group(2)
                dist_info['wid'] = float(val)

            iso_m = re.search(r'ISO\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)|ISO\(1\)\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)', content, re.IGNORECASE)
            if iso_m:
                val = iso_m.group(1) or iso_m.group(2)
                dist_info['iso'] = float(val)

            qua_m = re.search(r'QUA\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)|QUA\(1\)\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)', content, re.IGNORECASE)
            if qua_m:
                val = qua_m.group(1) or qua_m.group(2)
                dist_info['qua'] = float(val)

            # Extração de estatísticas da distribuição do relatório NORMOS
            tot_area_m = re.search(r'Total distribution area\s*=\s*([+-]?\d+\.?\d*)', content, re.IGNORECASE)
            if tot_area_m:
                dist_info['area'] = float(tot_area_m.group(1))

            tot_pct_m = re.search(r'=\s*([+-]?\d+\.?\d*)\s*%\s*of\s*spectrum', content, re.IGNORECASE)
            if tot_pct_m:
                dist_info['rel_area_pct'] = float(tot_pct_m.group(1))

            avg_m = re.search(r'Average value of BHF\s*=\s*([+-]?\d+\.?\d*)', content, re.IGNORECASE)
            if avg_m:
                dist_info['bhf_avg'] = float(avg_m.group(1))

            std_m = re.search(r'Standard deviation\s*=\s*([+-]?\d+\.?\d*)', content, re.IGNORECASE)
            if std_m:
                dist_info['bhf_std'] = float(std_m.group(1))

            info['distribution'] = dist_info

    except Exception as e:
        print(f"[AVISO] Erro ao analisar metadados do arquivo .JOB: {e}")

    return info


def locate_associated_files(target_path: Path):
    """
    Identifica os arquivos .MOS e .JOB a partir do caminho fornecido pelo usuário.
    """
    job_path = None
    mos_path = None
    job_info = {}

    if target_path.suffix.lower() == '.job':
        job_path = target_path
        job_info = parse_job_file(job_path)

        if job_info.get('mos_filename'):
            candidate = job_path.parent / job_info['mos_filename']
            if candidate.exists():
                mos_path = candidate
            else:
                for f in job_path.parent.iterdir():
                    if f.name.lower() == job_info['mos_filename'].lower():
                        mos_path = f
                        break

        if not mos_path:
            candidate = job_path.with_suffix('.MOS')
            if candidate.exists():
                mos_path = candidate
            else:
                candidate_lower = job_path.with_suffix('.mos')
                if candidate_lower.exists():
                    mos_path = candidate_lower

    elif target_path.suffix.lower() in ('.mos', '.mcs'):
        mos_path = target_path

        possible_jobs = list(mos_path.parent.glob('*.JOB')) + list(mos_path.parent.glob('*.job'))
        for j_file in possible_jobs:
            j_info = parse_job_file(j_file)
            if j_info.get('mos_filename') and j_info['mos_filename'].lower() == mos_path.name.lower():
                job_path = j_file
                job_info = j_info
                break

        if not job_path:
            candidate = mos_path.with_suffix('.JOB')
            if candidate.exists():
                job_path = candidate
                job_info = parse_job_file(job_path)

    return mos_path, job_path, job_info


# ==============================================================================
# 2. LEITURA UNIVERSAL DE MCS / MOS (ENGENHARIA REVERSA DE READMCS.EXE)
# ==============================================================================

def parse_mos_file(mos_path: Path) -> tuple[np.ndarray, dict]:
    """
    Lê contagens e metadados de arquivos MCS / MOS nos formatos:
    - WisSoft XML (SpectrRelax / WisEl MCA)
    - MCS ASCII / Texto delimitado por espaços ou quebras de linha
    - Formatos de colunas (Channel / Count)
    """
    counts = []
    meta = {
        'channels': 0,
        'time': None,
        'device': None,
        'mode': None,
        'firmware': None,
        'win1': None,
        'win2': None
    }

    # Tentativa 1: XML WisSoft
    try:
        tree = ET.parse(mos_path)
        root = tree.getroot()
        data_elem = root.find('data')
        meta_elem = root.find('meta')

        if meta_elem is not None:
            meta['device'] = meta_elem.attrib.get('device')
            meta['firmware'] = meta_elem.attrib.get('firmware')
            meta['mode'] = meta_elem.attrib.get('mode')
            w1 = meta_elem.find('WIN1')
            if w1 is not None:
                meta['win1'] = (w1.attrib.get('BEGIN'), w1.attrib.get('END'))
            w2 = meta_elem.find('WIN2')
            if w2 is not None:
                meta['win2'] = (w2.attrib.get('BEGIN'), w2.attrib.get('END'))

        if data_elem is not None and data_elem.text:
            text_data = data_elem.text.strip()
            counts = [float(val) for val in text_data.split()]
            if 'time' in data_elem.attrib:
                meta['time'] = float(data_elem.attrib['time'])
            meta['channels'] = len(counts)
            return np.array(counts, dtype=float), meta
    except Exception:
        pass

    # Tentativa 2: Leitura robusta de texto (XML incompleto ou bloco <data> sem fechamento)
    with open(mos_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    data_tag_m = re.search(r'<data\b([^>]*)>(.*)', content, re.DOTALL | re.IGNORECASE)
    if data_tag_m:
        attrs = data_tag_m.group(1)
        body = data_tag_m.group(2)
        end_idx = body.lower().find('</data>')
        if end_idx != -1:
            body = body[:end_idx]

        time_m = re.search(r'time\s*=\s*["\']?(\d+)', attrs)
        if time_m:
            meta['time'] = float(time_m.group(1))

        tokens = body.split()
        for t in tokens:
            cleaned = t.replace('.', '', 1).lstrip('-')
            if cleaned.isdigit():
                counts.append(float(t))

        if counts:
            meta['channels'] = len(counts)
            return np.array(counts, dtype=float), meta

    # Tentativa 3: Arquivo MCS puro em texto (linhas numéricas)
    lines = content.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(('#', ';', '*', '<')):
            continue
        parts = stripped.split()
        if len(parts) == 1:
            try:
                counts.append(float(parts[0]))
            except ValueError:
                continue
        elif len(parts) >= 2:
            # Pode ser: Channel Count ou Count1 Count2 ...
            try:
                # Se o primeiro for int sequencial, o segundo é count
                counts.append(float(parts[1]))
            except ValueError:
                for p in parts:
                    try:
                        counts.append(float(p))
                    except ValueError:
                        pass

    if not counts:
        raise ValueError(f"Não foi possível extrair dados numéricos do arquivo {mos_path.name}")

    meta['channels'] = len(counts)
    return np.array(counts, dtype=float), meta


def run_readmcs_cli(file_path: Path):
    """
    Substituto interpretado em Python do utilitário READMCS.EXE.
    Lê o arquivo MCS/MOS e exibe o relatório de cabeçalho, canais, estatísticas
    de taxa de contagem e verificação de consistência.
    """
    print(f"\n{'='*75}")
    print(f" MossView READMCS (Leitor de Arquivos de Aquisição MCS / MOS)")
    print(f" Análise Técnica e Metadados do Espectro: {file_path.name}")
    print(f"{'='*75}")

    counts, meta = parse_mos_file(file_path)
    total_counts = np.sum(counts)
    mean_count = np.mean(counts)
    max_count = np.max(counts)
    min_count = np.min(counts)

    print(f" Arquivo              : {file_path.name}")
    print(f" Caminho Completo     : {file_path.resolve()}")
    print(f" Número de Canais     : {len(counts)}")
    if meta.get('time'):
        t_sec = meta['time']
        hours = t_sec / 3600.0
        cps = total_counts / t_sec if t_sec > 0 else 0
        print(f" Tempo de Aquisição   : {t_sec:.1f} s ({hours:.2f} horas)")
        print(f" Taxa de Contagem     : {cps:.2f} contagens/segundo (CPS)")
    if meta.get('device'):
        print(f" Dispositivo MCA      : Dispositivo #{meta['device']} (Firmware: {meta.get('firmware')})")
    if meta.get('mode'):
        print(f" Modo de Aquisição    : {meta['mode']}")
    if meta.get('win1'):
        print(f" Janela SCA 1         : Canal {meta['win1'][0]} a {meta['win1'][1]}")
    if meta.get('win2'):
        print(f" Janela SCA 2         : Canal {meta['win2'][0]} a {meta['win2'][1]}")

    print(f"\n --- Resumo Estatístico dos Canais ---")
    print(f" Contagens Totais     : {int(total_counts):,}")
    print(f" Contagem Média/Canal : {mean_count:.1f}")
    print(f" Contagem Máxima      : {int(max_count):,}")
    print(f" Contagem Mínima      : {int(min_count):,}")
    print(f" Profundidade Máx.    : {((max_count - min_count)/max_count)*100.0:.2f}% de efeito de absorção")
    print(f" Ruído Poisson (std)  : +/- {np.sqrt(mean_count):.1f} contagens")

    print(f"\n --- Primeiros 5 e Últimos 5 Canais ---")
    print("  Canal        Contagem")
    for i in range(min(5, len(counts))):
        print(f"  {i+1:5d}        {int(counts[i]):8d}")
    print("  ...          ...")
    for i in range(max(0, len(counts) - 5), len(counts)):
        print(f"  {i+1:5d}        {int(counts[i]):8d}")
    print(f"{'='*75}\n")


# ==============================================================================
# 3. CONVERSÃO E DOBRAGEM DE ESPECTROS (ENGENHARIA REVERSA DE WCONVERT.EXE)
# ==============================================================================

def fold_spectrum(counts: np.ndarray, target_channels: int = 512) -> np.ndarray:
    """
    Executa a dobragem (folding) simétrica de um espectro Mössbauer de acionamento
    triangular (TRIANG=.TRUE.).
    Combina os canais de aceleração e desaceleração:
    Folded[i] = Counts[i] + Counts[2*target_channels - 1 - i]
    """
    total = len(counts)
    if total < 2 * target_channels:
        # Se tiver exatamente o dobro ou mais
        half = total // 2
        c1 = counts[:half]
        c2 = counts[half:2*half][::-1]
        return c1 + c2

    c1 = counts[:target_channels]
    c2 = counts[target_channels:2*target_channels][::-1]
    return c1 + c2


def export_converted_data(output_path: Path, velocity: np.ndarray, counts: np.ndarray,
                          y_theo: np.ndarray = None, subspectra: list = None,
                          metadata: dict = None, fmt: str = 'lst'):
    """
    Substituto interpretado em Python do utilitário WCONVERT.EXE.
    Converte e exporta o espectro para os formatos colunares .LST, .PLT, .DAT ou .CSV.
    """
    baseline = np.max(counts) if y_theo is None else np.max(y_theo)
    rel_trans = (counts / baseline) * 100.0
    err_trans = (np.sqrt(counts) / baseline) * 100.0

    sep = '\t' if fmt.lower() in ('lst', 'plt', 'dat') else ','

    with open(output_path, 'w', encoding='utf-8') as f:
        # Cabeçalho com metadados NORMOS
        f.write(f"# MossView WCONVERT - Espectro Mössbauer Formatado ({fmt.upper()})\n")
        if metadata:
            if metadata.get('title'):
                f.write(f"# Titulo: {metadata['title']}\n")
            if metadata.get('mos_filename'):
                f.write(f"# Arquivo MOS: {metadata['mos_filename']}\n")
            if metadata.get('vmax'):
                f.write(f"# VMAX: {metadata['vmax']} mm/s\n")
            if metadata.get('bkg'):
                f.write(f"# Baseline (BKG): {metadata['bkg']}\n")
            if metadata.get('chi2'):
                f.write(f"# Chi-2 Normalizado: {metadata['chi2']}\n")

        headers = ["Channel", "Velocity_mm_s", "Counts_Exp", "Rel_Trans_pct", "Error_pct"]
        if y_theo is not None:
            headers.append("Theory_Counts")
            headers.append("Theory_Trans_pct")
            headers.append("Residual_sigma")

        if subspectra:
            for i, _ in enumerate(subspectra):
                headers.append(f"Sub_{i+1}_pct")

        f.write(sep.join(headers) + "\n")

        n = len(velocity)
        for i in range(n):
            row = [
                str(i + 1),
                f"{velocity[i]:.6f}",
                f"{counts[i]:.1f}",
                f"{rel_trans[i]:.4f}",
                f"{err_trans[i]:.4f}"
            ]
            if y_theo is not None:
                t_counts = y_theo[i]
                t_trans = (t_counts / baseline) * 100.0
                sigma = np.sqrt(counts[i]) if counts[i] > 0 else 1.0
                resid = (counts[i] - t_counts) / sigma
                row.append(f"{t_counts:.1f}")
                row.append(f"{t_trans:.4f}")
                row.append(f"{resid:.3f}")

            if subspectra:
                for sub in subspectra:
                    sub_val = (sub[i] / baseline) * 100.0
                    row.append(f"{sub_val:.4f}")

            f.write(sep.join(row) + "\n")

    print(f"[OK] Espectro exportado com sucesso no formato {fmt.upper()}: {output_path}")


def run_convert_cli(input_path: Path, output_path: Path = None, fold: bool = False, fmt: str = 'lst'):
    """
    Comando CLI para converter dados de espectro.
    """
    resolved = resolve_file_path(str(input_path))
    mos_p, job_p, job_info = locate_associated_files(resolved)

    if not mos_p or not mos_p.exists():
        print(f"[ERRO] Arquivo de dados .MOS não encontrado para {resolved}")
        sys.exit(1)

    counts, meta = parse_mos_file(mos_p)
    vmax = job_info.get('vmax', 10.0)
    vmax_raw = job_info.get('vmax_raw', 10.0)

    if fold or (job_info.get('triang') and len(counts) >= 1024):
        target_ch = job_info.get('nd', 512)
        if target_ch > 512:
            target_ch = target_ch // 2
        counts = fold_spectrum(counts, target_channels=target_ch)

    if vmax_raw < 0:
        counts = counts[::-1]

    velocity = calculate_velocity_scale(len(counts), vmax)

    # Simulação teórica se houver job
    y_theo = None
    subspectra = None
    if job_p and job_p.exists():
        model = MossbauerModel.from_job_info(job_info, counts)
        y_theo, subspectra = model.compute_spectrum(velocity)

    if not output_path:
        output_path = mos_p.with_suffix(f'.{fmt.lower()}')

    export_converted_data(output_path, velocity, counts, y_theo=y_theo,
                          subspectra=subspectra, metadata=job_info, fmt=fmt)


# ==============================================================================
# 4. MOTOR FÍSICO E SIMULAÇÃO MÖSSBAUER (WDIST, WSITE, WSIMDATA)
# ==============================================================================

class MossbauerModel:
    """
    Implementação em Python das rotinas analíticas do NORMOS (WDIST / WSITE / WSIMDATA).
    Calcula perfis de absorção ressonante Mössbauer:
    - Singletos (NXLL = 1)
    - Dubletos Quadrupolar (NXLL = 2)
    - Sextetos Magnéticos de 57Fe (NXLL = 6)
    - Distribuição Contínua de Campo Hiperfino P(Bhf)
    """

    # Razões das 6 linhas magnéticas nucleares do 57Fe em função de Bhf (Tesla)
    # Desdobramento Zeeman nuclear: 33 Tesla de Fe alfa metálico corresponde a ~10.6 mm/s de separação externa.
    FE57_ZEEMAN_SHIFTS = np.array([-0.1617, -0.0934, -0.0254, 0.0254, 0.0934, 0.1617])
    FE57_INTENSITY_RATIOS = np.array([3.0, 2.0, 1.0, 1.0, 2.0, 3.0]) / 12.0

    def __init__(self, bkg: float, vmax: float):
        self.bkg = bkg
        self.vmax = vmax
        self.crystalline_sites = []
        self.hyperfine_distribution = None

    @classmethod
    def from_job_info(cls, job_info: dict, counts: np.ndarray = None):
        """
        Instancia o modelo físico a partir das informações extraídas do arquivo .JOB.
        """
        bkg = job_info.get('bkg')
        if bkg is None and counts is not None:
            bkg = float(np.max(counts))
        elif bkg is None:
            bkg = 100000.0

        vmax = job_info.get('vmax', 10.0)
        model = cls(bkg=bkg, vmax=vmax)

        # Sítios cristalinos discretos (WSITE)
        for s in job_info.get('sites', []):
            model.add_site(
                lines=s.get('lines', 2),
                area=s.get('area', 0.08),
                isomer_shift=s.get('is', 0.0),
                fwhm=s.get('fwhm', 0.3),
                quadrupole_split=s.get('qs', 0.0),
                hyperfine_field=s.get('bhf', 0.0)
            )

        # Distribuição de campo hiperfino (WDIST)
        dist = job_info.get('distribution')
        if dist and dist.get('active'):
            model.set_distribution(
                bhf_avg=dist.get('bhf_avg', 31.5),
                bhf_std=dist.get('bhf_std', 5.7),
                bhf_start=dist.get('bhf_start', 9.0),
                nsb=dist.get('nsb', 38),
                dtb=dist.get('dtb', 0.9),
                area=dist.get('area', 0.12),
                isomer_shift=dist.get('iso', 0.0),
                quadrupole_shift=dist.get('qua', 0.0),
                fwhm=dist.get('wid', 0.29)
            )

        return model

    def add_site(self, lines: int, area: float, isomer_shift: float,
                 fwhm: float, quadrupole_split: float = 0.0, hyperfine_field: float = 0.0):
        self.crystalline_sites.append({
            'lines': lines,
            'area': area,
            'is': isomer_shift,
            'fwhm': max(fwhm, 0.05),
            'qs': quadrupole_split,
            'bhf': hyperfine_field
        })

    def set_distribution(self, bhf_avg: float, bhf_std: float, bhf_start: float,
                         nsb: int, dtb: float, area: float, isomer_shift: float,
                         quadrupole_shift: float, fwhm: float):
        self.hyperfine_distribution = {
            'bhf_avg': bhf_avg,
            'bhf_std': max(bhf_std, 0.1),
            'bhf_start': bhf_start,
            'nsb': nsb,
            'dtb': dtb,
            'area': area,
            'iso': isomer_shift,
            'qua': quadrupole_shift,
            'fwhm': max(fwhm, 0.05)
        }

    @staticmethod
    def lorentzian(v: np.ndarray, v0: float, gamma: float, area: float) -> np.ndarray:
        """
        Perfil Lorentziano com área integrada finita:
        Integral de -inf a +inf = area
        Amplitude central = 2 * area / (pi * gamma)
        """
        half_gamma = gamma / 2.0
        amp = (2.0 * area) / (np.pi * gamma)
        return amp * (half_gamma**2) / ((v - v0)**2 + half_gamma**2)

    def compute_spectrum(self, velocity: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
        """
        Calcula o espectro de transmissão teórica total Y_theo(v) e cada subespectro individual.
        Y_theo(v) = BKG * (1.0 - Absorção_Total(v))
        """
        total_absorption = np.zeros_like(velocity, dtype=float)
        subspectra = []

        # 1. Subespectros Cristalinos Discretos
        for site in self.crystalline_sites:
            lines = site['lines']
            area = site['area']
            is_val = site['is']
            gamma = site['fwhm']
            qs = site['qs']
            bhf = site['bhf']

            site_abs = np.zeros_like(velocity, dtype=float)

            if lines == 1:
                # Singleto
                site_abs += self.lorentzian(velocity, v0=is_val, gamma=gamma, area=area)

            elif lines == 2:
                # Dubleto Quadrupolar (duas linhas de área area/2 separadas por QS)
                line_area = area / 2.0
                v1 = is_val - qs / 2.0
                v2 = is_val + qs / 2.0
                site_abs += self.lorentzian(velocity, v0=v1, gamma=gamma, area=line_area)
                site_abs += self.lorentzian(velocity, v0=v2, gamma=gamma, area=line_area)

            elif lines == 6 or bhf > 0.0:
                # Sexteto Magnético Fe-57
                for shift_factor, rel_i in zip(self.FE57_ZEEMAN_SHIFTS, self.FE57_INTENSITY_RATIOS):
                    # Deslocamento magnético + isomer shift + desvio quadrupolar
                    q_sign = 1.0 if abs(shift_factor) > 0.1 else -1.0
                    v_pos = is_val + shift_factor * bhf + q_sign * qs
                    l_area = area * rel_i
                    site_abs += self.lorentzian(velocity, v0=v_pos, gamma=gamma, area=l_area)

            total_absorption += site_abs
            # Converte a contribuição do subsítio para contagens
            sub_counts = self.bkg * (1.0 - site_abs)
            subspectra.append(sub_counts)

        # 2. Distribuição Contínua de Campo Hiperfino (WDIST)
        if self.hyperfine_distribution:
            dist = self.hyperfine_distribution
            nsb = dist['nsb']
            dtb = dist['dtb']
            b_start = dist['bhf_start']
            b_avg = dist['bhf_avg']
            b_std = dist['bhf_std']
            tot_dist_area = dist['area']
            iso = dist['iso']
            qua = dist['qua']
            gamma = dist['fwhm']

            b_vals = b_start + np.arange(nsb) * dtb
            # Distribuição de probabilidade Gaussiana / Hesse-Ruebartsch
            prob = np.exp(-0.5 * ((b_vals - b_avg) / b_std)**2)
            prob_sum = np.sum(prob)
            if prob_sum > 0:
                prob /= prob_sum

            dist_abs = np.zeros_like(velocity, dtype=float)

            for b_field, p_weight in zip(b_vals, prob):
                sextet_area = tot_dist_area * p_weight
                for shift_factor, rel_i in zip(self.FE57_ZEEMAN_SHIFTS, self.FE57_INTENSITY_RATIOS):
                    q_sign = 1.0 if abs(shift_factor) > 0.1 else -1.0
                    v_pos = iso + shift_factor * b_field + q_sign * qua
                    l_area = sextet_area * rel_i
                    dist_abs += self.lorentzian(velocity, v0=v_pos, gamma=gamma, area=l_area)

            total_absorption += dist_abs
            dist_counts = self.bkg * (1.0 - dist_abs)
            subspectra.append(dist_counts)

        y_theo = self.bkg * (1.0 - total_absorption)
        return y_theo, subspectra

    def get_distribution_curve(self, num_points: int = 200) -> tuple[np.ndarray, np.ndarray]:
        """
        Retorna a curva P(Bhf) para plotagem da distribuição.
        """
        if not self.hyperfine_distribution:
            return None, None

        dist = self.hyperfine_distribution
        b_avg = dist['bhf_avg']
        b_std = dist['bhf_std']
        b_min = max(0.0, b_avg - 3.5 * b_std)
        b_max = b_avg + 3.5 * b_std

        b_axis = np.linspace(b_min, b_max, num_points)
        p_axis = np.exp(-0.5 * ((b_axis - b_avg) / b_std)**2) / (b_std * np.sqrt(2 * np.pi))
        return b_axis, p_axis


def run_sim_cli(job_path: Path, output_path: Path = None, channels: int = 512):
    """
    Substituto interpretado em Python do utilitário WSIMDATA.EXE.
    Gera um espectro sintético/teórico a partir de um arquivo .JOB.
    """
    resolved = resolve_file_path(str(job_path))
    job_info = parse_job_file(resolved)

    vmax = job_info.get('vmax', 10.0)
    velocity = calculate_velocity_scale(channels, vmax)
    model = MossbauerModel.from_job_info(job_info)
    y_theo, subspectra = model.compute_spectrum(velocity)

    # Simula ruído Poisson se desejado
    noise = np.random.normal(0, np.sqrt(y_theo))
    simulated_counts = np.clip(y_theo + noise, a_min=0, a_max=None)

    if not output_path:
        output_path = resolved.with_name(f"{resolved.stem}_simulated.lst")

    export_converted_data(output_path, velocity, simulated_counts, y_theo=y_theo,
                          subspectra=subspectra, metadata=job_info, fmt='lst')


def run_info_cli(job_path: Path):
    """
    Substituto interpretado em Python do utilitário PMINFO / WSITE / WDIST.
    Exibe um resumo detalhado de todos os parâmetros físicos do ajuste.
    """
    resolved = resolve_file_path(str(job_path))
    info = parse_job_file(resolved)

    print(f"\n{'='*75}")
    print(f" MossView Fit-Info (Resumo Físico dos Parâmetros de Ajuste NORMOS)")
    print(f" Arquivo .JOB: {resolved.name}")
    print(f"{'='*75}")
    print(f" Título               : {info.get('title') or 'N/A'}")
    print(f" Arquivo .MOS         : {info.get('mos_filename') or 'N/A'}")
    print(f" VMAX (Velocidade)    : {info.get('vmax')} mm/s")
    print(f" Canais (&DATA)       : {info.get('nd')}")
    print(f" Modo Triangular      : {info.get('triang')}")
    print(f" Baseline (BKG)       : {info.get('bkg')}")
    print(f" Chi-2 Normalizado    : {info.get('chi2')}")

    sites = info.get('sites', [])
    print(f"\n --- Sítios Cristalinos Discretos (WSITE) : {len(sites)} sítio(s) ---")
    for s in sites:
        rel_str = f"{s['rel_area']:.2f}%" if s.get('rel_area') is not None else "N/A"
        print(f" Sítio #{s['index']}:")
        print(f"   Tipo de Linhas     : {s['lines']} linhas ({'Singleto' if s['lines']==1 else 'Dubleto' if s['lines']==2 else 'Sexteto'})")
        print(f"   Área do Subespectro: {s['area']:.5f} mm/s (Área Relativa: {rel_str})")
        print(f"   Isomer Shift (IS)  : {s['is']:+.5f} mm/s")
        print(f"   Quadrupole Split   : {s['qs']:+.5f} mm/s")
        print(f"   Largura (FWHM)     : {s['fwhm']:.5f} mm/s")
        if s['bhf'] > 0:
            print(f"   Campo Hiperfino    : {s['bhf']:.2f} Tesla")

    dist = info.get('distribution')
    if dist and dist.get('active'):
        pct_str = f"{dist['rel_area_pct']:.2f}%" if dist.get('rel_area_pct') is not None else "N/A"
        print(f"\n --- Distribuição de Campo Hiperfino (WDIST) ---")
        print(f"   Campo Médio <Bhf>  : {dist['bhf_avg']:.2f} +/- {dist['bhf_std']:.2f} Tesla")
        print(f"   Área da Distr.     : {dist['area']:.5f} mm/s (Área Relativa: {pct_str})")
        print(f"   Faixa de Campo     : {dist['bhf_start']:.2f} a {dist['bhf_start'] + dist['nsb']*dist['dtb']:.2f} Tesla")
        print(f"   Número de Passos   : {dist['nsb']} passos de {dist['dtb']:.2f} Tesla")
        print(f"   Isomer Shift Médio : {dist['iso']:+.5f} mm/s")
        print(f"   Quadrupole Médio   : {dist['qua']:+.5f} mm/s")
        print(f"   Largura Intrínseca : {dist['wid']:.5f} mm/s")
    print(f"{'='*75}\n")


# ==============================================================================
# 5. VALIDAÇÃO E FILTRAGEM DO BLOCO &PARAM
# ==============================================================================

def extract_reference_values(content: str) -> dict:
    """
    Extrai valores de referência/finais das tabelas do relatório no arquivo .JOB/.RES.
    """
    refs = {}

    # 1. Tabela de Parâmetros: "Index Name Initial Final Error"
    pattern_index = re.compile(
        r'^\s*\d+\s+([A-Z0-9_]+(?:\(\d+\))?)\s+[+-]?\d+\.?\d*(?:[eE][+-]?\d+)?\s+([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)',
        re.MULTILINE
    )
    for match in pattern_index.finditer(content):
        param_name = match.group(1).upper()
        try:
            refs[param_name] = float(match.group(2))
        except ValueError:
            pass

    # 2. Tabela "Sub. #Lines Area (mm/s)" para mapear áreas de subespectros (ARX)
    if "Sub. #Lines" in content:
        sub_block = content.split("Sub. #Lines")[1]
        pattern_area = re.compile(r'^\s*(\d+)\s+\d+\s+([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)', re.MULTILINE)
        for match in pattern_area.finditer(sub_block):
            sub_idx = match.group(1)
            try:
                refs[f"ARX({sub_idx})"] = float(match.group(2))
            except ValueError:
                pass

    return refs


def validate_and_filter_param_block(job_path: Path, content: str) -> tuple[str, Path, list[str]]:
    """
    Valida e edita estritamente os dados dentro do bloco &PARAM ... &END.
    Detecta e corrige discrepâncias numéricas (como deslocamentos de casas decimais em ARX,
    ISX, WIX, QUX) em relação ao relatório ou limites físicos.
    """
    param_match = re.search(r'(&PARAM\b.*?&END)', content, re.DOTALL | re.IGNORECASE)
    if not param_match:
        return content, job_path, []

    original_param_block = param_match.group(1)
    warnings = []
    refs = extract_reference_values(content)

    param_kv_pattern = re.compile(r'([A-Z0-9_]+\(\d+\))\s*=\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)', re.IGNORECASE)

    def replace_param(match):
        key = match.group(1).upper()
        raw_val = match.group(2)
        try:
            val = float(raw_val)
        except ValueError:
            return match.group(0)

        base_name = re.sub(r'\(\d+\)', '', key)
        target_val = refs.get(key) or refs.get(base_name)

        if target_val is not None:
            # Tolerância para desvios significativos
            if abs(val - target_val) > 1e-4:
                formatted_target = f"{target_val:.6f}".rstrip('0').rstrip('.') if abs(target_val) < 100 else f"{target_val}"
                warnings.append(
                    f"Parâmetro {key}={val} fora do intervalo esperado. Corrigido para {key}={formatted_target} (esperado: {target_val})."
                )
                return match.group(0).replace(raw_val, formatted_target)

        # Regra de proteção física para ARX (> 0.5 mm/s costuma indicar erro de ordem de grandeza)
        if base_name == "ARX" and val > 0.5:
            corrected_val = val / 10.0
            formatted_target = f"{corrected_val:.6f}".rstrip('0').rstrip('.')
            warnings.append(
                f"Parâmetro {key}={val} excede o limite físico esperado de área. Corrigido para {key}={formatted_target}."
            )
            return match.group(0).replace(raw_val, formatted_target)

        return match.group(0)

    new_param_block = param_kv_pattern.sub(replace_param, original_param_block)

    if warnings and job_path:
        new_content = content.replace(original_param_block, new_param_block)
        stem = job_path.stem
        updated_job_path = job_path if stem.endswith("-updated") else job_path.parent / f"{stem}-updated.job"

        with open(updated_job_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return new_content, updated_job_path, warnings

    return content, job_path, warnings


# ==============================================================================
# 6. VISUALIZAÇÃO GRÁFICA CIENTÍFICA (ENGENHARIA REVERSA DE MBPLOT.EXE)
# ==============================================================================

def calculate_velocity_scale(num_channels: int, vmax: float) -> np.ndarray:
    """
    Calcula a escala de velocidades em mm/s para um espectro Mössbauer linear.
    """
    return np.linspace(-abs(vmax), abs(vmax), num_channels)


def plot_mossbauer(velocity: np.ndarray, counts: np.ndarray, title: str,
                   job_name: str, mos_name: str, output_image_path: Path,
                   y_theo: np.ndarray = None, subspectra: list = None,
                   model: MossbauerModel = None, show_gui: bool = True,
                   dpi: int = 150):
    """
    Substituto interpretado em Python do utilitário MBPLOT.EXE.
    Renderiza o espectro Mössbauer com:
    - Pontos experimentais com barras de erro poissoniano
    - Curva teórica total ajustada (Y_theo)
    - Deconvolução dos subespectros componentes (cristalinos e distribuição)
    - Painel inferior com resíduos estatísticos (Y_exp - Y_theo) / sigma
    - Inset / Subgráfico com a distribuição de campo hiperfino P(Bhf) quando houver
    - Caixa informativa com metadados e parâmetros físicos
    """
    baseline = np.max(counts) if y_theo is None else np.max(y_theo)
    rel_trans = (counts / baseline) * 100.0
    errors_rel = (np.sqrt(counts) / baseline) * 100.0

    has_residuals = y_theo is not None
    has_distribution = model is not None and model.hyperfine_distribution is not None

    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')

    # Se houver resíduos, usa layout de dois eixos verticais (espectro + resíduos)
    if has_residuals:
        fig = plt.figure(figsize=(11.5, 7.5), dpi=dpi)
        w_dist = 1.3 if has_distribution else 0.001
        gs = fig.add_gridspec(2, 2, height_ratios=[3.5, 1.0], width_ratios=[3.8, w_dist],
                               hspace=0.08, wspace=0.38)
        ax1 = fig.add_subplot(gs[0, 0])
        ax_res = fig.add_subplot(gs[1, 0], sharex=ax1)
        ax_dist = fig.add_subplot(gs[0, 1]) if has_distribution else None
    else:
        fig, ax1 = plt.subplots(figsize=(10, 6), dpi=dpi)
        ax_res = None
        ax_dist = None

    # --- 1. GRÁFICO PRINCIPAL: ESPECTRO MÖSSBAUER ---
    ax1.errorbar(velocity, rel_trans, yerr=errors_rel, fmt='o', color='#004080',
                 ecolor='#80b3ff', elinewidth=0.6, markersize=3, label='Dados Experimentais', alpha=0.85)

    ax1.axhline(100.0, color='gray', linestyle='--', linewidth=0.8, alpha=0.7, label='Linha de Base (100%)')

    # Subespectros individuais
    if subspectra:
        colors = ['#2ca02c', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22']
        for i, sub in enumerate(subspectra):
            sub_trans = (sub / baseline) * 100.0
            label_sub = f"Sub #{i+1}"
            if model and i < len(model.crystalline_sites):
                site = model.crystalline_sites[i]
                type_name = "Singleto" if site['lines'] == 1 else "Dubleto" if site['lines'] == 2 else "Sexteto"
                label_sub = f"Sub #{i+1} ({type_name})"
            elif model and model.hyperfine_distribution and i == len(subspectra) - 1:
                label_sub = "Distr. P(B)"

            col = colors[i % len(colors)]
            ax1.plot(velocity, sub_trans, linestyle=':', linewidth=1.2, color=col, alpha=0.9, label=label_sub)

    # Curva Teórica Total
    if y_theo is not None:
        theo_trans = (y_theo / baseline) * 100.0
        ax1.plot(velocity, theo_trans, color='#d62728', linewidth=1.8, label='Ajuste Teórico Total')

    if not has_residuals:
        ax1.set_xlabel('Velocidade (mm/s)', fontsize=11, fontweight='bold')
    else:
        ax1.tick_params(labelbottom=False)

    ax1.set_ylabel('Transmissão Relativa (%)', fontsize=11, fontweight='bold', color='#004080')
    ax1.tick_params(axis='y', labelcolor='#004080')

    # Eixo secundário direito: Total Counts
    ax2 = ax1.twinx()
    ax2.set_ylabel('Contagens Totais', fontsize=10, color='#555555')
    min_counts = np.min(counts)
    ax2.set_ylim((min_counts / baseline) * 100, 100.5)
    ax2.set_yticks(np.linspace((min_counts / baseline) * 100, 100, 6))
    ax2.set_yticklabels([f"{int(val * baseline / 100):,}" for val in ax2.get_yticks()])
    ax2.grid(False)

    display_title = title if title else f"Espectro Mössbauer - {mos_name}"
    ax1.set_title(display_title, fontsize=12, fontweight='bold', pad=10)

    # Caixa de Informações
    info_lines = [
        f"Arquivo: {mos_name}",
        f"JOB: {job_name if job_name else 'Nenhum'}",
        f"Canais: {len(counts)}",
        f"Vmax: {np.max(np.abs(velocity)):.4f} mm/s",
        f"BKG: {int(baseline):,}"
    ]
    if model and model.hyperfine_distribution:
        d = model.hyperfine_distribution
        info_lines.append(f"<Bhf>: {d['bhf_avg']:.1f} +/- {d['bhf_std']:.1f} T")
        info_lines.append(f"Área Distr.: {d['area']:.4f}")

    info_text = "\n".join(info_lines)
    ax1.text(0.02, 0.05, info_text, transform=ax1.transAxes, fontsize=8.5,
             verticalalignment='bottom', bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.88, edgecolor='#ccc'))

    ax1.legend(loc='upper right', frameon=True, fontsize=8)

    # --- 2. GRÁFICO DE RESÍDUOS NORMALIZADOS ---
    if ax_res is not None and y_theo is not None:
        sigma = np.sqrt(counts)
        sigma[sigma == 0] = 1.0
        residuals = (counts - y_theo) / sigma

        ax_res.scatter(velocity, residuals, s=6, color='#004080', alpha=0.7)
        ax_res.axhline(0.0, color='crimson', linestyle='-', linewidth=0.8)
        ax_res.axhline(2.0, color='gray', linestyle='--', linewidth=0.6)
        ax_res.axhline(-2.0, color='gray', linestyle='--', linewidth=0.6)
        ax_res.set_xlabel('Velocidade (mm/s)', fontsize=11, fontweight='bold')
        ax_res.set_ylabel('Resíduo (σ)', fontsize=9, fontweight='bold')
        ax_res.set_ylim(-4.5, 4.5)
        ax_res.tick_params(labelsize=8)

    # --- 3. GRÁFICO DE DISTRIBUIÇÃO P(Bhf) ---
    if ax_dist is not None:
        b_axis, p_axis = model.get_distribution_curve()
        if b_axis is not None:
            ax_dist.plot(b_axis, p_axis, color='#8c564b', linewidth=1.5)
            ax_dist.fill_between(b_axis, p_axis, color='#8c564b', alpha=0.25)
            ax_dist.axvline(model.hyperfine_distribution['bhf_avg'], color='red', linestyle='--', linewidth=1.0)
            ax_dist.set_xlabel('B_hf (Tesla)', fontsize=9, fontweight='bold')
            ax_dist.set_ylabel('P(B)', fontsize=9, fontweight='bold')
            ax_dist.set_title('Distribuição P(B_hf)', fontsize=10, fontweight='bold')
            ax_dist.tick_params(labelsize=8)

    if has_residuals:
        fig.subplots_adjust(left=0.08, right=0.97, top=0.94, bottom=0.09, hspace=0.08, wspace=0.38)
    else:
        plt.tight_layout()

    if output_image_path:
        plt.savefig(output_image_path, dpi=dpi, bbox_inches='tight')
        print(f"[OK] Gráfico do espectro salvo com sucesso em: {output_image_path}")

    if show_gui:
        plt.show()
    else:
        plt.close(fig)


# ==============================================================================
# 7. MODO INTERATIVO (ENGENHARIA REVERSA DO P.EXE / MENUS DO MBPLOT)
# ==============================================================================

def run_interactive_cli(target_file: str = None):
    """
    Substituto interpretado em Python do utilitário interativo P.EXE e menu do MBPLOT.
    Permite operar o MossView através de um menu interativo de opções no terminal.
    """
    print("\n" + "="*70)
    print(" MossView Console Interativo (Compatível com P.EXE e MBPLOT.EXE)")
    print("="*70)

    current_file = target_file
    while True:
        print(f"\nArquivo Atual: {current_file if current_file else 'Nenhum'}")
        print("  [1] Selecionar/Alterar arquivo (.JOB ou .MOS)")
        print("  [2] Visualizar Espectro na Tela (MBPLOT)")
        print("  [3] Inspecionar Metadados do Detector (READMCS)")
        print("  [4] Resumo Físico dos Parâmetros de Ajuste (WSITE/WDIST)")
        print("  [5] Converter e Exportar para Colunas .LST / .CSV (WCONVERT)")
        print("  [6] Simular Espectro Teórico (WSIMDATA)")
        print("  [7] Validar e Corrigir Bloco &PARAM")
        print("  [Q] Sair")

        choice = input("\nEscolha uma opção: ").strip().upper()

        if choice == 'Q':
            print("Encerrando console interativo. Até logo!")
            break

        if choice == '1':
            new_f = input("Digite o caminho do arquivo (.job ou .mos): ").strip()
            if new_f:
                current_file = new_f

        elif choice == '2':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            run_plot_flow(current_file, show_gui=True)

        elif choice == '3':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            res = resolve_file_path(current_file)
            mos_p, _, _ = locate_associated_files(res)
            if mos_p and mos_p.exists():
                run_readmcs_cli(mos_p)
            else:
                print("[ERRO] Arquivo de dados .MOS não encontrado.")

        elif choice == '4':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            res = resolve_file_path(current_file)
            _, job_p, _ = locate_associated_files(res)
            if job_p and job_p.exists():
                run_info_cli(job_p)
            else:
                print("[ERRO] Arquivo .JOB associado não encontrado.")

        elif choice == '5':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            fmt = input("Formato de saída (lst/csv/dat) [padrão: lst]: ").strip() or 'lst'
            run_convert_cli(Path(current_file), fmt=fmt)

        elif choice == '6':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            res = resolve_file_path(current_file)
            _, job_p, _ = locate_associated_files(res)
            if job_p and job_p.exists():
                run_sim_cli(job_p)
            else:
                print("[ERRO] Arquivo .JOB associado não encontrado para simulação.")

        elif choice == '7':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            res = resolve_file_path(current_file)
            _, job_p, job_info = locate_associated_files(res)
            if job_p and job_p.exists():
                raw_content = job_info.get('raw_content', '')
                _, updated_path, warnings = validate_and_filter_param_block(job_p, raw_content)
                if warnings:
                    print("\n[AVISO] Inconsistências corrigidas no &PARAM:")
                    for w in warnings:
                        print(f"  -> {w}")
                    print(f"[OK] Arquivo atualizado salvo em: {updated_path}\n")
                else:
                    print("[OK] Bloco &PARAM validado. Nenhuma inconsistência encontrada.")
            else:
                print("[ERRO] Arquivo .JOB não encontrado para validação.")


# ==============================================================================
# 8. FLUXO PRINCIPAL DE PLOTAGEM E EXECUÇÃO
# ==============================================================================

def run_plot_flow(file_path_str: str, output_image_path: Path = None,
                  show_gui: bool = True, fold: bool = False, dpi: int = 150):
    """
    Fluxo completo e integrado de processamento e plotagem.
    """
    try:
        resolved_path = resolve_file_path(file_path_str)
    except Exception as e:
        print(f"[ERRO] Falha ao processar o caminho especificado: {e}")
        sys.exit(1)

    if not resolved_path.exists():
        print(f"[ERRO] Arquivo não encontrado:\n  -> {resolved_path}")
        sys.exit(1)

    print(f"[OK] Arquivo localizado: {resolved_path}")

    mos_path, job_path, job_info = locate_associated_files(resolved_path)

    if not mos_path or not mos_path.exists():
        referenced_mos = job_info.get('mos_filename') if job_path else None
        if referenced_mos:
            expected_path = resolved_path.parent / referenced_mos
            print(f"[ERRO] Não foi possível encontrar o arquivo .MOS referenciado: {referenced_mos}")
            print(f"[INFO] Local esperado: {expected_path}")
        else:
            expected_path = resolved_path.with_suffix('.MOS')
            print(f"[ERRO] Não foi possível encontrar o arquivo .MOS associado a {resolved_path.name}")
            print(f"[INFO] Local esperado: {expected_path}")
        sys.exit(1)

    # 1. Validação e correção do bloco &PARAM no arquivo .JOB
    if job_path and job_path.exists():
        raw_content = job_info.get('raw_content', '')
        _, updated_job_path, warnings = validate_and_filter_param_block(job_path, raw_content)

        if warnings:
            print("\n[AVISO] Valores fora do padrão físico foram detectados no bloco &PARAM:")
            for w in warnings:
                print(f"  -> {w}")
            print(f"[OK] Arquivo atualizado com bloco &PARAM corrigido: {updated_job_path}\n")
            job_path = updated_job_path
            job_info = parse_job_file(job_path)

    # 2. Leitura do arquivo de dados .MOS
    try:
        counts, meta = parse_mos_file(mos_path)
        print(f"[OK] Espectro .MOS carregado: {len(counts)} canais lidos.")
    except Exception as e:
        print(f"[ERRO] Falha ao ler o arquivo .MOS: {e}")
        sys.exit(1)

    vmax = job_info.get('vmax', 10.0)
    vmax_raw = job_info.get('vmax_raw', 10.0)
    title = job_info.get('title', '')
    triang = job_info.get('triang', True)

    # Se folding foi solicitado explicitamente ou se o arquivo opera em modo triangular com 1024 canais
    if fold or (triang and len(counts) >= 1024 and job_info.get('nd') in (512, 1024)):
        target_ch = 512 if len(counts) >= 1024 else len(counts) // 2
        counts = fold_spectrum(counts, target_channels=target_ch)
        print(f"[INFO] Dobragem simétrica (folding) aplicada: {len(counts)} canais.")

    # Se VMAX for negativo no NORMOS (ex: VMAX=-10.9166), a velocidade diminui com o número do canal
    # (canal 1 corresponde a +VMAX). Invertemos a ordem das contagens para que coincidam com o eixo
    # físico de velocidade crescente (-VMAX até +VMAX).
    if vmax_raw < 0:
        counts = counts[::-1]
        print("[INFO] Orientação do transdutor (VMAX < 0): canais alinhados ao eixo de velocidade crescente.")

    velocity = calculate_velocity_scale(len(counts), vmax)

    # 4. Cálculo do Modelo Físico NORMOS (Y_theo e subespectros)
    model = None
    y_theo = None
    subspectra = None
    if job_path and job_path.exists():
        model = MossbauerModel.from_job_info(job_info, counts)
        y_theo, subspectra = model.compute_spectrum(velocity)
        print(f"[OK] Modelo teórico físico sintetizado: {len(subspectra)} subespectro(s) decomposto(s).")

    job_name = job_path.name if job_path else "Nenhum"
    mos_name = mos_path.name
    if not output_image_path:
        output_image_path = mos_path.with_suffix('.png')

    # 5. Renderização Gráfica MBPLOT
    plot_mossbauer(velocity, counts, title, job_name, mos_name, output_image_path,
                   y_theo=y_theo, subspectra=subspectra, model=model,
                   show_gui=show_gui, dpi=dpi)


# ==============================================================================
# 9. PONTO DE ENTRADA CLI (DISPATCHER COM SUBCOMANDOS E RETROCOMPATIBILIDADE)
# ==============================================================================

def main():
    """
    Ponto de entrada do CLI MossView.
    Mantém 100% de compatibilidade com chamadas anteriores:
        mossview arquivo.job
        mossview arquivo.mos
    E disponibiliza os novos subcomandos inspirados no NORMOS DOS:
        mossview plot [ARQUIVO] [--save] [--no-gui] [--fold]
        mossview readmcs [ARQUIVO]
        mossview convert [ARQUIVO] [--output OUT] [--format lst|csv|dat]
        mossview sim [JOB] [--output OUT]
        mossview info [JOB]
        mossview validate [JOB]
        mossview interactive [ARQUIVO]
    """
    # Verificação de compatibilidade retroativa: se o primeiro argumento for um arquivo existente
    # ou não for um dos subcomandos reservados, trata diretamente como arquivo de espectro.
    subcommands = {'plot', 'readmcs', 'convert', 'sim', 'info', 'validate', 'interactive', '-i', '--interactive'}

    if len(sys.argv) > 1 and sys.argv[1] not in subcommands and not sys.argv[1].startswith('-'):
        # Execução padrão retrocompatível: mossview <caminho_arquivo>
        target_file = sys.argv[1]
        run_plot_flow(target_file, show_gui=True)
        return

    parser = argparse.ArgumentParser(
        prog="mossview",
        description="MossView - Sistema Moderno em Python para Análise, Simulação e Plotagem Mössbauer (Substituto do NORMOS DOS)"
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Comandos disponíveis")

    # Subcomando: plot
    p_plot = subparsers.add_parser("plot", help="Renderiza o espectro Mössbauer (MBPLOT)")
    p_plot.add_argument("file", help="Arquivo .JOB ou .MOS")
    p_plot.add_argument("--save", "-s", action="store_true", help="Salva a imagem em disco")
    p_plot.add_argument("--output", "-o", type=str, default=None, help="Caminho do arquivo de imagem de saída")
    p_plot.add_argument("--no-gui", action="store_true", help="Não abre a janela interativa do Matplotlib")
    p_plot.add_argument("--fold", action="store_true", help="Aplica dobragem simétrica (folding) do espectro")
    p_plot.add_argument("--dpi", type=int, default=150, help="Resolução DPI da imagem (padrão: 150)")

    # Subcomando: readmcs
    p_mcs = subparsers.add_parser("readmcs", help="Inspeciona arquivos MCS/MOS e exibe metadados de aquisição (READMCS)")
    p_mcs.add_argument("file", help="Arquivo .MOS ou .MCS")

    # Subcomando: convert
    p_conv = subparsers.add_parser("convert", help="Converte espectro para formato de colunas LST/CSV/DAT (WCONVERT)")
    p_conv.add_argument("file", help="Arquivo .JOB ou .MOS")
    p_conv.add_argument("--output", "-o", type=str, default=None, help="Arquivo de saída")
    p_conv.add_argument("--format", "-f", choices=['lst', 'csv', 'dat', 'plt'], default='lst', help="Formato de exportação")
    p_conv.add_argument("--fold", action="store_true", help="Aplica dobragem (folding) antes da conversão")

    # Subcomando: sim
    p_sim = subparsers.add_parser("sim", help="Simula espectro Mössbauer a partir dos parâmetros de &PARAM (WSIMDATA)")
    p_sim.add_argument("job", help="Arquivo .JOB de entrada")
    p_sim.add_argument("--output", "-o", type=str, default=None, help="Arquivo .LST de saída")
    p_sim.add_argument("--channels", "-c", type=int, default=512, help="Número de canais da simulação (padrão: 512)")

    # Subcomando: info
    p_info = subparsers.add_parser("info", help="Exibe resumo dos parâmetros físicos de ajuste (WSITE/WDIST)")
    p_info.add_argument("job", help="Arquivo .JOB de entrada")

    # Subcomando: validate
    p_val = subparsers.add_parser("validate", help="Valida e corrige discrepâncias no bloco &PARAM")
    p_val.add_argument("job", help="Arquivo .JOB de entrada")

    # Subcomando: interactive
    p_inter = subparsers.add_parser("interactive", help="Console interativo em terminal (P.EXE)")
    p_inter.add_argument("file", nargs="?", default=None, help="Arquivo inicial opcional")

    # Se nenhum argumento for passado, abre o modo interativo
    if len(sys.argv) == 1:
        run_interactive_cli()
        return

    args = parser.parse_args()

    if args.subcommand == "plot":
        out_p = Path(args.output) if args.output else None
        run_plot_flow(args.file, output_image_path=out_p, show_gui=not args.no_gui, fold=args.fold, dpi=args.dpi)

    elif args.subcommand == "readmcs":
        target = resolve_file_path(args.file)
        run_readmcs_cli(target)

    elif args.subcommand == "convert":
        out_p = Path(args.output) if args.output else None
        run_convert_cli(Path(args.file), output_path=out_p, fold=args.fold, fmt=args.format)

    elif args.subcommand == "sim":
        out_p = Path(args.output) if args.output else None
        run_sim_cli(Path(args.job), output_path=out_p, channels=args.channels)

    elif args.subcommand == "info":
        run_info_cli(Path(args.job))

    elif args.subcommand == "validate":
        resolved = resolve_file_path(args.job)
        job_info = parse_job_file(resolved)
        raw_content = job_info.get('raw_content', '')
        _, updated_path, warnings = validate_and_filter_param_block(resolved, raw_content)
        if warnings:
            print("\n[AVISO] Inconsistências corrigidas no &PARAM:")
            for w in warnings:
                print(f"  -> {w}")
            print(f"[OK] Arquivo atualizado salvo em: {updated_path}\n")
        else:
            print("[OK] Bloco &PARAM validado com sucesso. Nenhuma discrepância encontrada.")

    elif args.subcommand in ("interactive", None):
        target = args.file if hasattr(args, 'file') else None
        run_interactive_cli(target)


if __name__ == "__main__":
    main()
