"""
Gameplay Programmer — writes the actual gameplay code that ties the
engine, level, assets, and materials together. Then runs `vite build` to
prove it compiles.

This is the only agent that writes JS code. It writes:
  - game/src/game/game.js          (replaces the placeholder)
  - game/src/game/<helpers>.js     (optional small helpers)

It must use the existing engine modules (Engine, Renderer, Input, Audio,
Assets, UI, PostFX, Physics) — never reimplement them.
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


_GAMEPLAY_SYSTEM = """You are a Gameplay Programmer. You ship the gameplay
code that turns the design + level + assets into a playable Three.js game.

═════════ ENGINE API (already provided — DO NOT REIMPLEMENT) ═════════

Imports available everywhere:
  import * as THREE from 'three';

The Engine instance is passed to your Game class. You use:

  // Scene + camera
  engine.renderer.scene             — THREE.Scene; add your meshes here
  engine.renderer.camera            — current camera (replace freely)
  engine.renderer.three             — THREE.WebGLRenderer
  engine.renderer.setExposure(v)
  engine.renderer.setShadowQuality('off|low|medium|high|vsm')

  // Lighting (HDRI + CSM + Sky + Fog)
  await engine.applyLightingPreset(name)            // see Tech-Art preset list
  engine.lighting.registerMaterial(material)        // ALWAYS call after creating
                                                      MeshStandardMaterial — required
                                                      for CSM cascades to apply
  engine.lighting.envTexture                        // current HDRI

  // Post-FX
  engine.enablePostFX(presetName)                   // call in preload() or start()
  engine.postfx.applyPreset(name)
  engine.postfx.setQuality('high|medium|low')
  engine.postfx.setFocus(distance)                  // dynamic DOF focus
  engine.postfx.setUniforms({bloom, ca, vignette, grain, dof_focus, dof_aperture})

  // Input
  engine.input.down / .pressed / .released          — Set<key>
  engine.input.mouse.dx/dy/.buttons/.pointerLocked
  engine.input.requestPointerLock()
  engine.input.axis(neg,pos,padAxis)

  // Audio
  engine.audio.blip(type)                           — 'shoot|hit|jump|pickup|die|click|beep'
  engine.audio.hum({root, dur, gain})

  // Assets
  engine.assets.primitive(kind, opts)               — Mesh: cube|sphere|cylinder|capsule|cone|torus|plane
  engine.assets.loadGltf(id, url)                   — await in preload()
  engine.assets.spawn(id)                           — { scene, anim, source }
                                                      anim is an Anim wrapper if clips exist
  engine.assets.loadTextureSet(id, {map, normalMap, roughnessMap, aoMap, ...})
  engine.assets.makePBRMaterial(id, {color, metalness, roughness})
  engine.assets.instanced(geom, mat, count)         — THREE.InstancedMesh, perfect for swarms
  engine.assets.lod([{object, distance}, ...])      — THREE.LOD

  // Particles (built-in GPU instanced)
  engine.particles.explosion(pos, {count,color,size,force})
  engine.particles.muzzleFlash(pos, dir, {count,color,size})
  engine.particles.blood(pos, {count,color})
  engine.particles.dust(pos, {count,color})
  engine.particles.sparkle(pos, {count,color})
  engine.particles.smoke(pos, {count,color})
  engine.particles.emit({position, velocity, color, alpha, size, life, gravity})

  // Decals (bullet holes, scorch marks, blood)
  engine.decals.spray(targetMesh, position, normal, {size, color, opacity})

  // Animation (skeletal, returned from assets.spawn(id).anim)
  anim.play(name, {fade, loop, timeScale})
  anim.triggerOnce(name, {fade})
  anim.update(dt)                                   — call from update()

  // UI
  engine.ui.text(slot, text)                        — slot ∈ tl|tr|bottom
  engine.ui.bar(label, value, max, slot)
  engine.ui.showOverlay(title, body, btn, onClick)
  engine.ui.hideOverlay()

  // Physics (kinematic helpers)
  import { Physics } from '/src/engine/physics.js';
  const phys = new Physics({ gravity: [0,-25,0] });
  phys.addStatic({ min: vec3, max: vec3 });
  const body = phys.addBody({ position, velocity, radius, height, kinematic });
  phys.step(dt);
  const hit = phys.raycast(origin, dir, maxDist);

