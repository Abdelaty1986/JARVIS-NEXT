import json
import shutil
from pathlib import Path

from config import RUNTIME_MEMORY_DIR


class RollbackService:
    def __init__(self, runtime_logs_dir):
        self.logs_dir = runtime_logs_dir

    def create_checkpoint(self, files):
        checkpoint = {
            "files": [],
        }
        for f in files:
            p = Path(f)
            if p.exists():
                content = p.read_text(encoding="utf-8")
            else:
                content = "__NEW_FILE__"
            checkpoint["files"].append({
                "path": str(p),
                "content": content,
            })
        return checkpoint

    def rollback(self, checkpoint):
        restored = []
        for entry in checkpoint.get("files", []):
            path = Path(entry["path"])
            if entry["content"] == "__NEW_FILE__":
                if path.exists():
                    path.unlink()
                restored.append(f"deleted {path}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(entry["content"], encoding="utf-8")
                restored.append(f"restored {path}")
        return {"ok": True, "restored": restored}
