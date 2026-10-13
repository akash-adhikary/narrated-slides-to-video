#!/usr/bin/env bash
# Opens Narrated Slides Studio in your browser. Keep this window open while you work.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/html2mp4-studio ]; then
  echo "The app isn't installed yet. Run ./setup.sh first (or double-click \"Install.command\")."; exit 1
fi
exec .venv/bin/html2mp4-studio
