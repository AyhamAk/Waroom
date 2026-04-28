"""
Game Director — sets pillars, picks the genre/recipe, locks the design doc.

On cycle 0:
  - Match a recipe to the brief (or fall back to walking_sim).
  - Write docs/game-design.md (pillars + core loop + win/lose + controls).
  - Set state["recipe_name"] so the graph routes accordingly.

On later cycles (after vision playtest):
  - Read docs/playtest-report.json — judge whether the build is shippable.
  - Emit APPROVED or improvement notes in director_feedback.

Director never writes code. It writes specs + verdicts. Same pattern as
director_3d in the Blender pipeline.
"""
import json
import time
from pathlib import Path
from typing import Callable

from agents.base import READ_FILE_TOOL, WRITE_FILE_TOOL, run_agent_with_tools
from graph.game_state import GameState
from recipes.games import pick_game_recipe, parameterize_recipe, list_game_recipes
from tools.file_ops import read_file, write_file


_DIRECTOR_SYSTEM = """You are the Game Director of a top-tier indie studio.

You write the GAME DESIGN DOCUMENT (docs/game-design.md) — never code.

═════════ ON CYCLE 1 (initial design) ═════════

A recipe has already been matched and parameterised for you. The user
message contains the parameterised JSON. You:

1. Read the brief and the recipe.
2. Write docs/game-design.md in this EXACT structure:

   # <Game Title>
   ## Pillars
   - 3-4 short pillars that anchor every decision
   ## Core Loop
   - One paragraph: what does the player do every 30 seconds?
   ## Win / Lose
   - Win: ...
   - Lose: ...
   ## Controls
   - Bullet list of key bindings
   ## Camera
   - One-line camera contract
   ## Art Direction
   - 2-3 sentences on style + lighting mood
   ## Audio Direction
   - 2-3 sentences on music + SFX vibe
   ## Scope (CRITICAL)
   - 1 level, ~3-5 minutes of play, ~20 unique assets max
   - Hard "no": multiplayer, accounts, monetisation, save slots

3. STOP after writing.

═════════ ON CYCLE 2+ (review) ═════════

You receive a playtest report (docs/playtest-report.json). You:

1. Read it.
2. Write docs/director-review.md with verdict APPROVED or REVISE +
   one short paragraph of notes.
3. STOP.

APPROVED requires: build runs, controls feel right, screenshots show
the genre's signature, no console errors. Anything less → REVISE.

═════════ HARD RULES ═════════

- Never write code. Never write engine config. Never write asset specs.
- Keep docs/game-design.md under 80 lines.
- One write_file call. Then stop."""


async def game_director_node(state: GameState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("game_session", {})
    workspace = state["workspace_dir"]
    cycle = state.get("cycle", 0) + 1

    await emit("agent-status", {"agentId": "game-director", "status": "thinking"})
    await _push(emit, f"🎬 Game Director — cycle {cycle}")

    # Cycle 1 — pick a recipe and write the GDD.
    if cycle == 1:
        recipe = pick_game_recipe(state["brief"], genre_hint=state.get("genre", "auto"))
        recipe_name = recipe.get("name") if recipe else None
        spec = parameterize_recipe(recipe, state["brief"], state.get("art_style", "stylized")) if recipe else {}
        spec_json = json.dumps(spec, indent=2)
        recipe_list = ", ".join(list_game_recipes())

        user_msg = f"""BRIEF: {state['brief']}
GENRE_HINT: {state.get('genre', 'auto')}
ART_STYLE: {state.get('art_style', 'stylized')}
RECIPE_MATCHED: {recipe_name or '(none — write a custom GDD)'}
RECIPE_LIBRARY: {recipe_list}

PARAMETERISED RECIPE:
{spec_json}

Write docs/game-design.md following the cycle-1 template in your system
prompt. Use the recipe as your skeleton. Keep it tight."""
    else:
        # Review pass — judge the playtest.
        report = read_file(workspace, "docs/playtest-report.json") or "(no report yet)"
        gdd = read_file(workspace, "docs/game-design.md") or "(no GDD)"
        user_msg = f"""CYCLE: {cycle}

GAME DESIGN DOC (your earlier output, for reference):
{gdd[:1500]}

PLAYTEST REPORT (vision QA, freshest pass):
{report[:2500]}

Write docs/director-review.md with verdict APPROVED or REVISE plus a
short paragraph of notes. Then stop."""

    async def tool_executor(name: str, inputs: dict):
        if name == "read_file":
            return read_file(workspace, inputs["path"])
        if name == "write_file":
            path = inputs["path"]
            content = inputs["content"]
            result = write_file(workspace, path, content)
            if result.get("ok"):
                await _emit_file(emit, session, path, content, "game-director")
            return json.dumps(result)
        return f"Unknown tool: {name}"

    stop_files = ["docs/game-design.md"] if cycle == 1 else ["docs/director-review.md"]
    await run_agent_with_tools(
        system_prompt=_DIRECTOR_SYSTEM,
        user_message=user_msg,
        tools=[READ_FILE_TOOL, WRITE_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="game-director",
        api_key=state["api_key"],
        max_tokens=3000,
        max_iterations=4,
        session=session,
        stop_after_write=stop_files,
        cache_system=True,
    )

    if cycle == 1:
        recipe = pick_game_recipe(state["brief"], genre_hint=state.get("genre", "auto"))
        gdd = read_file(workspace, "docs/game-design.md")
        await _push(emit, f"📜 GDD written (recipe: {recipe.get('name') if recipe else 'custom'})")
        await emit("agent-status", {"agentId": "game-director", "status": "idle"})
        return {
            "cycle": cycle,
            "game_design": gdd,
            "recipe_name": recipe.get("name") if recipe else None,
            "genre": (recipe.get("genre") if recipe else state.get("genre", "auto")),
            "total_tokens": session.get("tokens", 0) if session else 0,
        }

    # Review cycle.
    review = read_file(workspace, "docs/director-review.md") or ""
    is_done = "APPROVED" in review.upper()
    await _push(emit, f"🎬 Director review — {'APPROVED ✓' if is_done else 'REVISE'}")
    await emit("agent-status", {"agentId": "game-director", "status": "idle"})
    return {
        "cycle": cycle,
        "director_feedback": review,
        "is_done": is_done,
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
