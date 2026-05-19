import os
import re
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, request

from config import RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR, BASE_DIR
from jarvis_app.services.task_state_service import TaskStateService
from jarvis_app.services.task_router import TaskRouter
from jarvis_app.services.agent_orchestrator import AgentOrchestrator

execution_bp = Blueprint("execution", __name__)
_task_state = TaskStateService(RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR)
_router = TaskRouter()
_orch = AgentOrchestrator(RUNTIME_LOGS_DIR)

# ---------------------------------------------------------------------------
# Action detection – map free-text commands to a known action name
# ---------------------------------------------------------------------------

def _detect_action(text):
    lowered = text.lower().strip()
    if "git status" in lowered or lowered in ("status", "check status"):
        return "status_check"
    if any(w in lowered for w in ("health", "compile", "py_compile", "pycompile")):
        return "health_check"
    if "list" in lowered and "file" in lowered:
        return "list_files"
    if ("read" in lowered and "file" in lowered) or lowered.startswith("read "):
        return "read_file"
    if "ui" in lowered and any(w in lowered for w in ("report", "inspect", "check")):
        return "ui_report"
    if "route" in lowered and any(w in lowered for w in ("report", "list", "show")):
        return "route_report"
    if "status" in lowered:
        return "status_check"
    return "status_check"


def _create_plan(action, text):
    plans = {
        "status_check": "Run `git status --short` to check repository working tree state",
        "health_check": "Run `python -m py_compile app.py` to verify application syntax",
        "list_files": "Safely enumerate project files (max depth 3, excluding hidden/compiled)",
        "read_file": "Read contents of a project file (project-root confined, secrets blocked)",
        "ui_report": "Inspect `mobile_control_center.html` – structure, API endpoints, issues",
        "route_report": "Inspect all registered Flask route files and their URL patterns",
    }
    return plans.get(action, f"Execute task on route: {text[:120]}")


# ---------------------------------------------------------------------------
# Action execution – each known action performs a real, safe operation
# ---------------------------------------------------------------------------

def _execute_action(action, task_id, text):
    cwd = str(BASE_DIR)

    if action == "status_check":
        return _run_safe_command(["git", "status", "--short"], cwd,
                                 summary_success=lambda out: f"Git status: {len([l for l in out.splitlines() if l.strip()])} change(s)" if out.strip() else "Working tree clean",
                                 summary_failure="git status failed")

    if action == "health_check":
        return _run_safe_command(["python", "-m", "py_compile", "app.py"], cwd,
                                 summary_success="Syntax OK",
                                 summary_failure=lambda err: f"Syntax error: {err[:200]}")

    if action == "list_files":
        return _action_list_files()

    if action == "read_file":
        return _action_read_file(text)

    if action == "ui_report":
        return _action_ui_report()

    if action == "route_report":
        return _action_route_report()

    return False, "", "", f"Unknown action: {action}"


def _run_safe_command(cmd, cwd, summary_success=None, summary_failure=None):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=cwd)
        ok = proc.returncode == 0
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        if ok:
            summary = summary_success(stdout) if callable(summary_success) else (summary_success or "OK")
        else:
            summary = summary_failure(stderr) if callable(summary_failure) else (summary_failure or "Failed")
        return ok, stdout, stderr, summary
    except subprocess.TimeoutExpired:
        return False, "", "Timed out (30s)", "Command timed out"
    except Exception as e:
        return False, "", str(e), f"Error: {e}"


def _action_list_files():
    try:
        files = []
        for root, dirs, fnames in os.walk(str(BASE_DIR)):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules")]
            depth = root.replace(str(BASE_DIR), "").count(os.sep)
            if depth > 3:
                dirs.clear()
                continue
            for fname in fnames:
                if fname.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(root, fname), str(BASE_DIR))
                files.append(rel)
        stdout = "\n".join(sorted(files))
        return True, stdout, "", f"Listed {len(files)} files"
    except Exception as e:
        return False, "", str(e), f"Error: {e}"


