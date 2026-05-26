"""
QA Swarm — six specialized agents that attack a URL from different angles.

LangGraph nodes (imported by qa_graph.py):
  scout_node(state, config)       — Playwright discovery pass
  parallel_qa_node(state, config) — runs 5 QA agents concurrently
  synthesis_node(state, config)   — aggregates bugs, writes report

Internal agent coroutines (called by parallel_qa_node):
  _run_visual(...)    — screenshots at 4 viewports → Claude vision
  _run_console(...)   — JS errors + failed network requests
  _run_a11y(...)      — axe-core accessibility scan
  _run_security(...)  — HTTP headers + source code patterns
  _run_functional(...)— broken links + form submission testing
"""
import asyncio
import base64
import json
import re
import time
from pathlib import Path
from typing import Callable, Optional

import anthropic

from graph.qa_state import QAState


# ── WCAG colour-math helpers ──────────────────────────────────────────────────

def _rel_luminance(r: float, g: float, b: float) -> float:
    """Relative luminance per WCAG 2.1 (inputs 0–255)."""
    def _f(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * _f(r) + 0.7152 * _f(g) + 0.0722 * _f(b)


def _contrast_ratio(l1: float, l2: float) -> float:
    """WCAG contrast ratio between two relative luminance values."""
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _parse_rgb(css_color: str) -> tuple:
    """Parse 'rgb(r, g, b)' or 'rgba(r, g, b, a)' → (r, g, b) ints. Returns None on failure."""
    m = re.match(r'rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)', css_color or '')
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


# ── Shared helpers ────────────────────────────────────────────────────────────

def _ts() -> int:
    return int(time.time() * 1000)


async def _push(emit: Callable, message: str, agent_id: str = "system") -> None:
    await emit("new-message", {
        "from": agent_id, "to": None, "type": "system",
        "message": message, "id": _ts(), "timestamp": _ts(),
    })


async def _status(emit: Callable, agent_id: str, status: str) -> None:
    await emit("agent-status", {"agentId": agent_id, "status": status})


def _next_bug_id(bugs: list) -> str:
    return f"bug_{len(bugs) + 1:04d}"


async def _add_bug(
    bugs: list, session: dict, emit: Callable, *,
    severity: str, type_: str, title: str, description: str,
    agent_id: str, url: str = "", element: str = "",
    reproduction: str = "", screenshot: str = "",
) -> None:
    """Add a bug to the shared list and emit qa-bug SSE event."""
    bug = {
        "id": _next_bug_id(bugs),
        "severity": severity,
        "type": type_,
        "title": title,
        "description": description,
        "agentId": agent_id,
        "url": url,
        "element": element,
        "reproduction": reproduction,
        "screenshot": screenshot,
        "timestamp": _ts(),
    }
    bugs.append(bug)
    session["bugs"] = bugs
    await emit("qa-bug", bug)


def _save_screenshot(workspace_dir: str, agent_id: str, png_bytes: bytes, session_id: str, label: str = "") -> str:
    """Save PNG bytes to workspace/screenshots/, return relative URL path."""
    shots_dir = Path(workspace_dir) / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{label}" if label else ""
    filename = f"{agent_id.replace('-', '_')}{suffix}_{_ts()}.png"
    (shots_dir / filename).write_bytes(png_bytes)
    return f"/api/qa/screenshot/{session_id}/{filename}"


async def _emit_screenshot(emit: Callable, agent_id: str, url_path: str, viewport: str = "") -> None:
    await emit("qa-screenshot", {
        "agentId": agent_id, "url": url_path,
        "viewport": viewport, "timestamp": _ts(),
    })


# ── Scout Agent ───────────────────────────────────────────────────────────────

async def scout_node(state: QAState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("qa_session", {})
    target_url = state["target_url"]
    workspace_dir = state["workspace_dir"]
    session_id = state["session_id"]

    await _status(emit, "scout-qa", "working")
    await _push(emit, f"🔍 Scout — mapping {target_url}", "scout-qa")

    site_map = [target_url]
    test_plan = f"Target: {target_url}"
    forms_found = 0
    links_found = 0

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            try:
                await page.goto(target_url, wait_until="load", timeout=15000)
                title = await page.title()

                # Discover internal links
                all_links = await page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => e.href).filter(h => h && !h.startsWith('javascript') && !h.startsWith('#'))"
                )
                base = target_url.rstrip("/")
                internal = list({l for l in all_links if l.startswith(base) or not l.startswith("http")})[:8]
                site_map = list({target_url} | set(internal))
                links_found = len(all_links)

                # Count forms
                forms_found = await page.locator("form").count()

                # Screenshot
                png = await page.screenshot(full_page=False)
                shot_url = _save_screenshot(workspace_dir, "scout-qa", png, session_id, "landing")
                await _emit_screenshot(emit, "scout-qa", shot_url, "1280x800")

                test_plan = (
                    f"Title: {title}\n"
                    f"Pages discovered: {len(site_map)}\n"
                    f"Links found: {links_found}\n"
                    f"Forms found: {forms_found}\n"
                    f"URLs: {', '.join(site_map[:5])}"
                )
                await _push(emit, f"🔍 Scout done — {len(site_map)} pages, {forms_found} forms", "scout-qa")
            except Exception as exc:
                await _push(emit, f"🔍 Scout warning: {exc}", "scout-qa")
            finally:
                await browser.close()
    except ImportError:
        await _push(emit, "⚠️ Playwright not installed — scout running in headless mode", "scout-qa")
    except Exception as exc:
        await _push(emit, f"🔍 Scout error: {exc}", "scout-qa")

    await _status(emit, "scout-qa", "idle")
    return {"site_map": site_map, "test_plan": test_plan}


