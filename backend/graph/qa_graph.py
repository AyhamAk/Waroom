"""QA Swarm LangGraph pipeline.

Flow:
  scout_node → parallel_qa_node → synthesize_node → END

scout_node    — Playwright discovery: maps routes, forms, links
parallel_qa_node — runs 5 QA agents concurrently via asyncio.gather
synthesize_node — writes bugs.json + report.md, marks done
"""
from langgraph.graph import END, StateGraph, START

from agents.qa_agents import parallel_qa_node, scout_node, synthesis_node
from graph.qa_state import QAState


def build_qa_graph():
    builder = StateGraph(QAState)
    builder.add_node("scout",       scout_node)
    builder.add_node("parallel_qa", parallel_qa_node)
    builder.add_node("synthesize",   synthesis_node)
    builder.add_edge(START,        "scout")
    builder.add_edge("scout",      "parallel_qa")
    builder.add_edge("parallel_qa","synthesize")
    builder.add_edge("synthesize",   END)
    return builder.compile()
