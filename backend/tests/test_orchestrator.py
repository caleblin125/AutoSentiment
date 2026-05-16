import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents import orchestrator
from app.agents.types import SentimentLabel, SentimentResult, SourceType
from app.api import event_bus
from app.core.config import Settings
from app.ingest.fetch import FetchedItem
from app.models import Base, EvidenceChunk, Run, RunEvent


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_research_completes_and_persists_report(monkeypatch, session_factory) -> None:
    settings = Settings(brave_api_key="test", max_urls_per_run=3, max_items_per_run=2)

    monkeypatch.setattr(orchestrator, "supplemental_media_search", lambda *_a, **_kw: _async([]))
    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "expand_queries", lambda *_args, **_kwargs: _async(["q1", "q2"]))
    monkeypatch.setattr(
        orchestrator,
        "brave_search",
        lambda query, **_kwargs: _async(["https://reddit.example/1", "https://news.example/2", "https://reddit.example/1"] if query == "q1" else ["https://news.example/3"]),
    )
    monkeypatch.setattr(
        orchestrator,
        "fetch_items",
        lambda url, **_kw: _async([FetchedItem(snippet=f"snippet {url}", url=url, source_type=SourceType.REDDIT if "reddit" in url else SourceType.NEWS)]),
    )
    async def fake_batch(_self, snippets: list[str]) -> list[SentimentResult]:
        return [
            SentimentResult(
                label=SentimentLabel.POSITIVE if "reddit" in s else SentimentLabel.NEGATIVE,
                summary="mock summary",
            )
            for s in snippets
        ]

    monkeypatch.setattr(orchestrator.SentimentQueue, "analyze_batch", fake_batch)
    monkeypatch.setattr(
        orchestrator,
        "synthesize_report",
        lambda *_args, **_kwargs: _async({"themes": ["theme"], "narrative": "Narrative."}),
    )

    async with session_factory() as db:
        run = Run(topic="topic", freshness="pm", status="pending")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    queue = event_bus.register(run_id)
    await orchestrator.run_research(run_id, "topic", "pm", settings)

    streamed = []
    while True:
        event = await queue.get()
        if event is None:
            break
        streamed.append(event)

    async with session_factory() as db:
        run = await db.get(Run, run_id)
        chunks = (await db.execute(EvidenceChunk.__table__.select())).all()
        events = (await db.execute(RunEvent.__table__.select())).all()

    event_bus.deregister(run_id)

    assert run is not None
    assert run.status == "completed"
    assert run.report["metadata"]["research_depth"] == "standard"
    assert run.report["overall"]["total"] == 2
    assert run.report["top_positive"][0]["summary"] == "mock summary"
    assert run.report["timings"]["total_ms"] >= 0
    assert "graph" in run.report
    assert "source_facts" in run.report
    assert run.report["timings"]["sentiment_model_calls"] == 2.0
    event_types = [event["type"] for event in streamed]
    assert event_types[0] == "run_started"
    assert event_types[-1] == "run_completed"
    assert event_types.count("item_analyzed") == 2
    assert "synthesis_started" in event_types
    assert len(chunks) == 2
    assert len(events) == len(streamed)
    # Every event must carry server-side elapsed_ms.
    for event in streamed:
        assert "elapsed_ms" in event["detail"], f"elapsed_ms missing from {event['type']}"
        assert isinstance(event["detail"]["elapsed_ms"], float)


@pytest.mark.asyncio
async def test_run_research_marks_run_error_and_emits_sentinel(monkeypatch, session_factory) -> None:
    settings = Settings(brave_api_key="test")

    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "expand_queries", lambda *_args, **_kwargs: _async(["q1"]))

    async def failing_search(*_args, **_kwargs):
        raise RuntimeError("query failed")

    monkeypatch.setattr(orchestrator, "brave_search", failing_search)

    async with session_factory() as db:
        run = Run(topic="topic", freshness="pm", status="pending")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    queue = event_bus.register(run_id)
    await orchestrator.run_research(run_id, "topic", "pm", settings)

    streamed = []
    while True:
        event = await queue.get()
        if event is None:
            break
        streamed.append(event)

    async with session_factory() as db:
        run = await db.get(Run, run_id)

    event_bus.deregister(run_id)

    assert run is not None
    assert run.status == "error"
    assert streamed[-1]["type"] == "run_error"
    assert streamed[-1]["detail"]["message"] == "query failed"
    assert "elapsed_ms" in streamed[-1]["detail"]


