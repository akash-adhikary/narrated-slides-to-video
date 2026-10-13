#!/usr/bin/env bash
# One-time setup: creates .venv, installs html2mp4 and the headless browser it renders with.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null; then
  echo "ffmpeg is required. macOS: brew install ffmpeg   |   Ubuntu: sudo apt install ffmpeg" >&2; exit 1
fi

if command -v uv >/dev/null; then
  uv venv .venv --python 3.11 -q
  uv pip install --python .venv/bin/python -q -e .
else
  PY=$(command -v python3.12 || command -v python3.11 || command -v python3.10 || true)
  [ -n "$PY" ] || { echo "Python 3.10–3.12 is required (or install uv: https://docs.astral.sh/uv/)" >&2; exit 1; }
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -e .
fi
.venv/bin/python -m playwright install chromium

echo
echo "Done. Try it:"
echo "  source .venv/bin/activate"
echo "  html2mp4 examples/example.html"
