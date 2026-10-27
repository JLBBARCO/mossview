#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_NAME="${MOSSVIEW_OUTPUT_NAME:-MossView-linux}"

python -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --windowed \
  --name "$OUTPUT_NAME" \
  --add-data "$SCRIPT_DIR/assets:assets" \
  "$SCRIPT_DIR/gui.py"