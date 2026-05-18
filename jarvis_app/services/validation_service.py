import subprocess
from pathlib import Path

from config import BASE_DIR


class ValidationService:
    def validate_files(self, files_changed):
        steps = []
        all_passed = True
        for f in files_changed:
            if f.endswith(".py"):
                step = self._py_compile(f)
                steps.append(step)
                if not step.get("ok"):
                    all_passed = False
        return {
            "status": "passed" if all_passed else "failed",
            "steps": steps,
            "files_checked": len(steps),
        }

    def _py_compile(self, file_path):
        full = BASE_DIR / file_path
        if not full.exists():
            return {"file": file_path, "ok": True, "reason": "not_found"}
        try:
            r = subprocess.run(
                ["python3", "-m", "py_compile", str(full)],
                capture_output=True, text=True, timeout=30,
            )
            return {
                "file": file_path,
                "ok": r.returncode == 0,
                "stdout": r.stdout[:500],
                "stderr": r.stderr[:500],
            }
        except Exception as exc:
            return {"file": file_path, "ok": False, "error": str(exc)}

    def check_file_exists(self, path):
        return (BASE_DIR / path).exists()
