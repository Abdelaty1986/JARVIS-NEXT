from pathlib import Path


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)
    return Path(path).resolve()


def safe_relative_to(path, root):
    try:
        return Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return None


def is_within_root(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def normalize_path(path):
    return str(Path(path).resolve())
