from datetime import datetime


class JarvisMobileControlCenter:
    """
    Lightweight mobile control center data provider for JARVIS.
    Reads actual execution mode from the mode manager.
    """

    def snapshot(self):
        from jarvis.runtime.execution_mode_manager import read_mode
        from jarvis.agents.opencode_engineering_agent import detect_opencode
        mode_data = read_mode()
        current_mode = mode_data.get("mode", "controlled_real_execution")

        agents = [
            "Local Reviewer",
            "Gemini",
            "Groq",
            "OpenRouter",
        ]
        opencode_detection = detect_opencode()
        if opencode_detection.get("installed"):
            agents.append("OpenCode Engineering Agent")

        return {
            "status": "online",
            "mode": current_mode,
            "voice": "enabled",
            "runtime": "ready",
            "agents": agents,
            "safety": {
                "sandbox": current_mode == "simulation_only",
                "rollback": True,
                "signed_receipts": True,
                "gated_apply": current_mode != "simulation_only",
            },
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
