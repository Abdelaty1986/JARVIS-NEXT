from flask import Blueprint, jsonify, request
from datetime import datetime

from config import RUNTIME_LOGS_DIR
from jarvis_app.services.execution_service import ExecutionService
from jarvis_app.services.runtime_status_service import RuntimeStatusService
from jarvis_app.services.task_state_service import TaskStateService
from config import RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR

runtime_bp = Blueprint("runtime", __name__)
_task_state = TaskStateService(RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR)
_execution = ExecutionService(RUNTIME_LOGS_DIR)


@runtime_bp.route("/jarvis/api/runtime/status")
def runtime_status():
    return jsonify(RuntimeStatusService().status())


@runtime_bp.route("/jarvis/api/runtime/tasks")
def runtime_tasks():
    return jsonify(_task_state.list_all())


@runtime_bp.route("/jarvis/api/runtime/active-tasks")
def runtime_active_tasks():
    return jsonify(_task_state.list_active())


@runtime_bp.route("/jarvis/api/system-health")
def system_health():
    return jsonify({
        "healthy": True,
        "status": "ok",
        "mode": "active",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })


@runtime_bp.route("/jarvis/api/execution/history")
def execution_history():
    return jsonify(_task_state.list_history())


@runtime_bp.route("/jarvis/api/execution/request", methods=["POST"])
def execution_request_compat():
    payload = request.json or {}
    command = payload.get("command", "")
    from jarvis_app.services.task_router import TaskRouter
    from jarvis_app.services.agent_orchestrator import AgentOrchestrator
    from jarvis_app.services.opencode_service import OpenCodeService
    from jarvis_app.services.engineering_service import EngineeringService
    from jarvis_app.services.research_service import ResearchService
    from jarvis_app.services.output_folder_service import OutputFolderService
    router = TaskRouter()
    routing = router.route(command)
    task = _task_state.create(command, routing["route"])
    agent_id = AgentOrchestrator(RUNTIME_LOGS_DIR).select_agent(routing["route"], command)
    _task_state.update(task["task_id"], selected_agent=agent_id, status="routed",
                       normalized_text=routing["normalized"])
    return jsonify({
        "ok": True,
        "detected_mode": routing["route"],
        "flow": "engineering_task",
        "patch_state": {
            "patch_id": task["task_id"],
            "apply_status": "WAITING_APPROVAL",
            "approval_state": "waiting_patch_approval",
            "apply_supported": True,
            "requested_task": command,
            "operations": [],
            "files_changed": [],
        }
    })