═════════ STRICT WORKFLOW ═════════

1. list_files game/src once.
2. Read docs/engine-config.json, docs/materials.json,
   docs/levels/level_01.json, docs/asset-manifest.json,
   docs/game-design.md.
3. Write game/src/game/game.js — a complete Game class:
     constructor(engine), preload() (load any glTFs from manifest),
     start() (build scene from level loader, set camera per engine config,
     spawn player, attach PostFX from tech-art preset),
     update(dt, t) (input, physics step, AI, win/lose, HUD).
4. Optionally write 1-2 small helper files under game/src/game/.
5. run_command "cd game && npm install --no-audit --no-fund" if
   game/node_modules is missing (timeout 90).
6. run_command "cd game && npm run build" (timeout 180).
7. Verify the build wrote public/index.html. If it did — STOP.
   If not — read the error, fix the offending file, build again.

═════════ MANDATORY preload() PATTERN ═════════

The runtime fetches two JSON files at boot — both already live in the
Vite project's public/ folder so they're served at root:

  /asset-manifest.json   — Asset Lead's output. Each entry has:
      type:    "gltf"     → load via engine.assets.loadGltf(id, entry.path)
      type:    "procedural" → built lazily later via engine.assets.primitive()
      anims:   [...]        → present on rigged glTFs
      tags:    [...]        → for runtime filtering if needed

  /materials.json         — Tech-Art's output. Has lighting, post_fx,
                            materials.<id>, and block_materials.<name>.

In preload(), do EXACTLY this:

  async preload() {
    const [manifest, materials] = await Promise.all([
      fetch('/asset-manifest.json').then(r => r.json()),
      fetch('/materials.json').then(r => r.json()),
    ]);
    this.manifest = manifest;
    this.materials = materials;

    // 1. Lighting first — HDRI takes a moment to load.
    await this.engine.applyLightingPreset(materials.lighting.preset);
    if (materials.lighting.exposure_override != null)
      this.engine.renderer.setExposure(materials.lighting.exposure_override);

    // 2. Post-FX — apply preset, then per-effect overrides.
    this.engine.enablePostFX(materials.post_fx.preset);
    this.engine.postfx.setUniforms({
      bloom:    materials.post_fx.bloom_strength_override,
      vignette: materials.post_fx.vignette_amount_override,
      ca:       materials.post_fx.ca_override,
      grain:    materials.post_fx.grain_override,
      dof_focus: materials.post_fx.dof_focus_override,
    });

    // 3. Load every gltf asset declared in the manifest IN PARALLEL.
    const gltfEntries = Object.entries(manifest).filter(([_, e]) => e.type === 'gltf');
    await Promise.all(gltfEntries.map(([id, entry]) =>
      this.engine.assets.loadGltf(id, entry.path)
    ));
  }

═════════ HARD RULES ═════════

- ALWAYS use the engine API above. NEVER reimplement WebGL, input, audio,
  loading, post-fx, lighting, particles, decals, animation, or shadow setup.
- ALWAYS instantiate procedural manifest entries via
  engine.assets.primitive(entry.kind, {color: entry.color, metalness: ..., roughness: ...}).
- ALWAYS instantiate glTF entries via engine.assets.spawn(entry.id) — this
  returns {scene, anim, source}; .scene goes into the world, .anim drives
  AnimationMixer (call anim.play('Walk') etc.).
- For rigged characters: call anim.update(dt) every frame from your
  game.update().
- ALWAYS call engine.lighting.registerMaterial(material) after creating any
  new MeshStandardMaterial / MeshPhysicalMaterial — required for CSM cascades.
- ALWAYS pull material params (base_color, metallic, roughness, emissive,
  emissive_strength) from materials.materials[id] when spawning a glTF —
  override the spawned scene's MeshStandardMaterial fields with these.
- Pointer-lock genres (FPS): call requestPointerLock() in a click handler.
- Top-down genres: position camera high on Y, look down at the player.
- Movement is ALWAYS delta-time scaled (vec.multiplyScalar(speed * dt)).
- Use engine.particles for any combat/feedback FX — never spawn meshes for
  short-lived particles, the GPU system is much cheaper.
- Use engine.decals.spray() for bullet holes / blood / scorch marks.
- Use engine.assets.instanced() for swarms (>10 of the same enemy).
- Game logic file under 380 lines. If longer, split into 2-3 files.

