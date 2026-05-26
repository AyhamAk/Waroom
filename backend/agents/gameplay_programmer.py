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

═════════ VISUAL QUALITY MANDATE ═════════

The game MUST look polished and visually impressive. This is non-negotiable.
Every game you build must have ALL of the following:

GEOMETRY DIVERSITY
- Never use a plain SphereGeometry for more than one entity type.
- Each distinct game entity (player, each enemy type, core, props) must use a
  DIFFERENT geometry: OctahedronGeometry, IcosahedronGeometry, ConeGeometry,
  TorusGeometry, CylinderGeometry, DodecahedronGeometry, LatheGeometry, etc.
- Enemies must look threatening. Shards = sharp cones. Drones = octahedra.
  Giants = icosahedra. Never plain spheres.

FLOOR / ARENA SHADERS
- Static flat-colored floors are forbidden. Every floor or platform surface
  MUST use a ShaderMaterial with a procedural pattern: hex grid, circuit
  lines, voronoi cells, or animated pulse rings.
- Hex grid fragment shader pattern is the gold standard for sci-fi arenas.
  Always implement it when the genre is top-down, arena, or tower-defense.

DECORATIVE ELEMENTS
- Every arena must have at least 4 decorative props at the corners/edges:
  obelisks, pylons, floating crystals, etc. These add depth and scale.
- Obelisks: tall thin CylinderGeometry + ConeGeometry tip, emissive material,
  small PointLight at the tip.

PARTICLE EFFECTS
- Use engine.particles.explosion() on every enemy death — color matched to
  enemy type.
- Use engine.particles.muzzleFlash() on every player shot.
- Use engine.particles.sparkle() on wave clear and score milestones.

ANIMATIONS
- The core/central object MUST rotate and pulse.
- The player entity MUST have a hover bob animation (sin wave on Y).
- Enemies MUST have type-specific rotation: drones spin on Y, shards tumble
  on X+Y, giants roll on all axes.

EMISSIVE LIGHTING
- All game-relevant objects (player, enemies, core, arena lines) must use
  emissive materials. A game where the entities don't glow looks dead.
- Target emissiveIntensity: 1.0–1.5 for primary objects, 0.5–0.8 for
  secondary/decorative. Never 0.

POSTFX WIRING
- Wire chromatic aberration spikes to impact events (core hit).
- Wire bloom strength changes to game state (low HP = stronger bloom).

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

  // Trails — ribbon trails behind fast-moving objects (enemies, projectiles)
  const trail = engine.trails.create(mesh, {color, length, width, opacity})
  trail.destroy()                                    — call when entity dies

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

═════════ SURFACE TEXTURES ═════════

docs/textures.json is written by the Texture Artist before you run.
READ IT with read_file("docs/textures.json") during your initial reads.

Schema:
  {
    "floor": {"file": "textures/floor.png", "repeat": 8},
    "wall":  {"file": "textures/wall.png",  "repeat": 4},
    "prop":  {"file": "textures/prop.png",  "repeat": 2}
  }

APPLICATION RULES (mandatory when textures.json exists and has no errors):
- ALL large flat surfaces (ground planes, arena floors, platforms,
  terrain) → use textures["floor"]. Flat MeshStandardMaterial colors
  are FORBIDDEN for these when a floor texture is available.
- ALL vertical barriers, walls, fences → use textures["wall"].
- ALL crates, barrels, boxes, static props → use textures["prop"].
- NEVER apply textures to animated entities (player, enemies, pickups)
  — their geometry + emissive materials are intentional.

Load pattern — add this helper near the top of game.js:

    const _texLoader = new THREE.TextureLoader()
    function _loadTex(file, repeat) {
      const t = _texLoader.load(file)
      t.wrapS = t.wrapT = THREE.RepeatWrapping
      t.repeat.set(repeat, repeat)
      return t
    }

Then in scene setup after reading textures.json:

    let txFloor = null, txWall = null, txProp = null
    try {
      const txData = await fetch('/textures.json').then(r => r.json())
      if (txData.floor?.file) txFloor = _loadTex(txData.floor.file, txData.floor.repeat || 8)
      if (txData.wall?.file)  txWall  = _loadTex(txData.wall.file,  txData.wall.repeat  || 4)
      if (txData.prop?.file)  txProp  = _loadTex(txData.prop.file,  txData.prop.repeat  || 2)
    } catch (_) { /* textures optional */ }