# ── Visual Agent ─────────────────────────────────────────────────────────────

async def _run_visual(
    target_url: str, workspace_dir: str, session_id: str,
    bugs: list, session: dict, emit: Callable, api_key: str,
) -> str:
    agent_id = "visual-qa"
    await _status(emit, agent_id, "working")
    await _push(emit, "👁 Visual — capturing 4 viewports", agent_id)

    viewports = [
        (1920, 1080, "desktop"),
        (390,  844,  "mobile"),
    ]
    scroll_positions = [0, 50, 100]  # percent

    screenshots_b64 = []

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            for w, h, label in viewports:
                try:
                    ctx = await browser.new_context(viewport={"width": w, "height": h})
                    page = await ctx.new_page()
                    await page.goto(target_url, wait_until="load", timeout=15000)
                    await page.wait_for_timeout(500)
                    # Capture at 3 scroll positions
                    for scroll_pct in scroll_positions:
                        try:
                            await page.evaluate(
                                f"window.scrollTo(0, document.body.scrollHeight * {scroll_pct/100})"
                            )
                            await page.wait_for_timeout(300)
                            png = await page.screenshot(full_page=False)
                            scroll_label = f"{label}_{scroll_pct}pct"
                            shot_url = _save_screenshot(workspace_dir, agent_id, png, session_id, scroll_label)
                            await _emit_screenshot(emit, agent_id, shot_url, f"{w}x{h} @{scroll_pct}%")
                            b64 = base64.standard_b64encode(png).decode()
                            screenshots_b64.append({
                                "label": label, "viewport": f"{w}x{h}",
                                "scroll": f"{scroll_pct}%", "b64": b64, "url": shot_url
                            })
                        except Exception as scroll_exc:
                            await _push(emit, f"👁 Visual scroll error {label}@{scroll_pct}%: {scroll_exc}", agent_id)
                    await ctx.close()
                except Exception as exc:
                    await _push(emit, f"👁 Visual {label} error: {exc}", agent_id)
                    await _add_bug(bugs, session, emit,
                        severity="info", type_="visual",
                        title=f"Visual agent failed at {label} viewport",
                        description=str(exc),
                        agent_id=agent_id, url=target_url,
                        reproduction=f"Screenshot capture failed at {label} ({w}x{h}px)",
                    )
            await browser.close()
    except ImportError:
        await _push(emit, "⚠️ Playwright not installed — visual agent skipped", agent_id)
        await _status(emit, agent_id, "idle")
        return "skipped: playwright not installed"
    except Exception as exc:
        await _push(emit, f"👁 Visual error: {exc}", agent_id)
        await _status(emit, agent_id, "idle")
        return f"error: {exc}"

    if not screenshots_b64:
        await _status(emit, agent_id, "idle")
        return "no screenshots captured"

    # Send to Claude vision for analysis
    try:
        client = anthropic.Anthropic(api_key=api_key)
        content = [
            {
                "type": "text",
                "text": (
                    f"You are a senior UI/UX designer and visual QA engineer reviewing {target_url}.\n"
                    "I'm sending you screenshots at multiple viewports and scroll positions.\n\n"
                    "Analyze for ALL of the following:\n\n"
                    "LAYOUT & STRUCTURE\n"
                    "- Overflow, truncation, overlap, misalignment\n"
                    "- Inconsistent spacing between similar sections\n"
                    "- Elements cut off at viewport edges\n\n"
                    "TYPOGRAPHY\n"
                    "- Text too small to read comfortably\n"
                    "- Inconsistent font sizes across similar elements\n"
                    "- Poor line height (lines too tight or too loose)\n"
                    "- Heading visual hierarchy unclear\n\n"
                    "COLOR & CONTRAST\n"
                    "- Low contrast text that is hard to read\n"
                    "- Inconsistent brand colors across sections\n"
                    "- Color combinations that clash or feel unintentional\n\n"
                    "SCROLL & ANIMATION\n"
                    "- Elements broken mid-animation between scroll positions\n"
                    "- Jarring visual jumps between scroll frames\n"
                    "- Content overlapping during transitions\n\n"
                    "RESPONSIVE DESIGN\n"
                    "- Content fine on desktop but broken on mobile\n"
                    "- Touch targets visibly too small on mobile\n"
                    "- Horizontal scroll appearing on mobile viewport\n\n"
                    "Respond with a JSON array (no markdown). Each item:\n"
                    '{"severity":"critical|high|medium|low",'
                    '"category":"layout|typography|color|scroll|responsive",'
                    '"title":"short title","description":"specific description with viewport/scroll info",'
                    '"element":"CSS selector or description",'
                    '"viewport":"desktop|mobile","scroll_position":"top|middle|bottom"}\n'
                    "Only report real bugs you can actually see. Empty array if none found."
                ),
            }
        ]
        for s in screenshots_b64:
            content.append({"type": "text", "text": f"Viewport: {s['viewport']} ({s['label']}) — scroll: {s.get('scroll','top')}"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": s["b64"]},
            })

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        found_bugs = json.loads(raw)
        if not isinstance(found_bugs, list):
            found_bugs = []

        for b in found_bugs:
            viewport_label = b.get("viewport", "")
            shot = next((s["url"] for s in screenshots_b64 if s["label"] in viewport_label or s["viewport"] in viewport_label), "")
            await _add_bug(
                bugs, session, emit,
                severity=b.get("severity", "medium"),
                type_="visual",
                title=b.get("title", "Visual bug"),
                description=b.get("description", ""),
                agent_id=agent_id,
                url=target_url,
                element=b.get("element", ""),
                reproduction=f"View page at {b.get('viewport', 'unknown')} viewport",
                screenshot=shot,
            )
        await _push(emit, f"👁 Visual done — {len(found_bugs)} bugs found", agent_id)
    except Exception as exc:
        await _push(emit, f"👁 Vision analysis error: {exc}", agent_id)

    await _status(emit, agent_id, "idle")
    return f"{len(bugs)} bugs reported"


