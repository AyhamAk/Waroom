import os
from pathlib import Path


def _safe_path(workspace: str, rel_path: str) -> str:
    ws = Path(workspace).resolve()
    full = (ws / rel_path.lstrip("/")).resolve()
    if not str(full).startswith(str(ws)):
        raise ValueError(f"Path traversal blocked: {rel_path}")
    return str(full)


def read_file(workspace: str, path: str) -> str:
    try:
        full = _safe_path(workspace, path)
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return f"(file not found: {path})"
    except Exception as e:
        return f"(error reading {path}: {e})"


def write_file(workspace: str, path: str, content: str) -> dict:
    try:
        full = _safe_path(workspace, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        lines = content.count("\n") + 1
        return {"ok": True, "path": path, "lines": lines, "bytes": len(content)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_files(workspace: str, subdir: str = "") -> list:
    try:
        base = (Path(workspace) / subdir) if subdir else Path(workspace)
        result = []
        for p in sorted(base.rglob("*")):
            if p.is_file() and ".git" not in str(p) and "node_modules" not in str(p):
                rel = str(p.relative_to(workspace)).replace("\\", "/")
                result.append({"path": rel, "size": p.stat().st_size})
        return result
    except Exception as e:
        return [{"error": str(e)}]
