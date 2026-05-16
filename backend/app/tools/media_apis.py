"""Supplemental no-key media API search.

These sources expand coverage without spending Brave quota. They are best-effort
and never block the main Brave-backed search path.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx


async def supplemental_media_search(query: str, *, limit: int = 12) -> list[str]:
    urls: list[str] = []
    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
        # Prefer broad non-Reddit indexes first; Reddit is useful but should not
        # dominate runs when other public sources are available.
        for fn in (_search_gdelt, _search_hacker_news, _search_wikipedia, _search_arxiv, _search_reddit):
            remaining = max(0, limit - len(urls))
            if remaining <= 0:
                break
            fn_limit = min(remaining, max(2, limit // 4)) if fn.__name__ == "_search_reddit" else remaining
            try:
                urls.extend(await fn(client, query, fn_limit))
            except Exception:
                continue
    return _dedupe(urls)[:limit]


async def _search_gdelt(client: httpx.AsyncClient, query: str, limit: int) -> list[str]:
    response = await client.get(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params={
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": min(limit, 20),
        },
    )
    response.raise_for_status()
    articles = response.json().get("articles") or []
    return [str(article["url"]) for article in articles if article.get("url")]


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


async def _search_wikipedia(client: httpx.AsyncClient, query: str, limit: int) -> list[str]:
    response = await client.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "opensearch",
            "search": query,
            "limit": min(limit, 10),
            "namespace": 0,
            "format": "json",
            "origin": "*",
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or len(payload) < 4:
        return []
    return [str(url) for url in payload[3] if url]


async def _search_arxiv(client: httpx.AsyncClient, query: str, limit: int) -> list[str]:
    response = await client.get(
        "https://export.arxiv.org/api/query",
        params={
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": min(limit, 10),
        },
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    urls: list[str] = []
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
        identifier = entry.findtext("{http://www.w3.org/2005/Atom}id")
        if identifier:
            urls.append(identifier)
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
    for child in children[:limit]:
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
