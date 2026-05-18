from datetime import datetime
from pathlib import Path
import uuid
import json

from jarvis.execution.runtime_queue_worker import queue_file_lock


class RuntimeCommandAPI:
    ALLOWED_COMMANDS = {
        "system_review",
        "run_tests",
        "scan_errors",
        "improve",
        "report",
    }

    def __init__(self, logger=None, queue_path=None):
        self.logger = logger
        self.queue_path = Path(queue_path or "JARVIS_CORE/runtime_logs/runtime_command_queue.jsonl")
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)

    def persist_command(self, result):
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)

        with queue_file_lock():
            with self.queue_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

        return result

    def read_queue(self, limit=20, filter_stale=True):
        if not self.queue_path.exists():
            return []

        lines = self.queue_path.read_text(encoding="utf-8").splitlines()
        items = [json.loads(line) for line in lines if line.strip()]
        if filter_stale:
            # Remove stale rejected entries that are likely engineering tasks
            # (These commands were routed to engineering pipeline instead)
            filtered = []
            seen_active = set()
            for item in reversed(items):
                cmd = item.get("command", "")
                if item.get("status") == "rejected" and item.get("reason") == "command_not_allowed":
                    # If a newer entry with same text exists in a non-rejected state, skip
                    if cmd in seen_active:
                        continue
                    # Engineering tasks are NOT in ALLOWED_COMMANDS - these are stale
                    if cmd and cmd not in self.ALLOWED_COMMANDS:
                        continue  # skip stale engineering rejects
                if item.get("status") in ("queued", "running", "completed"):
                    seen_active.add(cmd)
                filtered.append(item)
            items = list(reversed(filtered))
        recent = items[-limit:]
        return recent

    def submit_command(self, command, payload=None, project_id="ledgerx"):
        payload = payload or {}
        command = str(command or "").strip().lower()

        command_id = str(uuid.uuid4())

        if command not in self.ALLOWED_COMMANDS:
            result = {
                "command_id": command_id,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "accepted": False,
                "status": "rejected",
                "reason": "command_not_allowed",
                "command": command,
                "payload": payload,
            }
        else:
            result = {
                "command_id": command_id,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "accepted": True,
                "status": "queued",
                "reason": "safe_command_queued_no_direct_apply",
                "command": command,
                "payload": payload,
            }

        # Only persist queued/accepted commands, not rejected ones
        if result.get("accepted"):
            self.persist_command(result)

        if self.logger:
            self.logger.log_event(
                event_type="runtime_command_submitted",
                project_id=project_id,
                task=command,
                status=result["status"],
                details=result,
            )

        return result
