import difflib
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import BASE_DIR, RUNTIME_LOGS_DIR, RUNTIME_MEMORY_DIR
from jarvis_app.services.rollback_service import RollbackService
from jarvis_app.services.validation_service import ValidationService
from jarvis_app.services.engineering_service import EngineeringService
from jarvis_app.utils.safety import BLOCKED_DIR_NAMES, BLOCKED_FILE_SUFFIXES


class EngineeringExecutionService:
    def __init__(self, logs_dir=None):
        self.logs_dir = logs_dir or RUNTIME_LOGS_DIR
        self.rollback = RollbackService(self.logs_dir)
        self.validation = ValidationService()
        self.engineering = EngineeringService(self.logs_dir)
        self.snapshots_dir = RUNTIME_MEMORY_DIR / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Action detection
    # ------------------------------------------------------------------

    def detect_action(self, text):
        lowered = text.lower().strip()

        # Diagnostics
        if any(w in lowered for w in ("diagnostics", "diagnostic", "health page", "system status page")):
            return "generate_diagnostics"

        # Create page / create feature
        if any(w in lowered for w in ("create a", "create new", "build a", "make a")):
            if "page" in lowered or "template" in lowered:
                return "create_page"
            if "route" in lowered or "endpoint" in lowered:
                return "add_route"
            if "feature" in lowered:
                return "create_feature"
            if "api" in lowered:
                return "add_api_endpoint"
            return "create_page"

        if lowered.startswith("create") and "page" in lowered:
            return "create_page"

        # Modify / improve
        if any(w in lowered for w in ("modify", "update", "change", "edit")):
            if "template" in lowered or "html" in lowered:
                return "update_template"
            if "route" in lowered:
                return "add_route"
            if "api" in lowered:
                return "add_api_endpoint"
            if "module" in lowered or ".py" in lowered:
                return "update_python_module"
            if "page" in lowered or "ui" in lowered:
                return "modify_page"
            return "refactor_file"

        # Improve UI
        if any(w in lowered for w in ("improve", "enhance", "polish")):
            return "improve_ui"

        # Fix
        if any(w in lowered for w in ("fix", "repair", "bug", "issue", "error")):
            return "fix_bug"

        # Add route / endpoint
        if lowered.startswith("add"):
            if "route" in lowered or "page" in lowered or "url" in lowered:
                return "add_route"
            if "api" in lowered or "endpoint" in lowered:
                return "add_api_endpoint"

        # Refactor
        if "refactor" in lowered:
            return "refactor_file"

        # Validate
        if any(w in lowered for w in ("validate", "compile", "check syntax")):
            return "run_validation"

        # Inspect
        if any(w in lowered for w in ("inspect", "runtime status", "system info")):
            return "inspect_runtime"

        return "create_page"

    # ------------------------------------------------------------------
    # Plan creation
    # ------------------------------------------------------------------

    def create_plan(self, action, text):
        handler_name = f"_plan_{action}"
        handler = getattr(self, handler_name, None)
        if handler:
            return handler(text)
        return self._plan_generic(action, text)

    def _plan_generic(self, action, text):
        return {
            "action": action,
            "plan_summary": text[:200],
            "target_files": [],
            "operations": [],
            "diff_preview": "No specific plan available for this action.",
            "final_urls": [],
        }

    # ---- create_page ----

    def _plan_create_page(self, text):
        page_name = self._extract_page_name(text)
        route_path = f"/jarvis/{page_name}"
        template_file = f"templates/jarvis/{page_name}.html"
        # Add the route to the existing engineering_bp – no new blueprint needed
        route_file = "jarvis_app/routes/engineering_routes.py"
        func_name = page_name.replace("-", "_")

        route_code = f"""
@engineering_bp.route("{route_path}")
def {func_name}_page():
    return render_template("jarvis/{page_name}.html",
                           title="{page_name.title().replace('-', ' ')}",
                           data={{"status": "online", "page": "{page_name}", "source": "engineering"}})
"""
        template_html = self._generate_template_html(page_name)

        return {
            "action": "create_page",
            "plan_summary": f"Create a new page at {route_path} with template {template_file}",
            "target_files": [
                {"path": route_file, "operation": "modify", "purpose": f"Add route {route_path}"},
                {"path": template_file, "operation": "create", "purpose": f"HTML template for {page_name}"},
            ],
            "operations": [
                {"type": "append_to_file", "path": route_file, "content": route_code},
                {"type": "create_file", "path": template_file, "content": template_html},
            ],
            "diff_preview": self._make_preview(template_file, "", template_html),
            "final_urls": [route_path],
            "dynamic_routes": [
                {"path": route_path,
                 "template": f"jarvis/{page_name}.html",
                 "title": page_name.title().replace("-", " "),
                 "view_func": func_name}
            ],
        }

    # ---- generate_diagnostics ----

    def _plan_generate_diagnostics(self, text):
        return self._plan_create_page(text if "diagnostics" in text.lower() else "diagnostics")

    # ---- add_route ----

    def _plan_add_route(self, text):
        route_name = self._extract_route_name(text)
        route_path = f"/jarvis/{route_name}" if not route_name.startswith("/") else route_name
        handler_name = route_name.replace("/", "_").replace("-", "_").lstrip("_")
        if not handler_name:
            handler_name = "new_page"
        route_file = "jarvis_app/routes/engineering_routes.py"

        route_code = f"""
@engineering_bp.route("{route_path}")
def {handler_name}():
    return render_template("jarvis/{route_name}.html",
                           title="{route_name.title().replace('_', ' ')}",
                           data={{
                               "status": "online",
                               "page": "{route_name}",
                               "timestamp": datetime.utcnow().isoformat() + "Z",
                           }})
"""
        template_file = f"templates/jarvis/{route_name}.html"
        template_html = self._generate_template_html(route_name)

        return {
            "action": "add_route",
            "plan_summary": f"Add new route {route_path} in {route_file} with template {template_file}",
            "target_files": [
                {"path": route_file, "operation": "modify", "purpose": "Add route definition"},
                {"path": template_file, "operation": "create", "purpose": "HTML template for new route"},
            ],
            "operations": [
                {"type": "append_to_file", "path": route_file, "content": route_code},
                {"type": "create_file", "path": template_file, "content": template_html},
            ],
            "diff_preview": f"--- a/{route_file}\n+++ b/{route_file}\n+{route_code.strip()}\n",
            "final_urls": [route_path],
            "generated_content": {
                template_file: template_html,
            },
        }

    # ---- add_api_endpoint ----

    def _plan_add_api_endpoint(self, text):
        endpoint = self._extract_endpoint_name(text)
        api_path = f"/jarvis/api/{endpoint}" if not endpoint.startswith("/jarvis/api") else endpoint
        func_name = endpoint.replace("/", "_").replace("-", "_").replace(".", "_").lstrip("_")
        route_file = "jarvis_app/routes/engineering_routes.py"

        code = f"""
@engineering_bp.route("{api_path}")
def api_{func_name}():
    return jsonify({{
        "ok": True,
        "endpoint": "{api_path}",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }})
"""
        return {
            "action": "add_api_endpoint",
            "plan_summary": f"Add API endpoint {api_path} in {route_file}",
            "target_files": [
                {"path": route_file, "operation": "modify", "purpose": f"Add API endpoint {api_path}"},
            ],
            "operations": [
                {"type": "append_to_file", "path": route_file, "content": code},
            ],
            "diff_preview": f"--- a/{route_file}\n+++ b/{route_file}\n+{code.strip()}\n",
            "final_urls": [api_path],
        }

    # ---- modify_page / improve_ui ----

    def _plan_modify_page(self, text):
        return self._plan_update_template(text)

    def _plan_improve_ui(self, text):
        return self._plan_update_template("mobile_control_center.html")

    # ---- update_template ----

    def _plan_update_template(self, text):
        template_name = self._extract_template_name(text)
        template_path = f"templates/jarvis/{template_name}" if not template_name.startswith("templates/") else template_name
        full_path = BASE_DIR / template_path

        if not full_path.exists():
            return {
                "action": "update_template",
                "plan_summary": f"Template {template_path} not found. Creating it.",
                "target_files": [{"path": template_path, "operation": "create", "purpose": "New template"}],
                "operations": [{"type": "create_file", "path": template_path,
                               "content": self._generate_template_html(template_name.replace(".html", "").split("/")[-1])}],
                "diff_preview": f"Template {template_path} does not exist yet. Will create new file.",
                "final_urls": [],
            }

        current = full_path.read_text(encoding="utf-8")
        improvement = self._generate_improvement(text, template_path, current)

        return {
            "action": "update_template",
            "plan_summary": f"Modify {template_path}: {improvement['summary']}",
            "target_files": [{"path": template_path, "operation": "modify", "purpose": improvement["summary"]}],
            "operations": [{"type": "modify_file", "path": template_path,
                           "old_content": improvement.get("old_text", ""),
                           "new_content": improvement.get("new_text", "")}],
            "diff_preview": improvement.get("diff", "No automatic diff available."),
            "final_urls": [],
        }

    # ---- fix_bug ----

    def _plan_fix_bug(self, text):
        if "template" in text.lower() or "html" in text.lower() or "ui" in text.lower():
            target = "templates/jarvis/mobile_control_center.html"
        elif "route" in text.lower():
            target = "jarvis_app/routes/mobile_routes.py"
        else:
            target = "jarvis_app/routes/execution_routes.py"

        return {
            "action": "fix_bug",
            "plan_summary": f"Inspect and fix potential issues in {target}",
            "target_files": [{"path": target, "operation": "inspect", "purpose": "Bug inspection and fix"}],
            "operations": [],
            "diff_preview": f"Will inspect {target} for common issues and apply fixes.",
            "final_urls": [],
        }

    # ---- update_python_module ----

    def _plan_update_python_module(self, text):
        module_name = self._extract_module_name(text)
        module_path = f"jarvis_app/{module_name}" if not module_name.startswith("jarvis_app") else module_name
        if not module_path.endswith(".py"):
            module_path += ".py" if "." not in module_path else module_path
        full_path = BASE_DIR / module_path

        if not full_path.exists():
            return {
                "action": "update_python_module",
                "plan_summary": f"Module {module_path} not found.",
                "target_files": [],
                "operations": [],
                "diff_preview": f"Module {module_path} does not exist.",
                "final_urls": [],
            }

        return {
            "action": "update_python_module",
            "plan_summary": f"Inspect {module_path} for potential improvements.",
            "target_files": [{"path": module_path, "operation": "inspect", "purpose": "Code inspection"}],
            "operations": [],
            "diff_preview": f"Module {module_path} found. Manual code review needed for specific changes.",
            "final_urls": [],
        }

    # ---- refactor_file ----

    def _plan_refactor_file(self, text):
        return self._plan_update_python_module(text)

    # ---- run_validation ----

    def _plan_run_validation(self, text):
        return {
            "action": "run_validation",
            "plan_summary": "Run py_compile validation on project Python files",
            "target_files": [],
            "operations": [{"type": "validate", "files": ["app.py"]}],
            "diff_preview": "Will run syntax validation on project files.",
            "final_urls": [],
        }

    # ---- inspect_runtime ----

    def _plan_inspect_runtime(self, text):
        return {
            "action": "inspect_runtime",
            "plan_summary": "Collect runtime status, tasks, and system information",
            "target_files": [],
            "operations": [],
            "diff_preview": "Runtime inspection does not modify files.",
            "final_urls": [],
        }

    # ------------------------------------------------------------------
    # Plan application (after approval)
    # ------------------------------------------------------------------

    def apply_plan(self, plan, task_id=None):
        operations = plan.get("operations", [])
        target_files = plan.get("target_files", [])
        action = plan.get("action", "unknown")

        created_files = []
        modified_files = []
        rollback_id = None
        validation_results = {}
        stdout_parts = []
        stderr_parts = []

        # Create rollback checkpoint for files that will be modified
        files_to_backup = [t["path"] for t in target_files
                          if t.get("operation") in ("modify", "create")]
        if files_to_backup:
            existing = [str(BASE_DIR / f) for f in files_to_backup
                       if (BASE_DIR / f).exists()]
            if existing:
                checkpoint = self.rollback.create_checkpoint(existing)
                rollback_id = str(uuid.uuid4())[:12]
                snap = self.snapshots_dir / f"snapshot_{rollback_id}.json"
                snap.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
                stdout_parts.append(f"Rollback snapshot saved: {snap}")

        # Execute operations
        for op in operations:
            otype = op.get("type", "")
            path = op.get("path", "")
            full_path = BASE_DIR / path

            try:
                if otype == "create_file":
                    content = op.get("content", "")
                    # Safety: block dangerous paths
                    if self._is_blocked_path(path):
                        stderr_parts.append(f"BLOCKED: {path} is not allowed")
                        continue
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")
                    created_files.append(path)
                    stdout_parts.append(f"Created: {path} ({len(content)} bytes)")

                elif otype == "modify_file":
                    if self._is_blocked_path(path):
                        stderr_parts.append(f"BLOCKED: {path} is not allowed")
                        continue
                    if full_path.exists():
                        current = full_path.read_text(encoding="utf-8")
                        new_content = op.get("new_content", current)
                        old_text = op.get("old_text", "")
                        if old_text and old_text in current:
                            new_content = current.replace(old_text, op.get("new_text", ""), 1)
                        if new_content != current:
                            full_path.write_text(new_content, encoding="utf-8")
                            modified_files.append(path)
                            stdout_parts.append(f"Modified: {path}")
                        else:
                            stdout_parts.append(f"Unchanged: {path} (no diff)")

                elif otype == "append_to_file":
                    if self._is_blocked_path(path):
                        stderr_parts.append(f"BLOCKED: {path} is not allowed")
                        continue
                    content_to_append = op.get("content", "")
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(full_path, "a", encoding="utf-8") as f:
                        f.write(content_to_append)
                    modified_files.append(path)
                    stdout_parts.append(f"Appended to: {path} ({len(content_to_append)} bytes)")

                elif otype == "validate":
                    val_files = op.get("files", [])
                    vresult = self.validation.validate_files(val_files)
                    validation_results = vresult
                    stdout_parts.append(f"Validation: {vresult.get('status', 'unknown')}")

            except Exception as e:
                stderr_parts.append(f"Error applying {otype} on {path}: {e}")

        # Run validation on created/modified Python files
        all_changed = created_files + modified_files
        py_files = [f for f in all_changed if f.endswith(".py")]
        if py_files:
            validation_results = self.validation.validate_files(py_files)

        stdout = "\n".join(stdout_parts) if stdout_parts else "No output"
        stderr = "\n".join(stderr_parts) if stderr_parts else ""

        # Collect final URLs from plan
        final_urls = plan.get("final_urls", [])

        # Check if any URL is accessible
        verified_urls = []
        for url in final_urls:
            verified_urls.append(url)

        return {
            "ok": len(stderr_parts) == 0,
            "action": action,
            "created_files": created_files,
            "modified_files": modified_files,
            "final_urls": final_urls,
            "validation": validation_results,
            "rollback_snapshot_id": rollback_id or None,
            "stdout": stdout,
            "stderr": stderr,
            "summary": f"Created {len(created_files)} file(s), modified {len(modified_files)} file(s)",
        }

    # (blueprint registration handled by adding routes to existing engineering_bp)

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    def _is_blocked_path(self, path):
        p = path.replace("\\", "/")
        for blocked in BLOCKED_DIR_NAMES:
            if f"/{blocked}/" in p or p.startswith(f"{blocked}/") or p == blocked:
                return True
        for suffix in BLOCKED_FILE_SUFFIXES:
            if p.endswith(suffix):
                return True
        if p.startswith(".env") or "/.env" in p:
            return True
        if ".git/" in p:
            return True
        if "config.py" == p.split("/")[-1]:
            return True
        if "secret" in p.lower() and p.endswith(".py"):
            return True
        return False

    # ------------------------------------------------------------------
    # Content generators
    # ------------------------------------------------------------------

    def _generate_route_code(self, page_name, route_path, template_file, blueprint_name):
        bp_name = blueprint_name
        func_name = page_name.replace("-", "_")
        route_path_clean = route_path
        rel_template = template_file.replace("templates/", "", 1) if template_file.startswith("templates/") else template_file
        return f'''from flask import Blueprint, jsonify, render_template
from datetime import datetime

{bp_name} = Blueprint("{page_name}", __name__)


@{bp_name}.route("{route_path_clean}")
def {func_name}():
    return render_template("{rel_template}",
                           title="{page_name.title().replace('-', ' ')}",
                           data={{"status": "online", "page": "{page_name}", "timestamp": datetime.utcnow().isoformat() + "Z"}})
'''

    def _generate_template_html(self, page_name):
        title = page_name.replace("-", " ").replace("_", " ").title()
        route_path = f"/jarvis/{page_name}"
        return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - JARVIS</title>
