from flask import Blueprint, jsonify, request

from jarvis_app.services.output_folder_service import OutputFolderService

output_bp = Blueprint("output", __name__)
_output = OutputFolderService()


@output_bp.route("/jarvis/api/output-folders")
def list_output_folders():
    return jsonify(_output.list_folders())


@output_bp.route("/jarvis/api/output-folder/set", methods=["POST"])
def set_output_folder():
    payload = request.json or {}
    folder = payload.get("folder", "")
    return jsonify(_output.set_folder(folder))


@output_bp.route("/jarvis/api/output-folder/create", methods=["POST"])
def create_output_folder():
    payload = request.json or {}
    folder = payload.get("folder", "")
    return jsonify(_output.create_folder(folder))


@output_bp.route("/jarvis/api/output-folder/current")
def current_output_folder():
    return jsonify(_output.get_current())
