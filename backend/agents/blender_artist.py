"""
Blender Artist 3D — thin executor.

Workflow:
    1. Ensure bpy_runtime is loaded inside Blender (once per session).
    2. Read docs/scene-plan.json produced by the Scene Architect.
    3. Call br.build_scene_from_spec(spec) — ONE blender_execute call builds
       the entire scene (materials, objects, lights, camera, animation, compositor).
    4. Run br.qa_checklist() — self-diagnose critical issues.
    5. Render one preview, attach it as vision feedback, and iterate only if
       QA reports issues.
    6. Write docs/build-report.md summary.

Previous implementation made 15-25 blender_execute calls with a full preview
image attached to each. This version typically makes 2-4 calls and attaches
preview images only at decision points.
"""
import json
import time
from pathlib import Path
from typing import Callable

from agents.base import READ_FILE_TOOL, WRITE_FILE_TOOL, run_agent_with_tools
from graph.blender_state import BlenderState
from tools.blender_tool import execute_blender_async, encode_preview_as_b64, save_viewport_render
from tools.bpy_runtime import get_runtime_source, install_marker_code
from tools.file_ops import read_file, write_file

# ── Tool schemas ──────────────────────────────────────────────────────────────

BLENDER_EXECUTE_TOOL = {
    "name": "blender_execute",
    "description": (
        "Execute Python in the live Blender instance. The `br` namespace is preloaded "
        "(bpy_runtime) — call br.build_scene_from_spec(spec), br.make_pbr(), "
        "br.camera_orbit() etc. Returns stdout + a TEXT summary. To see a rendered "
        "preview, call the request_preview tool afterwards."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python to run inside Blender."},
        },
        "required": ["code"],
    },
}

