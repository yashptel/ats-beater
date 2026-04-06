#!/usr/bin/env bash
set -euo pipefail

PORT=${1:-8000}

# Kill anything running on the port
PID=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "Killing process(es) on port $PORT: $PID"
    kill -9 $PID 2>/dev/null || true
    sleep 0.5
fi

echo "Starting server on port $PORT..."
uv run uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
