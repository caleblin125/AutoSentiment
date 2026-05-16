"""Fetch and extract text items from URLs.

Reddit URLs: fetch url.json → extract top-level comments (cap 20).
News URLs:   httpx GET → trafilatura extraction → split into paragraphs.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from urllib.parse import urlparse, urlsplit, urlunsplit

import httpx
import trafilatura

from app.agents.types import SourceType

_SNIPPET_DELIMITER = "\n␞\n"  # ASCII record separator wrapped in newlines

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


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


async def read_url_cache(
    db,
    url: str,
    ttl_seconds: int,
) -> list[FetchedItem] | None:
    """Return cached FetchedItems for url if fresh, else None.

    Must be awaited serially against db (no concurrent calls on the same session).
    """
    if db is None or ttl_seconds <= 0:
        return None

    from sqlalchemy import select
    from app.models import FetchedURLCache

    cache_key = _url_hash(url)
    row = (
        await db.execute(select(FetchedURLCache).where(FetchedURLCache.url_hash == cache_key))
    ).scalar_one_or_none()
    if row is None:
        return None

    cached_at = row.created_at
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - cached_at > timedelta(seconds=ttl_seconds):
        return None

    try:
        source_type = SourceType(row.source_type)
    except ValueError:
        source_type = classify_source_type(url)
    snippets = [s for s in row.extracted_text.split(_SNIPPET_DELIMITER) if s.strip()]
    return [FetchedItem(snippet=s, url=url, source_type=source_type) for s in snippets]


async def write_url_cache(
    db,
    url: str,
    items: list[FetchedItem],
) -> None:
    """Persist fetched items so a future run can skip the network round-trip.

    Must be awaited serially against db. Silently swallows write errors so
    cache problems never break a run.
    """
    if db is None or not items:
        return

    from sqlalchemy import select
    from app.models import FetchedURLCache

    cache_key = _url_hash(url)
    snippets_blob = _SNIPPET_DELIMITER.join(item.snippet for item in items)
    source_type_value = items[0].source_type.value
    try:
        row = (
            await db.execute(select(FetchedURLCache).where(FetchedURLCache.url_hash == cache_key))
        ).scalar_one_or_none()
        if row is None:
            db.add(FetchedURLCache(
                url_hash=cache_key,
                url=url,
                extracted_text=snippets_blob,
                source_type=source_type_value,
            ))
        else:
            row.extracted_text = snippets_blob
            row.source_type = source_type_value
            row.created_at = datetime.now(UTC)
        await db.flush()
    except Exception:
        pass


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
