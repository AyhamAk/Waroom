from typing import Optional
from typing_extensions import TypedDict


class CompanyState(TypedDict):
    # Session identity
    session_id: str
    workspace_dir: str
    provider: str
    api_key: str

    # Company config
    brief: str
    company_type: str

    # Cycle tracking
    cycle: int

    # Agent outputs (updated each cycle)
    ceo_decision: str
    tech_spec: str
    design_spec: str
    qa_report: str

    # History (appended each cycle)
    past_decisions: list

    # Control flow
    is_done: bool
    founder_override: Optional[str]

    # Running token total (updated by nodes)
    total_tokens: int


def make_initial_state(
    session_id: str,
    workspace_dir: str,
    brief: str,
    company_type: str,
    provider: str,
    api_key: str,
) -> CompanyState:
    return CompanyState(
        session_id=session_id,
        workspace_dir=workspace_dir,
        provider=provider,
        api_key=api_key,
        brief=brief,
        company_type=company_type,
        cycle=0,
        ceo_decision="",
        tech_spec="",
        design_spec="",
        qa_report="",
        past_decisions=[],
        is_done=False,
        founder_override=None,
        total_tokens=0,
    )
