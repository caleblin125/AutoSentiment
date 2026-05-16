"""Fetch and extract text items from URLs.

Reddit URLs: fetch url.json → extract top-level comments (cap 20).
News URLs:   httpx GET → trafilatura extraction → split into paragraphs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlparse, urlsplit, urlunsplit

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


def classify_source_type(url: str) -> SourceType:
    """Map common platforms to broad source buckets with domain-aware heuristics."""
    host = urlparse(url).netloc.lower()
    # Remove www/m prefixes for cleaner matching.
    host_clean = host.removeprefix("www.").removeprefix("m.").removeprefix("old.")

    if "reddit.com" in host:
        return SourceType.REDDIT
    if any(d in host for d in ("youtube.com", "youtu.be", "tiktok.com", "twitch.tv", "vimeo.com")):
        return SourceType.VIDEO
    if any(d in host for d in ("x.com", "twitter.com", "threads.net", "facebook.com",
                                "instagram.com", "linkedin.com", "tumblr.com", "bsky.app")):
        return SourceType.SOCIAL

    # Known forums and community sites.
    _forum_domains = {
        "news.ycombinator.com", "quora.com", "stackexchange.com", "stackoverflow.com",
        "medium.com", "substack.com", "discourse.org", "lemmy.world", "lemmy.ml",
        "stocktwits.com", "seekingalpha.com",  # financial discussion
        "trustpilot.com", "sitejabber.com", "g2.com", "capterra.com",  # review forums
        "producthunt.com", "slant.co",
        "groups.google.com",
    }
    if host_clean in _forum_domains or any(host_clean.endswith(f".{d}") for d in _forum_domains):
        return SourceType.FORUM

    # Known news / journalistic domains.
    _news_domains = {
        "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com",
        "wsj.com", "bloomberg.com", "cnn.com", "washingtonpost.com",
        "theguardian.com", "economist.com", "ft.com", "politico.com",
        "npr.org", "aljazeera.com", "dw.com", "france24.com",
        "nature.com", "science.org", "sciencedirect.com", "techcrunch.com",
        "theverge.com", "wired.com", "arstechnica.com", "engadget.com",
        "variety.com", "hollywoodreporter.com", "deadline.com",  # entertainment trade
        "ign.com", "gamespot.com", "pcgamer.com", "eurogamer.net",  # gaming press
        "marketwatch.com", "cnbc.com", "barrons.com", "investopedia.com",  # financial news
    }
    if host_clean in _news_domains or any(host_clean.endswith(f".{d}") for d in _news_domains):
        return SourceType.NEWS

    # Generic keyword fallback for uncategorized domains.
    if any(term in host for term in ("news", "press", "journal", "times", "post", "daily")):
        return SourceType.NEWS
    if any(term in host for term in ("forum", "community", "discuss", "board")):
        return SourceType.FORUM

    return SourceType.WEB


async def fetch_items(url: str, client: httpx.AsyncClient | None = None) -> list[FetchedItem]:
    """Dispatch to reddit or news fetcher based on URL. Returns list of extractable items."""
    try:
        if is_reddit_url(url):
            return await _fetch_reddit(url, client=client)
        return await _fetch_news(url, client=client)
    except Exception:
        return []


async def _fetch_reddit(url: str, client: httpx.AsyncClient | None = None) -> list[FetchedItem]:
    """GET url.json, parse comments array, return up to REDDIT_COMMENTS_PER_THREAD items."""
    reddit_url = _reddit_json_url(url)
    if client is None:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _USER_AGENT}) as own_client:
            response = await own_client.get(reddit_url)
            response.raise_for_status()
            payload = response.json()
    else:
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


async def _fetch_news(url: str, client: httpx.AsyncClient | None = None) -> list[FetchedItem]:
    """httpx GET, trafilatura.extract, split on double-newline into paragraph chunks."""
    if client is None:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _USER_AGENT}) as own_client:
            response = await own_client.get(url)
            response.raise_for_status()
    else:
        response = await client.get(url)
        response.raise_for_status()

    extracted = await asyncio.to_thread(trafilatura.extract, response.text) or ""
    return [
        FetchedItem(snippet=chunk.strip(), url=url, source_type=classify_source_type(url))
        for chunk in extracted.split("\n\n")
        if len(chunk.strip()) >= 40
    ]


def _reddit_json_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.path.endswith(".json"):
        return url
    return urlunsplit((parts.scheme, parts.netloc, f"{parts.path.rstrip('/')}.json", parts.query, parts.fragment))
