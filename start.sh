#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [ ! -x .venv/bin/uvicorn ]; then
  printf '%s\n' 'Run ./setup.sh first.'
  exit 1
fi
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
