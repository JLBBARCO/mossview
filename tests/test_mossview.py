# -*- coding: utf-8 -*-
"""
Testes unitários e de integração para os módulos do MossView.
"""

from pathlib import Path
import numpy as np
import pytest

from mossview.lib import (
    resolve_file_path,
    locate_associated_files,
    parse_job_file,
    validate_and_filter_param_block,
    parse_mos_file,
    fold_spectrum,
    export_converted_data,
    calculate_velocity_scale,
    MossbauerModel,
    load_and_process_spectrum,
)


@pytest.fixture
def sample_job_path():
    path = Path("data-control/b025adi.job").resolve()
    assert path.exists(), f"Arquivo de teste não encontrado: {path}"
    return path


@pytest.fixture
def sample_mos_path():
    path = Path("data-control/b025a-26.mos").resolve()
    assert path.exists(), f"Arquivo de teste não encontrado: {path}"
    return path


def test_resolve_file_path(sample_job_path):
    resolved = resolve_file_path(str(sample_job_path))
    assert resolved.exists()
    assert resolved.is_file()


def test_locate_associated_files(sample_job_path, sample_mos_path):
    # A partir do .job
    mos_p, job_p, info = locate_associated_files(sample_job_path)
    assert job_p is not None and job_p.exists()
    assert mos_p is not None and mos_p.exists()
    assert info.get('mos_filename') is not None

    # A partir do .mos
    mos_p2, job_p2, info2 = locate_associated_files(sample_mos_path)
    assert mos_p2 is not None and mos_p2.exists()
    assert job_p2 is not None and job_p2.exists()


def test_parse_job_file(sample_job_path):
    info = parse_job_file(sample_job_path)
    assert info['vmax'] > 0
    assert info['triang'] is True
    assert len(info['sites']) > 0
    assert info['distribution'] is not None
    assert info['distribution']['active'] is True


def test_parse_mos_file(sample_mos_path):
    counts, meta = parse_mos_file(sample_mos_path)
    assert len(counts) > 0
    assert meta['channels'] == len(counts)
    assert np.all(counts >= 0)


def test_fold_spectrum():
    data = np.arange(1024, dtype=float)
    folded = fold_spectrum(data, target_channels=512)
    assert len(folded) == 512
    # Canal i + Canal (1023 - i) = 1023
    assert np.all(folded == 1023.0)


def test_mossbauer_model():
    velocity = np.linspace(-10, 10, 512)
    model = MossbauerModel(bkg=100000.0, vmax=10.0)
    model.add_site(lines=2, area=0.08, isomer_shift=0.2, fwhm=0.3, quadrupole_split=0.6)
    y_theo, subs = model.compute_spectrum(velocity)

    assert len(y_theo) == 512
    assert len(subs) == 1
    assert np.all(y_theo <= 100000.0)
    assert np.min(y_theo) < 100000.0


def test_load_and_process_spectrum(sample_job_path):
    data = load_and_process_spectrum(str(sample_job_path), fold=True)
    assert data['counts'] is not None
    assert len(data['counts']) == 512
    assert data['velocity'] is not None
    assert len(data['velocity']) == 512
    assert data['y_theo'] is not None
    assert len(data['subspectra']) > 0


def test_export_converted_data(tmp_path, sample_job_path):
    data = load_and_process_spectrum(str(sample_job_path), fold=True)
    out_file = tmp_path / "test_export.lst"
    export_converted_data(
        output_path=out_file,
        velocity=data['velocity'],
        counts=data['counts'],
        y_theo=data['y_theo'],
        subspectra=data['subspectra'],
        metadata=data['job_info'],
        fmt='lst'
    )
    assert out_file.exists()
    content = out_file.read_text(encoding='utf-8')
    assert "MossView WCONVERT" in content
    assert "Velocity_mm_s" in content


def test_gui_initialization(sample_job_path):
    from mossview.gui import MossViewGUI
    app = MossViewGUI(initial_file=str(sample_job_path))
    assert app.current_file_path is not None
    assert app.spectrum_data is not None
    assert len(app.spectrum_data['counts']) == 512
    app.withdraw()
    app.destroy()
