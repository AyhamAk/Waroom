"""
Vision Playtester — runs the built game in a real browser, captures
screenshots, scores the experience on a rubric, emits typed fixes.

Same architecture as qa_3d.py:
  - One run_playtest call (no LLM iteration overhead — pure tool work).
  - The captured frames are attached as vision blocks to the LLM prompt.
  - The LLM scores on the rubric and writes docs/playtest-report.json.
  - Fixes are TYPED — never raw code. Same DSL shape as Blender's QA.

The Gameplay Programmer applies the typed fixes on the next pass via the
same agent code path — no separate "fix executor" needed.
"""
import json
import time
from pathlib import Path
from typing import Callable

from agents.base import READ_FILE_TOOL, WRITE_FILE_TOOL, run_agent_with_tools
from graph.game_state import GameState
from tools.file_ops import read_file, write_file
from tools.playtester import run_playtest, encode_frame_b64


_PLAYTEST_SYSTEM = """You are a senior 3D game playtester. You have just
played the build. Multiple screenshots are attached as vision blocks. Score
the experience on a rubric and emit a SHORT typed fix list.

═════════ RUBRIC (1-10 per axis) ═════════

CONTROLS    — Does input feel responsive? Camera sane? Pointer-lock OK?
VISUALS     — PBR materials read? Lighting moods correct? Post-FX present?
GAMEPLAY    — Genre-defining beats happen? First encounter visible? Goal clear?
PERFORMANCE — Frame stable? No stutter visible across screenshots?
POLISH      — HUD readable? Audio cues present? Win/lose visible?

APPROVED: all five ≥ 7 AND overall ≥ 7.5.
REVISE:   any axis < 7 → emit typed fixes.

═════════ TYPED FIX OPS (the COMPLETE list) ═════════

  {"op": "set_camera_fov",        "args": {"fov": <num>}}
  {"op": "set_camera_offset",     "args": {"offset": [x,y,z]}}
  {"op": "set_camera_lerp",       "args": {"lerp": <num 0..1>}}

  {"op": "set_player_speed",      "args": {"speed": <num>}}
  {"op": "set_jump_velocity",     "args": {"velocity": <num>}}
  {"op": "set_gravity",           "args": {"gravity": <num>}}
  {"op": "set_mouse_sensitivity", "args": {"sensitivity": <num>}}

  {"op": "set_exposure",          "args": {"exposure": <num>}}
  {"op": "set_postfx_preset",     "args": {"preset": "vibrant_action|cinematic_grit|filmic_soft|filmic_dreamy|standard|minimal"}}
  {"op": "set_bloom_strength",    "args": {"strength": <num>}}
  {"op": "set_vignette_amount",   "args": {"amount": <num>}}
  {"op": "set_fog",               "args": {"enabled": true, "color": "#hex", "near": <num>, "far": <num>}}

  {"op": "set_material",          "args": {"id": "<asset_id>", "base_color": "#hex", "metallic": <num>, "roughness": <num>, "emissive": "#hex", "emissive_strength": <num>}}
  {"op": "set_block_material",    "args": {"name": "floor|wall|crate|hazard", "base_color": "#hex", "metallic": <num>, "roughness": <num>}}

  {"op": "set_spawn_rate",        "args": {"spawner": "<id>", "rate": <num>}}
  {"op": "set_max_alive",         "args": {"spawner": "<id>", "max": <int>}}
  {"op": "set_goal_amount",       "args": {"amount": <int>}}

  {"op": "add_hud_text",          "args": {"slot": "tl|tr|bottom", "text": "<text>"}}
  {"op": "set_hud_health_bar",    "args": {"max": <int>}}

  {"op": "fix_console_error",     "args": {"file": "src/...", "hint": "<one-line>"}}

═════════ HARD RULES ═════════

- Maximum 5 fixes per report. Prioritise the lowest-scoring axis.
- If the current pass score is LOWER than a previous one, suggest fewer +
  smaller fixes OR set verdict APPROVED to stop the regression.
- Never output `code` or `call` fields. Only `op` and `args`.
- Never output raw JS, Python, or shell. Only the typed ops above.
- Valid JSON only — no markdown fences, no prose around the object.

═════════ OUTPUT — docs/playtest-report.json ═════════

{
  "scores": {
    "controls":    {"score": 8, "notes": "..."},
    "visuals":     {"score": 6, "notes": "..."},
    "gameplay":    {"score": 7, "notes": "..."},
    "performance": {"score": 9, "notes": "..."},
    "polish":      {"score": 7, "notes": "..."}
  },
  "overall": 7.4,
  "verdict": "REVISE",
  "build_ok": true,
  "fixes": [
    {"op": "set_postfx_preset",   "args": {"preset": "vibrant_action"}},
    {"op": "set_bloom_strength",  "args": {"strength": 0.85}}
  ]
}"""


