from ddgs import DDGS


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the internet for any information — races, local running events, routes,
    training advice, weather events, etc. Returns titles, URLs, and snippets."""
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title"),
                "url": r.get("href"),
                "snippet": r.get("body"),
            })
    return results if results else [{"message": f"No results found for: {query}"}]
