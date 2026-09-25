"""
The three agents (nodes) in the graph.

Each function here has the exact same shape on purpose: it takes the
current WorkflowState, does its one job, and returns a dict of the fields
it wants to update. LangGraph merges that returned dict back into the
overall state before handing it to the next node. This is the core
pattern of a LangGraph node -- read state in, partial state update out.
"""

import os
from google import genai
from state import WorkflowState
from tools import web_search, fetch_page

MODEL = "gemini-flash-lite-latest"

_client_instance = None


def _client() -> genai.Client:
    """
    Reuse a single Gemini client across all nodes instead of creating a new
    one per call. Creating many short-lived clients back-to-back caused
    'Cannot send a request, as the client has been closed' errors -- a
    single shared client avoids that entirely.
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _client_instance


def _ask_gemini(prompt: str) -> str:
    """Small helper: one-shot prompt in, plain text out."""
    response = _client().models.generate_content(model=MODEL, contents=prompt)
    return (response.text or "").strip()


# ---------------------------------------------------------------------------
# Node 1: Researcher
# ---------------------------------------------------------------------------
def researcher_node(state: WorkflowState) -> dict:
    """
    Searches the web for the topic, fetches the most promising page, and
    hands the Writer real material to work from -- not just a bare topic.
    """
    topic = state["topic"]
    print(f"\n[Researcher] Searching for: {topic}")

    results = web_search(topic, max_results=3)
    sources = []
    for r in results[:2]:  # fetch the top 2 to keep this fast and cheap
        content = fetch_page(r["url"])
        sources.append({**r, "content": content})
        print(f"[Researcher] Fetched: {r['url']} ({len(content)} chars)")

    return {"sources": sources}


# ---------------------------------------------------------------------------
# Node 2: Writer
# ---------------------------------------------------------------------------
def writer_node(state: WorkflowState) -> dict:
    """
    Writes (or revises) a short draft using the Researcher's material.
    If there's feedback from a previous Fact-Checker rejection, it must
    address that feedback specifically -- this is what makes the loop
    actually converge instead of repeating the same mistake.
    """
    topic = state["topic"]
    sources = state.get("sources", [])
    feedback = state.get("feedback", "")
    revision_count = state.get("revision_count", 0)

    source_text = "\n\n".join(
        f"SOURCE ({s['url']}):\n{s['content'][:1500]}" for s in sources if s.get("content")
    )

    if feedback:
        print(f"\n[Writer] Revising draft (attempt {revision_count + 1}) based on feedback...")
        prompt = f"""You are a careful writer. Revise your previous draft about "{topic}"
based on this fact-checker feedback: {feedback}

Use only the following source material -- do not invent facts:
{source_text}

Write a short, corrected draft (3-5 sentences)."""
    else:
        print(f"\n[Writer] Writing first draft...")
        prompt = f"""You are a careful writer. Write a short, factual draft (3-5 sentences)
about "{topic}" using ONLY the following source material -- do not invent facts
or add anything not supported by these sources:

{source_text}"""

    draft = _ask_gemini(prompt)
    return {"draft": draft, "revision_count": revision_count + (1 if feedback else 0)}


# ---------------------------------------------------------------------------
# Node 3: Fact-Checker
# ---------------------------------------------------------------------------
def fact_checker_node(state: WorkflowState) -> dict:
    """
    Checks the Writer's draft against the actual fetched source material.
    Returns approved=True/False and, if rejected, specific feedback the
    Writer can act on. This node's decision is what drives the conditional
    edge in the graph.
    """
    draft = state["draft"]
    sources = state.get("sources", [])
    source_text = "\n\n".join(
        f"SOURCE ({s['url']}):\n{s['content'][:1500]}" for s in sources if s.get("content")
    )

    print(f"\n[Fact-Checker] Checking draft against {len(sources)} source(s)...")

    prompt = f"""You are a strict fact-checker. Compare this draft against the source
material below. Check whether every claim in the draft is actually
supported by the sources -- do not judge writing style.

Pay EXTRA scrutiny to any specific number, statistic, percentage, date, or
named quote in the draft. These must appear in the source material in
essentially the same form -- a close paraphrase of a qualitative statement
is fine, but a specific number that does NOT appear in the sources (even
if it sounds plausible) must be REJECTed. If you cannot find a number
explicitly in the source text, treat it as unsupported.

DRAFT:
{draft}

SOURCE MATERIAL:
{source_text}

Respond in EXACTLY this format, nothing else:
VERDICT: APPROVE or REJECT
FEEDBACK: <if REJECT, explain specifically which claim is unsupported and why. If APPROVE, write "none">"""

    result = _ask_gemini(prompt)

    approved = "VERDICT: APPROVE" in result.upper()
    feedback_line = ""
    for line in result.splitlines():
        if line.strip().upper().startswith("FEEDBACK:"):
            feedback_line = line.split(":", 1)[1].strip()

    print(f"[Fact-Checker] Verdict: {'APPROVED' if approved else 'REJECTED'}")
    if not approved:
        print(f"[Fact-Checker] Feedback: {feedback_line}")

    return {"approved": approved, "feedback": feedback_line if not approved else ""}