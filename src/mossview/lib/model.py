# -*- coding: utf-8 -*-
"""
Motor físico e modelo analítico Mössbauer (57Fe).
Engenharia reversa e substituto em Python dos módulos NORMOS (WDIST, WSITE e WSIMDATA).
"""

from typing import Tuple, List, Optional
import numpy as np


def calculate_velocity_scale(num_channels: int, vmax: float) -> np.ndarray:
    """
    Calcula a escala de velocidades em mm/s para um espectro Mössbauer linear.
    """
    return np.linspace(-abs(vmax), abs(vmax), num_channels)


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
        self.crystalline_sites: List[dict] = []
        self.hyperfine_distribution: Optional[dict] = None

    @classmethod
    def from_job_info(cls, job_info: dict, counts: Optional[np.ndarray] = None):
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

    def compute_spectrum(self, velocity: np.ndarray) -> Tuple[np.ndarray, List[np.ndarray]]:
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

    def get_distribution_curve(self, num_points: int = 200) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
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
