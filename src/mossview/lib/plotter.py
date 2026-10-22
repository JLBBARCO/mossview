# -*- coding: utf-8 -*-
"""
Módulo de visualização gráfica científica para espectros Mössbauer.
Engenharia reversa e substituto em Python do MBPLOT.EXE.
"""

from pathlib import Path
from typing import Optional, List
import numpy as np
import matplotlib.pyplot as plt

from .model import MossbauerModel


def plot_mossbauer(velocity: np.ndarray, counts: np.ndarray, title: str,
                   job_name: str, mos_name: str, output_image_path: Optional[Path] = None,
                   y_theo: Optional[np.ndarray] = None, subspectra: Optional[List[np.ndarray]] = None,
                   model: Optional[MossbauerModel] = None, show_gui: bool = True,
                   dpi: int = 150, return_fig: bool = False, fig: Optional[plt.Figure] = None):
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

    # Se uma figura já foi fornecida (ex: Canvas Tkinter), limpa-a, senão cria uma nova
    if fig is None:
        if has_residuals:
            fig = plt.figure(figsize=(11.5, 7.5), dpi=dpi)
        else:
            fig = plt.figure(figsize=(10, 6), dpi=dpi)
    else:
        fig.clear()

    if has_residuals:
        w_dist = 1.3 if has_distribution else 0.001
        gs = fig.add_gridspec(2, 2, height_ratios=[3.5, 1.0], width_ratios=[3.8, w_dist],
                               hspace=0.08, wspace=0.38)
        ax1 = fig.add_subplot(gs[0, 0])
        ax_res = fig.add_subplot(gs[1, 0], sharex=ax1)
        ax_dist = fig.add_subplot(gs[0, 1]) if has_distribution else None
    else:
        ax1 = fig.add_subplot(1, 1, 1)
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
        fig.tight_layout()

    if output_image_path:
        fig.savefig(output_image_path, dpi=dpi, bbox_inches='tight')
        print(f"[OK] Gráfico do espectro salvo com sucesso em: {output_image_path}")

    if show_gui:
        plt.show()
    elif not return_fig:
        plt.close(fig)

    if return_fig:
        return fig
