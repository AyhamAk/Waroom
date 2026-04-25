"""
Renderer 3D — Sets up the final render, exports a frame sequence, then
encodes an MP4 via ffmpeg.

Emits:
  "render-progress" — periodic updates during frame render
  "video-ready"     — when output.mp4 is complete
"""
import time
from pathlib import Path
from typing import Callable

from agents.base import RUN_COMMAND_TOOL, run_agent_with_tools
from agents.blender_artist import BLENDER_EXECUTE_TOOL
from graph.blender_state import BlenderState
from tools.blender_tool import execute_blender_async
from tools.code_runner import run_command
from tools.file_ops import read_file

_RENDERER_SYSTEM = """You are a Blender render pipeline engineer. Render the animation using
Blender's built-in FFmpeg video encoder — NO external ffmpeg needed.

CRITICAL RULES:
- DO NOT change render engine, resolution, or samples — the artist already set quality settings.
- ONLY set output path and file format, then render.
- Use MPEG4 codec (NOT H264) — H264 from Blender is often unplayable on Windows Media Player.

STEP 1 — Set output to MP4 via Blender's built-in encoder:
import bpy, os

scene = bpy.context.scene
output_path = r'OUTPUT_PATH_PLACEHOLDER'
os.makedirs(os.path.dirname(output_path), exist_ok=True)

scene.render.filepath = output_path
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'MPEG4'
scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
scene.render.ffmpeg.audio_codec = 'NONE'
scene.render.ffmpeg.video_bitrate = 8000

print("OUTPUT_CONFIGURED:", output_path)
print("Engine:", scene.render.engine)
print("Resolution:", scene.render.resolution_x, "x", scene.render.resolution_y)

STEP 2 — Render animation:
import bpy
bpy.ops.render.render(animation=True)
print("RENDER_ANIMATION_COMPLETE")

That's it. Two blender_execute calls. DO NOT use run_command for encoding.
After RENDER_ANIMATION_COMPLETE, you are done."""


async def renderer_3d_node(state: BlenderState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("blender_session", {})
    workspace = state["workspace_dir"]

    frames_dir = Path(workspace) / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    output_mp4 = Path(workspace) / "output.mp4"

    await emit("agent-status", {"agentId": "renderer-3d", "status": "working"})
    await _push_sys(emit, "Renderer 3D — starting final render")

    # Emit progress immediately so UI shows activity
    await emit("render-progress", {"phase": "setup", "message": "Configuring render settings"})

    user_msg = f"""WORKSPACE: {workspace}
FRAMES_DIR: {str(frames_dir)}
OUTPUT_MP4: {str(output_mp4)}

Configure Blender render settings and render all 120 frames to {str(frames_dir)}.
Then encode to {str(output_mp4)} using ffmpeg.

In the blender_execute render setup code, replace 'FRAMES_DIR_PLACEHOLDER' with:
{str(frames_dir).replace(chr(92), chr(92)+chr(92))}

Steps:
1. blender_execute: set render settings + output path to frames dir
2. blender_execute: bpy.ops.render.render(animation=True) — this will take a while
3. run_command: ffmpeg to encode frames → output.mp4
4. run_command: verify output.mp4 exists (dir output.mp4)"""

    video_path: list[str | None] = [None]
    render_error: list[str | None] = [None]

    async def tool_executor(name: str, inputs: dict):
        if name == "blender_execute":
            code = inputs["code"]
            await emit("render-progress", {
                "phase": "rendering",
                "message": "Blender rendering frames...",
            })
            # Animation render can take many minutes — use long timeout
            result = await execute_blender_async(code, timeout=600)
            if result.get("status") == "error":
                render_error[0] = result.get("message", "unknown")
                return f"BLENDER_ERROR: {result.get('message', 'unknown')}"
            output = result.get("result", "")
            if "RENDER_ANIMATION_COMPLETE" in output:
                await emit("render-progress", {
                    "phase": "encoding",
                    "message": "Render complete — finalizing video",
                })
                import asyncio
                await asyncio.sleep(2)
                if output_mp4.exists() and output_mp4.stat().st_size > 1000:
                    mp4_path = str(output_mp4)
                    video_path[0] = mp4_path
                    if session:
                        session["video_path"] = mp4_path
                    rel_url = f"/api/blender/video/{state['session_id']}"
                    await emit("video-ready", {
                        "path": mp4_path,
                        "url": rel_url,
                        "session_id": state["session_id"],
                        "size_bytes": output_mp4.stat().st_size,
                    })
                    await _push_sys(emit, f"Video ready: {mp4_path}")
            elif "OUTPUT_CONFIGURED" in output:
                await emit("render-progress", {
                    "phase": "rendering",
                    "message": "Settings configured — starting render",
                })
            return f"OK: {output[:500]}"

        if name == "run_command":
            command = inputs["command"]
            timeout = min(int(inputs.get("timeout", 120)), 600)
            result = await run_command(workspace, command, timeout=timeout)

            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            returncode = result.get("returncode", -1)

            # Detect successful ffmpeg completion
            if "ffmpeg" in command and returncode == 0:
                mp4_path = str(output_mp4)
                if output_mp4.exists() and output_mp4.stat().st_size > 1000:
                    video_path[0] = mp4_path
                    if session:
                        session["video_path"] = mp4_path
                    rel_url = f"/api/blender/video/{state['session_id']}"
                    await emit("video-ready", {
                        "path": mp4_path,
                        "url": rel_url,
                        "session_id": state["session_id"],
                        "size_bytes": output_mp4.stat().st_size,
                    })
                    await _push_sys(emit, f"Video ready: {mp4_path}")

            summary_parts = []
            if stdout:
                summary_parts.append(f"STDOUT:\n{stdout[:2000]}")
            if stderr and stderr.strip():
                summary_parts.append(f"STDERR:\n{stderr[:1000]}")
            summary_parts.append(f"Exit code: {returncode}")
            return "\n".join(summary_parts) or "Command completed"

        if name == "read_file":
            return read_file(workspace, inputs["path"])

        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_RENDERER_SYSTEM,
        user_message=user_msg,
        tools=[BLENDER_EXECUTE_TOOL, RUN_COMMAND_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="renderer-3d",
        api_key=state["api_key"],
        max_tokens=4096,
        max_iterations=8,
        session=session,
    )

    tokens = session.get("tokens", 0) if session else 0
    final_video = video_path[0]

    if session:
        session["video_path"] = final_video

    await emit("agent-status", {"agentId": "renderer-3d", "status": "idle"})
    if final_video:
        await _push_sys(emit, f"Renderer 3D done — video saved to {final_video}")
    else:
        await _push_sys(emit, "Renderer 3D done — check logs for render status")

    return {
        "video_path": final_video,
        "total_tokens": tokens,
    }


async def _push_sys(emit: Callable, message: str):
    await emit("new-message", {
        "from": "system",
        "to": None,
        "type": "system",
        "message": message,
        "id": int(time.time() * 1000),
        "timestamp": int(time.time() * 1000),
    })
