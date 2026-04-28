"""
Tech-Art — picks lighting + post-fx + material presets. Pure JSON output.

The Engine Engineer already wrote engine-config.json with one slot per
preset. Tech-Art writes a fuller materials.json that the gameplay
programmer reads when materialising props from the asset manifest.
"""
import json
import time
from typing import Callable

from agents.base import READ_FILE_TOOL, WRITE_FILE_TOOL, run_agent_with_tools
from graph.game_state import GameState
from tools.file_ops import read_file, write_file


_TECH_ART_SYSTEM = """You are a Tech-Artist. You write ONE file:
docs/materials.json. The engine has a full cinematic stack — HDRI lighting,
CSM cascaded shadows, SSAO, bokeh DOF, bloom, film grain, chromatic
aberration, vignette, optional procedural sky shader. Pick the presets and
materials that make the genre look its best.

Schema (top-level fields are REQUIRED):

{
  "lighting": {
    "preset":   "warm_outdoor_skybox | golden_hour_outdoor | moody_industrial | stylized_topdown_punch | neon_night | studio_neutral",
    "use_csm":   true,                  // cascaded shadows — true for outdoor / large levels
    "csm_cascades": 3,                  // 2-4
    "csm_max_far":  100,
    "csm_shadow_size": 2048,            // 1024 (perf) | 2048 (default) | 4096 (quality)
    "exposure_override": null           // optional — null lets the preset decide
  },
  "post_fx": {
    "preset":     "vibrant_action | cinematic_grit | filmic_soft | filmic_dreamy | warm_outdoor_skybox | moody_industrial | stylized_topdown_punch | neon_night | retro_film | standard | minimal",
    "bloom_strength_override":   null,
    "vignette_amount_override":  null,
    "ca_override":               null,
    "grain_override":            null,
    "dof_focus_override":        null,
    "quality":                   "high"  // high | medium | low
  },
  "materials": {
    "<asset_id>": {
      "base_color":         "#hex",
      "metallic":            0.0,
      "roughness":           0.6,
      "emissive":           "#000000",
      "emissive_strength":   0.0,
      "normal_scale":        1.0
    }
  },
  "block_materials": {
    "floor":  { "base_color":"#hex", "metallic":0,    "roughness":0.95 },
    "wall":   { "base_color":"#hex", "metallic":0,    "roughness":0.85 },
    "crate":  { "base_color":"#hex", "metallic":0.1,  "roughness":0.7 },
    "hazard": { "base_color":"#ff3344", "metallic":0, "roughness":0.6, "emissive":"#ff3344", "emissive_strength":0.6 }
  }
}

═════════ HOW TO PICK ═════════

Outdoor / large levels  → use_csm: true, lighting=warm_outdoor_skybox or golden_hour_outdoor.
Indoor / industrial     → use_csm: false, lighting=moody_industrial, post_fx=cinematic_grit.
Top-down arcade         → use_csm: false, lighting=stylized_topdown_punch, post_fx=stylized_topdown_punch.
Cyberpunk / neon        → lighting=neon_night, post_fx=neon_night (high bloom).
Retro / arcade          → post_fx=retro_film (heavy grain + scanlines).

═════════ STRICT WORKFLOW ═════════

1. Read docs/asset-manifest.json — every key needs a materials.<id> entry.
2. Read docs/levels/level_01.json — every block.material seen needs a
   block_materials entry.
3. Pick presets that match the recipe + design.
4. Set use_csm based on level size (true if XZ > 30m).
5. Write docs/materials.json. Stop.

═════════ HARD RULES ═════════

- Valid JSON. No comments, no trailing commas.
- Preset names MUST come from the enums above — never invent new ones.
- Cohesive palette: max 6 distinct hues across all materials.
- Hazards always emissive red/orange/yellow so they read at distance.
- Keep _override fields null unless you have a strong reason — presets are tuned.
- One write_file call. Then stop."""


async def tech_art_node(state: GameState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("game_session", {})
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "tech-art", "status": "thinking"})
    await _push(emit, "🎨 Tech-Art — picking presets + material palette")

    manifest = read_file(workspace, "docs/asset-manifest.json") or "{}"
    level = read_file(workspace, "docs/levels/level_01.json") or "{}"
    engine_cfg = read_file(workspace, "docs/engine-config.json") or "{}"

    user_msg = f"""GENRE: {state.get('genre', 'auto')}
RECIPE: {state.get('recipe_name')}

ASSET MANIFEST KEYS:
{json.dumps(list(json.loads(manifest).keys()) if manifest.strip() else [], indent=2)}

LEVEL (excerpt):
{level[:1200]}

ENGINE CONFIG (presets already chosen):
{engine_cfg[:1200]}

Write docs/materials.json that covers every asset id and every block
material. Keep the palette tight."""

    async def tool_executor(name: str, inputs: dict):
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
                await _emit_file(emit, session, path, content, "tech-art")
                # Mirror materials.json into game/public/ so the runtime
                # can fetch '/materials.json' alongside the asset manifest.
                if path == "docs/materials.json":
                    try:
                        write_file(workspace, "game/public/materials.json", content)
                    except Exception:
                        pass
            return json.dumps(result)
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_TECH_ART_SYSTEM,
        user_message=user_msg,
        tools=[READ_FILE_TOOL, WRITE_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="tech-art",
        api_key=state["api_key"],
        max_tokens=4000,
        max_iterations=3,
        session=session,
        stop_after_write=["docs/materials.json"],
        cache_system=True,
    )

    cfg = read_file(workspace, "docs/materials.json")
    await emit("agent-status", {"agentId": "tech-art", "status": "idle"})
    await _push(emit, "🎨 Tech-Art done")
    return {
        "materials_config": cfg,
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
