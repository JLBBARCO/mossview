# -*- coding: utf-8 -*-
"""
Módulo de leitura, análise e validação de arquivos de configuração e ajuste .JOB (NORMOS).
"""

import re
from pathlib import Path


def parse_job_file(job_path: Path) -> dict:
    """
    Lê o arquivo .JOB do NORMOS e extrai metadados completos de &DATA, &PARAM,
    tabelas de resultados físicos e parâmetros de ajuste.
    """
    info = {
        'mos_filename': None,
        'title': '',
        'vmax': 10.0,
        'vmax_raw': 10.0,
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
