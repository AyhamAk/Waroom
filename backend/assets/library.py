"""
Asset library — search, fetch, and copy CC0 glTFs into a session workspace.

The index lives at backend/assets/library.json. Files live at
backend/assets/library/<source>/<file>. The Asset Lead queries via tag
filters; the bridge copies the chosen file into the per-session workspace
so the runtime can serve it as `/assets/<file>.glb`.
"""
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Optional


_ROOT = Path(__file__).parent
_LIBRARY_DIR = _ROOT / "library"
_INDEX_PATH = _ROOT / "library.json"


# ─── Public API ───────────────────────────────────────────────────────────────

def library_path() -> Path:
    return _LIBRARY_DIR


def _load_index() -> dict:
    if not _INDEX_PATH.exists():
        return {"version": 1, "assets": {}, "sources": {}}
    try:
        return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "assets": {}, "sources": {}}


def get_asset(asset_id: str) -> Optional[dict]:
    """Return the full library entry for an id, or None."""
    idx = _load_index()
    entry = idx.get("assets", {}).get(asset_id)
    if not entry:
        return None
    return {**entry, "id": asset_id}


def library_summary() -> dict:
    """Return counts + tag/type histograms for the Asset Lead's prompt context."""
    idx = _load_index()
    assets = idx.get("assets", {})
    type_counts = Counter()
    tag_counts = Counter()
    for entry in assets.values():
        type_counts[entry.get("type", "unknown")] += 1
        for t in entry.get("tags", []):
            tag_counts[t] += 1
    return {
        "asset_count": len(assets),
        "types": dict(type_counts),
        "top_tags": dict(tag_counts.most_common(40)),
        "sources": idx.get("sources", {}),
    }


def available_types() -> list[str]:
    return sorted(library_summary()["types"].keys())


def available_tags(top_n: int = 100) -> list[str]:
    counts = library_summary()["top_tags"]
    return list(counts.keys())[:top_n]


def search_library(
    type: Optional[str] = None,
    tags: Optional[list[str]] = None,
    anims: Optional[list[str]] = None,
    max_tris: Optional[int] = None,
    limit: int = 8,
) -> list[dict]:
    """Return ranked matches.

    Hard filters: type (exact), anims (must contain all listed),
    max_tris (must be ≤). Soft scoring: tag overlap (more = higher),
    smaller tri count breaks ties.
    """
    idx = _load_index()
    assets = idx.get("assets", {})
    candidates: list[dict] = []
    for asset_id, entry in assets.items():
        if type and entry.get("type") != type:
            continue
        if anims:
            available = set(entry.get("anims", []))
            if not all(a in available for a in anims):
                continue
        if max_tris is not None and entry.get("tris", 0) > max_tris:
            continue
        candidates.append({**entry, "id": asset_id})

    def score(entry: dict) -> tuple:
        tag_overlap = 0
        if tags:
            entry_tags = set(entry.get("tags", []))
            tag_overlap = sum(1 for t in tags if t in entry_tags)
        # higher tag overlap first; smaller tri count first as tiebreaker
        return (tag_overlap, -entry.get("tris", 0))

    candidates.sort(key=score, reverse=True)
    return candidates[:limit]


def copy_to_workspace(asset_id: str, workspace_dir: str) -> Optional[dict]:
    """Copy the asset into <workspace>/game/public/assets/ and return a
    runtime-ready manifest entry. Returns None if the id is unknown or
    the file is missing on disk."""
    entry = get_asset(asset_id)
    if not entry:
        return None
    src = _LIBRARY_DIR / entry["path"]
    if not src.exists():
        return None

    target_dir = Path(workspace_dir) / "game" / "public" / "assets"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / src.name
    if not target.exists():
        shutil.copy2(src, target)

    return {
        "id": asset_id,
        "type": "gltf",
        "path": f"/assets/{src.name}",
        "abs_path": str(target),
        "size_bytes": target.stat().st_size,
        "anims": entry.get("anims", []),
        "tris": entry.get("tris", 0),
        "source": entry.get("source", "library"),
        "license": entry.get("license", "CC0"),
        "library_id": asset_id,
        "tags": entry.get("tags", []),
    }
