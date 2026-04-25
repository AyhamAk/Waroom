"""
QA 3D — Post-build quality gate.

Takes ONE viewport screenshot. Runs br.qa_checklist() for machine checks.
Scores the scene 1-10 on geometry / materials / lighting / composition. If any
axis < 7, emits a targeted JSON fix request for Artist to execute. Otherwise
advances to Animator.

Writes: docs/qa-report.json (latest scoring + fix requests)
"""
import json
import time
from pathlib import Path
from typing import Callable

from agents.base import READ_FILE_TOOL, WRITE_FILE_TOOL, run_agent_with_tools
from agents.blender_artist import BLENDER_EXECUTE_TOOL, REQUEST_PREVIEW_TOOL
from graph.blender_state import BlenderState
from tools.blender_tool import execute_blender_async, encode_preview_as_b64, save_viewport_render
from tools.bpy_runtime import get_runtime_source, install_marker_code
from tools.file_ops import read_file, write_file

# QA does one visual review + writes a structured JSON verdict. Lean system prompt.
_QA_SYSTEM = """You are a senior 3D quality reviewer. Your job: judge the rendered preview,
score the scene, and emit a SHORT list of typed fixes if anything is off.

═════════ WORKFLOW (strict) ═════════

1. request_preview — render and SEE the scene (one call).
2. blender_execute ONCE to collect machine data:
       import json
       summary = br.scene_summary()
       issues = br.qa_checklist()
       print("SUMMARY:", json.dumps(summary))
       print("ISSUES:", json.dumps(issues))
3. Judge image + machine data. Write docs/qa-report.json (your ONLY output).

Total: 1 request_preview + 1 blender_execute + 1 write_file. Nothing else.

═════════ SCORING RUBRIC (1-10 per axis) ═════════

GEOMETRY     — silhouette clean? Smooth where it should be? Scale real?
MATERIALS    — no default grey? PBR values sensible for each material?
LIGHTING     — 3D shape reads? Rim separation? No pure-black / blown-out?
COMPOSITION  — product dominates frame? DOF sells depth? Focal length right?

APPROVED: all four ≥ 7 AND overall ≥ 7.5.
REVISE:   any axis < 7 → emit typed fixes.

═════════ CRITICAL RULE — TYPED FIXES ONLY ═════════

Fixes MUST use the typed op format below. You CANNOT emit raw Python or bpy
code. The Artist applies fixes via `br.apply_fixes(fixes)` — a safe, bounded
dispatcher that never touches mesh data.

VALID FIX OPS (this is the complete list):

  {"op": "set_light_energy",        "args": {"light": "<name>", "energy": <float>}}
  {"op": "set_light_color",         "args": {"light": "<name>", "color": "#hex"}}
  {"op": "set_light_size",          "args": {"light": "<name>", "size": <float>}}
  {"op": "add_light",               "args": {"name": "<new_name>", "type": "AREA|POINT|SUN|SPOT",
                                              "location": [x,y,z], "rotation": [rx,ry,rz],
                                              "energy": <float>, "color": "#hex", "size": <float>}}
  {"op": "delete_object",           "args": {"name": "<name>"}}

  {"op": "move_camera",             "args": {"location": [x,y,z], "look_at": [x,y,z]}}
  {"op": "set_camera_focal",        "args": {"focal_mm": <float>}}
  {"op": "set_camera_fstop",        "args": {"fstop": <float>}}
  {"op": "set_camera_dof_distance", "args": {"distance": <float>}}
  {"op": "set_active_camera",       "args": {"camera": "<name>"}}

  {"op": "move_object",             "args": {"name": "<name>", "location": [x,y,z]}}
  {"op": "scale_object",            "args": {"name": "<name>", "scale": [x,y,z]}}   # object-level scale only — never bakes mesh
  {"op": "rotate_object",           "args": {"name": "<name>", "rotation": [rx,ry,rz]}}

  {"op": "set_material_param",      "args": {"material": "<name>",
                                              "param": "base_color|metallic|roughness|ior|transmission|emission_color|emission_strength|alpha|sheen|clearcoat|clearcoat_roughness",
                                              "value": <float or "#hex">}}

  {"op": "set_world_strength",      "args": {"strength": <float>}}
  {"op": "set_compositor_preset",   "args": {"preset": "commercial|cinematic|luxury|scifi|minimal"}}
  {"op": "set_render_samples",      "args": {"samples": <int>}}

No other op names are valid. Unknown ops will be rejected.

═════════ OUTPUT — docs/qa-report.json ═════════

{
  "scores": {
    "geometry":    {"score": 8, "notes": "..."},
    "materials":   {"score": 9, "notes": "..."},
    "lighting":    {"score": 6, "notes": "rim too weak; product lacks separation"},
    "composition": {"score": 8, "notes": "..."}
  },
  "overall": 7.75,
  "verdict": "REVISE",
  "fixes": [
    {"op": "set_light_energy", "args": {"light": "RimLight", "energy": 800}},
    {"op": "set_light_color",  "args": {"light": "RimLight", "color": "#ffd4a0"}}
  ]
}

═════════ HARD RULES ═════════

- Maximum 4 fixes per report. Prioritise the lowest-scoring axis.
- If the current pass score is LOWER than a previous pass (score history is in
  your user message), something we already tried made it worse. Suggest fewer,
  SMALLER changes OR set verdict = "APPROVED" to stop the regression.
- Never output `"code"` or `"call"` fields. Only `op` and `args`.
- Never output raw Python. Never reference bpy or br in fix args.
- Valid JSON only — no markdown fences, no prose around the object."""


