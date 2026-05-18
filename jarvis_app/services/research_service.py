import json
import os
from pathlib import Path

from config import BASE_DIR, JARVIS_CORE_DIR


class ResearchService:
    def __init__(self, runtime_memory_dir):
        self.reports_dir = runtime_memory_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def scan_jarvis(self, task_text, action="report"):
        from datetime import datetime
        import uuid
        report = {
            "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "task": task_text[:200],
            "action": action,
            "target": "JARVIS_CORE",
            "files_scanned": 0,
            "issues": [],
            "summary": {},
        }
        issues = []
        files_scanned = 0
        if JARVIS_CORE_DIR.exists():
            for root, dirs, files in os.walk(JARVIS_CORE_DIR):
                for fn in files:
                    if fn.endswith(".py"):
                        files_scanned += 1
                        fpath = os.path.join(root, fn)
                        try:
                            content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            continue
                        for i, line in enumerate(content.splitlines(), 1):
                            stripped = line.strip()
                            if stripped.startswith("#") or stripped.startswith("import ") or stripped.startswith("from "):
                                continue
                            if "TODO" in stripped or "FIXME" in stripped or "XXX" in stripped:
                                rel = os.path.relpath(fpath, str(BASE_DIR))
                                issues.append({
                                    "file": rel, "line": i, "type": "todo_fixme",
                                    "text": stripped[:80],
                                })
                            if "print(" in stripped and "def " not in stripped and "logger" not in stripped:
                                pass
        report["files_scanned"] = files_scanned
        report["issues"] = issues[:50]
        report["summary"] = {
            "files_scanned": files_scanned,
            "total_issues": len(issues),
            "todo_fixme_count": sum(1 for i in issues if i.get("type") == "todo_fixme"),
        }
        report_file = self.reports_dir / f"scan_{uuid.uuid4().hex[:8]}.json"
        report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "ok": True,
            "files_scanned": files_scanned,
            "issues_found": len(issues),
            "report_file": str(report_file.relative_to(BASE_DIR)),
            "summary": report["summary"],
        }
