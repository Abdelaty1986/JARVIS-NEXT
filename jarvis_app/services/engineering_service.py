import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import BASE_DIR, TEMPLATES_DIR


class EngineeringService:
    def __init__(self, runtime_logs_dir):
        self.logs_dir = runtime_logs_dir

    def create_html_page(self, page_name, content=None, output_dir=None):
        if not output_dir:
            output_dir = TEMPLATES_DIR
        else:
            output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = page_name.strip().lower().replace(" ", "_").replace("-", "_") + ".html"
        target = output_dir / filename

        if content is None:
            title = page_name.replace("_", " ").title()
            content = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>{title}</title></head>
<body><div class="container"><h1>{title}</h1><p>Created by JARVIS-NEXT</p></div></body>
</html>"""

        target.write_text(content, encoding="utf-8")
        return {
            "ok": True,
            "file": str(target.relative_to(BASE_DIR)),
            "page_name": page_name,
            "output_dir": str(output_dir),
        }

    def generate_healthy_dashboard(self, output_dir=None):
        if not output_dir:
            output_dir = TEMPLATES_DIR
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / "healthy_dashboard.html"
        content = self._build_healthy_dashboard_html()
        target.write_text(content, encoding="utf-8")
        return {
            "ok": True,
            "file": str(target.relative_to(BASE_DIR)),
        }

    def _build_healthy_dashboard_html(self):
        return """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>هيلثي داش بورد</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI','Cairo',Tahoma,sans-serif;}
body{background:#0f172a;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}
.dashboard{max-width:1200px;width:100%;}
.header{text-align:center;margin-bottom:40px;}
.header h1{font-size:2.5em;color:#00f0ff;text-shadow:0 0 20px rgba(0,240,255,.3);}
.header p{color:#94a3b8;margin-top:8px;}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px;margin-bottom:30px;}
.card{background:#1e293b;border-radius:16px;padding:24px;border:1px solid rgba(0,240,255,.1);transition:transform .2s;}
.card:hover{transform:translateY(-4px);border-color:rgba(0,240,255,.3);}
.card .icon{font-size:2em;margin-bottom:12px;}
.card .label{color:#94a3b8;font-size:.85em;text-transform:uppercase;letter-spacing:1px;}
.card .value{font-size:2em;font-weight:bold;margin:8px 0;color:#00f0ff;}
.card .progress{height:6px;background:#0f172a;border-radius:3px;overflow:hidden;margin-top:8px;}
.card .progress .bar{height:100%;border-radius:3px;transition:width 1s;}
.bar-water{background:#38bdf8;width:75%;}
.bar-steps{background:#a78bfa;width:62%;}
.bar-sleep{background:#f472b6;width:80%;}
.bar-calories{background:#fb923c;width:55%;}
.stats{background:#1e293b;border-radius:16px;padding:24px;border:1px solid rgba(0,240,255,.1);}
.stats h2{color:#00f0ff;margin-bottom:16px;}
.stat-row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(0,240,255,.05);}
.stat-row:last-child{border-bottom:none;}
.stat-label{color:#94a3b8;}
.stat-value{color:#e2e8f0;font-weight:bold;}
.activities{background:#1e293b;border-radius:16px;padding:24px;margin-top:20px;border:1px solid rgba(0,240,255,.1);}
.activities h2{color:#00f0ff;margin-bottom:16px;}
.activity-item{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(0,240,255,.05);}
.activity-item:last-child{border-bottom:none;}
.activity-time{color:#64748b;font-size:.85em;}
</style>
</head>
<body>
<div class="dashboard">
<div class="header">
<h1>🏥 هيلثي داش بورد</h1>
<p>نظام متابعة الصحة الشخصية</p>
</div>
<div class="grid">
<div class="card"><div class="icon">🔥</div><div class="label">السعرات الحرارية</div><div class="value">1,850</div><div class="progress"><div class="bar bar-calories" style="width:55%"></div></div></div>
<div class="card"><div class="icon">💧</div><div class="label">المياه</div><div class="value">2.1 لتر</div><div class="progress"><div class="bar bar-water" style="width:75%"></div></div></div>
<div class="card"><div class="icon">👣</div><div class="label">الخطوات</div><div class="value">8,420</div><div class="progress"><div class="bar bar-steps" style="width:62%"></div></div></div>
<div class="card"><div class="icon">😴</div><div class="label">النوم</div><div class="value">7.5 ساعات</div><div class="progress"><div class="bar bar-sleep" style="width:80%"></div></div></div>
</div>
<div class="stats"><h2>📊 إحصائيات اليوم</h2>
<div class="stat-row"><span class="stat-label">معدل ضربات القلب</span><span class="stat-value">72 نبضة/دقيقة</span></div>
<div class="stat-row"><span class="stat-label">ضغط الدم</span><span class="stat-value">120/80 مم زئبق</span></div>
<div class="stat-row"><span class="stat-label">الأكسجين في الدم</span><span class="stat-value">98%</span></div>
<div class="stat-row"><span class="stat-label">الوزن</span><span class="stat-value">75 كجم</span></div>
<div class="stat-row"><span class="stat-label">مؤشر كتلة الجسم</span><span class="stat-value">23.4</span></div>
</div>
<div class="activities"><h2>⚡ النشاطات الأخيرة</h2>
<div class="activity-item"><span>🏃 جري صباحي</span><span class="activity-time">30 دقيقة • 7:00 ص</span></div>
<div class="activity-item"><span>🧘 يوغا</span><span class="activity-time">20 دقيقة • 12:30 م</span></div>
<div class="activity-item"><span>🚶 مشي مسائي</span><span class="activity-time">15 دقيقة • 8:00 م</span></div>
</div>
</div>
</body>
</html>"""

    def generate_scan_report(self, task_text):
        report = {
            "scan_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "task": task_text[:200],
            "files_scanned": 0,
            "issues_found": [],
            "summary": {},
        }
        scan_dir = BASE_DIR / "JARVIS_CORE"
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
        report["files_scanned"] = files_scanned
        report["issues_found"] = issues[:50]
        report["summary"] = {
            "total_files_scanned": files_scanned,
            "total_issues": len(issues),
            "todo_fixme_count": sum(1 for i in issues if i.get("type") == "todo_fixme"),
        }

        report_dir = BASE_DIR / "runtime_memory" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"scan_report_{uuid.uuid4().hex[:8]}.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "ok": True,
            "files_scanned": files_scanned,
            "issues_found": len(issues),
            "report_file": str(report_path.relative_to(BASE_DIR)),
            "summary": report["summary"],
        }
