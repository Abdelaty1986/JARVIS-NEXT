import json
import uuid
from datetime import datetime, timezone
from threading import RLock


class TaskStateService:
    def __init__(self, memory_dir, logs_dir):
        self.memory_dir = memory_dir
        self.logs_dir = logs_dir
        self.tasks_path = memory_dir / "tasks.json"
        self.events_path = logs_dir / "task_events.jsonl"
        self._lock = RLock()
        self._load()

    def _load(self):
        if self.tasks_path.exists():
            try:
                self._tasks = json.loads(self.tasks_path.read_text(encoding="utf-8"))
            except Exception:
                self._tasks = {}
        else:
            self._tasks = {}
        self._deduplicate()

    def _save(self):
        self.tasks_path.write_text(
            json.dumps(self._tasks, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _event(self, event):
        entry = {**event, "timestamp": datetime.now(timezone.utc).isoformat()}
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _deduplicate(self):
        seen = {}
        for tid, task in list(self._tasks.items()):
            if tid in seen:
                self._tasks.pop(tid)
            else:
                seen[tid] = True

    def create(self, raw_text, route, output_folder=None):
        tid = str(uuid.uuid4())
        task = {
            "task_id": tid,
            "raw_text": raw_text,
            "normalized_text": "",
            "route": route,
            "selected_agent": None,
            "output_folder": str(output_folder) if output_folder else "",
            "status": "received",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "reason": "",
            "files_changed": [],
            "stdout": "",
            "stderr": "",
            "validation_status": "not_run",
            "approval_state": "not_required",
            "final_result": "",
        }
        with self._lock:
            self._tasks[tid] = task
            self._save()
        self._event({"event": "task_created", "task_id": tid, "route": route})
        return task

    def update(self, task_id, **kwargs):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            for k, v in kwargs.items():
                if v is not None:
                    task[k] = v
            task["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save()
        self._event({"event": "task_updated", "task_id": task_id, "changes": kwargs})
        return task

    def _reload(self):
        with self._lock:
            self._load()

    def get(self, task_id):
        self._reload()
        return self._tasks.get(task_id)

    def list_active(self):
        self._reload()
        active_statuses = {"received", "routed", "parsed", "waiting_approval", "approved", "running"}
        return [t for t in self._tasks.values() if t.get("status") in active_statuses]

    def list_history(self, limit=50):
        self._reload()
        final_statuses = {"applied", "completed", "failed", "rejected", "rolled_back"}
        tasks = [t for t in self._tasks.values() if t.get("status") in final_statuses]
        tasks.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
        return tasks[:limit]

    def list_all(self, limit=50):
        self._reload()
        tasks = list(self._tasks.values())
        tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return tasks[:limit]
