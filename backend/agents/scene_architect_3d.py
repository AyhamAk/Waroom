"""
Scene Architect 3D — Converts the director's creative brief into a compact JSON
spec (ACP/scene-plan.json) that Blender Artist can execute mechanically via
bpy_runtime.build_scene_from_spec.

Reads:  docs/scene-concept.md
Writes: docs/scene-plan.json
"""
import json
import time
from typing import Callable

from agents.base import READ_FILE_TOOL, WRITE_FILE_TOOL, run_agent_with_tools
from graph.blender_state import BlenderState
from tools.file_ops import read_file, write_file

# The Architect outputs ONE file: scene-plan.json. No markdown. No freeform prose.
# Every field maps 1:1 to bpy_runtime.build_scene_from_spec().
_ARCHITECT_SYSTEM = """You are a Blender Technical Director. You translate a creative brief into
a COMPACT JSON scene specification that is executed mechanically by bpy_runtime.

═══════════════════════════════════════════════
YOUR ONLY OUTPUT: docs/scene-plan.json
═══════════════════════════════════════════════

The runtime library exposes material presets, HDRI registry, style scaffolds,
and a build_scene_from_spec() function. Your JSON is the input to that function.
DO NOT write bpy code. DO NOT write markdown. DO NOT repeat the brief.

═══════════════════════════════════════════════
SCHEMA
═══════════════════════════════════════════════
{
  "style": "commercial" | "cinematic" | "luxury" | "scifi" | "minimal",
  "scaffold": true,                          // apply_style() scaffold; default true
  "render": {
    "engine": "EEVEE_NEXT" | "CYCLES",       // default EEVEE_NEXT for 120-frame animation
    "samples": 64,
    "resolution": [1280, 720],
    "fps": 24,
    "frames": 120
  },
  "filmic": {"look": "High Contrast", "exposure": 0.0},
  "world": {
    "hdri_slug":    "<polyhaven_slug>",      // OPTIONAL — overrides style default
    "hdri_style":   "commercial|cinematic|scifi|luxury|outdoor|night",
    "hdri_resolution": "1k|2k|4k",           // default 2k
    "color":        "#hex",                  // OPTIONAL if no hdri
    "strength":     1.0
  },
  "materials": [
    // Option A (preferred when matches) — preset-based:
    {"id": "hero_mat", "preset": "brushed_aluminum"},
    // Option B — custom PBR:
    {"id": "backdrop_mat", "base_color": "#f5f2ee", "roughness": 0.85, "metallic": 0.0}
  ],
  "objects": [
    {
      "id":         "product_body",           // name used by lights/camera/animation
      "primitive":  "CUBE|CYLINDER|UV_SPHERE|PLANE|CONE|TORUS|ICO_SPHERE|MONKEY|EMPTY",
      "location":   [0.0, 0.0, 0.0],          // metres
      "scale":      [1.0, 1.0, 1.0],
      "rotation_euler": [0.0, 0.0, 0.0],      // radians
      "material":   "hero_mat",               // id from materials[] or a preset name
      "subdivision": 2,                        // SubSurf viewport level (0 = off)
      "shade_smooth": true,
      "bevel": {"width": 0.02, "segments": 3} // OPTIONAL, adds BEVEL modifier
    }
  ],
  "lights": [
    // OPTIONAL — style scaffolds add their own. Only add here for hero/custom lights.
    {"id":"HeroRim", "type":"AREA", "location":[2.5,3.0,4.0], "rotation_euler":[1.0,0,2.5],
     "energy": 400, "color":"#ffe0a0", "size": 1.2}
  ],
  "camera": {
    "location":     [4.5, -7.0, 2.5],
    "look_at":      [0, 0, 0.5],
    "focal_mm":     50,
    "dof_distance": 7.5,
    "fstop":        2.8,
    "dutch_deg":    0.0,
    "track":        "product_body"            // OPTIONAL — TRACK_TO constraint
  },
  "animation": {
    "camera_orbit": {"radius": 8.0, "height": 4.0, "start_deg": -90, "end_deg": 90, "frames": 120},
    "product_float": {"obj": "product_body", "amplitude": 0.15, "frames": 120},
    "scale_in_reveal": {"obj": "product_body", "start_frame": 1, "end_frame": 20},
    "bezier_all": true
  },
  "compositor": {
    "preset": "cinematic",                   // commercial|cinematic|luxury|scifi|minimal
    "glow": true,
    "vignette": 0.3
  }
}

═══════════════════════════════════════════════
MATERIAL PRESETS (use these when possible — hand-tuned PBR)
═══════════════════════════════════════════════
Metals:    brushed_aluminum, chrome, polished_steel, brushed_steel, gold,
           brushed_gold, rose_gold, copper, bronze, titanium, black_anodized
Plastics:  plastic_glossy_black, plastic_matte_black, plastic_white_glossy,
           plastic_white_matte, abs_grey
Glass:     glass_clear, glass_frosted, glass_tinted_black, glass_tinted_blue, crystal
Stone:     ceramic_white, porcelain, concrete_smooth, concrete_polished,
           marble_white, marble_black
Fabric:    velvet_red, velvet_black, velvet_blue, suede_tan, leather_black,
           leather_brown, leather_tan, denim, cotton_white
Wood:      walnut_wood, oak_light, oak_dark, maple, ebony
Emissive:  neon_cyan, neon_magenta, neon_amber, holographic_blue
Car paint: car_paint_red, car_paint_black, car_paint_white, car_paint_silver
Rubber:    rubber_matte

═══════════════════════════════════════════════
HDRI REGISTRY (Poly Haven — free, CC0)
═══════════════════════════════════════════════
commercial: studio_small_08, studio_small_09, studio_small_03
cinematic:  industrial_sunset_02_puresky, rainforest_trail, moonless_golf
luxury:     studio_small_03, studio_small_04, brown_photostudio_01
scifi:      kloofendal_48d_partly_cloudy, satara_night, dikhololo_night

═══════════════════════════════════════════════
AUTHORING RULES
═══════════════════════════════════════════════
1. Use "scaffold": true + a style — that gets you free floor, 3-point lights,
   camera, world, compositor. Only add lights[] / camera{} overrides if the
   creative brief demands something specific.
2. Every dimension in metres. Product is centered at (0,0,0) unless the style
   says otherwise (scifi platform → product at (0,0,0.15)).
3. Prefer material presets over custom PBR — they are hand-tuned.
4. Keep arrays short. Three well-placed props beat ten random objects.
5. Output ONLY valid JSON. No comments, no trailing commas, no markdown fences.

Write your JSON spec using the write_file tool with path="docs/scene-plan.json"."""