═════════ EXIT CONDITION ═════════

You are done when public/index.html exists in the workspace root and
your last `npm run build` exited 0. Do not write a docs report — the
playtester is the next step."""


async def gameplay_programmer_node(state: GameState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("game_session", {})
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "gameplay-programmer", "status": "working"})
    await _push(emit, "🕹️ Gameplay Programmer — writing game code")

    gdd = read_file(workspace, "docs/game-design.md") or ""
    level = read_file(workspace, "docs/levels/level_01.json") or "{}"
    manifest = read_file(workspace, "docs/asset-manifest.json") or "{}"
    materials = read_file(workspace, "docs/materials.json") or "{}"
    engine_cfg = read_file(workspace, "docs/engine-config.json") or "{}"

    is_rebuild = bool(state.get("is_rebuild"))
    fixes = state.get("playtest_fixes") or []

    if is_rebuild:
        prompt_intro = (
            "REBUILD PASS — the last fix attempt regressed. Discard prior "
            "changes and re-implement game.js from scratch using the design "
            "docs below."
        )
    elif fixes:
        prompt_intro = (
            "FIX PASS — the playtester returned typed corrections. Apply "
            "ONLY these fixes. Do NOT rewrite the whole file unless required.\n"
            f"PLAYTEST FIXES:\n{json.dumps(fixes, indent=2)}"
        )
    else:
        prompt_intro = "INITIAL BUILD."

    user_msg = f"""{prompt_intro}

GENRE: {state.get('genre', 'auto')}
RECIPE: {state.get('recipe_name')}

GAME DESIGN DOC:
{gdd[:2000]}

LEVEL:
{level[:2500]}

ASSET MANIFEST:
{manifest[:2000]}

MATERIALS:
{materials[:1500]}

ENGINE CONFIG:
{engine_cfg[:1500]}

Follow the strict workflow in your system prompt. End when public/index.html
exists and the last build exited 0."""

    files_written: list[str] = []

    async def tool_executor(name: str, inputs: dict):
        if name == "list_files":
            return json.dumps(list_files(workspace, inputs.get("subdir", "game")))
        if name == "read_file":
            return read_file(workspace, inputs["path"])
        if name == "run_command":
            timeout = min(int(inputs.get("timeout", 60)), 200)
            result = await run_command(workspace, inputs["command"], timeout=timeout)
            summary = []
            if result["stdout"]:
                summary.append(f"STDOUT:\n{result['stdout'][:3000]}")
            if result["stderr"] and result["stderr"].strip():
                summary.append(f"STDERR:\n{result['stderr'][:1500]}")
            summary.append(f"Exit: {result['returncode']}")
            return "\n".join(summary)
        if name == "write_file":
            path = inputs["path"]
            content = inputs["content"]
            real_path = path
            # Anything under src/ goes inside game/src/
            if path.startswith("src/"):
                real_path = "game/" + path
            elif not path.startswith("game/") and not path.startswith("public/") and not path.startswith("docs/"):
                # Default new code into the game project.
                if path.endswith(".js") or path.endswith(".ts") or path.endswith(".css") or path.endswith(".html"):
                    real_path = "game/src/game/" + Path(path).name
            result = write_file(workspace, real_path, content)
            if result.get("ok"):
                files_written.append(real_path)
                await _emit_file(emit, session, real_path, content, "gameplay-programmer")
            return json.dumps(result)
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_GAMEPLAY_SYSTEM,
        user_message=user_msg,
        tools=[LIST_FILES_TOOL, READ_FILE_TOOL, RUN_COMMAND_TOOL, WRITE_FILE_TOOL],
        tool_executor=tool_executor,
        emit=emit,
        agent_id="gameplay-programmer",
        api_key=state["api_key"],
        max_tokens=12000,
        max_iterations=20,
        session=session,
        cache_system=True,
    )

    public_index = Path(workspace) / "public" / "index.html"
    built = public_index.exists()
    await emit("agent-status", {"agentId": "gameplay-programmer", "status": "idle"})
    await _push(emit, f"🕹️ Gameplay Programmer done — build {'✓ ok' if built else '✗ FAILED'}")
    return {
        "gameplay_files": files_written,
        "total_tokens": session.get("tokens", 0) if session else 0,
        "is_rebuild": False,   # consume the rebuild flag
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
