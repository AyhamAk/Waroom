"""
Asset Lead — translates the level + GDD into a typed asset request list,
then dispatches to the asset bridge (Blender → glTF, with procedural
fallback for primitives). Writes docs/asset-manifest.json.

Like Blender QA, the agent emits ONLY typed ops — never raw Python — and
the bridge is the single safe entry point.
"""
import json
import time
from pathlib import Path
from typing import Callable

from agents.base import READ_FILE_TOOL, WRITE_FILE_TOOL, run_agent_with_tools
from graph.game_state import GameState
from tools.asset_bridge import request_assets, resolve_slots, write_manifest
from tools.file_ops import read_file, write_file

try:
    from assets import library_summary
except ImportError:
    library_summary = lambda: {"asset_count": 0, "types": {}, "top_tags": {}}


PICK_ASSETS_TOOL = {
    "name": "pick_assets",
    "description": (
        "Pick a batch of game assets in ONE call. Each entry is a SLOT — "
        "the bridge first searches the curated CC0 glTF library for a "
        "match by type + tags (+ required animations), copies the .glb "
        "into the workspace, and returns a runtime-ready manifest entry. "
        "If nothing matches, the bridge falls back to a procedural "
        "primitive built from `fallback_*` fields. Call ONCE with the "
        "full list — do NOT loop."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "assets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id":   {"type": "string", "description": "How the runtime refers to this slot — must match the level's asset/material field"},
                        "type": {"type": "string", "enum": [
                            "character_rigged", "enemy_rigged",
                            "weapon_handheld", "prop_static",
                            "environment_tile", "vfx",
                        ]},
                        "tags":   {"type": "array", "items": {"type": "string"}, "description": "Ranking tags — best-effort match"},
                        "anims":  {"type": "array", "items": {"type": "string"}, "description": "Required animation names — entries lacking them are filtered out"},
                        "max_tris": {"type": "integer", "description": "Triangle budget cap"},
                        "fallback_kind":   {"type": "string", "enum": [
                            "cube", "sphere", "cylinder", "cone", "plane",
                            "torus", "capsule", "monkey",
                        ]},
                        "fallback_color":     {"type": "string"},
                        "fallback_metallic":  {"type": "number"},
                        "fallback_roughness": {"type": "number"},
                        "fallback_size":      {"type": "number"},
                    },
                    "required": ["id", "type"],
                },
            },
        },
        "required": ["assets"],
    },
}


_ASSET_LEAD_SYSTEM = """You are the Asset Lead.

You translate the GDD + level into a flat list of asset SLOTS, then call
ONE tool: pick_assets. The bridge first tries to match each slot to a real
glTF in the curated CC0 library; only if nothing matches does it fall back
to a procedural primitive built from your `fallback_*` fields.

═════════ STRICT WORKFLOW ═════════

1. Read docs/levels/level_01.json — collect every distinct asset id
   referenced by props/spawners + every block material.
2. Build a flat slot list. For each id, decide:
     - type:    character_rigged | enemy_rigged | weapon_handheld |
                prop_static | environment_tile | vfx
     - tags:    short list of preferred tags (e.g. "robot", "scifi",
                "humanoid", "metallic"). The library ranks by tag overlap.
     - anims:   REQUIRED animations if rigged (e.g. ["walk","run"]).
                Library entries lacking ALL listed clips get filtered out.
     - max_tris: triangle budget (player <= 6000, enemy <= 4000,
                prop <= 2500, environment_tile <= 1500).
     - fallback_kind / color / metallic / roughness / size — used IF the
                library has no match. Pick a flat colour that reads at distance.
3. ONE call to pick_assets with the full list.
4. ONE call to write_file for docs/asset-manifest.json with the result.
5. Stop.

═════════ LIBRARY HINTS (live — provided in your user message) ═════════

Your user message lists the library's available types + most common tags.
Match your slot tags to those tags so the picker actually finds something.
If the library is empty (asset_count: 0), every slot will fall back to a
primitive — still emit good fallback_* fields so the procedural shapes look
intentional.

═════════ HARD RULES ═════════

- Maximum 25 slots total.
- IDs MUST match the level's `asset:` and `material:` fields exactly.
- For block materials (floor, wall, crate, hazard) → type:
  environment_tile, fallback_kind: cube. The runtime maps these ids to
  textured/coloured cubes.
- Hazard fallback colour is always emissive red/orange/yellow.
- Never call any tool other than pick_assets, read_file, write_file.
- Never invent asset IDs not referenced by the level + GDD.
- One pick_assets call. One write_file call. Then stop."""


