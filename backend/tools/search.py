import json

try:
    from duckduckgo_search import DDGS
    _HAS_DDGS = True
except ImportError:
    _HAS_DDGS = False


def web_search(query: str, max_results: int = 5) -> str:
    if not _HAS_DDGS:
        return json.dumps([{"title": "Search unavailable", "body": "Use your own knowledge.", "url": ""}])
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return json.dumps([{"title": "No results", "body": "No results found. Use your own knowledge.", "url": ""}])
        return json.dumps([
            {"title": r.get("title", ""), "body": r.get("body", "")[:400], "url": r.get("href", "")}
            for r in results
        ], indent=2)
    except Exception as e:
        err = str(e)
        # Rate limit — tell agent to skip, not retry
        if "202" in err or "Ratelimit" in err or "ratelimit" in err.lower():
            return json.dumps([{
                "title": "Rate limited",
                "body": "Search rate limited. Skip web_search and use your own knowledge to proceed.",
                "url": ""
            }])
        return json.dumps([{"title": "Search error", "body": f"Search failed: {err[:100]}. Use your own knowledge.", "url": ""}])
