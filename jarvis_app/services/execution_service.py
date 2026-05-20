import json
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from config import BASE_DIR, ALLOWED_OUTPUT_ROOTS
from jarvis_app.utils.safety import is_safe_command, is_safe_output_path


class ExecutionService:
    def __init__(self, runtime_logs_dir):
        self.logs_dir = runtime_logs_dir
        self.events_path = runtime_logs_dir / "execution_events.jsonl"

    def execute(self, command, task_id=None):
        safe, reason = is_safe_command(command)
        if not safe:
            return self._result(False, command, None, "", reason, task_id)
        try:
            cmd_list = shlex.split(command)
            proc = subprocess.run(
                cmd_list, shell=False, capture_output=True, text=True, timeout=30,
                cwd=str(BASE_DIR),
            )
            return self._result(
                proc.returncode == 0, command, proc.returncode,
                proc.stdout, proc.stderr, task_id,
            )
        except subprocess.TimeoutExpired:
            return self._result(False, command, -9, "", "Timed out", task_id)
        except Exception as exc:
            return self._result(False, command, -1, "", str(exc), task_id)

    def _result(self, ok, command, returncode, stdout, stderr, task_id):
        r = {
            "ok": ok,
            "command": command,
            "returncode": returncode,
            "stdout": stdout[:5000],
            "stderr": stderr[:2000],
            "task_id": task_id,
        }
        self._log(r)
        return r

    def _log(self, result):
        try:
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        except Exception:
            pass