def _action_read_file(text):
    # Extract the filename from the command
    tokens = text.replace("read", "").replace("file", "").replace("safely", "").strip().split()
    filename = None
    for t in tokens:
        t = t.strip("'\".,;:")
        if t.endswith((".py", ".html", ".css", ".js", ".json", ".txt", ".md", ".yml", ".yaml",
                       ".cfg", ".ini", ".toml", ".sh", ".env.example", ".gitignore")):
            filename = t
            break
    if not filename:
        for t in text.split():
            t = t.strip("'\".,;:")
            if "/" in t or "\\" in t or t.endswith((".py", ".html", ".css")):
                filename = t
                break
    if not filename:
        return False, "", "No filename found in command", "Error: specify a file to read"

    target = (BASE_DIR / filename).resolve()
    try:
        target.relative_to(BASE_DIR)
    except ValueError:
        return False, "", f"Access denied: {filename} is outside project root", "Error: file access denied"

    blocked_prefixes = (".env", ".git/", "config.py", "SECRET")
    rel = str(target.relative_to(BASE_DIR))
    if any(rel.startswith(p) for p in blocked_prefixes):
        return False, "", f"Access denied: {filename} is a blocked path", "Error: file access denied"

    if not target.is_file():
        return False, "", f"File not found: {filename}", f"Error: {filename} does not exist"

    try:
        content = target.read_text(encoding="utf-8")
        return True, content[:5000], "", f"Read {filename} ({len(content)} bytes)"
    except Exception as e:
        return False, "", str(e), f"Error reading file: {e}"


def _action_ui_report():
    tpl = BASE_DIR / "templates" / "jarvis" / "mobile_control_center.html"
    if not tpl.exists():
        return False, "", "Template not found", "Error: template file missing"
    content = tpl.read_text(encoding="utf-8")
    lines = content.split("\n")
    api_endpoints = sorted(set(re.findall(r"/jarvis/api/[a-zA-Z/_-]+", content)))

    report = [
        f"File        : {tpl}",
        f"Lines       : {len(lines)}",
        f"Size        : {len(content)} bytes",
        f"API calls   : {len(api_endpoints)}",
        "",
        "--- API Endpoints referenced ---",
    ]
    report.extend(f"  {ep}" for ep in api_endpoints)

    report += ["", "--- HTML Structure ---"]
    for line in lines:
        s = line.strip()
        if '<div' in s and ('class=' in s or 'id=' in s):
            m = re.search(r'class=["\']([^"\']+)["\']', s) or re.search(r'id=["\']([^"\']+)["\']', s)
            label = m.group(1) if m else ""
            report.append(f"  <div>  {label}"[:120])

    stdout = "\n".join(report)
    return True, stdout, "", f"UI Report: {len(lines)} lines, {len(api_endpoints)} API endpoints"


def _action_route_report():
    routes_dir = BASE_DIR / "jarvis_app" / "routes"
    if not routes_dir.is_dir():
        return False, "", "Routes directory not found", "Error: routes dir missing"

    report = ["=== Registered Route Files ==="]
    route_files = sorted(routes_dir.glob("*_routes.py"))
    total = 0
    for rf in route_files:
        text = rf.read_text(encoding="utf-8")
        routes = re.findall(r'@\w+_bp\.route\(["\']([^"\']+)["\']', text)
        if not routes:
            continue
        total += len(routes)
        report.append(f"\n{rf.name}  ({len(routes)} route(s)):")
        report.extend(f"  {r}" for r in routes)

    stdout = "\n".join(report)
    return True, stdout, "", f"Route Report: {len(route_files)} files, {total} route(s)"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@execution_bp.route("/jarvis/api/runtime/execute", methods=["POST"])
def runtime_execute():
    payload = request.json or {}
    command = payload.get("command", "")
    task_text = payload.get("task", command)

    if not command.strip():
        return jsonify({"ok": False, "error": "No command provided"}), 400

    routing = _router.route(task_text)
    task = _task_state.create(task_text, routing["route"])
    agent_id = _orch.select_agent(routing["route"], task_text)

    action = _detect_action(task_text)
    plan = _create_plan(action, task_text)

    task = _task_state.update(
        task["task_id"],
        selected_agent=agent_id,
        status="routed",
        normalized_text=routing["normalized"],
        action=action,
        plan=plan,
    )
    task = _task_state.update(task["task_id"], status="waiting_approval")

    _orch.log_agent_action(agent_id, routing["route"], task["task_id"], "waiting_approval")

    return jsonify({
        "ok": True,
        "task_id": task["task_id"],
        "status": "waiting_approval",
        "route": routing["route"],
        "action": action,
        "agent_id": agent_id,
        "plan": plan,
    })


