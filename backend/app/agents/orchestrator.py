"""Main research pipeline — wires all stages and emits SSE events."""

from __future__ import annotations

import logging
import asyncio
from time import perf_counter
from typing import TYPE_CHECKING

from app.api import event_bus
from app.agents.light_queue import SentimentQueue
from app.agents.nemoclaw import expand_queries, synthesize_report
from app.agents.types import SSEEventType, SentimentLabel
from app.db.session import AsyncSessionLocal
from app.ingest.fetch import classify_source_type, fetch_items
from app.models import EvidenceChunk, Run, RunEvent
from app.reports.builder import build_idea_graph, compute_aspects, compute_counts, compute_source_facts, pick_top_quotes
from app.tools.search import brave_search

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


async def run_research(run_id: str, topic: str, freshness: str | None, settings: Settings) -> None:
    """End-to-end pipeline for one run. Runs as a background asyncio task.

    Stages (see SPEC.md §Agent Flow):
      1. 120B query expansion
      2. Brave search (1/sec) → unique URLs
      3. Fetch + extract items per URL
      4. 30B sentiment per item → store EvidenceChunk + emit item_analyzed
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
            # Persist every streamed event so completed runs still have an audit trail.
            nonlocal seq
            seq += 1
            event = {
                "seq": seq,
                "type": event_type.value,
                "message": message,
                "detail": detail or {},
            }
            db.add(
                RunEvent(
                    run_id=run_id,
                    seq=seq,
                    type=event_type.value,
                    message=message,
                    detail=detail or {},
                )
            )
            await db.flush()
            if queue is not None:
                # The queue is best-effort: a disconnected browser should not stop the run.
                queue.put_nowait(event)

        try:
            run = await db.get(Run, run_id)
            if run is None:
                raise ValueError(f"Run not found: {run_id}")

            run.status = "running"
            await emit(
                SSEEventType.RUN_STARTED,
                "Run started",
                {"topic": topic, "freshness": freshness},
            )
            await db.commit()

            stage_started = perf_counter()
            queries = _expand_platform_queries(await expand_queries(topic, settings=settings), topic)
            timings["query_expansion_ms"] = _elapsed_ms(stage_started)
            urls: list[str] = []
            seen_urls: set[str] = set()

            stage_started = perf_counter()
            for query in queries:
                await emit(SSEEventType.SEARCH_QUERIED, "Search queried", {"query": query})
                await db.commit()

                remaining = settings.max_urls_per_run - len(urls)
                if remaining <= 0:
                    break

                for url in await brave_search(
                    query,
                    freshness=freshness,
                    count=remaining,
                    settings=settings,
                ):
                    # Preserve first-seen ordering while avoiding duplicate fetch/model work.
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    urls.append(url)
                    if len(urls) >= settings.max_urls_per_run:
                        break
            timings["search_ms"] = _elapsed_ms(stage_started)

            fetched_items = []
            stage_started = perf_counter()
            for url in urls:
                if len(fetched_items) >= settings.max_items_per_run:
                    break

                items = await fetch_items(url)
                remaining = settings.max_items_per_run - len(fetched_items)
                selected_items = items[:remaining]
                fetched_items.extend(selected_items)

                source_type = (
                    selected_items[0].source_type.value
                    if selected_items
                    else classify_source_type(url).value
                )
                await emit(
                    SSEEventType.URL_FETCHED,
                    "URL fetched",
                    {
                        "url": url,
                        "source_type": source_type,
                        "item_count": len(selected_items),
                        "duration_ms": _elapsed_ms(stage_started),
                    },
                )
                await db.commit()
            timings["fetch_ms"] = _elapsed_ms(stage_started)

            sentiment_queue = SentimentQueue(settings)
            chunks: list[EvidenceChunk] = []

            stage_started = perf_counter()
            analyzed_items = await asyncio.gather(
                *(_analyze_item(sentiment_queue, item) for item in fetched_items)
            )
            for item, result, duration_ms in analyzed_items:
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
                        "source_type": chunk.source_type,
                        "duration_ms": duration_ms,
                    },
                )
                await db.commit()
            timings["sentiment_ms"] = _elapsed_ms(stage_started)

            counts = compute_counts(chunks)
            top_positive = pick_top_quotes(chunks, SentimentLabel.POSITIVE)
            top_negative = pick_top_quotes(chunks, SentimentLabel.NEGATIVE)
            aspects = compute_aspects(chunks, topic)
            source_facts = compute_source_facts(chunks)
            chunks_summary = _summaries_for_synthesis(chunks)

            await emit(SSEEventType.SYNTHESIS_STARTED, "Synthesis started")
            await db.commit()

            stage_started = perf_counter()
            synthesis = await synthesize_report(topic, chunks_summary, counts, settings=settings)
            timings["synthesis_ms"] = _elapsed_ms(stage_started)
            themes = synthesis.get("themes", [])
            timings["total_ms"] = _elapsed_ms(run_started_at)
            report = {
                **counts,
                "top_positive": top_positive,
                "top_negative": top_negative,
                "themes": themes,
                "narrative": synthesis.get("narrative", "Synthesis unavailable."),
                "timings": timings,
                "aspects": aspects,
                "source_facts": source_facts,
                "graph": build_idea_graph(topic, chunks, themes, aspects),
            }

            run.report = report
            run.status = "completed"
            await emit(SSEEventType.RUN_COMPLETED, "Run completed", {"report": report})
            await db.commit()
        except Exception as exc:
            logger.exception("Run failed: %s", run_id)
            run = await db.get(Run, run_id)
            if run is not None:
                run.status = "error"
            await emit(
                SSEEventType.RUN_ERROR,
                "Run error",
                {"message": str(exc)},
            )
            await db.commit()
        finally:
            if queue is not None:
                queue.put_nowait(None)


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


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
    """Add opinion-heavy platforms while preserving model-generated intent."""
    platform_queries = [
        f"{topic} site:reddit.com",
        f"{topic} site:news.ycombinator.com",
        f"{topic} site:quora.com",
        f"{topic} site:youtube.com",
        f"{topic} forum discussion",
        f"{topic} user complaints",
    ]
    expanded = [*queries, *platform_queries]
    seen = set()
    unique = []
    for query in expanded:
        normalized = query.strip()
        if normalized and normalized.lower() not in seen:
            seen.add(normalized.lower())
            unique.append(normalized)
    return unique