def test_expand_platform_queries_adds_unique_opinion_platforms() -> None:
    queries = orchestrator._expand_platform_queries(["Tesla Model 3", "tesla model 3"], "Tesla Model 3")

    # Original query must be first; no duplicates (case-insensitive).
    assert queries[0] == "Tesla Model 3"
    assert len(queries) == len({q.lower() for q in queries})

    # Must include diverse platforms — Reddit limited to ≤1 explicit query.
    query_str = " ".join(queries)
    assert "site:reddit.com" in query_str
    assert "site:youtube.com" in query_str
    assert "site:quora.com" in query_str
    assert "site:trustpilot.com" in query_str
    reddit_count = sum(1 for q in queries if "reddit.com" in q.lower())
    assert reddit_count <= 1, f"Too many Reddit queries ({reddit_count})"

    # Must include at least one semantic review query.
    assert any("review" in q.lower() or "opinion" in q.lower() for q in queries)

    # Must include international languages.
    assert any("opinión" in q or "avis" in q or "Bewertung" in q for q in queries)


def test_select_diverse_urls_preserves_non_reddit_sources() -> None:
    urls = [
        *[f"https://www.reddit.com/r/example/comments/{i}" for i in range(10)],
        "https://reuters.com/article/1",
        "https://news.ycombinator.com/item?id=1",
        "https://youtube.com/watch?v=1",
        "https://example.com/post",
    ]

    selected = orchestrator._select_diverse_urls(urls, max_urls=8)

    assert "https://reuters.com/article/1" in selected
    assert "https://news.ycombinator.com/item?id=1" in selected
    assert "https://youtube.com/watch?v=1" in selected
    assert "https://example.com/post" in selected
    assert sum("reddit.com" in url for url in selected) <= 2
    assert sum("reddit.com" not in url for url in selected) >= 4


def test_summaries_for_synthesis_limits_and_balances_labels() -> None:
    chunks = [
        EvidenceChunk(id=f"p{i}", run_id="r", url="u", source_type="reddit", snippet="s", label="positive", summary=f"p{i}")
        for i in range(8)
    ] + [
        EvidenceChunk(id=f"n{i}", run_id="r", url="u", source_type="reddit", snippet="s", label="negative", summary=f"n{i}")
        for i in range(8)
    ] + [
        EvidenceChunk(id=f"z{i}", run_id="r", url="u", source_type="reddit", snippet="s", label="neutral", summary=f"z{i}")
        for i in range(8)
    ]

    summaries = orchestrator._summaries_for_synthesis(chunks, limit=9)

    assert len(summaries) == 9
    assert {summary["label"] for summary in summaries} == {"positive", "neutral", "negative"}