async def asset_lead_node(state: GameState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("game_session", {})
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "asset-lead", "status": "working"})
    await _push(emit, "📦 Asset Lead — building asset manifest")

    gdd = read_file(workspace, "docs/game-design.md") or ""
    level = read_file(workspace, "docs/levels/level_01.json") or "{}"

    # Surface live library state to the agent so it picks tags that exist.
    summary = library_summary()
    type_counts = summary.get("types", {})
    top_tags = summary.get("top_tags", {})
    library_hint = (
        f"asset_count: {summary.get('asset_count', 0)}\n"
        f"types_available: {json.dumps(type_counts)}\n"
        f"top_tags: {list(top_tags.keys())[:30]}"
    )

    user_msg = f"""GAME DESIGN DOC (excerpt):
{gdd[:1200]}

LEVEL (level_01.json):
{level[:3000]}

LIBRARY STATE (live snapshot):
{library_hint}

Build the slot list per your system prompt — pick library-friendly tags
where they exist, otherwise fill in good fallback_* fields. Call
pick_assets once with the full list, then write_file
docs/asset-manifest.json with the returned manifest, then stop."""

    asset_results: dict = {}

    async def tool_executor(name: str, inputs: dict):
        nonlocal asset_results
        if name == "read_file":
            return read_file(workspace, inputs["path"])
        if name == "write_file":
            path = inputs["path"]
            content = inputs["content"]
            if path.endswith(".json"):
                try:
                    parsed = json.loads(content)
                    content = json.dumps(parsed, indent=2)
                except json.JSONDecodeError as exc:
                    return json.dumps({"error": f"JSON_PARSE_FAILED: {exc}"})
            result = write_file(workspace, path, content)
            if result.get("ok"):
                await _emit_file(emit, session, path, content, "asset-lead")
            return json.dumps(result)
        if name == "pick_assets":
            slots = inputs.get("assets", []) or []
            await _push(emit, f"📦 Resolving {len(slots)} asset slots (library-first)…")
            asset_results = await resolve_slots(workspace, slots)
            try:
                write_manifest(workspace, asset_results)
            except Exception as exc:
                await _push(emit, f"manifest write warning: {exc}")
            # Compact summary log so the agent sees library-vs-procedural split.
            from_library = sum(1 for v in asset_results.values() if v.get("type") == "gltf")
            from_procedural = len(asset_results) - from_library
            await _push(emit, f"   {from_library} from library, {from_procedural} procedural fallback")
            return json.dumps(asset_results)[:6000]
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_ASSET_LEAD_SYSTEM,
        user_message=user_msg,
        tools=[PICK_ASSETS_TOOL, READ_FILE_TOOL, WRITE_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="asset-lead",
        api_key=state["api_key"],
        max_tokens=4000,
        max_iterations=5,
        session=session,
        stop_after_write=["docs/asset-manifest.json"],
        cache_system=True,
    )

    manifest_text = read_file(workspace, "docs/asset-manifest.json") or json.dumps(asset_results, indent=2)
    await emit("agent-status", {"agentId": "asset-lead", "status": "idle"})
    await _push(emit, f"📦 Asset Lead done — {len(asset_results)} assets")
    return {
        "asset_manifest": manifest_text,
        "total_tokens": session.get("tokens", 0) if session else 0,
    }


async def _push(emit, message):
    await emit("new-message", {
        "from": "system", "to": None, "type": "system",
        "message": message, "id": int(time.time() * 1000), "timestamp": int(time.time() * 1000),
    })


async def _emit_file(emit, session, path, content, agent_id):
    lines = content.count("\n") + 1
    entry = {"path": path, "content": content, "agentId": agent_id,
             "ts": int(time.time() * 1000), "lines": lines}
    if session is not None:
        files = session.get("files", [])
        idx = next((i for i, f in enumerate(files) if f["path"] == path), -1)
        if idx >= 0: files[idx] = entry
        else: files.append(entry)
        session["files"] = files
    await emit("new-file", entry)
