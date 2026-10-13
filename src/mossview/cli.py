#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MossView - Mössbauer spectrum viewer (.mos and .job)
with validation and filtering restricted to parameters in the &PARAM block.
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
    Resolve the input file path using these rules:
    1. If the absolute path exists, return it.
    2. If the path exists in the current working directory (CWD), return it.
    3. If the path exists in the Python script directory, return it.
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
    Read a NORMOS .JOB file and extract display metadata and raw content
    for analysis of the &PARAM block.
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
        print(f"[WARNING] Error reading metadata from .JOB file: {e}")

    return info


def extract_reference_values(content: str) -> dict:
    """
    Extract reference/final values from report tables in the .JOB/.RES file.
    """
    refs = {}

    # 1. Parameter table: "Index Name Initial Final Error"
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

    # 2. "Sub. #Lines Area (mm/s)" table for mapping subspectrum areas (ARX)
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
    Validate and edit ONLY data inside the &PARAM ... &END block.
    Check numeric discrepancies (such as decimal-place shifts in ARX)
    against report data or physical limits.
    """
    param_match = re.search(r'(&PARAM\b.*?&END)', content, re.DOTALL | re.IGNORECASE)
    if not param_match:
        return content, job_path, []

    original_param_block = param_match.group(1)
    warnings = []
    refs = extract_reference_values(content)

    # Regular expression to capture KEY(INDEX)=VALUE assignments
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
            # Check for a significant deviation from the expected value (e.g. a decimal-place error)
            if abs(val - target_val) > 1e-4:
                formatted_target = f"{target_val:.5f}".rstrip('0').rstrip('.') if abs(target_val) < 100 else f"{target_val}"
                warnings.append(
                    f"Parameter {key}={val} is outside the expected range. Corrected to {key}={formatted_target} (expected: {target_val})."
                )
                return match.group(0).replace(raw_val, formatted_target)

        # Fallback safeguard if ARX exceeds the typical limit (> 0.5 mm/s) without an available table
        if base_name == "ARX" and val > 0.5:
            corrected_val = val / 10.0
            formatted_target = f"{corrected_val:.5f}".rstrip('0').rstrip('.')
            warnings.append(
                f"Parameter {key}={val} exceeds the expected spectrum limit. Corrected to {key}={formatted_target}."
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
    Read counts from a .MOS file in XML (WisSoft) or plain text/ASCII format.
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
        raise ValueError(f"Could not extract numeric data from file {mos_path.name}")

    return np.array(counts, dtype=float), meta


def locate_associated_files(target_path: Path):
    """
    Identify the .MOS and .JOB files from the path provided by the user.
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
    Calculate the velocity scale (in mm/s) for a linear Mössbauer scan.
    """
    return np.linspace(-abs(vmax), abs(vmax), num_channels)


def plot_mossbauer(velocity: np.ndarray, counts: np.ndarray, title: str, job_name: str, mos_name: str, output_image_path: Path):
    """
    Generate a Mössbauer spectrum plot in relative transmission (%) and raw counts.
    """
    baseline = np.max(counts)
    rel_transmission = (counts / baseline) * 100.0
    errors_rel = (np.sqrt(counts) / baseline) * 100.0

    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    fig, ax1 = plt.subplots(figsize=(10, 6), dpi=120)

    ax1.errorbar(velocity, rel_transmission, yerr=errors_rel, fmt='o', color='#004080',
                 ecolor='#80b3ff', elinewidth=0.8, markersize=3, label='Experimental Data', alpha=0.85)

    ax1.axhline(100.0, color='crimson', linestyle='--', linewidth=1.0, label='Baseline (100%)')

    ax1.set_xlabel('Velocity (mm/s)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Relative Transmission (%)', fontsize=12, fontweight='bold', color='#004080')
    ax1.tick_params(axis='y', labelcolor='#004080')

    ax2 = ax1.twinx()
    ax2.set_ylabel('Total Counts', fontsize=11, color='#555555')
    min_counts = np.min(counts)
    ax2.set_ylim((min_counts / baseline) * 100, 100.5)
    ax2.set_yticks(np.linspace((min_counts / baseline) * 100, 100, 6))
    ax2.set_yticklabels([f"{int(val * baseline / 100):,}" for val in ax2.get_yticks()])
    ax2.grid(False)

    display_title = title if title else f"Mossbauer Spectrum - {mos_name}"
    plt.title(display_title, fontsize=13, fontweight='bold', pad=15)

    info_text = (f"File: {mos_name}\n"
                 f"JOB: {job_name if job_name else 'None'}\n"
                 f"Channels: {len(counts)}\n"
                 f"Vmax: {np.max(np.abs(velocity)):.4f} mm/s\n"
                 f"Max Count: {int(baseline):,}")

    ax1.text(0.02, 0.05, info_text, transform=ax1.transAxes, fontsize=9,
             verticalalignment='bottom', bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.85, edgecolor='#ccc'))

    ax1.legend(loc='upper right', frameon=True)
    fig.tight_layout()

    plt.savefig(output_image_path, dpi=300)
    print(f"[SUCCESS] Plot saved to: {output_image_path}")

    plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="MossView - Mössbauer spectrum reader and viewer (.MOS and .JOB)"
    )
    parser.add_argument("file", help="File name or full path (.job or .mos)")
    args = parser.parse_args()

    try:
        resolved_path = resolve_file_path(args.file)
    except Exception as e:
        print(f"[ERROR] Failed to process the specified path: {e}")
        sys.exit(1)

    if not resolved_path.exists():
        print(f"[ERROR] File not found:\n  -> {resolved_path}")
        sys.exit(1)

    print(f"[OK] File found: {resolved_path}")

    mos_path, job_path, job_info = locate_associated_files(resolved_path)

    if not mos_path or not mos_path.exists():
        referenced_mos = job_info.get('mos_filename') if job_path else None
        if referenced_mos:
            expected_path = resolved_path.parent / referenced_mos
            print(
                f"[ERROR] Could not find the .MOS data file referenced by "
                f"{resolved_path.name}: {referenced_mos}"
            )
            print(f"[INFO] Expected location: {expected_path}")
        else:
            expected_path = resolved_path.with_suffix('.MOS')
            print(f"[ERROR] Could not find the .MOS data file associated with {resolved_path.name}")
            print(f"[INFO] Expected location: {expected_path}")
        print("[INFO] Place the referenced .MOS file in the same directory as the .JOB file and try again.")
        sys.exit(1)

    # 1. Read and validate the &PARAM block in the .JOB file
    if job_path and job_path.exists():
        raw_content = job_info.get('raw_content', '')
        _, updated_job_path, warnings = validate_and_filter_param_block(job_path, raw_content)

        if warnings:
            print("\n[WARNING] Values outside the expected range were found in the &PARAM block:")
            for w in warnings:
                print(f"  -> {w}")
            print(f"[OK] Updated file with corrected &PARAM block saved to: {updated_job_path}\n")
            job_path = updated_job_path
            job_info = parse_job_file(job_path)

    # 2. Read the .MOS data file
    try:
        counts, meta = parse_mos_file(mos_path)
        print(f"[OK] .MOS spectrum loaded: {len(counts)} channels read.")
    except Exception as e:
        print(f"[ERROR] Failed to read .MOS file: {e}")
        sys.exit(1)

    vmax = job_info.get('vmax', 10.0)
    title = job_info.get('title', '')
    velocity = calculate_velocity_scale(len(counts), vmax)

    job_name = job_path.name if job_path else "None"
    mos_name = mos_path.name
    output_png = mos_path.with_suffix('.png')

    plot_mossbauer(velocity, counts, title, job_name, mos_name, output_png)


if __name__ == "__main__":
    main()