# ── Console Agent ─────────────────────────────────────────────────────────────

async def _run_console(
    target_url: str, site_map: list, workspace_dir: str, session_id: str,
    bugs: list, session: dict, emit: Callable,
) -> str:
    agent_id = "console-qa"
    await _status(emit, agent_id, "working")
    await _push(emit, "⚡ Console — monitoring JS errors and network failures", agent_id)

    errors_found = 0
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            for url in site_map[:4]:
                js_errors = []
                console_errors = []
                failed_requests = []

                try:
                    page = await browser.new_page()
                    page.on("pageerror", lambda e: js_errors.append(str(e)))
                    page.on("console", lambda m: console_errors.append({"type": m.type, "text": m.text}) if m.type in ("error", "warning") else None)
                    page.on("requestfailed", lambda r: failed_requests.append({"url": r.url, "failure": r.failure}))

                    await page.goto(url, wait_until="load", timeout=15000)
                    # Scroll to trigger lazy-loaded content
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(500)

                    # Take screenshot
                    png = await page.screenshot()
                    shot_url = _save_screenshot(workspace_dir, agent_id, png, session_id, "console")
                    await _emit_screenshot(emit, agent_id, shot_url, "1280x800")

                    for err in js_errors:
                        await _add_bug(bugs, session, emit,
                            severity="critical", type_="console",
                            title=f"JavaScript error: {str(err)[:80]}",
                            description=str(err), agent_id=agent_id, url=url,
                            reproduction="Open browser console while visiting the page",
                            screenshot=shot_url,
                        )
                        errors_found += 1

                    for c in console_errors[:10]:
                        sev = "high" if c["type"] == "error" else "low"
                        await _add_bug(bugs, session, emit,
                            severity=sev, type_="console",
                            title=f"Console {c['type']}: {c['text'][:80]}",
                            description=c["text"], agent_id=agent_id, url=url,
                            reproduction="Open browser DevTools → Console",
                            screenshot=shot_url,
                        )
                        errors_found += 1

                    for req in failed_requests[:10]:
                        sev = "high" if req["url"].endswith((".js", ".css")) else "medium"
                        await _add_bug(bugs, session, emit,
                            severity=sev, type_="console",
                            title=f"Failed request: {req['url'][-60:]}",
                            description=f"Request failed: {req['url']}\nReason: {req['failure']}",
                            agent_id=agent_id, url=url,
                            reproduction="Open DevTools → Network tab, filter by failed",
                            screenshot=shot_url,
                        )
                        errors_found += 1

                    await page.close()
                except Exception as exc:
                    await _push(emit, f"⚡ Console error on {url}: {exc}", agent_id)

            await browser.close()
    except ImportError:
        await _push(emit, "⚠️ Playwright not installed — console agent skipped", agent_id)
    except Exception as exc:
        await _push(emit, f"⚡ Console error: {exc}", agent_id)
        await _add_bug(bugs, session, emit,
            severity="info", type_="console",
            title="Console agent failed",
            description=str(exc), agent_id=agent_id, url=target_url,
            reproduction="Console agent crashed — check backend logs",
        )

    await _push(emit, f"⚡ Console done — {errors_found} issues found", agent_id)
    await _status(emit, agent_id, "idle")
    return f"{errors_found} issues"


# ── A11y Agent ────────────────────────────────────────────────────────────────

AXE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.3/axe.min.js"

