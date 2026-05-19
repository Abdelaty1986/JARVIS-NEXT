from flask import Blueprint, jsonify, request

from config import RUNTIME_LOGS_DIR
from jarvis_app.services.voice_service import VoiceService

voice_bp = Blueprint("voice", __name__)
_voice = VoiceService()


@voice_bp.route("/jarvis/api/voice/status")
def voice_status():
    return jsonify(_voice.status())


@voice_bp.route("/jarvis/api/voice/transcribe", methods=["POST"])
def voice_transcribe():
    audio = request.get_data()
    return jsonify(_voice.transcribe(audio))


@voice_bp.route("/jarvis/api/voice/respond", methods=["POST"])
def voice_respond():
    payload = request.json or {}
    text = payload.get("text", "")
    return jsonify(_voice.respond(text))


@voice_bp.route("/jarvis/api/voice/stop", methods=["POST"])
def voice_stop():
    return jsonify(_voice.stop())


@voice_bp.route("/jarvis/api/voice/mute", methods=["POST"])
def voice_mute():
    return jsonify(_voice.mute())


@voice_bp.route("/jarvis/api/voice/speak", methods=["POST"])
def voice_speak():
    payload = request.json or {}
    text = payload.get("text", "")
    if not text:
        return jsonify({"ok": False, "error": "No text provided"}), 400
    result = _voice.respond(text)
    return jsonify(result)
