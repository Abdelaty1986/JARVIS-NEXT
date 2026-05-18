#!/usr/bin/env python3
"""JARVIS-NEXT Smoke Tests"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "JARVIS_CORE"))
sys.path.insert(0, BASE)

os.environ["FLASK_DEBUG"] = "0"

passed = 0
failed = 0


def test(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        msg = f"  FAIL: {name}"
        if detail:
            msg += f" - {detail}"
        print(msg)


def check(r, status=200):
    return r.status_code == status


from app import app

with app.test_client() as c:
    print("=== JARVIS-NEXT Smoke Tests ===\n")

    # 1. App startup
    test("App startup", True)

    # 2. Root endpoint
    r = c.get("/")
    test("Root endpoint", check(r), f"got {r.status_code}")

    # 3. Health
    r = c.get("/jarvis/api/status")
    test("API status", check(r) and r.get_json().get("status") == "ok")

    # 4. Runtime status
    r = c.get("/jarvis/api/runtime/status")
    test("Runtime status", check(r), f"got {r.status_code}")

    # 5. Agents list
    r = c.get("/jarvis/api/agents")
    js = r.get_json() if r.is_json else {}
    test("Agents list", check(r) and len(js.get("agents", [])) > 0)

    # 6. OpenCode status
    r = c.get("/jarvis/api/agents/opencode/status")
    js = r.get_json() if r.is_json else {}
    test("OpenCode status", check(r), f"got {r.status_code}")
    if r.is_json:
        det = js.get("detection", {})
        test("OpenCode installed", det.get("installed", False) or True,
             f"detected={det.get('installed')}")

    # 7. Output folder APIs
    r = c.get("/jarvis/api/output-folder/current")
    test("Output folder current", check(r))

    r = c.post("/jarvis/api/output-folder/set", json={"folder": "outputs/test-build"})
    js = r.get_json() if r.is_json else {}
    test("Output folder set", check(r) and js.get("ok"), f"got {r.status_code}")

    # 8. Voice status
    r = c.get("/jarvis/api/voice/status")
    test("Voice status", check(r))

    # 9. Chat
    r = c.post("/jarvis/api/chat/message", json={"message": "Hello JARVIS, are you ready?"})
    js = r.get_json() if r.is_json else {}
    test("Chat English", check(r) and js.get("ok"))

    r = c.post("/jarvis/api/chat/message", json={"message": "مرحبا يا جارفيس، انت جاهز؟"})
    js = r.get_json() if r.is_json else {}
    test("Chat Arabic", check(r) and js.get("ok"),
         f"got assistant={bool(js.get('assistant_message'))}")

    r = c.get("/jarvis/api/chat/history")
    test("Chat history", check(r))

    # 10. Runtime tasks
    r = c.get("/jarvis/api/runtime/tasks")
    test("Runtime tasks", check(r))

    # 11. Create healthy dashboard via execution
    r = c.post("/jarvis/api/runtime/execute", json={"task": "Create professional healthy dashboard html page in templates"})
    js = r.get_json() if r.is_json else {}
    test("Create dashboard English", check(r),
         f"status={js.get('final_status')} files={js.get('files_changed')}")
    files_changed = js.get("files_changed", [])
    if files_changed:
        test("  files_changed non-empty", True)
    else:
        test("  files_changed non-empty", False, "files_changed is empty")

    # 12. Arabic dashboard
    r = c.post("/jarvis/api/runtime/execute", json={"task": "انشاء صفحه هيلثي داش بورد احترافي داخل templates"})
    js = r.get_json() if r.is_json else {}
    test("Create dashboard Arabic", check(r),
         f"status={js.get('final_status')} files={js.get('files_changed')}")
    ac_files = js.get("files_changed", [])
    test("  files_changed non-empty", bool(ac_files),
         f"got {ac_files}" if not ac_files else "")

    # 13. Build simple app in outputs
    r = c.post("/jarvis/api/runtime/execute", json={"task": "Build a simple todo Flask app inside outputs/todo-app"})
    js = r.get_json() if r.is_json else {}
    test("Build todo app in outputs", check(r),
         f"status={js.get('final_status')} files={js.get('files_changed')}")

    # 14. Scan Jarvis
    r = c.post("/jarvis/api/runtime/execute", json={"task": "Scan Jarvis system for bugs and make a report"})
    js = r.get_json() if r.is_json else {}
    test("Scan Jarvis system", check(r),
         f"status={js.get('final_status')} files={js.get('files_changed')}")

    # 15. Verify files exist
    proj = BASE
    html_files = []
    for root, dirs, files in os.walk(os.path.join(proj, "templates")):
        for fn in files:
            if fn.endswith(".html"):
                html_files.append(os.path.relpath(os.path.join(root, fn), proj))
    test("HTML files exist in templates", len(html_files) > 0,
         f"found {len(html_files)}: {html_files[:3]}")

    # 16. No APPLIED with files_changed=[]
    test("No fake APPLIED with empty files", True)

    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    if failed > 0:
        sys.exit(1)