async def _run_a11y(
    target_url: str, workspace_dir: str, session_id: str,
    bugs: list, session: dict, emit: Callable,
) -> str:
    agent_id = "a11y-qa"
    await _status(emit, agent_id, "working")
    await _push(emit, "♿ A11y — running accessibility scan", agent_id)

    violations_found = 0
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(target_url, wait_until="load", timeout=15000)

                # Inject axe-core
                await page.add_script_tag(url=AXE_CDN)
                await page.wait_for_timeout(500)

                # Run axe
                results = await page.evaluate("""
                    async () => {
                        const r = await axe.run();
                        return r.violations.map(v => ({
                            id: v.id,
                            impact: v.impact,
                            description: v.description,
                            help: v.help,
                            helpUrl: v.helpUrl,
                            nodes: v.nodes.slice(0,2).map(n => ({
                                html: n.html.slice(0,200),
                                target: n.target[0] || '',
                                failureSummary: n.failureSummary
                            }))
                        }));
                    }
                """)

                # Screenshot with focus rings visible
                png = await page.screenshot()
                shot_url = _save_screenshot(workspace_dir, agent_id, png, session_id, "a11y")
                await _emit_screenshot(emit, agent_id, shot_url, "1280x800")

                impact_to_severity = {
                    "critical": "critical", "serious": "high",
                    "moderate": "medium", "minor": "low",
                }

                for v in (results or []):
                    sev = impact_to_severity.get(v.get("impact", "minor"), "low")
                    nodes_desc = "; ".join(
                        n.get("target", "") for n in v.get("nodes", []) if n.get("target")
                    )
                    await _add_bug(bugs, session, emit,
                        severity=sev, type_="accessibility",
                        title=f"A11y: {v.get('help', v.get('id', 'violation'))}",
                        description=f"{v.get('description', '')}\nAffected: {nodes_desc}\nMore: {v.get('helpUrl', '')}",
                        agent_id=agent_id, url=target_url,
                        element=nodes_desc[:100],
                        reproduction=f"Run axe-core audit. Rule: {v.get('id', '')}",
                        screenshot=shot_url,
                    )
                    violations_found += 1

            except Exception as exc:
                await _push(emit, f"♿ A11y scan error: {exc}", agent_id)
            finally:
                await browser.close()
    except ImportError:
        await _push(emit, "⚠️ Playwright not installed — a11y agent skipped", agent_id)
    except Exception as exc:
        await _push(emit, f"♿ A11y error: {exc}", agent_id)
        await _add_bug(bugs, session, emit,
            severity="info", type_="accessibility",
            title="A11y agent failed",
            description=str(exc), agent_id=agent_id, url=target_url,
            reproduction="A11y agent crashed — check backend logs",
        )

    await _push(emit, f"♿ A11y done — {violations_found} violations found", agent_id)
    await _status(emit, agent_id, "idle")
    return f"{violations_found} violations"


# ── Security Agent ────────────────────────────────────────────────────────────

_SECURITY_HEADERS = [
    ("Content-Security-Policy",       "high",   "Missing Content-Security-Policy header — allows XSS attacks"),
    ("Strict-Transport-Security",     "high",   "Missing HSTS header — site vulnerable to protocol downgrade"),
    ("X-Frame-Options",               "medium", "Missing X-Frame-Options — site may be clickjacked"),
    ("X-Content-Type-Options",        "medium", "Missing X-Content-Type-Options — MIME sniffing risk"),
    ("Referrer-Policy",               "low",    "Missing Referrer-Policy — may leak URL data to third parties"),
    ("Permissions-Policy",            "low",    "Missing Permissions-Policy — browser features unrestricted"),
]

_API_KEY_PATTERNS = [
    (r"AIza[0-9A-Za-z\-_]{35}",          "Google API key"),
    (r"sk-[a-zA-Z0-9]{48}",              "OpenAI API key"),
    (r"sk-ant-[a-zA-Z0-9\-_]{93}",       "Anthropic API key"),
    (r"ghp_[a-zA-Z0-9]{36}",             "GitHub Personal Access Token"),
    (r"AKIA[0-9A-Z]{16}",                "AWS Access Key"),
    (r"(?i)api[_-]?key\s*[=:]\s*['\"][a-zA-Z0-9_\-]{20,}['\"]", "Hardcoded API key"),
    (r"(?i)password\s*[=:]\s*['\"][^'\"]{8,}['\"]", "Hardcoded password"),
    (r"(?i)secret\s*[=:]\s*['\"][^'\"]{8,}['\"]",   "Hardcoded secret"),
]