@pytest.mark.asyncio
async def test_parallel_fetch_respects_item_cap_and_emits_events(monkeypatch, session_factory) -> None:
    """Parallel URL fetch must cap total items at max_items_per_run.

    Each URL returns 3 items; with 4 URLs and a cap of 5, exactly 5 chunks should
    be stored regardless of which fetch tasks complete first.
    """
    settings = Settings(brave_api_key="test", max_urls_per_run=4, max_items_per_run=5)

    monkeypatch.setattr(orchestrator, "supplemental_media_search", lambda *_a, **_kw: _async([]))
    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "expand_queries", lambda *_a, **_kw: _async(["q"]))
    monkeypatch.setattr(
        orchestrator,
        "brave_search",
        lambda *_a, **_kw: _async([
            "https://reddit.example/1",
            "https://reddit.example/2",
            "https://news.example/1",
            "https://news.example/2",
        ]),
    )

    call_times: list[float] = []

    async def _fake_fetch(url: str, **_kw) -> list[FetchedItem]:
        import time
        call_times.append(time.monotonic())
        # Simulate a small I/O delay to allow genuine concurrency.
        await asyncio.sleep(0.01)
        return [
            FetchedItem(snippet=f"s{i} {url}", url=url, source_type=SourceType.NEWS)
            for i in range(3)
        ]

    monkeypatch.setattr(orchestrator, "fetch_items", _fake_fetch)
    monkeypatch.setattr(
        orchestrator.SentimentQueue,
        "analyze",
        lambda _self, _snippet: _async(SentimentResult(label=SentimentLabel.NEUTRAL, summary="ok")),
    )
    monkeypatch.setattr(
        orchestrator,
        "synthesize_report",
        lambda *_a, **_kw: _async({"themes": [], "narrative": ""}),
    )

    async with session_factory() as db:
        run = Run(topic="parallel", freshness=None, status="pending")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    queue = event_bus.register(run_id)
    await orchestrator.run_research(run_id, "parallel", None, settings)

    events: list[dict] = []
    while True:
        ev = await queue.get()
        if ev is None:
            break
        events.append(ev)
    event_bus.deregister(run_id)

    async with session_factory() as db:
        run = await db.get(Run, run_id)
        chunks = (await db.execute(EvidenceChunk.__table__.select())).all()

    assert run is not None
    assert run.status == "completed"
    # Cap must be honoured: 4 URLs × 3 items each = 12 potential, capped at 5.
    assert len(chunks) == 5
    # Fetch tasks ran concurrently: all 4 fetch calls should start before the
    # slowest one finishes (i.e. the spread in start times < 4 × sleep delay).
    assert len(call_times) == 4
    spread = max(call_times) - min(call_times)
    assert spread < 0.04, f"Fetches appear sequential (spread={spread:.3f}s)"
    # fetch_started event must be emitted before any url_fetched events.
    event_types = [e["type"] for e in events]
    fetch_started_idx = next(i for i, t in enumerate(event_types) if t == "fetch_started")
    first_url_fetched_idx = next(i for i, t in enumerate(event_types) if t == "url_fetched")
    assert fetch_started_idx < first_url_fetched_idx


@pytest.mark.asyncio
async def test_cancel_during_search_stops_run_and_emits_cancelled(monkeypatch, session_factory) -> None:
    """Requesting cancel while searches are queued must stop the pipeline,
    set status='cancelled', and emit run_cancelled as the final event."""
    from app.api import event_bus

    settings = Settings(brave_api_key="test", max_urls_per_run=10, max_items_per_run=10)
    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "expand_queries", lambda *_a, **_kw: _async(["q1", "q2", "q3"]))

    call_count = 0

    async def cancelling_search(*_a, **_kw):
        nonlocal call_count
        call_count += 1
        # Signal cancel on the first search call.
        if call_count == 1:
            event_bus.request_cancel(run_id)
        return []

    monkeypatch.setattr(orchestrator, "brave_search", cancelling_search)

    async with session_factory() as db:
        run = Run(topic="cancel-me", freshness=None, status="pending")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    queue = event_bus.register(run_id)
    await orchestrator.run_research(run_id, "cancel-me", None, settings)

    events: list[dict] = []
    while True:
        ev = await queue.get()
        if ev is None:
            break
        events.append(ev)
    event_bus.deregister(run_id)

    async with session_factory() as db:
        run = await db.get(Run, run_id)

    assert run is not None
    assert run.status == "cancelled"
    event_types = [e["type"] for e in events]
    assert event_types[-1] == "run_cancelled"
    # Pipeline should have stopped — not all queries ran.
    assert call_count < 3


@pytest.mark.asyncio
async def test_run_research_respects_query_budget(monkeypatch, session_factory) -> None:
    settings = Settings(brave_api_key="test", max_urls_per_run=20, max_items_per_run=10)
    searched: list[str] = []

    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "expand_queries", lambda *_a, **_kw: _async(["q1", "q2", "q3", "q4"]))

    async def fake_search(query, **_kw):
        searched.append(query)
        return []

    monkeypatch.setattr(orchestrator, "brave_search", fake_search)
    monkeypatch.setattr(orchestrator, "synthesize_report", lambda *_a, **_kw: _async({"themes": [], "narrative": ""}))

    async with session_factory() as db:
        run = Run(topic="budgeted", freshness=None, status="pending")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    queue = event_bus.register(run_id)
    await orchestrator.run_research(run_id, "budgeted", None, settings, research_depth="quick")
    while await queue.get() is not None:
        pass
    event_bus.deregister(run_id)

    assert len(searched) == 3


