"""
Core agentic loop engine.
Each agent gets tools, runs until task_complete or max_iterations.
The LLM decides every action — this is what makes it a real agent.

IMPORTANT: The Anthropic sync client blocks the event loop.
We run it in a thread executor so SSE streams stay live, Ctrl+C works,
and /api/stop can cancel mid-call.
"""
import asyncio
import json
import time
from typing import Callable, Coroutine

import anthropic


async def run_agent_with_tools(
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    tool_executor: Callable[..., Coroutine],
    emit: Callable[..., Coroutine],
    agent_id: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 8096,
    max_iterations: int = 25,
    session: dict | None = None,
    stop_after_write: list[str] | None = None,
) -> tuple[str, int]:
    """
    Run an agent in a tool-use loop until it stops calling tools or hits max_iterations.
    Returns (final_text, total_tokens_used).
    API calls run in thread executor — event loop stays free for SSE + signals.
    """
    client = anthropic.Anthropic(api_key=api_key)
    messages: list[dict] = [{"role": "user", "content": user_message}]
    total_tokens = 0
    _msg_counter = [0]
    loop = asyncio.get_event_loop()

    async def push(msg_type: str, text: str, to: str | None = None):
        _msg_counter[0] += 1
        await emit("new-message", {
            "from": agent_id,
            "to": to,
            "type": msg_type,
            "message": text,
            "id": _msg_counter[0],
            "timestamp": int(time.time() * 1000),
        })
        # Also write to session log
        if session and session.get("workspace_dir"):
            _log(session["workspace_dir"], agent_id, msg_type, text)

    for iteration in range(max_iterations):
        # Run the blocking Anthropic call in a thread — keeps event loop free
        try:
            msgs_snapshot = list(messages)
            response = await loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    tools=tools,
                    messages=msgs_snapshot,
                ),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await push("communicate", f"⚠️ API error: {str(exc)[:120]}")
            break

        tokens_used = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)
        total_tokens += tokens_used

        # Update running total in session and emit immediately with real value
        if session is not None:
            session["tokens"] = session.get("tokens", 0) + tokens_used
            await emit("token-update", {"delta": tokens_used, "total": session["tokens"]})

        # Surface agent thinking text
        for block in response.content:
            if hasattr(block, "text") and block.text and block.text.strip():
                display = block.text.strip()[:400]
                await push("communicate", display)

        if response.stop_reason == "end_turn":
            final_text = " ".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            return final_text, total_tokens

        if response.stop_reason == "max_tokens":
            await push("communicate", "⚠️ Output truncated at token limit. Recovering.")
            # Anthropic requires tool_result for every tool_use in the assistant message.
            # If we send plain text instead we get a 400. Find all tool_use ids first.
            tool_use_ids = [
                b.id for b in response.content
                if hasattr(b, "type") and b.type == "tool_use" and hasattr(b, "id")
            ]
            messages.append({"role": "assistant", "content": response.content})
            if tool_use_ids:
                messages.append({"role": "user", "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tid,
                        "content": (
                            "Response was cut off before this tool call completed. "
                            "Retry: call write_file again with the COMPLETE content. "
                            "Split into multiple smaller files (max 300 lines each) if needed."
                        ),
                    }
                    for tid in tool_use_ids
                ]})
            else:
                messages.append({"role": "user", "content": [
                    {"type": "text", "text": "Your response was cut off. Continue and complete your task — split large files into smaller ones if needed."}
                ]})
            continue

        if response.stop_reason == "tool_use":
            tool_results: list[dict] = []
            wrote_stop_file = False

            for block in response.content:
                if block.type != "tool_use":
                    continue

                input_preview = json.dumps(block.input)[:120]
                await push("communicate", f"🔧 `{block.name}` ← {input_preview}")

                try:
                    result = await tool_executor(block.name, block.input)
                    result_str = str(result) if result is not None else "ok"
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    result_str = f"TOOL ERROR: {exc}"

                if len(result_str) > 20:
                    await push("communicate", f"↩ {result_str[:300]}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str[:6000],
                })

                # Stop immediately after writing a key file — no summary call needed
                if stop_after_write and block.name == "write_file":
                    written_path = block.input.get("path", "")
                    if any(written_path == s or written_path.endswith("/" + s) for s in stop_after_write):
                        wrote_stop_file = True

            if wrote_stop_file:
                return "Done", total_tokens

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    return "Agent reached max iterations", total_tokens


def _log(workspace_dir: str, agent_id: str, msg_type: str, text: str):
    """Append a line to logs/session.log — non-critical, never raises."""
    try:
        import os
        log_path = os.path.join(workspace_dir, "logs", "session.log")
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] [{agent_id.upper():12}] {text[:200]}\n"
        with open(log_path, "a", encoding="utf-8", errors="replace") as f:
            f.write(line)
    except Exception:
        pass


# ── Standard tool schemas ────────────────────────────────────────────────────

READ_FILE_TOOL = {
    "name": "read_file",
    "description": "Read any file from the workspace",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "File path relative to workspace"}},
        "required": ["path"],
    },
}

WRITE_FILE_TOOL = {
    "name": "write_file",
    "description": "Write content to a file (creates directories as needed)",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to workspace"},
            "content": {"type": "string", "description": "Full file content to write"},
        },
        "required": ["path", "content"],
    },
}

LIST_FILES_TOOL = {
    "name": "list_files",
    "description": "List all files in the workspace (or a subdirectory)",
    "input_schema": {
        "type": "object",
        "properties": {"subdir": {"type": "string", "description": "Subdirectory to list (optional, default: all)"}},
    },
}

RUN_COMMAND_TOOL = {
    "name": "run_command",
    "description": (
        "Execute a shell command in the workspace. "
        "Use for: installing packages (npm install, pip install), running code, "
        "starting servers (append & for background), running tests, building projects. "
        "Returns stdout, stderr, and exit code."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 60, max 120)"},
        },
        "required": ["command"],
    },
}

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for research, documentation, best practices, or competitive analysis. "
        "If search fails or returns a rate limit error, skip it and use your own knowledge."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Search query"}},
        "required": ["query"],
    },
}
