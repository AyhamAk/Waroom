"""
Engine Engineer — wires the genre's runtime specifics on top of the Vite
+ Three.js scaffold. Writes ONE config + at most one or two source files.

Workflow:
  1. The orchestrator has already copied templates/game_base/ → workspace/game/.
  2. Read docs/game-design.md + the recipe + level + asset manifest.
  3. Write docs/engine-config.json — declarative wiring the gameplay
     programmer reads. Camera, physics, perf budget, post-fx preset, etc.
  4. Optionally write src/engine/level_loader.js (a tiny module that
     consumes level_01.json + asset-manifest.json and returns a Scene).

The Gameplay Programmer is the agent that writes the actual gameplay.
"""
import json
import time
from pathlib import Path
from typing import Callable

from agents.base import (
    LIST_FILES_TOOL, READ_FILE_TOOL, RUN_COMMAND_TOOL,
    WRITE_FILE_TOOL, run_agent_with_tools,
)
from graph.game_state import GameState
from tools.code_runner import run_command
from tools.file_ops import list_files, read_file, write_file


_ENGINE_SYSTEM = """You are an Engine Engineer. The Vite + Three.js scaffold
is ALREADY in workspace/game/. The engine has built-in modules for:
  - PBR rendering (sRGB output, ACES tone-map, MeshStandardMaterial)
  - Lighting: HDRI (RGBE), procedural Sky, Sun, CSM cascaded shadows, fog
  - PostFX: SSAO, bloom, bokeh DOF, FXAA, chromatic aberration, film grain, vignette
  - Particles (GPU instanced quads), decals, AnimationMixer wrapper
  - InstancedMesh + LOD helpers for swarms / dense scenes
You add genre-specific wiring on top — DO NOT rewrite any engine module.

═════════ STRICT WORKFLOW ═════════

1. list_files once to confirm the scaffold is intact.
2. Write docs/engine-config.json — pure data, no code. Schema:

   {
     "camera": {
       "type": "first_person|third_person_orbit|topdown_orthographic|fixed",
       "fov_or_size": 60,
       "follow": "player",
       "follow_offset": [0, 4, -7],
       "follow_lerp": 0.12,
       "min_pitch_deg": -10,
       "max_pitch_deg": 60
     },
     "physics": {
       "gravity": [0, -25, 0],
       "kind": "kinematic_capsule|rigid_body_with_capsule|kinematic_2d_in_3d_plane",
       "move_speed": 7.5,
       "sprint_mult": 1.5,
       "jump_velocity": 9.5,
       "air_control": 0.3
     },
     "input": {
       "pointer_lock": true,
       "mouse_sensitivity": 0.0022,
       "headbob": {"amplitude": 0.05, "speed": 9}
     },
     "perf_budget": {
       "target_fps": 60,
       "max_triangles": 1200000,
       "max_draw_calls": 120,
       "max_lights": 6,
       "texture_memory_mb": 200
     },
     "lighting_preset": "warm_outdoor_skybox|moody_industrial|stylized_topdown_punch|golden_hour_outdoor",
     "post_fx_preset": "vibrant_action|cinematic_grit|filmic_soft|filmic_dreamy|warm_outdoor_skybox|moody_industrial|stylized_topdown_punch|standard|minimal"
   }

3. Write src/engine/level_loader.js — a 60-100 line module that exports
   `loadLevel(engine, levelJson, manifest)`. It must:
     - Build collision boxes from level.blocks (push to engine.physics.colliders).
     - Spawn props using engine.assets — use Assets.primitive() for
       procedural manifest entries, GLTFLoader for glTF entries.
     - Place lights from level.lights.
     - Return { spawn, goal, spawners, triggers }.
   Keep it generic — it should work for every genre.

4. STOP.

═════════ HARD RULES ═════════

- Pick EXACTLY ONE preset from each enum — never invent new names.
- Match the recipe's perf_budget verbatim.
- Never write game.js. Never write main.js. Never touch package.json.
- Two write_file calls maximum. Then stop."""


async def engine_engineer_node(state: GameState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("game_session", {})
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "engine-engineer", "status": "working"})
    await _push(emit, "⚙️ Engine Engineer — wiring camera + physics")

    gdd = read_file(workspace, "docs/game-design.md") or ""
    level = read_file(workspace, "docs/levels/level_01.json") or "{}"
    manifest = read_file(workspace, "docs/asset-manifest.json") or "{}"

    recipe_text = ""
    try:
        from recipes.games import load_game_recipe
        recipe = load_game_recipe(state.get("recipe_name") or "")
        if recipe:
            recipe_text = json.dumps({
                "camera": recipe.get("camera", {}),
                "physics": recipe.get("physics", {}),
                "perf_budget": recipe.get("perf_budget", {}),
                "lighting_preset": recipe.get("lighting_preset"),
                "post_fx_preset": recipe.get("post_fx_preset"),
            }, indent=2)
    except Exception:
        pass

    user_msg = f"""GENRE: {state.get('genre', 'auto')}
RECIPE: {state.get('recipe_name')}

RECIPE CAMERA + PHYSICS + PERF + PRESETS:
{recipe_text}

GDD (excerpt):
{gdd[:1000]}

LEVEL (excerpt):
{level[:1500]}

ASSET MANIFEST (keys only):
{json.dumps(list(json.loads(manifest).keys()) if manifest.strip() else [], indent=2)}

Write docs/engine-config.json then src/engine/level_loader.js per your
system prompt. Two write_file calls max. Then stop."""

    async def tool_executor(name: str, inputs: dict):
        if name == "list_files":
            return json.dumps(list_files(workspace, inputs.get("subdir", "game")))
        if name == "read_file":
            return read_file(workspace, inputs["path"])
        if name == "run_command":
            timeout = min(int(inputs.get("timeout", 60)), 120)
            result = await run_command(workspace, inputs["command"], timeout=timeout)
            return f"STDOUT:\n{result['stdout'][:1500]}\nSTDERR:\n{result['stderr'][:600]}\nExit: {result['returncode']}"
        if name == "write_file":
            path = inputs["path"]
            content = inputs["content"]
            if path.endswith(".json"):
                try:
                    parsed = json.loads(content)
                    content = json.dumps(parsed, indent=2)
                except json.JSONDecodeError as exc:
                    return json.dumps({"error": f"JSON_PARSE_FAILED: {exc}"})
            # Engine-side files live under game/ so Vite picks them up.
            real_path = path
            if path.startswith("src/"):
                real_path = "game/" + path
            result = write_file(workspace, real_path, content)
            if result.get("ok"):
                await _emit_file(emit, session, real_path, content, "engine-engineer")
            return json.dumps(result)
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_ENGINE_SYSTEM,
        user_message=user_msg,
        tools=[LIST_FILES_TOOL, READ_FILE_TOOL, RUN_COMMAND_TOOL, WRITE_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="engine-engineer",
        api_key=state["api_key"],
        max_tokens=6000,
        max_iterations=6,
        session=session,
        stop_after_write=["game/src/engine/level_loader.js"],
        cache_system=True,
    )

    cfg = read_file(workspace, "docs/engine-config.json")
    await emit("agent-status", {"agentId": "engine-engineer", "status": "idle"})
    await _push(emit, "⚙️ Engine Engineer done")
    return {
        "engine_config": cfg,
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
