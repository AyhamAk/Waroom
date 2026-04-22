import asyncio
import os
import sys


async def run_command(workspace: str, command: str, timeout: int = 60) -> dict:
    """
    Run a shell command in the workspace directory.
    Handles background processes (commands ending with &).
    Returns stdout, stderr, returncode.
    """
    is_background = command.strip().endswith("&")
    if is_background:
        command = command.strip()[:-1].strip()

    try:
        if sys.platform == "win32":
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ},
            )
        else:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ},
            )

        if is_background:
            # Give it 3 seconds to start, don't wait for completion
            await asyncio.sleep(3)
            stdout_data = b""
            stderr_data = b""
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(), timeout=0.1
                )
            except (asyncio.TimeoutError, Exception):
                pass
            return {
                "stdout": stdout_data.decode("utf-8", errors="replace")[:1000] or f"Background process started (PID {proc.pid})",
                "stderr": stderr_data.decode("utf-8", errors="replace")[:500],
                "returncode": 0,
                "success": True,
                "background": True,
            }

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return {
                "stdout": stdout_data.decode("utf-8", errors="replace")[:4000],
                "stderr": stderr_data.decode("utf-8", errors="replace")[:1000],
                "returncode": proc.returncode,
                "success": proc.returncode == 0,
                "background": False,
            }
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "returncode": -1,
                "success": False,
                "background": False,
            }

    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "success": False,
            "background": False,
        }
