#!/usr/bin/env python3
"""
JARVIS Mobile Control Center – full-cycle end-to-end verification.

Tests every button, every endpoint, and the large engineering order.
Prints a PASS/FAIL table and execution summary.
"""

import json
import os
import shutil
import subprocess
import sys
import time

TMP_MEMORY = "/tmp/jarvis_verify_memory"
TMP_LOGS = "/tmp/jarvis_verify_logs"

os.environ["RUNTIME_MEMORY_DIR"] = TMP_MEMORY
os.environ["RUNTIME_LOGS_DIR"] = TMP_LOGS

# Must happen BEFORE importing app modules
from jarvis_app import create_app

app = create_app()
client = app.test_client()

import config

config.RUNTIME_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
config.RUNTIME_LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

class Tester:
    def __init__(self):
        self.results = []
        self.pass_count = 0
        self.fail_count = 0

    def test(self, label, fn):
        try:
            fn()
            self.results.append((label, "PASS", ""))
            self.pass_count += 1
        except Exception as e:
            self.results.append((label, "FAIL", str(e)[:100]))
            self.fail_count += 1

    def api(self, method, path, data=None):
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(
                path,
                data=json.dumps(data or {}),
                content_type="application/json",
            )
        return resp.get_json()

    def print_report(self):
        print()
        print("=" * 72)
        print(f"  FINAL RESULTS:  {self.pass_count} PASS  /  {self.fail_count} FAIL")
        print("=" * 72)
        print(f"  {'Test':40s} {'Result':7s}  {'Error'}")
        print(f"  {'-'*40} {'-'*7}  {'-'*40}")
        for label, status, err in self.results:
            err_short = err[:60] if err else ""
            print(f"  {label:40s} {status:7s}  {err_short}")
        print()
        return self.fail_count == 0


# ===========================================================================
# TESTS
# ===========================================================================

t = Tester()

# ---- Phase 1: Basic API endpoints (used by UI polling) ----

print("=== PHASE 1: Basic API Endpoints ===")

t.test("GET /jarvis/api/status", lambda: (
    (r := t.api("GET", "/jarvis/api/status")) and r.get("status") == "ok" or 1 / 0
))

t.test("GET /jarvis/api/runtime/status", lambda: (
    (r := t.api("GET", "/jarvis/api/runtime/status"))
    and "mode" in r
    or 1 / 0
))

t.test("GET /jarvis/api/agents", lambda: (
    (r := t.api("GET", "/jarvis/api/agents")) and "agents" in r or 1 / 0
))

t.test("GET /jarvis/api/voice/status", lambda: (
    (r := t.api("GET", "/jarvis/api/voice/status")) and "enabled" in r or 1 / 0
))

t.test("GET /jarvis/api/engineering/status", lambda: (
    (r := t.api("GET", "/jarvis/api/engineering/status"))
    and r.get("available") is True
    or 1 / 0
))

t.test("GET /jarvis/api/execution/status", lambda: (
    (r := t.api("GET", "/jarvis/api/execution/status"))
    and r.get("mode") == "active"
    or 1 / 0
))

# ---- Phase 2: Safe execution actions ----

print("\n=== PHASE 2: Safe Execution Actions ===")

t.test("POST /jarvis/api/runtime/execute (git status)", lambda: (
    (r := t.api("POST", "/jarvis/api/runtime/execute",
                {"command": "git status", "task": "git status"}))
    and r.get("status") == "waiting_approval"
    or 1 / 0
))

t.test("POST /jarvis/api/execution/approve", lambda: (
    (r := t.api("POST", "/jarvis/api/execution/approve", {}))
    and r.get("status") == "approved"
    or 1 / 0
))

t.test("POST /jarvis/api/execution/run", lambda: (
    (r := t.api("POST", "/jarvis/api/execution/run", {}))
    and r.get("status") in ("completed", "failed")
    or 1 / 0
))

# ---- Phase 3: Engineering pipeline ----

print("\n=== PHASE 3: Engineering Pipeline ===")

t.test("POST /jarvis/api/engineering/execute", lambda: (
    (r := t.api("POST", "/jarvis/api/engineering/execute",
                {"command": "create a test page verifypage",
                 "task": "create a test page verifypage"}))
    and r.get("status") == "waiting_approval"
    and r.get("plan") is not None
    or 1 / 0
))

# Track task id for approve/apply
tasks = t.api("GET", "/jarvis/api/runtime/tasks") or []
eng_tasks = [tk for tk in tasks if tk.get("route", "").startswith("engineering.")]
eng_id = eng_tasks[0]["task_id"] if eng_tasks else None

t.test("POST /jarvis/api/engineering/approve", lambda: (
    eng_id is not None
    and (r := t.api("POST", "/jarvis/api/engineering/approve",
                    {"task_id": eng_id}))
    and r.get("status") == "approved"
    or 1 / 0
))

t.test("POST /jarvis/api/engineering/apply", lambda: (
    (r := t.api("POST", "/jarvis/api/engineering/apply",
                {"task_id": eng_id}))
    and r.get("status") == "completed"
    and len(r.get("created_files", []) + r.get("modified_files", [])) >= 1
    or 1 / 0
))

t.test("GET /jarvis/verifypage (created page)", lambda: (
    client.get("/jarvis/verifypage").status_code == 200 or 1 / 0
))

# ---- Phase 4: GET endpoints ----

print("\n=== PHASE 4: GET Endpoints ===")

t.test("GET /jarvis/api/runtime/tasks", lambda: (
    len(t.api("GET", "/jarvis/api/runtime/tasks") or []) >= 1 or 1 / 0
))