async def qa_3d_node(state: BlenderState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("blender_session", {})
    workspace = state["workspace_dir"]

    renders_dir = Path(workspace) / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    qa_pass = state.get("qa_pass", 0) + 1
    await emit("agent-status", {"agentId": "qa-3d", "status": "working"})
    await _push_sys(emit, f"QA 3D — pass {qa_pass} quality review")

    # Ensure runtime is loaded and current
    marker = await execute_blender_async(install_marker_code(), timeout=10)
    marker_out = marker.get("result") or ""
    if "RUNTIME_MISSING" in marker_out or "RUNTIME_OUTDATED" in marker_out:
        await execute_blender_async(get_runtime_source(), timeout=30)

    style = state.get("style", "commercial")
    product_desc = state["product_description"]
    concept = read_file(workspace, "docs/scene-concept.md")[:600]
    previous_qa = read_file(workspace, "docs/qa-report.json")
    previous_qa_hint = ""
    if previous_qa and not previous_qa.startswith("(file not found"):
        previous_qa_hint = f"\n\nPREVIOUS QA PASS (for delta comparison):\n{previous_qa[:1200]}"

    # Score history so QA can detect regressions and back off
    history = state.get("qa_score_history") or []
    history_hint = ""
    if history:
        history_hint = (
            f"\n\nSCORE HISTORY (oldest to newest): {[round(s,1) for s in history]}"
            f"\nIf the last score is LOWER than the previous one, your last fixes made"
            f" things worse. Suggest fewer, smaller changes OR approve to stop regression."
        )

    user_msg = f"""PRODUCT: {product_desc}
STYLE: {style}
PASS: {qa_pass}

DIRECTOR'S VISION (for reference):
{concept}
{previous_qa_hint}{history_hint}

Run the QA workflow. Score each axis 1-10, then write docs/qa-report.json.
Fixes MUST use the typed {{op, args}} format from your system prompt.
NEVER emit raw Python or bpy code. NEVER use "code" or "call" fields."""

    latest_render: list[str | None] = [state.get("latest_render_path")]
    qa_json_content = ""

    async def tool_executor(name: str, inputs: dict):
        if name == "blender_execute":
            code = inputs["code"]
            result = await execute_blender_async(code, timeout=45)
            if result.get("status") == "error":
                return f"BLENDER_ERROR: {result.get('message', 'unknown')}"
            return f"OK: {result.get('result', '')[:1500]}"

        if name == "request_preview":
            path = latest_render[0]
            if not path or not Path(path).exists():
                preview_filename = f"qa_preview_{qa_pass:02d}.png"
                path = str(renders_dir / preview_filename)
                rr = save_viewport_render(path)
                if rr.get("status") == "error":
                    return f"PREVIEW_FAILED: {rr.get('message', 'unknown')}"
                latest_render[0] = path
                if session:
                    session["latest_render"] = path
                rel_url = f"/api/blender/render/{state['session_id']}/{Path(path).name}"
                await emit("blender-frame", {
                    "path": path, "url": rel_url,
                    "frame": qa_pass, "session_id": state["session_id"],
                })
            encoded = encode_preview_as_b64(path)
            if not encoded:
                return f"PREVIEW_ENCODE_FAILED at {path}"
            b64, media = encoded
            return [
                {"type": "text", "text": f"QA pass {qa_pass} preview. Judge quality of geometry, materials, lighting, composition."},
                {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
            ]

        if name == "read_file":
            return read_file(workspace, inputs["path"])

        if name == "write_file":
            nonlocal qa_json_content
            path = inputs["path"]
            content = inputs["content"]
            if path.endswith(".json"):
                try:
                    parsed = json.loads(content)
                    content = json.dumps(parsed, indent=2)
                except json.JSONDecodeError as exc:
                    return f"JSON_ERROR: {exc}. Retry with valid JSON."
            result = write_file(workspace, path, content)
            if path == "docs/qa-report.json" and result.get("ok"):
                qa_json_content = content
            return str(result)

        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_QA_SYSTEM,
        user_message=user_msg,
        tools=[BLENDER_EXECUTE_TOOL, REQUEST_PREVIEW_TOOL, READ_FILE_TOOL, WRITE_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="qa-3d",
        api_key=state["api_key"],
        max_tokens=4096,
        max_iterations=5,
        session=session,
        stop_after_write=["docs/qa-report.json"],
        cache_system=True,
    )

    # Parse verdict for routing
    verdict = "REVISE"
    overall = 0.0
    fixes: list = []
    if not qa_json_content:
        qa_json_content = read_file(workspace, "docs/qa-report.json")
    try:
        qa_data = json.loads(qa_json_content)
        verdict = qa_data.get("verdict", "REVISE").upper()
        overall = float(qa_data.get("overall", 0))
        fixes = qa_data.get("fixes", [])
    except Exception:
        pass

    # Safety valve — after 3 passes, force approval to prevent infinite loop
    MAX_QA_PASSES = 3
    if qa_pass >= MAX_QA_PASSES and verdict != "APPROVED":
        await _push_sys(emit, f"QA pass {qa_pass} — force-advancing (max reached, score {overall:.1f})")
        verdict = "APPROVED"

    tokens = session.get("tokens", 0) if session else 0
    await emit("agent-status", {"agentId": "qa-3d", "status": "idle"})
    await _push_sys(emit, f"QA 3D done — verdict={verdict} score={overall:.1f}")

    # Append to score history for regression detection
    new_history = list(state.get("qa_score_history") or [])
    new_history.append(overall)

    return {
        "qa_pass": qa_pass,
        "qa_verdict": verdict,
        "qa_score": overall,
        "qa_fixes": fixes,
        "qa_report": qa_json_content,
        "qa_score_history": new_history,
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
