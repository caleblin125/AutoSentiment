"""Supplemental no-key media API search.

These sources expand coverage without spending Brave quota. They are best-effort
and never block the main Brave-backed search path.

All five sources are queried in parallel via asyncio.gather; results are
interleaved round-robin so no single platform can dominate the URL pool.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import httpx


async def supplemental_media_search(
    query: str,
    *,
    limit: int = 12,
    include_source_map: bool = False,
) -> list[str] | tuple[list[str], dict[str, list[str]]]:
    """Fetch supplemental URLs from GDELT, HN, Wikipedia, arXiv, and Reddit in parallel.

    Args:
        query: Search query string.
        limit: Maximum total URLs to return.
        include_source_map: If True, also return a dict mapping url -> [source_names].

    Returns:
        List of deduplicated URLs, or (urls, source_map) if include_source_map=True.
    """
    per_source = max(2, limit // 3)
    reddit_limit = max(2, limit // 4)  # Reddit capped at ~25%

    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
        results = await asyncio.gather(
            _search_gdelt(client, query, per_source),
            _search_hacker_news(client, query, per_source),
            _search_wikipedia(client, query, per_source),
            _search_arxiv(client, query, per_source),
            _search_reddit(client, query, reddit_limit),
            return_exceptions=True,
        )

    source_names = ["gdelt", "hn", "wikipedia", "arxiv", "reddit"]
    valid: list[tuple[str, list[str]]] = []
    for name, result in zip(source_names, results):
        if isinstance(result, list):
            valid.append((name, result))

    # Round-robin interleaving: alternate between sources so the final list
    # naturally diversifies across platforms rather than appending each source
    # as a block.
    urls: list[str] = []
    source_map: dict[str, list[str]] = {}
    max_len = max((len(lst) for _, lst in valid), default=0)

    for i in range(max_len):
        for name, lst in valid:
            if i < len(lst):
                url = lst[i]
                source_map.setdefault(url, []).append(name)
                urls.append(url)

    deduped = _dedupe(urls)[:limit]

    if include_source_map:
        # Only keep entries for URLs that made the final cut.
        final_set = set(deduped)
        trimmed = {u: v for u, v in source_map.items() if u in final_set}
        return deduped, trimmed

    return deduped


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
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped
