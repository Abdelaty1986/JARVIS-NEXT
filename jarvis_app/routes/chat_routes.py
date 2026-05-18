from flask import Blueprint, jsonify, request

from config import RUNTIME_MEMORY_DIR
from jarvis_app.services.conversation_service import ConversationService

chat_bp = Blueprint("chat", __name__)
_conversation = ConversationService(RUNTIME_MEMORY_DIR)


@chat_bp.route("/jarvis/api/chat/message", methods=["POST"])
def chat_message():
    payload = request.json or {}
    message = payload.get("message", "")
    result = _conversation.process_message(message)
    return jsonify(result)


@chat_bp.route("/jarvis/api/chat/history")
def chat_history():
    return jsonify(_conversation.get_history())


@chat_bp.route("/jarvis/api/chat/clear", methods=["POST"])
def chat_clear():
    return jsonify(_conversation.clear_history())
