"""
Rebuild library.json from whatever is in backend/assets/library/.

Walks <library>/<source>/<file>.<ext> and emits an entry per discovered
glTF / glb. Tag inference is intentionally minimal — we read sidecar
.json metadata if present (`<file>.tags.json`) for explicit override,
otherwise we infer from filename + folder.

Run with:

    python -m assets.index_library

Sidecar metadata format (optional; lives next to the asset file):

    {
      "type":    "character_rigged | enemy_rigged | weapon_handheld | prop_static | environment_tile | vfx | hdri",
      "tags":    ["humanoid", "scifi", "robot"],
      "anims":   ["idle", "walk", "run"],
      "tris":    3120,
      "license": "CC0",
      "credit":  "Original author / link"
    }
"""
import json
import re
import struct
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent
_LIBRARY_DIR = _ROOT / "library"
_INDEX_PATH = _ROOT / "library.json"


# Heuristic mappers from filename → type. Best-effort; sidecar metadata wins.
_TYPE_HINTS: list[tuple[str, str]] = [
    (r"\b(player|character|hero|robot|knight|alien|monster|zombie|skeleton|ninja|wizard|mage|ranger|warrior|hooded)\b", "character_rigged"),
    (r"\b(enemy|chaser|swarm|drone|grunt|boss|guard|spider|slime)\b",                                                   "enemy_rigged"),
    (r"\b(pistol|rifle|shotgun|sword|axe|bow|gun|weapon|blade|knife)\b",                                                 "weapon_handheld"),
    (r"\b(crate|barrel|chair|table|prop|chest|box|debris|vase|lamp|book)\b",                                             "prop_static"),
    (r"\b(floor|wall|tile|ceiling|brick|stone|panel|door|frame|column|pillar)\b",                                        "environment_tile"),
    (r"\b(particle|smoke|spark|sprite|vfx|effect)\b",                                                                    "vfx"),
    (r"\b(hdr|hdri|skybox|env)\b",                                                                                       "hdri"),
]

_TAG_FROM_FOLDER = {
    "khronos":    ["pbr", "test_model"],
    "kenney":     ["stylized", "low_poly"],
    "quaternius": ["stylized", "low_poly"],
    "mixamo":     ["humanoid", "rigged", "mocap"],
}


def _read_glb_triangle_count(path: Path) -> int:
    """Best-effort triangle count from a .glb header. Returns 0 on failure."""
    if path.suffix.lower() != ".glb":
        return 0
    try:
        with path.open("rb") as f:
            magic = f.read(4)
            if magic != b"glTF":
                return 0
            f.read(8)  # version + length
            chunk_len = struct.unpack("<I", f.read(4))[0]
            chunk_type = f.read(4)
            if chunk_type != b"JSON":
                return 0
            j = json.loads(f.read(chunk_len).decode("utf-8", errors="replace"))
        # Sum indices/3 for triangle primitives, fall back to vertex count/3.
        total = 0
        meshes = j.get("meshes", [])
        accessors = j.get("accessors", [])
        for m in meshes:
            for prim in m.get("primitives", []):
                if prim.get("mode", 4) != 4:  # TRIANGLES = 4
                    continue
                idx = prim.get("indices")
                if idx is not None and 0 <= idx < len(accessors):
                    total += accessors[idx].get("count", 0) // 3
                else:
                    pos_idx = prim.get("attributes", {}).get("POSITION")
                    if pos_idx is not None and 0 <= pos_idx < len(accessors):
                        total += accessors[pos_idx].get("count", 0) // 3
        return int(total)
    except Exception:
        return 0


def _read_glb_animation_names(path: Path) -> list[str]:
    if path.suffix.lower() != ".glb":
        return []
    try:
        with path.open("rb") as f:
            if f.read(4) != b"glTF":
                return []
            f.read(8)
            chunk_len = struct.unpack("<I", f.read(4))[0]
            if f.read(4) != b"JSON":
                return []
            j = json.loads(f.read(chunk_len).decode("utf-8", errors="replace"))
        return [a.get("name", f"anim_{i}") for i, a in enumerate(j.get("animations", []))]
    except Exception:
        return []


def _infer_type(name: str) -> str:
    lower = name.lower()
    for pattern, type_name in _TYPE_HINTS:
        if re.search(pattern, lower):
            return type_name
    return "prop_static"


def _infer_tags(rel_path: Path, name: str) -> list[str]:
    tags: list[str] = []
    folder_first = rel_path.parts[0] if rel_path.parts else ""
    tags.extend(_TAG_FROM_FOLDER.get(folder_first, []))
    lower = name.lower()
    for token in re.split(r"[\s_\-.]+", lower):
        if 2 < len(token) < 24 and token.isalpha() and token not in tags:
            tags.append(token)
    # Drop generic noise.
    for noise in ("glb", "gltf", "binary", "glb-binary"):
        if noise in tags:
            tags.remove(noise)
    return tags[:12]


def rebuild() -> dict:
    """Rebuild library.json from disk. Returns the new index."""
    index: dict = {
        "version": 1,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "sources": json.loads(_INDEX_PATH.read_text(encoding="utf-8")).get("sources", {})
                   if _INDEX_PATH.exists() else {},
        "assets": {},
    }

    if not _LIBRARY_DIR.exists():
        _LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

    for path in sorted(_LIBRARY_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".glb", ".gltf"):
            continue
        rel = path.relative_to(_LIBRARY_DIR)
        source = rel.parts[0] if rel.parts else "unknown"
        name = path.stem

        # Stable id: <source>_<filename_slug>
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        asset_id = f"{source}_{slug}"

        # Sidecar metadata override.
        sidecar = path.with_suffix(path.suffix + ".meta.json")
        meta = {}
        if sidecar.exists():
            try: meta = json.loads(sidecar.read_text(encoding="utf-8"))
            except Exception: meta = {}

        anims = meta.get("anims") or _read_glb_animation_names(path)
        tris = meta.get("tris") or _read_glb_triangle_count(path)
        type_ = meta.get("type") or _infer_type(name)
        tags = meta.get("tags") or _infer_tags(rel, name)
        # If the model has skeletal anims, mark it as rigged.
        if anims and "rigged" not in tags:
            tags.append("rigged")
        if anims and type_ == "prop_static":
            type_ = "character_rigged"

        index["assets"][asset_id] = {
            "path":    str(rel).replace("\\", "/"),
            "type":    type_,
            "tags":    tags,
            "anims":   anims,
            "tris":    tris,
            "size_bytes": path.stat().st_size,
            "source":  source,
            "license": meta.get("license", "CC0"),
            "credit":  meta.get("credit"),
        }

    _INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


if __name__ == "__main__":
    idx = rebuild()
    n = len(idx["assets"])
    print(f"Indexed {n} assets → {_INDEX_PATH}")
    if n == 0:
        print()
        print("Library is empty. To bootstrap a starter pack:")
        print("    python -m assets.bootstrap")
        print()
        print("Or drop your own glTF/glb files into:")
        print(f"    {_LIBRARY_DIR}/<source-name>/")
        print("and re-run this command.")