REQUEST_PREVIEW_TOOL = {
    "name": "request_preview",
    "description": (
        "Render and return a viewport preview image as vision feedback. Use this "
        "ONLY when you need to visually verify the scene — after the full build, "
        "or when debugging a specific issue. Returns an image block you can look at."
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

# ── System prompt — deliberately compact; the heavy lifting is in bpy_runtime ─

_ARTIST_SYSTEM = """You are a Blender Artist. You execute a PRE-WRITTEN spec via bpy_runtime.
You are a mechanical executor, NOT a creative decision-maker.

═════════ STRICT WORKFLOW — INITIAL BUILD (qa_pass == 0) ═════════

1. Read docs/scene-plan.json with read_file.
2. blender_execute ONCE with exactly this pattern:
       import json
       spec = json.loads(r\"\"\"<paste the JSON exactly>\"\"\")
       report = br.build_scene_from_spec(spec)
       issues = br.qa_checklist()
       print("BUILD_REPORT:", json.dumps(report))
       print("QA_ISSUES:", json.dumps(issues))
3. request_preview ONCE.
4. write_file docs/build-report.md (4-6 lines summarising what was built).

STOP. Do not "improve" the scene. Do not delete floors or reframe cameras. Do
not second-guess the spec. If you see problems in the preview, QA will flag
them and you'll get TYPED fixes in a later pass.

ONE blender_execute + ONE request_preview + ONE write_file. That is all.

═════════ STRICT WORKFLOW — FIX PASS (qa_pass > 0) ═════════

Your user message will include a TYPED FIX LIST as JSON. Apply them via a single
br.apply_fixes() call — NEVER write raw bpy code in a fix pass.

1. blender_execute ONCE:
       import json
       fixes = json.loads(r\"\"\"<paste the typed fix list exactly>\"\"\")
       report = br.apply_fixes(fixes)
       issues = br.qa_checklist()
       print("FIX_REPORT:", json.dumps(report))
       print("QA_ISSUES:", json.dumps(issues))
2. request_preview ONCE.
3. write_file docs/build-report.md noting which fixes applied and which failed.

STOP. Do NOT call bpy.ops. Do NOT call transform_apply. Do NOT rescale meshes.
Do NOT invent new fixes. Do NOT delete objects that weren't in the fix list.
Only call br.apply_fixes(fixes) with the exact fixes from your user message.

═════════ WHY THIS IS STRICT ═════════

Previous runs showed agents making speculative "improvements" that compounded
into broken scenes. The recipe/spec is pre-validated. The typed fix list comes
from QA which can see the rendered preview. Your job is execution, not design.

═════════ br NAMESPACE (for reference; do NOT write raw Python in fixes) ═════════

  br.build_scene_from_spec(spec)   ← ONLY on initial build
  br.apply_fixes(fixes)            ← ONLY on fix passes
  br.qa_checklist()                ← diagnostic; OK to call
  br.scene_summary()               ← diagnostic; OK to call

Anything else (make_pbr, make_light, compositor_polish, etc.) is already
invoked inside build_scene_from_spec and apply_fixes. Do not call them
directly from your code — everything you need is in the two primary entry
points."""


async def blender_artist_node(state: BlenderState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("blender_session", {})
    workspace = state["workspace_dir"]

    renders_dir = Path(workspace) / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    preview_counter = [0]
    latest_render: list[str | None] = [None]

    await emit("agent-status", {"agentId": "blender-artist-3d", "status": "working"})
    await _push_sys(emit, "Blender Artist 3D — loading runtime, executing spec")

    # ── Step 0: Ensure bpy_runtime is loaded (and current) in Blender ────────
    marker = await execute_blender_async(install_marker_code(), timeout=10)
    marker_out = (marker.get("result") or "")
    needs_reload = (
        "RUNTIME_MISSING" in marker_out
        or "RUNTIME_OUTDATED" in marker_out
        or marker.get("status") == "error"
    )
    if needs_reload:
        reason = "outdated" if "OUTDATED" in marker_out else "missing"
        await _push_sys(emit, f"Injecting bpy_runtime ({reason}) into Blender session")
        load_result = await execute_blender_async(get_runtime_source(), timeout=30)
        if load_result.get("status") == "error":
            await _push_sys(emit, f"bpy_runtime load failed: {load_result.get('message','unknown')}")
        else:
            await _push_sys(emit, "bpy_runtime ready (br.* namespace available)")

    # ── Step 1: Provide spec + invoke agent ──────────────────────────────────
    scene_plan_json = read_file(workspace, "docs/scene-plan.json")
    # Fall back for back-compat if somehow only .md exists
    if not scene_plan_json or scene_plan_json.startswith("(file not found"):
        md = read_file(workspace, "docs/scene-plan.md")
        if md and not md.startswith("(file not found"):
            scene_plan_json = md  # will trip the JSON-parse guard below
    concept = read_file(workspace, "docs/scene-concept.md")
    style = state.get("style", "commercial")

    # Validate the spec up-front so the agent can focus on execution, not parsing
    try:
        _ = json.loads(scene_plan_json) if scene_plan_json else None
        spec_summary_hint = ""
    except Exception as exc:
        spec_summary_hint = f"\nWARNING: scene-plan.json is invalid ({exc}). Use br.apply_style('{style}') then build manually."

    qa_fixes = state.get("qa_fixes") or []
    qa_pass = state.get("qa_pass", 0)
    is_rebuild = bool(state.get("is_rebuild"))
    is_fix_pass = qa_pass > 0 and len(qa_fixes) > 0 and not is_rebuild

    if is_fix_pass:
        # Fix pass — typed fixes only. Artist calls br.apply_fixes(fixes).
        # Filter to typed-op format; strip legacy {code, call} fields defensively.
        clean_fixes = [
            {"op": f.get("op") or f.get("action"), "args": f.get("args", {})}
            for f in qa_fixes
            if (f.get("op") or f.get("action"))
        ]
        fixes_json = json.dumps(clean_fixes, indent=2)
        user_msg = f"""PRODUCT: {state['product_description']}
STYLE: {style}
QA_PASS: {qa_pass}

FIX PASS — apply the typed fixes below via br.apply_fixes(). Do NOT rebuild.
Do NOT write any bpy code beyond the single br.apply_fixes(fixes) call.

TYPED FIXES (copy this JSON exactly into your blender_execute):
{fixes_json}

Workflow:
  1. ONE blender_execute:
       import json
       fixes = json.loads(r\"\"\"{fixes_json}\"\"\")
       report = br.apply_fixes(fixes)
       print("FIX_REPORT:", json.dumps(report))
       print("QA_ISSUES:", json.dumps(br.qa_checklist()))
  2. ONE request_preview.
  3. write_file docs/build-report.md."""
    elif is_rebuild:
        # Regression detected — rebuild from scratch using the original spec.
        # Discards any partial fixes that made things worse.
        user_msg = f"""PRODUCT: {state['product_description']}
STYLE: {style}

REBUILD PASS — the last fix attempt regressed. Ignore current scene state.
Rebuild from the ORIGINAL spec below exactly as in your initial-build workflow.

docs/scene-plan.json:
{scene_plan_json}

DIRECTOR'S NOTES (context only):
{(concept or '')[:500]}

ONE blender_execute (br.build_scene_from_spec). ONE request_preview. ONE
write_file build-report. Do NOT apply any fixes — the regression told us the
fixes were wrong; we're back to known-good."""
    else:
        user_msg = f"""PRODUCT: {state['product_description']}
STYLE: {style}

docs/scene-plan.json (your input spec):
{scene_plan_json}

DIRECTOR'S NOTES (context only):
{(concept or '')[:500]}
{spec_summary_hint}

Initial build per system prompt: ONE blender_execute (br.build_scene_from_spec),
ONE request_preview, ONE write_file. No speculation."""

    async def tool_executor(name: str, inputs: dict):
        nonlocal latest_render
        if name == "blender_execute":
            code = inputs["code"]
            result = await execute_blender_async(code, timeout=90)
            if result.get("status") == "error":
                return f"BLENDER_ERROR: {result.get('message', 'unknown error')}"
            # Save a preview to disk for the UI but DO NOT attach it to the tool
            # result (agent must explicitly request via request_preview).
            preview_counter[0] += 1
            preview_filename = f"preview_{preview_counter[0]:03d}.png"
            preview_path = str(renders_dir / preview_filename)
            render_result = save_viewport_render(preview_path)
            if render_result.get("status") != "error":
                latest_render[0] = preview_path
                if session:
                    session["latest_render"] = preview_path
                rel_url = f"/api/blender/render/{state['session_id']}/{preview_filename}"
                await emit("blender-frame", {
                    "path": preview_path,
                    "url": rel_url,
                    "frame": preview_counter[0],
                    "session_id": state["session_id"],
                })
            out = result.get("result", "")
            return f"OK. {out[:1200]}\nPREVIEW_SAVED: {preview_path} (call request_preview to view)"

        if name == "request_preview":
            path = latest_render[0]
            if not path:
                # Force a render right now
                preview_counter[0] += 1
                preview_filename = f"preview_{preview_counter[0]:03d}.png"
                path = str(renders_dir / preview_filename)
                rr = save_viewport_render(path)
                if rr.get("status") == "error":
                    return "PREVIEW_FAILED: no preview available yet"
                latest_render[0] = path
                if session:
                    session["latest_render"] = path
            encoded = encode_preview_as_b64(path)
            if not encoded:
                return f"PREVIEW_ENCODE_FAILED at {path}"
            b64, media = encoded
            return [
                {"type": "text", "text": f"Preview from {Path(path).name}. Examine carefully."},
                {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
            ]

        if name == "read_file":
            return read_file(workspace, inputs["path"])

        if name == "write_file":
            path = inputs["path"]
            content = inputs["content"]
            return str(write_file(workspace, path, content))

        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_ARTIST_SYSTEM,
        user_message=user_msg,
        tools=[BLENDER_EXECUTE_TOOL, REQUEST_PREVIEW_TOOL, READ_FILE_TOOL, WRITE_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="blender-artist-3d",
        api_key=state["api_key"],
        max_tokens=4096,
        max_iterations=5,          # ONE execute + ONE preview + ONE write, with retry room
        session=session,
        cache_system=True,
    )

    tokens = session.get("tokens", 0) if session else 0
    final_render = latest_render[0]
    if session:
        session["latest_render"] = final_render

    await emit("agent-status", {"agentId": "blender-artist-3d", "status": "idle"})
    await _push_sys(emit, "Blender Artist 3D done — scene built")

    # Clear rebuild flag once consumed — next QA pass starts fresh
    out = {
        "latest_render_path": final_render,
        "total_tokens": tokens,
    }
    if is_rebuild:
        out["is_rebuild"] = False
    return out


async def _push_sys(emit: Callable, message: str):
    await emit("new-message", {
        "from": "system",
        "to": None,
        "type": "system",
        "message": message,
        "id": int(time.time() * 1000),
        "timestamp": int(time.time() * 1000),
    })
