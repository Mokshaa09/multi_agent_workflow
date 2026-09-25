"""
Simple web tools, reused from Project #1 (the Research Agent).

Unlike Project #1, agents here don't dynamically decide when to call these --
the Researcher node just calls them directly as a normal function call, since
its whole job every time is "search and fetch." Keeping this simple and
predictable is deliberate: the complexity in THIS project lives in the graph
structure (multiple agents, conditional routing), not in tool-selection.
"""

import os
import requests
from tavily import TavilyClient

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
_tavily_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None


def web_search(query: str, max_results: int = 3) -> list[dict]:
    """Search the web. Returns a list of {title, url, snippet} dicts, or [] on failure."""
    if not _tavily_client:
        return []
    try:
        response = _tavily_client.search(query=query, max_results=max_results, search_depth="basic")
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")[:400]}
            for r in response.get("results", [])
        ]
    except Exception:
        return []


def fetch_page(url: str, max_chars: int = 3000) -> str:
    """Fetch a URL's readable text. Returns '' on failure."""
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (multi-agent-workflow/0.1)"})
        resp.raise_for_status()
        text = resp.text
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
        except ImportError:
            pass
        return text[:max_chars]
    except Exception:
        return ""
