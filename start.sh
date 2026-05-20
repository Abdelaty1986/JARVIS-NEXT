#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Load .env if present (overrides existing env vars)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

export PYTHONPATH="${PYTHONPATH}:$(pwd)/JARVIS_CORE"
echo "Starting JARVIS-NEXT..."
python app.py
