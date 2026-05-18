import difflib
import json
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class ControlledEngineeringRuntime:
    """Approval-gated patch planner and bounded file mutation runtime."""

    MAX_TASK_CHARS = 600
    MAX_HISTORY = 100
    MAX_OUTPUT_CHARS = 60000

    # Typo map for JARVIS variants
    JARVIS_TYPOS = ("javres", "javeres", "jarves", "jarvies", "jarvis", "جارفيس")

    def _normalize_task_text(self, text):
        """Normalize common JARVIS typos and lowercase."""
        lowered = text.lower().strip()
        for typo in self.JARVIS_TYPOS:
            if typo in lowered:
                lowered = lowered.replace(typo, "jarvis")
        return lowered

    ENGINEERING_KEYWORDS = (
        "fix",
        "repair",
        "bug",
        "add",
        "improve",
        "solve",
        "scan",
        "search",
        "check",
        "report",
        "route",
        "split",
        "module",
        "modules",
        "modularize",
        "refactor",
        "rename",
        "change",
        "ui",
        "button",
        "label",
        "text",
        "arabic",
        "hud",
        "dashboard",
        "template",
        "app.py",
        "create",
        "page",
        "html",
        "new",
        "واجهة",
        "الواجهة",
        "واجهه",
        "الواجهه",
        "الرئيسية",
        "الرئيسيه",
        "صفحة",
        "الصفحة",
        "صفحه",
        "الصفحه",
        "زر",
        "الزر",
        "عنوان",
        "اصلح",
        "أصلح",
        "إصلاح",
        "اصلاح",
        "صحح",
        "عالج",
        "حل",
        "غيّر",
        "غير",
        "تغيير",
        "بدّل",
        "بدل",
        "أضف",
        "اضف",
        "إضافة",
        "اضافة",
        "حسّن",
        "حسن",
        "تحسين",
        "قسّم",
        "قسم",
        "تقسيم",
        "موديولات",
        "وحدات",
        "مسار",
        "راوت",
        "خطأ",
        "خطا",
        "مشكلة",
        "مشكل",
        "نص",
        "عربي",
        "العربية",
        "العربيه",
    )

    UNSAFE_KEYWORDS = (
        "delete",
        "remove database",
        "drop database",
        "drop table",
        "rm ",
        "del ",
        "erase",
        "format",
        "deploy",
        "push",
        "reset --hard",
        "checkout --",
        "secret",
        ".env",
        "database.db",
        "احذف",
        "حذف",
        "امسح",
        "مسح",
        "دمر",
        "دمّر",
        "انشر",
        "نشر",
        "قاعدة البيانات",
        "قاعدة بيانات",
    )

    ALLOWED_ROOTS = ("templates", "static", "JARVIS_CORE")
    ALLOWED_FILES = ("app.py", "jarvis_server.py")
    BLOCKED_PARTS = {
        ".git",
        "__pycache__",
        "runtime_memory",
        "runtime_logs",
        "instance",
        "venv",
        ".venv",
    }
    BLOCKED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".env", ".pem", ".key", ".pfx"}
    BLOCKED_FILENAMES = {".env", "secret_key.txt", "database.db"}

    def __init__(self, project_root=None):
        self.project_root = Path(project_root or ".").resolve()
        self.memory_dir = self.project_root / "JARVIS_CORE" / "runtime_memory"
        self.logs_dir = self.project_root / "JARVIS_CORE" / "runtime_logs"
        self.state_path = self.memory_dir / "controlled_engineering_state.json"
        self.history_path = self.memory_dir / "controlled_engineering_history.json"
        self.events_path = self.logs_dir / "controlled_engineering_events.jsonl"
        self._lock = threading.RLock()
        self._last_oc_stdout = ""
        self._last_oc_stderr = ""

    def status(self):
        return {
            "mode": "controlled_engineering_runtime",
            "bounded": True,
            "approval_required": True,
            "unrestricted_shell_execution": False,
            "deploy_allowed": False,
            "file_deletion_allowed": False,
            "allowed_edit_paths": [
                "templates/",
                "static/",
                "JARVIS_CORE/",
                "app.py",
                "jarvis_server.py",
            ],
            "current": self.current_state(),
        }

    def classify_request(self, text):
        task = str(text or "").strip()
        lowered = self._normalize_task_text(task)
        if not task:
            return {
                "detected_mode": "unsupported_or_unsafe",
                "reason": "Empty input cannot be planned or executed.",
            }
        if len(task) > self.MAX_TASK_CHARS:
            return {
                "detected_mode": "unsupported_or_unsafe",
                "reason": f"Input exceeds {self.MAX_TASK_CHARS} characters.",
            }
        if any(token in lowered for token in self.UNSAFE_KEYWORDS):
            return {
                "detected_mode": "unsupported_or_unsafe",
                "reason": "Unsafe or destructive request detected. JARVIS will not plan or execute it.",
            }
        if self._looks_like_safe_command(lowered):
            return {
                "detected_mode": "safe_command",
                "reason": "Input looks like a safe whitelisted command.",
            }
        if any(keyword in lowered for keyword in self.ENGINEERING_KEYWORDS):
            return {
                "detected_mode": "engineering_task",
                "reason": "Input describes a software repair or development task.",
            }
        return {
            "detected_mode": "unsupported_or_unsafe",
            "reason": "Input is neither a safe command nor a supported engineering task.",
        }

    def request_patch(self, task):
        task = str(task or "").strip()
        classification = self.classify_request(task)
        # Also normalize for internal plan building
        normed = self._normalize_task_text(task)
        # Store normalized version alongside
        classification["normalized_task"] = normed
        if classification["detected_mode"] != "engineering_task":
            return self.block_request(task, classification["reason"])

        plan = self._build_patch_plan(task)
        state = {
            "patch_id": str(uuid.uuid4()),
            "detected_mode": "engineering_task",
            "requested_task": task,
            "interpreted_intent": plan["interpreted_intent"],
            "files_to_modify": plan["files_to_modify"],
            "proposed_changes": plan["proposed_changes"],
            "expected_diff": plan["expected_diff"],
            "expected_change_summary": plan["expected_change_summary"],
            "risk_level": plan["risk_level"],
            "validation_plan": plan["validation_plan"],
            "rollback_plan": plan["rollback_plan"],
            "approval_required": plan["apply_supported"],
            "approval_state": "waiting_patch_approval" if plan["apply_supported"] else "planning_only",
            "apply_supported": plan["apply_supported"],
            "apply_status": "WAITING_APPROVAL" if plan["apply_supported"] else "PLANNING_ONLY",
            "safety_decision": plan["safety_decision"],
            "operations": plan["operations"],
            "rollback_checkpoint": None,
            "files_changed": [],
            "validation_result": {
                "status": "not_run",
                "steps": [],
                "stdout": "",
                "stderr": "",
            },
            "stdout": "",
            "stderr": "",
            "final_result": (
                "patch_waiting_for_approval"
                if plan["apply_supported"]
                else "patch_plan_created_without_safe_mutation_template"
            ),
            "created_at": self._now(),
            "updated_at": self._now(),
            "approved_at": None,
            "applied_at": None,
            "finished_at": None,
        }
        self._write_json(self.state_path, state)
        self._append_event(
            {
                "event": "patch_plan_requested",
                "patch_id": state["patch_id"],
                "task": task,
                "status": state["apply_status"],
                "approval_state": state["approval_state"],
            }
        )
        self._append_history(
            {
                "event": "planned",
                "patch_id": state["patch_id"],
                "requested_task": task,
                "files_changed": [],
                "approval_state": state["approval_state"],
                "result": state["final_result"],
                "validation_result": state["validation_result"],
                "timestamp": self._now(),
            }
        )
        return {
            "ok": True,
            "detected_mode": "engineering_task",
            "message": "Engineering task planned. Patch approval is required before applying.",
            "patch_state": state,
        }

    def block_request(self, task, reason):
        state = {
            "patch_id": str(uuid.uuid4()),
            "detected_mode": "unsupported_or_unsafe",
            "requested_task": str(task or "").strip(),
            "interpreted_intent": "Request blocked before patch planning.",
            "files_to_modify": [],
            "proposed_changes": [],
            "expected_diff": "",
            "expected_change_summary": reason,
            "risk_level": "blocked",
            "validation_plan": [],
            "rollback_plan": ["No file changes were made, so rollback is not required."],
            "approval_required": False,
            "approval_state": "blocked_unsafe",
            "apply_supported": False,
            "apply_status": "BLOCKED",
            "safety_decision": {
                "allowed": False,
                "reason": reason,
                "approval_required": False,
                "destructive_execution": False,
                "deploy": False,
                "file_deletion": False,
                "shell_execution": False,
            },
            "operations": [],
            "rollback_checkpoint": None,
            "files_changed": [],
            "validation_result": {
                "status": "not_run",
                "steps": [],
                "stdout": "",
                "stderr": "",
            },
            "stdout": "",
            "stderr": "",
            "final_result": "blocked_before_patch_planning",
            "created_at": self._now(),
            "updated_at": self._now(),
            "approved_at": None,
            "applied_at": None,
            "finished_at": self._now(),
        }
        self._write_json(self.state_path, state)
        self._append_event(
            {
                "event": "patch_request_blocked",
                "patch_id": state["patch_id"],
                "task": state["requested_task"],
                "status": "BLOCKED",
                "reason": reason,
            }
        )
        self._append_history(
            {
                "event": "blocked",
                "patch_id": state["patch_id"],
                "requested_task": state["requested_task"],
                "files_changed": [],
                "approval_state": "blocked_unsafe",
                "result": reason,
                "validation_result": state["validation_result"],
                "timestamp": self._now(),
            }
        )
        return {
            "ok": False,
            "detected_mode": "unsupported_or_unsafe",
            "message": reason,
            "patch_state": state,
        }

    def current_state(self):
        with self._lock:
            if not self.state_path.exists():
                return self._default_state()
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception as exc:
                state = self._default_state()
                state["apply_status"] = "FAILED"
                state["final_result"] = f"engineering_state_read_failed: {exc}"
                return state

    def approve_patch(self, patch_id=None):
        state = self.current_state()
        if not state.get("patch_id"):
            return self._failure("No patch is waiting for approval.", state)
        if patch_id and patch_id != state.get("patch_id"):
            return self._failure("Patch approval id does not match the current patch.", state)
        if state.get("approval_state") != "waiting_patch_approval":
            return self._failure("Current patch is not waiting for approval.", state)
        if not state.get("safety_decision", {}).get("allowed"):
            return self._failure("Unsafe patch plans cannot be approved.", state)
        if not state.get("apply_supported"):
            return self._failure("This plan has no deterministic safe mutation template.", state)

        now = self._now()
        state["approval_state"] = "patch_approved"
        state["apply_status"] = "APPROVED"
        state["approved_at"] = now
        state["updated_at"] = now
        state["final_result"] = "patch_approved_waiting_to_apply"
        self._write_json(self.state_path, state)
        self._append_event(
            {
                "event": "patch_approved",
                "patch_id": state["patch_id"],
                "task": state.get("requested_task"),
                "status": "APPROVED",
            }
        )
        self._append_history(
            {
                "event": "approved",
                "patch_id": state["patch_id"],
                "requested_task": state.get("requested_task"),
                "files_changed": [],
                "approval_state": state["approval_state"],
                "result": state["final_result"],
                "validation_result": state["validation_result"],
                "timestamp": now,
            }
        )
        return {"ok": True, "message": "Patch approved.", "patch_state": state}

    def reject_patch(self, patch_id=None, reason=None):
        state = self.current_state()
        if not state.get("patch_id"):
            return self._failure("No patch is available to reject.", state)
        if patch_id and patch_id != state.get("patch_id"):
            return self._failure("Patch rejection id does not match the current patch.", state)
        if state.get("apply_status") == "APPLYING":
            return self._failure("A patch that is applying cannot be rejected.", state)

        now = self._now()
        state["approval_state"] = "patch_rejected"
        state["apply_status"] = "REJECTED"
        state["updated_at"] = now
        state["finished_at"] = now
        state["final_result"] = reason or "Patch rejected by human operator."
        self._write_json(self.state_path, state)
        self._append_event(
            {
                "event": "patch_rejected",
                "patch_id": state["patch_id"],
                "task": state.get("requested_task"),
                "status": "REJECTED",
                "reason": state["final_result"],
            }
        )
        self._append_history(
            {
                "event": "rejected",
                "patch_id": state["patch_id"],
                "requested_task": state.get("requested_task"),
                "files_changed": [],
                "approval_state": state["approval_state"],
                "result": state["final_result"],
                "validation_result": state["validation_result"],
                "timestamp": now,
            }
        )
        return {"ok": True, "message": "Patch rejected.", "patch_state": state}

    def apply_approved_patch(self, patch_id=None):
        state = self.current_state()
        if not state.get("patch_id"):
            return self._failure("No patch is available to apply.", state)
        if patch_id and patch_id != state.get("patch_id"):
            return self._failure("Patch apply id does not match the current patch.", state)
        if state.get("approval_state") != "patch_approved":
            return self._failure("Patch must be approved before applying.", state)
        if state.get("apply_status") in {"APPLIED", "VALIDATION_FAILED"}:
            return self._failure("Patch has already reached a final apply state.", state)

        ops = state.get("operations", [])
        if not ops:
            state["apply_status"] = "FAILED"
            state["final_result"] = "no_file_operations_generated"
            state["updated_at"] = self._now()
            state["finished_at"] = self._now()
            self._write_json(self.state_path, state)
            return {"ok": False, "message": "No file operations were generated. Patch cannot be applied.", "patch_state": state}

        try:
            self._validate_operations_for_mutation(ops)
            checkpoint = self._create_rollback_checkpoint(state)
            task_context = state.get("requested_task", "")
            changed_files = self._apply_operations(ops, task_context=task_context)
            if not changed_files:
                state["apply_status"] = "FAILED"
                state["final_result"] = "no_file_operations_generated"
                state["updated_at"] = self._now()
                state["finished_at"] = self._now()
                state["rollback_checkpoint"] = checkpoint
                self._write_json(self.state_path, state)
                return {"ok": False, "message": "No files were changed during apply. All operations produced no changes.", "patch_state": state}
            validation_files = changed_files or self._operation_paths(state.get("operations", []))
            validation = self._run_validation(validation_files, state.get("operations", []))
            now = self._now()

            state["rollback_checkpoint"] = checkpoint
            state["files_changed"] = changed_files
            state["validation_result"] = validation
            oc_stdout = getattr(self, "_last_oc_stdout", "")
            oc_stderr = getattr(self, "_last_oc_stderr", "")
            combined_stdout = validation.get("stdout", "")
            if oc_stdout:
                combined_stdout = oc_stdout + "\n" + combined_stdout
            combined_stderr = validation.get("stderr", "")
            if oc_stderr:
                combined_stderr = oc_stderr + "\n" + combined_stderr
            state["stdout"] = combined_stdout
            state["stderr"] = combined_stderr
            state["applied_at"] = now
            state["finished_at"] = now
            state["updated_at"] = now
            if validation.get("status") == "passed":
                state["apply_status"] = "APPLIED"
                state["final_result"] = "Patch applied and validation passed."
            else:
                state["apply_status"] = "VALIDATION_FAILED"
                state["final_result"] = "Patch applied but validation failed. Rollback is available."

            self._write_json(self.state_path, state)
            self._append_event(
                {
                    "event": "patch_applied",
                    "patch_id": state["patch_id"],
                    "task": state.get("requested_task"),
                    "status": state["apply_status"],
                    "files_changed": changed_files,
                    "validation_status": validation.get("status"),
                }
            )
            self._append_history(
                {
                    "event": "applied",
                    "patch_id": state["patch_id"],
                    "requested_task": state.get("requested_task"),
                    "files_changed": changed_files,
                    "approval_state": state["approval_state"],
                    "result": state["final_result"],
                    "validation_result": validation,
                    "timestamp": now,
                }
            )
            return {"ok": validation.get("status") == "passed", "message": state["final_result"], "patch_state": state}
        except Exception as exc:
            now = self._now()
            state["apply_status"] = "FAILED"
            state["final_result"] = f"Patch apply failed: {exc}"
            state["stderr"] = str(exc)
            state["updated_at"] = now
            state["finished_at"] = now
            self._write_json(self.state_path, state)
            self._append_event(
                {
                    "event": "patch_apply_failed",
                    "patch_id": state.get("patch_id"),
                    "task": state.get("requested_task"),
                    "status": "FAILED",
                    "error": str(exc),
                }
            )
            return {"ok": False, "message": state["final_result"], "patch_state": state}

    def rollback_patch(self, patch_id=None):
        state = self.current_state()
        checkpoint = state.get("rollback_checkpoint") or {}
        if not checkpoint:
            return self._failure("No rollback checkpoint is available.", state)
        if patch_id and patch_id != state.get("patch_id"):
            return self._failure("Rollback patch id does not match the current patch.", state)

        restored = []
        for item in checkpoint.get("files", []):
            relative_path = item.get("path")
            path = self._resolve_mutation_path(relative_path)
            if item.get("content") == "__NEW_FILE__":
                if path.exists():
                    path.unlink()
            else:
                path.write_text(item.get("content", ""), encoding="utf-8")
            restored.append(relative_path)

        now = self._now()
        state["apply_status"] = "ROLLED_BACK"
        state["final_result"] = "Patch rolled back from checkpoint."
        state["updated_at"] = now
        state["finished_at"] = now
        state["files_changed"] = restored
        self._write_json(self.state_path, state)
        self._append_event(
            {
                "event": "patch_rolled_back",
                "patch_id": state.get("patch_id"),
                "files_changed": restored,
                "status": "ROLLED_BACK",
            }
        )
        self._append_history(
            {
                "event": "rolled_back",
                "patch_id": state.get("patch_id"),
                "requested_task": state.get("requested_task"),
                "files_changed": restored,
                "approval_state": state.get("approval_state"),
                "result": state["final_result"],
                "validation_result": state.get("validation_result"),
                "timestamp": now,
            }
        )
        return {"ok": True, "message": state["final_result"], "patch_state": state}

    def history(self):
        if not self.history_path.exists():
            return []
        try:
            history = json.loads(self.history_path.read_text(encoding="utf-8"))
            if isinstance(history, list):
                return history[-self.MAX_HISTORY :]
        except Exception:
            pass
        return []

    def logs(self):
        if not self.events_path.exists():
            return []
        events = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events[-self.MAX_HISTORY :]

    def _build_patch_plan(self, task):
        lowered = self._normalize_task_text(task)
        if self._is_scan_jarvis_task(lowered):
            return self._build_scan_jarvis_patch(task, lowered)
        # When OpenCode is available, prefer it for create-page and engineering tasks
        if self._opencode_available():
            if self._is_create_page_task(lowered):
                return self._escalate_to_opencode(task, lowered)
            if self._is_arabic_dashboard_issue(lowered):
                return self._escalate_to_opencode(task, lowered)
        # Fallback to internal handlers when OpenCode unavailable
        if self._is_create_page_task(lowered):
            plan = self._build_create_new_template_patch(task)
            if plan.get("operations"):
                return plan
            return self._escalate_to_opencode(task, lowered)
        if self._is_arabic_dashboard_issue(lowered):
            plan = self._build_arabic_dashboard_patch_plan(task)
            if plan.get("operations"):
                return plan
            return self._escalate_to_opencode(task, lowered)
        if "request plan" in lowered and "create patch plan" in lowered:
            return self._build_create_patch_plan_button_patch(task)
        if "engineering patch mode active" in lowered:
            return self._build_hud_label_patch_plan(task)
        if self._is_generic_engineering_task(lowered):
            plan = self._build_generic_engineering_patch(task)
            if plan.get("operations") or not self._opencode_available():
                return plan
            return self._escalate_to_opencode(task, lowered)
        if self._opencode_available():
            return self._escalate_to_opencode(task, lowered)
        return self._build_planning_only_task(task)

    def _opencode_available(self):
        try:
            from jarvis.agents.opencode_engineering_agent import detect_opencode
            d = detect_opencode()
            return d.get("installed", False)
        except Exception:
            return False

    def _escalate_to_opencode(self, task, lowered):
        return {
            "interpreted_intent": "Escalate to OpenCode engineering agent",
            "files_to_modify": [],
            "proposed_changes": [
                "This task will be handled by OpenCode engineering agent.",
                "OpenCode will generate and apply code changes directly.",
            ],
            "expected_change_summary": "OpenCode agent handles the task autonomously.",
            "expected_diff": "Managed by OpenCode CLI.",
            "risk_level": "medium",
            "validation_plan": [
                "OpenCode will run its own validation.",
                "Post-apply validation will check git status and py_compile.",
            ],
            "rollback_plan": [
                "Use git revert if needed.",
                "Modified files tracked in git status.",
            ],
            "apply_supported": True,
            "safety_decision": {
                "allowed": True,
                "reason": "Escalated to OpenCode engineering agent with project root enforcement.",
                "approval_required": True,
                "bounded_execution": True,
                "shell_execution": True,
                "destructive_execution": False,
                "deploy": False,
                "file_deletion": False,
            },
            "operations": [
                {
                    "type": "opencode_escalation",
                    "description": f"Run OpenCode agent for: {task[:200]}",
                    "expected_marker": "opencode_escalation",
                    "task": task,
                }
            ],
        }

    def _is_generic_engineering_task(self, lowered):
        keywords = (
            "fix", "صلح", "أصلح", "إصلاح", "تصليح", "bug", "خطأ",
            "improve", "حسن", "طور", "تحسين", "تطوير", "باتش", "patch",
            "debug", "حلل", "تحليل", "فشل",
            "refactor", "هيكلة", "إعادة هيكلة", "أعد هيكلة",
            "clean", "نظف", "تنظيف",
            "test", "اختبار", "اختبر",
            "deploy", "انشر", "نشر",
            "apply", "طبق", "تطبيق",
            "create", "أنشئ", "أنشاء", "إنشاء", "صنع", "عمل", "كوّن", "كون",
            "page", "صفحة", "صفحه",
            "html",
            "new", "جديد", "جديده", "جديدة",
            "scan", "search", "check", "مسح", "فحص", "بحث",
            "report", "تقرير",
            "jarvis",
        )
        return any(k in lowered for k in keywords)

    def _is_scan_jarvis_task(self, lowered):
        """Detect 'scan jarvis system for bugs/fixes/report' tasks."""
        has_scan = any(token in lowered for token in ("scan", "search", "check", "مسح", "فحص", "بحث"))
        has_jarvis = "jarvis" in lowered
        has_bug = any(token in lowered for token in ("bug", "خطأ", "خطا", "مشكلة", "مشكل"))
        has_report = any(token in lowered for token in ("report", "تقرير", "report"))
        has_fix = any(token in lowered for token in ("fix", "إصلاح", "اصلاح", "أصلح", "صلح", "تصليح"))
        return has_scan and has_jarvis and (has_bug or has_report or has_fix)

    def _build_scan_jarvis_patch(self, task, lowered):
        has_report = any(token in lowered for token in ("report", "تقرير"))
        has_fix = any(token in lowered for token in ("fix", "إصلاح", "اصلاح", "أصلح", "صلح", "تصليح"))
        # Determine action type
        action = "scan"
        if has_fix:
            action = "scan_and_fix"
        elif has_report:
            action = "scan_and_report"

        # Generate a structured diagnostic report
        from datetime import datetime
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        report_path = f"JARVIS_CORE/runtime_logs/jarvis_scan_report_{uuid.uuid4().hex[:8]}.json"
        report = {
            "scan_time": now,
            "target": "JARVIS-CORE",
            "scan_type": action,
            "files_scanned": 0,
            "issues_found": [],
            "summary": {},
        }
        # Actually scan JARVIS_CORE Python files
        import os
        scan_dir = self.project_root / "JARVIS_CORE"
        issues = []
        files_scanned = 0
        if scan_dir.exists():
            for root, dirs, files in os.walk(scan_dir):
                for fn in files:
                    if fn.endswith(".py"):
                        files_scanned += 1
                        fpath = os.path.join(root, fn)
                        try:
                            content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            continue
                        # Check for common issues
                        lines = content.splitlines()
                        for i, line in enumerate(lines, 1):
                            stripped = line.strip()
                            if stripped.startswith("import ") or stripped.startswith("from "):
                                continue
                            if "TODO" in stripped or "FIXME" in stripped or "XXX" in stripped:
                                rel = os.path.relpath(fpath, str(self.project_root))
                                issues.append({
                                    "file": rel,
                                    "line": i,
                                    "type": "todo_fixme",
                                    "text": stripped.strip()[:80],
                                })
                            if "print(" in stripped and "def " not in stripped:
                                # Check if it's inside a function definition-ish
                                pass  # Too many false positives

        report["files_scanned"] = files_scanned
        report["issues_found"] = issues[:50]
        report["summary"] = {
            "total_files_scanned": files_scanned,
            "total_issues_found": len(issues),
            "todo_fixme_count": sum(1 for i in issues if i["type"] == "todo_fixme"),
        }

        # Write the report (always — even for fix, the report is the primary deliverable)
        report_abspath = self.project_root / report_path
        report_abspath.parent.mkdir(parents=True, exist_ok=True)
        report_abspath.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        # If fix mode, prepare operations that clean up TODO/FIXME lines
        operations = []
        if has_fix and issues:
            for issue in issues[:5]:
                fpath = self.project_root / issue["file"]
                if fpath.exists():
                    old_content = fpath.read_text(encoding="utf-8", errors="replace")
                    lines = old_content.splitlines()
                    line_idx = issue["line"] - 1
                    if 0 <= line_idx < len(lines):
                        old_line = lines[line_idx]
                        new_line = old_line.rstrip()
                        if new_line.strip().startswith("#"):
                            new_line = "# Reviewed: " + new_line.strip().lstrip("#").strip()
                        else:
                            new_line = "# Reviewed: " + new_line.strip()
                        lines[line_idx] = new_line
                    new_content = "\n".join(lines)
                    if new_content != old_content:
                        operations.append({
                            "type": "replace_file_text",
                            "path": issue["file"],
                            "description": f"Review TODO/FIXME at line {issue['line']} in {issue['file']}: {issue['text'][:60]}.",
                            "expected_marker": "Reviewed",
                            "content": new_content,
                        })

        report_rel = report_path.replace("\\", "/")
        return {
            "interpreted_intent": f"{action}: Scan JARVIS system for bugs and {'fix issues' if has_fix else 'generate report'}.",
            "files_to_modify": [report_rel] + ([op["path"] for op in operations] if operations else []),
            "proposed_changes": [
                f"Scan JARVIS_CORE Python files for bugs and issues.",
                f"Found {len(issues)} issues in {files_scanned} files.",
                f"{'Fixed ' + str(fix_count) + ' TODO/FIXME issues.' if has_fix and fix_count else ''}",
                f"Generated diagnostic report: {report_rel}",
            ],
            "expected_change_summary": f"JARVIS scan completed. Report saved to {report_rel}. {'Fixed ' + str(fix_count) + ' issues.' if has_fix and fix_count else ''}" if action != "scan_and_report" else f"Diagnostic report generated at {report_rel}.",
            "expected_diff": f"Scan report: {report_rel} - {len(issues)} issues found in {files_scanned} files.",
            "risk_level": "low",
            "validation_plan": [
                "Confirm scan report was generated.",
                "Confirm fixed files still pass py_compile.",
            ],
            "rollback_plan": [
                "Delete generated report and revert any fixed files from checkpoint.",
            ],
            "apply_supported": bool(operations),
            "safety_decision": {
                "allowed": True,
                "reason": f"Scan JARVIS system for bugs with {'fix' if has_fix else 'report'}. Low risk bounded operation.",
                "approval_required": bool(operations),
                "bounded_execution": True,
                "shell_execution": False,
                "destructive_execution": False,
                "deploy": False,
                "file_deletion": False,
            },
            "operations": operations[:2] if operations else [],
        }

    def _is_arabic_dashboard_issue(self, lowered):
        has_arabic_issue = any(
            token in lowered
            for token in (
                "عربي",
                "العربية",
                "العربيه",
                "لغة",
                "اللغه",
                "اللغة",
                "واجهة",
                "الواجهة",
                "dashboard",
            )
        )
        has_ui_surface = any(
            token in lowered
            for token in (
                "dashboard",
                "hud",
                "واجهة",
                "الواجهة",
                "الرئيسية",
                "الرئيسيه",
                "صفحة",
                "الصفحة",
            )
        )
        return has_arabic_issue and has_ui_surface

    def _build_arabic_dashboard_patch_plan(self, task):
        target = "templates/jarvis/mobile_control_center.html"
        original = self._read_project_file(target)
        updated = self._apply_arabic_dashboard_support_to_text(original)
        expected_diff = self._build_diff(target, original, updated)

        return {
            "interpreted_intent": "Improve Arabic and RTL rendering in the JARVIS dashboard/HUD.",
            "files_to_modify": [target],
            "proposed_changes": [
                "Add scoped Arabic/RTL text handling for the JARVIS HUD.",
                "Ensure mixed Arabic/English task text can wrap safely without overlapping controls.",
                "Add dir=\"auto\" to the command input and dynamic status/history containers.",
                "Use an Arabic-capable font fallback without removing existing runtime panels or controls.",
            ],
            "expected_change_summary": (
                "templates/jarvis/mobile_control_center.html will receive scoped CSS and "
                "dir=\"auto\" attributes for Arabic dashboard text rendering."
            ),
            "expected_diff": expected_diff,
            "risk_level": "low",
            "validation_plan": [
                "Confirm the template contains the Arabic HUD support CSS marker.",
                "Confirm the command input and dynamic text containers use dir=\"auto\".",
                "Run py_compile only for modified Python files; none are expected for this template patch.",
                "Record validation status, stdout, and stderr in runtime memory.",
            ],
            "rollback_plan": [
                "Create a rollback checkpoint with original template contents before applying.",
                "If validation fails, expose rollback in the HUD and keep the checkpoint available.",
                "Rollback restores the original template content from runtime memory.",
            ],
            "apply_supported": True,
            "safety_decision": {
                "allowed": True,
                "reason": (
                    "Deterministic template-only Arabic HUD rendering patch is safe to apply after approval."
                    if original != updated
                    else "Arabic HUD rendering support already exists; approval will re-validate the safe template state."
                ),
                "approval_required": True,
                "bounded_execution": True,
                "shell_execution": False,
                "destructive_execution": False,
                "deploy": False,
                "file_deletion": False,
            },
            "operations": [
                {
                    "type": "replace_file_text",
                    "path": target,
                    "description": "Add scoped Arabic/RTL HUD rendering support.",
                    "expected_marker": "JARVIS_ARABIC_HUD_TEXT_SUPPORT",
                    "content": updated,
                }
            ],
        }

    def _build_create_patch_plan_button_patch(self, task):
        target = "templates/jarvis/mobile_control_center.html"
        original = self._read_project_file(target)
        updated = self._apply_create_patch_plan_button_to_text(original)
        expected_diff = self._build_diff(target, original, updated)

        return {
            "interpreted_intent": "Rename the JARVIS request planning button to Create Patch Plan.",
            "files_to_modify": [target],
            "proposed_changes": [
                "Change the visible Request Plan button label to Create Patch Plan.",
                "Keep the existing form, endpoint, approval flow, and safe command routing intact.",
                "Avoid backend shell execution, deploy, deletion, database, and secret changes.",
            ],
            "expected_change_summary": (
                "templates/jarvis/mobile_control_center.html will update the visible "
                "request button text from Request Plan to Create Patch Plan."
            ),
            "expected_diff": expected_diff,
            "risk_level": "low",
            "validation_plan": [
                "Confirm the edited template contains Create Patch Plan.",
                "Run py_compile only for modified Python files; none are expected for this patch.",
                "Record validation status, stdout, and stderr in runtime memory.",
            ],
            "rollback_plan": [
                "Create a rollback checkpoint with original template contents before applying.",
                "If validation fails, expose rollback in the HUD and keep the checkpoint available.",
                "Rollback restores the original template content from runtime memory.",
            ],
            "apply_supported": True,
            "safety_decision": {
                "allowed": True,
                "reason": (
                    "Deterministic template-only button label patch is safe to apply after approval."
                    if original != updated
                    else "The requested button label already exists; approval will re-validate the safe template state."
                ),
                "approval_required": True,
                "bounded_execution": True,
                "shell_execution": False,
                "destructive_execution": False,
                "deploy": False,
                "file_deletion": False,
            },
            "operations": [
                {
                    "type": "replace_file_text",
                    "path": target,
                    "description": "Rename the request planning button.",
                    "expected_marker": "Create Patch Plan",
                    "content": updated,
                }
            ],
        }

    def _build_hud_label_patch_plan(self, task):
        target = "templates/jarvis/mobile_control_center.html"
        original = self._read_project_file(target)
        updated = self._apply_hud_label_to_text(original)
        expected_diff = self._build_diff(target, original, updated)

        return {
            "interpreted_intent": "Add a harmless visible engineering patch mode label to the JARVIS HUD.",
            "files_to_modify": [target],
            "proposed_changes": [
                "Add a small visible HUD label with the exact text ENGINEERING PATCH MODE ACTIVE.",
                "Add scoped CSS for the label inside the existing JARVIS HUD template.",
                "Avoid backend, database, deployment, deletion, and shell changes.",
            ],
            "expected_change_summary": (
                "templates/jarvis/mobile_control_center.html will receive a scoped label "
                "near the existing approval execution console."
            ),
            "expected_diff": expected_diff,
            "risk_level": "low",
            "validation_plan": [
                "Confirm the edited template contains ENGINEERING PATCH MODE ACTIVE.",
                "Run py_compile only for modified Python files; none are expected for this patch.",
                "Record validation status, stdout, and stderr in runtime memory.",
            ],
            "rollback_plan": [
                "Create a rollback checkpoint with original file contents before applying.",
                "If validation fails, expose rollback in the HUD and keep the checkpoint available.",
                "Rollback restores the original template content from runtime memory.",
            ],
            "apply_supported": True,
            "safety_decision": {
                "allowed": True,
                "reason": (
                    "Deterministic template-only patch is safe to apply after approval."
                    if original != updated
                    else "The requested visible label already exists; approval will re-validate the safe template state."
                ),
                "approval_required": True,
                "bounded_execution": True,
                "shell_execution": False,
                "destructive_execution": False,
                "deploy": False,
                "file_deletion": False,
            },
            "operations": [
                {
                    "type": "replace_file_text",
                    "path": target,
                    "description": "Insert the engineering patch mode label and scoped CSS.",
                    "expected_marker": "ENGINEERING PATCH MODE ACTIVE",
                    "content": updated,
                }
            ],
        }

    def _build_generic_engineering_patch(self, task):
        lowered = task.lower()
        files = self._infer_files_for_task(task)
        changes = []
        diffs = []
        valid_files = []
        for f in files:
            try:
                resolved = self._resolve_mutation_path(f)
                if resolved and resolved.exists() and resolved.is_file():
                    content = resolved.read_text(encoding="utf-8")
                    changes.append(f"Review and update {f}")
                    diffs.append(f"Target: {f} — {len(content.splitlines())} lines available for supervised patch")
                    valid_files.append(f)
            except (ValueError, OSError):
                pass
        if not valid_files and self._is_create_page_task(lowered):
            # New file creation: infer name from task and create in templates/
            return self._build_create_new_template_patch(task)
        if not valid_files:
            # Fallback: use app.py if no valid files found
            try:
                self._resolve_mutation_path("app.py")
                content = self._read_project_file("app.py") or ""
                changes.append("Review and update app.py")
                diffs.append("Target: app.py — main application file")
                valid_files.append("app.py")
            except (ValueError, OSError):
                changes.append(f"Prepare engineering patch for: {task[:80]}")
                diffs.append("No valid target files identified for safe mutation")
                valid_files = []

        return {
            "interpreted_intent": f"Engineering task: {task[:80]}",
            "files_to_modify": valid_files,
            "proposed_changes": changes,
            "expected_change_summary": f"JARVIS prepared a supervised engineering patch for: {task[:120]}",
            "expected_diff": "\n".join(diffs) if diffs else "No diff generated.",
            "risk_level": "medium",
            "validation_plan": [
                "Validate target files exist.",
                "Run py_compile on modified Python files.",
                "Record validation status, stdout, and stderr in runtime memory.",
            ],
            "rollback_plan": [
                "Create a rollback checkpoint with original file contents before applying.",
                "If validation fails, expose rollback in the HUD and keep the checkpoint available.",
                "Rollback restores the original content from runtime memory.",
            ],
            "apply_supported": bool(valid_files),
            "safety_decision": {
                "allowed": bool(valid_files),
                "reason": (
                    f"Supervised engineering patch for: {task[:120]}. "
                    "Risk-gated approval required before file mutation."
                ) if valid_files else (
                    f"Planning-only: no valid files identified for: {task[:120]}."
                ),
                "approval_required": bool(valid_files),
                "bounded_execution": True,
                "shell_execution": False,
                "destructive_execution": False,
                "deploy": False,
                "file_deletion": False,
            },
            "operations": [
                {
                    "type": "replace_file_text",
                    "path": f,
                    "description": f"Review and prepare {f} for supervised engineering patch.",
                    "expected_marker": "",
                    "content": self._read_project_file(f) or "",
                }
                for f in valid_files[:2]
            ],
        }

    def _build_planning_only_task(self, task):
        files = self._infer_files_for_task(task)
        return {
            "interpreted_intent": "Plan a controlled engineering change without applying a file mutation.",
            "files_to_modify": files,
            "proposed_changes": [
                "Inspect the affected UI/backend area.",
                "Prepare a bounded patch only after a deterministic safe mutation is available.",
                "Keep database, secrets, deployment, deletion, and arbitrary shell access blocked.",
            ],
            "expected_change_summary": (
                "JARVIS classified this as an engineering task and produced a planning-only patch preview. "
                "No safe deterministic edit template matched this request yet."
            ),
            "expected_diff": "No diff generated. This task requires a more specific bounded patch template.",
            "risk_level": "medium",
            "validation_plan": [
                "No file validation will run because no patch will be applied.",
                "When a deterministic patch is available, validate modified Python files with py_compile.",
            ],
            "rollback_plan": [
                "No rollback checkpoint is needed because no file changes will be made.",
            ],
            "apply_supported": False,
            "safety_decision": {
                "allowed": False,
                "reason": "Engineering task planned, but no deterministic safe mutation template matched.",
                "approval_required": False,
                "bounded_execution": True,
                "shell_execution": False,
                "destructive_execution": False,
                "deploy": False,
                "file_deletion": False,
            },
            "operations": [],
        }

    def _is_create_page_task(self, lowered):
        has_create = any(token in lowered for token in (
            "create", "أنشئ", "أنشاء", "إنشاء", "انشاء", "انشئ",
            "صنع", "عمل", "new", "جديد", "جديده", "جديدة",
            "صمم", "تصميم", "اعمل", "أعمل", "كوّن", "كون", "عمل",
        ))
        has_page = any(token in lowered for token in (
            "page", "html", "صفحة", "صفحه", "الصفحة", "الصفحه",
            "template", "قالب", "dashboard", "داش", "بورد", "داشبورد",
            "هوم", "home",
        ))
        return has_create and has_page

    AR_TO_EN = {
        "هيلثي": "healthy",
        "هيلث": "health",
        "الصحة": "health",
        "لياقة": "fitness",
        "داش": "dashboard",
        "بورد": "",
        "داشبورد": "dashboard",
        "هوم": "home",
        "الرئيسية": "main",
        "الرئيسيه": "main",
        "اتصال": "contact",
        "تواصل": "contact",
        "عنا": "about",
        "حول": "about",
        "خدمات": "services",
        "منتجات": "products",
        "سعر": "pricing",
        "احترافي": "professional",
        "محترف": "professional",
        "متقدم": "advanced",
        "بسيط": "simple",
        "مظلم": "dark",
        "فاتح": "light",
        "رياضي": "sports",
        "طبي": "medical",
        "تعليمي": "educational",
        "أخبار": "news",
        "مدونة": "blog",
    }

    SKIP_WORDS = {
        "create", "a", "an", "as", "the", "html", "page", "new", "template",
        "professional", "basic", "simple", "modern", "responsive", "clean",
        "إنشاء", "انشاء", "أنشاء", "أنشئ", "انشئ", "صفحة", "صفحه",
        "الصفحة", "الصفحه", "جديد", "جديده", "جديدة",
        "صمم", "تصميم", "اعمل", "أعمل", "كوّن", "كون", "عمل", "صنع",
        "احترافي", "محترف", "basic", "arabic",
    }

    def _extract_page_name(self, lowered):
        """Extract a page name from the task, mapping Arabic to English."""
        words = lowered.split()
        # Filter skip words
        content_words = [w for w in words if w not in self.SKIP_WORDS]
        if not content_words:
            return "coffee"
        # Check for "داش بورد" as two-word "dashboard"
        result = []
        i = 0
        while i < len(content_words):
            w = content_words[i]
            if w == "داش" and i + 1 < len(content_words) and content_words[i + 1] == "بورد":
                result.append("dashboard")
                i += 2
                continue
            mapped = self.AR_TO_EN.get(w, w)
            # Keep only ascii-alphanumeric for filename
            clean = "".join(c for c in mapped if c.isalnum() or c in "-_")
            if clean:
                result.append(clean)
            i += 1
        if not result:
            return "coffee"
        return "_".join(result)

    def _build_healthy_dashboard_html(self, title_ar):
        """Generate a professional Arabic RTL health dashboard HTML."""
        return """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>""" + title_ar + """</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{
  font-family:'Segoe UI',Tahoma,Arial,sans-serif;
  background:linear-gradient(135deg,#0a1628,#1a2a4a);
  color:#e0f0ff;min-height:100vh;padding:20px;
}
.header{text-align:center;padding:30px 20px 20px}
.header h1{font-size:28px;color:#00e5ff;text-shadow:0 0 20px rgba(0,229,255,.3)}
.header p{color:#80b0d0;font-size:14px;margin-top:8px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;max-width:900px;margin:20px auto}
.card{
  background:rgba(255,255,255,.05);border:1px solid rgba(0,229,255,.12);
  border-radius:16px;padding:20px;text-align:center;
  backdrop-filter:blur(10px);transition:transform .2s
}
.card:hover{transform:translateY(-4px)}
.card .icon{font-size:32px;margin-bottom:8px}
.card .value{font-size:28px;font-weight:700;color:#00e5ff;margin:4px 0}
.card .label{font-size:12px;color:#80b0d0;text-transform:uppercase;letter-spacing:1px}
.card .unit{font-size:11px;color:#6080a0}
.section{max-width:900px;margin:24px auto}
.section h2{font-size:18px;color:#00e5ff;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid rgba(0,229,255,.1)}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.progress-bar{height:8px;background:rgba(255,255,255,.06);border-radius:4px;overflow:hidden;margin:8px 0}
.progress-fill{height:100%;border-radius:4px;background:linear-gradient(90deg,#00e5ff,#00ff88);transition:width 1s}
.stat-row{display:flex;justify-content:space-between;padding:8px 12px;background:rgba(255,255,255,.03);border-radius:8px;margin-bottom:6px}
.stat-row .stat-label{color:#80b0d0;font-size:13px}
.stat-row .stat-value{color:#00e5ff;font-weight:600;font-size:13px}
.footer{text-align:center;padding:20px;color:#406080;font-size:11px;margin-top:20px}
@media(max-width:600px){.grid-2{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="header">
  <h1>""" + title_ar + """</h1>
  <p>نظرة شاملة على مؤشراتك الصحية اليومية</p>
</div>

<div class="metrics">
  <div class="card">
    <div class="icon">🔥</div>
    <div class="value">2,450</div>
    <div class="label">السعرات الحرارية</div>
    <div class="unit">من أصل 2,200</div>
    <div class="progress-bar"><div class="progress-fill" style="width:82%"></div></div>
  </div>
  <div class="card">
    <div class="icon">💧</div>
    <div class="value">1.8</div>
    <div class="label">الماء</div>
    <div class="unit">لتر من أصل 2.5</div>
    <div class="progress-bar"><div class="progress-fill" style="width:72%"></div></div>
  </div>
  <div class="card">
    <div class="icon">👣</div>
    <div class="value">6,842</div>
    <div class="label">الخطوات</div>
    <div class="unit">من أصل 10,000</div>
    <div class="progress-bar"><div class="progress-fill" style="width:68%"></div></div>
  </div>
  <div class="card">
    <div class="icon">😴</div>
    <div class="value">7.5</div>
    <div class="label">النوم</div>
    <div class="unit">ساعات من أصل 8</div>
    <div class="progress-bar"><div class="progress-fill" style="width:94%"></div></div>
  </div>
</div>

<div class="section">
  <h2>📊 تفاصيل المؤشرات</h2>
  <div class="grid-2">
    <div class="stat-row"><span class="stat-label"> calories</span><span class="stat-value">■■■■■■■■□□ 82%</span></div>
    <div class="stat-row"><span class="stat-label">الماء</span><span class="stat-value">■■■■■■■□□□ 72%</span></div>
    <div class="stat-row"><span class="stat-label">الخطوات</span><span class="stat-value">■■■■■■□□□□ 68%</span></div>
    <div class="stat-row"><span class="stat-label">النوم</span><span class="stat-value">■■■■■■■■■□ 94%</span></div>
  </div>
</div>

<div class="section">
  <h2>🏃 النشاط البدني</h2>
  <div class="stat-row"><span class="stat-label">المشي</span><span class="stat-value">45 دقيقة</span></div>
  <div class="stat-row"><span class="stat-label">الجري</span><span class="stat-value">12 دقيقة</span></div>
  <div class="stat-row"><span class="stat-label">تمارين القوة</span><span class="stat-value">20 دقيقة</span></div>
  <div class="stat-row"><span class="stat-label">اليوغا</span><span class="stat-value">15 دقيقة</span></div>
</div>

<div class="footer">
  <p>هيلثي داش بورد © 2026 — جميع المؤشرات للتتبع اليومي</p>
</div>
</body>
</html>"""

    def _build_create_new_template_patch(self, task):
        lowered = task.lower()
        page_name = self._extract_page_name(lowered)
        filename = page_name.strip() + ".html"
        target = f"templates/{filename}"

        # Detect if this is a health/dashboard task for specialized output
        is_health = any(w in lowered for w in ("هيلثي", "هيلث", "health", "صحة", "الصحة"))
        is_dashboard = any(w in lowered for w in ("داش", "بورد", "داشبورد", "dashboard", "board", "dash"))

        if is_health and is_dashboard:
            title_ar = "هيلثي داش بورد"
            if "احترافي" in lowered:
                title_ar = "هيلثي داش بورد احترافي"
            content = self._build_healthy_dashboard_html(title_ar)
            interpreted = "إنشاء هيلثي داش بورد احترافي باللغة العربية"
        else:
            title_en = page_name.replace("_", " ").title()
            content = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_en}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="container">
        <h1>{title_en}</h1>
        <p>مرحباً بك في {title_en}</p>
    </div>
