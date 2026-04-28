"""
Per-workspace SQLite checkpointer for LangGraph pipelines.

Why: a `MemorySaver` checkpoint is fine for a single live session but loses
everything on server restart. With a SQLite saver, every node completion
flushes to disk — close the browser, kill the server, come back tomorrow,
hit Resume and the graph picks up at the last completed node.

Usage:

    async with open_checkpointer(workspace_dir) as saver:
        graph = build_game_graph(checkpointer=saver)
        async for chunk in graph.astream(initial_state, config=cfg):
            ...

The saver context wraps the async db connection — keep it alive for the
whole graph execution. Falls back gracefully to MemorySaver if the sqlite
extras are missing OR if the runtime version mismatch raises during setup
or first use (e.g. an aiosqlite/langgraph-checkpoint-sqlite combo where
`alist` calls a removed Connection attribute).
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator


def _warn(msg: str) -> None:
    print(f"[checkpointer] {msg}", file=sys.stderr)


@asynccontextmanager
async def open_checkpointer(workspace_dir: str) -> AsyncIterator:
    """Yield a LangGraph checkpointer scoped to this workspace.

    Order of preference:
      1. AsyncSqliteSaver (per-workspace `checkpoint.db`) — full durable
         resume across server restart.
      2. MemorySaver — pause/resume still works while the server is up;
         resume across restart degrades to file-level (session.json) only.

    Any exception raised while *setting up* the sqlite saver is caught and
    triggers the MemorySaver fallback, so a botched dependency install
    can't take the whole pipeline down.
    """
    db_path = Path(workspace_dir) / "checkpoint.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    sqlite_ctx = None
    saver = None

    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        sqlite_ctx = AsyncSqliteSaver.from_conn_string(str(db_path))
    except ImportError:
        sqlite_ctx = None

    if sqlite_ctx is not None:
        try:
            saver = await sqlite_ctx.__aenter__()
            # Touch the API once to surface version-mismatch bugs at setup
            # time rather than mid-graph (where they'd kill the run).
            cfg = {"configurable": {"thread_id": "_probe"}}
            async for _ in saver.alist(cfg, limit=1):
                break
        except Exception as exc:
            _warn(f"sqlite saver unusable ({exc!r}); falling back to MemorySaver.")
            try:
                await sqlite_ctx.__aexit__(type(exc), exc, exc.__traceback__)
            except Exception:
                pass
            sqlite_ctx = None
            saver = None

    if saver is None:
        from langgraph.checkpoint.memory import MemorySaver
        saver = MemorySaver()

    try:
        yield saver
    finally:
        if sqlite_ctx is not None:
            try:
                await sqlite_ctx.__aexit__(None, None, None)
            except Exception:
                # Squash teardown errors — never mask a real exception
                # from inside the graph run.
                pass
