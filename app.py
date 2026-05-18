#!/usr/bin/env python3
"""JARVIS-NEXT: Conversational AI Engineering Runtime."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "JARVIS_CORE"))

from jarvis_app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5005))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"JARVIS-NEXT starting on port {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
