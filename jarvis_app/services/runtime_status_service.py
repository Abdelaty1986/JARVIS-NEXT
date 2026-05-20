import os
import shutil
import subprocess
from pathlib import Path

from config import BASE_DIR


def _find_opencode():
    path = os.environ.get("OPCODE_CLI")
    if path:
        return path
    path = shutil.which("opencode")
    if path:
        return path
    return str(BASE_DIR / "bin" / "opencode")


class RuntimeStatusService:
    def status(self):
        return {
            "mode": "active",
            "runtime": "ready",
            "version": "JARVIS-NEXT 1.0",
            "python": self._python_version(),
            "opencode": self._opencode_version(),
            "project_root": str(BASE_DIR),
        }

    def _python_version(self):
        try:
            r = subprocess.run(["python3", "--version"], capture_output=True, text=True, timeout=5)
            return r.stdout.strip() or r.stderr.strip()
        except Exception:
            return "unknown"

    def _opencode_version(self):
        try:
            r = subprocess.run([_find_opencode(), "--version"], capture_output=True, text=True, timeout=5)
            return (r.stdout or r.stderr or "").strip()[:30]
        except Exception:
            return "not detected"
