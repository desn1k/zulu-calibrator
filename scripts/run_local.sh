#!/bin/sh
# Local run on this computer only (no auth yet — never expose it on a network).
# Usage from the repository root:  sh scripts/run_local.sh
set -eu
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3.12}"
PORT="${PORT:-8000}"

if [ ! -x .venv/bin/python ]; then
    echo "Creating .venv with $PYTHON ..."
    "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.lock

export DATABASE_URL="sqlite:///./data/local.db"
.venv/bin/python -m alembic upgrade head

echo "Open http://127.0.0.1:$PORT/ (Ctrl+C to stop)"
exec .venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "$PORT"
