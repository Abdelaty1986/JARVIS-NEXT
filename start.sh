#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export PYTHONPATH="${PYTHONPATH}:$(pwd)/JARVIS_CORE"
echo "Starting JARVIS-NEXT..."
python app.py
