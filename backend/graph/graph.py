"""
LangGraph orchestration.
CEO → Lead Engineer → Designer → Developer → QA → CEO (loop)
Exits when CEO decides DONE.
"""
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from graph.state import CompanyState
from agents.ceo import ceo_node
from agents.lead_engineer import lead_engineer_node
from agents.designer import designer_node
from agents.developer import developer_node
from agents.qa import qa_node


def _route_after_ceo(state: CompanyState) -> str:
    if state.get("is_done"):
        return "done"
    return "build"


def build_graph():
    """Build and compile the agent graph with in-memory checkpointing."""
    g = StateGraph(CompanyState)

    g.add_node("ceo", ceo_node)
    g.add_node("lead_engineer", lead_engineer_node)
    g.add_node("designer", designer_node)
    g.add_node("developer", developer_node)
    g.add_node("qa", qa_node)

    g.set_entry_point("ceo")

    # CEO routes to build pipeline or done
    g.add_conditional_edges(
        "ceo",
        _route_after_ceo,
        {"build": "lead_engineer", "done": END},
    )

    # Linear pipeline after CEO
    g.add_edge("lead_engineer", "designer")
    g.add_edge("designer", "developer")
    g.add_edge("developer", "qa")
    g.add_edge("qa", "ceo")  # loop back

    checkpointer = MemorySaver()
    return g.compile(checkpointer=checkpointer)
