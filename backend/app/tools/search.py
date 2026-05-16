"""Brave Search API client — rate-limited to 1 req/sec."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

import httpx

from app.core.config import Settings

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_rate_sem = asyncio.Semaphore(1)


async def brave_search(
    query: str,
    *,
    freshness: str | None = None,
    count: int = 10,
    settings: Settings,
) -> list[str]:
    """Search Brave and return a list of result URLs.

    Rate-limited: one request per second enforced via semaphore + sleep.
    """
    if not settings.brave_api_key:
        raise RuntimeError("BRAVE_API_KEY is not configured")

    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.brave_api_key,
    }
    params = {"q": query, "count": count}
    if freshness:
        params["freshness"] = freshness

    await _rate_sem.acquire()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(_BRAVE_SEARCH_URL, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()
        return _extract_result_urls(payload)
    finally:
        await asyncio.sleep(1)
        _rate_sem.release()


def _extract_result_urls(payload: dict) -> list[str]:
    """Return URLs from Brave's common response shapes.

    Brave's web search API nests normal web results under ``web.results``. Some
    mocks and older examples use top-level ``results``, so accept both shapes to
    keep tests and local stubs representative without breaking real queries.
    """
    results: Iterable[dict] = payload.get("results") or payload.get("web", {}).get("results") or []
    return [result["url"] for result in results if result.get("url")]
