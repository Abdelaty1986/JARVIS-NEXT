import os
from pathlib import Path


BLOCKED_DIR_NAMES = {"erp-system", "erp_system", ".git"}
BLOCKED_FILE_SUFFIXES = {".exe", ".dll", ".so", ".dylib", ".bin"}
BLOCKED_COMMANDS = {"rm -rf /", "rm -rf ~", "sudo", "chmod 777", "dd if=", ">:",
                    "git push", "git commit"}


def is_safe_output_path(path, allowed_roots):
    p = Path(path).resolve()
    for root in allowed_roots:
        try:
            p.relative_to(Path(root).resolve())
            return True
        except ValueError:
            continue
    return False


def is_safe_command(command):
    cmd_lower = command.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return False, f"Blocked command fragment: {blocked}"
    safe_prefixes = (
        "git status", "git branch", "git log", "pwd", "ls",
        "find ", "grep ", "echo ", "python --version",
        "python3 --version", "whoami", "date", "which",
    )
    if cmd_lower.startswith(safe_prefixes):
        return True, ""
    return False, "Command not in safe list"
