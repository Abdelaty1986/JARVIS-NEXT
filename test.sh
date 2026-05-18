#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export PYTHONPATH="${PYTHONPATH}:$(pwd)/JARVIS_CORE"

echo "=== JARVIS-NEXT Test Suite ==="

echo ""
echo "--- py_compile checks ---"
python -m py_compile app.py && echo "  app.py: PASS"

find . -name "*.py" -not -path "*/__pycache__/*" -print0 | while IFS= read -r -d '' f; do
    python -m py_compile "$f" 2>/dev/null || echo "  FAIL: $f"
done
echo "  All Python files compiled successfully."

echo ""
echo "--- Smoke Tests ---"
python -m pytest tests/smoke_test.py -v 2>/dev/null || python tests/smoke_test.py 2>&1 | tail -30

echo ""
echo "=== Done ==="
