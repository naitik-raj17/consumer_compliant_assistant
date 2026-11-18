#!/usr/bin/env bash
# Linux one-folder build for local testing. Output: dist/ConsumerGuard/ConsumerGuard
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python
# Standalone Pythons (uv/pyenv) keep libtk/libtcl in their own lib dir; let PyInstaller find them.
PYLIB="$("$PY" -c 'import sys; print(sys.base_prefix)')/lib"
export LD_LIBRARY_PATH="$PYLIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
"$PY" -m PyInstaller --noconfirm --clean --onedir --windowed \
  --name ConsumerGuard \
  --add-data "kb_seed:kb_seed" \
  --collect-data customtkinter \
  main.py
echo "Built: dist/ConsumerGuard/ConsumerGuard"
