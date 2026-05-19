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
        try:
            opc = os.environ.get("OPCODE_CLI", "/usr/local/bin/opencode")
        except Exception:
            opc = "/usr/local/bin/opencode"
        detail = {"executable_path": opc}
        if os.path.isfile(opc) and os.access(opc, os.X_OK):
            try:
                r = subprocess.run([opc, "--version"], capture_output=True, text=True, timeout=10)
                version = (r.stdout or r.stderr or "").strip()[:50]
                detail["version"] = version
                if r.returncode == 0 and version:
                    # CLI works -- mark available regardless of provider config
                    self._agents["opencode_engineering"]["status"] = "available"
                    detail["error"] = ""
                else:
                    self._agents["opencode_engineering"]["status"] = "unavailable"
                    detail["error"] = f"Version check exit={r.returncode}: {r.stderr[:100]}"
            except subprocess.TimeoutExpired:
                self._agents["opencode_engineering"]["status"] = "unavailable"
                detail["error"] = "Version check timed out"
            except Exception as e:
                self._agents["opencode_engineering"]["status"] = "unavailable"
                detail["error"] = f"Version check failed: {e}"
        else:
            self._agents["opencode_engineering"]["status"] = "unavailable"
            detail["error"] = "CLI not detected"
        self._agents["opencode_engineering"].update(detail)

    def list_agents(self):
        return list(self._agents.values())

    def select_agent(self, route, task_text=""):
        is_ar = has_arabic(task_text)
        if route in ("engineering_create_file", "engineering_create_page",
                     "engineering_create_project", "engineering_create_feature",
                     "engineering_modify_existing", "engineering_modify_page",
                     "engineering_fix", "engineering_fix_bug",
                     "engineering_refactor", "engineering_refactor_file",
                     "engineering_add_route", "engineering_add_api_endpoint",
                     "engineering_update_template", "engineering_improve_ui",
                     "engineering_generate_diagnostics", "engineering_run_validation",
                     "engineering_inspect_runtime", "opencode_engineering"):
            if self._agents.get("opencode_engineering", {}).get("status") == "available":
                return "opencode_engineering"
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
