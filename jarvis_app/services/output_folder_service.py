import os
from pathlib import Path

from config import BASE_DIR, DEFAULT_OUTPUT_DIR, ALLOWED_OUTPUT_ROOTS
from jarvis_app.utils.safety import is_safe_output_path


class OutputFolderService:
    def __init__(self):
        self._current = Path(DEFAULT_OUTPUT_DIR)

    def get_current(self):
        return {
            "current": str(self._current.resolve()),
            "exists": self._current.exists(),
        }

    def set_folder(self, folder_path):
        if not folder_path:
            return {"ok": False, "error": "No folder path provided"}
        p = Path(folder_path)
        if not p.is_absolute():
            p = BASE_DIR / p
        p = p.resolve()
        if not is_safe_output_path(p, ALLOWED_OUTPUT_ROOTS):
            return {"ok": False, "error": f"Folder {p} is outside allowed roots"}
        p.mkdir(parents=True, exist_ok=True)
        self._current = p
        return {"ok": True, "current": str(p)}

    def create_folder(self, folder_path):
        if not folder_path:
            return {"ok": False, "error": "No folder path provided"}
        p = Path(folder_path)
        if not p.is_absolute():
            p = BASE_DIR / p
        p = p.resolve()
        if not is_safe_output_path(p, ALLOWED_OUTPUT_ROOTS):
            return {"ok": False, "error": f"Folder {p} is outside allowed roots"}
        p.mkdir(parents=True, exist_ok=True)
        self._current = p
        return {"ok": True, "current": str(p), "created": True}

    def resolve_output(self, text, task_type):
        text_lower = text.lower()
        p = self._current

        if "in templates" in text_lower or "داخل templates" in text_lower or "في templates" in text_lower:
            p = BASE_DIR / "templates"
        elif "inside outputs" in text_lower or "داخل outputs" in text_lower or "في outputs" in text_lower:
            # Extract subfolder like "inside outputs/todo-app"
            import re
            m = re.search(r'(?:inside|in|داخل|في)\s+outputs[/\\]?(\S+)', text_lower)
            if m:
                sub = m.group(1).strip().rstrip("/").rstrip("\\")
                p = BASE_DIR / "outputs" / sub
            else:
                p = BASE_DIR / "outputs"
        elif "in static" in text_lower or "داخل static" in text_lower:
            p = BASE_DIR / "static"
        elif task_type == "engineering_create_file":
            p = BASE_DIR / "templates"

        p.mkdir(parents=True, exist_ok=True)
        self._current = p
        return str(p.resolve())

    def list_folders(self):
        folders = []
        roots = [BASE_DIR / "outputs", BASE_DIR / "templates"]
        for root in roots:
            if root.exists():
                for item in sorted(root.iterdir()):
                    if item.is_dir():
                        folders.append(str(item.resolve()))
        return folders
