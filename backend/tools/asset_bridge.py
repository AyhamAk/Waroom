"""
Asset Bridge — Asset Lead → Blender pipeline → glTF for the game.

Reuses the existing ahujasid Blender MCP plus bpy_runtime. For each asset
the Asset Lead requests:
    1. Build a minimal scene of just that asset using br helpers.
    2. Export it as glTF/glb via bpy.ops.export_scene.gltf.
    3. Save into <workspace>/game/public/assets/<asset_id>.glb.
    4. Return the relative path the game will fetch at runtime.

Designed so the Asset Lead never writes raw Python — it calls request_asset
with a short typed spec and gets back a path. The bridge is best-effort: if
Blender is offline, primitive assets are still produced from a procedural
fallback so the game build does not stall.
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from tools.blender_tool import execute_blender_async, ping as blender_ping
from tools.bpy_runtime import get_runtime_source, install_marker_code


# Procedural fallback metadata — the runtime will use Assets.primitive()
# when these files don't exist on disk.
_PROCEDURAL_KINDS = {"cube", "sphere", "cylinder", "capsule", "plane", "torus", "cone"}


async def _ensure_runtime_loaded() -> bool:
    marker = await execute_blender_async(install_marker_code(), timeout=10)
    out = marker.get("result") or ""
    if "RUNTIME_MISSING" in out or "RUNTIME_OUTDATED" in out or marker.get("status") == "error":
        load = await execute_blender_async(get_runtime_source(), timeout=30)
        return load.get("status") != "error"
    return True


def _build_code_for_asset(spec: dict, gltf_path: str) -> str:
    """
    Build a tiny Python program that, when run inside Blender, constructs the
    asset and exports it as glTF/glb. The Asset Lead supplies the spec; we
    materialise it via br helpers so no raw bpy gets executed.
    """
    spec_json = json.dumps(spec)
    out_path = gltf_path.replace("\\", "/")
    return f"""
