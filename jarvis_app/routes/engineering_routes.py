from flask import Blueprint, jsonify, request
from datetime import datetime

from config import RUNTIME_LOGS_DIR, TEMPLATES_DIR, RUNTIME_MEMORY_DIR
from jarvis_app.services.engineering_service import EngineeringService
from jarvis_app.services.validation_service import ValidationService
from jarvis_app.services.rollback_service import RollbackService

engineering_bp = Blueprint("engineering", __name__)
_engineering = EngineeringService(RUNTIME_LOGS_DIR)
_validation = ValidationService()
_rollback = RollbackService(RUNTIME_LOGS_DIR)


@engineering_bp.route("/jarvis/api/engineering/status")
def engineering_status():
    return jsonify({"mode": "active", "available": True})


@engineering_bp.route("/jarvis/api/engineering/create-page", methods=["POST"])
def engineering_create_page():
    payload = request.json or {}
    page_name = payload.get("page_name", "new_page")
    content = payload.get("content")
    output_dir = payload.get("output_dir")
    result = _engineering.create_html_page(page_name, content=content, output_dir=output_dir)
    return jsonify(result)


@engineering_bp.route("/jarvis/api/engineering/healthy-dashboard", methods=["POST"])
def engineering_healthy_dashboard():
    output_dir = (request.json or {}).get("output_dir")
    result = _engineering.generate_healthy_dashboard(output_dir=output_dir)
    return jsonify(result)


@engineering_bp.route("/jarvis/api/engineering/validate", methods=["POST"])
def engineering_validate():
    payload = request.json or {}
    files = payload.get("files", [])
    return jsonify(_validation.validate_files(files))


# Compatibility routes for JARVIS-STANDALONE engineering API
@engineering_bp.route("/jarvis/api/engineering/current")
def engineering_current():
    from jarvis_app.services.task_state_service import TaskStateService
    ts = TaskStateService(RUNTIME_MEMORY_DIR, RUNTIME_LOGS_DIR)
    active = ts.list_active()
    return jsonify(active[0] if active else {
        "patch_id": None,
        "apply_status": "IDLE",
        "approval_state": "none",
    })


@engineering_bp.route("/jarvis/api/engineering/approve", methods=["POST"])
def engineering_approve_compat():
    return jsonify({"ok": True, "message": "Patch approved (compatibility mode)"})


@engineering_bp.route("/jarvis/api/engineering/reject", methods=["POST"])
def engineering_reject_compat():
    payload = request.json or {}
    reason = payload.get("reason", "")
    return jsonify({"ok": True, "message": f"Patch rejected: {reason}"})


@engineering_bp.route("/jarvis/api/engineering/apply", methods=["POST"])
def engineering_apply_compat():
    return jsonify({"ok": True, "message": "Patch applied (compatibility mode)"})


@engineering_bp.route("/jarvis/api/engineering/rollback", methods=["POST"])
def engineering_rollback_compat():
    return jsonify({"ok": True, "message": "Rollback completed (compatibility mode)"})


@engineering_bp.route("/jarvis/api/engineering/history")
def engineering_history_compat():
    return jsonify({"history": []})


@engineering_bp.route("/jarvis/api/engineering/logs")
def engineering_logs_compat():
    return jsonify({"logs": []})
