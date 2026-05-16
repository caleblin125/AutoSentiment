"""Main research pipeline — wires all stages and emits SSE events."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.api import event_bus
from app.api.event_bus import clear_cancel, is_cancelled, request_cancel as _request_cancel  # noqa: F401
from app.agents.light_queue import SentimentQueue
from app.agents.nemoclaw import expand_queries, synthesize_report
from app.agents.ollama import GenerationCancelled
from app.agents.types import SSEEventType, SentimentLabel
from app.db.session import AsyncSessionLocal
from app.ingest.fetch import classify_source_type, fetch_items
from app.models import EvidenceChunk, Run, RunEvent
from app.reports.builder import build_idea_graph, compute_aspects, compute_counts, compute_source_facts, pick_top_quotes
from app.tools.search import brave_search

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_FETCH_CONCURRENCY = 8


class _CancelledByUser(Exception):
    """Raised internally when a user cancels the run; triggers a clean shutdown."""


async def run_research(
    run_id: str,
    topic: str,
    freshness: str | None,
    settings: Settings,
    skip_urls: frozenset[str] = frozenset(),
) -> None:
    """End-to-end pipeline for one run. Runs as a background asyncio task.

    Stages (see SPEC.md §Agent Flow):
      1. 120B query expansion
      2. Brave search (1/sec) → unique URLs
      3. Parallel URL fetch (up to _FETCH_CONCURRENCY at once), events emitted as each finishes
      4. 30B sentiment per item (concurrency-capped via SentimentQueue), events emitted as each finishes
      5. 120B synthesis → store report + emit run_completed
    """
    queue = event_bus.get(run_id)
    seq = 0
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
                await expand_queries(topic, settings=settings, cancel_check=_cancel_check),
                topic,
            )
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

                for url in await brave_search(query, freshness=freshness, count=remaining, settings=settings):
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

            fetch_tasks = [
                asyncio.create_task(_fetch_url_timed(url, fetch_sem))
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

            stage_started = perf_counter()
            analyze_tasks = [
                asyncio.create_task(_analyze_item(sentiment_queue, item))
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

            # ── Stage 5: synthesis ──────────────────────────────────────────
            counts = compute_counts(chunks)
            top_positive = pick_top_quotes(chunks, SentimentLabel.POSITIVE)
            top_negative = pick_top_quotes(chunks, SentimentLabel.NEGATIVE)
            aspects = compute_aspects(chunks, topic)
            source_facts = compute_source_facts(chunks)
            chunks_summary = _summaries_for_synthesis(chunks)

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
                "graph": build_idea_graph(topic, chunks, themes, aspects),
            }

            run.report = report
            run.status = "completed"
            await emit(SSEEventType.RUN_COMPLETED, "Run completed", {"report": report})
            await db.commit()

        except (_CancelledByUser, GenerationCancelled):
            logger.info("Run cancelled by user: %s", run_id)
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


async def _fetch_url_timed(url: str, sem: asyncio.Semaphore) -> tuple[str, list, float]:
    """Fetch items from one URL, gated by sem, returning (url, items, duration_ms)."""
    t0 = perf_counter()
    async with sem:
        items = await fetch_items(url)
    return url, items, _elapsed_ms(t0)


async def _analyze_item(sentiment_queue: SentimentQueue, item) -> tuple:
    """Analyze one fetched item and retain timing for per-item telemetry."""
    started_at = perf_counter()
    result = await sentiment_queue.analyze(item.snippet)
    return item, result, _elapsed_ms(started_at)


def _summaries_for_synthesis(chunks: list[EvidenceChunk], limit: int = 40) -> list[dict]:
    """Keep synthesis prompts bounded while preserving sentiment diversity."""
    selected: list[EvidenceChunk] = []
    per_label = max(1, limit // 3)
    for label in SentimentLabel:
        selected.extend([chunk for chunk in chunks if str(chunk.label) == label.value][:per_label])

    seen = {chunk.id for chunk in selected}
    selected.extend(chunk for chunk in chunks if chunk.id not in seen)
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