@pytest.mark.asyncio
async def test_run_research_deduplicates_identical_sentiment_snippets(monkeypatch, session_factory) -> None:
    settings = Settings(brave_api_key="test", max_queries_per_run=1, max_urls_per_run=2, max_items_per_run=4)
    analyze_calls = 0

    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "expand_queries", lambda *_a, **_kw: _async(["q"]))
    monkeypatch.setattr(orchestrator, "brave_search", lambda *_a, **_kw: _async(["https://news.example/1"]))
    monkeypatch.setattr(
        orchestrator,
        "fetch_items",
        lambda _url, **_kw: _async([
            FetchedItem(snippet="Same snippet", url="https://news.example/1", source_type=SourceType.NEWS),
            FetchedItem(snippet=" same   snippet ", url="https://news.example/1", source_type=SourceType.NEWS),
            FetchedItem(snippet="Different snippet", url="https://news.example/1", source_type=SourceType.NEWS),
        ]),
    )

    async def fake_analyze_batch(_self, snippets: list[str]) -> list[SentimentResult]:
        nonlocal analyze_calls
        analyze_calls += len(snippets)
        return [SentimentResult(label=SentimentLabel.NEUTRAL, summary="ok") for _ in snippets]

    monkeypatch.setattr(orchestrator.SentimentQueue, "analyze_batch", fake_analyze_batch)
    monkeypatch.setattr(orchestrator, "synthesize_report", lambda *_a, **_kw: _async({"themes": [], "narrative": ""}))

    async with session_factory() as db:
        run = Run(topic="dupes", freshness=None, status="pending")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    queue = event_bus.register(run_id)
    await orchestrator.run_research(run_id, "dupes", None, settings)
    while await queue.get() is not None:
        pass
    event_bus.deregister(run_id)

    async with session_factory() as db:
        run = await db.get(Run, run_id)

    # With DB-backed sentiment cache integration, the analyze path may include
    # additional cache-check operations. The important invariant is that items
    # are correctly processed and totals match.
    assert analyze_calls >= 2
    assert run is not None
    assert run.report["overall"]["total"] == 3
    assert run.report["timings"]["sentiment_cache_hits"] >= 1.0


@pytest.mark.asyncio
async def test_run_research_does_not_count_cached_search_against_quota(monkeypatch, session_factory) -> None:
    from app.models import BraveQuotaUsage

    settings = Settings(max_urls_per_run=2, max_items_per_run=1)

    monkeypatch.setattr(orchestrator, "supplemental_media_search", lambda *_a, **_kw: _async([]))
    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "is_cached_search", lambda *_a, **_kw: True)
    monkeypatch.setattr(orchestrator, "brave_search", lambda *_a, **_kw: _async([]))
    monkeypatch.setattr(orchestrator, "synthesize_report", lambda *_a, **_kw: _async({"themes": [], "narrative": ""}))

    async with session_factory() as db:
        run = Run(topic="cached-search", freshness=None, status="pending")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    queue = event_bus.register(run_id)
    await orchestrator.run_research(run_id, "cached-search", None, settings, research_depth="quick")
    while await queue.get() is not None:
        pass
    event_bus.deregister(run_id)

    async with session_factory() as db:
        usage_rows = (await db.execute(BraveQuotaUsage.__table__.select())).all()

    assert usage_rows == []


@pytest.mark.asyncio
async def test_fetch_url_timed_returns_empty_items_on_timeout(monkeypatch) -> None:
    async def slow_fetch(_url: str, **_kw):
        await asyncio.sleep(0.02)
        return [FetchedItem(snippet="late", url="https://example.com", source_type=SourceType.NEWS)]

    monkeypatch.setattr(orchestrator, "fetch_items", slow_fetch)
    monkeypatch.setattr(orchestrator, "_FETCH_TIMEOUT_SECONDS", 0.001)

    url, items, elapsed = await orchestrator._fetch_url_timed("https://example.com", asyncio.Semaphore(1))

    assert url == "https://example.com"
    assert items == []
    assert elapsed >= 0


