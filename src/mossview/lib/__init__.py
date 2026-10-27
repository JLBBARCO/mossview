# -*- coding: utf-8 -*-
"""
MossView Core Library - Módulos de Análise, Física, Leitura, Conversão e Visualização Mössbauer.
"""

from .files import (
    resolve_file_path,
    locate_associated_files,
    open_file_dialog_native,
    open_in_system_file_manager,
)
from .job import (
    parse_job_file,
    extract_reference_values,
    validate_and_filter_param_block,
)
from .mos import (
    parse_mos_file,
)
from .converter import (
    fold_spectrum,
    export_converted_data,
)
from .model import (
    calculate_velocity_scale,
    MossbauerModel,
)
from .plotter import (
    plot_mossbauer,
)
from .pipeline import (
    load_and_process_spectrum,
    run_readmcs_cli,
    run_convert_cli,
    run_sim_cli,
    run_info_cli,
    run_plot_flow,
)

__all__ = [
    "resolve_file_path",
    "locate_associated_files",
    "open_file_dialog_native",
    "open_in_system_file_manager",
    "parse_job_file",
    "extract_reference_values",
    "validate_and_filter_param_block",
    "parse_mos_file",
    "fold_spectrum",
    "export_converted_data",
    "calculate_velocity_scale",
    "MossbauerModel",
    "plot_mossbauer",
    "load_and_process_spectrum",
    "run_readmcs_cli",
    "run_convert_cli",
    "run_sim_cli",
    "run_info_cli",
    "run_plot_flow",
]