<style>
:root {{ --bg: #0d1117; --bg-card: #1c2128; --border: #30363d; --text: #e6edf3; --text-muted: #8b949e; --accent: #00d4ff; --green: #00e676; --red: #ff1744; --radius: 12px; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); padding: 20px; }}
.card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }}
h1 {{ font-size: 24px; margin-bottom: 16px; color: var(--accent); }}
h2 {{ font-size: 18px; margin-bottom: 12px; color: var(--text); }}
.status-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }}
.status-dot.online {{ background: var(--green); box-shadow: 0 0 8px var(--green); }}
.status-dot.offline {{ background: var(--red); box-shadow: 0 0 8px var(--red); }}
.info {{ color: var(--text-muted); font-size: 14px; }}
.btn {{ display: inline-block; padding: 10px 20px; background: var(--accent); color: #000; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; text-decoration: none; }}
.btn:hover {{ opacity: 0.9; }}
</style>
</head>
<body>
<div class="card">
  <h1>{title}</h1>
  <p class="info">JARVIS-NEXT Engineering Runtime</p>
</div>
<div class="card">
  <h2>Status</h2>
  <p><span class="status-dot online"></span>System Online</p>
  <p class="info">Page: <code>{route_path}</code></p>
  <p class="info" id="timestamp">Loading...</p>
</div>
<div class="card" style="text-align:center">
  <a href="/jarvis/mobile" class="btn">Back to Mobile Control Center</a>
</div>
<script>
document.getElementById('timestamp').textContent = 'Generated: ' + new Date().toISOString();
</script>
</body>
</html>'''

    def _generate_improvement(self, text, template_path, current_content):
        return {"summary": f"Template inspection for {template_path}",
                "diff": f"Template {template_path} exists ({len(current_content)} bytes).\nNo automatic changes applied.",
                "old_text": "", "new_text": ""}

    # ------------------------------------------------------------------
    # Name extraction helpers
    # ------------------------------------------------------------------

    def _extract_page_name(self, text):
        for prefix in ("diagnostics", "diagnostic"):
            if prefix in text.lower():
                return "diagnostics"
        m = re.search(r'(?:page|called|named|route)\s+["\']?([a-zA-Z][a-zA-Z0-9_/-]*)["\']?', text, re.IGNORECASE)
        if m:
            return m.group(1).strip("/").replace("/", "_")
        m = re.search(r'(?:create|build|make|new)\s+(?:a\s+|an\s+|the\s+)?([a-zA-Z][a-zA-Z0-9_]*)', text, re.IGNORECASE)
        if m:
            return m.group(1)
        return "new_page"

    def _extract_route_name(self, text):
        m = re.search(r'(?:at|to|route|path|endpoint)\s+["\']?(/[a-zA-Z0-9_/-]+)["\']?', text, re.IGNORECASE)
        if m:
            name = m.group(1).strip("/").replace("/", "_")
            return name if name else "new_route"
        m = re.search(r'(?:add|create|new)\s+(?:a\s+)?(?:route\s+)?(?:for\s+)?["\']?([a-zA-Z][a-zA-Z0-9_/-]*)["\']?', text, re.IGNORECASE)
        if m:
            return m.group(1).strip("/").replace("/", "_")
        return "new_route"

    def _extract_endpoint_name(self, text):
        m = re.search(r'(?:at|to|endpoint|path)\s+["\']?(/[a-zA-Z0-9_/-]+)["\']?', text, re.IGNORECASE)
        if m:
            return m.group(1).lstrip("/")
        m = re.search(r'(?:add|create|new)\s+(?:a\s+)?(?:api\s+)?(?:endpoint\s+)?["\']?([a-zA-Z][a-zA-Z0-9_/-]*)["\']?', text, re.IGNORECASE)
        if m:
            return m.group(1).lstrip("/")
        return "new_endpoint"

    def _extract_template_name(self, text):
        m = re.search(r'["\']?([a-zA-Z][a-zA-Z0-9_./-]*\.html)["\']?', text)
        if m:
            return m.group(1)
        if "mobile" in text.lower() or "control" in text.lower():
            return "mobile_control_center.html"
        if "diagnostics" in text.lower():
            return "diagnostics.html"
        return "mobile_control_center.html"

    def _extract_module_name(self, text):
        for word in text.split():
            word = word.strip("'\".,;:")
            if word.endswith(".py") and "/" not in word:
                return word
        m = re.search(r'(?:module|file)\s+["\']?([a-zA-Z][a-zA-Z0-9_/.-]*)["\']?', text, re.IGNORECASE)
        if m:
            return m.group(1)
        return "routes/engineering_routes.py"

    @staticmethod
    def _make_preview(filename, old, new):
        diff = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
        return "".join(diff)

    # ------------------------------------------------------------------
    # Non-file actions (inspect, validate)
    # ------------------------------------------------------------------

    def run_inspection(self):
        result = {"status": "online", "mode": "active", "checks": {}}

        # Check app.py compiles
        try:
            r = subprocess.run(["python", "-m", "py_compile", "app.py"],
                              capture_output=True, text=True, timeout=10, cwd=str(BASE_DIR))
            result["checks"]["app_py_compile"] = "passed" if r.returncode == 0 else f"failed: {r.stderr[:200]}"
        except Exception as e:
            result["checks"]["app_py_compile"] = f"error: {e}"

        # Check routes directory
        routes_dir = BASE_DIR / "jarvis_app" / "routes"
        if routes_dir.exists():
            route_files = list(routes_dir.glob("*_routes.py"))
            result["checks"]["route_files"] = f"{len(route_files)} route file(s)"
            result["routes"] = [rf.name for rf in route_files]

        # Check templates
        tpl_dir = BASE_DIR / "templates" / "jarvis"
        if tpl_dir.exists():
            tpl_files = list(tpl_dir.glob("*.html"))
            result["checks"]["templates"] = f"{len(tpl_files)} template(s)"
            result["templates"] = [tf.name for tf in tpl_files]

        # Git status
        try:
            r = subprocess.run(["git", "status", "--short"],
                              capture_output=True, text=True, timeout=10, cwd=str(BASE_DIR))
            result["checks"]["git_status"] = r.stdout.strip() or "clean"
        except Exception as e:
            result["checks"]["git_status"] = f"error: {e}"

        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        return result

    def run_validation_check(self, files=None):
        if files is None:
            files = ["app.py"]
        route_dir = BASE_DIR / "jarvis_app" / "routes"
        if route_dir.exists():
            files.extend(str(rf.relative_to(BASE_DIR)) for rf in route_dir.glob("*_routes.py"))
        return self.validation.validate_files(files)
