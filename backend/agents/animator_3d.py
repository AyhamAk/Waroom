"""
Animator 3D — Adds cinematic keyframe animation to the existing Blender scene
using the bpy_runtime helpers.

Reads: docs/scene-plan.json (for the animation config that the architect specified)
Executes: br.camera_orbit / br.float_animation / br.scale_in_reveal / br.set_bezier_all

Note: the scene spec's animation block is already executed by Artist when it
calls build_scene_from_spec. This agent exists to tune animation per-style or
add hero accents the architect didn't pre-specify.
"""
import json
import time
from typing import Callable

from agents.base import READ_FILE_TOOL, run_agent_with_tools
from agents.blender_artist import BLENDER_EXECUTE_TOOL
from graph.blender_state import BlenderState
from tools.blender_tool import execute_blender_async
from tools.bpy_runtime import get_runtime_source, install_marker_code
from tools.file_ops import read_file

_ANIMATOR_SYSTEM = """You are a cinematic motion designer. You polish and verify animation in an
existing Blender scene using the bpy_runtime library (namespace `br`, preloaded).

═════════ YOUR JOB ═════════

The Artist already ran br.build_scene_from_spec(spec) which may have applied
camera_orbit / product_float / scale_in_reveal per the scene-plan. Your job:

1. blender_execute: verify keyframes exist, add style-specific polish.
2. Call br.set_bezier_all() at the end so every fcurve has smooth easing.
3. Done — do not render here (Renderer handles that).

One or two blender_execute calls total.

═════════ br ANIMATION API ═════════

  br.camera_orbit(cam_name='Camera', radius=8, height=4,
                  start_deg=-90, end_deg=90, frames=120, target=(0,0,0))
  br.float_animation(obj_name, amplitude=0.15, frames=120, cycles=1.0)
  br.scale_in_reveal(obj_name, start_frame=1, end_frame=20, target_scale=None)
  br.set_bezier_all()
  br.scene_summary()   # inspect: objects, camera, lights, frame_range

═════════ STYLE PRESETS ═════════

commercial: orbit 180°, subtle float ±0.05, scale-in 1-20
cinematic:  slow orbit 120°, no float, dramatic scale-in 1-25
luxury:     barely-there orbit 60°, NO float, hold still
scifi:      rapid orbit starting fast ending slow 270°, float ±0.2

═════════ RULES ═════════

- NEVER reset the scene. You are adding TO an existing scene.
- Look at br.scene_summary() to find the hero object name if unknown.
- Always finish with br.set_bezier_all() for premium easing."""


async def animator_3d_node(state: BlenderState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("blender_session", {})
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "animator-3d", "status": "working"})
    await _push_sys(emit, "Animator 3D — polishing keyframes")

    # Ensure runtime still loaded and current (cheap no-op if it is)
    marker = await execute_blender_async(install_marker_code(), timeout=10)
    marker_out = marker.get("result") or ""
    if "RUNTIME_MISSING" in marker_out or "RUNTIME_OUTDATED" in marker_out:
        await execute_blender_async(get_runtime_source(), timeout=30)

    scene_plan = read_file(workspace, "docs/scene-plan.json")
    try:
        spec = json.loads(scene_plan) if scene_plan else {}
    except Exception:
        spec = {}
    anim = spec.get("animation") or {}
    style = state.get("style", "commercial")
    product_desc = state["product_description"]

    user_msg = f"""PRODUCT: {product_desc}
STYLE: {style}

SCENE-PLAN ANIMATION BLOCK (already executed by Artist):
{json.dumps(anim, indent=2) if anim else '(none specified — start fresh)'}

Verify/polish the animation. Run one or two blender_execute calls.
Always finish with br.set_bezier_all()."""

    async def tool_executor(name: str, inputs: dict):
        if name == "blender_execute":
            code = inputs["code"]
            result = await execute_blender_async(code, timeout=45)
            if result.get("status") == "error":
                return f"BLENDER_ERROR: {result.get('message', 'unknown')}"
            return f"OK: {result.get('result', '')[:800]}"

        if name == "read_file":
            return read_file(workspace, inputs["path"])

        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_ANIMATOR_SYSTEM,
        user_message=user_msg,
        tools=[BLENDER_EXECUTE_TOOL, READ_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="animator-3d",
        api_key=state["api_key"],
        max_tokens=4096,
        max_iterations=4,
        session=session,
        cache_system=True,
    )

    tokens = session.get("tokens", 0) if session else 0
    await emit("agent-status", {"agentId": "animator-3d", "status": "idle"})
    await _push_sys(emit, "Animator 3D done — keyframes polished")

    return {"total_tokens": tokens}


async def _push_sys(emit: Callable, message: str):
    await emit("new-message", {
        "from": "system",
        "to": None,
        "type": "system",
        "message": message,
        "id": int(time.time() * 1000),
        "timestamp": int(time.time() * 1000),
    })
