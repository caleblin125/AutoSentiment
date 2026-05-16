"""Supplemental no-key media API search.

These sources expand coverage without spending Brave quota. They are best-effort
and never block the main Brave-backed search path.
"""

from __future__ import annotations

import httpx


async def supplemental_media_search(query: str, *, limit: int = 12) -> list[str]:
    urls: list[str] = []
    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
        for fn in (_search_hacker_news, _search_reddit):
            remaining = max(0, limit - len(urls))
            if remaining <= 0:
                break
            try:
                urls.extend(await fn(client, query, remaining))
            except Exception:
                continue
    return _dedupe(urls)[:limit]


async def _search_hacker_news(client: httpx.AsyncClient, query: str, limit: int) -> list[str]:
    response = await client.get(
        "https://hn.algolia.com/api/v1/search",
        params={"query": query, "tags": "story", "hitsPerPage": min(limit, 20)},
    )
    response.raise_for_status()
    hits = response.json().get("hits") or []
    urls = []
    for hit in hits:
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        if url:
            urls.append(str(url))
    return urls


async def _search_reddit(client: httpx.AsyncClient, query: str, limit: int) -> list[str]:
    response = await client.get(
        "https://www.reddit.com/search.json",
        params={"q": query, "sort": "relevance", "limit": min(limit, 25), "type": "link"},
        headers={"User-Agent": "AutoSentiment/0.1"},
    )
    response.raise_for_status()
    children = response.json().get("data", {}).get("children", [])
    urls = []
    for child in children:
        data = child.get("data", {})
        permalink = data.get("permalink")
        if permalink:
            urls.append(f"https://www.reddit.com{permalink}")
    return urls


def _dedupe(urls: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped
