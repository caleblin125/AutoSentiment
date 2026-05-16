"""Fetch and extract text items from URLs.

Reddit URLs: fetch url.json → extract top-level comments (cap 20).
News URLs:   httpx GET → trafilatura extraction → split into paragraphs.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx
import trafilatura

from app.agents.types import SourceType

REDDIT_COMMENTS_PER_THREAD = 20
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


@dataclass
class FetchedItem:
    snippet: str
    url: str
    source_type: SourceType


def is_reddit_url(url: str) -> bool:
    return "reddit.com" in url


async def fetch_items(url: str) -> list[FetchedItem]:
    """Dispatch to reddit or news fetcher based on URL. Returns list of extractable items."""
    try:
        if is_reddit_url(url):
            return await _fetch_reddit(url)
        return await _fetch_news(url)
    except Exception:
        return []


async def _fetch_reddit(url: str) -> list[FetchedItem]:
    """GET url.json, parse comments array, return up to REDDIT_COMMENTS_PER_THREAD items."""
    reddit_url = _reddit_json_url(url)
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _USER_AGENT}) as client:
        response = await client.get(reddit_url)
        response.raise_for_status()
        payload = response.json()

    children = payload[1]["data"]["children"]
    items: list[FetchedItem] = []

    for child in children:
        if child.get("kind") != "t1":
            continue
        body = child.get("data", {}).get("body", "").strip()
        if not body:
            continue
        items.append(FetchedItem(snippet=body, url=url, source_type=SourceType.REDDIT))
        if len(items) >= REDDIT_COMMENTS_PER_THREAD:
            break

    return items


async def _fetch_news(url: str) -> list[FetchedItem]:
    """httpx GET, trafilatura.extract, split on double-newline into paragraph chunks."""
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _USER_AGENT}) as client:
        response = await client.get(url)
        response.raise_for_status()

    extracted = trafilatura.extract(response.text) or ""
    return [
        FetchedItem(snippet=chunk.strip(), url=url, source_type=SourceType.NEWS)
        for chunk in extracted.split("\n\n")
        if len(chunk.strip()) >= 40
    ]


def _reddit_json_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.path.endswith(".json"):
        return url
    return urlunsplit((parts.scheme, parts.netloc, f"{parts.path.rstrip('/')}.json", parts.query, parts.fragment))
