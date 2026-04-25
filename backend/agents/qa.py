"""
QA Agent — actually tests the code by running it.
Uses run_command to execute real test scenarios.
CRITICAL: Always writes docs/qa-report.md — even partial results beat no report.
"""
import json
import time
from typing import Callable

from agents.base import (
    LIST_FILES_TOOL, READ_FILE_TOOL, RUN_COMMAND_TOOL,
    WRITE_FILE_TOOL, run_agent_with_tools,
)
from graph.state import CompanyState
from tools.code_runner import run_command
from tools.file_ops import list_files, read_file, write_file

QA_TOOLS = [LIST_FILES_TOOL, READ_FILE_TOOL, RUN_COMMAND_TOOL, WRITE_FILE_TOOL]

_QA_SYSTEM_NPM = """You are a QA Engineer. You test code by RUNNING it. You MUST write docs/qa-report.md.

TOOLS:
- list_files: See what was built
- read_file: Read source files when needed
- run_command: Execute installs, builds, tests
- write_file: Write the QA report

WORKFLOW — STRICT ORDER, do not skip or reorder:
1. Find the project dir (where package.json lives)
2. run_command: "cd <project> && npm install" (timeout: 90)
3. run_command: "cd <project> && npm run build" (timeout: 90)
4. ★ WRITE docs/qa-report.md IMMEDIATELY with the build result ★
   Do this NOW — before any other action. This is your #1 job.
5. STOP. You are done.

After step 4, stop immediately. Do not run more commands. Do not summarize.

REPORT FORMAT:
# QA Report — Cycle [N]

## Build
**Status**: PASS / FAIL
**Command**: (exact command)
**Error**: (full error if FAIL)

## Verdict
GOOD — ready for next feature
BLOCKED — [specific: file:line — error — fix]

WINDOWS: "cd dir && command" syntax. "dir" not "ls".
"""

_QA_SYSTEM_VANILLA = """You are a QA Engineer. This is a vanilla JS project (no build step).

TOOLS:
- read_file: Read source files
- run_command: Validate JS files
- write_file: Write the QA report

WORKFLOW — 3 steps max:
1. Verify public/index.html exists (you already know this — it was confirmed)
2. For each .js file in public/: run "node --check public/js/app.js" (or whichever files exist)
3. ★ WRITE docs/qa-report.md IMMEDIATELY ★ then STOP.

Do not install packages. Do not create package.json. Do not run npm.
Do not do anything except validate JS syntax and write the report.

REPORT FORMAT:
# QA Report — Cycle [N]

## Build
**Status**: PASS (vanilla JS, no build needed)
**Checks**: node --check results

## Verdict
GOOD — ready for next feature
NEEDS FIXES — [specific: file:line — error]

After writing the report, stop immediately.
"""


async def qa_node(state: CompanyState, config: dict) -> dict:
    emit: Callable = config["configurable"]["emit"]
    session: dict = config["configurable"]["session"]
    workspace = state["workspace_dir"]

    await emit("agent-status", {"agentId": "qa", "status": "working"})
    await _push_sys(emit, "🔍 QA — testing what was built")

    ceo_decision = read_file(workspace, "docs/feature-priority.md")
    all_files = list_files(workspace)
    file_paths = [f["path"] for f in all_files]

    # Detect project type — vanilla JS has no package.json outside public/
    has_npm = any(
        p.endswith("package.json") and not p.startswith("public/") and not p.startswith("docs/")
        for p in file_paths
    )
    has_public_index = any(p == "public/index.html" for p in file_paths)
    public_js_files = [p for p in file_paths if p.startswith("public/") and p.endswith(".js")]

    if has_npm:
        project_dirs = list({f["path"].split("/")[0] for f in all_files
                             if "/" in f["path"] and not f["path"].startswith("docs/")
                             and not f["path"].startswith("logs/") and not f["path"].startswith("public/")})
        qa_system = _QA_SYSTEM_NPM
        max_iter = 10
        proj_dir = project_dirs[0] if project_dirs else 'unknown'
        has_modules = any(p.startswith(f"{proj_dir}/node_modules/") for p in file_paths)
        install_note = "SKIP npm install (node_modules already exists)" if has_modules else "Run npm install first"

        user_msg = f"""Company: {state['brief']}
Cycle: {state['cycle']}

FEATURE: {ceo_decision}

PROJECT DIR: {proj_dir}
{install_note}

Steps: {"npm run build" if has_modules else "npm install → npm run build"} → write docs/qa-report.md → STOP."""
    else:
        qa_system = _QA_SYSTEM_VANILLA
        max_iter = 5
        public_index_status = "EXISTS" if has_public_index else "MISSING — BLOCKED"
        user_msg = f"""Company: {state['brief']}
Cycle: {state['cycle']}

FEATURE: {ceo_decision}

PROJECT TYPE: Vanilla JS (no package.json — skip npm entirely)
public/index.html: {public_index_status}
JS files in public/: {json.dumps(public_js_files)}

Steps:
1. run node --check on each JS file listed above
2. Write docs/qa-report.md with results
3. STOP."""

    async def tool_executor(name: str, inputs: dict):
        if name == "read_file":
            return read_file(workspace, inputs["path"])
        if name == "list_files":
            return json.dumps(list_files(workspace, inputs.get("subdir", "")))
        if name == "run_command":
            timeout = min(int(inputs.get("timeout", 60)), 120)
            result = await run_command(workspace, inputs["command"], timeout=timeout)
            summary = []
            if result["stdout"]:
                summary.append(f"STDOUT:\n{result['stdout'][:2000]}")
            if result["stderr"] and result["stderr"].strip():
                summary.append(f"STDERR:\n{result['stderr'][:1000]}")
            summary.append(f"Exit: {result['returncode']} ({'OK' if result['success'] else 'FAIL'})")
            return "\n".join(summary)
        if name == "write_file":
            result = write_file(workspace, inputs["path"], inputs["content"])
            if result.get("ok"):
                await _emit_file(emit, session, inputs["path"], inputs["content"], "qa")
            return json.dumps(result)
        return f"Unknown tool: {name}"

    await run_agent_with_tools(
        system_prompt=qa_system,
        user_message=user_msg,
        tools=QA_TOOLS,
        tool_executor=tool_executor,
        emit=emit,
        agent_id="qa",
        api_key=state["api_key"],
        max_tokens=4000,
        max_iterations=max_iter,
        session=session,
        stop_after_write=["docs/qa-report.md"],
    )

    qa_report = read_file(workspace, "docs/qa-report.md")
    await emit("agent-status", {"agentId": "qa", "status": "idle"})

    return {"qa_report": qa_report, "total_tokens": session.get("tokens", 0)}


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
