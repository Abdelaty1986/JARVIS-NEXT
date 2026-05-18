import json
from datetime import datetime, timezone

from jarvis_app.utils.text_normalizer import has_arabic


class AgentOrchestrator:
    def __init__(self, runtime_logs_dir):
        self.logs_dir = runtime_logs_dir
        self.events_path = runtime_logs_dir / "agent_events.jsonl"
        self._agents = {}
        self._discover()

    def _discover(self):
        self._agents = {
            "opencode_engineering": {
                "name": "OpenCode Engineering Agent",
                "type": "local_cli",
                "status": "checking",
                "capabilities": [
                    "code_generation", "bug_fixing", "refactoring",
                    "file_creation", "test_generation", "patch_planning",
                    "validation", "project_analysis",
                ],
            },
            "internal_engineering": {
                "name": "Internal Engineering Agent",
                "type": "builtin",
                "status": "available",
                "capabilities": [
                    "patch_planning", "file_creation", "template_generation",
                    "rollback", "validation",
                ],
            },
            "research": {
                "name": "Research Agent",
                "type": "builtin",
                "status": "available",
                "capabilities": [
                    "code_analysis", "bug_detection", "report_generation",
                    "architecture_analysis",
                ],
            },
            "runtime_execution": {
                "name": "Runtime Execution Agent",
                "type": "builtin",
                "status": "available",
                "capabilities": [
                    "command_execution", "shell_access",
                ],
            },
            "voice": {
                "name": "Voice Agent",
                "type": "builtin",
                "status": "available",
                "capabilities": [
                    "speech_to_text", "text_to_speech",
                ],
            },
            "validation": {
                "name": "Validation Agent",
                "type": "builtin",
                "status": "available",
                "capabilities": [
                    "py_compile", "file_check", "syntax_validation",
                ],
            },
            "rollback": {
                "name": "Rollback Agent",
                "type": "builtin",
                "status": "available",
                "capabilities": [
                    "file_restore", "state_revert",
                ],
            },
        }
        self._check_opencode()

    def _check_opencode(self):
        import os, subprocess
        opc = "/usr/local/bin/opencode"
        if os.path.isfile(opc) and os.access(opc, os.X_OK):
            try:
                r = subprocess.run([opc, "--version"], capture_output=True, text=True, timeout=10)
                version = (r.stdout or r.stderr or "").strip()[:20]
                self._agents["opencode_engineering"]["status"] = "available"
                self._agents["opencode_engineering"]["version"] = version
                self._agents["opencode_engineering"]["executable_path"] = opc
            except Exception:
                self._agents["opencode_engineering"]["status"] = "error"
                self._agents["opencode_engineering"]["error"] = "Version check failed"
        else:
            self._agents["opencode_engineering"]["status"] = "unavailable"
            self._agents["opencode_engineering"]["error"] = "CLI not detected"

    def list_agents(self):
        return list(self._agents.values())

    def select_agent(self, route, task_text=""):
        is_ar = has_arabic(task_text)
        if route in ("engineering_create_file", "engineering_create_project",
                     "engineering_modify_existing", "engineering_fix",
                     "engineering_refactor", "opencode_engineering"):
            if self._agents.get("opencode_engineering", {}).get("status") == "available":
                return "opencode_engineering"
            if route == "engineering_create_file":
                return "internal_engineering"
            return "internal_engineering"
        if route == "engineering_scan_report":
            return "research"
        if route == "rollback_action":
            return "rollback"
        if route == "voice_action":
            return "voice"
        if route == "status_report":
            return "runtime_execution"
        return "internal_engineering"

    def log_agent_action(self, agent_id, action, task_id, result):
        entry = {
            "agent_id": agent_id,
            "action": action,
            "task_id": task_id,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
