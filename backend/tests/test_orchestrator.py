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
    assert [event["type"] for event in streamed] == [
        "run_started",
        "search_queried",
        "search_queried",
        "url_fetched",
        "url_fetched",
        "item_analyzed",
        "item_analyzed",
        "synthesis_started",
        "run_completed",
    ]
    assert len(chunks) == 2
    assert len(events) == len(streamed)


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
    assert streamed[-1]["detail"] == {"message": "query failed"}


async def _async(value):
    return value
