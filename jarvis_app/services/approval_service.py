class ApprovalService:
    def __init__(self):
        self._pending = {}

    def requires_approval(self, route, task_text):
        if route in ("engineering_create_file",) and "templates" in task_text.lower():
            return False
        if route == "engineering_create_project":
            return False
        if route in ("engineering_modify_existing", "engineering_fix", "engineering_refactor"):
            return True
        if route == "rollback_action":
            return True
        return False

    def approve(self, task_id):
        if task_id in self._pending:
            del self._pending[task_id]
            return {"ok": True, "task_id": task_id}
        return {"ok": False, "error": "No pending approval for this task"}

    def reject(self, task_id, reason=""):
        if task_id in self._pending:
            del self._pending[task_id]
            return {"ok": True, "task_id": task_id, "reason": reason}
        return {"ok": False, "error": "No pending approval for this task"}
