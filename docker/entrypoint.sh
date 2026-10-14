#!/bin/sh
# Apply database migrations, then start the web server.
set -eu

alembic upgrade head

# Only Caddy on the internal compose network can reach this port, so forwarded headers are trusted.
exec uvicorn app.main:create_app --factory \
    --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips '*' \
    --no-server-header \
    --log-level "${LOG_LEVEL:-info}"
