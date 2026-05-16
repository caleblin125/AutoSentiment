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


@pytest.mark.asyncio
async def test_create_run_returns_cached_when_recent_completed_run_exists(monkeypatch, db_session) -> None:
    """POST /api/runs must return cached=True and the existing run_id when a
    completed run for the same topic+freshness exists within the TTL window."""
    monkeypatch.setattr(routes, "run_research", lambda *_a, **_kw: None)

    # Seed a completed run that is fresh (within TTL).
    from datetime import UTC, datetime
    existing = Run(
        topic="EV trucks",
        freshness="pm",
        status="completed",
        created_at=datetime.now(UTC),
        report={"overall": {"total": 10}},
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    response = await routes.create_run(
        routes.RunRequest(topic="EV trucks", freshness="pm"),
        db=db_session,
        settings=Settings(),
    )

    assert response.cached is True
    assert response.run_id == existing.id


@pytest.mark.asyncio
async def test_cancel_run_signals_event_bus_and_returns_cancelled(db_session) -> None:
    """POST /api/runs/{id}/cancel must call request_cancel and return cancelled=True."""
    from app.api import event_bus as eb

    run = Run(topic="cancel-me", freshness=None, status="running")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    cancelled_calls: list[str] = []
    real_request_cancel = eb.request_cancel

    def patched_cancel(rid: str) -> None:
        cancelled_calls.append(rid)
        real_request_cancel(rid)

    import unittest.mock
    with unittest.mock.patch.object(eb, "request_cancel", patched_cancel):
        result = await routes.cancel_run(run.id, db_session)

    assert result["cancelled"] is True
    assert run.id in cancelled_calls
    eb.clear_cancel(run.id)


@pytest.mark.asyncio
async def test_cancel_run_no_ops_for_completed_run(db_session) -> None:
    """Cancelling a completed run must return cancelled=False without side-effects."""
    from app.api import event_bus as eb

    run = Run(topic="done", freshness=None, status="completed")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    result = await routes.cancel_run(run.id, db_session)
    assert result["cancelled"] is False
    assert not eb.is_cancelled(run.id)


@pytest.mark.asyncio
async def test_expand_run_creates_new_run_with_doubled_limits(monkeypatch, db_session) -> None:
    """POST /api/runs/{id}/expand must create a new run with 2× URL/item limits."""
    launched: list[tuple] = []

    async def fake_run_research(*args, **_kw) -> None:
        launched.append(args)

    monkeypatch.setattr(routes, "run_research", fake_run_research)

    original = Run(topic="EVs", freshness="pm", status="completed")
    db_session.add(original)
    await db_session.commit()
    await db_session.refresh(original)

    settings = Settings(max_urls_per_run=10, max_items_per_run=50)
    response = await routes.expand_run(original.id, db_session, settings)

    assert response.cached is False
    new_run = await db_session.get(Run, response.run_id)
    assert new_run is not None
    assert new_run.topic == "EVs"
    assert new_run.freshness is None  # expanded runs use "any time"
    await asyncio.sleep(0)
    assert len(launched) == 1
    _run_id, _topic, _freshness, expanded_settings, _skip = launched[0]
    assert expanded_settings.max_urls_per_run == 20
    assert expanded_settings.max_items_per_run == 100

    event_bus.deregister(response.run_id)


@pytest.mark.asyncio
async def test_stream_events_replays_stored_events_for_cancelled_run(db_session) -> None:
    """The SSE endpoint must also replay events for cancelled runs."""
    from app.models import RunEvent

    run = Run(topic="topic", freshness=None, status="cancelled")
    db_session.add(run)
    await db_session.flush()
    ev = RunEvent(run_id=run.id, seq=1, type="run_cancelled", message="Cancelled", detail={})
    db_session.add(ev)
    await db_session.commit()
    await db_session.refresh(run)

    response = await routes.stream_events(run.id, db_session)
    chunks = [c async for c in response.body_iterator]

    assert len(chunks) == 1
    import json
    payload = json.loads(chunks[0].removeprefix("data: ").removesuffix("\n\n"))
    assert payload["type"] == "run_cancelled"


@pytest.mark.asyncio
async def test_list_runs_returns_all_statuses(db_session) -> None:
    """GET /api/runs must return runs in all statuses, not just completed."""
    for st in ("running", "completed", "cancelled", "error"):
        db_session.add(Run(topic=f"topic-{st}", freshness=None, status=st))
    await db_session.commit()

    result = await routes.list_runs(topic=None, status=None, limit=40, db=db_session)
    statuses = {r["status"] for r in result}
    assert statuses >= {"running", "completed", "cancelled", "error"}
    assert all("status" in r for r in result)


@pytest.mark.asyncio
async def test_start_nemoclaw_creates_sub_run(monkeypatch, db_session) -> None:
    """POST /api/runs/{id}/nemoclaw must create a linked NemoClaw run and start it."""
    launched: list[tuple] = []

    async def fake_run_nemoclaw(*args, **_kw) -> None:
        launched.append(args)

    monkeypatch.setattr(routes, "run_research", lambda *_a, **_kw: None)
    import app.api.routes as _routes_mod
    import importlib
    import app.agents.nemoclaw_agent as nc_mod
    monkeypatch.setattr(nc_mod, "run_nemoclaw", fake_run_nemoclaw)

    parent = Run(topic="AI safety", freshness=None, status="running")
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    settings = Settings()
    response = await routes.start_nemoclaw(parent.id, db_session, settings)
    nc_run = await db_session.get(Run, response.run_id)
    assert nc_run is not None
    assert "[NemoClaw]" in nc_run.topic
    assert "AI safety" in nc_run.topic

    await asyncio.sleep(0)
    assert len(launched) == 1
    _, topic, parent_id, _ = launched[0]
    assert topic == "AI safety"
    assert parent_id == parent.id

    event_bus.deregister(response.run_id)


@pytest.mark.asyncio
async def test_stream_events_replays_stored_events_for_completed_run(db_session) -> None:
    """The SSE endpoint must replay stored RunEvent rows for completed runs
    so cached runs deliver their full event history to the frontend."""
    from app.models import RunEvent

    run = Run(topic="topic", freshness="pm", status="completed", report={})
    db_session.add(run)
    await db_session.flush()
    ev = RunEvent(run_id=run.id, seq=1, type="run_completed", message="Done", detail={"ok": True})
    db_session.add(ev)
    await db_session.commit()
    await db_session.refresh(run)

    response = await routes.stream_events(run.id, db_session)
    chunks = [c async for c in response.body_iterator]

    assert len(chunks) == 1
    import json
    payload = json.loads(chunks[0].removeprefix("data: ").removesuffix("\n\n"))
    assert payload["type"] == "run_completed"
    assert payload["detail"] == {"ok": True}