Apply:
    const floorMat = new THREE.MeshStandardMaterial({
      map: txFloor, roughness: 0.92, metalness: 0.0
    })
    const wallMat = new THREE.MeshStandardMaterial({
      map: txWall, roughness: 0.85, metalness: 0.0
    })

- Textures load async — Three.js renders fine before they arrive (no
  need to await). The material updates automatically when the image loads.
- If textures.json fetch fails or a file field is null, fall back to the
  flat color from materials.json. Never let a missing texture crash init.

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

═══ ASSET MANIFEST SCHEMA (READ THIS TWICE) ═══

The asset-manifest.json file is a FLAT OBJECT. The keys ARE the asset
IDs. There is NO `.assets` wrapper, NO `.entries` wrapper, NO nesting
of any kind. This is not a suggestion — it is the actual shape on disk.

Real example of what you will fetch — copy this mentally before writing
code:

    {
      "floor":  { "id": "floor",  "type": "procedural", "kind": "cube",
                  "color": "#0a0a1a", "metallic": 0.9, "roughness": 0.2 },
      "wall":   { "id": "wall",   "type": "procedural", "kind": "cube",
                  "color": "#1a1a3a", "metallic": 0.8, "roughness": 0.3 },
      "pillar": { "id": "pillar", "type": "gltf",
                  "path": "assets/pillar.glb", "anims": ["spin"] }
    }

Notice: the top-level keys are "floor", "wall", "pillar" — NOT "assets".

═══ ABSOLUTE BANS (these have caused real production crashes) ═══

  ✗ NEVER WRITE: manifest.assets
  ✗ NEVER WRITE: manifest.assets || {}
  ✗ NEVER WRITE: manifest?.assets
  ✗ NEVER WRITE: const assets = manifest.assets ?? {}
  ✗ NEVER WRITE: for (const [id, entry] of Object.entries(manifest.assets))

  These all silently produce an empty asset set, which boots a black
  empty canvas with NO error message. The user sees nothing, the
  playtester captures black frames, the bug looks like a "preview
  failure" but is actually your code.

═══ THE ONLY CORRECT PATTERN ═══

  // Iterate the manifest directly — keys ARE asset IDs.
  const gltfEntries = Object.entries(manifest)
    .filter(([_, e]) => e && e.type === 'gltf');
  // entry.id, entry.type, entry.path, entry.color, entry.kind, etc. all
  // live directly on each entry object.

═══ NO DEFENSIVE `||` DEFAULTS ON SCHEMA READS ═══

If you find yourself writing `someObj.knownKey || {}` or `?? defaultValue`
on a property that should always exist according to the schema — DON'T.
Let the missing-property surface as an exception. The error overlay we
have on the iframe will show the stack trace in 1 second; a `||` default
hides the bug for hours.

  ✗ const lighting = materials.lighting || {};   // hides bugs
  ✓ const lighting = materials.lighting;         // throws if missing

The only place `||` defaults are acceptable is for genuinely-optional
values (e.g. `materials.post_fx.bloom_strength_override` which is null
if Tech-Art chose the preset default).

═══ FIX-THEN-INVESTIGATE WORKFLOW RULE ═══

When a build is failing or a runtime bug is identified:
  1. State what the bug is in one sentence.
  2. Your VERY NEXT TOOL CALL must be `write_file` patching the bug.
     NOT another read_file. NOT another run_command. write_file.
  3. THEN run the build again to verify.
  4. If the bug isn't fully fixed, repeat — but each cycle must include
     at least one write_file. Reading without writing is forbidden after
     the first time you've named the bug.

You will be tempted to "just check one more file" before writing the
fix. Resist. The diagnosis you have is enough. Patch first; if the
patch is wrong, the next run will tell you and you can iterate.

═══ READ_FILE TRUNCATION WARNING ═══

