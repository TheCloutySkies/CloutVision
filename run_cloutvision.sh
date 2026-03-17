#!/usr/bin/env bash
set -euo pipefail

PROJECT="/Users/cloutyskies/Desktop/CloutVisionMac"
VENV="$PROJECT/venv"

cd "$PROJECT"

if [[ ! -d "$VENV" ]]; then
  echo "Creating virtual environment at $VENV ..."
  python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

if ! python -c "import PyQt6" >/dev/null 2>&1; then
  echo "Installing PyQt6 into venv ..."
  python -m pip install --upgrade pip >/dev/null
  python -m pip install "PyQt6>=6.4.0"
fi

exec python "$PROJECT/cloutvision_qt.py"
