# -*- coding: utf-8 -*-
"""
Módulo de conversão, dobragem (folding) e exportação colunar de espectros Mössbauer.
Engenharia reversa e substituto em Python do WCONVERT.EXE.
"""

from pathlib import Path
from typing import Optional, List
import numpy as np


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
                          y_theo: Optional[np.ndarray] = None, subspectra: Optional[List[np.ndarray]] = None,
                          metadata: Optional[dict] = None, fmt: str = 'lst'):
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
