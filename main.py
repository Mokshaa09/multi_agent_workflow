"""
CLI entry point.

Usage:
    python main.py "your topic here"
"""

import sys
import json
from dotenv import load_dotenv

load_dotenv()  # must run before importing graph/nodes/tools, which read API keys at import time

from graph import build_graph


def main():
    if len(sys.argv) < 2:
        print('Usage: python main.py "your topic"')
        sys.exit(1)

    topic = sys.argv[1]
    print(f"Topic: {topic}")
    print("=" * 60)

    workflow = build_graph()

    initial_state = {
        "topic": topic,
        "sources": [],
        "draft": "",
        "feedback": "",
        "approved": False,
        "revision_count": 0,
        "max_revisions": 2,
    }

    final_state = workflow.invoke(initial_state)

    print("\n" + "=" * 60)
    print("FINAL DRAFT")
    print("=" * 60)
    print(final_state["draft"])

    print("\n" + "-" * 60)
    print(f"Approved: {final_state['approved']}")
    print(f"Revisions used: {final_state['revision_count']} / {final_state['max_revisions']}")
    if not final_state["approved"]:
        print(f"Last feedback (unresolved): {final_state.get('feedback', '')}")
    print(f"Sources used: {[s['url'] for s in final_state['sources']]}")

    with open("last_run.json", "w") as f:
        json.dump(final_state, f, indent=2)
    print("\nFull final state saved to last_run.json")


if __name__ == "__main__":
    main()
