#!/usr/bin/env bash
# Start Pergen from the repo root (loads venv if present).
#
# Boot path
# ---------
# After the OOD/TDD refactor every route lives in a per-domain Flask
# Blueprint registered through ``backend.app_factory.create_app()``.
# The legacy ``backend.app`` module is now an 87-line shim with **zero
# routes** kept only for in-tree imports — booting it directly serves
# 404s for every URL.  We default to the factory and let an operator
# override with ``FLASK_APP=backend.app`` if they really need the shim.
#
# Config selection
# ----------------
# ``FLASK_CONFIG`` (default: ``development``) is read by ``create_app``
# and resolves to one of: ``default`` / ``development`` / ``testing`` /
# ``production`` from ``backend/config/app_config.py::CONFIG_MAP``.
# Production refuses to start with the placeholder SECRET_KEY.
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

# Wave-7.2: auto-load .env from the repo root so operators can keep
# PERGEN_API_TOKEN / PERGEN_DEV_OPEN_API / SECRET_KEY in a file instead
# of sourcing them every time. Flask CLI also loads .env when
# python-dotenv is installed (see requirements.txt) — this shell-side
# block is the belt-and-suspenders fallback for venvs that don't yet
# have python-dotenv.
#
# Existing shell env vars take precedence over .env (.env is a
# baseline, not an override). We parse line-by-line so we can skip any
# KEY that is already set in the environment.
if [[ -f ".env" ]]; then
  while IFS= read -r _line || [[ -n "$_line" ]]; do
    # Skip blanks and comments.
    [[ -z "${_line// }" ]] && continue
    [[ "$_line" =~ ^[[:space:]]*# ]] && continue
    # KEY=VALUE form only; ignore anything else (defensive).
    [[ "$_line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
    _key="${BASH_REMATCH[1]}"
    _val="${BASH_REMATCH[2]}"
    # Strip optional surrounding single or double quotes.
    if [[ "$_val" =~ ^\".*\"$ ]] || [[ "$_val" =~ ^\'.*\'$ ]]; then
      _val="${_val:1:${#_val}-2}"
    fi
    # Don't clobber existing shell exports.
    if [[ -z "${!_key:-}" ]]; then
      export "$_key"="$_val"
    fi
  done < ".env"
  unset _line _key _val
fi

# Default to the App Factory so all 12 blueprints register.
# Override with ``FLASK_APP=backend.app`` to boot the legacy shim.
export FLASK_APP="${FLASK_APP:-backend.app_factory:create_app}"
export FLASK_CONFIG="${FLASK_CONFIG:-development}"
HOST="${FLASK_RUN_HOST:-127.0.0.1}"
PORT="${FLASK_RUN_PORT:-5000}"

echo "Pergen starting"
echo "  FLASK_APP    = ${FLASK_APP}"
echo "  FLASK_CONFIG = ${FLASK_CONFIG}"
echo "  URL          = http://${HOST}:${PORT}/"

exec python -m flask run --host "$HOST" --port "$PORT" "$@"
