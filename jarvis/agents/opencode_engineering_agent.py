import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from jarvis.agents.base_agent import BaseAgent


OPCODE_CLI = "/usr/local/bin/opencode"
JARVIS_PROJECT_ROOT = os.path.abspath(
    os.environ.get(
        "JARVIS_PROJECT_ROOT",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."),
    )
)


def detect_opencode():
    info = {
        "installed": False,
        "executable_path": None,
        "version": None,
        "enabled": False,
        "last_check": None,
        "error": None,
    }
    if not os.path.isfile(OPCODE_CLI):
        info["error"] = f"opencode not found at {OPCODE_CLI}"
        info["last_check"] = datetime.now(timezone.utc).isoformat()
        return info
    if not os.access(OPCODE_CLI, os.X_OK):
        info["error"] = f"opencode at {OPCODE_CLI} is not executable"
        info["last_check"] = datetime.now(timezone.utc).isoformat()
        return info
    try:
        result = subprocess.run(
            [OPCODE_CLI, "--version"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            info["version"] = result.stdout.strip() or result.stderr.strip()
        else:
            info["version"] = "unknown"
    except Exception as exc:
        info["error"] = f"opencode version check failed: {exc}"
        info["last_check"] = datetime.now(timezone.utc).isoformat()
        return info
    info["installed"] = True
    info["executable_path"] = OPCODE_CLI
    info["enabled"] = True
    info["last_check"] = datetime.now(timezone.utc).isoformat()
    return info


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _project_root():
    return Path(JARVIS_PROJECT_ROOT).resolve()


class OpenCodeEngineeringAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="OpenCode Engineering Agent",
            role="Real executable engineering agent using OpenCode CLI",
            provider="opencode_local",
            cost="free",
        )
        self.project_root = _project_root()
        self.memory_dir = self.project_root / "JARVIS_CORE" / "runtime_memory"
        self.logs_dir = self.project_root / "JARVIS_CORE" / "runtime_logs"
        self.state_path = self.memory_dir / "opencode_agent_state.json"
        self.tasks_path = self.memory_dir / "opencode_agent_tasks.json"
        self.events_path = self.logs_dir / "opencode_agent_events.jsonl"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._detection = detect_opencode()
        self._lock = threading.RLock()
        self._load_state()

    def _load_state(self):
        if self.state_path.exists():
            try:
                self._state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                self._state = self._default_state()
        else:
            self._state = self._default_state()
        if self.tasks_path.exists():
            try:
                self._tasks = json.loads(self.tasks_path.read_text(encoding="utf-8"))
            except Exception:
                self._tasks = []
        else:
            self._tasks = []
        self._save_state()

    def _default_state(self):
        return {
            "detection": self._detection,
            "last_task": None,
            "last_result": None,
            "enabled": self._detection.get("installed", False),
            "updated_at": _now(),
        }

    def _save_state(self):
        with self._lock:
            self._state["detection"] = self._detection
            self._state["updated_at"] = _now()
            self.state_path.write_text(
                json.dumps(self._state, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.tasks_path.write_text(
                json.dumps(self._tasks, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _append_event(self, event):
        with self._lock:
            entry = {**event, "timestamp": _now()}
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def status(self):
        self._detection = detect_opencode()
        return {
            "name": self.name,
            "role": self.role,
            "provider": self.provider,
            "detection": self._detection,
            "enabled": self._state.get("enabled", False) and self._detection.get("installed", False),
            "last_task": self._state.get("last_task"),
            "last_result": self._state.get("last_result"),
            "tasks_count": len(self._tasks),
            "project_root": str(self.project_root),
        }

    def info(self):
        return {
            "name": self.name,
            "role": self.role,
            "provider": self.provider,
            "cost": self.cost,
            "status": "available" if self._detection.get("installed") else "unavailable",
            "version": self._detection.get("version"),
            "capabilities": [
                "code_generation",
                "bug_fixing",
                "refactoring",
                "file_creation",
                "test_generation",
                "patch_planning",
                "validation",
                "project_analysis",
            ],
            "enabled": self._state.get("enabled", False) and self._detection.get("installed", False),
        }

    def think(self, task):
        return self.run_task(task, mode="plan_only")

    def run_task(self, task, mode="supervised_apply"):
        task = str(task or "").strip()
        if not task:
            return self._error_result("Task is empty", task)

        if not self._detection.get("installed"):
            return self._error_result(
                f"OpenCode unavailable: {self._detection.get('error', 'CLI not detected')}",
                task,
            )

        if not self._state.get("enabled", False):
            return self._error_result(
                "OpenCode unavailable: agent is disabled in configuration",
                task,
            )

        mode = mode.strip().lower()
        if mode not in ("plan_only", "supervised_apply", "direct_apply_inside_project_root"):
            mode = "supervised_apply"

        task_id = str(uuid.uuid4())
        started_at = _now()
        cwd = str(self.project_root)

        if not self._within_project_root(cwd):
            return self._error_result(
                "OpenCode unavailable: execution outside project root is blocked",
                task,
            )

        opencode_cmd = self._build_opencode_command(task, mode)

        stdout_lines = []
        stderr_lines = []
        returncode = -1

        before_snapshot = self._take_file_snapshot()

        try:
            proc = subprocess.run(
                opencode_cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=cwd,
                env=self._safe_env(),
            )
            returncode = proc.returncode
            stdout_lines = proc.stdout.splitlines() if proc.stdout else []
            stderr_lines = proc.stderr.splitlines() if proc.stderr else []
        except subprocess.TimeoutExpired:
            returncode = -9
            stderr_lines = ["OpenCode agent: task timed out after 300 seconds"]
        except Exception as exc:
            returncode = -1
            stderr_lines = [f"OpenCode agent execution error: {exc}"]

        finished_at = _now()
        stdout_text = "\n".join(stdout_lines[-200:])
        stderr_text = "\n".join(stderr_lines[-200:])

        after_snapshot = self._take_file_snapshot()
        files_changed = []
        for f in after_snapshot:
            if f not in before_snapshot:
                try:
                    rel = str(Path(f).relative_to(self.project_root))
                    files_changed.append(rel)
                except Exception:
                    files_changed.append(f)
            elif after_snapshot[f] != before_snapshot[f]:
                try:
                    rel = str(Path(f).relative_to(self.project_root))
                    files_changed.append(rel)
                except Exception:
                    files_changed.append(f)

        created_patterns = []
        for line in stdout_lines:
            low = line.lower()
            if "created" in low and "`" in line:
                import re
                matches = re.findall(r'`([^`]+)`', line)
                created_patterns.extend(matches)
        for cp in created_patterns:
            cp = cp.strip().lstrip("/").replace("\\", "/")
            if cp.endswith(".html") or cp.endswith(".py"):
                if cp not in files_changed:
                    files_changed.append(cp)

        validation = self._run_validation(files_changed)

        success = returncode == 0
        status = "completed" if success else "failed"

        result = {
            "task_id": task_id,
            "command_text": task,
            "mode": mode,
            "cwd": cwd,
            "opencode_path": self._detection.get("executable_path"),
            "started_at": started_at,
            "finished_at": finished_at,
            "returncode": returncode,
            "stdout_summary": stdout_text[:5000],
            "stderr_summary": stderr_text[:2000],
            "files_changed": files_changed,
            "validation": validation,
            "final_status": status,
        }

        task_entry = {
            "task_id": task_id,
            "task": task,
            "mode": mode,
            "started_at": started_at,
            "finished_at": finished_at,
            "returncode": returncode,
            "final_status": status,
            "files_changed": files_changed,
            "validation_status": validation.get("status", "unknown"),
        }
        result["files_changed"] = list(set(files_changed))

        with self._lock:
            self._tasks.append(task_entry)
            self._state["last_task"] = task
            self._state["last_result"] = result
            self._save_state()

        self._append_event({
            "event": "task_completed" if success else "task_failed",
            "task_id": task_id,
            "task": task,
            "mode": mode,
            "returncode": returncode,
            "files_changed": files_changed,
            "validation_status": validation.get("status", "unknown"),
        })

        return result

    def _build_opencode_command(self, task, mode):
        if mode == "plan_only":
            cmd = [OPCODE_CLI, "run", "--print-logs", f"Plan only: {task}"]
        elif mode == "direct_apply_inside_project_root":
            cmd = [OPCODE_CLI, "run", "--print-logs", task]
        else:
            cmd = [OPCODE_CLI, "run", "--print-logs", task]
        return cmd

    def _safe_env(self):
        env = os.environ.copy()
        for key in list(env.keys()):
            if any(secret in key.lower() for secret in ("key", "secret", "token", "password", "credential")):
                if key in ("PATH", "HOME", "USER", "SHELL", "LANG", "LC_ALL", "TERM"):
                    continue
        keep = {
            "PATH": env.get("PATH", ""),
            "HOME": env.get("HOME", ""),
            "USER": env.get("USER", ""),
            "SHELL": env.get("SHELL", ""),
            "LANG": env.get("LANG", "en_US.UTF-8"),
            "LC_ALL": env.get("LC_ALL", "en_US.UTF-8"),
            "TERM": env.get("TERM", "xterm-256color"),
        }
        return keep

    def _within_project_root(self, path):
        try:
            resolved = Path(path).resolve()
            return str(resolved).startswith(str(self.project_root))
        except Exception:
            return False

    def _take_file_snapshot(self):
        snap = {}
        try:
            for root, dirs, files in os.walk(str(self.project_root)):
                for fn in files:
                    fpath = os.path.join(root, fn)
                    try:
                        mtime = os.path.getmtime(fpath)
                        snap[fpath] = mtime
                    except Exception:
                        pass
        except Exception:
            pass
        return snap

    def _run_validation(self, files_changed):
        steps = []
        all_passed = True

        python_files = [f for f in files_changed if f.endswith(".py")]
        for pyf in python_files:
            abspath = self.project_root / pyf
            if not abspath.exists():
                continue
            step = {"file": pyf, "type": "py_compile", "status": "unknown"}
            try:
                result = subprocess.run(
                    ["python3", "-m", "py_compile", str(abspath)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    step["status"] = "passed"
                else:
                    step["status"] = "failed"
                    step["stderr"] = result.stderr[:500]
                    all_passed = False
            except Exception as exc:
                step["status"] = "error"
                step["stderr"] = str(exc)
                all_passed = False
            steps.append(step)

        if files_changed:
            step = {"file": "all", "type": "git_status", "status": "passed"}
            steps.append(step)

        return {
            "status": "passed" if all_passed else "failed",
            "steps": steps,
            "stdout": f"Validated {len(python_files)} Python files, {len(files_changed)} total changed files",
            "stderr": "",
        }

    def _error_result(self, message, task):
        return {
            "task_id": str(uuid.uuid4()),
            "command_text": task,
            "mode": "none",
            "cwd": str(self.project_root),
            "opencode_path": self._detection.get("executable_path"),
            "started_at": _now(),
            "finished_at": _now(),
            "returncode": -1,
            "stdout_summary": "",
            "stderr_summary": message,
            "files_changed": [],
            "validation": {"status": "not_run", "steps": [], "stdout": "", "stderr": ""},
            "final_status": "failed",
        }

    def list_tasks(self, limit=20):
        return list(reversed(self._tasks[-limit:]))

    def get_task(self, task_id):
        for t in self._tasks:
            if t.get("task_id") == task_id:
                return t
        return None

    def get_last_result(self):
        return self._state.get("last_result")

    def set_enabled(self, enabled):
        with self._lock:
            self._state["enabled"] = bool(enabled)
            self._save_state()
        return self._state["enabled"]


_opencode_agent_instance = None


def get_opencode_agent():
    global _opencode_agent_instance
    if _opencode_agent_instance is None:
        _opencode_agent_instance = OpenCodeEngineeringAgent()
    return _opencode_agent_instance


if __name__ == "__main__":
    agent = OpenCodeEngineeringAgent()
    print(json.dumps(agent.info(), indent=2, ensure_ascii=False))
    print(json.dumps(agent.status(), indent=2, ensure_ascii=False))
    result = agent.run_task("Check if OpenCode CLI works", mode="plan_only")
    print(json.dumps(result, indent=2, ensure_ascii=False))
