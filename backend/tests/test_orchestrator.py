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
    settings = Settings(max_urls_per_run=3, max_items_per_run=2)

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
        lambda url: _async([FetchedItem(snippet=f"snippet {url}", url=url, source_type=SourceType.REDDIT if "reddit" in url else SourceType.NEWS)]),
    )
    monkeypatch.setattr(
        orchestrator.SentimentQueue,
        "analyze",
        lambda _self, snippet: _async(
            SentimentResult(
                label=SentimentLabel.POSITIVE if "reddit" in snippet else SentimentLabel.NEGATIVE,
                summary="mock summary",
            )
        ),
    )
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
    assert run.report["overall"]["total"] == 2
    assert run.report["top_positive"][0]["summary"] == "mock summary"
    assert run.report["timings"]["total_ms"] >= 0
    assert "graph" in run.report
    assert "source_facts" in run.report
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
    settings = Settings()

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

    assert queries[0] == "Tesla Model 3"
    assert len(queries) == len({query.lower() for query in queries})
    assert "Tesla Model 3 site:reddit.com" in queries
    assert "Tesla Model 3 site:youtube.com" in queries
    assert "Tesla Model 3 forum discussion" in queries


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
    settings = Settings(max_urls_per_run=4, max_items_per_run=5)

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

    async def _fake_fetch(url: str) -> list[FetchedItem]:
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

    settings = Settings(max_urls_per_run=10, max_items_per_run=10)
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


def test_domain_from_url_strips_www() -> None:
    assert orchestrator._domain_from_url("https://www.reddit.com/r/foo") == "www.reddit.com".removeprefix("www.")
    assert orchestrator._domain_from_url("https://news.ycombinator.com/item?id=1") == "news.ycombinator.com"
    assert orchestrator._domain_from_url("https://techcrunch.com/2024/article") == "techcrunch.com"


async def _async(value):
    return value