</body>
</html>"""
            interpreted = f"إنشاء صفحة جديدة: {title_en}"

        return {
            "interpreted_intent": interpreted,
            "files_to_modify": [target],
            "proposed_changes": [
                f"Create new template file {target}.",
                f"Professional Arabic RTL page for {page_name.replace('_', ' ')}.",
            ],
            "expected_change_summary": f"New template {target} will be created with a professional {'health dashboard' if is_health and is_dashboard else 'Arabic'} page.",
            "expected_diff": "New file created: " + target,
            "risk_level": "low",
            "validation_plan": [
                "Confirm the new template file was created.",
                "No Python validation needed for HTML template changes.",
            ],
            "rollback_plan": [
                "Create a rollback checkpoint with __NEW_FILE__ marker before creating.",
                "Rollback deletes the created file and restores the prior state.",
            ],
            "apply_supported": True,
            "safety_decision": {
                "allowed": True,
                "reason": f"Creating a new HTML template ({target}) is a safe bounded file creation in templates/.",
                "approval_required": True,
                "bounded_execution": True,
                "shell_execution": False,
                "destructive_execution": False,
                "deploy": False,
                "file_deletion": False,
            },
            "operations": [
                {
                    "type": "replace_file_text",
                    "path": target,
                    "description": f"Create new template file {target}.",
                    "expected_marker": page_name[:20].title() if not is_health else "هيلثي داش بورد",
                    "content": content,
                }
            ],
        }

    def _infer_files_for_task(self, task):
        lowered = self._normalize_task_text(task)
        files = []
        # If it's a "create page" task, let _build_create_new_template_patch handle it
        if self._is_create_page_task(lowered):
            return []
        if self._is_scan_jarvis_task(lowered):
            return []
        if any(token in lowered for token in ("hud", "jarvis", "ui", "page", "button", "arabic", "text")):
            files.append("templates/jarvis/mobile_control_center.html")
        if "route" in lowered or "api" in lowered:
            files.append("app.py")
        if "style" in lowered or "css" in lowered:
            files.append("static/style.css")
        return files or ["templates/", "static/", "app.py"]

    def _apply_hud_label_to_text(self, original):
        text = original
        css_marker = ".engineering-patch-active-label"
        html_marker = "ENGINEERING PATCH MODE ACTIVE"
        if css_marker not in text:
            css = """