async def scene_architect_3d_node(state: BlenderState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("blender_session", {})
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "scene-architect-3d", "status": "working"})
    await _push_sys(emit, "Scene Architect 3D — writing scene-plan.json")

    concept = read_file(workspace, "docs/scene-concept.md")
    style = state.get("style", "commercial")

    user_msg = f"""DIRECTOR'S CREATIVE BRIEF:
{concept}

PRODUCT: {state['product_description']}
STYLE: {style}

Translate the brief into a SINGLE valid JSON scene spec.
Follow the schema in your system prompt EXACTLY.
Write it to docs/scene-plan.json with the write_file tool.

Start from style="{style}" and scaffold=true — the runtime gives you a free
lighting/camera/floor/compositor scaffold for that style. Only override if the
brief demands something specific (e.g. "product on a mirror" → override camera
or add a prop, not a whole new light rig).

Output nothing else. Just the JSON file."""

    scene_plan_json = ""

    async def tool_executor(name: str, inputs: dict):
        nonlocal scene_plan_json
        if name == "read_file":
            return read_file(workspace, inputs["path"])
        if name == "write_file":
            path = inputs["path"]
            content = inputs["content"]
            # Validate JSON before accepting
            if path.endswith(".json"):
                try:
                    parsed = json.loads(content)
                    # Re-serialize to guarantee clean JSON on disk
                    content = json.dumps(parsed, indent=2)
                except json.JSONDecodeError as exc:
                    return f"JSON_ERROR: {exc}. Retry with valid JSON — no trailing commas, no comments, use double quotes."
            result = write_file(workspace, path, content)
            if result.get("ok") and path == "docs/scene-plan.json":
                scene_plan_json = content
            return str(result)
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_ARCHITECT_SYSTEM,
        user_message=user_msg,
        tools=[READ_FILE_TOOL, WRITE_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="scene-architect-3d",
        api_key=state["api_key"],
        max_tokens=4096,
        max_iterations=4,
        session=session,
        stop_after_write=["docs/scene-plan.json"],
    )

    if not scene_plan_json:
        scene_plan_json = read_file(workspace, "docs/scene-plan.json")

    tokens = session.get("tokens", 0) if session else 0
    await emit("agent-status", {"agentId": "scene-architect-3d", "status": "idle"})
    await _push_sys(emit, "Scene Architect 3D done — scene-plan.json ready")

    return {"scene_plan": scene_plan_json, "total_tokens": tokens}


async def _push_sys(emit: Callable, message: str):
    await emit("new-message", {
        "from": "system",
        "to": None,
        "type": "system",
        "message": message,
        "id": int(time.time() * 1000),
        "timestamp": int(time.time() * 1000),
    })
