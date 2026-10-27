# -*- coding: utf-8 -*-
"""
Módulo de leitura universal de arquivos MCS / MOS de aquisição Mössbauer.
Engenharia reversa e substituto em Python do READMCS.EXE.
"""

import re
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np


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
