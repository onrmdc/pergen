#!/usr/bin/env bash
# Start Pergen from the repo root (loads venv if present).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -f "venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "venv/bin/activate"
elif [[ -f ".venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source ".venv/bin/activate"
else
  echo "No venv found. From this directory run:"
  echo "  python3 -m venv venv"
  echo "  source venv/bin/activate"
  echo "  python -m pip install -r requirements.txt"
  exit 1
fi

export FLASK_APP="${FLASK_APP:-backend.app}"
HOST="${FLASK_RUN_HOST:-127.0.0.1}"
PORT="${FLASK_RUN_PORT:-5000}"
exec python -m flask run --host "$HOST" --port "$PORT" "$@"
