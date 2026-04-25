"""
Blender socket client — communicates with the ahujasid/blender-mcp addon
running inside Blender on localhost:9876.

Protocol (newline-delimited JSON):
    Request:  {"type": "execute_code", "params": {"code": "<python>"}}\n
    Success:  {"status": "success", "result": {"executed": true, "result": "<stdout>"}}
    Error:    {"status": "error", "message": "<reason>"}

We unwrap the nested success result so callers see `result.get('result')` → stdout.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import socket
from typing import Optional

BLENDER_HOST = os.environ.get("BLENDER_HOST", "localhost")
BLENDER_PORT = int(os.environ.get("BLENDER_PORT", "9876"))


def execute_blender(code: str, timeout: int = 30) -> dict:
    """Send Python code to Blender via TCP socket. Returns a dict with
    `status` ('success' | 'error'), plus `result` (stdout) or `message` (error)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((BLENDER_HOST, BLENDER_PORT))
            msg = json.dumps({"type": "execute_code", "params": {"code": code}})
            s.sendall((msg + "\n").encode("utf-8"))
            data = b""
            while True:
                try:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                    # Stop as soon as we have a complete JSON object
                    try:
                        json.loads(data.decode("utf-8").strip())
                        break
                    except json.JSONDecodeError:
                        continue
                except socket.timeout:
                    break
            if not data:
                return {"status": "error", "message": "No response from Blender socket"}
            parsed = json.loads(data.decode("utf-8").strip())
            # Unwrap nested success result: {"status":"success","result":{"executed":true,"result":"..."}}
            if parsed.get("status") == "success" and isinstance(parsed.get("result"), dict):
                parsed["result"] = parsed["result"].get("result", "")
            return parsed
    except ConnectionRefusedError:
        return {
            "status": "error",
            "message": (
                f"Blender not reachable on {BLENDER_HOST}:{BLENDER_PORT}. "
                "Open Blender → N-panel → MCP tab → Start Server."
            ),
        }
    except json.JSONDecodeError as exc:
        return {"status": "error", "message": f"JSON parse error: {exc}"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def execute_blender_async(code: str, timeout: int = 30) -> dict:
    """Async wrapper — runs the blocking socket call in a thread executor so the
    event loop stays free for SSE streaming and cancellation."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: execute_blender(code, timeout))


def save_viewport_render(output_path: str) -> dict:
    """
    Trigger a fast EEVEE still render to the given path. Uses a temp_override
    context for bpy.ops.render.render so it works even when the socket handler
    runs without an active viewport area.
    """
    safe_path = output_path.replace("\\", "\\\\")
    code = f"""
import bpy, os, math

scene = bpy.context.scene
os.makedirs(os.path.dirname(r'{safe_path}'), exist_ok=True)

# Ensure an active camera exists
if not scene.camera:
    cam_data = bpy.data.cameras.new(name='_PreviewCam')
    cam_obj = bpy.data.objects.new(name='_PreviewCam', object_data=cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.location = (7.36, -6.93, 4.96)
    cam_obj.rotation_euler = (math.radians(63.6), 0, math.radians(46.7))
    scene.camera = cam_obj

scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_x = 960
scene.render.resolution_y = 540
scene.render.filepath = r'{safe_path}'

# render.render() is one of the few bpy.ops we truly need. Wrap in a context
# override so it doesn't choke on the missing UI area in socket-handler context.
try:
    window = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
    if window:
        with bpy.context.temp_override(window=window):
            bpy.ops.render.render(write_still=True)
    else:
        bpy.ops.render.render(write_still=True)
    print("RENDER_OK:" + r'{safe_path}')
except Exception as exc:
    print("RENDER_ERROR:", exc)
"""
    return execute_blender(code, timeout=120)


def encode_preview_as_b64(path: str, max_width: int = 480) -> Optional[tuple[str, str]]:
    """
    Load a preview PNG, resize to max_width (token savings), return (base64, mime).
    Returns None if file missing or encoding fails.
    """
    if not path or not os.path.isfile(path):
        return None
    try:
        from PIL import Image
        img = Image.open(path)
        if img.width > max_width:
            ratio = max_width / img.width
            new_h = int(img.height * ratio)
            img = img.resize((max_width, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        data = base64.b64encode(buf.getvalue()).decode("ascii")
        return data, "image/png"
    except ImportError:
        # Pillow not available — encode the raw file
        try:
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            return data, "image/png"
        except Exception:
            return None
    except Exception:
        return None


def get_scene_info() -> dict:
    """Quick scene summary — used for debugging."""
    code = """
import bpy, json
info = {
    "objects": [o.name for o in bpy.data.objects],
    "materials": [m.name for m in bpy.data.materials],
    "cameras": [o.name for o in bpy.data.objects if o.type == 'CAMERA'],
    "lights": [o.name for o in bpy.data.objects if o.type == 'LIGHT'],
    "frame_range": (bpy.context.scene.frame_start, bpy.context.scene.frame_end),
    "render_engine": bpy.context.scene.render.engine,
    "active_camera": bpy.context.scene.camera.name if bpy.context.scene.camera else None,
}
print(json.dumps(info))
"""
    return execute_blender(code, timeout=10)


def ping() -> bool:
    """Lightweight reachability probe — returns True if the socket accepts connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.5)
            s.connect((BLENDER_HOST, BLENDER_PORT))
        return True
    except OSError:
        return False
