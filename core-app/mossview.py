#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MossView - Visualizador de Espectros Mössbauer (.mos e .job)
com validação e filtragem restrita aos parâmetros do bloco &PARAM.
"""

import sys
import os
import re
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import matplotlib.pyplot as plt


def resolve_file_path(input_path_str: str) -> Path:
    """
    Resolve o caminho do arquivo de entrada conforme a regra:
    1. Se for caminho absoluto e existir -> retorna ele.
    2. Se existir no diretório de trabalho atual (CWD) -> retorna ele.
    3. Se existir no mesmo diretório do script python -> retorna ele.
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
    Lê o arquivo .JOB no formato NORMOS e extrai metadados de visualização
    e o conteúdo bruto para análise do bloco &PARAM.
    """
    info = {
        'mos_filename': None,
        'title': '',
        'vmax': 10.0,
        'nd': None,
        'triang': True,
        'raw_content': ''
    }

    try:
        with open(job_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            info['raw_content'] = content
            lines = [line.strip() for line in content.splitlines() if line.strip()]

        for line in lines[:6]:
            if line.lower().endswith('.mos'):
                info['mos_filename'] = line
                break

        title_lines = []
        for line in lines:
            if line.startswith('*'):
                cleaned = line.strip('*').strip()
                if cleaned:
                    title_lines.append(cleaned)
        if title_lines:
            info['title'] = " | ".join(title_lines)

        data_match = re.search(r'&DATA(.*?)&END', content, re.DOTALL | re.IGNORECASE)
        if data_match:
            data_block = data_match.group(1)

            vmax_m = re.search(r'VMAX\s*=\s*([+-]?\d+\.?\d*)', data_block, re.IGNORECASE)
            if vmax_m:
                info['vmax'] = abs(float(vmax_m.group(1)))

            nd_m = re.search(r'ND\s*=\s*(\d+)', data_block, re.IGNORECASE)
            if nd_m:
                info['nd'] = int(nd_m.group(1))

            triang_m = re.search(r'TRIANG\s*=\s*\.?(TRUE|FALSE)\.?', data_block, re.IGNORECASE)
            if triang_m:
                info['triang'] = (triang_m.group(1).upper() == 'TRUE')

    except Exception as e:
        print(f"[AVISO] Erro ao ler metadados do arquivo .JOB: {e}")

    return info


def extract_reference_values(content: str) -> dict:
    """
    Extrai valores de referência/finais das tabelas do relatório presentes no arquivo .JOB/.RES.
    """
    refs = {}

    # 1. Tabela de parâmetros "Index Name Initial Final Error"
    pattern_index = re.compile(
        r'^\s*\d+\s+([A-Z]+)\s+[+-]?\d+\.?\d*(?:[eE][+-]?\d+)?\s+([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)',
        re.MULTILINE
    )
    for match in pattern_index.finditer(content):
        param_name = match.group(1).upper()
        try:
            refs[param_name] = float(match.group(2))
        except ValueError:
            pass

    # 2. Tabela "Sub. #Lines Area (mm/s)" para mapeamento de áreas de subspectro (ARX)
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
    Valida e edita ESTRITAMENTE os dados contidos dentro do bloco &PARAM ... &END.
    Verifica discrepâncias numéricas (como deslocamentos de casas decimais em ARX)
    comparando com os dados do relatório ou limites físicos.
    """
    param_match = re.search(r'(&PARAM\b.*?&END)', content, re.DOTALL | re.IGNORECASE)
    if not param_match:
        return content, job_path, []

    original_param_block = param_match.group(1)
    warnings = []
    refs = extract_reference_values(content)

    # Expressão regular para capturar chaves CHAVE(ÍNDICE)=VALOR
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
            # Verifica desvio significativo do valor esperado (ex: erro de casa decimal)
            if abs(val - target_val) > 1e-4:
                formatted_target = f"{target_val:.5f}".rstrip('0').rstrip('.') if abs(target_val) < 100 else f"{target_val}"
                warnings.append(
                    f"Parâmetro {key}={val} fora do espectro esperado. Ajustado para {key}={formatted_target} (Esperado: {target_val})."
                )
                return match.group(0).replace(raw_val, formatted_target)

        # Regra de salvaguarda caso ARX exceda limite típico (> 0.5 mm/s) sem tabela disponível
        if base_name == "ARX" and val > 0.5:
            corrected_val = val / 10.0
            formatted_target = f"{corrected_val:.5f}".rstrip('0').rstrip('.')
            warnings.append(
                f"Parâmetro {key}={val} excede o limite do espectro esperado. Ajustado para {key}={formatted_target}."
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


def parse_mos_file(mos_path: Path) -> tuple[np.ndarray, dict]:
    """
    Lê o arquivo de contagens .MOS em formato XML (WisSoft) ou texto/ASCII puro.
    """
    counts = []
    meta = {}

    try:
        tree = ET.parse(mos_path)
        root = tree.getroot()
        data_elem = root.find('data')
        if data_elem is not None and data_elem.text:
            text_data = data_elem.text.strip()
            counts = [float(val) for val in text_data.split()]
            if 'time' in data_elem.attrib:
                meta['time'] = float(data_elem.attrib['time'])
            return np.array(counts, dtype=float), meta
    except Exception:
        pass

    with open(mos_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    data_match = re.search(r'<data[^>]*>(.*?)</data>', content, re.DOTALL | re.IGNORECASE)
    if data_match:
        text_data = data_match.group(1).strip()
        tokens = text_data.split()
        counts = [float(v) for v in tokens if v.replace('.', '', 1).lstrip('-').isdigit()]
        return np.array(counts, dtype=float), meta

    tokens = content.split()
    for t in tokens:
        try:
            counts.append(float(t))
        except ValueError:
            continue

    if not counts:
        raise ValueError(f"Não foi possível extrair dados numéricos do arquivo {mos_path.name}")

    return np.array(counts, dtype=float), meta


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

    elif target_path.suffix.lower() == '.mos':
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


def calculate_velocity_scale(num_channels: int, vmax: float) -> np.ndarray:
    """
    Calcula a escala de velocidade (em mm/s) para a varredura linear Mössbauer.
    """
    return np.linspace(-abs(vmax), abs(vmax), num_channels)


def plot_mossbauer(velocity: np.ndarray, counts: np.ndarray, title: str, job_name: str, mos_name: str, output_image_path: Path):
    """
    Gera o gráfico espectroscópico Mössbauer em Transmissão Relativa (%) e Contagens Brutas.
    """
    baseline = np.max(counts)
    rel_transmission = (counts / baseline) * 100.0
    errors_rel = (np.sqrt(counts) / baseline) * 100.0

    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    fig, ax1 = plt.subplots(figsize=(10, 6), dpi=120)

    ax1.errorbar(velocity, rel_transmission, yerr=errors_rel, fmt='o', color='#004080',
                 ecolor='#80b3ff', elinewidth=0.8, markersize=3, label='Dados Experimentais', alpha=0.85)

    ax1.axhline(100.0, color='crimson', linestyle='--', linewidth=1.0, label='Linha de Base (100%)')

    ax1.set_xlabel('Velocidade (mm/s)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Transmissão Relativa (%)', fontsize=12, fontweight='bold', color='#004080')
    ax1.tick_params(axis='y', labelcolor='#004080')

    ax2 = ax1.twinx()
    ax2.set_ylabel('Contagens Totais', fontsize=11, color='#555555')
    min_counts = np.min(counts)
    ax2.set_ylim((min_counts / baseline) * 100, 100.5)
    ax2.set_yticks(np.linspace((min_counts / baseline) * 100, 100, 6))
    ax2.set_yticklabels([f"{int(val * baseline / 100):,}" for val in ax2.get_yticks()])
    ax2.grid(False)

    display_title = title if title else f"Espectro Mössbauer - {mos_name}"
    plt.title(display_title, fontsize=13, fontweight='bold', pad=15)

    info_text = (f"Arquivo: {mos_name}\n"
                 f"JOB: {job_name if job_name else 'Nenhum'}\n"
                 f"Canais: {len(counts)}\n"
                 f"Vmax: {np.max(np.abs(velocity)):.4f} mm/s\n"
                 f"Contagem Máx: {int(baseline):,}")

    ax1.text(0.02, 0.05, info_text, transform=ax1.transAxes, fontsize=9,
             verticalalignment='bottom', bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.85, edgecolor='#ccc'))

    ax1.legend(loc='upper right', frameon=True)
    fig.tight_layout()

    plt.savefig(output_image_path, dpi=300)
    print(f"[SUCESSO] Gráfico salvo em: {output_image_path}")

    plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="MossView - Leitor e Visualizador de Espectros Mössbauer (.MOS e .JOB)"
    )
    parser.add_argument("file", help="Nome do arquivo ou caminho completo (.job ou .mos)")
    args = parser.parse_args()

    try:
        resolved_path = resolve_file_path(args.file)
    except Exception as e:
        print(f"[ERRO] Falha ao processar o caminho indicado: {e}")
        sys.exit(1)

    if not resolved_path.exists():
        print(f"[ERRO] O arquivo não foi encontrado:\n  -> {resolved_path}")
        sys.exit(1)

    print(f"[OK] Arquivo localizado em: {resolved_path}")

    mos_path, job_path, job_info = locate_associated_files(resolved_path)

    if not mos_path or not mos_path.exists():
        print(f"[ERRO] Não foi possível localizar o arquivo de dados .MOS associado a {resolved_path.name}")
        sys.exit(1)

    # 1. Leitura e validação dos parâmetros do &PARAM no arquivo .JOB
    if job_path and job_path.exists():
        raw_content = job_info.get('raw_content', '')
        _, updated_job_path, warnings = validate_and_filter_param_block(job_path, raw_content)

        if warnings:
            print("\n[ATENÇÃO] Informação fora do espectro esperado constatada no bloco &PARAM:")
            for w in warnings:
                print(f"  -> {w}")
            print(f"[OK] Arquivo atualizado com o bloco &PARAM corrigido salvo em: {updated_job_path}\n")
            job_path = updated_job_path
            job_info = parse_job_file(job_path)

    # 2. Leitura do arquivo de dados .MOS
    try:
        counts, meta = parse_mos_file(mos_path)
        print(f"[OK] Espectro .MOS carregado: {len(counts)} canais lidos.")
    except Exception as e:
        print(f"[ERRO] Falha ao ler arquivo .MOS: {e}")
        sys.exit(1)

    vmax = job_info.get('vmax', 10.0)
    title = job_info.get('title', '')
    velocity = calculate_velocity_scale(len(counts), vmax)

    job_name = job_path.name if job_path else "Nenhum"
    mos_name = mos_path.name
    output_png = mos_path.with_suffix('.png')

    plot_mossbauer(velocity, counts, title, job_name, mos_name, output_png)


if __name__ == "__main__":
    main()