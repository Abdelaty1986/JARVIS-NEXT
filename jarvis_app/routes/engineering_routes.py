import flask

from flask import Blueprint, jsonify, render_template, request, current_app
from werkzeug.routing import Rule
from datetime import datetime

from config import RUNTIME_LOGS_DIR, RUNTIME_MEMORY_DIR, TEMPLATES_DIR
from jarvis_app.services.task_state_service import TaskStateService
from jarvis_app.services.engineering_execution_service import EngineeringExecutionService
from jarvis_app.services.agent_orchestrator import AgentOrchestrator
from jarvis_app.services.opencode_service import OpenCodeService
from jarvis_app.services.validation_service import ValidationService

engineering_bp = Blueprint("engineering", __name__)
_task_state = TaskStateService(RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR)
_engine = EngineeringExecutionService(RUNTIME_LOGS_DIR)
_orch = AgentOrchestrator(RUNTIME_LOGS_DIR)
_validation = ValidationService()
_opencode = OpenCodeService(RUNTIME_LOGS_DIR)


@engineering_bp.route("/jarvis/api/engineering/execute", methods=["POST"])
def engineering_execute():
    try:
        payload = request.json or {}
        command = payload.get("command", "")
        task_text = payload.get("task", command)

        if not command.strip():
            return jsonify({"ok": False, "error": "No command provided"}), 400

        action = _engine.detect_action(task_text)
        plan = _engine.create_plan(action, task_text)

        verification = plan.get("verification_status", "matched")
        mismatch_reason = plan.get("mismatch_reason", "")

        task = _task_state.create(task_text, "engineering." + action)
        route_for_agent = f"engineering_{action}"
        agent_id = _orch.select_agent(route_for_agent, task_text)
        _task_state.update(
            task["task_id"],
            selected_agent=agent_id,
            status="parsed",
            normalized_text=command,
            action=action,
            plan_summary=plan.get("plan_summary", ""),
            plan=plan,
        )
        _task_state.update(task["task_id"], status="planning")
        _task_state.update(task["task_id"], status="waiting_approval")
        _orch.log_agent_action(agent_id, action, task["task_id"], "waiting_approval")

        return jsonify({
            "ok": True,
            "task_id": task["task_id"],
            "status": "waiting_approval",
            "action": action,
            "agent_id": agent_id,
            "plan_summary": plan.get("plan_summary", ""),
            "verification": verification,
            "mismatch_reason": mismatch_reason,
            "match_score": plan.get("match_score", 1.0),
            "plan": plan,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Engineering execute failed: {e}"}), 500


@engineering_bp.route("/jarvis/api/engineering/plan", methods=["POST"])
def engineering_plan():
    try:
        payload = request.json or {}
        command = payload.get("command", "")
        task_id = payload.get("task_id")

        if not command and not task_id:
            return jsonify({"ok": False, "error": "Provide command or task_id"}), 400

        if task_id:
            task = _task_state.get(task_id)
            if not task:
                return jsonify({"ok": False, "error": "Task not found"}), 404
            plan = task.get("plan", {})
            return jsonify({"ok": True, "plan": plan})

        action = _engine.detect_action(command)
        plan = _engine.create_plan(action, command)
        return jsonify({
            "ok": True,
            "action": action,
            "verification": plan.get("verification_status", "matched"),
            "mismatch_reason": plan.get("mismatch_reason", ""),
            "match_score": plan.get("match_score", 1.0),
            "plan": plan,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Engineering plan failed: {e}"}), 500


@engineering_bp.route("/jarvis/api/engineering/approve", methods=["POST"])
def engineering_approve():
    payload = request.json or {}
    task_id = payload.get("task_id")

    if task_id:
        task = _task_state.get(task_id)
        if not task:
            return jsonify({"ok": False, "error": "Task not found"}), 404
        if task.get("status") not in ("waiting_approval",):
            return jsonify({
                "ok": False,
                "error": f"Task state is '{task.get('status')}', expected 'waiting_approval'"
            }), 400
        _task_state.update(task_id, status="approved", approval_state="approved")
    else:
        all_tasks = _task_state.list_all(999)
        waiting = [t for t in all_tasks if t.get("status") == "waiting_approval"]
        if not waiting:
            return jsonify({"ok": False, "error": "No task waiting for approval"}), 404
        task_id = waiting[0]["task_id"]
        _task_state.update(task_id, status="approved", approval_state="approved")

    return jsonify({
        "ok": True,
        "task_id": task_id,
        "status": "approved",
        "message": "Engineering task approved",
    })


@engineering_bp.route("/jarvis/api/engineering/apply", methods=["POST"])
def engineering_apply():
    try:
        payload = request.json or {}
        task_id = payload.get("task_id")

        def _resolve():
            nonlocal task_id
            if task_id:
                t = _task_state.get(task_id)
                if not t:
                    return None, "Task not found"
                if t.get("status") not in ("approved", "waiting_approval"):
                    return None, f"State is '{t['status']}', need 'approved' or 'waiting_approval'"
                return t, None
            for st in ("approved", "waiting_approval"):
                candidates = [t for t in _task_state.list_all(999) if t.get("status") == st]
                if candidates:
                    return candidates[0], None
            return None, "No task ready to apply"

        task, err = _resolve()
        if err:
            return jsonify({"ok": False, "error": err}), 404
        if not task:
            return jsonify({"ok": False, "error": "Task not found"}), 404

        task_id = task["task_id"]
        cur_status = task.get("status", "")

        if cur_status in ("completed", "failed", "validating", "applying"):
            return jsonify({
                "ok": cur_status == "completed",
                "task_id": task_id,
                "status": cur_status,
                "created_files": task.get("created_files", []),
                "modified_files": task.get("modified_files", []),
                "final_urls": task.get("final_urls", []),
                "validation": task.get("validation", {}),
                "rollback_snapshot_id": task.get("rollback_snapshot_id"),
                "stdout": task.get("stdout", ""),
                "stderr": task.get("stderr", ""),
                "summary": task.get("final_result", task.get("result", "")),
            })

        if cur_status == "waiting_approval":
            _task_state.update(task_id, status="approved", approval_state="approved")

        _task_state.update(task_id, status="applying")

        plan = task.get("plan", {})
        if not plan:
            action = task.get("action") or _engine.detect_action(task.get("raw_text", ""))
            plan = _engine.create_plan(action, task.get("raw_text", ""))

        result = _engine.apply_plan(plan, task_id)

        _task_state.update(task_id, status="validating")

        for route_info in plan.get("dynamic_routes", []):
            path = route_info.get("path", "")
            template = route_info.get("template", "")
            title = route_info.get("title", "")
            view_func_name = route_info.get("view_func", "generic")

            def _make_view(tp, tt):
                def _view():
                    return render_template(tp, title=tt, data={"status": "online", "page": tt.lower().replace(" ", "-")})
                _view.__name__ = view_func_name
                return _view

            existing = [r for r in current_app.url_map.iter_rules() if r.rule == path]
            if not existing:
                endpoint_name = view_func_name + "_endpoint"
                rule = Rule(path, endpoint=endpoint_name, methods={"GET"})
                current_app.url_map.add(rule)
                current_app.view_functions[endpoint_name] = _make_view(template, title)
                result.setdefault("stdout", "")
                result["stdout"] += f"\nRegistered route: {path}"

        py_files = result.get("created_files", []) + result.get("modified_files", [])
        py_files = [f for f in py_files if f.endswith(".py")]
        if py_files:
            val = _validation.validate_files(py_files)
            result["validation"] = val

        final = "completed" if result.get("ok") else "failed"
        _task_state.update(
            task_id,
            status=final,
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            final_result=result.get("summary", ""),
            created_files=result.get("created_files", []),
            modified_files=result.get("modified_files", []),
            final_urls=result.get("final_urls", []),
            rollback_snapshot_id=result.get("rollback_snapshot_id"),
            validation=result.get("validation", {}),
        )

        return jsonify({
            "ok": result.get("ok", False),
            "task_id": task_id,
            "status": final,
            "action": result.get("action", ""),
            "created_files": result.get("created_files", []),
            "modified_files": result.get("modified_files", []),
            "final_urls": result.get("final_urls", []),
            "validation": result.get("validation", {}),
            "rollback_snapshot_id": result.get("rollback_snapshot_id"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "summary": result.get("summary", ""),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Engineering apply failed: {e}"}), 500


@engineering_bp.route("/jarvis/api/engineering/task/<task_id>")
def engineering_task(task_id):
    try:
        task = _task_state.get(task_id)
        if not task:
            return jsonify({"ok": False, "error": "Task not found"}), 404
        return jsonify(task)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to get task: {e}"}), 500


@engineering_bp.route("/jarvis/api/engineering/status")
def engineering_status():
    try:
        active = _task_state.list_active()
        eng_active = [t for t in active if t.get("route", "").startswith("engineering.")]
        oc = _opencode.health()
        return jsonify({
            "mode": "active",
            "available": True,
            "active_tasks": len(eng_active),
            "active_task": eng_active[0] if eng_active else None,
            "opencode_available": oc.get("available", False),
            "opencode_usable": oc.get("usable", False),
            "opencode_version": oc.get("version"),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Engineering status failed: {e}"}), 500


@engineering_bp.route("/jarvis/api/engineering/history")
def engineering_history():
    try:
        all_tasks = _task_state.list_all(100)
        eng_tasks = [t for t in all_tasks if t.get("route", "").startswith("engineering.")]
        return jsonify({
            "history": eng_tasks,
            "count": len(eng_tasks),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to get history: {e}"}), 500


@engineering_bp.route("/jarvis/api/engineering/dry-run", methods=["POST"])
def engineering_dry_run():
    try:
        payload = request.json or {}
        command = payload.get("command", "")
        if not command.strip():
            return jsonify({"ok": False, "error": "No command provided"}), 400
        action = _engine.detect_action(command)
        plan = _engine.create_plan(action, command)
        return jsonify({
            "ok": True,
            "action": action,
            "plan_summary": plan.get("plan_summary", ""),
            "verification": plan.get("verification_status", "matched"),
            "mismatch_reason": plan.get("mismatch_reason", ""),
            "match_score": plan.get("match_score", 1.0),
            "plan": plan,
            "note": "Dry-run — no files were modified",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Dry-run failed: {e}"}), 500


@engineering_bp.route("/jarvis/api/opencode/health")
def opencode_health():
    health = _opencode.health()
    return jsonify(health)

@engineering_bp.route("/jarvis/about")
def about_page():
    return render_template("jarvis/about.html",
                           title="About",
                           data={"status": "online", "page": "about", "source": "engineering"})


@engineering_bp.route("/jarvis/diagnostics")
def diagnostics_page():
    return render_template("jarvis/diagnostics.html",
                           title="Diagnostics",
                           data={"status": "online", "page": "diagnostics", "source": "engineering"})

@engineering_bp.route("/jarvis/mobile")
def mobile_page():
    return render_template("jarvis/mobile.html",
                           title="Mobile",
                           data={"status": "online", "page": "mobile", "source": "engineering"})

@engineering_bp.route("/jarvis/check")
def check_page():
    return render_template("jarvis/check.html",
                           title="Check",
                           data={"status": "online", "page": "check", "source": "engineering"})


@engineering_bp.route("/jarvis/settings")
def settings_page():
    return render_template("jarvis/settings.html",
                           title="Settings",
                           data={"status": "online", "page": "settings", "source": "engineering"})


@engineering_bp.route("/jarvis/api/settings/ai-safety-check", methods=["POST"])
def ai_safety_check():
    try:
        payload = request.json or {}
        context = payload.get("context", "JARVIS-NEXT runtime")
        toggle_state = payload.get("toggle_state", {})

        try:
            from ai_orchestrator import analyze_with_gemini
            snippet = (
                f"Toggle state: {toggle_state}\n"
                f"Routes registered: {len(list(current_app.url_map.iter_rules()))}\n"
                f"Debug mode: {current_app.config.get('DEBUG', False)}"
            )
            result = analyze_with_gemini(context, snippet)
        except Exception as e:
            return jsonify({"ok": False, "error": f"Gemini analysis failed: {e}"}), 500

        return jsonify({
            "ok": True,
            "result": result,
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"AI safety check failed: {e}"}), 500

@engineering_bp.route("/jarvis/check")
def check_page():
    return render_template("jarvis/check.html",
                           title="Check",
                           data={"status": "online", "page": "check", "source": "engineering"})
