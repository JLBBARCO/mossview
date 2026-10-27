# MossView

MossView is a command-line tool for reading Mössbauer spectra and plotting relative transmission. The main application is [`src/mossview/cli.py`](src/mossview/cli.py). It reads counts from a `.mos` file and, when it finds an associated `.job` file, uses its metadata for the plot title and velocity scale.

## Requirements

- Python 3.8 or later, as declared in `pyproject.toml`.
- Dependencies listed in [`requirements.txt`](requirements.txt): NumPy and Matplotlib, with their transitive dependencies pinned there.

Install the dependencies in a virtual environment if desired:

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS or Linux
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Usage

After installing the package, pass a `.mos` or `.job` file to either the
`mossview` command or the module:

```bash
mossview data-control/b025a-26.mos
python -m mossview data-control/b025adi.job
```

When given a `.job`, MossView tries to locate the `.mos` file named near the beginning of the job file, then falls back to a file with the same base name. When given a `.mos`, it looks for a `.job` that references it or has the same base name. Paths are checked as provided, then relative to the script directory.

The program prints progress and saves a PNG beside the `.mos` file with the same base name. It also opens an interactive Matplotlib window; close the window to end the process.

## Processing flow

1. Resolves the input path and finds the associated `.mos` and `.job` files.
2. Reads recognized metadata from the `.job`'s `&DATA ... &END` block: `VMAX` (absolute value), `ND`, and `TRIANG`. The plot uses `VMAX`, defaulting to 10 mm/s when unavailable. `ND` and `TRIANG` are read but do not affect current processing.
3. Reads counts from the `.mos`. The parser accepts XML containing a `<data>` element, as well as text containing numbers. It can read the XML `time` attribute, but does not currently use it in the plot.
4. Builds a linear velocity scale from `-VMAX` to `+VMAX`, with one point per count.
5. Calculates relative transmission as `count / maximum_count × 100` and plots Poisson error bars as `√count / maximum_count × 100`.
6. Saves and displays the plot.

## `&PARAM` block validation

When a `.job` file is available, the program examines assignments only inside the `&PARAM ... &END` block. It compares selected parameters with final values found in tables in the same file. It also checks `ARX` values above 0.5 mm/s when no applicable reference is available. If it finds discrepancies, it writes a copy with the `-updated.job` suffix, reports the changes, and uses that copy. The original `.job` is not overwritten by this process.

This correction is a heuristic for numeric discrepancies and `ARX` values. It is not a complete NORMOS format validator or a guarantee of physical correctness. Review the `-updated.job` file before using it with another program.

## Repository components

| Path | Purpose |
| --- | --- |
| `src/mossview/cli.py` | Main application: file reading, association, limited validation, and plotting. |
| `data-control/` | Local sample `.mos`, `.job`, and image files. This directory is ignored by Git. |
| `legado/main.py` | Independent plotting simulator for damped sine waves and Lissajous curves; it is not called by the current MossView application. |
| `legado/executables/` | Historical DOS/MBPLOT-related executables, separate from the main application. |
| `website/` | Minimal website content; it does not provide a working viewer interface. |
| `pyproject.toml` | Package metadata and Semantic Release configuration. |
| `.github/workflows/` | Release and PyPI publishing automation. |

## Website deployment

The static website is configured for Netlify through [`netlify.toml`](netlify.toml).
The repository root is used as the build base, no build command is required, and
Netlify publishes the [`website/`](website/) directory directly.

To deploy it, create a new Netlify site linked to this repository and leave the
build settings empty; the committed configuration supplies the publish
directory. A custom domain, if needed, must be configured in the Netlify site
settings.

## Current scope and limitations

- The available interface is a CLI with an interactive plot; there is no dedicated GUI or web application.
- The velocity axis is always linear and symmetric. The program does not use `ND` or `TRIANG` to reconstruct other acquisition geometries.
- The permissive text parser extracts numeric tokens but does not support every possible `.mos` format.
- The package provides both the `mossview` console command and `python -m mossview`.
- `legado/README.md` describes a historical system and its executables, not the current implementation.

## Development and releases

Release versions are controlled by [.github/version.txt](.github/version.txt):

- `main` uses the `release` entry and creates a stable PyPI release.
- `beta` uses the `pre-release` entry and creates a prerelease. If the entry has no
  prerelease suffix, the workflow adds `b0` automatically (for example,
  `1.0.3` becomes `1.0.3b0`).

When the selected version already exists on PyPI or as a Git tag, the release
workflow increments it automatically, updates `version.txt` and
`pyproject.toml`, commits those changes, and publishes the new version.

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE).
