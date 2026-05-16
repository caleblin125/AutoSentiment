"""Brave Search API client — rate-limited to 1 req/sec with persistent cache."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import monotonic
from collections.abc import Iterable

import httpx

from app.core.config import Settings

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_MAX_COUNT = 20
_CACHE_TTL_SECONDS = 30 * 60
_rate_sem = asyncio.Semaphore(1)


async def brave_search(
    query: str,
    *,
    freshness: str | None = None,
    count: int = 10,
    settings: Settings,
    db = None,
) -> list[str]:
    """Search Brave and return a list of result URLs.

    Rate-limited: one request per second enforced via semaphore + sleep.
    Cache checked in: in-process memory, then SQLite (if db provided),
    then live Brave API.
    """
    if not settings.brave_api_key:
        raise RuntimeError("BRAVE_API_KEY is not configured")

    clamped_count = max(1, min(count, _BRAVE_MAX_COUNT))
    cache_key = _make_cache_key(query, freshness, clamped_count)

    # Layer 1: in-process memory cache (fast, no DB round-trip).
    from app.tools import search as _mod
    inproc = _mod._memory_cache.get(cache_key)
    if inproc and monotonic() - inproc[0] < _CACHE_TTL_SECONDS:
        return list(inproc[1])

    # Layer 2: SQLite persistent cache (survives restarts).
    if db is not None:
        from sqlalchemy import select
        from app.models import BraveResultCache
        row = (await db.execute(
            select(BraveResultCache).where(BraveResultCache.cache_key == cache_key)
        )).scalar_one_or_none()
        if row and (monotonic() - row.created_at.timestamp()) < _CACHE_TTL_SECONDS:
            _mod._memory_cache[cache_key] = (monotonic(), row.result_urls)
            return list(row.result_urls)

    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.brave_api_key,
    }
    params = {"q": query, "count": clamped_count}
    if freshness:
        params["freshness"] = freshness

    await _rate_sem.acquire()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(_BRAVE_SEARCH_URL, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()
        urls = _extract_result_urls(payload)

        # Persist to both layers.
        _mod._memory_cache[cache_key] = (monotonic(), urls)
        if db is not None:
            from sqlalchemy import select as _sel
            from app.models import BraveResultCache
            existing = (await db.execute(
                _sel(BraveResultCache).where(BraveResultCache.cache_key == cache_key)
            )).scalar_one_or_none()
            if existing is None:
                db.add(BraveResultCache(cache_key=cache_key, result_urls=urls, result_raw=payload))
            else:
                existing.result_urls = urls
                existing.created_at = datetime.now(UTC)
            await db.flush()

        return urls
    finally:
        await asyncio.sleep(1)
        _rate_sem.release()


def _make_cache_key(query: str, freshness: str | None, count: int) -> str:
    fresh_part = freshness or "none"
    return f"{fresh_part}:{count}:{query.strip().casefold()}"


def _extract_result_urls(payload: dict) -> list[str]:
    """Return URLs from Brave's common response shapes."""
    results: Iterable[dict] = payload.get("results") or payload.get("web", {}).get("results") or []
    return [result["url"] for result in results if result.get("url")]


def is_cached_search(query: str, *, freshness: str | None = None, count: int = 10) -> bool:
    clamped_count = max(1, min(count, _BRAVE_MAX_COUNT))
    cache_key = _make_cache_key(query, freshness, clamped_count)
    from app.tools import search as _mod
    cached = _mod._memory_cache.get(cache_key)
    return bool(cached and monotonic() - cached[0] < _CACHE_TTL_SECONDS)


# Module-level in-process cache (fast path).
_memory_cache: dict[str, tuple[float, list[str]]] = {}
