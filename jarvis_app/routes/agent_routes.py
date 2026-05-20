from flask import Blueprint, jsonify, request

from config import RUNTIME_LOGS_DIR, RUNTIME_MEMORY_DIR
from jarvis_app.services.agent_orchestrator import AgentOrchestrator
from jarvis_app.services.opencode_service import OpenCodeService

agent_bp = Blueprint("agents", __name__)
_orch = AgentOrchestrator(RUNTIME_LOGS_DIR)
_opencode = OpenCodeService(RUNTIME_LOGS_DIR)


@agent_bp.route("/jarvis/api/agents")
def list_agents():
    try:
        agents = _orch.list_agents()
        return jsonify({
            "agents": agents,
            "opencode_detection": _opencode.status().get("detection"),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to list agents: {e}"}), 500


@agent_bp.route("/jarvis/api/agents/opencode/status")
def opencode_status():
    try:
        return jsonify(_opencode.status())
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to get opencode status: {e}"}), 500


@agent_bp.route("/jarvis/api/agents/opencode/run", methods=["POST"])
def opencode_run():
    try:
        payload = request.json or {}
        task = payload.get("task", "")
        mode = payload.get("mode", "supervised_apply")
        output_folder = payload.get("output_folder")
        if not task:
            return jsonify({"ok": False, "error": "task is required"}), 400
        result = _opencode.run(task, output_folder=output_folder, mode=mode)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": f"OpenCode run failed: {e}"}), 500


@agent_bp.route("/jarvis/api/agents/opencode/tasks")
def opencode_tasks():
    return jsonify([])


@agent_bp.route("/jarvis/api/agents/opencode/task/<task_id>")
def opencode_task(task_id):
    return jsonify({"error": "not found"}), 404
