"""
Designer Agent — produces UI/UX design spec.
Writes docs/design-spec.md.
"""
import json
import time
from typing import Callable

from agents.base import WRITE_FILE_TOOL, run_agent_with_tools
from graph.state import CompanyState
from tools.file_ops import read_file, write_file

DESIGNER_TOOLS = [WRITE_FILE_TOOL]

_DESIGNER_SYSTEM = """You are a senior UI/UX Designer. You produce exact design specs developers implement directly.

TOOLS:
- write_file: Your ONLY tool. Call it immediately.

CRITICAL: Write ONLY the new "## Cycle N — [Feature]" section.
DO NOT rewrite or repeat previous cycles. The system appends your output automatically.
Keep your section under 100 lines. Exact values, zero ambiguity.

YOUR SECTION MUST CONTAIN:
- Colors: exact hex + CSS custom properties (e.g. "--hud-glow: #00e5ff")
- Layout: element structure, exact dimensions, grid/flex rules
- CSS classes: exact names the Developer copies directly
- Interactions: hover/active states, transition timing

RULES:
- One write_file call, then STOP. No summary, no explanation.
- Dark neon aesthetic. Specific: "#0a0f1e background, 1px solid #1a2a4a borders" not "dark theme"
"""


async def designer_node(state: CompanyState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"]["session"]
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "designer", "status": "thinking"})
    await _push_sys(emit, "🎨 Designer — creating UI/UX specification")

    ceo_decision = read_file(workspace, "docs/feature-priority.md")
    tech_spec = read_file(workspace, "docs/technical-spec.md")
    existing_design = read_file(workspace, "docs/design-spec.md")

    # Pass tail of tech spec and existing design for context — agent writes NEW section only
    tech_ctx = tech_spec[-1500:].lstrip() if tech_spec and not tech_spec.startswith("(file") else "See CEO decision"
    design_ctx = ""
    if existing_design and not existing_design.startswith("(file"):
        tail = existing_design[-600:].lstrip()
        design_ctx = f"EXISTING DESIGN TAIL (context only — do NOT repeat):\n...{tail}"
    else:
        design_ctx = "No existing design spec — write the first section from scratch."

    user_msg = f"""Company: {state['brief']}
Type: {state['company_type']}
Cycle: {state['cycle']}

CEO DECISION:
{ceo_decision}

TECH SPEC (recent):
...{tech_ctx}

{design_ctx}

Write ONLY the new ## Cycle {state['cycle']} section. Call write_file NOW."""

    async def tool_executor(name: str, inputs: dict):
        if name == "write_file":
            path = inputs["path"]
            content = inputs["content"]
            # Append mode: Designer writes only the new section; we prepend existing content
            if path == "docs/design-spec.md":
                prev = read_file(workspace, path)
                if prev and not prev.startswith("(file"):
                    content = prev.rstrip() + "\n\n---\n\n" + content.lstrip()
            result = write_file(workspace, path, content)
            if result.get("ok"):
                await _emit_file(emit, session, path, content, "designer")
            return json.dumps(result)
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_DESIGNER_SYSTEM,
        user_message=user_msg,
        tools=DESIGNER_TOOLS,
        tool_executor=tool_executor,
        emit=emit,
        agent_id="designer",
        api_key=state["api_key"],
        max_tokens=16000,
        max_iterations=5,
        session=session,
        stop_after_write=["docs/design-spec.md"],
    )

    design_spec = read_file(workspace, "docs/design-spec.md")
    await emit("agent-status", {"agentId": "designer", "status": "idle"})

    return {"design_spec": design_spec, "total_tokens": session.get("tokens", 0)}


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
