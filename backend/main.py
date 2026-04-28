"""
WarRoom v2 — Python/FastAPI Backend
Real agentic system: agents with tools, loops, code execution.
Replaces server.js entirely. Run with: python main.py
"""
import asyncio
import base64
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# Windows: ProactorEventLoop required for subprocess support
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# ── Paths ────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent
ROOT_DIR    = BACKEND_DIR.parent
PUBLIC_DIR  = ROOT_DIR / "public"
WORKSPACE_DIR = ROOT_DIR / "workspace"
WORKSPACE_DIR.mkdir(exist_ok=True)

# ── Session (single active session model) ────────────────────────────────────
_session: dict = {
    "running": False,
    "paused": False,
    "speed": 1.0,
    "session_id": None,
    "workspace_dir": None,
    "brief": "",
    "category": "tech-startup",
    "provider": "anthropic",
    "api_key": "",
    "tokens": 0,
    "start_time": None,
    "files": [],
    "cycle": 0,
    "task": None,
}

# ── SSE broadcast — all connected clients get every event ────────────────────
# Each connected /api/stream client has its own queue in this list.
_sse_clients: list[asyncio.Queue] = []

async def _emit(event_type: str, data: dict):
    """Broadcast an event to every connected SSE client."""
    dead = []
    for q in _sse_clients:
        try:
            q.put_nowait({"type": event_type, "data": data})
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _sse_clients.remove(q)
        except ValueError:
            pass

async def _push_sys(message: str, to: str | None = None):
    await _emit("new-message", {
        "from": "system", "to": to, "type": "system",
        "message": message,
        "id": int(time.time() * 1000),
        "timestamp": int(time.time() * 1000),
    })

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="WarRoom v2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# ── Preview endpoints ─────────────────────────────────────────────────────────

_LOADING_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#07090f;color:#00e676;font-family:'Share Tech Mono','Courier New',monospace;
     display:flex;align-items:center;justify-content:center;height:100vh}}
