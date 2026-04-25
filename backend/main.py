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
    if not candidate.exists() or candidate.is_dir():
        candidate = PUBLIC_DIR / "index.html"
    if not candidate.exists():
        raise HTTPException(404, "Frontend not found")

    mime = _MIME.get(candidate.suffix.lower(), "text/plain")
    return Response(content=candidate.read_bytes(), media_type=mime)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    print(f"\n  WarRoom v2 (Python) -> http://localhost:{port}\n")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level="info")
