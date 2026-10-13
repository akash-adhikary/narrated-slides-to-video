#!/usr/bin/env bash
# One-time setup for Narrated Slides Studio. No admin password or Homebrew needed.
# Installs everything inside this folder (.venv) plus a few caches in your home folder.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf "\n\033[1m%s\033[0m\n" "$1"; }

say "1/4  Checking for uv (the Python installer)…"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null; then
  echo "     Installing uv into your home folder…"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  export PATH="$HOME/.local/bin:$PATH"
fi
echo "     ok"

say "2/4  Installing the app (this downloads Python and the libraries it needs)…"
uv venv .venv --python 3.11 -q --allow-existing
uv pip install --python .venv/bin/python -q -e .
echo "     ok"

say "3/4  Installing the browser used to draw the slides…"
.venv/bin/python -m playwright install chromium >/dev/null
echo "     ok"

say "4/4  Downloading the narrator voice and preparing music (a few minutes the first time)…"
.venv/bin/python - <<'PY'
import warnings; warnings.filterwarnings("ignore")
from html2mp4 import cli, music
cli.synthesize([{"chunks": ["Setup complete."]}], "af_heart", 0.9, cli.CACHE / "tts")
for style in music.STYLES: music.ensure(style, cli.CACHE / "music")
PY
echo "     ok"

say "All set."
echo "  To open the Studio:  double-click \"Open Studio.command\" in this folder,"
echo "  or run:              ./studio.sh"
echo
