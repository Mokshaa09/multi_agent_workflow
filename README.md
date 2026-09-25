# Multi-Agent Workflow: Researcher → Writer → Fact-Checker

A LangGraph pipeline where three specialized agents hand work to each
other: a Researcher gathers real sources, a Writer drafts from them, and
a Fact-Checker verifies the draft against the actual sources -- sending it
back to the Writer for revision if a claim isn't supported.

## Architecture

```
   ┌─────────────┐      ┌────────┐      ┌──────────────┐
   │ Researcher  │ ───► │ Writer │ ───► │ Fact-Checker │
   └─────────────┘      └────────┘      └──────┬───────┘
                              ▲                  │
                              │                  ▼
                              │           approved? ──► END (done)
                              │                  │
                              └── no, revise ─────┘
                                  (up to 2x, then
                                   give up gracefully)
```

- **Researcher** — searches the web for the topic, fetches the top pages,
  hands the Writer real source material (not just the bare topic).
- **Writer** — drafts a short piece using only that source material. On a
  revision round, it's also given the Fact-Checker's specific feedback and
  must address it.
- **Fact-Checker** — the conditional decision point. Compares the draft
  against the actual fetched sources and returns `APPROVE` or `REJECT` with
  specific feedback.

## The state schema

All three nodes read from and write to one shared `WorkflowState` (see
`state.py`):

```python
class WorkflowState(TypedDict):
    topic: str
    sources: list[dict]     # what the Researcher found
    draft: str               # the Writer's current draft
    feedback: str             # Fact-Checker's notes, if rejected
    approved: bool             # True once Fact-Checker signs off
    revision_count: int         # how many times we've looped back
    max_revisions: int           # hard cap on the loop
```

## The conditional edge

This is the graph's actual decision point, implemented in
`route_after_fact_check()` in `graph.py`:

- If the Fact-Checker approved → route to `END`.
- If rejected but revisions remain → route back to `writer`.
- If rejected AND the revision cap is hit → route to `END` anyway (give up
  gracefully rather than loop forever).

## What happens if the Fact-Checker rejects twice

This is handled explicitly, not left to chance:

`max_revisions` is set to `2`. Each time the Writer revises in response to
feedback, `revision_count` increments. If the Fact-Checker rejects a second
time and `revision_count` has reached `max_revisions`, the router's
`give_up` branch fires instead of `revise` — the graph ends immediately
rather than sending it back to the Writer a third time.

Critically, the program does **not** pretend the result is good: the final
printed output shows `Approved: False` and prints the Fact-Checker's last
unresolved feedback alongside the draft, so whoever reads the output knows
exactly what wasn't verified and why. This mirrors the same design
principle as the step-limit safety valve in Project #1 (the Research
Agent) — the system is allowed to fail, but never silently and never by
looping forever.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in GEMINI_API_KEY and TAVILY_API_KEY in .env
```

Free keys: Gemini at https://aistudio.google.com, Tavily at https://tavily.com.

## Run

```bash
python main.py "What is the Model Context Protocol?"
```

## Example runs

### Example 1 — Straightforward factual topic (approved first try)
**Topic:** `What is the Model Context Protocol?`

**Final draft:**
> The Model Context Protocol (MCP) is an open standard and open-source framework introduced by Anthropic in November 2024 to standardize how AI systems and LLMs integrate and share data with external tools, systems, and data sources. Created by engineers David Soria Parra and Justin Spahr-Summers, MCP addresses information silos and the "N×M integration problem" by providing a consistent interface for reading files, executing functions, and handling contextual prompts. The protocol acts like a USB-C port for AI systems... Following its announcement, MCP has been adopted by major AI providers, including OpenAI and Google DeepMind.

- **Approved:** True
- **Revisions used:** 0 / 2
- **Sources:** `en.wikipedia.org/wiki/Model_Context_Protocol`, `databricks.com/blog/what-is-model-context-protocol`

### Example 2 — Security-focused topic (approved first try, despite an incomplete source)
**Topic:** `What are the security risks of the Model Context Protocol?`

**Final draft:**
> The Model Context Protocol (MCP) is an open standard launched by Anthropic in November 2024 to enable AI assistants to interact with external tools and services on behalf of users. It standardizes how applications provide context to LLMs by acting as a universal interface layer... replacing fragmented integrations with a single protocol.

- **Approved:** True
- **Revisions used:** 0 / 2
- **Sources:** `live.paloaltonetworks.com/...mcp-security-exposed...`, `pillar.security/blog/the-security-risks-of-model-context-protocol-mcp`
- **Notable:** one fetched source returned 0 characters (likely a JavaScript-heavy page our simple fetcher couldn't read), demonstrating the system continuing gracefully on a partial source rather than crashing.

### Example 3 — Comparison topic that genuinely exercised the reject → revise loop
**Topic:** `How does MCP adoption compare in speed to older API integration standards?`

**Final draft:**
> Anthropic's Model Context Protocol (MCP) has experienced an unusually rapid growth trajectory since its publication in November 2024. Eighteen months later, it has evolved into the de facto integration standard for the enterprise AI economy, achieving 41% enterprise adoption by 2026. The protocol overall has hit 97 million downloads, alongside significant adoption of its TypeScript and Python SDKs...

- **Approved:** False
- **Revisions used:** 2 / 2 (hit the safety cap)
- **Last unresolved feedback:** *"The draft claims 'The protocol overall has hit 97 million downloads'... The source text states that 'MCP's TypeScript and Python SDKs reached 97 million [downloads]', meaning the 97 million applies to the SDKs specifically, not the protocol overall."*
- **This is the real example of the double-rejection case described above.** The Writer twice attributed an SDK-specific download figure to the protocol as a whole, a subtle misattribution the Fact-Checker correctly caught both times. After the second rejection, the graph's `give_up` branch fired exactly as designed: it stopped looping, returned the best available draft, and printed `Approved: False` plus the exact unresolved feedback — an honest failure rather than a silent one.

## What this proves

Example 3 isn't a hypothetical description of what *would* happen on a double rejection — it's a real run where it actually happened, caught by making the Fact-Checker specifically scrutinize numeric claims against source text rather than accepting plausible-sounding paraphrases.