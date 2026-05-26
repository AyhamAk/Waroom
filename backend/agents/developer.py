"""
Developer Agent — THE STAR of the system.
Reads specs, writes real code, RUNS IT, sees output, fixes errors — loops until working.
Supports any language: vanilla JS, TypeScript/Vite, Python FastAPI, Node.js, anything.
"""
import json
import time
from typing import Callable

from agents.base import (
    LIST_FILES_TOOL, READ_FILE_TOOL, RUN_COMMAND_TOOL,
    WRITE_FILE_TOOL, WEB_SEARCH_TOOL,
    run_agent_with_tools,
)
from graph.state import CompanyState
from tools.code_runner import run_command
from tools.file_ops import list_files, read_file, write_file
from tools.search import web_search

DEV_TOOLS = [READ_FILE_TOOL, WRITE_FILE_TOOL, LIST_FILES_TOOL, RUN_COMMAND_TOOL, WEB_SEARCH_TOOL]

_DEV_SYSTEM = """You are an elite developer. You ship working, beautiful, complete products.

TOOLS:
- read_file: Read existing code files (NOT docs — specs are already in the message)
- write_file: Write code
- list_files: See workspace state
- run_command: Install, build, run
- web_search: Max 1 search if genuinely needed; if rate-limited, use own knowledge

━━━ ZERO TOLERANCE RULES ━━━
- NO TODO comments. NO placeholder functions. NO "// implement later".
- Every function must be FULLY implemented. Every feature must WORK.
- COPY the design spec CSS variables, class names, dimensions EXACTLY — never improvise styles.
- The result must be impressive. Users will screenshot it. Make it beautiful.

━━━ WORKFLOW ━━━
1. list_files() ONCE — see what exists
2. write_file immediately for each needed file — no planning, no re-reading docs
3. For npm/Vite: install → build → verify public/index.html → fix if needed
4. For vanilla JS: write all files then done

━━━ FILE SPLITTING — MANDATORY FOR LARGE PROJECTS ━━━
Never write one file over 400 lines. Split by concern:
  public/index.html      — HTML + CDN imports only (< 50 lines)
  public/js/engine.js    — rendering, Three.js scene setup
  public/js/game.js      — logic, entities, state machine
  public/js/ui.js        — HUD, menus, overlays
  public/css/style.css   — all styles (copy exact values from design spec)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TYPESCRIPT + VITE PROJECTS — MANDATORY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ALWAYS create this file first:
   Path: <project>/src/vite-env.d.ts
   Content: /// <reference types="vite/client" />
   (This fixes ALL CSS module import errors in TypeScript)

2. ALWAYS configure vite.config.ts with BOTH of these:
   import { resolve } from 'path';
   base: './',   ← CRITICAL: makes asset paths relative so the preview proxy works
   build: {
     outDir: resolve(__dirname, '../public'),
     emptyOutDir: true,
   }
   This means "npm run build" outputs DIRECTLY to workspace/public/ — no copy step needed.

3. Build script in package.json MUST be just "vite build", not "tsc && vite build":
   "build": "vite build"
   (TypeScript errors won't block the preview this way. Fix TS errors separately if needed.)

4. After build: verify with run_command("dir public /B 2>&1") that index.html is there.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VANILLA JS — ALL FILES MUST LIVE IN public/
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL RULE: EVERY file you write MUST be inside public/ or a public/ subdirectory.
NEVER create a src/ directory. NEVER put JS/CSS outside public/.

Correct structure:
  public/index.html        ← entry point
  public/css/style.css     ← styles
  public/js/app.js         ← main logic
  public/js/engine.js      ← additional modules

In index.html, reference with RELATIVE paths:
  <link rel="stylesheet" href="css/style.css">
  <script type="module" src="js/app.js"></script>

NEVER write:
  src/main.js              ← WRONG, preview cannot serve src/
  ../src/anything          ← WRONG, breaks the preview entirely
  <script src="../src/..."> ← WRONG

No build step needed. Files in public/ go straight to the preview.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WINDOWS COMMANDS — THIS RUNS ON WINDOWS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- "dir" not "ls", "dir /B" for just filenames
- "type file.txt" not "cat file.txt"
- "findstr" not "grep"
- "xcopy /E /Y src\\ dest\\" not "cp -r"
- "rmdir /s /q dir" not "rm -rf"
- NEVER use "mkdir -p" — just use write_file (it creates dirs automatically)
- Run in subdirectory: "cd <dir> && <command>"
- npm create vite is INTERACTIVE and will time out — scaffold manually instead:
  Write package.json, tsconfig.json, vite.config.ts, index.html, src/ files by hand

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GAME QUALITY — NON-NEGOTIABLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For games: NEVER use DOM elements for game objects — use Canvas2D or Three.js/PixiJS.
- requestAnimationFrame game loop with delta-time — NEVER setTimeout for rendering
- Particle system: minimum 200 simultaneous particles with object pooling
- Smooth 60fps: all movement is delta * speed, never frame-count dependent
- Visual polish: ctx.shadowBlur glow on everything, gradients, alpha compositing layers
- Camera shake on impact, screen flash on death/hit
- Sound: Web Audio API oscillators for SFX — no external audio files needed
- HUD: drawn on canvas, not DOM — health bars, score, wave counter, all canvas
- Background: layered parallax or animated shader-style effect, never a plain color
- Before finishing: ask "Would someone screenshot this and share it?" — if NO, add more polish
- Self-check: particles ✓, glow ✓, animations ✓, sounds ✓, game-over screen ✓

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3D SCROLL WEBSITE MODE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When the tech spec includes gsap AND ScrollTrigger AND lenis — you are building a
scroll-driven 3D website. NOT a game. Completely different rules:

MANDATORY FILE STRUCTURE (no Vite, no build step, pure vanilla in public/):
  public/index.html        — importmap + semantic HTML sections
  public/css/style.css     — all styles including section layouts
  public/js/main.js        — Lenis + GSAP bootstrap + Three.js renderer init
  public/js/scene.js       — Three.js scene, camera, lights, 3D objects
  public/js/animations.js  — all GSAP ScrollTrigger timelines

HTML SKELETON — always use this structure:
  <!DOCTYPE html><html lang="en"><head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><!-- from brief --></title>
    <link rel="stylesheet" href="css/style.css">
    <script type="importmap">{"imports":{
      "three":"https://esm.sh/three@0.165.0",
      "three/addons/":"https://esm.sh/three@0.165.0/examples/jsm/",
      "gsap":"https://esm.sh/gsap@3.12.5",
      "gsap/ScrollTrigger":"https://esm.sh/gsap@3.12.5/ScrollTrigger.js",
      "lenis":"https://esm.sh/lenis@1.1.13"
    }}</script>
  </head><body>
    <canvas id="webgl"></canvas>
    <main id="content">
      <section id="hero" class="section"><!-- hero content --></section>
      <section id="about" class="section"><!-- about content --></section>
      <section id="features" class="section"><!-- features --></section>
      <section id="cta" class="section"><!-- CTA --></section>
    </main>
    <script type="module" src="js/main.js"></script>
  </body></html>

CSS BASELINE — always include in style.css:
  *,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
  html{overflow-x:hidden;scroll-behavior:auto} /* Lenis handles smooth scroll */
  body{background:#080810;color:#fff;font-family:system-ui,sans-serif}
  #webgl{position:fixed;top:0;left:0;width:100%;height:100vh;z-index:0;pointer-events:none}
  #content{position:relative;z-index:1}
  .section{min-height:100vh;display:flex;flex-direction:column;
           justify-content:center;padding:0 8vw;position:relative}
  h1{font-size:clamp(3rem,8vw,7rem);line-height:1.05;letter-spacing:-0.02em;font-weight:800}
  h2{font-size:clamp(2rem,5vw,4.5rem);line-height:1.1;letter-spacing:-0.01em;font-weight:700}
  p{font-size:clamp(1rem,1.5vw,1.2rem);line-height:1.7;color:rgba(255,255,255,0.65);max-width:55ch}
  .reveal{opacity:0}  /* GSAP animates these in */

MAIN.JS — always exactly this bootstrap pattern:
  import * as THREE from 'three'
  import gsap from 'gsap'
  import ScrollTrigger from 'gsap/ScrollTrigger'
  import Lenis from 'lenis'
  import { initScene, updateScene } from './scene.js'
  import { initAnimations } from './animations.js'

  gsap.registerPlugin(ScrollTrigger)

  const lenis = new Lenis({ lerp: 0.08, duration: 1.2 })
  lenis.on('scroll', ScrollTrigger.update)
  gsap.ticker.add((time) => lenis.raf(time * 1000))
  gsap.ticker.lagSmoothing(0)

  const ctx = initScene()
  initAnimations(ctx.camera, ctx.scene)

  ;(function tick() {
    requestAnimationFrame(tick)
    updateScene(ctx)
  })()

SCENE.JS — Three.js setup + objects:
  import * as THREE from 'three'
  export function initScene() {
    const renderer = new THREE.WebGLRenderer({
      canvas: document.getElementById('webgl'), antialias:true, alpha:true
    })
    renderer.setSize(window.innerWidth, window.innerHeight)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.toneMapping = THREE.ACESFilmicToneMapping

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(60, window.innerWidth/window.innerHeight, 0.1, 100)
    camera.position.set(0, 0, 6)

    // Resize
    window.addEventListener('resize', () => {
      camera.aspect = window.innerWidth/window.innerHeight
      camera.updateProjectionMatrix()
      renderer.setSize(window.innerWidth, window.innerHeight)
    })

    // 3D objects — BUILD IMPRESSIVE ONES per the design spec
    // Examples: particles, glowing geometries, wireframes, custom shaders
    // Always add ambient + directional light
    scene.add(new THREE.AmbientLight(0xffffff, 0.4))
    const dir = new THREE.DirectionalLight(0xffffff, 2); dir.position.set(5,5,5)
    scene.add(dir)

    return { scene, camera, renderer }
  }
  export function updateScene({ scene, camera, renderer }) {
    renderer.render(scene, camera)
  }

ANIMATIONS.JS — all ScrollTrigger timelines:
  import ScrollTrigger from 'gsap/ScrollTrigger'
  import gsap from 'gsap'

  export function initAnimations(camera, scene) {
    // 1. Reveal all .reveal elements on scroll
    gsap.utils.toArray('.reveal').forEach(el => {
      gsap.to(el, {
        opacity:1, y:0, duration:1, ease:'power3.out',
        scrollTrigger:{ trigger:el, start:'top 82%', toggleActions:'play none none reverse' }
      })
    })

    // 2. Camera flythrough — ties 3D camera position to scroll progress
    gsap.to(camera.position, {
      z:3, y:0.8,
      ease:'none',
      scrollTrigger:{ trigger:'#about', start:'top bottom', end:'bottom top', scrub:1.5 }
    })

    // 3. Pinned section with scroll-driven progress
    const pin = document.getElementById('features')
    if (pin) {
      ScrollTrigger.create({
        trigger: pin, start:'top top', end:'+=120%', pin:true, pinSpacing:true,
        onUpdate: self => {
          // Drive 3D animations by self.progress (0→1)
          const obj = scene.getObjectByName('feature-mesh')
          if (obj) obj.rotation.y = self.progress * Math.PI * 2
        }
      })
    }
  }

3D OBJECTS — must be visually stunning. Always choose from:
- Particle cloud: Float32BufferAttribute positions, THREE.Points, custom ShaderMaterial with size attenuation
- Icosahedron/TorusKnot with MeshStandardMaterial, emissive glow, rotate in render loop
- Wireframe sphere that morphs: SphereGeometry + WireframeGeometry, animate vertex positions
- Background gradient via PlaneGeometry + ShaderMaterial with uTime uniform
- Bloom: import EffectComposer, RenderPass, UnrealBloomPass from three/addons/

SCROLL-REACTIVE 3D (examples to follow):
  // Object follows scroll position
  ScrollTrigger.create({
    trigger:'#hero', start:'top top', end:'bottom top', scrub:true,
    onUpdate: self => {
      const mesh = scene.getObjectByName('hero-obj')
      if(mesh){
        mesh.rotation.y = self.progress * Math.PI
        mesh.position.y = self.progress * -1.5
      }
    }
  })

TYPOGRAPHY RULES for scroll sites:
- All headings get class="reveal" for GSAP entrance animations
- Use CSS gradient text for hero: background:linear-gradient(135deg,#a855f7,#3b82f6);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent
- Stagger paragraph words using span.word wrappers animated with gsap.from(words,{stagger:0.03})
- Navigation: fixed top, backdrop-filter:blur(20px), transparent background

QUALITY BAR (would an Awwwards jury shortlist this?):
- Minimum 3 scroll-triggered animation sequences
- At least 1 pinned section with scroll progress driving 3D
- Three.js background reacts to scroll (camera moves + objects animate)
- Hero section must have a large 3D object prominently featured
- Smooth scroll via Lenis feels buttery — never jerky
- Color palette: dark background (#080810 or similar) + 2 vivid accent colors
- Glassmorphism cards: backdrop-filter:blur(16px), border:1px solid rgba(255,255,255,0.1)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NON-NEGOTIABLE EXIT CONDITION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You MUST NOT stop until public/index.html exists in the workspace root public/ directory.
If the build fails, fix the error and rebuild. If TypeScript errors block the build,
change the build script to "vite build" and rebuild. Keep going until the file exists.
Run "dir public /B 2>&1" to verify. If you see index.html — you're done.
"""


async def developer_node(state: CompanyState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"]["session"]
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "builder", "status": "working"})
    await _push_sys(emit, f"💻 Developer — building cycle {state['cycle']} feature")

    ceo_decision = read_file(workspace, "docs/feature-priority.md")
    tech_spec = read_file(workspace, "docs/technical-spec.md")
    design_spec = read_file(workspace, "docs/design-spec.md")
    all_files = list_files(workspace)

    existing_code_ctx = _build_code_context(workspace, all_files)

    # Pass most recent spec content — older cycles already exist as code in the workspace
    tech_ctx = tech_spec[-3000:].lstrip() if tech_spec and not tech_spec.startswith("(file") else "Use best judgment"
    design_ctx = design_spec[-2000:].lstrip() if design_spec and not design_spec.startswith("(file") else "Dark neon theme, professional"

    user_msg = f"""Company: {state['brief']}
Type: {state['company_type']}
Cycle: {state['cycle']}

CEO DECISION:
{ceo_decision}

TECHNICAL SPEC (most recent — do NOT read this file again):
...{tech_ctx}

DESIGN SPEC (most recent — do NOT read this file again):
...{design_ctx}

FILES ALREADY IN WORKSPACE:
{json.dumps([f['path'] for f in all_files], indent=2) if all_files else '[]'}

{existing_code_ctx}

All context is above. DO NOT call read_file for any docs/ file.
Start with list_files() then write_file immediately.
End goal: public/index.html must exist and contain the working app."""

    async def tool_executor(name: str, inputs: dict):
        if name == "read_file":
            return read_file(workspace, inputs["path"])
        if name == "write_file":
            path = inputs["path"]
            content = inputs["content"]
            result = write_file(workspace, path, content)
            if result.get("ok"):
                await _emit_file(emit, session, path, content, "builder")
                if path.startswith("public/"):
                    await emit("preview-refresh", {"path": path, "ts": int(time.time() * 1000)})
            return json.dumps(result)
        if name == "list_files":
            return json.dumps(list_files(workspace, inputs.get("subdir", "")))
        if name == "run_command":
            timeout = min(int(inputs.get("timeout", 60)), 120)
            result = await run_command(workspace, inputs["command"], timeout=timeout)
            summary = []
            if result["stdout"]:
                summary.append(f"STDOUT:\n{result['stdout'][:3000]}")
            if result["stderr"] and result["stderr"].strip():
                summary.append(f"STDERR:\n{result['stderr'][:1000]}")
            summary.append(f"Exit code: {result['returncode']}")
            return "\n".join(summary) or "Command completed"
        if name == "web_search":
            return web_search(inputs["query"])
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_DEV_SYSTEM,
        user_message=user_msg,
        tools=DEV_TOOLS,
        tool_executor=tool_executor,
        emit=emit,
        agent_id="builder",
        api_key=state["api_key"],
        max_tokens=16000,
        max_iterations=35,
        session=session,
    )

    await emit("agent-status", {"agentId": "builder", "status": "idle"})
    await _push_sys(emit, f"✅ Developer done — cycle {state['cycle']} shipped")

    return {"total_tokens": session.get("tokens", 0)}


