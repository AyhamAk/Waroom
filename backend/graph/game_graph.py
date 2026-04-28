"""
Game Studio LangGraph pipeline.

Flow:

  director (cycle 1) ──► level_designer ──► asset_lead ──► engine_engineer
                                                                   │
                                                                   ▼
                                                              tech_art
                                                                   │
                                                                   ▼
                                                          gameplay_programmer
                                                                   │
                                                                   ▼
                                                          vision_playtester ◄──┐
                                                            ┌─────┴─────┐      │
                                                          revise   approved    │ (fix, max 3)
                                                            │           │      │
                                                            ▼           ▼      │
                                                         qa_fix      director ◄┘ (review)
                                                            │           │
                                                            └───────────┘
                                                                ┌──────┴──────┐
                                                              done       rebuild (max 1)
                                                                │              │
                                                                ▼              ▼
                                                              END        gameplay_programmer

The shape is identical to the Blender pipeline so the same hardening
patterns apply: regression detection, bounded fix passes, rebuild
fallback when a fix attempt regresses badly.
"""
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.asset_lead import asset_lead_node
from agents.engine_engineer import engine_engineer_node
from agents.game_director import game_director_node
from agents.gameplay_programmer import gameplay_programmer_node
from agents.level_designer import level_designer_node
from agents.tech_art import tech_art_node
from agents.vision_playtester import vision_playtester_node
from graph.game_state import GameState
from templates.game_base import scaffold_game_workspace


MAX_PLAYTEST_PASSES = 3
REGRESSION_DELTA = 0.5
MAX_REBUILDS_PER_CYCLE = 1


def _route_after_director(state: GameState) -> str:
    """
    After Director:
      - Cycle 1: go to level_designer.
      - Later cycles (review pass): APPROVED → END, otherwise rebuild back
        to gameplay_programmer with the director's notes in feedback.
    """
    cycle = state.get("cycle", 0)
    if state.get("is_done"):
        return "done"
    if cycle <= 1:
        return "design"
    return "rebuild"


def _route_after_playtester(state: GameState) -> str:
    """
    After playtester:
      - APPROVED → director (review).
      - Hit max passes → director (force-review).
      - Score regressed by >= REGRESSION_DELTA → rebuild (once per cycle).
      - Otherwise → fix pass via gameplay_programmer.
    """
    verdict = (state.get("playtest_verdict") or "").upper()
    pass_no = state.get("playtest_pass", 0)
    history = state.get("playtest_score_history") or []

    if verdict == "APPROVED":
        return "review"
    if pass_no >= MAX_PLAYTEST_PASSES:
        return "review"

    if len(history) >= 2 and (history[-2] - history[-1]) >= REGRESSION_DELTA:
        if state.get("is_rebuild"):
            return "review"
        return "rebuild"

    return "fix"


async def _scaffold_node(state: GameState, config: dict) -> dict:
    """
    Idempotent scaffold step — copies templates/game_base/ into
    workspace/game/ so every downstream agent starts from a working
    baseline. Cheap to re-run; only fills missing files.

    Returns a no-op state write — `{"is_rebuild": False}` — to satisfy
    LangGraph 0.2.x's contract that every node must touch at least one
    state field. (SqliteSaver enforces this strictly; MemorySaver is more
    lenient, which is why the pipeline appeared to work in early tests.)
    """
    workspace = state["workspace_dir"]
    scaffold_game_workspace(workspace)
    return {"is_rebuild": False}


async def _rebuild_node(state: GameState, config: dict) -> dict:
    """Set the rebuild flag, clear any pending fixes, and bounce back to gameplay."""
    return {"is_rebuild": True, "playtest_fixes": []}


def build_game_graph(checkpointer=None):
    """Compile the game graph.

    Pass a `checkpointer` (e.g. AsyncSqliteSaver) to enable resume-across-
    restart. Defaults to MemorySaver for in-memory only execution.
    """
    g = StateGraph(GameState)

    g.add_node("scaffold",            _scaffold_node)
    g.add_node("director",            game_director_node)
    g.add_node("level_designer",      level_designer_node)
    g.add_node("asset_lead",          asset_lead_node)
    g.add_node("engine_engineer",     engine_engineer_node)
    g.add_node("tech_art",            tech_art_node)
    g.add_node("gameplay_programmer", gameplay_programmer_node)
    g.add_node("playtester",          vision_playtester_node)
    g.add_node("rebuild",             _rebuild_node)

    g.set_entry_point("scaffold")
    g.add_edge("scaffold", "director")

    g.add_conditional_edges(
        "director",
        _route_after_director,
        {"design": "level_designer", "rebuild": "gameplay_programmer", "done": END},
    )

    # Linear creative chain.
    g.add_edge("level_designer",      "asset_lead")
    g.add_edge("asset_lead",          "engine_engineer")
    g.add_edge("engine_engineer",     "tech_art")
    g.add_edge("tech_art",            "gameplay_programmer")
    g.add_edge("gameplay_programmer", "playtester")

    # Playtest loop.
    g.add_conditional_edges(
        "playtester",
        _route_after_playtester,
        {
            "fix":     "gameplay_programmer",   # apply typed fixes
            "rebuild": "rebuild",                # discard fixes, redo gameplay
            "review":  "director",               # director makes the final call
        },
    )
    g.add_edge("rebuild", "gameplay_programmer")

    if checkpointer is None:
        checkpointer = MemorySaver()
    return g.compile(checkpointer=checkpointer)
