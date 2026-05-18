import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import OPCODE_CLI, BASE_DIR, ALLOWED_OUTPUT_ROOTS


class OpenCodeService:
    def __init__(self, runtime_logs_dir):
        self.logs_dir = runtime_logs_dir
        self.events_path = runtime_logs_dir / "opencode_events.jsonl"
        self._detection = self._detect()

    def _detect(self):
        if not os.path.isfile(OPCODE_CLI):
            return {"installed": False, "error": f"Not found at {OPCODE_CLI}"}
        if not os.access(OPCODE_CLI, os.X_OK):
            return {"installed": False, "error": "Not executable"}
        try:
            r = subprocess.run([OPCODE_CLI, "--version"], capture_output=True, text=True, timeout=15)
            version = (r.stdout or r.stderr or "").strip()[:50]
            return {"installed": True, "version": version, "executable_path": OPCODE_CLI, "usable": False}
        except Exception as exc:
            return {"installed": False, "error": str(exc)}

    def _is_usable(self):
        if not self._detect().get("installed"):
            return False
        try:
            r = subprocess.run(
                [OPCODE_CLI, "providers", "list"],
                capture_output=True, text=True, timeout=10,
            )
            stdout = r.stdout + r.stderr
            return "0 credentials" not in stdout.lower() and r.returncode == 0
        except Exception:
            return False

    def status(self):
        d = self._detect()
        usable = self._is_usable()
        d["usable"] = usable
        return {
            "detection": d,
            "enabled": d.get("installed", False) and usable,
        }

    def run(self, task, output_folder=None, mode="supervised_apply"):
        if not self._detect().get("installed"):
            return self._error("OpenCode unavailable: CLI not found", task)
        if not self._is_usable():
            return self._error("OpenCode unavailable: provider not configured (run 'opencode providers login')", task)
        task_id = str(uuid.uuid4())
        cwd = str(BASE_DIR)
        output_dir = output_folder or str(BASE_DIR / "outputs")
        of_text = f"\nOutput folder: {output_dir}\nAllowed roots: {[str(r) for r in ALLOWED_OUTPUT_ROOTS]}\n"

        cmd = [OPCODE_CLI, "run", "--print-logs", task + of_text]

        stdout_lines = []
        stderr_lines = []
        returncode = -1

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, cwd=cwd,
                env=self._safe_env(),
            )
            returncode = proc.returncode
            stdout_lines = proc.stdout.splitlines() if proc.stdout else []
            stderr_lines = proc.stderr.splitlines() if proc.stderr else []
        except subprocess.TimeoutExpired:
            returncode = -9
            stderr_lines = ["OpenCode timed out after 120s"]
        except Exception as exc:
            returncode = -1
            stderr_lines = [f"OpenCode error: {exc}"]

        stdout_text = "\n".join(stdout_lines[-200:])
        stderr_text = "\n".join(stderr_lines[-200:])

        files_changed = self._detect_changed_files()
        created_from_stdout = self._parse_created_files(stdout_lines)
        files_changed = list(set(files_changed + created_from_stdout))

        result = {
            "task_id": task_id,
            "task": task,
            "mode": mode,
            "returncode": returncode,
            "stdout_summary": stdout_text[:5000],
            "stderr_summary": stderr_text[:2000],
            "files_changed": files_changed,
            "final_status": "completed" if returncode == 0 else "failed",
        }
        self._log(result)
        return result

    def _safe_env(self):
        env = os.environ.copy()
        keep = {"PATH", "HOME", "USER", "SHELL", "LANG", "LC_ALL", "TERM"}
        return {k: v for k, v in env.items() if k in keep}

    def _detect_changed_files(self):
        changed = []
        try:
            r = subprocess.run(
                ["git", "status", "--short"], capture_output=True, text=True,
                timeout=10, cwd=str(BASE_DIR),
            )
            if r.returncode == 0:
                for line in r.stdout.strip().splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) >= 2:
                        changed.append(parts[1])
        except Exception:
            pass
        # FS fallback: find new files in outputs/ and templates/
        try:
            for root_dir in ["outputs", "templates"]:
                d = BASE_DIR / root_dir
                if d.exists():
                    for f in sorted(d.rglob("*")):
                        if f.is_file() and f.suffix in (".html", ".py", ".css", ".js", ".txt", ".md"):
                            changed.append(str(f.relative_to(BASE_DIR)))
        except Exception:
            pass
        return list(set(changed))

    def _parse_created_files(self, lines):
        import re
        files = []
        for line in lines:
            m = re.search(r'`([^`]+)`', line)
            if m:
                fname = m.group(1).strip().lstrip("/")
                if fname.endswith((".html", ".py", ".css", ".js", ".txt", ".md")):
                    files.append(fname)
        return files

    def _log(self, result):
        try:
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _error(self, msg, task):
        return {
            "task_id": str(uuid.uuid4()),
            "task": task,
            "final_status": "failed",
            "files_changed": [],
            "stderr_summary": msg,
        }
