#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8090}"   # Render provides PORT; fallback for local runs

uvicorn fidden.asgi:application \
  --host 0.0.0.0 \
  --port "$PORT" \
  --ws websockets
