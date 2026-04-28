"""
Session metadata persistence — sits alongside the LangGraph SQLite
checkpoint and stores the *non-graph* fields the API needs to resume:
session_id, brief, genre, files emitted, token total, pause timestamp,
preview URL, etc.

The LangGraph checkpoint records what each agent has produced; this file
records what the SSE clients need to redraw the UI on resume.
"""
import json
import time
from pathlib import Path
from typing import Optional


_NON_PERSISTABLE = {"task"}    # asyncio.Task can't survive pickling/restart


def save_session(workspace_dir: str, payload: dict) -> str:
    """Atomically persist the session dict to <ws>/session.json."""
    p = Path(workspace_dir) / "session.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: v for k, v in payload.items() if k not in _NON_PERSISTABLE}
    safe.setdefault("saved_at", int(time.time() * 1000))
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(safe, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)
    return str(p)


def load_session(workspace_dir: str) -> Optional[dict]:
    p = Path(workspace_dir) / "session.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_sessions(workspace_root: str, prefix: str = "", paused_only: bool = False) -> list[dict]:
    """List persisted sessions under workspace_root, newest first.

    Each entry: {session_id, workspace_dir, brief, paused, paused_at, ...}.
    Sessions without a session.json are skipped. Capped at 25 entries.
    """
    root = Path(workspace_root)
    if not root.exists():
        return []

    out: list[dict] = []
    for sd in root.iterdir():
        if not sd.is_dir():
            continue
        if prefix and not sd.name.startswith(prefix):
            continue
        s = load_session(str(sd))
        if not s or "session_id" not in s:
            continue
        if paused_only and not s.get("paused"):
            continue
        s["workspace_dir"] = str(sd)
        out.append(s)

    out.sort(key=lambda d: d.get("saved_at", 0), reverse=True)
    return out[:25]


def mark_paused(workspace_dir: str, session: dict) -> None:
    """Helper: set paused=True, stamp paused_at, persist."""
    session["paused"] = True
    session["paused_at"] = int(time.time() * 1000)
    save_session(workspace_dir, session)


def mark_resumed(workspace_dir: str, session: dict) -> None:
    """Helper: clear paused, persist."""
    session["paused"] = False
    session.pop("paused_at", None)
    save_session(workspace_dir, session)
