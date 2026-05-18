from flask import Blueprint, jsonify, render_template, request
from datetime import datetime

from config import BASE_DIR, RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR

mobile_bp = Blueprint("mobile", __name__)


@mobile_bp.route("/jarvis/mobile")
def jarvis_mobile():
    try:
        from jarvis_app.services.runtime_status_service import RuntimeStatusService
        from jarvis_app.services.agent_orchestrator import AgentOrchestrator
        orch = AgentOrchestrator(RUNTIME_LOGS_DIR)
        data = {
            "status": "online",
            "mode": "active",
            "voice": "enabled",
            "runtime": "ready",
            "agents": [a.get("name", a.get("agent_id", "Agent")) for a in orch.list_agents()],
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return render_template("jarvis/mobile_control_center.html", data=data)
    except Exception as exc:
        return f"<html><body><h1>JARVIS-NEXT</h1><p>Mobile UI error: {exc}</p></body></html>"


@mobile_bp.route("/jarvis/mobile/api/status")
def jarvis_mobile_api_status():
    from jarvis_app.services.runtime_status_service import RuntimeStatusService
    return jsonify(RuntimeStatusService().status())


@mobile_bp.route("/jarvis/mobile/api/runtime/insight-snapshot")
@mobile_bp.route("/jarvis/mobile/api/insight-snapshot")
def jarvis_mobile_insight_snapshot():
    from jarvis_app.services.agent_orchestrator import AgentOrchestrator
    orch = AgentOrchestrator(RUNTIME_LOGS_DIR)
    return jsonify({
        "system_status": "online",
        "runtime_mode": "active",
        "voice_enabled": True,
        "agents_count": len(orch.list_agents()),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })


# --- Compatibility shims for JARVIS-STANDALONE mobile API ---

@mobile_bp.route("/jarvis/mobile/api/runtime/execution-mode")
def mobile_execution_mode():
    return jsonify({"mode": "active", "status": "ready"})


@mobile_bp.route("/jarvis/mobile/api/runtime/execution-summary")
def mobile_execution_summary():
    return jsonify({
        "active": 0, "completed": 0, "failed": 0,
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@mobile_bp.route("/jarvis/mobile/api/runtime/activity-feed")
def mobile_activity_feed():
    return jsonify({"events": [], "count": 0})


@mobile_bp.route("/jarvis/mobile/api/runtime/insights")
def mobile_insights():
    return jsonify({"insights": [], "count": 0})


@mobile_bp.route("/jarvis/mobile/api/runtime/correlation")
def mobile_correlation():
    return jsonify({"correlation": []})


@mobile_bp.route("/jarvis/mobile/api/runtime/command")
@mobile_bp.route("/jarvis/mobile/api/command", methods=["GET", "POST"])
def mobile_command():
    if request.method == "POST":
        payload = request.json or {}
        command = payload.get("command", "")
        from jarvis_app.services.task_router import TaskRouter
        from jarvis_app.services.task_state_service import TaskStateService
        from jarvis_app.services.agent_orchestrator import AgentOrchestrator
        router = TaskRouter()
        routing = router.route(command)
        task_state = TaskStateService(RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR)
        task = task_state.create(command, routing["route"])
        orch = AgentOrchestrator(RUNTIME_LOGS_DIR)
        agent_id = orch.select_agent(routing["route"], command)
        task_state.update(task["task_id"], selected_agent=agent_id, status="routed",
                         normalized_text=routing["normalized"])
        return jsonify({
            "accepted": True,
            "command_id": task["task_id"],
            "route": routing["route"],
            "agent_id": agent_id,
        })
    return jsonify({"commands": []})


@mobile_bp.route("/jarvis/mobile/api/runtime/patch/status")
def mobile_patch_status():
    from jarvis_app.services.task_state_service import TaskStateService
    ts = TaskStateService(RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR)
    return jsonify({"patch": ts.list_active()[:1] or [], "status": "idle"})


@mobile_bp.route("/jarvis/mobile/api/runtime/patch/approve", methods=["POST"])
def mobile_patch_approve():
    return jsonify({"ok": True, "message": "Patch approved (compatibility mode)"})


@mobile_bp.route("/jarvis/mobile/api/runtime/patch/reject", methods=["POST"])
def mobile_patch_reject():
    return jsonify({"ok": True, "message": "Patch rejected (compatibility mode)"})


@mobile_bp.route("/jarvis/mobile/api/runtime/intent/parse", methods=["POST"])
def mobile_intent_parse():
    payload = request.json or {}
    text = payload.get("text", "")
    from jarvis_app.utils.text_normalizer import detect_task_type, normalize_text
    return jsonify({
        "intent": detect_task_type(text),
        "normalized": normalize_text(text),
        "confidence": 0.85,
    })


@mobile_bp.route("/jarvis/mobile/api/runtime/supervision")
def mobile_supervision():
    return jsonify({"alerts": [], "warnings": [], "healthy": True})


@mobile_bp.route("/jarvis/mobile/api/architecture/drift")
def mobile_drift():
    return jsonify({"drift_score": 0, "stable": True})


@mobile_bp.route("/jarvis/mobile/api/architecture/trends")
def mobile_trends():
    return jsonify({"trends": []})


@mobile_bp.route("/jarvis/mobile/api/architecture/hotspots")
def mobile_hotspots():
    return jsonify({"hotspots": []})


@mobile_bp.route("/jarvis/mobile/api/architecture/priorities")
def mobile_priorities():
    return jsonify({"priorities": []})


@mobile_bp.route("/jarvis/mobile/api/architecture/dependency-reasoning")
def mobile_dependency_reasoning():
    return jsonify({"dependencies": []})


@mobile_bp.route("/jarvis/mobile/api/architecture/recommendations")
def mobile_recommendations():
    return jsonify({"recommendations": []})


@mobile_bp.route("/jarvis/mobile/api/erp/intelligence")
def mobile_erp_intelligence():
    return jsonify({"autonomy": "standalone", "erp_routes": []})


@mobile_bp.route("/jarvis/mobile/api/scheduler/run", methods=["POST"])
def mobile_scheduler_run():
    return jsonify({"ok": True, "status": "completed"})


@mobile_bp.route("/jarvis/mobile/api/worker/tick", methods=["POST"])
def mobile_worker_tick():
    return jsonify({"ok": True, "status": "tick_completed"})
