"""
Blender Studio pipeline graph.

Flow:
    director ──┬─ (recipe matched, cycle 0) ──────────────┐
               └─ scene_architect ────────── build ───────┤
                                                           ▼
                                                     blender_artist
                                                           │
                                                           ▼
                                                       qa_3d  ◄────────┐
                                                     ┌───┴───┐        │
                                                  revise  approved     │ (fix, max 3)
                                                     │       │        │
                                                     └──── qa_fix ─────┘
                                                             │
                                                         animator_3d
                                                             │
                                                         director (review)
                                                             │
                                                     ┌──────┴──────┐
                                                  approved    rebuild (max 3 cycles)
                                                     │            │
                                                     ▼            ▼
                                                 renderer      scene_architect / recipe
                                                     │
                                                    END
"""
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.animator_3d import animator_3d_node
from agents.blender_artist import blender_artist_node
from agents.director_3d import director_3d_node
from agents.qa_3d import qa_3d_node
from agents.renderer_3d import renderer_3d_node
from agents.scene_architect_3d import scene_architect_3d_node
from graph.blender_state import BlenderState

MAX_BUILD_CYCLES = 3
MAX_QA_PASSES = 3
REGRESSION_DELTA = 0.5      # QA score drop that triggers a rebuild instead of more fixes
MAX_REBUILDS = 1            # at most one rebuild per cycle; further regressions force-approve


def _route_after_director(state: BlenderState) -> str:
    """
    After Director reviews:
      - first pass (cycle just incremented to 1) with a matched recipe: go build (scene-plan.json is pre-written).
      - first pass without recipe: go to architect to plan.
      - subsequent passes with APPROVED feedback: go to render.
      - otherwise rebuild (recipe path if matched, else architect).
    """
    cycle = state.get("cycle", 0)
    feedback = state.get("director_feedback", "") or ""
    is_done = state.get("is_done", False)

    if is_done:
        return "done"

    # Right after first creative brief (cycle is now 1)
    if cycle <= 1:
        # Recipe path: spec already on disk → Artist
        if state.get("recipe_name"):
            return "build"
        # Or scene-plan.json was pre-written somehow
        workspace = state.get("workspace_dir", "")
        if workspace and (Path(workspace) / "docs" / "scene-plan.json").exists():
            return "build"
        return "plan"

    # Review after seeing a render
    if "APPROVED" in feedback.upper():
        return "render"

    # Hit iteration cap — accept whatever we have
    if cycle > MAX_BUILD_CYCLES:
        return "render"

    # Need a full rebuild. If recipe was used, still rebuild via architect so
    # the director's corrective notes land in a fresh plan.
    return "plan"


def _route_after_qa(state: BlenderState) -> str:
    """
    QA emits APPROVED or REVISE. Routing rules:
      - verdict APPROVED: advance to animation.
      - reached max passes: force-advance.
      - score regressed vs previous pass by >= REGRESSION_DELTA: route to
        "rebuild" (Artist re-runs initial build from the original spec,
        discarding any fix-induced damage). Only once per cycle.
      - otherwise: normal fix path.
    """
    verdict = (state.get("qa_verdict") or "").upper()
    qa_pass = state.get("qa_pass", 0)
    history = state.get("qa_score_history") or []

    if verdict == "APPROVED":
        return "animate"
    if qa_pass >= MAX_QA_PASSES:
        return "animate"

    # Detect regression: current score is the LAST entry of history.
    if len(history) >= 2:
        delta = history[-2] - history[-1]
        if delta >= REGRESSION_DELTA:
            # Already rebuilt once this cycle? Force-advance rather than loop.
            if state.get("is_rebuild"):
                return "animate"
            return "rebuild"

    return "fix"


def build_blender_graph():
    """Build and compile the Blender Studio agent graph."""
    g = StateGraph(BlenderState)

    g.add_node("director",       director_3d_node)
    g.add_node("scene_architect", scene_architect_3d_node)
    g.add_node("blender_artist",  blender_artist_node)
    g.add_node("qa",              qa_3d_node)
    g.add_node("animator",        animator_3d_node)
    g.add_node("renderer",        renderer_3d_node)

    g.set_entry_point("director")

    g.add_conditional_edges(
        "director",
        _route_after_director,
        {
            "plan":   "scene_architect",
            "build":  "blender_artist",
            "render": "renderer",
            "done":   END,
        },
    )

    g.add_edge("scene_architect", "blender_artist")
    g.add_edge("blender_artist",  "qa")

    g.add_conditional_edges(
        "qa",
        _route_after_qa,
        {
            "fix":     "blender_artist",   # Artist re-runs with qa_fixes in state
            "rebuild": "rebuild",          # regression → rebuild from original spec
            "animate": "animator",
        },
    )

    # Rebuild node: sets is_rebuild=True then dispatches back to Artist.
    # A tiny passthrough node so the Artist's internal logic can branch on state.
    async def _rebuild_node(state: BlenderState, config: dict) -> dict:
        # Clear any lingering fix list so Artist doesn't re-apply; clear verdict.
        return {"is_rebuild": True, "qa_fixes": []}

    g.add_node("rebuild", _rebuild_node)
    g.add_edge("rebuild", "blender_artist")

    g.add_edge("animator", "director")     # Director vision-reviews the scene
    g.add_edge("renderer", END)

    checkpointer = MemorySaver()
    return g.compile(checkpointer=checkpointer)