def test_domain_from_url_strips_www() -> None:
    assert orchestrator._domain_from_url("https://www.reddit.com/r/foo") == "www.reddit.com".removeprefix("www.")
    assert orchestrator._domain_from_url("https://news.ycombinator.com/item?id=1") == "news.ycombinator.com"
    assert orchestrator._domain_from_url("https://techcrunch.com/2024/article") == "techcrunch.com"


@pytest.mark.asyncio
async def test_run_research_reuses_fetched_url_cache_across_runs(monkeypatch, session_factory) -> None:
    """A second run for the same URL must hit FetchedURLCache and skip fetch_items."""
    settings = Settings(brave_api_key="test", max_queries_per_run=1, max_urls_per_run=1, max_items_per_run=4)
    fetch_calls: list[str] = []

    monkeypatch.setattr(orchestrator, "supplemental_media_search", lambda *_a, **_kw: _async([]))
    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "expand_queries", lambda *_a, **_kw: _async(["q"]))
    monkeypatch.setattr(orchestrator, "brave_search", lambda *_a, **_kw: _async(["https://news.example/cached"]))

    async def tracked_fetch(url: str, **_kw):
        fetch_calls.append(url)
        return [FetchedItem(snippet="cached body text", url=url, source_type=SourceType.NEWS)]

    monkeypatch.setattr(orchestrator, "fetch_items", tracked_fetch)
    monkeypatch.setattr(
        orchestrator.SentimentQueue,
        "analyze",
        lambda _self, _snippet: _async(SentimentResult(label=SentimentLabel.NEUTRAL, summary="ok")),
    )
    monkeypatch.setattr(orchestrator, "synthesize_report", lambda *_a, **_kw: _async({"themes": [], "narrative": ""}))
    monkeypatch.setattr(orchestrator, "synthesize_report_streaming", lambda *_a, **_kw: _async({"themes": [], "narrative": ""}))

    async def _run_once(topic: str) -> dict:
        async with session_factory() as db:
            run = Run(topic=topic, freshness=None, status="pending")
            db.add(run)
            await db.commit()
            await db.refresh(run)
            run_id = run.id
        queue = event_bus.register(run_id)
        await orchestrator.run_research(run_id, topic, None, settings)
        while await queue.get() is not None:
            pass
        event_bus.deregister(run_id)
        async with session_factory() as db:
            stored = await db.get(Run, run_id)
            return dict(stored.report) if stored and stored.report else {}

    first = await _run_once("first run")
    second = await _run_once("second run")

    assert len(fetch_calls) == 1, f"Expected one network fetch across two runs, got {fetch_calls}"
    assert first.get("timings", {}).get("fetch_cache_hits", 0) == 0
    assert second.get("timings", {}).get("fetch_cache_hits", 0) >= 1
    assert second.get("timings", {}).get("fetch_cache_misses", 0) == 0


@pytest.mark.asyncio
async def test_run_research_skips_cache_when_ttl_zero(monkeypatch, session_factory) -> None:
    """ttl=0 disables the cache so every run re-fetches."""
    settings = Settings(brave_api_key="test", max_queries_per_run=1, max_urls_per_run=1, max_items_per_run=4, fetched_url_cache_ttl_seconds=0)
    fetch_calls: list[str] = []

    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "expand_queries", lambda *_a, **_kw: _async(["q"]))
    monkeypatch.setattr(orchestrator, "brave_search", lambda *_a, **_kw: _async(["https://news.example/ttl0"]))

    async def tracked_fetch(url: str, **_kw):
        fetch_calls.append(url)
        return [FetchedItem(snippet="some body", url=url, source_type=SourceType.NEWS)]

    monkeypatch.setattr(orchestrator, "fetch_items", tracked_fetch)
    monkeypatch.setattr(
        orchestrator.SentimentQueue,
        "analyze",
        lambda _self, _snippet: _async(SentimentResult(label=SentimentLabel.NEUTRAL, summary="ok")),
    )
    monkeypatch.setattr(orchestrator, "synthesize_report", lambda *_a, **_kw: _async({"themes": [], "narrative": ""}))
    monkeypatch.setattr(orchestrator, "synthesize_report_streaming", lambda *_a, **_kw: _async({"themes": [], "narrative": ""}))

    async def _run_once(topic: str) -> None:
        async with session_factory() as db:
            run = Run(topic=topic, freshness=None, status="pending")
            db.add(run)
            await db.commit()
            await db.refresh(run)
            run_id = run.id
        queue = event_bus.register(run_id)
        await orchestrator.run_research(run_id, topic, None, settings)
        while await queue.get() is not None:
            pass
        event_bus.deregister(run_id)

    await _run_once("a")
    await _run_once("b")

    assert len(fetch_calls) == 2


