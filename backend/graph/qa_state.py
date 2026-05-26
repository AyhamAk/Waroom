"""QA Swarm pipeline state."""
from typing import Optional
from typing_extensions import TypedDict


class QAState(TypedDict):
    session_id: str
    workspace_dir: str
    api_key: str
    target_url: str
    site_map: list          # discovered URLs
    test_plan: str          # scout's summary
    bugs: list              # final bug list (copied from session at end)
    agent_reports: dict     # per-agent summary strings
    synthesis: str          # final markdown report
    total_tokens: int
    is_done: bool


def make_qa_state(
    session_id: str,
    workspace_dir: str,
    api_key: str,
    target_url: str,
) -> QAState:
    return QAState(
        session_id=session_id,
        workspace_dir=workspace_dir,
        api_key=api_key,
        target_url=target_url,
        site_map=[],
        test_plan="",
        bugs=[],
        agent_reports={},
        synthesis="",
        total_tokens=0,
        is_done=False,
    )