t.test("GET /jarvis/api/runtime/task/<id>", lambda: (
    (tasks := t.api("GET", "/jarvis/api/runtime/tasks"))
    and len(tasks) > 0
    and (r := t.api("GET", f"/jarvis/api/runtime/task/{tasks[0]['task_id']}"))
    and "status" in r
    or 1 / 0
))

t.test("GET /jarvis/api/engineering/history", lambda: (
    (r := t.api("GET", "/jarvis/api/engineering/history"))
    and "history" in r
    or 1 / 0
))

t.test("GET /jarvis/api/engineering/task/<id>", lambda: (
    (r := t.api("GET", f"/jarvis/api/engineering/task/{eng_id}"))
    and r.get("status") == "completed"
    or 1 / 0
))

t.test("GET /jarvis/api/execution/current", lambda: (
    (r := t.api("GET", "/jarvis/api/execution/current"))
    and "tasks" in r
    or 1 / 0
))

t.test("GET /jarvis/mobile (UI template)", lambda: (
    client.get("/jarvis/mobile").status_code == 200 or 1 / 0
))

# ---- Phase 5: Large engineering order ----

print("\n=== PHASE 5: Large Engineering Order (diagnostics page) ===")

LARGE_ORDER = (
    "Create a new JARVIS diagnostics page at /jarvis/diagnostics. "
    "The page must show: server status, runtime status, agents status, "
    "voice status, recent task history, execution results, and a button "
    "returning to the Mobile Control Center."
)

t.test("POST /jarvis/api/engineering/execute (large order)", lambda: (
    (r := t.api("POST", "/jarvis/api/engineering/execute",
                {"command": LARGE_ORDER, "task": LARGE_ORDER}))
    and r.get("status") == "waiting_approval"
    and "/jarvis/diagnostics" in str(r.get("plan", {}).get("final_urls", []))
    or 1 / 0
))

tasks = t.api("GET", "/jarvis/api/runtime/tasks") or []
diag_tasks = [tk for tk in tasks if "diagnostics" in tk.get("raw_text", "").lower()]
diag_id = diag_tasks[0]["task_id"] if diag_tasks else None

t.test("POST /jarvis/api/engineering/approve (large)", lambda: (
    diag_id is not None
    and (r := t.api("POST", "/jarvis/api/engineering/approve",
                    {"task_id": diag_id}))
    and r.get("status") == "approved"
    or 1 / 0
))

apply_result = t.api("POST", "/jarvis/api/engineering/apply",
                     {"task_id": diag_id})

t.test("POST /jarvis/api/engineering/apply (large)", lambda: (
    apply_result is not None
    and apply_result.get("status") == "completed"
    or 1 / 0
))

t.test("GET /jarvis/diagnostics returns 200", lambda: (
    client.get("/jarvis/diagnostics").status_code == 200 or 1 / 0
))

# Verify page content
diag_resp = client.get("/jarvis/diagnostics")
if diag_resp.status_code == 200:
    html = diag_resp.data.decode()
    t.test("Diagnostics page has title", lambda: "Diagnostics" in html or 1 / 0)
    t.test("Diagnostics page has mobile link", lambda: "/jarvis/mobile" in html or 1 / 0)

# ---- Phase 6: Validation (py_compile) ----

print("\n=== PHASE 6: Validation ===")

t.test("py_compile app.py", lambda: (
    subprocess.run(
        ["python3", "-m", "py_compile", "app.py"],
        capture_output=True, cwd=str(config.BASE_DIR),
    ).returncode
    == 0
    or 1 / 0
))

t.test("py_compile engineering_execution_service.py", lambda: (
    subprocess.run(
        ["python3", "-m", "py_compile",
         "jarvis_app/services/engineering_execution_service.py"],
        capture_output=True, cwd=str(config.BASE_DIR),
    ).returncode
    == 0
    or 1 / 0
))

t.test("py_compile engineering_routes.py", lambda: (
    subprocess.run(
        ["python3", "-m", "py_compile",
         "jarvis_app/routes/engineering_routes.py"],
        capture_output=True, cwd=str(config.BASE_DIR),
    ).returncode
    == 0
    or 1 / 0
))

t.test("py_compile execution_routes.py", lambda: (
    subprocess.run(
        ["python3", "-m", "py_compile",
         "jarvis_app/routes/execution_routes.py"],
        capture_output=True, cwd=str(config.BASE_DIR),
    ).returncode
    == 0
    or 1 / 0
))

t.test("py_compile runtime_routes.py", lambda: (
    subprocess.run(
        ["python3", "-m", "py_compile",
         "jarvis_app/routes/runtime_routes.py"],
        capture_output=True, cwd=str(config.BASE_DIR),
    ).returncode
    == 0
    or 1 / 0
))

t.test("py_compile task_state_service.py", lambda: (
    subprocess.run(
        ["python3", "-m", "py_compile",
         "jarvis_app/services/task_state_service.py"],
        capture_output=True, cwd=str(config.BASE_DIR),
    ).returncode
    == 0
    or 1 / 0
))

# ===========================================================================
# Report
# ===========================================================================

all_ok = t.print_report()

print("=== LARGE ORDER EXECUTION DETAILS ===")
if apply_result:
    for key in (
        "status",
        "created_files",
        "modified_files",
        "final_urls",
        "validation",
        "rollback_snapshot_id",
        "summary",
    ):
        print(f"  {key:25s}: {apply_result.get(key, 'N/A')}")
    out = apply_result.get("stdout", "")
    if out:
        print(f"  {'stdout':25s}: {out[:400]}")
else:
    print("  (large order apply failed)")

print()
if all_ok:
    print("VERIFICATION COMPLETE – ALL CHECKS PASSED")
    sys.exit(0)
else:
    print(f"VERIFICATION COMPLETE – {t.fail_count} CHECK(S) FAILED")
    sys.exit(1)
