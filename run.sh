#!/usr/bin/env bash
# Launch the Ren'Py AI Translator (macOS / Linux).
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import webview" 2>/dev/null; then
  echo "Installing dependencies..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
fi

python main.py