.w{{text-align:center}}
.ic{{font-size:2.5rem;margin-bottom:1.2rem;animation:pulse 2s ease-in-out infinite}}
.tt{{font-size:.95rem;letter-spacing:.15em;margin-bottom:1.5rem}}
.bt{{width:220px;height:2px;background:#0d1420;margin:0 auto .75rem}}
.bf{{height:100%;background:#00e676;animation:ld 2.5s ease-in-out infinite;transform-origin:left}}
.sb{{font-size:.62rem;color:#2d4a3a;letter-spacing:.1em}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
@keyframes ld{{0%{{width:0}}60%{{width:85%}}100%{{width:100%}}}}
</style></head><body><div class="w">
<div class="ic">⚡</div><div class="tt">AGENTS DEPLOYING...</div>
<div class="bt"><div class="bf"></div></div>
<div class="sb">{subtitle}</div>
</div><script>setTimeout(()=>location.reload(),3000)</script></body></html>"""


def _normalize_preview_path(raw_path: str) -> str:
    """
    Resolve a path written in public/index.html to the correct preview URL.
    '../src/main.js' → public/../src/main.js → src/main.js → /preview-ws/src/main.js
    'app.js'         → public/app.js          → public/app.js → /preview/app.js
    """
    import os as _os
    normalized = _os.path.normpath(_os.path.join("public", raw_path)).replace("\\", "/")
    if normalized.startswith("public/"):
        return "/preview/" + normalized[7:]
    return "/preview-ws/" + normalized


def _rewrite_preview_src(m: re.Match) -> str:
    attr, path, quote = m.group(1), m.group(2), m.group(3)
    return attr + _normalize_preview_path(path) + quote


_PREVIEW_MIME = {
    ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
    ".css": "text/css", ".json": "application/json", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
    ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
    ".ico": "image/x-icon", ".webp": "image/webp",
    ".glb": "model/gltf-binary", ".gltf": "model/gltf+json",
    ".bin": "application/octet-stream", ".ktx2": "image/ktx2",
    ".hdr": "image/vnd.radiance", ".exr": "image/x-exr",
    ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav",
}

# File extensions a running game might fetch at runtime (data, models, audio,
# textures). Used by the catch-all to fall through to the active session's
# public/ when fetch('/asset-manifest.json') etc. miss the warroom's own public/.
_RUNTIME_DATA_EXTS = {
    ".json", ".glb", ".gltf", ".bin", ".ktx2",
    ".png", ".jpg", ".jpeg", ".webp", ".svg",
    ".hdr", ".exr", ".ogg", ".mp3", ".wav",
}


@app.get("/preview-now")
async def preview_now():
    ws = _session.get("workspace_dir")
    if not ws:
        return HTMLResponse(_LOADING_HTML.format(subtitle="AWAITING MISSION BRIEF"))

    index = Path(ws) / "public" / "index.html"
    if not index.exists():
        return HTMLResponse(_LOADING_HTML.format(subtitle="CYCLE 1 IN PROGRESS"))

    html = index.read_text(encoding="utf-8", errors="replace")
    # Rewrite relative paths — handles both same-dir and ../ escapes
    html = re.sub(
        r'((?:src|href)=["\'])(?!https?:|//|/|data:|#)([^"\']*?)(["\'])',
        _rewrite_preview_src,
        html, flags=re.IGNORECASE,
    )
    # Rewrite absolute /assets/ paths (Vite default base="/")
    html = html.replace('="/assets/', '="/preview/assets/')
    html = html.replace("='/assets/", "='/preview/assets/")
    reload = "<script>if(window.self!==window.top){setTimeout(function(){location.reload()},5000)}</script>"
    html = html.replace("</body>", reload + "</body>") if "</body>" in html else html + reload
    return HTMLResponse(html)


@app.get("/preview/{file_path:path}")
async def preview_file(file_path: str):
    ws = _session.get("workspace_dir")
    if not ws:
        raise HTTPException(404, "No active session")
    ws_pub = (Path(ws) / "public").resolve()
    full = (ws_pub / file_path).resolve()
    if not str(full).startswith(str(ws_pub)):
        raise HTTPException(403, "Forbidden")
    if not full.exists():
        raise HTTPException(404, f"Not found: {file_path}")
    mime = _PREVIEW_MIME.get(full.suffix.lower(), "text/plain")
    return Response(content=full.read_bytes(), media_type=mime)


@app.get("/preview-ws/{file_path:path}")
async def preview_ws_file(file_path: str):
    """Serve workspace-root files (e.g. src/main.js referenced via ../src/main.js)."""
    ws = _session.get("workspace_dir")
    if not ws:
        raise HTTPException(404, "No active session")
    ws_root = Path(ws).resolve()
    full = (ws_root / file_path).resolve()
    if not str(full).startswith(str(ws_root)):
        raise HTTPException(403, "Forbidden")
    if not full.exists():
        raise HTTPException(404, f"Not found: {file_path}")
    mime = _PREVIEW_MIME.get(full.suffix.lower(), "text/plain")
    return Response(content=full.read_bytes(), media_type=mime)


# ── SSE Stream ────────────────────────────────────────────────────────────────

@app.get("/api/stream")
async def stream(request: Request):
    # Each client gets its own queue — _emit broadcasts to all of them
    client_q: asyncio.Queue = asyncio.Queue(maxsize=2000)
    _sse_clients.append(client_q)

    async def generator():
        try:
            # Send current state immediately on connect
            yield {
                "event": "state",
                "data": json.dumps({
                    "running": _session["running"],
                    "paused": _session["paused"],
                    "speed": _session["speed"],
                    "tokens": _session["tokens"],
                    "startTime": _session["start_time"],
                    "files": _session["files"],
                    "brief": _session["brief"],
                    "cycle": _session["cycle"],
                }),
            }

            # Stream events until disconnected or sentinel
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(client_q.get(), timeout=15.0)
                    if event is None:
                        break
                    yield {"event": event["type"], "data": json.dumps(event["data"])}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            try:
                _sse_clients.remove(client_q)
            except ValueError:
                pass

    return EventSourceResponse(generator())


# ── Status ────────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def status():
    return {
        "running": _session["running"],
        "brief": _session["brief"],
        "tokens": _session["tokens"],
        "category": _session["category"],
        "agents": ["ceo", "lead-eng", "designer", "builder", "qa", "sales"],
    }


# ── Start Live ────────────────────────────────────────────────────────────────

class StartLiveRequest(BaseModel):
    brief: str
    agents: Optional[list] = None
    category: Optional[str] = "tech-startup"
    provider: Optional[str] = "anthropic"
    apiKey: str


@app.post("/api/start-live")
async def start_live(body: StartLiveRequest):
    from graph.graph import build_graph
    from graph.state import make_initial_state

    # Cancel any running session
    if _session.get("task") and not _session["task"].done():
        _session["task"].cancel()
        await asyncio.sleep(0.2)

    session_id = str(int(time.time() * 1000))
    ws_dir = str(WORKSPACE_DIR / session_id)
    for d in ["docs", "public", "logs", "api"]:
        Path(ws_dir, d).mkdir(parents=True, exist_ok=True)

    _session.update(
        running=True, paused=False, speed=1.0,
        session_id=session_id, workspace_dir=ws_dir,
        brief=body.brief, category=body.category or "tech-startup",
        provider=body.provider or "anthropic", api_key=body.apiKey,
        tokens=0, start_time=int(time.time() * 1000),
        files=[], cycle=0,
    )

    graph = build_graph()
    initial_state = make_initial_state(
        session_id=session_id,
        workspace_dir=ws_dir,
        brief=body.brief,
        company_type=body.category or "tech-startup",
        provider=body.provider or "anthropic",
        api_key=body.apiKey,
    )

    config = {
        "recursion_limit": 150,
        "configurable": {
            "thread_id": session_id,
            "emit": _emit,
            "session": _session,
        }
    }

    task = asyncio.create_task(_run_graph(graph, initial_state, config))
    _session["task"] = task

    return {"ok": True, "sessionId": session_id}


async def _run_graph(graph, initial_state: dict, config: dict):
    """Run the LangGraph pipeline with countdown and error handling."""
    try:
        # Countdown
        for i in [3, 2, 1]:
            await _emit("countdown", {"count": i})
            await asyncio.sleep(1)

        await _emit("live-start", {"startTime": _session["start_time"]})
        await _push_sys("🟢 WARROOM v2 ONLINE — Real agentic pipeline starting")

        # Mark all agents idle
        for aid in ["ceo", "lead-eng", "designer", "builder", "qa"]:
            await _emit("agent-status", {"agentId": aid, "status": "idle"})

        # Run the graph — it loops until CEO says DONE
        async for chunk in graph.astream(initial_state, config=config):
            # Update cycle in session from state
            for node_name, state_update in chunk.items():
                if isinstance(state_update, dict) and "cycle" in state_update:
                    _session["cycle"] = state_update["cycle"]

        await _push_sys("🏁 Pipeline complete — company shipped!")
        await _emit("stopped", {})

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        import traceback
        traceback.print_exc()
        await _push_sys(f"⚠️ Pipeline error: {str(exc)[:200]}")
        await _emit("error", {"message": str(exc)})
    finally:
        _session["running"] = False


# ── Control endpoints ──────────────────────────────────────────────────────────

class ContinueRequest(BaseModel):
    apiKey: str
    feedback: Optional[str] = None


@app.post("/api/continue")
async def continue_session(body: ContinueRequest):
    """Resume the last completed session from where it left off."""
    from graph.graph import build_graph
    from tools.file_ops import read_file as _read_file

    from tools.file_ops import write_file as _write_file
    ws_dir = _session.get("workspace_dir")
    if not ws_dir or not Path(ws_dir).exists():
        raise HTTPException(400, "No session to continue — workspace not found")

    # Write feedback to file so CEO picks it up
    if body.feedback and body.feedback.strip():
        _write_file(ws_dir, "docs/customer-feedback.md", f"# Customer Feedback\n\n{body.feedback.strip()}\n")

    if _session.get("task") and not _session["task"].done():
        raise HTTPException(400, "Session already running")

    # Detect current cycle from feature-priority.md
    fp = _read_file(ws_dir, "docs/feature-priority.md") or ""
    import re as _re
    m = _re.search(r"Cycle\s+(\d+)", fp)
    current_cycle = int(m.group(1)) if m else _session.get("cycle", 1)

    _session.update(
        running=True, paused=False, speed=1.0,
        api_key=body.apiKey,
        tokens=0,
        start_time=int(time.time() * 1000),
    )

    from graph.state import CompanyState
    resume_state = CompanyState(
        session_id=_session["session_id"],
        workspace_dir=ws_dir,
        provider=_session.get("provider", "anthropic"),
        api_key=body.apiKey,
        brief=_session["brief"],
        company_type=_session.get("category", "tech-startup"),
        cycle=current_cycle,
        ceo_decision=fp,
        tech_spec=_read_file(ws_dir, "docs/technical-spec.md") or "",
        design_spec=_read_file(ws_dir, "docs/design-spec.md") or "",
        qa_report=_read_file(ws_dir, "docs/qa-report.md") or "",
        past_decisions=[f"Cycle {current_cycle}: {fp[:120]}"],
        is_done=False,
        founder_override=None,
        total_tokens=0,
    )

    graph = build_graph()
    config = {
        "recursion_limit": 150,
        "configurable": {
            "thread_id": _session["session_id"] + "-cont",
            "emit": _emit,
            "session": _session,
        }
    }

    task = asyncio.create_task(_run_graph(graph, resume_state, config))
    _session["task"] = task

    return {"ok": True, "fromCycle": current_cycle}


@app.post("/api/stop")
async def stop():
    if _session.get("task") and not _session["task"].done():
        _session["task"].cancel()
    # Preserve workspace_dir and brief so /api/continue works after stop
    _session["running"] = False
    await _emit("stopped", {})
    return {"ok": True}


@app.post("/api/reset")
async def reset():
    """Full reset — clears workspace and returns to phase 1."""
    if _session.get("task") and not _session["task"].done():
        _session["task"].cancel()
    _session.update(running=False, workspace_dir=None, brief="", session_id=None)
    await _emit("stopped", {})
    return {"ok": True}


@app.post("/api/pause")
async def pause():
    _session["paused"] = True
    await _emit("paused", {})
    return {"ok": True}


@app.post("/api/resume")
async def resume():
    _session["paused"] = False
    await _emit("resumed", {})
    return {"ok": True}


class SpeedRequest(BaseModel):
    multiplier: float = 1.0

@app.post("/api/speed")
async def set_speed(body: SpeedRequest):
    _session["speed"] = body.multiplier
    await _emit("speed-change", {"speed": body.multiplier})
    return {"ok": True}


class MessageRequest(BaseModel):
    message: str

@app.post("/api/customer-feedback")
async def customer_feedback(body: MessageRequest):
    from tools.file_ops import write_file as _write_file
    text = body.message.strip()[:400]
    await _emit("customer-feedback", {"message": text})
    await _push_sys(f"👤 CUSTOMER: {text}", to="ceo")
    # Write to workspace so CEO picks it up next cycle
    ws = _session.get("workspace_dir")
    if ws:
        _write_file(ws, "docs/customer-feedback.md", f"# Customer Feedback\n\n{text}\n")
    return {"ok": True}


_CRISES = [
    "🚨 Competitor just launched an identical product with $10M in VC funding!",
    "🔥 PRODUCTION IS DOWN — 500 errors, all users affected. Fix NOW.",
    "💔 Our top enterprise client just churned — $60k ARR gone overnight.",
    "📰 TechCrunch published a negative piece on our data privacy practices.",
    "💸 Runway is 6 weeks. Investor meeting fell through this morning.",
    "⚠️ Critical SQL injection vulnerability found in our auth system.",
    "🎯 Y Combinator just reached out — application deadline in 24 hours!",
    "📉 App Store removed our app for guideline violation.",
]

@app.post("/api/inject-crisis")
async def inject_crisis():
    crisis = random.choice(_CRISES)
    await _emit("crisis", {"message": crisis})
    await _push_sys(f"🚨 CRISIS: {crisis}", to="ceo")
    return {"ok": True, "crisis": crisis}


@app.post("/api/console-errors")
async def console_errors(body: dict):
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# BLENDER STUDIO PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

# Per-session state for the Blender pipeline (one active session at a time)
_blender_session: dict = {
    "running": False,
    "session_id": None,
    "workspace_dir": None,
    "video_path": None,
    "latest_render": None,
    "tokens": 0,
    "task": None,
    "paused": False,
}


class BlenderStartRequest(BaseModel):
    productDescription: str
    style: Optional[str] = "commercial"
    imageBase64: Optional[str] = None   # base64-encoded product image (PNG/JPEG)
    apiKey: str


@app.post("/api/blender/start")
async def blender_start(body: BlenderStartRequest):
    """Start the Blender Studio pipeline for a product."""
    from graph.blender_graph import build_blender_graph
    from graph.blender_state import make_blender_state

    # Cancel any running blender task
    if _blender_session.get("task") and not _blender_session["task"].done():
        _blender_session["task"].cancel()
        await asyncio.sleep(0.2)

    session_id = f"blender_{int(time.time() * 1000)}"
    ws_dir = str(WORKSPACE_DIR / session_id)

    # Create workspace subdirectories
    for subdir in ["docs", "renders", "frames", "logs"]:
        Path(ws_dir, subdir).mkdir(parents=True, exist_ok=True)

    # Save uploaded product image if provided
    product_image_path: Optional[str] = None
    if body.imageBase64:
        try:
            image_bytes = base64.b64decode(body.imageBase64)
            product_image_path = str(Path(ws_dir) / "product_image.png")
            with open(product_image_path, "wb") as f:
                f.write(image_bytes)
        except Exception as exc:
            # Non-fatal — continue without product reference image
            await _push_sys(f"Warning: could not save product image: {exc}")
            product_image_path = None

    _blender_session.update(
        running=True,
        paused=False,
        session_id=session_id,
        workspace_dir=ws_dir,
        video_path=None,
        latest_render=None,
        tokens=0,
        task=None,
    )

    graph = build_blender_graph()
    initial_state = make_blender_state(
        session_id=session_id,
        workspace_dir=ws_dir,
        api_key=body.apiKey,
        product_description=body.productDescription,
        style=body.style or "commercial",
        product_image_path=product_image_path,
    )

    config = {
        "recursion_limit": 100,
        "configurable": {
            "thread_id": session_id,
            "emit": _emit,
            "blender_session": _blender_session,
        },
    }

    task = asyncio.create_task(_run_blender_graph(graph, initial_state, config))
    _blender_session["task"] = task

    return {"ok": True, "sessionId": session_id}


async def _run_blender_graph(graph, initial_state: dict, config: dict):
    """Run the Blender Studio LangGraph pipeline."""
    try:
        await _emit("blender-start", {
            "sessionId": _blender_session["session_id"],
            "product": initial_state.get("product_description", ""),
            "style": initial_state.get("style", "commercial"),
        })
        await _push_sys("Blender Studio pipeline starting")

        # Emit agent idle statuses
        for aid in ["director-3d", "scene-architect-3d", "blender-artist-3d", "animator-3d", "renderer-3d"]:
            await _emit("agent-status", {"agentId": aid, "status": "idle"})

        async for chunk in graph.astream(initial_state, config=config):
            for node_name, state_update in chunk.items():
                if isinstance(state_update, dict):
                    if "total_tokens" in state_update:
                        _blender_session["tokens"] = state_update["total_tokens"]
                        await _emit("token-update", {
                            "delta": 0,
                            "total": state_update["total_tokens"],
                        })
                    if "latest_render_path" in state_update and state_update["latest_render_path"]:
                        _blender_session["latest_render"] = state_update["latest_render_path"]
                    if "video_path" in state_update and state_update["video_path"]:
                        _blender_session["video_path"] = state_update["video_path"]

        await _push_sys("Blender Studio pipeline complete")
        await _emit("blender-done", {
            "sessionId": _blender_session["session_id"],
            "videoPath": _blender_session.get("video_path"),
        })

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        import traceback
        traceback.print_exc()
        await _push_sys(f"Blender pipeline error: {str(exc)[:200]}")
        await _emit("blender-error", {"message": str(exc)})
    finally:
        _blender_session["running"] = False


@app.post("/api/blender/stop")
async def blender_stop():
    """Cancel the running Blender pipeline."""
    if _blender_session.get("task") and not _blender_session["task"].done():
        _blender_session["task"].cancel()
    _blender_session["running"] = False
    await _emit("blender-stopped", {"sessionId": _blender_session.get("session_id")})
    return {"ok": True}


@app.get("/api/blender/status")
async def blender_status():
    """Return the current Blender pipeline status."""
    return {
        "running": _blender_session["running"],
        "sessionId": _blender_session["session_id"],
        "tokens": _blender_session["tokens"],
        "latestRender": _blender_session["latest_render"],
        "videoPath": _blender_session["video_path"],
    }


@app.get("/api/blender/render/{session_id}/{filename}")
async def blender_render_file(session_id: str, filename: str):
    """
    Serve a preview render PNG from the blender session workspace.
    The Blender Artist emits URLs in this format.
    """
    # Security: only allow .png files, no path traversal
    if ".." in filename or "/" in filename or not filename.endswith(".png"):
        raise HTTPException(400, "Invalid filename")

    ws = _blender_session.get("workspace_dir")
    if not ws:
        raise HTTPException(404, "No active blender session")

    ws_path = Path(ws).resolve()
    render_path = (ws_path / "renders" / filename).resolve()

    # Path traversal check
    if not str(render_path).startswith(str(ws_path)):
        raise HTTPException(403, "Forbidden")

    if not render_path.exists():
        raise HTTPException(404, f"Render not found: {filename}")

    return Response(content=render_path.read_bytes(), media_type="image/png")


@app.get("/api/blender/video/{session_id}")
async def blender_video(session_id: str):
    """Serve the final output.mp4 for the blender session."""
    ws = _blender_session.get("workspace_dir")
    if not ws:
        raise HTTPException(404, "No active blender session")

    video_path = Path(ws) / "output.mp4"
    if not video_path.exists():
        raise HTTPException(404, "Video not ready yet")

    return Response(
        content=video_path.read_bytes(),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f"attachment; filename=\"blender_output_{session_id}.mp4\"",
            "Content-Length": str(video_path.stat().st_size),
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# GAME STUDIO PIPELINE (3D, Three.js + Vite)
# ══════════════════════════════════════════════════════════════════════════════

# Per-session state for the game pipeline (one active session at a time).
_game_session: dict = {
    "running": False,
    "session_id": None,
    "workspace_dir": None,
    "preview_url": None,
    "latest_screenshot": None,
    "tokens": 0,
    "files": [],
    "task": None,
    "paused": False,
}


class GameStartRequest(BaseModel):
    brief: str
    genre: Optional[str] = "auto"
    artStyle: Optional[str] = "stylized"
    target: Optional[str] = "web"
    apiKey: str


@app.post("/api/game/start")
async def game_start(body: GameStartRequest):
    """Start the 3D Game Studio pipeline (with sqlite checkpointing)."""
    from graph.game_state import make_game_state

    if _game_session.get("task") and not _game_session["task"].done():
        _game_session["task"].cancel()
        await asyncio.sleep(0.2)

    session_id = f"game_{int(time.time() * 1000)}"
    ws_dir = str(WORKSPACE_DIR / session_id)
    for sub in ["docs", "docs/levels", "renders", "logs", "public"]:
        Path(ws_dir, sub).mkdir(parents=True, exist_ok=True)

    _game_session.update(
        running=True, paused=False,
        session_id=session_id, workspace_dir=ws_dir,
        preview_url=None, latest_screenshot=None,
        tokens=0, files=[], task=None,
        brief=body.brief, genre=body.genre or "auto",
        art_style=body.artStyle or "stylized",
        # Save api_key alongside the session so resume-after-restart works
        # without the user re-entering it. Kept inside the per-session
        # workspace; never returned by listing endpoints.
        api_key=body.apiKey,
    )

    initial_state = make_game_state(
        session_id=session_id,
        workspace_dir=ws_dir,
        api_key=body.apiKey,
        brief=body.brief,
        genre=body.genre or "auto",
        art_style=body.artStyle or "stylized",
        target=body.target or "web",
    )

    config = {
        "recursion_limit": 120,
        "configurable": {
            "thread_id": session_id,
            "emit": _emit,
            "game_session": _game_session,
        },
    }

    task = asyncio.create_task(_run_game_graph(initial_state, config, ws_dir))
    _game_session["task"] = task

    return {"ok": True, "sessionId": session_id}


async def _run_game_graph(initial_state: dict, config: dict, workspace_dir: str, resuming: bool = False):
    """Drive the Game Studio LangGraph and emit progress over SSE.

    Wraps the run inside an AsyncSqliteSaver context — every node
    completion checkpoints to <workspace>/checkpoint.db. Pass
    `resuming=True` to continue from the existing checkpoint (initial_state
    is ignored in that case; LangGraph resumes from the last persisted node).
    """
    from graph.checkpointer import open_checkpointer
    from graph.game_graph import build_game_graph
    from tools.session_persist import save_session

    try:
        async with open_checkpointer(workspace_dir) as saver:
            graph = build_game_graph(checkpointer=saver)

            event_name = "game-resumed" if resuming else "game-start"
            await _emit(event_name, {
                "sessionId": _game_session["session_id"],
                "brief": (initial_state or {}).get("brief", _game_session.get("brief", "")),
                "genre": (initial_state or {}).get("genre", _game_session.get("genre", "auto")),
            })
            await _push_sys("Game Studio pipeline " + ("resuming from checkpoint" if resuming else "starting"))

            for aid in [
                "game-director", "level-designer", "asset-lead",
                "engine-engineer", "tech-art", "gameplay-programmer",
                "vision-playtester",
            ]:
                await _emit("agent-status", {"agentId": aid, "status": "idle"})

            # Persist current session state up-front so a paused-pre-first-node
            # session is resumable.
            save_session(workspace_dir, _game_session)

            # `astream(None, config=...)` is LangGraph's idiom for "continue
            # from last checkpoint without seeding new state".
            stream_input = None if resuming else initial_state

            async for chunk in graph.astream(stream_input, config=config):
                for node_name, state_update in chunk.items():
                    if not isinstance(state_update, dict):
                        continue
                    if "total_tokens" in state_update:
                        _game_session["tokens"] = state_update["total_tokens"]
                        await _emit("token-update", {"delta": 0, "total": state_update["total_tokens"]})
                    if state_update.get("latest_screenshot"):
                        _game_session["latest_screenshot"] = state_update["latest_screenshot"]
                    if state_update.get("preview_url"):
                        _game_session["preview_url"] = state_update["preview_url"]
                # Persist after every node so a crash mid-graph doesn't lose
                # the file tree / token totals the UI displays on resume.
                save_session(workspace_dir, _game_session)

            await _push_sys("Game Studio pipeline complete — playable build ready")
            await _emit("game-done", {
                "sessionId": _game_session["session_id"],
                "previewUrl": _game_session.get("preview_url"),
            })
            # Mark the session as finished but keep session.json on disk.
            _game_session["running"] = False
            _game_session["paused"] = False
            _game_session["completed"] = True
            save_session(workspace_dir, _game_session)
    except asyncio.CancelledError:
        # Persist on cancel so the session can still be resumed.
        try: save_session(workspace_dir, _game_session)
        except Exception: pass
    except Exception as exc:
        import traceback
        traceback.print_exc()
        await _push_sys(f"Game pipeline error: {str(exc)[:200]}")
        await _emit("game-error", {"message": str(exc)})
        try: save_session(workspace_dir, _game_session)
        except Exception: pass
    finally:
        _game_session["running"] = False


@app.post("/api/game/pause")
async def game_pause():
    """Pause the agents.

    Effect: each agent loop spins on `session.paused` until cleared. The
    in-flight LLM call (if any) finishes — pause never drops a billed
    response. The session is persisted so the user can close the browser
    or even the server and resume later via /api/game/resume.
    """
    from tools.session_persist import mark_paused
    ws = _game_session.get("workspace_dir")
    if not ws:
        raise HTTPException(404, "No active game session")
    mark_paused(ws, _game_session)
    await _emit("game-paused", {"sessionId": _game_session.get("session_id")})
    await _push_sys("Game Studio paused — state persisted, safe to close.")
    return {"ok": True, "sessionId": _game_session.get("session_id")}


class GameResumeRequest(BaseModel):
    sessionId: Optional[str] = None
    apiKey: Optional[str] = None


@app.post("/api/game/resume")
async def game_resume(body: GameResumeRequest):
    """Resume a paused or interrupted session.

    Three cases:
      1. The current task is alive and paused — just clear the flag.
      2. The current task is gone but the session matches — reload from
         workspace + restart the graph (LangGraph picks up at the last
         completed node via the sqlite checkpoint).
      3. A specific sessionId is requested — switch to that workspace and
         resume it.
    """
    from tools.session_persist import load_session, mark_resumed, list_sessions
    from graph.game_state import make_game_state

    # Case 1 — current task is paused, just unpause.
    if (
        _game_session.get("task") and not _game_session["task"].done()
        and _game_session.get("paused")
        and (not body.sessionId or body.sessionId == _game_session.get("session_id"))
    ):
        ws = _game_session.get("workspace_dir")
        if ws: mark_resumed(ws, _game_session)
        await _emit("game-resumed", {"sessionId": _game_session.get("session_id"), "mode": "live"})
        await _push_sys("Game Studio resumed (live).")
        return {"ok": True, "mode": "live", "sessionId": _game_session.get("session_id")}

    # Case 2/3 — resume from disk.
    target_id = body.sessionId
    if not target_id:
        # Pick the newest paused-or-incomplete session.
        candidates = list_sessions(str(WORKSPACE_DIR), prefix="game_")
        candidates = [s for s in candidates if not s.get("completed")]
        if not candidates:
            raise HTTPException(404, "No paused or incomplete session found")
        target_id = candidates[0]["session_id"]

    ws_dir = str(WORKSPACE_DIR / target_id)
    if not Path(ws_dir).exists():
        raise HTTPException(404, f"Workspace gone for {target_id}")
    saved = load_session(ws_dir)
    if not saved:
        raise HTTPException(404, f"session.json missing for {target_id}")

    api_key = body.apiKey or saved.get("api_key")
    if not api_key:
        raise HTTPException(400, "apiKey required to resume — none persisted")

    # Cancel anything else in flight.
    if _game_session.get("task") and not _game_session["task"].done():
        _game_session["task"].cancel()
        await asyncio.sleep(0.2)

    # Restore the in-memory session from disk.
    _game_session.update(
        running=True, paused=False, completed=False,
        session_id=target_id, workspace_dir=ws_dir,
        preview_url=saved.get("preview_url"),
        latest_screenshot=saved.get("latest_screenshot"),
        tokens=saved.get("tokens", 0),
        files=saved.get("files", []),
        brief=saved.get("brief", ""),
        genre=saved.get("genre", "auto"),
        art_style=saved.get("art_style", "stylized"),
        api_key=api_key,
        task=None,
    )

    # Replay the persisted file tree to any connected SSE client so the UI
    # rehydrates on resume.
    for f in saved.get("files", []):
        try: await _emit("new-file", f)
        except Exception: pass

    config = {
        "recursion_limit": 120,
        "configurable": {
            "thread_id": target_id,
            "emit": _emit,
            "game_session": _game_session,
        },
    }
    # initial_state is ignored when resuming from a checkpoint, but we pass
    # one anyway to satisfy the type signature.
    initial_state = make_game_state(
        session_id=target_id,
        workspace_dir=ws_dir,
        api_key=api_key,
        brief=saved.get("brief", ""),
        genre=saved.get("genre", "auto"),
        art_style=saved.get("art_style", "stylized"),
    )

    task = asyncio.create_task(_run_game_graph(initial_state, config, ws_dir, resuming=True))
    _game_session["task"] = task
    return {"ok": True, "mode": "restored", "sessionId": target_id}


@app.post("/api/game/stop")
async def game_stop():
    """Stop the current session permanently. Use /api/game/pause if you want to resume later."""
    from tools.session_persist import save_session
    if _game_session.get("task") and not _game_session["task"].done():
        _game_session["task"].cancel()
    _game_session["running"] = False
    _game_session["paused"] = False
    _game_session["completed"] = True
    ws = _game_session.get("workspace_dir")
    if ws:
        try: save_session(ws, _game_session)
        except Exception: pass
    await _emit("game-stopped", {"sessionId": _game_session.get("session_id")})
    return {"ok": True}


@app.get("/api/game/sessions")
async def game_sessions():
    """List recent persisted sessions (paused or completed) for resume UI."""
    from tools.session_persist import list_sessions
    out = list_sessions(str(WORKSPACE_DIR), prefix="game_")
    # Strip secrets before returning.
    safe = []
    for s in out:
        s = dict(s)
        s.pop("api_key", None)
        # Limit files payload — UI only needs counts here.
        files = s.pop("files", [])
        s["file_count"] = len(files)
        safe.append(s)
    return {"sessions": safe, "current": _game_session.get("session_id")}


@app.get("/api/game/status")
async def game_status():
    return {
        "running": _game_session["running"],
        "paused":  _game_session.get("paused", False),
        "completed": _game_session.get("completed", False),
        "sessionId": _game_session["session_id"],
        "tokens": _game_session["tokens"],
        "previewUrl": _game_session.get("preview_url"),
        "latestScreenshot": _game_session.get("latest_screenshot"),
    }


@app.get("/api/game/screenshot/{session_id}/{filename}")
async def game_screenshot(session_id: str, filename: str):
    if ".." in filename or "/" in filename or not filename.endswith(".png"):
        raise HTTPException(400, "Invalid filename")
    ws = _game_session.get("workspace_dir")
    if not ws:
        raise HTTPException(404, "No active game session")
    ws_path = Path(ws).resolve()
    p = (ws_path / "renders" / filename).resolve()
    if not str(p).startswith(str(ws_path)) or not p.exists():
        raise HTTPException(404, "Screenshot not found")
    return Response(content=p.read_bytes(), media_type="image/png")


@app.get("/preview-game")
async def preview_game():
    """Serve the built game from the active game session's public/."""
    ws = _game_session.get("workspace_dir")
    if not ws:
        return HTMLResponse(_LOADING_HTML.format(subtitle="GAME STUDIO STANDING BY"))
    index = Path(ws) / "public" / "index.html"
    if not index.exists():
        return HTMLResponse(_LOADING_HTML.format(subtitle="BUILDING — VITE COMPILE IN PROGRESS"))
    html = index.read_text(encoding="utf-8", errors="replace")
    # Rewrite asset references so the iframe can resolve them under /preview-game-asset/.
    # Three cases:
    #   1. relative paths (no leading slash, scheme, etc.)
    #   2. root-absolute paths like /src/main.js — Vite's default
    #   3. /assets/* — Vite build output
    # Already-prefixed /preview-game-asset/* paths are left alone.
    html = re.sub(
        r'((?:src|href)=["\'])/(?![/])(?!preview-game-asset/|preview/|preview-ws/|api/)([^"\']*?)(["\'])',
        lambda m: m.group(1) + "/preview-game-asset/" + m.group(2) + m.group(3),
        html, flags=re.IGNORECASE,
    )
    html = re.sub(
        r'((?:src|href)=["\'])(?!https?:|//|/|data:|#)([^"\']*?)(["\'])',
        lambda m: m.group(1) + "/preview-game-asset/" + m.group(2) + m.group(3),
        html, flags=re.IGNORECASE,
    )
    reload = "<script>if(window.self!==window.top){setTimeout(function(){location.reload()},5000)}</script>"
    html = html.replace("</body>", reload + "</body>") if "</body>" in html else html + reload
    return HTMLResponse(html)


@app.get("/preview-game-asset/{file_path:path}")
async def preview_game_asset(file_path: str):
    ws = _game_session.get("workspace_dir")
    if not ws:
        raise HTTPException(404, "No active game session")
    pub = (Path(ws) / "public").resolve()
    full = (pub / file_path).resolve()
    if not str(full).startswith(str(pub)) or not full.exists():
        raise HTTPException(404, f"Not found: {file_path}")
    mime = _PREVIEW_MIME.get(full.suffix.lower(), "application/octet-stream")
    return Response(content=full.read_bytes(), media_type=mime)


@app.post("/api/preview-screenshot")
async def preview_screenshot(body: dict):
    return {"ok": True}


@app.get("/api/file")
async def get_file(path: str = ""):
    clean = path.replace("..", "").lstrip("/")
    ws = _session.get("workspace_dir")
    if not clean or not ws:
        raise HTTPException(404, "not found")
    full = Path(ws) / clean
    if not full.exists():
        raise HTTPException(404, "not found")
    return {"content": full.read_text(encoding="utf-8", errors="replace"), "path": clean}


@app.get("/api/files")
async def get_files():
    return {"files": _session.get("files", [])}


# ── Planning phase streaming (/api/run-agent) ─────────────────────────────────

class RunAgentRequest(BaseModel):
    systemPrompt: str
    context: str
    maxTokens: Optional[int] = 1000
    provider: Optional[str] = "anthropic"
    apiKey: str


@app.post("/api/run-agent")
async def run_agent_stream(body: RunAgentRequest):
    from llm_client import stream_message

    model = (
        "claude-haiku-4-5-20251001" if body.provider == "anthropic"
        else "gemini-2.0-flash"
    )

    async def generator():
        try:
            async for chunk in stream_message(
                provider=body.provider or "anthropic",
                api_key=body.apiKey,
                model=model,
                max_tokens=body.maxTokens or 1000,
                system=body.systemPrompt,
                messages=[{"role": "user", "content": body.context}],
            ):
                yield {"data": json.dumps({"type": "text", "text": chunk})}
            yield {"data": json.dumps({"type": "done"})}
        except Exception as exc:
            yield {"data": json.dumps({"type": "error", "message": str(exc)})}

    return EventSourceResponse(generator())


# ── Backend proxy (/backend/* → port 3001) ────────────────────────────────────

@app.api_route("/backend/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def backend_proxy(path: str, request: Request):
    import httpx
    try:
        url = f"http://localhost:3001/{path}"
        body_bytes = await request.body()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(
                method=request.method,
                url=url,
                content=body_bytes,
                headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )
    except Exception:
        raise HTTPException(503, "Backend service unavailable")


# ── Serve frontend static files ───────────────────────────────────────────────

_MIME = {
    ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
    ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
    ".json": "application/json", ".woff2": "font/woff2", ".woff": "font/woff",
}


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    # Don't catch API or preview routes
    if full_path.startswith(("api/", "preview", "backend/")):
        raise HTTPException(404)

    candidate = PUBLIC_DIR / full_path if full_path else PUBLIC_DIR / "index.html"
    if candidate.exists() and not candidate.is_dir():
        mime = _MIME.get(candidate.suffix.lower(), "text/plain")
        return Response(content=candidate.read_bytes(), media_type=mime)

    # If a game session is active, runtime fetches like fetch('/asset-manifest.json')
    # land here. The HTML rewriter can't see those (they happen at runtime, not in
    # markup), so fall through to the active session's public/ for known data
    # extensions. This makes generated games "just work" without per-agent path hacks.
    suffix = Path(full_path).suffix.lower()
    if suffix in _RUNTIME_DATA_EXTS and full_path:
        ws = _game_session.get("workspace_dir")
        if ws:
            ws_pub = (Path(ws) / "public").resolve()
            full = (ws_pub / full_path).resolve()
            if str(full).startswith(str(ws_pub)) and full.exists() and not full.is_dir():
                mime = _PREVIEW_MIME.get(suffix, "application/octet-stream")
                return Response(content=full.read_bytes(), media_type=mime)

    # Only fall back to index.html for extensionless paths (SPA routes).
    # A request for foo.js / foo.css that doesn't exist must 404, NOT serve HTML —
    # otherwise the browser parses HTML as JS and boots into a SyntaxError.
    if suffix and suffix != ".html":
        raise HTTPException(404, f"Asset not found: {full_path}")

    index = PUBLIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "Frontend not found")
    return Response(content=index.read_bytes(), media_type="text/html")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    print(f"\n  WarRoom v2 (Python) -> http://localhost:{port}\n")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level="info")