async def _run_security(
    target_url: str, workspace_dir: str, session_id: str,
    bugs: list, session: dict, emit: Callable,
) -> str:
    agent_id = "security-qa"
    await _status(emit, agent_id, "working")
    await _push(emit, "🔒 Security — scanning headers and source code", agent_id)

    issues_found = 0

    try:
        import urllib.request
        req = urllib.request.Request(target_url, headers={"User-Agent": "WarRoom-QA/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            headers = dict(resp.headers)
            source = resp.read(500_000).decode("utf-8", errors="replace")

        # Header checks
        for header, severity, description in _SECURITY_HEADERS:
            if header.lower() not in {k.lower() for k in headers}:
                await _add_bug(bugs, session, emit,
                    severity=severity, type_="security",
                    title=f"Missing security header: {header}",
                    description=description,
                    agent_id=agent_id, url=target_url,
                    reproduction=f"curl -I {target_url} | grep -i '{header.lower()}'",
                )
                issues_found += 1

        # Check cookies via Playwright for HttpOnly/Secure flags
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                ctx = await browser.new_context()
                page = await ctx.new_page()
                await page.goto(target_url, timeout=15000)
                cookies = await ctx.cookies()
                png = await page.screenshot()
                shot_url = _save_screenshot(workspace_dir, agent_id, png, session_id, "security")
                await _emit_screenshot(emit, agent_id, shot_url, "1280x800")
                await browser.close()

                for cookie in cookies:
                    if not cookie.get("httpOnly"):
                        await _add_bug(bugs, session, emit,
                            severity="medium", type_="security",
                            title=f"Cookie missing HttpOnly flag: {cookie['name']}",
                            description=f"Cookie '{cookie['name']}' is accessible via JavaScript (no HttpOnly). Vulnerable to XSS session theft.",
                            agent_id=agent_id, url=target_url,
                            element=f"Cookie: {cookie['name']}",
                            screenshot=shot_url,
                        )
                        issues_found += 1
                    if target_url.startswith("https") and not cookie.get("secure"):
                        await _add_bug(bugs, session, emit,
                            severity="medium", type_="security",
                            title=f"Cookie missing Secure flag: {cookie['name']}",
                            description=f"Cookie '{cookie['name']}' can be sent over HTTP. Set Secure flag.",
                            agent_id=agent_id, url=target_url,
                            element=f"Cookie: {cookie['name']}",
                            screenshot=shot_url,
                        )
                        issues_found += 1
        except Exception:
            pass

        # API key / secret scan in source
        for pattern, key_type in _API_KEY_PATTERNS:
            matches = re.findall(pattern, source)
            for match in matches[:2]:
                redacted = match[:8] + "..." + match[-4:] if len(match) > 12 else match
                await _add_bug(bugs, session, emit,
                    severity="critical", type_="security",
                    title=f"Exposed {key_type} in page source",
                    description=f"Found possible {key_type} in page source: {redacted}\nNever expose secrets in frontend code.",
                    agent_id=agent_id, url=target_url,
                    reproduction="View page source (Ctrl+U) and search for the pattern",
                )
                issues_found += 1

    except Exception as exc:
        await _push(emit, f"🔒 Security error: {exc}", agent_id)

    await _push(emit, f"🔒 Security done — {issues_found} issues found", agent_id)
    await _status(emit, agent_id, "idle")
    return f"{issues_found} issues"


# ── Functional Agent ──────────────────────────────────────────────────────────

async def _run_functional(
    target_url: str, site_map: list, workspace_dir: str, session_id: str,
    bugs: list, session: dict, emit: Callable,
) -> str:
    agent_id = "functional-qa"
    await _status(emit, agent_id, "working")
    await _push(emit, "🖱 Functional — testing links, forms, interactions", agent_id)

    issues_found = 0
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await page.goto(target_url, wait_until="load", timeout=15000)

                # Screenshot
                png = await page.screenshot()
                shot_url = _save_screenshot(workspace_dir, agent_id, png, session_id, "functional")
                await _emit_screenshot(emit, agent_id, shot_url, "1280x800")

                # Check all links for 4xx/5xx
                links = await page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => e.href).filter(h => h && h.startsWith('http')).slice(0, 20)"
                )
                for link in links:
                    try:
                        resp_page = await browser.new_page()
                        response = await resp_page.goto(link, timeout=10000)
                        if response and response.status >= 400:
                            await _add_bug(bugs, session, emit,
                                severity="high" if response.status == 404 else "medium",
                                type_="functional",
                                title=f"Broken link ({response.status}): {link[-60:]}",
                                description=f"Link returns HTTP {response.status}: {link}",
                                agent_id=agent_id, url=target_url,
                                element=f"a[href='{link}']",
                                reproduction=f"Click the link pointing to: {link}",
                                screenshot=shot_url,
                            )
                            issues_found += 1
                        await resp_page.close()
                    except Exception:
                        pass

                # Test forms — try submitting empty
                forms = await page.locator("form").all()
                for i, form in enumerate(forms[:3]):
                    try:
                        # Try submitting empty form
                        submit = form.locator("[type=submit], button")
                        if await submit.count() > 0:
                            await submit.first.click(timeout=3000)
                            await page.wait_for_timeout(500)
                            # Check if page errored badly
                            title_after = await page.title()
                            if any(w in title_after.lower() for w in ["error", "500", "crash"]):
                                await _add_bug(bugs, session, emit,
                                    severity="critical", type_="functional",
                                    title=f"Form {i+1} causes server error on empty submit",
                                    description=f"Submitting form {i+1} empty caused page title to become: '{title_after}'",
                                    agent_id=agent_id, url=target_url,
                                    reproduction=f"Find form {i+1} on the page, leave all fields empty, submit",
                                    screenshot=shot_url,
                                )
                                issues_found += 1
                    except Exception:
                        pass

            except Exception as exc:
                await _push(emit, f"🖱 Functional error: {exc}", agent_id)
            finally:
                await browser.close()

    except ImportError:
        await _push(emit, "⚠️ Playwright not installed — functional agent skipped", agent_id)
    except Exception as exc:
        await _push(emit, f"🖱 Functional error: {exc}", agent_id)
        await _add_bug(bugs, session, emit,
            severity="info", type_="functional",
            title="Functional agent failed",
            description=str(exc), agent_id=agent_id, url=target_url,
            reproduction="Functional agent crashed — check backend logs",
        )

    await _push(emit, f"🖱 Functional done — {issues_found} issues found", agent_id)
    await _status(emit, agent_id, "idle")
    return f"{issues_found} issues"