import json, traceback
try:
    spec = json.loads(r\"\"\"{spec_json}\"\"\")
    # Clear scene to a known state.
    br._safe_remove_all()
    kind = spec.get("kind", "cube")
    name = spec.get("id", "asset")
    color = spec.get("color", "#aaaaaa")
    metallic = float(spec.get("metallic", 0.0))
    roughness = float(spec.get("roughness", 0.6))
    size = float(spec.get("size", 1.0))

    # Material.
    mat = br.make_pbr(name + "_mat", base_color=color, metallic=metallic, roughness=roughness)

    # Geometry — fall back to a cube for any unknown kind. make_object is
    # the single safe entry point (no bpy.ops, context-free).
    prim_map = {
        "cube": "CUBE",
        "sphere": "UV_SPHERE",
        "cylinder": "CYLINDER",
        "cone": "CONE",
        "plane": "PLANE",
        "torus": "TORUS",
        "capsule": "CYLINDER",   # approx — runtime can replace with capsule
        "monkey": "MONKEY",
    }
    primitive = prim_map.get(kind.lower(), "CUBE")
    obj = br.make_object(
        name, primitive=primitive,
        scale=(size, size, size),
        material=mat,
        shade_smooth=(primitive in ("UV_SPHERE", "CYLINDER", "CONE", "TORUS", "MONKEY")),
    )

    # Centre to origin so the runtime can position freely.
    obj.location = (0, 0, 0)

    # Export glTF (binary). bpy.ops.export_scene.gltf is the supported path.
    import bpy, os
    os.makedirs(os.path.dirname(r"{out_path}"), exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=r"{out_path}",
        export_format='GLB',
        use_selection=True,
        export_apply=True,
        export_yup=True,
    )
    print("ASSET_EXPORTED:", r"{out_path}")
except Exception as e:
    traceback.print_exc()
    print("ASSET_EXPORT_ERROR:", str(e))
"""


def _procedural_manifest_entry(asset_id: str, spec: dict) -> dict:
    """
    For primitives we don't bother round-tripping through Blender — the
    runtime can build them via Assets.primitive(). Return a manifest entry
    that signals "procedural" to the loader.
    """
    return {
        "id": asset_id,
        "type": "procedural",
        "kind": spec.get("kind", "cube"),
        "color": spec.get("color", "#aaaaaa"),
        "metallic": float(spec.get("metallic", 0)),
        "roughness": float(spec.get("roughness", 0.6)),
        "size": float(spec.get("size", 1.0)),
    }


async def request_asset(workspace_dir: str, asset_id: str, spec: dict) -> dict:
    """
    Build (or fall back to procedural) a single asset and return its
    manifest entry. Never raises — if Blender is unreachable we degrade
    gracefully so the game still ships.
    """
    spec = dict(spec or {})
    kind = spec.get("kind", "cube")

    # Procedural shortcut — covers most "placeholder" cases the agents need.
    if spec.get("procedural") or kind in _PROCEDURAL_KINDS and not spec.get("force_blender"):
        return _procedural_manifest_entry(asset_id, spec)

    # Path layout: assets land inside the Vite project's public/ so they
    # are copied to the build output and served at /assets/...
    rel_path = f"public/assets/{asset_id}.glb"
    gltf_path = str(Path(workspace_dir) / "game" / rel_path)
    Path(gltf_path).parent.mkdir(parents=True, exist_ok=True)

    if not blender_ping():
        # Blender is offline — degrade to procedural so the build still ships.
        entry = _procedural_manifest_entry(asset_id, spec)
        entry["note"] = "blender_offline_fallback"
        return entry

    if not await _ensure_runtime_loaded():
        entry = _procedural_manifest_entry(asset_id, spec)
        entry["note"] = "runtime_load_failed"
        return entry

    code = _build_code_for_asset(spec, gltf_path)
    result = await execute_blender_async(code, timeout=60)
    out = result.get("result") or ""
    ok = "ASSET_EXPORTED:" in out and Path(gltf_path).exists()

    if not ok:
        entry = _procedural_manifest_entry(asset_id, spec)
        entry["note"] = "blender_export_failed"
        entry["error"] = (out[-300:] if out else "(no output)")
        return entry

    return {
        "id": asset_id,
        "type": "gltf",
        "path": "/assets/" + Path(gltf_path).name,    # served URL
        "abs_path": gltf_path,
        "size_bytes": Path(gltf_path).stat().st_size,
    }


# ── Library-first picking ─────────────────────────────────────────────────────
# When the Asset Lead requests a *slot* (e.g. "I need a humanoid character with
# walk + run animations") we first search the curated CC0 library. If we find
# a match, we copy the file into the workspace and return a glTF manifest
# entry. Falls through to a procedural primitive if nothing matches the slot's
# type or the library is empty.

def pick_from_library(slot: dict) -> dict | None:
    """
    Search the asset library for a slot spec and return a runtime-ready
    entry if one matches. The slot dict shape:

        {
          "id":    "<your_chosen_asset_id>",   # how the runtime refers to it
          "type":  "character_rigged | enemy_rigged | weapon_handheld |
                    prop_static | environment_tile",
          "tags":  ["humanoid", "scifi", "robot"],   # ranking signal
          "anims": ["walk", "run"],                  # required if listed
          "max_tris": 8000,                          # optional cap
        }

    Returns None when no match (caller falls back to primitive).
    """
    try:
        from assets import search_library
    except ImportError:
        return None
    hits = search_library(
        type=slot.get("type"),
        tags=slot.get("tags") or [],
        anims=slot.get("anims") or [],
        max_tris=slot.get("max_tris"),
        limit=1,
    )
    return hits[0] if hits else None


async def request_slot(workspace_dir: str, slot: dict) -> dict:
    """
    Library-first asset resolution for the Asset Lead. Tries the curated
    glTF library; falls back to a procedural primitive when nothing
    matches the slot's type/tags/anims. Always returns a manifest entry.
    """
    slot = dict(slot or {})
    asset_id = slot.get("id") or "asset"

    # 1. Library lookup.
    hit = pick_from_library(slot)
    if hit:
        try:
            from assets import copy_to_workspace
            entry = copy_to_workspace(hit["id"], workspace_dir)
            if entry:
                # The runtime uses the agent's chosen `id` so its level/
                # gameplay code stays stable; the library_id records the
                # original library entry for traceability.
                entry["id"] = asset_id
                return entry
        except Exception as exc:
            # Library copy failed — fall through to procedural.
            pass

    # 2. Procedural fallback.
    return _procedural_manifest_entry(asset_id, {
        "kind": slot.get("fallback_kind", "cube"),
        "color": slot.get("fallback_color", "#aaaaaa"),
        "metallic": slot.get("fallback_metallic", 0),
        "roughness": slot.get("fallback_roughness", 0.6),
        "size": slot.get("fallback_size", 1.0),
    })


async def resolve_slots(workspace_dir: str, slots: list[dict]) -> dict[str, Any]:
    """
    Resolve a batch of slot specs concurrently. Returns
    {asset_id: manifest_entry}. The Asset Lead calls this once with the
    full list per its system prompt.
    """
    coros = [request_slot(workspace_dir, slot) for slot in slots if slot.get("id")]
    if not coros:
        return {}
    results = await asyncio.gather(*coros, return_exceptions=True)
    out: dict[str, Any] = {}
    for slot, res in zip(slots, results):
        if isinstance(res, Exception):
            out[slot["id"]] = _procedural_manifest_entry(slot["id"], {
                "kind": slot.get("fallback_kind", "cube"),
                "color": slot.get("fallback_color", "#aaaaaa"),
            })
            out[slot["id"]]["error"] = str(res)[:200]
        else:
            out[slot["id"]] = res
    return out


async def request_assets(workspace_dir: str, requests: list[dict]) -> dict[str, Any]:
    """
    Build a batch of assets concurrently. `requests` is a list of
    {id, kind, color, metallic, roughness, size, ...}.
    Returns {asset_id: manifest_entry}.
    """
    coros = [
        request_asset(workspace_dir, r["id"], r)
        for r in requests
        if r.get("id")
    ]
    results = await asyncio.gather(*coros, return_exceptions=True)
    manifest: dict[str, Any] = {}
    for r, res in zip(requests, results):
        if isinstance(res, Exception):
            manifest[r["id"]] = _procedural_manifest_entry(r["id"], r)
            manifest[r["id"]]["error"] = str(res)[:200]
        else:
            manifest[r["id"]] = res
    return manifest


def write_manifest(workspace_dir: str, manifest: dict) -> str:
    """Write asset-manifest.json into docs/ (for agents) and game/public/ (for runtime)."""
    docs_path = Path(workspace_dir) / "docs" / "asset-manifest.json"
    runtime_path = Path(workspace_dir) / "game" / "public" / "asset-manifest.json"
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2)
    docs_path.write_text(payload, encoding="utf-8")
    runtime_path.write_text(payload, encoding="utf-8")
    return str(docs_path)
