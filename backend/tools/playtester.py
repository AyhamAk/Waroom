"""
Vision Playtester — drives the built game in a real browser, captures
screenshots at scripted moments, and feeds them to the QA agent for typed-
fix scoring.

Two modes:
  1. PLAYWRIGHT (preferred) — installs `playwright` + chromium, fully
     scripted: load URL, wait for canvas, send WASD + mouse, capture frames.
  2. STATIC FALLBACK — if Playwright isn't available, ship the build to the
     existing /preview-now endpoint and capture a single screenshot via the
     mss desktop grabber. Coverage is shallower but the loop still closes.

Either way the output is the same: a list of (label, png_path) pairs and a
short text summary that the QA agent attaches as vision blocks.
"""
import asyncio
import base64
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional


def _free_port(start: int = 5174, end: int = 5300) -> int:
    for p in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


@contextmanager
def _vite_preview(workspace_dir: str, port: int):
    """
    Spawn `npm run preview` for the workspace's game/ folder so the bundled
    build is served at http://localhost:<port>/. Cleans up on exit.
    """
    game_dir = Path(workspace_dir) / "game"
    proc: Optional[subprocess.Popen] = None
    try:
        if not (game_dir / "node_modules").exists():
            # The pipeline should have run npm install earlier; if not we
            # try once with a short timeout, otherwise the static fallback
            # will be used.
            try:
                subprocess.run(
                    ["npm", "install", "--no-audit", "--no-fund"],
                    cwd=str(game_dir), timeout=120, check=False, shell=(sys.platform == "win32"),
                )
            except Exception:
                pass

        env = {**os.environ, "PORT": str(port)}
        proc = subprocess.Popen(
            ["npm", "run", "preview", "--", "--port", str(port), "--strictPort"],
            cwd=str(game_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, shell=(sys.platform == "win32"),
        )
        # Wait until the port responds (max 12s).
        deadline = time.time() + 12
        ready = False
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    ready = True
                    break
            except OSError:
                time.sleep(0.25)
        if not ready:
            yield None
            return
        yield f"http://127.0.0.1:{port}"
    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


async def _playwright_drive(url: str, out_dir: Path, genre: str = "auto") -> list[dict]:
    """
    Drive the build with Playwright. Returns frames: [{label, path, ts}, ...].
    Returns [] if Playwright is unavailable (caller then falls back).
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return []

    frames: list[dict] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True, args=["--use-gl=swiftshader"])
        except Exception:
            return []
        ctx = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="load", timeout=15000)
        except Exception as exc:
            await browser.close()
            return [{"label": "load_failed", "path": "", "error": str(exc)[:200]}]

        # Wait for the canvas to appear and render at least one frame.
        try:
            await page.wait_for_selector("#stage", timeout=8000)
            await page.wait_for_function(
                "() => { const c = document.getElementById('stage'); return c && c.width > 100 && c.height > 100; }",
                timeout=8000,
            )
            await asyncio.sleep(0.8)
        except Exception:
            pass

        # Frame 0 — initial state.
        path = out_dir / "playtest_00_initial.png"
        await page.screenshot(path=str(path), full_page=False)
        frames.append({"label": "initial", "path": str(path), "ts": int(time.time() * 1000)})

        # Click once to engage pointer-lock / unlock audio.
        try:
            await page.mouse.click(640, 360)
        except Exception:
            pass
        await asyncio.sleep(0.4)

        # Drive a generic input sequence (WASD + jump + click) — the
        # specifics don't matter for scoring; we just need varied frames.
        sequences: list[tuple[str, list[str]]] = [
            ("after_movement", ["w", "w", "w"]),
            ("after_strafe",   ["a", "a"]),
            ("after_jump",     ["Space"]),
        ]
        for label, keys in sequences:
            for k in keys:
                try:
                    await page.keyboard.down(k)
                    await asyncio.sleep(0.18)
                    await page.keyboard.up(k)
                except Exception:
                    pass
            await asyncio.sleep(0.4)
            path = out_dir / f"playtest_{len(frames):02d}_{label}.png"
            try:
                await page.screenshot(path=str(path), full_page=False)
                frames.append({"label": label, "path": str(path), "ts": int(time.time() * 1000)})
            except Exception:
                pass

        # Mouse drag + click for shooter-style genres.
        try:
            await page.mouse.move(700, 380)
            await page.mouse.down()
            await asyncio.sleep(0.15)
            await page.mouse.up()
        except Exception:
            pass
        await asyncio.sleep(0.4)
        path = out_dir / f"playtest_{len(frames):02d}_after_action.png"
        try:
            await page.screenshot(path=str(path), full_page=False)
            frames.append({"label": "after_action", "path": str(path), "ts": int(time.time() * 1000)})
        except Exception:
            pass

        # Pull console errors and basic perf markers from the page.
        try:
            errors = await page.evaluate(
                "() => (window.__perfErrors || []).slice(-5)"
            )
        except Exception:
            errors = []

        # Final screenshot after a brief settle.
        await asyncio.sleep(0.8)
        path = out_dir / f"playtest_{len(frames):02d}_final.png"
        await page.screenshot(path=str(path), full_page=False)
        frames.append({
            "label": "final", "path": str(path),
            "ts": int(time.time() * 1000),
            "console_errors": errors,
        })

        await browser.close()

    return frames


def _static_fallback(url: str, out_dir: Path) -> list[dict]:
    """
    No-Playwright fallback. We can't drive the game without Playwright, so
    return an empty frames list with an explicit error. The QA agent's no-
    frames branch will write a typed fix report telling the user to run
    `playwright install chromium`.
    """
    return [{
        "label": "playwright_missing",
        "path": "",
        "error": "Playwright is not installed. Run: pip install playwright && playwright install chromium",
    }]


async def run_playtest(workspace_dir: str, port: Optional[int] = None, genre: str = "auto") -> dict[str, Any]:
    """
    Run a full playtest cycle. Returns:
      {
        "frames":   [{label, path, ts, ...}, ...],
        "url":      "http://...",
        "mode":     "playwright" | "static",
        "build_ok": bool,
        "errors":   [...],
      }

    The QA agent reads this, attaches frames as vision blocks, and emits
    typed fixes.
    """
    out_dir = Path(workspace_dir) / "renders"
    out_dir.mkdir(parents=True, exist_ok=True)

    port = port or _free_port()

    # 1. Make sure a build exists. If not, run `vite build`.
    game_dir = Path(workspace_dir) / "game"
    public_dir = Path(workspace_dir) / "public"
    index_html = public_dir / "index.html"
    if not index_html.exists() and game_dir.exists():
        try:
            subprocess.run(
                ["npm", "run", "build"],
                cwd=str(game_dir), timeout=180, check=False, shell=(sys.platform == "win32"),
            )
        except Exception:
            pass

    build_ok = index_html.exists()

    # 2. Try Playwright first.
    with _vite_preview(workspace_dir, port) as url:
        if url:
            frames = await _playwright_drive(url, out_dir, genre)
            if frames and any(f.get("path") for f in frames):
                return {
                    "frames": frames,
                    "url": url,
                    "mode": "playwright",
                    "build_ok": build_ok,
                    "errors": [],
                }
            # Playwright unavailable or failed — fall through to static.
            frames = _static_fallback(url, out_dir)
            return {
                "frames": frames,
                "url": url,
                "mode": "static",
                "build_ok": build_ok,
                "errors": ["playwright_unavailable_or_failed"],
            }

    return {
        "frames": [],
        "url": None,
        "mode": "none",
        "build_ok": build_ok,
        "errors": ["preview_server_failed_to_start"],
    }


def encode_frame_b64(path: str) -> Optional[tuple[str, str]]:
    """Encode a PNG as base64 + media_type, ready to attach as a vision block."""
    if not path or not Path(path).exists():
        return None
    try:
        from PIL import Image
        with Image.open(path) as img:
            img = img.convert("RGB")
            # Cap dimensions to keep token cost bounded.
            img.thumbnail((1024, 1024))
            tmp = path + ".thumb.png"
            img.save(tmp, format="PNG", optimize=True)
            data = Path(tmp).read_bytes()
            try:
                os.remove(tmp)
            except OSError:
                pass
        return base64.b64encode(data).decode("ascii"), "image/png"
    except Exception:
        # Pillow optional — fallback to raw bytes.
        try:
            data = Path(path).read_bytes()
            return base64.b64encode(data).decode("ascii"), "image/png"
        except Exception:
            return None