# ── Style Intelligence Agent ──────────────────────────────────────────────────

_STYLE_JS = """
(function() {
  const seen = new Set();
  const items = [];
  const selectors = 'p,h1,h2,h3,h4,h5,h6,a,button,label,span,li,td,th,div[class]';
  document.querySelectorAll(selectors).forEach(el => {
    if (!el.offsetParent && el.tagName !== 'BODY') return; // skip hidden
    const s = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return; // skip zero-size
    const key = el.tagName + '|' + s.color + '|' + s.backgroundColor + '|' + s.fontSize;
    if (seen.has(key)) return;
    seen.add(key);
    if (items.length >= 300) return;
    items.push({
      tag: el.tagName,
      text: (el.innerText || '').slice(0, 50).trim(),
      color: s.color,
      bg: s.backgroundColor,
      fontSize: s.fontSize,
      lineHeight: s.lineHeight,
      outline: s.outline,
      w: Math.round(r.width),
      h: Math.round(r.height),
    });
  });

  // Headings for hierarchy check
  const headings = [];
  document.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(h => {
    headings.push({ tag: h.tagName, text: (h.innerText||'').slice(0,60) });
  });

  // Interactive elements for touch target check
  const interactive = [];
  document.querySelectorAll('a,button,input,select,textarea,[role="button"],[tabindex]').forEach(el => {
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    interactive.push({
      tag: el.tagName, w: Math.round(r.width), h: Math.round(r.height),
      outline: s.outline, text: (el.innerText||el.value||'').slice(0,40),
    });
  });

  // Inline style count
  const inlineCount = document.querySelectorAll('[style]').length;

  return { items, headings, interactive, inlineCount };
})()
"""


