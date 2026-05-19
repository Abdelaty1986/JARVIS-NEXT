import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import OPCODE_CLI, BASE_DIR, ALLOWED_OUTPUT_ROOTS


class OpenCodeService:
    def __init__(self, runtime_logs_dir):
        self.logs_dir = runtime_logs_dir
        self.events_path = runtime_logs_dir / "opencode_events.jsonl"
        self._detection_cache = None
        self._cache_ttl = 30
        self._cache_time = 0
        self._last_error = None
        self._last_health_time = None

    def _run_cmd(self, args, timeout=15, env=None):
        result = {
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": None,
            "timed_out": False,
        }
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout,
                cwd=str(BASE_DIR), env=env,
            )
            result["returncode"] = proc.returncode
            result["stdout"] = (proc.stdout or "").strip()
            result["stderr"] = (proc.stderr or "").strip()
        except subprocess.TimeoutExpired:
            result["timed_out"] = True
            result["error"] = f"Timed out after {timeout}s"
        except FileNotFoundError:
            result["error"] = f"Binary not found: {args[0]}"
        except PermissionError:
            result["error"] = f"Permission denied: {args[0]}"
        except OSError as e:
            result["error"] = f"OS error: {e}"
        except Exception as e:
            result["error"] = f"Unexpected: {e}"
        return result

    def _detect(self):
        now = time.time()
        if self._detection_cache and (now - self._cache_time) < self._cache_ttl:
            return self._detection_cache

        cli_path = OPCODE_CLI
        version = None
        cli_works = False
        errors = []

        # Check 1: file exists
        if not os.path.isfile(cli_path):
            errors.append(f"Not found at {cli_path}")
            result = {"installed": False, "cli_works": False, "version": None,
                       "executable_path": cli_path, "errors": errors, "error": errors[0] if errors else None}
            self._detection_cache = result
            self._cache_time = now
            return result

        # Check 2: executable
        if not os.access(cli_path, os.X_OK):
            errors.append("Not executable")
            result = {"installed": True, "cli_works": False, "version": None,
                       "executable_path": cli_path, "errors": errors, "error": errors[0] if errors else None}
            self._detection_cache = result
            self._cache_time = now
            return result

        # Check 3: resolve symlink to real path
        try:
            real_path = os.path.realpath(cli_path)
        except Exception:
            real_path = cli_path

        # Check 4: run --version
        version_result = self._run_cmd([cli_path, "--version"], timeout=10)
        if version_result["error"]:
            errors.append(f"version check error: {version_result['error']}")
        elif version_result["returncode"] != 0:
            errors.append(f"version check exit={version_result['returncode']}: {version_result['stderr'][:100]}")
        else:
            version = (version_result["stdout"] or "").strip()[:50]
            cli_works = True

        # Check 5: which resolves
        which_path = None
        try:
            import shutil
            which_path = shutil.which("opencode")
        except Exception:
            pass

        # Check 6: PATH contains the dir
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        cli_dir = os.path.dirname(real_path)
        in_path = cli_dir in path_dirs

        result = {
            "installed": True,
            "cli_works": cli_works,
            "version": version,
            "executable_path": cli_path,
            "real_path": real_path,
            "which_resolves": which_path == cli_path or which_path == real_path,
            "in_path": in_path,
            "path_dirs_count": len(path_dirs),
            "errors": errors,
            "error": errors[0] if errors else None,
            "version_check": version_result,
        }

        self._detection_cache = result
        self._cache_time = now
        return result

    def _is_usable(self):
        detect = self._detect()
        if not detect.get("cli_works"):
            return False
        try:
            r = subprocess.run(
                [OPCODE_CLI, "providers", "list"],
                capture_output=True, text=True, timeout=10,
            )
            stdout = (r.stdout or "") + (r.stderr or "")
            has_creds = "0 credentials" not in stdout.lower()
            return r.returncode == 0 and has_creds
        except Exception:
            return False

    def health(self):
        self._last_health_time = datetime.now(timezone.utc).isoformat()
        detect = self._detect()
        usable = self._is_usable()
        return {
            "available": detect.get("cli_works", False),
            "usable": usable,
            "cli_path": detect.get("executable_path"),
            "real_path": detect.get("real_path"),
            "version": detect.get("version"),
            "which_resolves": detect.get("which_resolves", False),
            "in_path": detect.get("in_path", False),
            "path_dirs_count": detect.get("path_dirs_count", 0),
            "installed": detect.get("installed", False),
            "cli_works": detect.get("cli_works", False),
            "errors": detect.get("errors", []),
            "last_error": self._last_error,
            "last_health_time": self._last_health_time,
            "has_credentials": usable,
            "fallback": "internal_engineering",
            "version_check": detect.get("version_check", {}),
            "cache_ttl": self._cache_ttl,
        }

    def status(self):
        d = self._detect()
        usable = self._is_usable()
        return {
            "detection": d,
            "enabled": d.get("cli_works", False) and usable,
        }

    def run(self, task, output_folder=None, mode="supervised_apply"):
        detect = self._detect()
        if not detect.get("cli_works"):
            err = "OpenCode unavailable: CLI not working"
            self._last_error = err
            return self._error(err, task)

        if not self._is_usable():
            err = "OpenCode unavailable: no AI provider configured (run 'opencode providers login')"
            self._last_error = err
            return self._error(err, task)

        task_id = str(uuid.uuid4())
        cwd = str(BASE_DIR)
        output_dir = output_folder or str(BASE_DIR / "outputs")
        of_text = f"\nOutput folder: {output_dir}\nAllowed roots: {[str(r) for r in ALLOWED_OUTPUT_ROOTS]}\n"
        full_task = task + of_text

        cmd = [OPCODE_CLI, "run", "--print-logs", full_task]

        stdout_lines = []
        stderr_lines = []
        returncode = -1
        run_error = None
        timed_out = False

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, cwd=cwd,
            )
            returncode = proc.returncode
            stdout_lines = proc.stdout.splitlines() if proc.stdout else []
            stderr_lines = proc.stderr.splitlines() if proc.stderr else []
        except subprocess.TimeoutExpired:
            returncode = -9
            timed_out = True
            run_error = "Timed out after 120s"
            stderr_lines = [f"OpenCode timed out after 120s"]
        except FileNotFoundError:
            returncode = -1
            run_error = f"Binary not found: {OPCODE_CLI}"
            stderr_lines = [run_error]
        except PermissionError:
            returncode = -1
            run_error = f"Permission denied: {OPCODE_CLI}"
            stderr_lines = [run_error]
        except Exception as exc:
            returncode = -1
            run_error = f"Execution error: {exc}"
            stderr_lines = [run_error]

        self._last_error = run_error

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
            "timed_out": timed_out,
            "error": run_error,
        }
        self._log(result)
        return result

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
            "error": msg,
        }
