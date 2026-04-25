"""
Lead Engineer — translates CEO decisions into technical architecture.
Produces docs/technical-spec.md.
"""
import json
import time
from typing import Callable

from agents.base import WRITE_FILE_TOOL, run_agent_with_tools
from graph.state import CompanyState
from tools.file_ops import read_file, write_file

LE_TOOLS = [WRITE_FILE_TOOL]

_LE_SYSTEM = """You are a Lead Engineer. Write a compact technical spec the Developer can execute without thinking.

TOOLS:
- write_file: Your ONLY tool. ALWAYS write to path "docs/technical-spec.md" — no other path.

Write ONLY the new cycle section. System auto-appends. Keep it under 40 lines.
Use this EXACT compact format:

## Cycle N — Feature Name
stack: <lang> | <lib@version> (CDN or npm)
create:
  path/to/file.js — one-line description
modify:
  path/to/existing.js — exactly what changes
steps:
  1. Specific action (class name, method, algorithm)
  2. ...
preserve: files Developer must not touch

RULE: write_file path MUST be "docs/technical-spec.md". Nothing else. Then STOP.
"""


async def lead_engineer_node(state: CompanyState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"]["session"]
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "lead-eng", "status": "thinking"})
    await _push_sys(emit, "⚙️ Lead Engineer — designing technical approach")

    ceo_decision = read_file(workspace, "docs/feature-priority.md")
    existing_spec = read_file(workspace, "docs/technical-spec.md")

    # Pass tail of existing spec for context — agent writes NEW section only, system appends
    spec_ctx = ""
    if existing_spec and not existing_spec.startswith("(file"):
        tail = existing_spec[-800:].lstrip()
        spec_ctx = f"EXISTING SPEC TAIL (context only — do NOT repeat this):\n...{tail}"
    else:
        spec_ctx = "No existing spec — write the first section from scratch."

    user_msg = f"""Company: {state['brief']}
Type: {state['company_type']}
Cycle: {state['cycle']}

CEO DECISION:
{ceo_decision}

{spec_ctx}

Write ONLY the new ## Cycle {state['cycle']} section. Call write_file NOW."""

    async def tool_executor(name: str, inputs: dict):
        if name == "write_file":
            content = inputs["content"]
            # Force correct path — agent sometimes invents wrong filenames
            path = "docs/technical-spec.md"
            # Append mode: LE writes only the new section
            prev = read_file(workspace, path)
            if prev and not prev.startswith("(file"):
                content = prev.rstrip() + "\n\n---\n\n" + content.lstrip()
            result = write_file(workspace, path, content)
            if result.get("ok"):
                await _emit_file(emit, session, path, content, "lead-eng")
            return json.dumps(result)
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=_LE_SYSTEM,
        user_message=user_msg,
        tools=LE_TOOLS,
        tool_executor=tool_executor,
        emit=emit,
        agent_id="lead-eng",
        api_key=state["api_key"],
        max_tokens=16000,
        max_iterations=5,
        session=session,
        stop_after_write=["docs/technical-spec.md"],
    )

    tech_spec = read_file(workspace, "docs/technical-spec.md")
    await emit("agent-status", {"agentId": "lead-eng", "status": "idle"})

    return {"tech_spec": tech_spec, "total_tokens": session.get("tokens", 0)}


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
