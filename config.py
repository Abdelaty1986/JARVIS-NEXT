import os
from pathlib import Path

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).resolve()
JARVIS_CORE_DIR = BASE_DIR / "JARVIS_CORE"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
OUTPUTS_DIR = BASE_DIR / "outputs"
RUNTIME_MEMORY_DIR = BASE_DIR / "runtime_memory"
RUNTIME_LOGS_DIR = BASE_DIR / "runtime_logs"
REPORTS_DIR = RUNTIME_MEMORY_DIR / "reports"

DEFAULT_OUTPUT_DIR = os.environ.get("JARVIS_DEFAULT_OUTPUT_DIR", str(OUTPUTS_DIR))
ALLOWED_OUTPUT_ROOTS = os.environ.get(
    "JARVIS_ALLOWED_OUTPUT_ROOTS",
    f"{BASE_DIR},{OUTPUTS_DIR}",
).split(",")
ALLOWED_OUTPUT_ROOTS = [Path(p.strip()).resolve() for p in ALLOWED_OUTPUT_ROOTS]

SECRET_KEY = os.environ.get("SECRET_KEY", "jarvis-next-dev-key-change-in-production")
DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")

OPCODE_CLI = os.environ.get("OPCODE_CLI", "/usr/local/bin/opencode")

for d in [TEMPLATES_DIR, STATIC_DIR, OUTPUTS_DIR, RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