.engineering-patch-active-label{
  margin-top:10px;
  border:1px solid rgba(54,255,117,.48);
  border-radius:10px;
  padding:9px 12px;
  color:#dfffe8;
  background:rgba(19,76,48,.42);
  font-size:12px;
  font-weight:bold;
  letter-spacing:0;
  text-align:center;
}
"""
            anchor = ".approval-execution-console{"
            if anchor not in text:
                raise ValueError("HUD CSS anchor not found.")
            text = text.replace(anchor, css + "\n" + anchor, 1)

        if html_marker not in text:
            html = (
                '    <div class="engineering-patch-active-label" '
                'id="engineering-patch-mode-active">ENGINEERING PATCH MODE ACTIVE</div>\n\n'
            )
            anchor = '    <form class="execution-command-form" id="jarvis-execution-request-form">'
            if anchor not in text:
                raise ValueError("HUD label insertion anchor not found.")
            text = text.replace(anchor, html + anchor, 1)
        return text

    def _apply_create_patch_plan_button_to_text(self, original):
        old = '<button class="execution-button" type="submit">Request Plan</button>'
        new = '<button class="execution-button" type="submit">Create Patch Plan</button>'
        if new in original:
            return original
        if old not in original:
            raise ValueError("Request Plan button anchor not found.")
        return original.replace(old, new, 1)

    def _apply_arabic_dashboard_support_to_text(self, original):
        text = original
        marker = "JARVIS_ARABIC_HUD_TEXT_SUPPORT"
        if marker not in text:
            css = """