When read_file returns content that visibly ends mid-array, mid-object,
or mid-line (no closing brace, abrupt cutoff, etc.), DO NOT draw schema
conclusions from it. Either:
  - Re-read the file and look for the closing structure, OR
  - Use run_command with `wc -l` and `head -N`/`tail -N` to inspect
    specific sections, OR
  - Trust the schema from the source agent's spec (Asset Lead's manifest
    is always flat; that is documented in this prompt above), and don't
    re-derive the schema from a partial file read.

═══ FILE LOCATIONS ═══

The runtime fetches two JSON files at boot — both already live in the
Vite project's public/ folder so they're served at root:

  /asset-manifest.json   — Asset Lead's output (flat object, see above).
  /materials.json        — Tech-Art's output. Has lighting, post_fx,
                           materials.<id>, and block_materials.<name>.

═══ MANDATORY preload() — COPY THIS PATTERN EXACTLY ═══

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
    //    Iterate manifest itself — see "ABSOLUTE BANS" section above.
    const gltfEntries = Object.entries(manifest)
      .filter(([_, e]) => e && e.type === 'gltf');
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
- Every floor/platform MUST use ShaderMaterial (no plain MeshStandardMaterial
  for large horizontal surfaces visible from above).
- Every entity type must use a unique geometry — no two different entity
  categories may share the same geometry constructor.
- Minimum 4 decorative props in the scene.

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

    # Context trimmed — the system prompt already documents schema; we
    # only need enough excerpt for the agent to know the specific
    # game's content. Total ~5K chars vs ~9.5K previously, ~45% input
    # reduction. With 5-min prompt caching, this affects mostly the
    # first call of each cycle (subsequent iterations are cache reads).
    user_msg = f"""{prompt_intro}

GENRE: {state.get('genre', 'auto')}
RECIPE: {state.get('recipe_name')}

GAME DESIGN DOC (excerpt):
{gdd[:1200]}

LEVEL (excerpt):
{level[:1800]}

ASSET MANIFEST (excerpt):
{manifest[:1400]}

MATERIALS (excerpt):
{materials[:1100]}

ENGINE CONFIG (excerpt):
{engine_cfg[:900]}

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

            # ── HARD GUARD: forbidden-pattern check on JS source ─────────
            # The asset manifest is FLAT. References to manifest.assets are
            # a hallucinated wrapper that silently produces an empty asset
            # set, booting a black canvas with no error. We refuse the write
            # so the agent must fix it before progressing. (Spaces optional
            # to catch manifest.assets, manifest .assets, manifest?.assets.)
            if real_path.endswith((".js", ".ts", ".mjs")):
                import re as _re
                bad = []
                # Dot-access (incl. optional chaining + whitespace).
                if _re.search(r"manifest\s*\??\s*\.\s*assets\b", content):
                    bad.append("manifest.assets / manifest?.assets")
                # Bracket access with string key — same hallucinated wrapper.
                if _re.search(r"manifest\s*\??\s*\[\s*['\"]assets['\"]\s*\]", content):
                    bad.append("manifest['assets'] / manifest[\"assets\"]")
                if bad:
                    err = (
                        "WRITE REJECTED: forbidden pattern in code. "
                        "The asset manifest is FLAT — there is NO `.assets` wrapper. "
                        f"Found: {', '.join(bad)} in {real_path}. "
                        "The keys of the manifest object ARE the asset IDs. "
                        "Use Object.entries(manifest) or manifest[<id>] directly. "
                        "Re-emit write_file with the corrected source. "
                        "Do not proceed to build until fixed."
                    )
                    return json.dumps({"ok": False, "path": real_path, "error": err})

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
    session_id = state.get("session_id", "")
    preview_url = f"/workspace/{session_id}/public/" if built and session_id else None
    await emit("agent-status", {"agentId": "gameplay-programmer", "status": "idle"})
    await _push(emit, f"🕹️ Gameplay Programmer done — build {'✓ ok' if built else '✗ FAILED'}")
    return {
        "gameplay_files": files_written,
        "preview_url": preview_url,
        "total_tokens": session.get("tokens", 0) if session else 0,
        "is_rebuild": False,
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
