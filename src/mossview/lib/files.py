# -*- coding: utf-8 -*-
"""
Módulo de resolução, localização de arquivos e integração com o explorador de arquivos do sistema.
Compatível com Windows, Linux e macOS.
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Tuple, Optional

from .job import parse_job_file


def resolve_file_path(input_path_str: str) -> Path:
    """
    Resolve o caminho do arquivo de entrada usando as regras:
    1. Se o caminho absoluto existir, retorna-o.
    2. Se existir no diretório atual de trabalho (CWD), retorna-o.
    3. Se existir relativo ao pacote mossview, retorna-o.
    4. Se existir relativo à raiz do projeto, retorna-o.
    """
    path = Path(input_path_str)

    if path.is_absolute() and path.exists():
        return path.resolve()

    if path.exists():
        return path.resolve()

    # Relativo ao CWD
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path.resolve()

    # Relativo ao diretório do pacote mossview
    pkg_dir = Path(__file__).resolve().parent.parent
    pkg_relative_path = pkg_dir / path
    if pkg_relative_path.exists():
        return pkg_relative_path.resolve()

    # Relativo à raiz do projeto (pai de src)
    project_root = pkg_dir.parent.parent
    proj_relative_path = project_root / path
    if proj_relative_path.exists():
        return proj_relative_path.resolve()

    return path.resolve()


def locate_associated_files(target_path: Path) -> Tuple[Optional[Path], Optional[Path], dict]:
    """
    Identifica os arquivos .MOS e .JOB a partir do caminho fornecido pelo usuário.
    Retorna uma tupla (mos_path, job_path, job_info).
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


def open_file_dialog_native(title: str = "Selecionar Espectro Mössbauer", initial_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Abre a janela nativa do Explorador de Arquivos para seleção de arquivos (.job, .mos, .mcs).
    Compatível 100% com Windows, Linux e macOS via Tkinter FileDialog.
    """
    import tkinter as tk
    from tkinter import filedialog

    # Cria root temporário oculto se não houver loop Tk ativo
    temp_root = None
    try:
        current_tk = tk._default_root
        if current_tk is None:
            temp_root = tk.Tk()
            temp_root.withdraw()
            # Garante que a janela de diálogo fique no topo
            temp_root.attributes("-topmost", True)
            root_for_dialog = temp_root
        else:
            root_for_dialog = current_tk

        filetypes = [
            ("Arquivos Mössbauer (*.job, *.mos, *.mcs)", "*.job *.JOB *.mos *.MOS *.mcs *.MCS"),
            ("Arquivos NORMOS JOB (*.job)", "*.job *.JOB"),
            ("Arquivos de Aquisição MOS/MCS (*.mos, *.mcs)", "*.mos *.MOS *.mcs *.MCS"),
            ("Todos os arquivos (*.*)", "*.*")
        ]

        init_dir_str = str(initial_dir) if initial_dir and initial_dir.exists() else str(Path.cwd())

        selected = filedialog.askopenfilename(
            parent=root_for_dialog,
            title=title,
            initialdir=init_dir_str,
            filetypes=filetypes
        )

        if selected:
            return Path(selected).resolve()
        return None

    finally:
        if temp_root is not None:
            try:
                temp_root.destroy()
            except Exception:
                pass


def open_in_system_file_manager(target_path: Path):
    """
    Abre o gerenciador de arquivos padrão do sistema operacional (Windows Explorer,
    macOS Finder ou gerenciador Linux) apontando para a pasta ou selecionando o arquivo.
    Compatível com Windows, Linux e macOS.
    """
    resolved = target_path.resolve()
    target_dir = resolved if resolved.is_dir() else resolved.parent

    try:
        if sys.platform.startswith('win'):
            # Windows Explorer
            if resolved.is_file():
                subprocess.run(['explorer', '/select,', str(resolved)], check=False)
            else:
                os.startfile(str(target_dir))
        elif sys.platform.startswith('darwin'):
            # macOS Finder
            if resolved.is_file():
                subprocess.run(['open', '-R', str(resolved)], check=False)
            else:
                subprocess.run(['open', str(target_dir)], check=False)
        else:
            # Linux / Unix (xdg-open)
            subprocess.run(['xdg-open', str(target_dir)], check=False)
    except Exception as e:
        print(f"[AVISO] Não foi possível abrir o gerenciador de arquivos: {e}")
