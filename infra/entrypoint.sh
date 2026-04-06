#!/bin/sh
set -e

# Run migrations if RUN_MIGRATIONS=true (skip on normal cold starts)
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "Running database migrations..."
    uv run alembic upgrade head
fi

exec uv run uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers --forwarded-allow-ips='*'
