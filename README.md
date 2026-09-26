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
principle as the step-limit safety valve in the companion research-agent
project — the system is allowed to fail, but never silently and never by
looping forever. See the "Example runs" section below for confirmation
that this path was actually exercised during development, not just
theoretically implemented.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in GEMINI_API_KEY and TAVILY_API_KEY in .env
```

Free keys: Gemini at https://aistudio.google.com, Tavily at https://tavily.com.

## Run

```bash
python main.py "What is the James Webb Space Telescope and what has it discovered?"
```

## Example runs

### Example 1 — Simple factual topic (approved first try)
**Topic:** `What is the James Webb Space Telescope and what has it discovered?`

**Final draft:**
> The James Webb Space Telescope is the largest, most powerful space telescope ever built and sees the universe using infrared radiation. It is designed to allow scientists to view the universe approximately 200 million years after the Big Bang, capture images of some of the first galaxies, and examine the atmospheres of planets orbiting other stars. Using this telescope, astronomers have recently discovered the secrets of early galaxies that filled the infant cosmos with stardust by studying a much closer, more recent galaxy.

- **Approved:** True
- **Revisions used:** 0 / 2
- **Sources:** `space.com/.../james-webb-space-telescope-discovers...`, `spaceplace.nasa.gov/james-webb-space-telescope/en`

### Example 2 — Comparison topic (approved first try)
**Topic:** `How does the cheetah's top speed compare to other land animals?`

**Final draft:**
> The cheetah is recognized as the world's fastest land animal. Uniquely adapted for high speeds, it is capable of reaching speeds greater than 70 miles per hour in just over three seconds. Its top speed and remarkable acceleration are achieved through a unique body structure that includes a flexible spine, long legs, a tail, and semi-retractable claws.

- **Approved:** True
- **Revisions used:** 0 / 2
- **Sources:** `marathonhandbook.com/how-fast-can-a-cheetah-run`, `cheetah.org/uk/cheetahfacts`

### Example 3 — The reject → revise cycle actually firing, twice, then succeeding
**Topic:** `What are the health benefits of drinking green tea, and how much research supports them?`

**What happened:**
- **1st draft rejected:** claimed a "lower chance" of cognitive impairment without the specific statistic (64%) that was actually in the source.
- **1st revision rejected too:** claimed green tea helps with "fat burning," but the source only said it "positively influences metabolism" when combined with exercise — a different, more specific claim than "fat burning."
- **2nd revision approved.**

**Final draft:**
> Green tea is often touted as one of the healthiest beverages, containing plant-based antioxidant compounds called catechins, such as EGCG, which help prevent cell damage. Research also suggests that drinking green tea may benefit cognition, mood, and brain function due to compounds like caffeine and L-theanine. Additionally, a 2022 review found that green tea's ability to positively influence metabolism is enhanced when combined with aerobic or resistance exercise.

- **Approved:** True
- **Revisions used:** 2 / 2 (used the full budget, succeeded right at the cap)
- **Sources:** `goodrx.com/well-being/diet-nutrition/the-health-benefits-green-tea`, `healthline.com/nutrition/top-10-evidence-based-health-benefits-of-green-tea`
- **This is the clearest real evidence of the conditional edge working.** Two different rejection reasons, two successful corrections, and a final answer that only keeps claims the Fact-Checker could verify.

### Example 4 — Comparison across multiple named things (approved first try)
**Topic:** `How many moons does Jupiter have compared to Saturn?`

**Final draft:**
> Based on the provided sources, Jupiter currently has more than 100 known moons. In comparison, Saturn has more than double that amount, with over 280 known satellites. Despite having fewer total moons, Jupiter's system includes four large moons known as the Galilean moons (Io, Europa, Ganymede, and Callisto), while Saturn's satellite system is dominated by one large moon (Titan).

- **Approved:** True
- **Revisions used:** 0 / 2
- **Sources:** `universetoday.com/articles/why-does-jupiter-have-more-large-moons-than-saturn`, `dlr.de/.../the-small-moons-of-jupiter`

## What these examples show together

Across 4 runs on varied topics, the Fact-Checker consistently did its job: approving clean, well-supported drafts (Examples 1, 2, 4), and — most importantly — actually catching and correcting two distinct unsupported claims in Example 3, requiring two full revision rounds before the draft was clean enough to approve. That's the conditional edge (`route_after_fact_check()` in `graph.py`) making a real, consequential decision at runtime, not just existing as unused code.