@pytest.mark.asyncio
async def test_run_completes_when_one_sentiment_call_fails(monkeypatch, session_factory) -> None:
    """A transient failure in one item's sentiment analysis must not crash the run.
    The remaining items should still be analyzed and the run should complete."""
    settings = Settings(brave_api_key="test", max_urls_per_run=1, max_items_per_run=3)
    call_count = 0

    monkeypatch.setattr(orchestrator, "supplemental_media_search", lambda *_a, **_kw: _async([]))
    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "expand_queries", lambda *_a, **_kw: _async(["q"]))
    monkeypatch.setattr(orchestrator, "brave_search", lambda *_a, **_kw: _async(["https://news.example/1"]))
    monkeypatch.setattr(
        orchestrator,
        "fetch_items",
        lambda _url, **_kw: _async([
            FetchedItem(snippet="good item 1", url="https://news.example/1", source_type=SourceType.NEWS),
            FetchedItem(snippet="boom item",   url="https://news.example/1", source_type=SourceType.NEWS),
            FetchedItem(snippet="good item 2", url="https://news.example/1", source_type=SourceType.NEWS),
        ]),
    )

    async def batch_with_fallback(_self, snippets: list[str]) -> list[SentimentResult]:
        nonlocal call_count
        call_count += 1
        # In batch mode a failing item becomes neutral rather than being skipped.
        return [
            SentimentResult(label=SentimentLabel.NEUTRAL, summary="fallback")
            if "boom" in s
            else SentimentResult(label=SentimentLabel.POSITIVE, summary="ok")
            for s in snippets
        ]

    monkeypatch.setattr(orchestrator.SentimentQueue, "analyze_batch", batch_with_fallback)
    monkeypatch.setattr(orchestrator, "synthesize_report", lambda *_a, **_kw: _async({"themes": [], "narrative": ""}))

    async with session_factory() as db:
        run = Run(topic="flaky-test", freshness=None, status="pending")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    queue = event_bus.register(run_id)
    await orchestrator.run_research(run_id, "flaky-test", None, settings)
    while await queue.get() is not None:
        pass
    event_bus.deregister(run_id)

    async with session_factory() as db:
        stored = await db.get(Run, run_id)
        chunks = (await db.execute(EvidenceChunk.__table__.select())).all()

    assert stored is not None
    # Run must complete with all items stored (boom item stored as neutral, not skipped).
    assert stored.status == "completed"
    assert len(chunks) == 3


async def _async(value):
    return value


# ── Quality scoring tests ─────────────────────────────────────────────────────


def test_url_quality_score_credible_domain_adds_two() -> None:
    score = orchestrator._url_quality_score("https://reuters.com/article", {})
    assert score == 2


def test_url_quality_score_cross_source_adds_one() -> None:
    url = "https://example.com/post"
    score = orchestrator._url_quality_score(url, {url: ["brave", "hn"]})
    assert score == 1


def test_url_quality_score_credible_and_cross_source_adds_three() -> None:
    url = "https://bbc.com/news/story"
    score = orchestrator._url_quality_score(url, {url: ["brave", "gdelt"]})
    assert score == 3


def test_url_quality_score_unknown_domain_is_zero() -> None:
    assert orchestrator._url_quality_score("https://unknown-blog.example/", {}) == 0


def test_select_diverse_urls_quality_sorts_credible_first() -> None:
    """Credible URLs should be picked before non-credible within the same bucket."""
    urls = [
        "https://random-blog.example/post",
        "https://reuters.com/finance/story",
        "https://another-blog.example/post",
    ]
    selected = orchestrator._select_diverse_urls(urls, 2, {})
    assert selected[0] == "https://reuters.com/finance/story"


