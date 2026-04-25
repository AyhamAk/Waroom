"""
CEO Agent — researches, makes decisions, drives the company roadmap.
"""
import json
import time
from pathlib import Path
from typing import Callable

from agents.base import WRITE_FILE_TOOL, run_agent_with_tools
from graph.state import CompanyState
from tools.file_ops import read_file, write_file


CEO_TOOLS = [WRITE_FILE_TOOL]

_CEO_SYSTEM = """You are the CEO of a fast-moving startup. You set direction, you make calls.

TOOLS:
- write_file: Record your decisions (your ONLY tool)

All context is already in the message. Do NOT try to use any other tool.

WORKFLOW:
1. Write docs/feature-priority.md with ONE decision
2. (Cycle 1 only) Also write docs/product-roadmap.md with 6-8 milestones
3. STOP immediately after writing

DECISION FORMAT — pick exactly one:
  NEW FEATURE: [name] — [one specific sentence]
  FIX: [what's broken] — [exactly how to fix it]
  DONE: [reason] — only when QA verdict is GOOD AND public/index.html exists

RULES:
- Never repeat last cycle's decision.
- Specific: "16-step drum grid with Web Audio" not "add music features".
- If QA report MISSING (cycle > 1) → FIX decision, assume broken.
- If public/index.html MISSING (cycle > 1) → FIX decision.
- If CUSTOMER FEEDBACK exists → make it the priority for this cycle.
- DONE only when: QA=GOOD AND public/index.html exists AND no blockers.
"""


async def ceo_node(state: CompanyState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"]["session"]

    cycle = state["cycle"] + 1
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "ceo", "status": "thinking"})
    await _push_sys(emit, f"🎯 CEO — cycle {cycle} starting")

    qa_report  = read_file(workspace, "docs/qa-report.md")
    roadmap    = read_file(workspace, "docs/product-roadmap.md")
    feedback   = read_file(workspace, "docs/customer-feedback.md")
    # Clear feedback after reading so it only applies to this cycle
    if feedback and not feedback.startswith("(file"):
        write_file(workspace, "docs/customer-feedback.md", "")
    past      = state.get("past_decisions", [])
    past_ctx  = "\n".join(f"  • {d}" for d in past[-5:]) if past else "  (none yet)"

    # Check if the product has ever been delivered
    public_index_exists = Path(workspace, "public", "index.html").exists()

    # Build QA section with explicit warnings when report is missing
    has_qa_report = qa_report and not qa_report.startswith("(file")
    if cycle == 1:
        qa_section = "None yet (first cycle — normal)"
    elif has_qa_report:
        qa_section = qa_report
    else:
        qa_section = (
            "⚠️ QA REPORT IS MISSING — QA agent ran out of time and did not write a report. "
            "You MUST treat this as BLOCKED. Write a FIX decision. Do NOT write a NEW FEATURE decision."
        )

    # Hard warning when nothing has been delivered yet
    deliverable_warning = ""
    if cycle > 1 and not public_index_exists:
        deliverable_warning = (
            "\n🚨 CRITICAL: public/index.html DOES NOT EXIST — the product has never been "
            "successfully built. The preview is blank. You MUST write a FIX decision targeting "
            "the build failure. Writing a NEW FEATURE decision now would add code on top of "
            "broken code that nobody can see. DO NOT write NEW FEATURE."
        )

    feedback_section = ""
    if feedback and not feedback.startswith("(file"):
        feedback_section = f"\n🎯 CUSTOMER FEEDBACK (HIGH PRIORITY — address this cycle):\n{feedback}\n"

    user_msg = f"""Company: {state['brief']}
Type: {state['company_type']}
Cycle: {cycle}
{deliverable_warning}
{feedback_section}
PAST DECISIONS:
{past_ctx}

QA REPORT:
{qa_section}

ROADMAP:
{roadmap if roadmap and not roadmap.startswith('(file') else 'None yet — create it this cycle'}

{f"FOUNDER MESSAGE: {state['founder_override']}" if state.get('founder_override') else ""}

Write docs/feature-priority.md{"and docs/product-roadmap.md" if cycle == 1 else ""}, then stop."""

    async def tool_executor(name: str, inputs: dict):
        if name == "write_file":
            result = write_file(workspace, inputs["path"], inputs["content"])
            if result.get("ok"):
                await _emit_file(emit, session, inputs["path"], inputs["content"], "ceo")
            return json.dumps(result)
        return f"Unknown tool: {name}"

    system = _CEO_SYSTEM.replace("{brief}", state["brief"])

    # Cycle 1: write both docs → stop after roadmap (last write)
    # Cycle 2+: only feature-priority.md → stop immediately after
    stop_files = ["docs/product-roadmap.md"] if cycle == 1 else ["docs/feature-priority.md"]

    _, tokens = await run_agent_with_tools(
        system_prompt=system,
        user_message=user_msg,
        tools=CEO_TOOLS,
        tool_executor=tool_executor,
        emit=emit,
        agent_id="ceo",
        api_key=state["api_key"],
        max_iterations=8,
        session=session,
        stop_after_write=stop_files,
    )

    decision = read_file(workspace, "docs/feature-priority.md")
    is_done  = "done:" in decision.lower()

    # Hard stop after 8 cycles to prevent infinite loops
    if cycle >= 8 and not is_done:
        is_done = True
        await _push_sys(emit, f"🏁 Max cycles reached ({cycle}) — wrapping up")

    past_decisions = list(state.get("past_decisions", []))
    if decision and not decision.startswith("(file"):
        past_decisions.append(f"Cycle {cycle}: {decision[:120]}")

    await emit("agent-status", {"agentId": "ceo", "status": "idle"})

    return {
        "cycle": cycle,
        "ceo_decision": decision,
        "is_done": is_done,
        "past_decisions": past_decisions,
        "total_tokens": session.get("tokens", 0),
        "founder_override": None,
    }


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
    idx   = next((i for i, f in enumerate(files) if f["path"] == path), -1)
    if idx >= 0: files[idx] = entry
    else:        files.append(entry)
    session["files"] = files
    await emit("new-file", entry)
