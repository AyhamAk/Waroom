"""
BlenderState — TypedDict for the Blender Studio pipeline.
"""
from typing import Optional
from typing_extensions import TypedDict


class BlenderState(TypedDict):
    # Session identity
    session_id: str
    workspace_dir: str          # absolute path to per-session workspace
    api_key: str

    # User inputs
    product_description: str
    product_image_path: Optional[str]   # abs path to uploaded product PNG/JPEG
    style: str                          # "commercial" | "cinematic" | "scifi" | "luxury"

    # Agent outputs (overwritten each cycle)
    scene_concept: str          # director's creative brief (docs/scene-concept.md)
    scene_plan: str             # architect's JSON spec (docs/scene-plan.json)
    recipe_name: Optional[str]  # if a recipe matched and was used

    # Render artefacts
    latest_render_path: Optional[str]   # abs path to most recent preview PNG
    video_path: Optional[str]           # abs path to final output.mp4

    # Control flow
    cycle: int
    is_done: bool
    director_feedback: str      # "APPROVED" or improvement notes

    # QA loop state
    qa_pass: int                # how many QA passes for the current cycle
    qa_verdict: str             # "APPROVED" | "REVISE"
    qa_score: float             # 0-10
    qa_fixes: list              # list of {op, args} typed fix ops
    qa_report: str              # raw JSON report
    qa_score_history: list      # [score_pass1, score_pass2, ...] for regression detection
    is_rebuild: bool            # True when Artist should rebuild from spec instead of applying fixes

    # Token accounting
    total_tokens: int


def make_blender_state(
    session_id: str,
    workspace_dir: str,
    api_key: str,
    product_description: str,
    style: str,
    product_image_path: Optional[str] = None,
) -> BlenderState:
    return BlenderState(
        session_id=session_id,
        workspace_dir=workspace_dir,
        api_key=api_key,
        product_description=product_description,
        product_image_path=product_image_path,
        style=style,
        scene_concept="",
        scene_plan="",
        recipe_name=None,
        latest_render_path=None,
        video_path=None,
        cycle=0,
        is_done=False,
        director_feedback="",
        qa_pass=0,
        qa_verdict="",
        qa_score=0.0,
        qa_fixes=[],
        qa_report="",
        qa_score_history=[],
        is_rebuild=False,
        total_tokens=0,
    )
