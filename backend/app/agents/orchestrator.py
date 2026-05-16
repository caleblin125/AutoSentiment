"""Main research pipeline — wires all stages and emits SSE events."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.api import event_bus
from app.agents.light_queue import SentimentQueue
from app.agents.nemoclaw import expand_queries, synthesize_report
from app.agents.types import SSEEventType, SentimentLabel
from app.db.session import AsyncSessionLocal
from app.ingest.fetch import fetch_items, is_reddit_url
from app.models import EvidenceChunk, Run, RunEvent
from app.reports.builder import compute_counts, pick_top_quotes
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

            queries = await expand_queries(topic, settings=settings)
            urls: list[str] = []
            seen_urls: set[str] = set()

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

            fetched_items = []
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
                    else ("reddit" if is_reddit_url(url) else "news")
                )
                await emit(
                    SSEEventType.URL_FETCHED,
                    "URL fetched",
                    {"url": url, "source_type": source_type, "item_count": len(selected_items)},
                )
                await db.commit()

            sentiment_queue = SentimentQueue(settings)
            chunks: list[EvidenceChunk] = []

            for item in fetched_items:
                result = await sentiment_queue.analyze(item.snippet)
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
                    },
                )
                await db.commit()

            counts = compute_counts(chunks)
            top_positive = pick_top_quotes(chunks, SentimentLabel.POSITIVE)
            top_negative = pick_top_quotes(chunks, SentimentLabel.NEGATIVE)
            chunks_summary = [
                {
                    "label": chunk.label,
                    "summary": chunk.summary,
                    "url": chunk.url,
                    "source_type": chunk.source_type,
                }
                for chunk in chunks
            ]

            await emit(SSEEventType.SYNTHESIS_STARTED, "Synthesis started")
            await db.commit()

            synthesis = await synthesize_report(topic, chunks_summary, counts, settings=settings)
            report = {
                **counts,
                "top_positive": top_positive,
                "top_negative": top_negative,
                "themes": synthesis.get("themes", []),
                "narrative": synthesis.get("narrative", "Synthesis unavailable."),
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