@execution_bp.route("/jarvis/api/execution/approve", methods=["POST"])
def execution_approve():
    payload = request.json or {}
    task_id = payload.get("task_id")

    if task_id:
        task = _task_state.get(task_id)
        if not task:
            return jsonify({"ok": False, "error": "Task not found"}), 404
        if task.get("status") not in ("waiting_approval",):
            return jsonify({"ok": False, "error": f"Task state is '{task.get('status')}', expected 'waiting_approval'"}), 400
        _task_state.update(task_id, status="approved", approval_state="approved")
    else:
        all_tasks = _task_state.list_all(999)
        waiting = [t for t in all_tasks if t.get("status") == "waiting_approval"]
        if not waiting:
            return jsonify({"ok": False, "error": "No tasks waiting for approval"}), 404
        task_id = waiting[0]["task_id"]
        _task_state.update(task_id, status="approved", approval_state="approved")

    return jsonify({"ok": True, "task_id": task_id, "status": "approved", "message": "Task approved"})


@execution_bp.route("/jarvis/api/execution/run", methods=["POST"])
def execution_run():
    payload = request.json or {}
    task_id = payload.get("task_id")

    def _resolve_task():
        nonlocal task_id
        if task_id:
            t = _task_state.get(task_id)
            if not t:
                return None, "Task not found"
            if t.get("status") not in ("approved", "waiting_approval"):
                return None, f"Task state is '{t['status']}', expected 'approved' or 'waiting_approval'"
            return t, None
        all_tasks = _task_state.list_all(999)
        for status_filter in ("approved", "waiting_approval"):
            candidates = [t for t in all_tasks if t.get("status") == status_filter]
            if candidates:
                return candidates[0], None
        return None, "No tasks ready to run"

    task, err = _resolve_task()
    if err:
        return jsonify({"ok": False, "error": err}), 404
    if not task:
        return jsonify({"ok": False, "error": "Task not found"}), 404

    task_id = task["task_id"]
    if task.get("status") == "waiting_approval":
        _task_state.update(task_id, status="approved", approval_state="approved")

    _task_state.update(task_id, status="running")

    action = task.get("action") or _detect_action(task.get("raw_text", ""))
    text = task.get("raw_text", "")

    success, stdout, stderr, summary = _execute_action(action, task_id, text)

    final_status = "completed" if success else "failed"
    _task_state.update(
        task_id,
        status=final_status,
        stdout=stdout,
        stderr=stderr,
        final_result=summary,
    )

    return jsonify({
        "ok": success,
        "task_id": task_id,
        "status": final_status,
        "stdout": stdout,
        "stderr": stderr,
        "result": summary,
    })


@execution_bp.route("/jarvis/api/execution/reject", methods=["POST"])
def execution_reject():
    payload = request.json or {}
    task_id = payload.get("task_id")

    if task_id:
        task = _task_state.get(task_id)
        if not task:
            return jsonify({"ok": False, "error": "Task not found"}), 404
        _task_state.update(task_id, status="rejected", approval_state="rejected")
    else:
        all_tasks = _task_state.list_all(999)
        waiting = [t for t in all_tasks if t.get("status") == "waiting_approval"]
        if waiting:
            _task_state.update(waiting[0]["task_id"], status="rejected", approval_state="rejected")

    return jsonify({"ok": True, "message": "Task rejected"})


@execution_bp.route("/jarvis/api/execution/status")
def execution_status():
    return jsonify({"mode": "active", "status": "ready"})


@execution_bp.route("/jarvis/api/execution/current")
def execution_current():
    active = _task_state.list_active()
    return jsonify({"tasks": active})
