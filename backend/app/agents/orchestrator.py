"""Main research pipeline — wires all stages and emits SSE events."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from app.api import event_bus
from app.api.event_bus import clear_cancel, is_cancelled, request_cancel as _request_cancel  # noqa: F401
from app.agents.light_queue import SentimentQueue
from app.agents.nemoclaw import expand_queries, synthesize_report
from app.agents.ollama import GenerationCancelled
from app.agents.types import SSEEventType, SentimentLabel
from app.db.session import AsyncSessionLocal
from app.ingest.fetch import classify_source_type, fetch_items
from app.models import EvidenceChunk, Run, RunEvent
from app.reports.builder import (
    build_idea_graph,
    compute_aspects,
    compute_claims,
    compute_counts,
    compute_source_facts,
    compute_timeline,
    pick_top_quotes,
)
from app.search_planner import build_search_plan, record_brave_query
from app.tools.search import brave_search, is_cached_search

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_FETCH_CONCURRENCY = 8
_FETCH_TIMEOUT_SECONDS = 15.0
_FETCH_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


class _CancelledByUser(Exception):
    """Raised internally when a user cancels the run; triggers a clean shutdown."""


async def run_research(
    run_id: str,
    topic: str,
    freshness: str | None,
    settings: Settings,
    skip_urls: frozenset[str] = frozenset(),
    research_depth: str = "standard",
    depth_budget: dict | None = None,
    use_case: str = "generic",
) -> None:
    """End-to-end pipeline for one run. Runs as a background asyncio task.

    Stages:
      1. 120B query expansion
      2. Brave search (1/sec) → unique URLs
      3. Parallel URL fetch (up to _FETCH_CONCURRENCY at once)
      4. 30B sentiment per item (concurrency-capped via SentimentQueue)
      5. 120B synthesis → store report + emit run_completed
    """
    queue = event_bus.get(run_id)
    run_started_at = perf_counter()
    timings: dict[str, float] = {
        "query_expansion_ms": 0.0,
        "search_ms": 0.0,
        "fetch_ms": 0.0,
        "sentiment_ms": 0.0,
        "synthesis_ms": 0.0,
        "total_ms": 0.0,
    }

    async with AsyncSessionLocal() as db:
        # Start seq after any pre-seeded events (e.g. copied from original run on expand).
        from sqlalchemy import func as sqlfunc, select as _select
        _count_result = await db.execute(
            _select(sqlfunc.count()).select_from(RunEvent).where(RunEvent.run_id == run_id)
        )
        seq = _count_result.scalar_one() or 0

        async def emit(event_type: SSEEventType, message: str, detail: dict | None = None) -> None:
            """Persist and stream one SSE event.

            Adds server-side elapsed_ms so the frontend can show accurate timing
            without depending on clock synchronisation between client and server.
            """
            nonlocal seq
            seq += 1
            enriched = {**(detail or {}), "elapsed_ms": _elapsed_ms(run_started_at)}
            event = {
                "seq": seq,
                "type": event_type.value,
                "message": message,
                "detail": enriched,
            }
            db.add(
                RunEvent(
                    run_id=run_id,
                    seq=seq,
                    type=event_type.value,
                    message=message,
                    detail=enriched,
                )
            )
            await db.flush()
            if queue is not None:
                queue.put_nowait(event)

        try:
            run = await db.get(Run, run_id)
            if run is None:
                raise ValueError(f"Run not found: {run_id}")

            run.status = "running"
            await emit(SSEEventType.RUN_STARTED, "Run started", {"topic": topic, "freshness": freshness})
            await db.commit()

            # ── cancel_check propagated to all LLM calls for fast interruption ──
            def _cancel_check() -> bool:
                return is_cancelled(run_id)

            # ── Stage 1: query expansion ────────────────────────────────────
            stage_started = perf_counter()
            queries = _expand_platform_queries(
                await expand_queries(
                    topic, settings=settings,
                    freshness=freshness, cancel_check=_cancel_check,
                ),
                topic,
            )
            search_plan = await build_search_plan(
                topic,
                freshness=freshness,
                research_depth=research_depth,
                use_case=use_case,
                settings=settings,
                db=db,
                base_queries=queries,
            )
            queries = [planned.query for planned in search_plan.queries]
            timings["query_expansion_ms"] = _elapsed_ms(stage_started)

            if is_cancelled(run_id):
                raise _CancelledByUser()

            # ── Stage 2: Brave search (rate-limited, sequential) ────────────
            urls: list[str] = []
            seen_urls: set[str] = set()

            stage_started = perf_counter()
            for query in queries:
                if is_cancelled(run_id):
                    raise _CancelledByUser()

                await emit(SSEEventType.SEARCH_QUERIED, "Search queried", {"query": query})
                await db.commit()

                remaining = settings.max_urls_per_run - len(urls)
                if remaining <= 0:
                    break

                # Wrap in wait_for so a pending cancel isn't blocked by a slow HTTP response.
                try:
                    if not is_cached_search(query, freshness=freshness, count=remaining):
                        await record_brave_query(db)
                        await db.commit()
                    search_results = await asyncio.wait_for(
                        brave_search(query, freshness=freshness, count=remaining, settings=settings),
                        timeout=12.0,
                    )
                except asyncio.TimeoutError:
                    if is_cancelled(run_id):
                        raise _CancelledByUser()
                    logger.warning("Brave search timed out for query: %s", query)
                    continue
                if is_cancelled(run_id):
                    raise _CancelledByUser()
                for url in search_results:
                    if url in seen_urls or url in skip_urls:
                        continue
                    seen_urls.add(url)
                    urls.append(url)
                    if len(urls) >= settings.max_urls_per_run:
                        break
            timings["search_ms"] = _elapsed_ms(stage_started)

            if is_cancelled(run_id):
                raise _CancelledByUser()

            # ── Stage 3: parallel URL fetch ─────────────────────────────────
            await emit(SSEEventType.FETCH_STARTED, f"Fetching {len(urls)} URLs", {"url_count": len(urls)})
            await db.commit()

            fetch_sem = asyncio.Semaphore(_FETCH_CONCURRENCY)
            fetched_items: list[FetchedItem] = []  # type: ignore[name-defined]
            stage_started = perf_counter()

            async with httpx.AsyncClient(
                timeout=10.0,
                headers={"User-Agent": _FETCH_USER_AGENT},
                follow_redirects=True,
            ) as fetch_client:
                fetch_tasks = [
                    asyncio.create_task(_fetch_url_timed(url, fetch_sem, fetch_client))
                    for url in urls
                ]
                for future in asyncio.as_completed(fetch_tasks):
                    url, items, fetch_ms = await future
                    if is_cancelled(run_id):
                        for t in fetch_tasks:
                            t.cancel()
                        raise _CancelledByUser()
                    remaining = settings.max_items_per_run - len(fetched_items)
                    selected = items[:remaining] if remaining > 0 else []
                    fetched_items.extend(selected)

                    source_type = (
                        selected[0].source_type.value
                        if selected
                        else classify_source_type(url).value
                    )
                    domain = _domain_from_url(url)
                    await emit(
                        SSEEventType.URL_FETCHED,
                        f"Fetched {len(selected)} items from {domain}",
                        {
                            "url": url,
                            "domain": domain,
                            "source_type": source_type,
                            "item_count": len(selected),
                            "fetch_ms": round(fetch_ms, 1),
                        },
                    )
                    await db.commit()
            timings["fetch_ms"] = _elapsed_ms(stage_started)

            # ── Stage 4: sentiment analysis (parallel, capped by SentimentQueue) ──
            sentiment_queue = SentimentQueue(settings, cancel_check=_cancel_check)
            chunks: list[EvidenceChunk] = []
            sentiment_tasks: dict[str, asyncio.Task] = {}

            stage_started = perf_counter()
            analyze_tasks = [
                asyncio.create_task(_analyze_item_cached(sentiment_queue, item, sentiment_tasks))
                for item in fetched_items
            ]
            for future in asyncio.as_completed(analyze_tasks):
                if is_cancelled(run_id):
                    for t in analyze_tasks:
                        t.cancel()
                    raise _CancelledByUser()
                item, result, duration_ms = await future
                chunk = EvidenceChunk(
                    run_id=run_id,
                    url=item.url,
                    source_type=item.source_type.value,
                    snippet=item.snippet,
                    label=result.label.value,
                    summary=result.summary,
                )
                db.add(chunk)
                await db.flush()
                chunks.append(chunk)

                await emit(
                    SSEEventType.ITEM_ANALYZED,
                    "Item analyzed",
                    {
                        "evidence_id": chunk.id,
                        "label": chunk.label,
                        "summary": chunk.summary,
                        "url": chunk.url,
                        "domain": _domain_from_url(chunk.url),
                        "source_type": chunk.source_type,
                        "duration_ms": round(duration_ms, 1),
                    },
                )
                await db.commit()
            timings["sentiment_ms"] = _elapsed_ms(stage_started)
            timings["sentiment_model_calls"] = float(len(sentiment_tasks))
            timings["sentiment_cache_hits"] = float(max(0, len(fetched_items) - len(sentiment_tasks)))

            # ── Stage 5: synthesis ──────────────────────────────────────────
            counts = compute_counts(chunks)
            top_positive = pick_top_quotes(chunks, SentimentLabel.POSITIVE)
            top_negative = pick_top_quotes(chunks, SentimentLabel.NEGATIVE)
            aspects = compute_aspects(chunks, topic)
            source_facts = compute_source_facts(chunks)
            timeline = compute_timeline(chunks, topic)
            fact_check = compute_claims(chunks)
            synthesis_limit = _synthesis_limit(depth_budget)
            chunks_summary = _summaries_for_synthesis(chunks, limit=synthesis_limit)

            await emit(SSEEventType.SYNTHESIS_STARTED, "Synthesis started")
            await db.commit()

            stage_started = perf_counter()
            synthesis = await synthesize_report(
                topic, chunks_summary, counts, settings=settings, cancel_check=_cancel_check
            )
            timings["synthesis_ms"] = _elapsed_ms(stage_started)
            themes = synthesis.get("themes", [])
            timings["total_ms"] = _elapsed_ms(run_started_at)

            report = {
                "metadata": {
                    "topic": topic,
                    "freshness": freshness,
                    "research_depth": research_depth,
                    "use_case": use_case,
                    "depth_budget": depth_budget or {},
                    "search_plan": search_plan.to_dict(),
                },
                **counts,
                "top_positive": top_positive,
                "top_negative": top_negative,
                "themes": themes,
                "narrative": synthesis.get("narrative", "Synthesis unavailable."),
                "impacts": synthesis.get("impacts", []),
                "reasons": synthesis.get("reasons", []),
                "arguments": synthesis.get("arguments", []),
                "timings": timings,
                "aspects": aspects,
                "source_facts": source_facts,
                "timeline": timeline,
                "fact_check": fact_check,
                "graph": build_idea_graph(topic, chunks, themes, aspects),
            }

            run.report = report
            run.status = "completed"
            await emit(SSEEventType.RUN_COMPLETED, "Run completed", {"report": report})
            await db.commit()

        except (_CancelledByUser, GenerationCancelled):
            logger.info("Run cancelled: %s", run_id)
            run = await db.get(Run, run_id)
            if run is not None:
                run.status = "cancelled"
            await emit(SSEEventType.RUN_CANCELLED, "Run cancelled")
            await db.commit()

        except Exception as exc:
            logger.exception("Run failed: %s", run_id)
            run = await db.get(Run, run_id)
            if run is not None:
                run.status = "error"
            await emit(SSEEventType.RUN_ERROR, "Run error", {"message": str(exc)})
            await db.commit()

        finally:
            clear_cancel(run_id)
            if queue is not None:
                queue.put_nowait(None)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def _domain_from_url(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def _synthesis_limit(depth_budget: dict | None) -> int:
    if not depth_budget:
        return 60
    value = depth_budget.get("synthesis_sample_size")
    if not isinstance(value, int):
        return 60
    return max(12, min(value, 240))


async def _fetch_url_timed(
    url: str,
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, list, float]:
    """Fetch items from one URL, gated by sem, returning (url, items, duration_ms)."""
    t0 = perf_counter()
    async with sem:
        try:
            items = await asyncio.wait_for(fetch_items(url, client=client), timeout=_FETCH_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning("Fetch timed out for URL: %s", url)
            items = []
    return url, items, _elapsed_ms(t0)


async def _analyze_item(sentiment_queue: SentimentQueue, item) -> tuple:
    """Analyze one fetched item and retain timing for per-item telemetry."""
    started_at = perf_counter()
    result = await sentiment_queue.analyze(item.snippet)
    return item, result, _elapsed_ms(started_at)


async def _analyze_item_cached(
    sentiment_queue: SentimentQueue,
    item,
    sentiment_tasks: dict[str, asyncio.Task],
) -> tuple:
    """Share one model call across exact duplicate snippets within a run."""
    started_at = perf_counter()
    key = _sentiment_cache_key(item.snippet)
    task = sentiment_tasks.get(key)
    if task is None:
        task = asyncio.create_task(sentiment_queue.analyze(item.snippet))
        sentiment_tasks[key] = task
    result = await task
    return item, result, _elapsed_ms(started_at)


def _sentiment_cache_key(snippet: str) -> str:
    return " ".join(snippet.casefold().split())


_CREDIBLE_DOMAINS_SET = frozenset({
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com",
    "wsj.com", "bloomberg.com", "ft.com", "theguardian.com", "economist.com",
    "nature.com", "science.org", "sciencedirect.com", "pubmed.ncbi.nlm.nih.gov",
    "who.int", "cdc.gov", "europa.eu", "un.org", "mit.edu", "stanford.edu",
    "harvard.edu", "ieee.org", "acm.org",
})


def _chunk_is_credible(chunk: EvidenceChunk) -> bool:
    try:
        domain = urlparse(chunk.url).netloc.removeprefix("www.")
        return domain in _CREDIBLE_DOMAINS_SET or any(
            domain.endswith(f".{d}") for d in _CREDIBLE_DOMAINS_SET
        )
    except Exception:
        return False


def _summaries_for_synthesis(chunks: list[EvidenceChunk], limit: int = 40) -> list[dict]:
    """Keep synthesis prompts bounded while preserving sentiment diversity.

    Credible sources are always included first to up-weight authoritative signals
    in the 120B model's context window.
    """
    # Partition into credible and regular.
    credible = [c for c in chunks if _chunk_is_credible(c)]
    regular  = [c for c in chunks if not _chunk_is_credible(c)]

    selected: list[EvidenceChunk] = []
    per_label = max(1, limit // 3)

    # Take credible sources first, diverse across labels.
    for label in SentimentLabel:
        selected.extend([c for c in credible if str(c.label) == label.value][:per_label])

    # Fill remainder from regular sources, balanced by label.
    seen = {c.id for c in selected}
    for label in SentimentLabel:
        selected.extend(
            [c for c in regular if str(c.label) == label.value and c.id not in seen][: per_label]
        )
        seen = {c.id for c in selected}

    seen = {c.id for c in selected}
    selected.extend(c for c in chunks if c.id not in seen)

    return [
        {
            "label": chunk.label,
            "summary": chunk.summary,
            "url": chunk.url,
            "source_type": chunk.source_type,
        }
        for chunk in selected[:limit]
    ]


def _expand_platform_queries(queries: list[str], topic: str) -> list[str]:
    """Expand queries across diverse opinion sources with reduced Reddit dominance.

    Source mix:
    - Independent forums and discussion boards (Quora, HN, Stack Exchange)
    - Social platforms (X/Twitter, YouTube, Threads, LinkedIn)
    - News & editorial (avoid aggregated SEO spam)
    - One Reddit query (not prioritised — Brave already surfaces Reddit organically)
    - Review sites (Trustpilot, G2, product-specific)
    - International coverage in 5 languages so non-English opinion is included

    The LLM-generated ``queries`` from expand_queries come first; platform queries
    follow, deduped by normalised lower-case content.
    """
    # ── Broad semantic queries (diverse signals) ────────────────────────────
    semantic = [
        f"{topic} review opinion",
        f"{topic} user experience feedback",
        f"{topic} pros cons analysis",
        f"{topic} criticism problems issues",
        f"{topic} expert opinion assessment",
        f"{topic} news update recent",
    ]

    # ── Platform-specific (spread across sources, not Reddit-heavy) ─────────
    platform = [
        f"{topic} site:quora.com",                # question/answer — high signal
        f"{topic} site:news.ycombinator.com",      # tech/science discussion
        f"{topic} site:youtube.com",               # video comment sentiment
        f"{topic} site:x.com",                     # real-time public opinion
        f"{topic} site:threads.net",               # Meta's text platform
        f"{topic} site:linkedin.com",              # professional perspective
        f"{topic} site:trustpilot.com",            # consumer reviews
        f"{topic} site:reddit.com",                # one balanced Reddit query
        f"{topic} site:stackexchange.com",         # factual community Q&A
        f"{topic} site:g2.com",                    # B2B software reviews
        f"{topic} site:producthunt.com",           # product launch reactions
    ]

    # ── International queries — included when topic has broad global relevance ──
    # Detect likely proper nouns / brand names (starts with capital in original).
    is_likely_global = any(w[0].isupper() for w in topic.split() if w)
    intl = [
        f"{topic} opinión análisis foro",                # Spanish (ES/LA)
        f"{topic} avis retour expérience",               # French
        f"{topic} Bewertung Erfahrung Meinung",          # German
        f"{topic} opinião avaliação discussão",           # Portuguese (BR/PT)
        f"{topic} recensione opinione forum",             # Italian
        f"{topic} 评价 评论 用户 体验",                   # Simplified Chinese
        f"{topic} 評価 口コミ ユーザー",                  # Japanese
        f"{topic} 리뷰 의견 평가",                        # Korean
    ] if is_likely_global else [
        f"{topic} opinión foro análisis",
        f"{topic} avis forum discussion",
        f"{topic} Meinung Bewertung Erfahrung",
        f"{topic} 評価 意見 ユーザー",
    ]

    expanded = [*queries, *semantic, *platform, *intl]
    seen: set[str] = set()
    unique: list[str] = []
    for query in expanded:
        normalized = query.strip()
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            unique.append(normalized)
    return unique
