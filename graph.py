"""
The graph: wires Researcher -> Writer -> Fact-Checker together, with a
CONDITIONAL edge after the Fact-Checker that either finishes the workflow
or sends it back to the Writer for another revision.

This conditional edge is the actual "brief requirement" this project hinges
on: it's a real decision point where the graph's path changes based on
what happened at runtime, not a fixed straight line.
"""

from langgraph.graph import StateGraph, END
from state import WorkflowState
from nodes import researcher_node, writer_node, fact_checker_node


def route_after_fact_check(state: WorkflowState) -> str:
    """
    This function IS the conditional edge. LangGraph calls it after the
    fact_checker node runs, and whatever string it returns tells LangGraph
    which node to go to next.

    Two ways out of the loop:
      1. approved == True -> we're done
      2. revision_count has hit max_revisions -> we give up gracefully,
         same safety-valve idea as the step limit in Project #1
    """
    if state.get("approved"):
        return "done"
    if state.get("revision_count", 0) >= state.get("max_revisions", 2):
        return "give_up"
    return "revise"


def build_graph():
    graph = StateGraph(WorkflowState)

    graph.add_node("researcher", researcher_node)
    graph.add_node("writer", writer_node)
    graph.add_node("fact_checker", fact_checker_node)

    graph.set_entry_point("researcher")
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", "fact_checker")

    # The conditional edge: fact_checker's output decides what happens next.
    graph.add_conditional_edges(
        "fact_checker",
        route_after_fact_check,
        {
            "done": END,       # approved -> stop, we're finished
            "give_up": END,    # hit the revision cap -> stop, but honestly
            "revise": "writer" # rejected, budget remains -> back to Writer
        },
    )

    return graph.compile()