def _build_code_context(workspace: str, all_files: list) -> str:
    """Compact view of key existing files so developer knows current state."""
    priority_paths = [
        "public/index.html", "public/app.js", "public/style.css",
        "public/js/engine.js", "public/js/game.js", "public/js/ui.js",
        "api/server.js", "api/main.py",
    ]
    # Also include any public/js/*.js files found in workspace
    extra = [f["path"] for f in all_files if f["path"].startswith("public/js/") and f["path"] not in priority_paths]
    lines = []
    for path in priority_paths + extra:
        if any(f["path"] == path for f in all_files):
            content = read_file(workspace, path)
            if content and not content.startswith("(file"):
                snippet = content[:600] + ("…" if len(content) > 600 else "")
                lines.append(f"\n=== {path} (existing) ===\n{snippet}")
    return "\n".join(lines) if lines else ""


async def _push_sys(emit, message):
    await emit("new-message", {
        "from": "system", "to": None, "type": "system",
        "message": message, "id": int(time.time() * 1000), "timestamp": int(time.time() * 1000),
    })


async def _emit_file(emit, session, path, content, agent_id):
    lines = content.count("\n") + 1
    entry = {"path": path, "content": content, "agentId": agent_id,
             "ts": int(time.time() * 1000), "lines": lines}
    files = session.get("files", [])
    idx = next((i for i, f in enumerate(files) if f["path"] == path), -1)
    if idx >= 0:
        files[idx] = entry
    else:
        files.append(entry)
    session["files"] = files
    await emit("new-file", entry)
