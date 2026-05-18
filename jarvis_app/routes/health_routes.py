from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/jarvis/api/status")
def api_status():
    return jsonify({
        "status": "ok",
        "service": "JARVIS-NEXT",
        "version": "1.0",
    })


@health_bp.route("/jarvis/api/health")
def health_check():
    return jsonify({"healthy": True, "status": "ok"})


@health_bp.route("/")
def root():
    return jsonify({
        "service": "JARVIS-NEXT",
        "description": "Conversational AI Engineering Runtime",
        "endpoints": {
            "chat": "/jarvis/api/chat/message",
            "runtime": "/jarvis/api/runtime/status",
            "agents": "/jarvis/api/agents",
            "opencode": "/jarvis/api/agents/opencode/status",
            "voice": "/jarvis/api/voice/status",
            "mobile": "/jarvis/mobile",
        }
    })