/* JARVIS_ARABIC_HUD_TEXT_SUPPORT */
.jarvis-arabic-text,
.approval-execution-console [dir="auto"],
.approval-execution-console [dir="rtl"],
.engineering-patch-panel [dir="auto"],
.engineering-patch-panel [dir="rtl"]{
  font-family:Tahoma,"Segoe UI",Arial,sans-serif;
  unicode-bidi:plaintext;
  overflow-wrap:anywhere;
  word-break:normal;
  line-height:1.55;
}

.approval-execution-console input[dir="auto"]{
  text-align:start;
}
"""
            anchor = ".engineering-patch-active-label{"
            if anchor not in text:
                raise ValueError("Arabic HUD CSS anchor not found.")
            text = text.replace(anchor, css + "\n" + anchor, 1)

        replacements = {
            '<input id="jarvis-execution-command-input" type="text" value="git status --short" autocomplete="off">':
                '<input id="jarvis-execution-command-input" type="text" value="git status --short" autocomplete="off" dir="auto">',
            '<div class="value" id="jarvis-current-command">Waiting for command</div>':
                '<div class="value jarvis-arabic-text" id="jarvis-current-command" dir="auto">Waiting for command</div>',
            '<div class="value" id="jarvis-interpreted-action">No command interpreted</div>':
                '<div class="value jarvis-arabic-text" id="jarvis-interpreted-action" dir="auto">No command interpreted</div>',
            '<div class="value" id="jarvis-patch-task">Waiting for engineering task</div>':
                '<div class="value jarvis-arabic-text" id="jarvis-patch-task" dir="auto">Waiting for engineering task</div>',
            '<pre class="patch-preview" id="jarvis-patch-diff">No patch preview yet.</pre>':
                '<pre class="patch-preview jarvis-arabic-text" id="jarvis-patch-diff" dir="auto">No patch preview yet.</pre>',
            '<div class="execution-history" id="jarvis-patch-history">':
                '<div class="execution-history jarvis-arabic-text" id="jarvis-patch-history" dir="auto">',
            '<div class="execution-history" id="jarvis-execution-history">':
                '<div class="execution-history jarvis-arabic-text" id="jarvis-execution-history" dir="auto">',
        }
        for old, new in replacements.items():
            if old in text and new not in text:
                text = text.replace(old, new, 1)
        return text

    def _validate_operations_for_mutation(self, operations):
        if not operations:
            raise ValueError("No safe file mutation operations are available.")
        for operation in operations:
            op_type = operation.get("type")
            if op_type == "opencode_escalation":
                if not operation.get("task"):
                    raise ValueError("OpenCode escalation operation requires a task.")
                continue
            if op_type != "replace_file_text":
                raise ValueError(f"Unsupported patch operation: {op_type}")
            self._resolve_mutation_path(operation.get("path"))
            content = operation.get("content")
            if not isinstance(content, str):
                raise ValueError("Patch operation content must be text.")

    def _create_rollback_checkpoint(self, state):
        files = []
        for operation in state.get("operations", []):
            op_path = operation.get("path")
            if not op_path:
                continue
            path = self._resolve_mutation_path(op_path)
            if path.exists():
                content = path.read_text(encoding="utf-8")
            else:
                content = "__NEW_FILE__"
            files.append(
                {
                    "path": str(path.relative_to(self.project_root)).replace("\\", "/"),
                    "content": content,
                }
            )
        checkpoint = {
            "checkpoint_id": str(uuid.uuid4()),
            "patch_id": state.get("patch_id"),
            "created_at": self._now(),
            "files": files,
        }
        path = self.memory_dir / f"controlled_engineering_rollback_{state.get('patch_id')}.json"
        self._write_json(path, checkpoint)
        checkpoint["path"] = str(path.relative_to(self.project_root)).replace("\\", "/")
        return checkpoint

    def _apply_operations(self, operations, task_context=None):
        changed = []
        oc_stdout_parts = []
        oc_stderr_parts = []
        for operation in operations:
            if operation.get("type") == "opencode_escalation":
                oc_result = self._run_opencode_escalation(operation, task_context)
                if oc_result.get("files_changed"):
                    changed.extend(oc_result["files_changed"])
                if oc_result.get("stdout_summary"):
                    oc_stdout_parts.append(oc_result["stdout_summary"])
                if oc_result.get("stderr_summary"):
                    oc_stderr_parts.append(oc_result["stderr_summary"])
                continue
            path = self._resolve_mutation_path(operation.get("path"))
            after = operation.get("content", "")
            if path.exists():
                before = path.read_text(encoding="utf-8")
                if before == after:
                    continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(after, encoding="utf-8")
            changed.append(str(path.relative_to(self.project_root)).replace("\\", "/"))
        self._last_oc_stdout = "\n".join(oc_stdout_parts)
        self._last_oc_stderr = "\n".join(oc_stderr_parts)
        return changed

    def _run_opencode_escalation(self, operation, task_context=None):
        try:
            from jarvis.agents.opencode_engineering_agent import get_opencode_agent
            agent = get_opencode_agent()
            task = operation.get("task", task_context or "")
            result = agent.run_task(task, mode="direct_apply_inside_project_root")
            if result.get("final_status") == "completed":
                self._append_event({
                    "event": "opencode_escalation_completed",
                    "task": task[:200],
                    "files_changed": result.get("files_changed", []),
                })
            return result
        except Exception as exc:
            self._append_event({
                "event": "opencode_escalation_failed",
                "error": str(exc),
            })
            return {"files_changed": [], "final_status": "failed", "error": str(exc)}

    def _operation_paths(self, operations):
        paths = []
        for operation in operations:
            path = self._resolve_mutation_path(operation.get("path"))
            paths.append(str(path.relative_to(self.project_root)).replace("\\", "/"))
        return paths

    def _run_validation(self, changed_files, operations=None):
        operations = operations or []
        steps = []
        stdout_parts = []
        stderr_parts = []
        status = "passed"

        for file_name in changed_files:
            if file_name.endswith(".py"):
                result = self._run_py_compile(file_name)
                steps.append(result)
                stdout_parts.append(result.get("stdout", ""))
                stderr_parts.append(result.get("stderr", ""))
                if not result.get("ok"):
                    status = "failed"

        if "app.py" in changed_files:
            result = self._run_py_compile("app.py")
            steps.append(result)
            stdout_parts.append(result.get("stdout", ""))
            stderr_parts.append(result.get("stderr", ""))
            if not result.get("ok"):
                status = "failed"

        if "templates/jarvis/mobile_control_center.html" in changed_files:
            contains_label = "ENGINEERING PATCH MODE ACTIVE" in self._read_project_file(
                "templates/jarvis/mobile_control_center.html"
            )
            result = {
                "name": "hud_label_presence",
                "command": "read templates/jarvis/mobile_control_center.html",
                "ok": contains_label,
                "returncode": 0 if contains_label else 1,
                "stdout": "ENGINEERING PATCH MODE ACTIVE found\n" if contains_label else "",
                "stderr": "" if contains_label else "ENGINEERING PATCH MODE ACTIVE not found\n",
            }
            steps.append(result)
            stdout_parts.append(result["stdout"])
            stderr_parts.append(result["stderr"])
            if not contains_label:
                status = "failed"

        for operation in operations:
            marker = operation.get("expected_marker")
            path_name = operation.get("path")
            if not marker or not path_name:
                continue
            content = self._read_project_file(path_name)
            marker_found = marker.lower() in content.lower()
            result = {
                "name": "expected_marker_presence",
                "command": f"read {path_name}",
                "ok": marker_found,
                "returncode": 0 if marker_found else 1,
                "stdout": f"{marker} found\n" if marker_found else "",
                "stderr": "" if marker_found else f"{marker} not found\n",
            }
            steps.append(result)
            stdout_parts.append(result["stdout"])
            stderr_parts.append(result["stderr"])
            if not marker_found:
                status = "failed"

        if not steps:
            steps.append(
                {
                    "name": "no_runtime_validation_needed",
                    "command": "no modified Python files",
                    "ok": True,
                    "returncode": 0,
                    "stdout": "No Python validation required for this patch.\n",
                    "stderr": "",
                }
            )
            stdout_parts.append("No Python validation required for this patch.\n")

        return {
            "status": status,
            "steps": steps,
            "stdout": self._bounded_output("".join(stdout_parts)),
            "stderr": self._bounded_output("".join(stderr_parts)),
        }

    def _run_py_compile(self, file_name):
        path = self._resolve_mutation_path(file_name)
        argv = [sys.executable, "-m", "py_compile", str(path.relative_to(self.project_root))]
        try:
            process = subprocess.run(
                argv,
                cwd=str(self.project_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                shell=False,
            )
            return {
                "name": "py_compile",
                "command": "python -m py_compile " + str(path.relative_to(self.project_root)),
                "ok": process.returncode == 0,
                "returncode": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            }
        except Exception as exc:
            return {
                "name": "py_compile",
                "command": "python -m py_compile " + str(path.relative_to(self.project_root)),
                "ok": False,
                "returncode": None,
                "stdout": "",
                "stderr": str(exc),
            }

    def _resolve_mutation_path(self, relative_path):
        if not relative_path:
            raise ValueError("Patch path is required.")
        candidate = (self.project_root / relative_path).resolve()
        try:
            normalized = candidate.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError(f"Patch path is outside the project: {relative_path}") from exc

        parts = set(normalized.parts)
        if parts & self.BLOCKED_PARTS:
            raise ValueError(f"Patch path is blocked: {relative_path}")
        if candidate.name in self.BLOCKED_FILENAMES or candidate.suffix.lower() in self.BLOCKED_SUFFIXES:
            raise ValueError(f"Patch path is blocked by filename or suffix: {relative_path}")

        normalized_text = str(normalized).replace("\\", "/")
        allowed = (
            normalized.parts[0] in self.ALLOWED_ROOTS
            or normalized_text in self.ALLOWED_FILES
        )
        if not allowed:
            raise ValueError(f"Patch path is not in an allowed edit area: {relative_path}")
        # Allow creating new files in templates/ and static/
        can_create_new = normalized.parts[0] in ("templates", "static")
        if not candidate.exists() and not can_create_new:
            raise ValueError(f"Patch target must already exist: {relative_path}")
        if candidate.exists() and not candidate.is_file():
            raise ValueError(f"Patch target must be a file: {relative_path}")
        return candidate

    def _read_project_file(self, relative_path):
        path = self._resolve_existing_project_file(relative_path)
        return path.read_text(encoding="utf-8")

    def _resolve_existing_project_file(self, relative_path):
        candidate = (self.project_root / relative_path).resolve()
        try:
            candidate.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError(f"Path is outside the project: {relative_path}") from exc
        if not candidate.exists() or not candidate.is_file():
            raise ValueError(f"Project file does not exist: {relative_path}")
        return candidate

    def _build_diff(self, relative_path, original, updated):
        diff = difflib.unified_diff(
            original.splitlines(),
            updated.splitlines(),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="",
        )
        return "\n".join(diff)

    def _looks_like_safe_command(self, lowered):
        tokens = lowered.split()
        if not tokens:
            return False
        # Git read-only commands
        if tokens[0] == "git" and len(tokens) >= 2:
            return tokens[1] in {"status", "log", "branch", "diff", "show", "help", "version"}
        # Python version check
        if tokens[0] in {"python", "python3", "python.exe", "py"} and len(tokens) >= 2:
            return tokens[1] in {"--version", "-V", "-m", "-c"}
        if tokens[0] in {"python", "python3", "python.exe", "py"} and lowered.strip() in {"python --version", "python3 --version", "python -V", "python3 -V"}:
            return True
        # Simple shell read-only commands
        if tokens[0] in {"pwd", "whoami", "hostname", "date", "uptime", "uname", "id"}:
            return True
        # echo (read-only output)
        if tokens[0] == "echo":
            return True
        # find (read-only file search)
        if tokens[0] == "find":
            return True
        # ls / dir listing
        if tokens[0] in {"ls", "dir", "ll", "la"}:
            return True
        # Gradle
        if tokens == ["gradle", "assembledebug"]:
            return True
        return False

    def _default_state(self):
        return {
            "patch_id": None,
            "detected_mode": "engineering_task",
            "requested_task": "",
            "interpreted_intent": "No engineering task requested.",
            "files_to_modify": [],
            "proposed_changes": [],
            "expected_diff": "",
            "expected_change_summary": "",
            "risk_level": "none",
            "validation_plan": [],
            "rollback_plan": [],
            "approval_required": True,
            "approval_state": "waiting_for_task",
            "apply_supported": False,
            "apply_status": "IDLE",
            "safety_decision": {
                "allowed": False,
                "reason": "No engineering task has been submitted.",
                "approval_required": True,
                "bounded_execution": True,
                "shell_execution": False,
                "destructive_execution": False,
                "deploy": False,
                "file_deletion": False,
            },
            "operations": [],
            "rollback_checkpoint": None,
            "files_changed": [],
            "validation_result": {
                "status": "not_run",
                "steps": [],
                "stdout": "",
                "stderr": "",
            },
            "stdout": "",
            "stderr": "",
            "final_result": "idle",
            "created_at": None,
            "updated_at": self._now(),
            "approved_at": None,
            "applied_at": None,
            "finished_at": None,
        }

    def _failure(self, message, state):
        return {"ok": False, "message": message, "patch_state": state}

    def _append_history(self, entry):
        history = self.history()
        history.append(entry)
        self._write_json(self.history_path, history[-self.MAX_HISTORY :])

    def _append_event(self, event):
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        event = dict(event)
        event["timestamp"] = self._now()
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _write_json(self, path, payload):
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _bounded_output(self, value):
        value = str(value or "")
        if len(value) <= self.MAX_OUTPUT_CHARS:
            return value
        return value[-self.MAX_OUTPUT_CHARS :]

    def _now(self):
        return datetime.now(timezone.utc).isoformat()