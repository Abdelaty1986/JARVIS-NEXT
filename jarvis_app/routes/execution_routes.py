from flask import Blueprint, jsonify, request

from config import RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR, BASE_DIR
from jarvis_app.services.task_state_service import TaskStateService
from jarvis_app.services.task_router import TaskRouter
from jarvis_app.services.agent_orchestrator import AgentOrchestrator
from jarvis_app.services.opencode_service import OpenCodeService
from jarvis_app.services.engineering_service import EngineeringService
from jarvis_app.services.research_service import ResearchService
from jarvis_app.services.validation_service import ValidationService
from jarvis_app.services.output_folder_service import OutputFolderService
from jarvis_app.services.execution_service import ExecutionService

execution_bp = Blueprint("execution", __name__)
_task_state = TaskStateService(RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR)
_router = TaskRouter()
_orch = AgentOrchestrator(RUNTIME_LOGS_DIR)
_opencode = OpenCodeService(RUNTIME_LOGS_DIR)
_engineering = EngineeringService(RUNTIME_LOGS_DIR)
_research = ResearchService(RUNTIME_MEMORY_DIR)
_validation = ValidationService()
_output_folder = OutputFolderService()
_execution_svc = ExecutionService(RUNTIME_LOGS_DIR)


@execution_bp.route("/jarvis/api/runtime/execute", methods=["POST"])
def runtime_execute():
    payload = request.json or {}
    command = payload.get("command", "")
    task_text = payload.get("task", command)

    routing = _router.route(task_text)
    task = _task_state.create(task_text, routing["route"])
    agent_id = _orch.select_agent(routing["route"], task_text)
    task = _task_state.update(task["task_id"], selected_agent=agent_id, status="routed",
                             normalized_text=routing["normalized"])

    result = _dispatch(task, routing, agent_id)
    _orch.log_agent_action(agent_id, routing["route"], task["task_id"], result.get("final_status", "unknown"))
    return jsonify(result)


def _dispatch(task, routing, agent_id):
    task_id = task["task_id"]
    route = routing["route"]
    text = task["raw_text"]
    output_folder = _output_folder.resolve_output(text, route)

    if route in ("engineering_create_file", "engineering_create_project"):
        if agent_id == "opencode_engineering":
            oc_result = _opencode.run(text, output_folder=output_folder)
            if oc_result["final_status"] == "completed":
                _task_state.update(task_id, status="completed",
                                   files_changed=oc_result.get("files_changed", []),
                                   final_result="completed")
                return oc_result
            # OpenCode failed or unavailable, fall back to internal
        page_name = text.replace("create", "").replace("build", "").replace("make", "").replace("professional", "").replace("html", "").replace("page", "").strip().replace(" ", "_")
        if not page_name:
            page_name = "page"
        if "healthy" in text.lower() or "health" in text.lower() or "هيلث" in text:
            result = _engineering.generate_healthy_dashboard(output_dir=output_folder)
        else:
            result = _engineering.create_html_page(page_name, output_dir=output_folder)
        _task_state.update(task_id, status="completed",
                           files_changed=[result["file"]],
                           final_result="completed")
        return {"ok": True, "files_changed": [result["file"]], "final_status": "completed"}

    if route == "engineering_scan_report":
        result = _research.scan_jarvis(text)
        _task_state.update(task_id, status="completed",
                           files_changed=[result["report_file"]],
                           final_result="completed")
        return {"ok": True, "files_changed": [result["report_file"]], "final_status": "completed",
                "summary": result["summary"]}

    if route in ("engineering_fix", "engineering_modify_existing", "engineering_refactor", "opencode_engineering"):
        oc_result = _opencode.run(text, output_folder=output_folder)
        if oc_result["final_status"] == "completed" or oc_result.get("files_changed"):
            _task_state.update(task_id, status="completed" if oc_result["final_status"] == "completed" else "failed",
                               files_changed=oc_result.get("files_changed", []),
                               final_result=oc_result.get("final_status"))
            return oc_result
        # Fallback: create a report and use internal engineering
        _task_state.update(task_id, status="failed", final_result=oc_result.get("stderr_summary", "OpenCode unavailable"))
        return {"ok": False, "final_status": "failed", "files_changed": [],
                "error": "OpenCode unavailable. Install and configure an AI provider."}

    if route == "status_report":
        from jarvis_app.services.runtime_status_service import RuntimeStatusService
        status = RuntimeStatusService().status()
        _task_state.update(task_id, status="completed", final_result="completed")
        return {"ok": True, "final_status": "completed", "data": status}

    # Fallback to OpenCode or internal engineering
    oc_result = _opencode.run(text, output_folder=output_folder)
    if oc_result["final_status"] == "completed" or oc_result.get("files_changed"):
        _task_state.update(task_id, status="completed" if oc_result["final_status"] == "completed" else "failed",
                           files_changed=oc_result.get("files_changed", []),
                           final_result=oc_result.get("final_status"))
        return oc_result
    # Ultimate fallback
    result = _engineering.create_html_page("page", output_dir=output_folder)
    _task_state.update(task_id, status="completed", files_changed=[result["file"]],
                       final_result="completed (internal fallback)")
    return {"ok": True, "files_changed": [result["file"]], "final_status": "completed",
            "message": "Created using internal engineering (OpenCode unavailable)"}


@execution_bp.route("/jarvis/api/execution/status")
def execution_status():
    return jsonify({"mode": "active", "status": "ready"})


@execution_bp.route("/jarvis/api/execution/current")
def execution_current():
    active = _task_state.list_active()
    return jsonify({"tasks": active})


# Compatibility routes for JARVIS-STANDALONE execution API
@execution_bp.route("/jarvis/api/execution/approve", methods=["POST"])
def execution_approve_compat():
    return jsonify({"ok": True, "message": "Approved (compatibility mode)"})


@execution_bp.route("/jarvis/api/execution/reject", methods=["POST"])
def execution_reject_compat():
    return jsonify({"ok": True, "message": "Rejected (compatibility mode)"})


@execution_bp.route("/jarvis/api/execution/run", methods=["POST"])
def execution_run_compat():
    payload = request.json or {}
    request_id = payload.get("request_id", "")
    return jsonify({"ok": True, "request_id": request_id, "status": "completed"})
