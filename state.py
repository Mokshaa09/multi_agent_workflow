"""
The shared state that flows through the graph.

Every node (Researcher, Writer, Fact-Checker) receives this whole dict,
reads whatever it needs, and returns updates to merge into it. This is
what the brief calls the "state schema" -- the single source of truth
that lets agents that never talk to each other directly still coordinate,
because they all read and write the same shared object.
"""

from typing import TypedDict


class WorkflowState(TypedDict):
    topic: str              # the user's original question/topic
    sources: list[dict]     # [{title, url, snippet, content}, ...] from the Researcher
    draft: str               # the Writer's current draft
    feedback: str             # the Fact-Checker's notes on the most recent draft
    approved: bool             # True once the Fact-Checker signs off
    revision_count: int         # how many times the Writer has revised -- our safety valve
    max_revisions: int           # hard cap, so the loop can never run forever
