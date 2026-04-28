"""
Level Designer — produces docs/levels/level_01.json.

Pure data, no code. The Engine + Gameplay Programmer consume the JSON to
spawn entities, geometry, triggers, lights. Designed so the same level
file works across genres (FPS, top-down, platformer) — the gameplay layer
chooses what to instantiate.
"""
import json
import time
from pathlib import Path
from typing import Callable

from agents.base import READ_FILE_TOOL, WRITE_FILE_TOOL, run_agent_with_tools
from graph.game_state import GameState
from tools.file_ops import read_file, write_file


_LEVEL_DESIGNER_SYSTEM = """You are a Level Designer. You produce ONE JSON
file: docs/levels/level_01.json.

Schema (every level uses this shape):

{
  "id": "level_01",
  "name": "Display name shown on load",
  "size": [width, depth],            // metres on the XZ plane
  "spawn":  {"position": [x,y,z], "rotation_y_deg": 0},
  "goal":   {"position": [x,y,z], "type": "portal|stars|reach|survive_waves", "amount": 1},
  "blocks": [                        // static collision geometry
    {"id": "b1", "kind": "box",  "position":[x,y,z], "size":[w,h,d], "material": "floor|wall|hazard|crate"}
  ],
  "props":  [                        // visual / interactive scenery
    {"id": "p1", "asset": "crate", "position":[x,y,z], "rotation_y_deg": 0}
  ],
  "spawners": [                      // enemy / pickup spawn points
    {"id": "s1", "asset": "enemy_chaser", "position":[x,y,z], "rate": 2.0, "max_alive": 4}
  ],
  "lights": [                        // beyond the global sun + IBL
    {"id": "l1", "kind": "point", "position":[x,y,z], "color":"#ffd9a0", "intensity": 4, "range": 8}
  ],
  "triggers": [                      // narrative + game-state events
    {"id": "t1", "kind": "zone", "position":[x,y,z], "size":[w,h,d], "event": "play_music|show_text|enable_spawner|win", "args":{}}
  ],
  "music":  "combat_loop|menu_ambient|ambient_drone|none"
}

═════════ RULES ═════════

- ONE level. About 3-5 minutes of play.
- Size between 20x20 and 60x60.
- Place a clear sightline from spawn to the first encounter (within 8m).
- Place the goal so the player must traverse most of the level to reach it.
- Use only assets the recipe declares (the user message lists them).
- All Y values reference the world plane Y=0 = ground.
- Boxes with "kind": "box" become collision blocks; their material name
  controls visuals (the runtime maps wall→grey concrete, hazard→red, etc.).

═════════ HARD CONSTRAINTS ═════════

- Maximum 60 blocks, 25 props, 6 spawners, 6 lights, 8 triggers.
- Valid JSON only. No comments, no trailing commas.
- Write to docs/levels/level_01.json. One write_file call. Then stop."""


async def level_designer_node(state: GameState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("game_session", {})
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "level-designer", "status": "thinking"})
    await _push(emit, "🗺️ Level Designer — composing level_01.json")

    gdd = read_file(workspace, "docs/game-design.md") or ""
    recipe_name = state.get("recipe_name") or ""
    genre = state.get("genre", "auto")

    # Surface the recipe's asset list so the designer doesn't invent assets.
    asset_hint = ""
    try:
        from recipes.games import load_game_recipe
        recipe = load_game_recipe(recipe_name) if recipe_name else None
        if recipe:
            asset_hint = json.dumps(recipe.get("asset_requirements", {}), indent=2)
    except Exception:
        pass

    user_msg = f"""GENRE: {genre}
RECIPE: {recipe_name or '(custom)'}

GAME DESIGN DOC:
{gdd[:1500]}

ASSETS DECLARED IN RECIPE (use these IDs):
{asset_hint or '(none — invent sensible asset ids)'}

Write docs/levels/level_01.json. Strictly follow the schema in your system prompt.
Make it interesting — vary heights, create cover lines, signpost the goal.
Then stop."""

    async def tool_executor(name: str, inputs: dict):
        if name == "read_file":
            return read_file(workspace, inputs["path"])
        if name == "write_file":
            path = inputs["path"]
            content = inputs["content"]
            # Validate JSON if the path ends in .json — same pattern as QA.
            if path.endswith(".json"):
                try:
                    parsed = json.loads(content)
                    content = json.dumps(parsed, indent=2)
                except json.JSONDecodeError as exc:
                    return json.dumps({"error": f"JSON_PARSE_FAILED: {exc}. Retry with valid JSON."})
            result = write_file(workspace, path, content)
            if result.get("ok"):
                await _emit_file(emit, session, path, content, "level-designer")
            return json.dumps(result)
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_LEVEL_DESIGNER_SYSTEM,
        user_message=user_msg,
        tools=[READ_FILE_TOOL, WRITE_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="level-designer",
        api_key=state["api_key"],
        max_tokens=8000,
        max_iterations=4,
        session=session,
        stop_after_write=["docs/levels/level_01.json"],
        cache_system=True,
    )

    # Write a manifest for downstream agents.
    levels_dir = Path(workspace) / "docs" / "levels"
    levels_dir.mkdir(parents=True, exist_ok=True)
    level_paths = sorted(p.name for p in levels_dir.glob("*.json") if p.name != "manifest.json")
    manifest = {"levels": level_paths, "active": level_paths[0] if level_paths else None}
    manifest_text = json.dumps(manifest, indent=2)
    write_file(workspace, "docs/levels/manifest.json", manifest_text)
    await _emit_file(emit, session, "docs/levels/manifest.json", manifest_text, "level-designer")

    await emit("agent-status", {"agentId": "level-designer", "status": "idle"})
    await _push(emit, f"🗺️ Level Designer done — {len(level_paths)} level(s)")
    return {
        "levels_manifest": manifest_text,
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
