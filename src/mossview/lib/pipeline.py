# -*- coding: utf-8 -*-
"""
Módulo integrador de pipelines de processamento, simulação e fluxos do MossView.
Compartilhado entre a interface de linha de comando (CLI) e a interface gráfica (GUI).
"""

import sys
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import numpy as np

from .files import resolve_file_path, locate_associated_files
from .job import parse_job_file, validate_and_filter_param_block
from .mos import parse_mos_file
from .converter import fold_spectrum, export_converted_data
from .model import calculate_velocity_scale, MossbauerModel
from .plotter import plot_mossbauer


def load_and_process_spectrum(file_path_str: str, fold: bool = False) -> Dict[str, Any]:
    """
    Carrega, resolve, valida metadados, processa canais e sintetiza o modelo físico
    para um dado arquivo (.JOB, .MOS ou .MCS).
    Retorna um dicionário estruturado com todos os artefatos calculados.
    """
    resolved_path = resolve_file_path(file_path_str)
    if not resolved_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {resolved_path}")

    mos_path, job_path, job_info = locate_associated_files(resolved_path)

    if not mos_path or not mos_path.exists():
        ref = job_info.get('mos_filename') if job_path else None
        if ref:
            raise FileNotFoundError(f"Arquivo de dados .MOS referenciado não encontrado: {ref}")
        raise FileNotFoundError(f"Arquivo .MOS associado a {resolved_path.name} não encontrado.")

    warnings = []
    # 1. Validação do bloco &PARAM
    if job_path and job_path.exists():
        raw_content = job_info.get('raw_content', '')
        _, updated_job_path, param_warnings = validate_and_filter_param_block(job_path, raw_content)
        if param_warnings:
            warnings.extend(param_warnings)
            job_path = updated_job_path
            job_info = parse_job_file(job_path)

    # 2. Leitura do arquivo .MOS
    counts, meta = parse_mos_file(mos_path)

    vmax = job_info.get('vmax', 10.0)
    vmax_raw = job_info.get('vmax_raw', 10.0)
    title = job_info.get('title', '')
    triang = job_info.get('triang', True)

    # 3. Dobragem (folding) simétrica se necessária
    folding_applied = False
    if fold or (triang and len(counts) >= 1024 and job_info.get('nd') in (512, 1024)):
        target_ch = 512 if len(counts) >= 1024 else len(counts) // 2
        counts = fold_spectrum(counts, target_channels=target_ch)
        folding_applied = True

    # 4. Ajuste de direção do transdutor se VMAX < 0
    if vmax_raw < 0:
        counts = counts[::-1]

    # 5. Eixo de velocidades
    velocity = calculate_velocity_scale(len(counts), vmax)

    # 6. Síntese do Modelo Teórico NORMOS
    model = None
    y_theo = None
    subspectra = None
    if job_path and job_path.exists():
        model = MossbauerModel.from_job_info(job_info, counts)
        y_theo, subspectra = model.compute_spectrum(velocity)

    return {
        'resolved_path': resolved_path,
        'mos_path': mos_path,
        'job_path': job_path,
        'job_info': job_info,
        'counts': counts,
        'meta': meta,
        'velocity': velocity,
        'vmax': vmax,
        'vmax_raw': vmax_raw,
        'title': title,
        'folding_applied': folding_applied,
        'model': model,
        'y_theo': y_theo,
        'subspectra': subspectra,
        'warnings': warnings
    }


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


def run_convert_cli(input_path: Path, output_path: Optional[Path] = None, fold: bool = False, fmt: str = 'lst'):
    """
    Comando CLI para converter dados de espectro (WCONVERT).
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
    print(f"[OK] Espectro exportado com sucesso no formato {fmt.upper()}: {output_path}")


def run_sim_cli(job_path: Path, output_path: Optional[Path] = None, channels: int = 512):
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
    print(f"[OK] Espectro simulado salvo com sucesso em: {output_path}")


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


def run_plot_flow(file_path_str: str, output_image_path: Optional[Path] = None,
                  show_gui: bool = True, fold: bool = False, dpi: int = 150):
    """
    Fluxo completo e integrado de processamento e plotagem.
    """
    try:
        data = load_and_process_spectrum(file_path_str, fold=fold)
    except Exception as e:
        print(f"[ERRO] {e}")
        sys.exit(1)

    print(f"[OK] Arquivo localizado: {data['resolved_path']}")
    for w in data['warnings']:
        print(f"[AVISO] &PARAM: {w}")

    print(f"[OK] Espectro .MOS carregado: {len(data['counts'])} canais lidos.")
    if data['folding_applied']:
        print(f"[INFO] Dobragem simétrica (folding) aplicada: {len(data['counts'])} canais.")
    if data['vmax_raw'] < 0:
        print("[INFO] Orientação do transdutor (VMAX < 0): canais alinhados ao eixo de velocidade crescente.")

    if data['subspectra']:
        print(f"[OK] Modelo teórico físico sintetizado: {len(data['subspectra'])} subespectro(s) decomposto(s).")

    mos_p = data['mos_path']
    job_p = data['job_path']
    job_name = job_p.name if job_p else "Nenhum"
    mos_name = mos_p.name

    if not output_image_path:
        output_image_path = mos_p.with_suffix('.png')

    # Renderização Gráfica MBPLOT
    plot_mossbauer(
        velocity=data['velocity'],
        counts=data['counts'],
        title=data['title'],
        job_name=job_name,
        mos_name=mos_name,
        output_image_path=output_image_path,
        y_theo=data['y_theo'],
        subspectra=data['subspectra'],
        model=data['model'],
        show_gui=show_gui,
        dpi=dpi
    )