async def _run_style(
    target_url: str, workspace_dir: str, session_id: str,
    bugs: list, session: dict, emit: Callable,
) -> str:
    agent_id = 'style-qa'
    await _status(emit, agent_id, 'working')
    await _push(emit, '🎨 Style — inspecting computed CSS, contrast & typography', agent_id)

    issues_found = 0
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1280, 'height': 800})
            try:
                await page.goto(target_url, wait_until='load', timeout=15000)
                await page.wait_for_timeout(800)  # let JS settle

                data = await page.evaluate(_STYLE_JS)
                png = await page.screenshot()
                shot_url = _save_screenshot(workspace_dir, agent_id, png, session_id, 'style')
                await _emit_screenshot(emit, agent_id, shot_url, '1280x800')

                items       = data.get('items', [])
                headings    = data.get('headings', [])
                interactive = data.get('interactive', [])
                inline_count = data.get('inlineCount', 0)

                # ── 1. Colour contrast ────────────────────────────────────────
                contrast_failures: dict = {}  # deduplicate by color pair
                for el in items:
                    fg = _parse_rgb(el.get('color', ''))
                    bg = _parse_rgb(el.get('bg', ''))
                    if not fg or not bg:
                        continue
                    # Skip fully transparent backgrounds
                    if bg == (0, 0, 0) and 'rgba' in (el.get('bg') or '') and 'alpha:0' in (el.get('bg') or ''):
                        continue
                    pair_key = f"{el['color']}|{el['bg']}"
                    if pair_key in contrast_failures:
                        continue
                    l_fg = _rel_luminance(*fg)
                    l_bg = _rel_luminance(*bg)
                    ratio = _contrast_ratio(l_fg, l_bg)
                    # Detect large text (>= 18pt / 24px, or 14pt bold / ~18.67px)
                    font_px = float((el.get('fontSize') or '16px').replace('px', '') or 16)
                    is_large = font_px >= 24
                    threshold_aa  = 3.0 if is_large else 4.5
                    threshold_aaa = 4.5 if is_large else 7.0
                    if ratio < threshold_aa:
                        sev = 'critical' if ratio < 2.0 else 'high'
                        contrast_failures[pair_key] = True
                        await _add_bug(bugs, session, emit,
                            severity=sev, type_='visual',
                            title=f'Contrast ratio {ratio:.1f}:1 fails WCAG AA ({threshold_aa}:1 required)',
                            description=(
                                f'Text "{el.get("text", "")[:40]}" on <{el["tag"].lower()}> has '
                                f'contrast ratio {ratio:.2f}:1 — below WCAG AA minimum of {threshold_aa}:1. '
                                f'Text color: {el["color"]}, Background: {el["bg"]}.'
                            ),
                            agent_id=agent_id, url=target_url,
                            element=el['tag'].lower(),
                            reproduction=(
                                f'1. Open {target_url}\n'
                                f'2. Inspect <{el["tag"].lower()}> element\n'
                                f'3. Check computed color ({el["color"]}) vs background ({el["bg"]})\n'
                                f'4. Contrast ratio is {ratio:.2f}:1 — minimum required: {threshold_aa}:1'
                            ),
                            screenshot=shot_url,
                        )
                        issues_found += 1
                    elif ratio < threshold_aaa:
                        contrast_failures[pair_key] = True
                        await _add_bug(bugs, session, emit,
                            severity='medium', type_='visual',
                            title=f'Contrast ratio {ratio:.1f}:1 fails WCAG AAA',
                            description=(
                                f'<{el["tag"].lower()}> "{el.get("text","")[:40]}" passes AA ({threshold_aa}:1) '
                                f'but fails AAA ({threshold_aaa}:1). Ratio: {ratio:.2f}:1.'
                            ),
                            agent_id=agent_id, url=target_url,
                            element=el['tag'].lower(),
                            reproduction=f'Check computed styles on <{el["tag"].lower()}>: {el["color"]} on {el["bg"]}',
                            screenshot=shot_url,
                        )
                        issues_found += 1
                    if issues_found > 20:  # cap to avoid spam
                        break

                # ── 2. Font size ──────────────────────────────────────────────
                small_fonts: set = set()
                for el in items:
                    fs_str = el.get('fontSize', '16px')
                    try:
                        fs = float(fs_str.replace('px', ''))
                    except (ValueError, AttributeError):
                        continue
                    if fs < 11 and el.get('text') and fs_str not in small_fonts:
                        small_fonts.add(fs_str)
                        await _add_bug(bugs, session, emit,
                            severity='medium', type_='visual',
                            title=f'Font size too small: {fs_str}',
                            description=f'<{el["tag"].lower()}> uses {fs_str} — below the recommended minimum of 12px. Affects readability.',
                            agent_id=agent_id, url=target_url,
                            element=el['tag'].lower(),
                            reproduction=f'Inspect <{el["tag"].lower()}> element — computed font-size: {fs_str}',
                            screenshot=shot_url,
                        )
                        issues_found += 1

                # ── 3. Touch target size ──────────────────────────────────────
                small_targets = 0
                for el in interactive[:100]:
                    w, h = el.get('w', 99), el.get('h', 99)
                    if w > 0 and h > 0 and (w < 44 or h < 44):
                        if small_targets < 5:
                            await _add_bug(bugs, session, emit,
                                severity='high', type_='visual',
                                title=f'Touch target too small: {el["tag"]} ({w}×{h}px)',
                                description=(
                                    f'<{el["tag"].lower()}> "{el.get("text","")[:40]}" is only {w}×{h}px. '
                                    f'WCAG 2.5.5 requires interactive targets to be at least 44×44px.'
                                ),
                                agent_id=agent_id, url=target_url,
                                element=el['tag'].lower(),
                                reproduction=f'Measure <{el["tag"].lower()}> bounding box — {w}×{h}px (need 44×44px)',
                                screenshot=shot_url,
                            )
                            issues_found += 1
                        small_targets += 1
                if small_targets > 5:
                    await _add_bug(bugs, session, emit,
                        severity='high', type_='visual',
                        title=f'{small_targets} interactive elements have touch targets < 44px',
                        description=f'Found {small_targets} buttons/links/inputs with touch targets smaller than 44×44px (WCAG 2.5.5). Impacts mobile usability.',
                        agent_id=agent_id, url=target_url,
                        reproduction='Inspect all <a>, <button>, <input> elements — measure bounding boxes',
                        screenshot=shot_url,
                    )
                    issues_found += 1

                # ── 4. Heading hierarchy ──────────────────────────────────────
                prev_level = 0
                for h in headings:
                    level = int(h['tag'][1])
                    if prev_level > 0 and level > prev_level + 1:
                        await _add_bug(bugs, session, emit,
                            severity='medium', type_='accessibility',
                            title=f'Heading hierarchy skip: H{prev_level} → H{level}',
                            description=(
                                f'Heading jumps from H{prev_level} to H{level} — skipping levels breaks '
                                f'document outline for screen readers. Found: "{h["text"]}"'
                            ),
                            agent_id=agent_id, url=target_url,
                            element=h['tag'].lower(),
                            reproduction=f'Find <{h["tag"].lower()}> "{h["text"][:40]}" — previous heading was H{prev_level}',
                            screenshot=shot_url,
                        )
                        issues_found += 1
                    prev_level = level

                # ── 5. Inline style overuse ───────────────────────────────────
                if inline_count > 40:
                    await _add_bug(bugs, session, emit,
                        severity='info', type_='visual',
                        title=f'{inline_count} inline style attributes detected',
                        description=f'Page has {inline_count} elements with inline style="" attributes. High inline style usage makes design inconsistency harder to detect and fix.',
                        agent_id=agent_id, url=target_url,
                        reproduction='In DevTools console: document.querySelectorAll("[style]").length',
                        screenshot=shot_url,
                    )
                    issues_found += 1

            except Exception as exc:
                await _push(emit, f'🎨 Style scan error: {exc}', agent_id)
                await _add_bug(bugs, session, emit,
                    severity='info', type_='visual',
                    title='Style agent failed', description=str(exc),
                    agent_id=agent_id, url=target_url,
                    reproduction='Style agent crashed — check backend logs',
                )
            finally:
                await browser.close()

    except ImportError:
        await _push(emit, '⚠️ Playwright not installed — style agent skipped', agent_id)
    except Exception as exc:
        await _push(emit, f'🎨 Style error: {exc}', agent_id)

    await _push(emit, f'🎨 Style done — {issues_found} issues found', agent_id)
    await _status(emit, agent_id, 'idle')
    return f'{issues_found} issues'


