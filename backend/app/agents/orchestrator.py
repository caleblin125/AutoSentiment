"""Main research pipeline — wires all stages and emits SSE events."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from time import perf_counter
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from app.api import event_bus
from app.api.event_bus import clear_cancel, is_cancelled, request_cancel as _request_cancel  # noqa: F401
from app.agents.light_queue import SentimentQueue
from app.agents.nemoclaw import expand_queries, synthesize_report, synthesize_report_streaming
from app.agents.ollama import GenerationCancelled
from app.agents.types import SSEEventType, SentimentLabel, SentimentResult
from app.db.session import AsyncSessionLocal
from app.ingest.fetch import classify_source_type, fetch_items, batch_read_url_cache, read_url_cache, write_url_cache
from app.models import EvidenceChunk, Run, RunEvent
from app.reports.builder import (
    build_idea_graph,
    compute_aspects,
    compute_claims,
    compute_chart_data,
    compute_counts,
    compute_source_facts,
    compute_threads,
    compute_timeline,
    compute_use_case_insights,
    pick_top_quotes,
)
from app.search_planner import build_search_plan, record_brave_query
from app.tools.search import brave_search, is_cached_search
from app.tools.media_apis import supplemental_media_search

if TYPE_CHECKING:
    from app.core.config import Settings


class ErrorCode(str, Enum):
    """Explicit error codes for client-facing messages."""
    BRAVE_KEY_MISSING = "brave_key_missing"
    BRAVE_QUOTA_EXCEEDED = "brave_quota_exceeded"
    BRAVE_RATE_LIMITED = "brave_rate_limited"
    MODEL_UNAVAILABLE = "model_unavailable"
    FETCH_TIMEOUT = "fetch_timeout"
    SYNTHESIS_FAILED = "synthesis_failed"
    CANCELLED_BY_USER = "cancelled_by_user"
    INTERNAL_ERROR = "internal_error"


class StructuredLogger(logging.LoggerAdapter):
    """Logger adapter that prefixes every message with the run ID."""
    def process(self, msg, kwargs):
        extra = self.extra or {}
        run_id = extra.get("run_id", "unknown")
        return f"[run={run_id}] {msg}", kwargs


logger = logging.getLogger(__name__)


def _get_logger(run_id: str) -> StructuredLogger:
    return StructuredLogger(logger, {"run_id": run_id})

_FETCH_CONCURRENCY = 12        # Task 4: increased from 8; domain caps prevent hammering any one host
_FETCH_CONCURRENCY_PER_DOMAIN = 2
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
        "search_brave_ms": 0.0,
        "search_media_ms": 0.0,
        "search_brave_cache_hits": 0.0,
        "search_brave_api_calls": 0.0,
        "search_cross_source_urls": 0.0,
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

            # ── Stage 2: search ─────────────────────────────────────────────
            # url_sources tracks which search backends found each URL so we can
            # score cross-corroborated URLs higher in the quality ranking step.
            urls: list[str] = []
            seen_urls: set[str] = set()
            url_sources: dict[str, list[str]] = {}  # url -> ["brave", "gdelt", ...]

            stage_started = perf_counter()
            brave_ms: float = 0.0
            media_api_ms: float = 0.0
            brave_cache_hits: int = 0
            brave_api_calls: int = 0

            # ── 2a: Brave search (rate-limited, sequential) ─────────────────
            # Pre-classify queries to batch quota recording for non-cached ones.
            if settings.brave_api_key:
                uncached_queries = [
                    q for q in queries
                    if not is_cached_search(q, freshness=freshness, count=settings.max_urls_per_run)
                ]
                brave_cache_hits = len(queries) - len(uncached_queries)
                if uncached_queries:
                    for _ in uncached_queries:
                        await record_brave_query(db)
                    await db.commit()

                _brave_t0 = perf_counter()
                for query in queries:
                    if is_cancelled(run_id):
                        raise _CancelledByUser()

                    await emit(SSEEventType.SEARCH_QUERIED, "Search queried", {"query": query})
                    await db.commit()

                    remaining = settings.max_urls_per_run - len(urls)
                    if remaining <= 0:
                        break

                    try:
                        search_results = await asyncio.wait_for(
                            brave_search(query, freshness=freshness, count=remaining, settings=settings, db=db),
                            timeout=12.0,
                        )
                        brave_api_calls += 1
                    except asyncio.TimeoutError:
                        if is_cancelled(run_id):
                            raise _CancelledByUser()
                        logger.warning("Brave search timed out: %s", query)
                        continue
                    if is_cancelled(run_id):
                        raise _CancelledByUser()
                    for url in search_results:
                        if url in seen_urls or url in skip_urls:
                            continue
                        seen_urls.add(url)
                        url_sources.setdefault(url, []).append("brave")
                        urls.append(url)
                        if len(urls) >= settings.max_urls_per_run:
                            break
                brave_ms = _elapsed_ms(_brave_t0)
            else:
                logger.warning("No BRAVE_API_KEY — running in degraded mode (media APIs only)")

            # ── 2b: Supplemental media APIs (no key required, parallel) ─────
            # Always run when enabled; not gated on Brave key so degraded mode works.
            if getattr(settings, "enable_media_api_search", True) and len(urls) < settings.max_urls_per_run:
                _media_t0 = perf_counter()
                try:
                    api_result = await supplemental_media_search(
                        topic,
                        limit=settings.max_urls_per_run - len(urls),
                        include_source_map=True,
                    )
                    api_urls: list[str]
                    api_source_map: dict[str, list[str]]
                    if isinstance(api_result, tuple):
                        api_urls, api_source_map = api_result
                    else:
                        api_urls, api_source_map = api_result, {}
                except Exception:
                    api_urls, api_source_map = [], {}
                media_api_ms = _elapsed_ms(_media_t0)

                for url in api_urls:
                    if url in skip_urls:
                        continue
                    for src in api_source_map.get(url, ["media_api"]):
                        url_sources.setdefault(url, []).append(src)
                    if url not in seen_urls:
                        seen_urls.add(url)
                        urls.append(url)
                    if len(urls) >= settings.max_urls_per_run:
                        break

            # ── 2c: Quality-ranked diversity selection ───────────────────────
            urls = _select_diverse_urls(urls, settings.max_urls_per_run, url_sources)

            timings["search_ms"] = _elapsed_ms(stage_started)
            timings["search_brave_ms"] = brave_ms
            timings["search_media_ms"] = media_api_ms
            timings["search_brave_cache_hits"] = float(brave_cache_hits)
            timings["search_brave_api_calls"] = float(brave_api_calls)
            timings["search_cross_source_urls"] = float(
                sum(1 for srcs in url_sources.values() if len(set(srcs)) > 1)
            )

            if is_cancelled(run_id):
                raise _CancelledByUser()

            # ── Stage 3: parallel URL fetch ─────────────────────────────────
            await emit(SSEEventType.FETCH_STARTED, f"Fetching {len(urls)} URLs", {"url_count": len(urls)})
            await db.commit()

            global_sem = asyncio.Semaphore(_FETCH_CONCURRENCY)
            domain_sems: dict[str, asyncio.Semaphore] = {}
            def _domain_sem(domain: str) -> asyncio.Semaphore:
                if domain not in domain_sems:
                    domain_sems[domain] = asyncio.Semaphore(_FETCH_CONCURRENCY_PER_DOMAIN)
                return domain_sems[domain]
            fetched_items: list[FetchedItem] = []  # type: ignore[name-defined]
            cache_hits = 0
            stage_started = perf_counter()

            ttl_seconds = getattr(settings, "fetched_url_cache_ttl_seconds", 86_400)

            # Batch-read URL cache in one SELECT IN query (Task 3).
            cache_batch = await batch_read_url_cache(db, urls, ttl_seconds)
            cached_pairs: list[tuple[str, list]] = [
                (url, items) for url, items in cache_batch.items() if items is not None
            ]
            uncached_urls: list[str] = [url for url, items in cache_batch.items() if items is None]

            # Emit cache hits up-front so the UI sees progress immediately.
            for url, items in cached_pairs:
                if is_cancelled(run_id):
                    raise _CancelledByUser()
                cache_hits += 1
                remaining = settings.max_items_per_run - len(fetched_items)
                selected = items[:remaining] if remaining > 0 else []
                fetched_items.extend(selected)
                source_type = (
                    selected[0].source_type.value if selected else classify_source_type(url).value
                )
                domain = _domain_from_url(url)
                await emit(
                    SSEEventType.URL_FETCHED,
                    f"Fetched {len(selected)} items from {domain} (cached)",
                    {
                        "url": url,
                        "domain": domain,
                        "source_type": source_type,
                        "item_count": len(selected),
                        "fetch_ms": 0.0,
                        "cache_hit": True,
                    },
                )
                await db.commit()

            async with httpx.AsyncClient(
                timeout=10.0,
                headers={"User-Agent": _FETCH_USER_AGENT},
                follow_redirects=True,
            ) as fetch_client:
                fetch_tasks = [
                    asyncio.create_task(_fetch_url_timed(url, global_sem, fetch_client, _domain_sem(_domain_from_url(url))))
                    for url in uncached_urls
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

                    # Persist on cache miss so future runs reuse this fetch.
                    if items and ttl_seconds > 0:
                        await write_url_cache(db, url, items)

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
                            "cache_hit": False,
                        },
                    )
                    await db.commit()
            timings["fetch_ms"] = _elapsed_ms(stage_started)
            timings["fetch_cache_hits"] = float(cache_hits)
            timings["fetch_cache_misses"] = float(len(uncached_urls))

            # ── Stage 4: sentiment analysis (parallel, batched) ───────────────
            sentiment_queue = SentimentQueue(settings, cancel_check=_cancel_check)
            chunks: list[EvidenceChunk] = []
            pending_cache: dict[str, tuple[str, str]] = {}
            confidence_map: dict[str, float] = {}

            stage_started = perf_counter()

            # Deduplicate snippets by cache key, preserving item order.
            seen_keys: dict[str, int] = {}  # cache_key -> first index
            unique_items: list = []
            for item in fetched_items:
                key = _sentiment_cache_key(item.snippet)
                if key not in seen_keys:
                    seen_keys[key] = len(unique_items)
                    unique_items.append(item)

            # Check DB sentiment cache for each unique snippet.
            unique_snippets = [item.snippet for item in unique_items]
            cached_results: dict[int, SentimentResult] = {}
            uncached_indices: list[int] = []
            if db is not None:
                import hashlib
                from app.models import SentimentCache
                from sqlalchemy import select as _sel3
                snippet_hashes = [hashlib.sha256(_sentiment_cache_key(s).encode()).hexdigest() for s in unique_snippets]
                rows = (await db.execute(
                    _sel3(SentimentCache).where(SentimentCache.snippet_hash.in_(snippet_hashes))
                )).scalars().all()
                row_map = {r.snippet_hash: r for r in rows}
                for i, sh in enumerate(snippet_hashes):
                    row = row_map.get(sh)
                    if row is not None:
                        cached_results[i] = SentimentResult(label=SentimentLabel(row.label), summary=row.summary)
                    else:
                        uncached_indices.append(i)
            else:
                uncached_indices = list(range(len(unique_items)))

            # Batch-analyze uncached snippets.
            if uncached_indices:
                uncached_snippets = [unique_snippets[i] for i in uncached_indices]
                batch_results = await sentiment_queue.analyze_batch(uncached_snippets)
                for j, idx in enumerate(uncached_indices):
                    if j < len(batch_results):
                        cached_results[idx] = batch_results[j]
                    else:
                        cached_results[idx] = SentimentResult(label=SentimentLabel.NEUTRAL, summary="batch miss")

            # Map results back to all fetched items (including duplicates).
            for item in fetched_items:
                if is_cancelled(run_id):
                    raise _CancelledByUser()
                key = _sentiment_cache_key(item.snippet)
                unique_idx = seen_keys[key]
                result = cached_results.get(unique_idx)
                if result is None:
                    result = SentimentResult(label=SentimentLabel.NEUTRAL, summary="analysis miss")

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
                confidence_map[chunk.id] = round(result.confidence, 2)

                import hashlib
                snippet_hash = hashlib.sha256(key.encode()).hexdigest()
                if snippet_hash not in pending_cache:
                    pending_cache[snippet_hash] = (result.label.value, result.summary)

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
                        "duration_ms": 0,
                        "confidence": confidence_map[chunk.id],
                    },
                )
                await db.commit()

            # Bulk-insert sentiment cache entries (deduplicated by dict).
            if pending_cache:
                from sqlalchemy import select as _sel
                from app.models import SentimentCache
                for snippet_hash, (label, summary) in pending_cache.items():
                    existing = (await db.execute(
                        _sel(SentimentCache).where(SentimentCache.snippet_hash == snippet_hash)
                    )).scalar_one_or_none()
                    if existing is None:
                        db.add(SentimentCache(snippet_hash=snippet_hash, label=label, summary=summary))
                await db.flush()

            timings["sentiment_ms"] = _elapsed_ms(stage_started)
            timings["sentiment_model_calls"] = float(len(uncached_indices))
            timings["sentiment_cache_hits"] = float(max(0, len(fetched_items) - len(uncached_indices)))

            # ── Stage 5: synthesis ──────────────────────────────────────────
            # Expanded and similar-topic runs can seed existing evidence before
            # new fetching starts; merge all stored chunks into this report.
            all_chunks_result = await db.execute(
                select(EvidenceChunk).where(EvidenceChunk.run_id == run_id)
            )
            chunks = list(all_chunks_result.scalars().all())
            counts = compute_counts(chunks)
            top_positive = pick_top_quotes(chunks, SentimentLabel.POSITIVE, confidence_map=confidence_map)
            top_negative = pick_top_quotes(chunks, SentimentLabel.NEGATIVE, confidence_map=confidence_map)
            aspects = compute_aspects(chunks, topic)
            source_facts = compute_source_facts(chunks)
            timeline = compute_timeline(chunks, topic)
            fact_check = compute_claims(chunks)
            threads = compute_threads(chunks, topic)
            use_case_insights = compute_use_case_insights(chunks, use_case, aspects, fact_check)
            chart_data = compute_chart_data(chunks, aspects, fact_check)
            synthesis_limit = _synthesis_limit(depth_budget)
            chunks_summary = _summaries_for_synthesis(chunks, limit=synthesis_limit)

            await emit(SSEEventType.SYNTHESIS_STARTED, "Synthesis started")
            await db.commit()

            stage_started = perf_counter()
            token_buf: list[str] = []
            async def _on_synthesis_token(token: str):
                token_buf.append(token)
                # Emit every ~8 tokens to avoid flooding the SSE stream.
                if len(token_buf) >= 8:
                    await emit(SSEEventType.SYNTHESIS_TOKEN, "", {"text": "".join(token_buf)})
                    token_buf.clear()

            synthesis = await synthesize_report_streaming(
                topic, chunks_summary, counts,
                settings=settings, cancel_check=_cancel_check,
                on_token=_on_synthesis_token,
            )
            # Flush remaining tokens.
            if token_buf:
                await emit(SSEEventType.SYNTHESIS_TOKEN, "", {"text": "".join(token_buf)})
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
                "threads": threads,
                "use_case_insights": use_case_insights,
                "chart_data": chart_data,
                "graph": build_idea_graph(topic, chunks, themes, aspects),
            }

            run.report = report
            run.status = "completed"
            await emit(SSEEventType.RUN_COMPLETED, "Run completed", {"report": report})
            await db.commit()

        except (_CancelledByUser, GenerationCancelled):
            _get_logger(run_id).info("Run cancelled by user")
            run = await db.get(Run, run_id)
            if run is not None:
                run.status = "cancelled"
            await emit(SSEEventType.RUN_CANCELLED, "Run cancelled",
                       {"error_code": ErrorCode.CANCELLED_BY_USER.value})
            await db.commit()

        except Exception as exc:
            _get_logger(run_id).exception("Run failed")
            run = await db.get(Run, run_id)
            if run is not None:
                run.status = "error"
            error_code = _classify_error(exc)
            await emit(SSEEventType.RUN_ERROR, "Run error",
                       {"message": str(exc), "error_code": error_code.value})
            await db.commit()

        finally:
            clear_cancel(run_id)
            if queue is not None:
                queue.put_nowait(None)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def _classify_error(exc: Exception) -> ErrorCode:
    """Map common exception types to explicit error codes."""
    msg = str(exc).lower()
    if "brave" in msg and ("key" in msg or "401" in msg):
        return ErrorCode.BRAVE_KEY_MISSING
    if "429" in msg or "rate" in msg:
        return ErrorCode.BRAVE_RATE_LIMITED
    if "quota" in msg or "exceeded" in msg:
        return ErrorCode.BRAVE_QUOTA_EXCEEDED
    if "connect" in msg or "refused" in msg or "timeout" in msg:
        return ErrorCode.MODEL_UNAVAILABLE
    if "timeout" in msg:
        return ErrorCode.FETCH_TIMEOUT
    if "synthesis" in msg or "synthesize" in msg:
        return ErrorCode.SYNTHESIS_FAILED
    return ErrorCode.INTERNAL_ERROR


async def recover_stale_runs() -> int:
    """Mark any runs still in 'running' state as 'error' on startup.

    Returns the number of recovered runs. This ensures the database
    reflects reality after an unclean shutdown.
    """
    from sqlalchemy import update
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(Run)
            .where(Run.status == "running")
            .values(status="error")
        )
        await db.commit()
        count = result.rowcount
        if count:
            logging.getLogger(__name__).info(
                "Recovered %d stale running run(s) after restart", count
            )
        return count


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
    domain_sem: asyncio.Semaphore | None = None,
) -> tuple[str, list, float]:
    """Fetch items from one URL with retry, returning (url, items, duration_ms)."""
    t0 = perf_counter()
    items: list = []
    async with sem:
        ds = domain_sem
        for attempt in range(3):
            try:
                async with (ds() if ds and attempt > 0 else (ds if ds else _null_context())):
                    inner = asyncio.wait_for(
                        fetch_items(url, client=client), timeout=_FETCH_TIMEOUT_SECONDS
                    )
                    if ds and attempt == 0:
                        items = await inner
                    else:
                        items = await inner
                    break
            except asyncio.TimeoutError:
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                logger.warning("Fetch timed out after 3 attempts: %s", url)
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                logger.warning("Fetch failed after 3 attempts: %s", url)
    return url, items, _elapsed_ms(t0)


def _null_context():
    """Async no-op context manager for when domain_sem is None."""
    class _NullCtx:
        async def __aenter__(self): return None
        async def __aexit__(self, *a): pass
    return _NullCtx()


async def _analyze_item(sentiment_queue: SentimentQueue, item) -> tuple:
    """Analyze one fetched item and retain timing for per-item telemetry."""
    started_at = perf_counter()
    result = await sentiment_queue.analyze(item.snippet)
    return item, result, _elapsed_ms(started_at)


async def _analyze_item_cached(
    sentiment_queue: SentimentQueue,
    item,
    sentiment_tasks: dict[str, asyncio.Task],
    db = None,
) -> tuple:
    """Share one model call across exact duplicate snippets within a run.
    Also checks the persistent sentiment cache (SQLite) before calling the model."""
    started_at = perf_counter()
    key = _sentiment_cache_key(item.snippet)
    task = sentiment_tasks.get(key)
    if task is not None:
        result = await task
        return item, result, _elapsed_ms(started_at), key

    # Check persistent sentiment cache.
    if db is not None:
        from sqlalchemy import select as _sel2
        from app.models import SentimentCache
        import hashlib
        snippet_hash = hashlib.sha256(key.encode()).hexdigest()
        row = (await db.execute(
            _sel2(SentimentCache).where(SentimentCache.snippet_hash == snippet_hash)
        )).scalar_one_or_none()
        if row is not None:
            from app.agents.types import SentimentLabel as _SL, SentimentResult
            try:
                label_enum = _SL(row.label)
            except ValueError:
                label_enum = _SL.NEUTRAL
            result = SentimentResult(label=label_enum, summary=row.summary)
            async def _cached_result():
                return result
            sentiment_tasks[key] = asyncio.ensure_future(_cached_result())
            return item, result, _elapsed_ms(started_at), key

    task = asyncio.create_task(sentiment_queue.analyze(item.snippet))
    sentiment_tasks[key] = task
    result = await task

    return item, result, _elapsed_ms(started_at), key


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


def _url_quality_score(url: str, url_sources: dict[str, list[str]]) -> int:
    """Score a URL for quality ranking within its source bucket.

    Higher scores surface first within each diversity bucket:
      +2  URL is from a credible domain (established news, academic, etc.)
      +1  URL was found by 2+ independent search backends (cross-corroborated)
    """
    score = 0
    try:
        domain = urlparse(url).netloc.removeprefix("www.")
        if domain in _CREDIBLE_DOMAINS_SET or any(domain.endswith(f".{d}") for d in _CREDIBLE_DOMAINS_SET):
            score += 2
    except Exception:
        pass
    sources = url_sources.get(url, [])
    if len(set(sources)) > 1:
        score += 1
    return score


def _select_diverse_urls(
    urls: list[str],
    max_urls: int,
    url_sources: dict[str, list[str]] | None = None,
) -> list[str]:
    """Balance fetched URLs across source buckets before expensive extraction.

    Within each bucket, URLs are ranked by quality score (credibility +
    cross-source corroboration) so the best candidates are analysed first.
    Brave can return many same-platform URLs for broad public-opinion queries.
    Round-robin selection keeps news, forum, video, social, and web sources
    represented while still allowing Reddit to contribute.
    """
    if max_urls <= 0:
        return []

    _sources = url_sources or {}

    priority = ["news", "web", "forum", "video", "social", "reddit"]
    groups: dict[str, list[str]] = {key: [] for key in priority}
    for url in urls:
        source = classify_source_type(url).value
        groups.setdefault(source, []).append(url)

    # Sort within each bucket by quality score descending so we pick the best
    # candidates when a bucket must be trimmed by the cap.
    for bucket in groups.values():
        bucket.sort(key=lambda u: _url_quality_score(u, _sources), reverse=True)

    caps = {
        "reddit": max(2, int(max_urls * 0.25 + 0.999)),
        "social": max(2, int(max_urls * 0.35 + 0.999)),
        "forum": max(2, int(max_urls * 0.40 + 0.999)),
    }
    selected: list[str] = []
    skipped: list[str] = []
    counts: dict[str, int] = {}

    while len(selected) < max_urls and any(groups.values()):
        progressed = False
        for source in priority:
            bucket = groups.get(source)
            if not bucket:
                continue
            url = bucket.pop(0)
            cap = caps.get(source, max_urls)
            if counts.get(source, 0) >= cap:
                skipped.append(url)
                progressed = True
                continue
            selected.append(url)
            counts[source] = counts.get(source, 0) + 1
            progressed = True
            if len(selected) >= max_urls:
                break
        if not progressed:
            break

    # Fill any remaining slots from capped-but-available URLs, still respecting
    # caps (so one platform still can't monopolise a run).
    for url in skipped:
        if len(selected) >= max_urls:
            break
        source = classify_source_type(url).value
        cap = caps.get(source, max_urls)
        if counts.get(source, 0) >= cap:
            continue
        selected.append(url)
        counts[source] = counts.get(source, 0) + 1
    return selected