async def vision_playtester_node(state: GameState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("game_session", {})
    workspace = state["workspace_dir"]

    pass_no = state.get("playtest_pass", 0) + 1
    await emit("agent-status", {"agentId": "vision-playtester", "status": "working"})
    await _push(emit, f"🎮 Vision Playtester — pass {pass_no} (driving the build)")

    # 1. Run the playtest — Playwright if available, else static fallback.
    playtest = await run_playtest(workspace, genre=state.get("genre", "auto"))
    frames = playtest.get("frames", []) or []
    mode = playtest.get("mode")
    build_ok = playtest.get("build_ok", False)
    errors = playtest.get("errors", [])
    preview_url = playtest.get("url")

    await _push(emit, f"   playtest mode={mode} build_ok={build_ok} frames={len([f for f in frames if f.get('path')])}")

    # 2. Build the LLM user message — text + vision blocks.
    history = state.get("playtest_score_history") or []
    history_hint = ""
    if history:
        history_hint = (
            f"\nSCORE HISTORY (oldest→newest): {[round(s,1) for s in history]}"
            f"\nIf the latest score is lower than the previous one, your last "
            f"fixes regressed. Suggest fewer + smaller changes or APPROVE."
        )

    text_intro = f"""GENRE: {state.get('genre', 'auto')}
RECIPE: {state.get('recipe_name')}
PASS: {pass_no}
BUILD: {'OK' if build_ok else 'FAILED — public/index.html missing'}
PLAYTEST_MODE: {mode}
PREVIEW_URL: {preview_url or '(none)'}
ERRORS: {errors}
{history_hint}

Score the build on the rubric, write docs/playtest-report.json with typed
fixes. NEVER emit raw code. Maximum 5 fixes."""

    user_blocks: list = [{"type": "text", "text": text_intro}]
    for f in frames:
        path = f.get("path")
        if not path:
            continue
        encoded = encode_frame_b64(path)
        if not encoded:
            continue
        b64, media = encoded
        user_blocks.append({
            "type": "text",
            "text": f"FRAME — {f.get('label', '?')} (ts {f.get('ts','-')}). Examine carefully.",
        })
        user_blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media, "data": b64},
        })

    # If we have NO frames (catastrophic playtest failure) we still write a
    # report so the graph keeps moving.
    if not any(b.get("type") == "image" for b in user_blocks):
        report = {
            "scores": {
                "controls":    {"score": 0, "notes": "no frames captured"},
                "visuals":     {"score": 0, "notes": "no frames captured"},
                "gameplay":    {"score": 0, "notes": "no frames captured"},
                "performance": {"score": 0, "notes": "no frames captured"},
                "polish":      {"score": 0, "notes": "no frames captured"},
            },
            "overall": 0,
            "verdict": "REVISE",
            "build_ok": build_ok,
            "fixes": [
                {"op": "fix_console_error", "args": {
                    "file": "src/game/game.js",
                    "hint": "Build/preview failed — check console for boot errors and ensure index.html mounts the canvas."
                }}
            ],
            "errors": errors,
        }
        write_file(workspace, "docs/playtest-report.json", json.dumps(report, indent=2))
        await emit("agent-status", {"agentId": "vision-playtester", "status": "idle"})
        new_history = list(history) + [0.0]
        return {
            "playtest_pass": pass_no,
            "playtest_verdict": "REVISE",
            "playtest_score": 0.0,
            "playtest_fixes": report["fixes"],
            "playtest_report": json.dumps(report),
            "playtest_score_history": new_history,
            "latest_screenshot": None,
            "preview_url": preview_url,
            "total_tokens": session.get("tokens", 0) if session else 0,
        }

    # 3. Hand the vision blocks to the LLM.
    report_content = ""

    async def tool_executor(name: str, inputs: dict):
        nonlocal report_content
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
            if result.get("ok") and path == "docs/playtest-report.json":
                report_content = content
                await _emit_file(emit, session, path, content, "vision-playtester")
            return json.dumps(result)
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_PLAYTEST_SYSTEM,
        user_message="(see content blocks)",
        user_message_content=user_blocks,
        tools=[READ_FILE_TOOL, WRITE_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="vision-playtester",
        api_key=state["api_key"],
        max_tokens=4000,
        max_iterations=4,
        session=session,
        stop_after_write=["docs/playtest-report.json"],
        cache_system=True,
    )

    # 4. Parse verdict for routing.
    verdict = "REVISE"
    overall = 0.0
    fixes: list = []
    if not report_content:
        report_content = read_file(workspace, "docs/playtest-report.json") or ""
    try:
        data = json.loads(report_content)
        verdict = data.get("verdict", "REVISE").upper()
        overall = float(data.get("overall", 0))
        fixes = data.get("fixes", [])
    except Exception:
        pass

    # Force-advance after 3 passes.
    MAX_PASSES = 3
    if pass_no >= MAX_PASSES and verdict != "APPROVED":
        await _push(emit, f"playtest pass {pass_no} — force-advancing (max reached, score {overall:.1f})")
        verdict = "APPROVED"

    new_history = list(history) + [overall]
    last_screenshot = next((f.get("path") for f in reversed(frames) if f.get("path")), None)

    await emit("agent-status", {"agentId": "vision-playtester", "status": "idle"})
    await _push(emit, f"🎮 Playtester — verdict={verdict} score={overall:.1f}")

    return {
        "playtest_pass": pass_no,
        "playtest_verdict": verdict,
        "playtest_score": overall,
        "playtest_fixes": fixes,
        "playtest_report": report_content,
        "playtest_score_history": new_history,
        "latest_screenshot": last_screenshot,
        "preview_url": preview_url,
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
