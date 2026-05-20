import os
import traceback

from flask import Flask, jsonify

from config import SECRET_KEY, DEBUG, TEMPLATES_DIR, STATIC_DIR, BASE_DIR


def create_app():
    app = Flask(
        __name__,
        template_folder=str(TEMPLATES_DIR),
        static_folder=str(STATIC_DIR),
        static_url_path="/static",
    )
    app.secret_key = SECRET_KEY
    app.config["DEBUG"] = DEBUG
    app.config["BASE_DIR"] = BASE_DIR

    _register_blueprints(app)
    _register_error_handlers(app)
    return app


def _register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"ok": False, "error": str(e)}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"ok": False, "error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"ok": False, "error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"ok": False, "error": "Internal server error"}), 500

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        if app.config.get("DEBUG"):
            tb = traceback.format_exc()
            return jsonify({"ok": False, "error": str(e), "traceback": tb}), 500
        return jsonify({"ok": False, "error": "Internal server error"}), 500


def _register_blueprints(app):
    from jarvis_app.routes.health_routes import health_bp
    from jarvis_app.routes.mobile_routes import mobile_bp
    from jarvis_app.routes.chat_routes import chat_bp
    from jarvis_app.routes.runtime_routes import runtime_bp
    from jarvis_app.routes.execution_routes import execution_bp
    from jarvis_app.routes.engineering_routes import engineering_bp
    from jarvis_app.routes.voice_routes import voice_bp
    from jarvis_app.routes.agent_routes import agent_bp
    from jarvis_app.routes.output_routes import output_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(mobile_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(runtime_bp)
    app.register_blueprint(execution_bp)
    app.register_blueprint(engineering_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(output_bp)

    _ensure_dirs(app)


def _ensure_dirs(app):
    from pathlib import Path
    dirs = [
        app.config.get("BASE_DIR", BASE_DIR) / "outputs",
        app.config.get("BASE_DIR", BASE_DIR) / "runtime_memory",
        app.config.get("BASE_DIR", BASE_DIR) / "runtime_logs",
        app.config.get("BASE_DIR", BASE_DIR) / "runtime_memory" / "reports",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