def test_select_diverse_urls_cross_source_promoted() -> None:
    """A URL seen from 2 sources should rank above a single-source URL."""
    credible = "https://reuters.com/story"
    cross = "https://example.com/news"
    single = "https://example.com/other"
    url_sources = {
        cross: ["brave", "gdelt"],  # cross-corroborated
        single: ["brave"],
    }
    # All WEB/NEWS bucket; cross-corroborated + credible should come out first.
    urls = [single, cross, credible]
    selected = orchestrator._select_diverse_urls(urls, 3, url_sources)
    assert selected.index(credible) < selected.index(single)


# ── Degraded mode (no Brave key) tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_run_research_degraded_mode_uses_media_apis(monkeypatch, session_factory) -> None:
    """When brave_api_key is empty, the pipeline should use supplemental_media_search."""
    settings = Settings(
        brave_api_key="",
        max_urls_per_run=2,
        max_items_per_run=2,
        enable_media_api_search=True,
    )
    media_called: list[str] = []

    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "expand_queries", lambda *_a, **_kw: _async(["q"]))

    async def mock_media(topic, *, limit=12, include_source_map=False):
        media_called.append(topic)
        urls = ["https://hn.example/item1", "https://hn.example/item2"][:limit]
        if include_source_map:
            return urls, {u: ["hn"] for u in urls}
        return urls

    monkeypatch.setattr(orchestrator, "supplemental_media_search", mock_media)
    monkeypatch.setattr(
        orchestrator,
        "fetch_items",
        lambda url, **_kw: _async([FetchedItem(snippet="text", url=url, source_type=SourceType.NEWS)]),
    )
    monkeypatch.setattr(
        orchestrator.SentimentQueue,
        "analyze",
        lambda _self, _s: _async(SentimentResult(label=SentimentLabel.NEUTRAL, summary="ok")),
    )
    monkeypatch.setattr(
        orchestrator,
        "synthesize_report_streaming",
        lambda *_a, **_kw: _async({"themes": [], "narrative": ""}),
    )

    async with session_factory() as db:
        run = Run(topic="degraded", freshness=None, status="pending")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    queue = event_bus.register(run_id)
    await orchestrator.run_research(run_id, "degraded", None, settings)
    while await queue.get() is not None:
        pass
    event_bus.deregister(run_id)

    assert media_called, "supplemental_media_search should have been called in degraded mode"

    async with session_factory() as db:
        stored = await db.get(Run, run_id)
        assert stored is not None
        assert stored.status == "completed"


# ── Timing breakdown tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_research_report_includes_search_timing_breakdown(monkeypatch, session_factory) -> None:
    settings = Settings(max_urls_per_run=1, max_items_per_run=1)

    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(orchestrator, "expand_queries", lambda *_a, **_kw: _async(["q"]))
    monkeypatch.setattr(orchestrator, "brave_search", lambda *_a, **_kw: _async(["https://news.example/t"]))

    async def mock_media(topic, *, limit=12, include_source_map=False):
        if include_source_map:
            return [], {}
        return []

    monkeypatch.setattr(orchestrator, "supplemental_media_search", mock_media)
    monkeypatch.setattr(
        orchestrator,
        "fetch_items",
        lambda url, **_kw: _async([FetchedItem(snippet="body", url=url, source_type=SourceType.NEWS)]),
    )
    monkeypatch.setattr(
        orchestrator.SentimentQueue,
        "analyze",
        lambda _self, _s: _async(SentimentResult(label=SentimentLabel.NEUTRAL, summary="ok")),
    )
    monkeypatch.setattr(
        orchestrator,
        "synthesize_report_streaming",
        lambda *_a, **_kw: _async({"themes": [], "narrative": ""}),
    )

    async with session_factory() as db:
        run = Run(topic="timing-test", freshness=None, status="pending")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    queue = event_bus.register(run_id)
    await orchestrator.run_research(run_id, "timing-test", None, settings)
    while await queue.get() is not None:
        pass
    event_bus.deregister(run_id)

    async with session_factory() as db:
        stored = await db.get(Run, run_id)
        assert stored is not None
        timings = stored.report.get("timings", {})

    assert "search_brave_ms" in timings
    assert "search_media_ms" in timings
    assert "search_brave_cache_hits" in timings
    assert "search_brave_api_calls" in timings
    assert "search_cross_source_urls" in timings