# ── Parallel QA node ──────────────────────────────────────────────────────────

async def parallel_qa_node(state: QAState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("qa_session", {})
    target_url = state["target_url"]
    site_map = state.get("site_map") or [target_url]
    workspace_dir = state["workspace_dir"]
    session_id = state["session_id"]
    api_key = state["api_key"]

    bugs: list = session.setdefault("bugs", [])

    await _push(emit, "🚀 All QA agents deploying in parallel...", "system")

    results = await asyncio.gather(
        _run_visual(target_url, workspace_dir, session_id, bugs, session, emit, api_key),
        _run_console(target_url, site_map, workspace_dir, session_id, bugs, session, emit),
        _run_a11y(target_url, workspace_dir, session_id, bugs, session, emit),
        _run_security(target_url, workspace_dir, session_id, bugs, session, emit),
        _run_functional(target_url, site_map, workspace_dir, session_id, bugs, session, emit),
        _run_style(target_url, workspace_dir, session_id, bugs, session, emit),
        return_exceptions=True,
    )

    agent_names = ["visual-qa", "console-qa", "a11y-qa", "security-qa", "functional-qa", "style-qa"]
    agent_reports = {}
    for name, result in zip(agent_names, results):
        if isinstance(result, Exception):
            agent_reports[name] = f"error: {result}"
            await _push(emit, f"⚠️ {name} crashed: {result}", "system")
        else:
            agent_reports[name] = str(result)

    await _push(emit, f"✅ All agents complete — {len(bugs)} total bugs found", "system")

    return {
        "bugs": list(bugs),
        "agent_reports": agent_reports,
    }


# ── Synthesis node ────────────────────────────────────────────────────────────

async def synthesis_node(state: QAState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"].get("qa_session", {})
    workspace_dir = state["workspace_dir"]
    bugs = state.get("bugs") or []

    await _status(emit, "synthesis-qa", "working")
    await _push(emit, "📋 Synthesis — writing final report", "synthesis-qa")

    # Count by severity
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for b in bugs:
        sev = b.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1

    # Write bugs.json
    bugs_path = Path(workspace_dir) / "bugs.json"
    bugs_path.write_text(json.dumps(bugs, indent=2), encoding="utf-8")

    # Write report.md
    report_lines = [
        f"# QA Report — {state['target_url']}",
        f"\n**Total bugs:** {len(bugs)}  ",
        f"🔴 Critical: {counts['critical']}  "
        f"🟠 High: {counts['high']}  "
        f"🟡 Medium: {counts['medium']}  "
        f"🔵 Low: {counts['low']}",
        "\n## Test Plan\n",
        state.get("test_plan", ""),
        "\n## Bugs by Severity\n",
    ]
    for sev in ("critical", "high", "medium", "low", "info"):
        sev_bugs = [b for b in bugs if b.get("severity") == sev]
        if sev_bugs:
            emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}.get(sev, "⚪")
            report_lines.append(f"\n### {emoji} {sev.upper()} ({len(sev_bugs)})\n")
            for b in sev_bugs:
                report_lines.append(f"- **[{b.get('type','?').upper()}]** {b.get('title','?')}")
                if b.get("description"):
                    report_lines.append(f"  > {b['description'][:200]}")

    synthesis = "\n".join(report_lines)
    (Path(workspace_dir) / "report.md").write_text(synthesis, encoding="utf-8")

    session["is_done"] = True
    session["synthesis"] = synthesis

    await _push(emit, f"📋 Report complete — {len(bugs)} bugs documented", "synthesis-qa")
    await _status(emit, "synthesis-qa", "idle")

    return {"synthesis": synthesis, "is_done": True}
