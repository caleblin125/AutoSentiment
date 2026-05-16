import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import event_bus, routes
from app.core.config import Settings
from app.models import Base, EvidenceChunk, Run


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_run_persists_pending_run_registers_queue_and_schedules_task(monkeypatch, db_session) -> None:
    scheduled = []

    async def fake_run_research(*_args, **_kwargs) -> None:
        scheduled.append(_args)
        return None

    monkeypatch.setattr(routes, "run_research", fake_run_research)

    response = await routes.create_run(
        routes.RunRequest(topic="  Tesla Model 3  ", freshness="pw"),
        db=db_session,
        settings=Settings(),
    )

    run = await db_session.get(Run, response.run_id)
    assert run is not None
    assert run.topic == "Tesla Model 3"
    assert run.freshness == "pw"
    assert run.status == "pending"
    assert event_bus.get(response.run_id) is not None
    await asyncio.sleep(0)
    assert len(scheduled) == 1

    event_bus.deregister(response.run_id)


@pytest.mark.asyncio
async def test_get_run_and_get_evidence_return_serializable_dicts(db_session) -> None:
    run = Run(topic="topic", freshness="pm", status="completed", report={"ok": True})
    db_session.add(run)
    await db_session.flush()
    chunk = EvidenceChunk(
        run_id=run.id,
        url="https://example.com",
        source_type="news",
        snippet="snippet",
        label="positive",
        summary="likes it",
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(run)
    await db_session.refresh(chunk)

    run_payload = await routes.get_run(run.id, db_session)
    evidence_payload = await routes.get_evidence(run.id, chunk.id, db_session)

    assert run_payload["report"] == {"ok": True}
    assert evidence_payload["snippet"] == "snippet"
    assert evidence_payload["run_id"] == run.id


@pytest.mark.asyncio
async def test_stream_events_yields_sse_data_and_deregisters(db_session) -> None:
    run = Run(topic="topic", freshness="pm", status="running")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    queue = event_bus.register(run.id)
    queue.put_nowait({"seq": 1, "type": "run_started", "message": "Run started", "detail": {}})
    queue.put_nowait(None)

    response = await routes.stream_events(run.id, db_session)
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    assert chunks == ['data: {"seq": 1, "type": "run_started", "message": "Run started", "detail": {}}\n\n']
    assert event_bus.get(run.id) is None


def test_run_request_validates_topic_and_freshness() -> None:
    with pytest.raises(ValueError):
        routes.RunRequest(topic="   ", freshness="pm")
    with pytest.raises(ValueError):
        routes.RunRequest(topic="topic", freshness="bad")
