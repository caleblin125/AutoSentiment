import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import event_bus, routes
from app.core.config import Settings
from app.models import Base, EvidenceChunk, Run, RunEvent


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
        scheduled.append((_args, _kwargs))
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
    args, kwargs = scheduled[0]
    assert args[3].max_queries_per_run == 6
    assert args[3].max_urls_per_run == 30
    assert kwargs["research_depth"] == "standard"
    assert kwargs["use_case"] == "generic"

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
async def test_get_evidence_includes_related_report_context(db_session) -> None:
    run = Run(
        topic="topic",
        freshness="pm",
        status="completed",
        report={
            "timeline": {"important_dates": [{"date": "2026-03-05", "evidence_ids": ["chunk-1"]}]},
            "fact_check": {"claims": [{"claim": "A claim", "evidence_ids": ["chunk-1"]}]},
            "aspects": [{"name": "cost", "evidence_ids": ["chunk-1"]}],
        },
    )
    db_session.add(run)
    await db_session.flush()
    chunk = EvidenceChunk(
        id="chunk-1",
        run_id=run.id,
        url="https://example.com",
        source_type="news",
        snippet="snippet",
        label="neutral",
        summary="summary",
    )
    db_session.add(chunk)
    await db_session.commit()

    payload = await routes.get_evidence(run.id, chunk.id, db_session)

    assert payload["related"]["timeline_events"][0]["date"] == "2026-03-05"
    assert payload["related"]["claims"][0]["claim"] == "A claim"
    assert payload["related"]["aspects"][0]["name"] == "cost"


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
    with pytest.raises(ValueError):
        routes.RunRequest(topic="topic", research_depth="too-much")
    with pytest.raises(ValueError):
        routes.RunRequest(topic="topic", use_case="not-real")


@pytest.mark.asyncio
async def test_preview_search_plan_returns_quota_and_queries(db_session) -> None:
    payload = await routes.preview_search_plan(
        topic="Movie launch",
        freshness="pm",
        research_depth="quick",
        use_case="entertainment_product",
        db=db_session,
        settings=Settings(),
    )

    assert payload["estimated_brave_queries"] == 3
    assert payload["monthly_quota_remaining"] == 2000
    assert payload["queries"]
    assert payload["queries"][0]["purpose"]


@pytest.mark.asyncio
async def test_diagnostics_reports_configuration_without_secrets(db_session) -> None:
    payload = await routes.diagnostics(
        db=db_session,
        settings=Settings(**{"brave_api_key": "secret-value"}),
    )

    assert payload["status"] == "ok"
    assert payload["database"]["writable"] is True
    assert payload["brave"] == {"api_key_present": True}
    assert "secret-value" not in str(payload)
    assert payload["models"]["nemoclaw_model"]
    assert "run_counts" in payload


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
        report={"metadata": {"research_depth": "standard"}, "overall": {"total": 10}},
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
async def test_create_run_cache_is_depth_sensitive(monkeypatch, db_session) -> None:
    async def fake_run_research(*_a, **_kw) -> None:
        return None

    monkeypatch.setattr(routes, "run_research", fake_run_research)

    from datetime import UTC, datetime
    existing = Run(
        topic="EV trucks",
        freshness="pm",
        status="completed",
        created_at=datetime.now(UTC),
        report={"metadata": {"research_depth": "quick"}, "overall": {"total": 10}},
    )
    db_session.add(existing)
    await db_session.commit()

    response = await routes.create_run(
        routes.RunRequest(topic="EV trucks", freshness="pm", research_depth="deep"),
        db=db_session,
        settings=Settings(),
    )

    assert response.cached is False
    assert response.run_id != existing.id
    event_bus.deregister(response.run_id)


@pytest.mark.asyncio
async def test_create_run_reuses_similar_completed_evidence(monkeypatch, db_session) -> None:
    launched: list[tuple] = []

    async def fake_run_research(*args, **kwargs) -> None:
        launched.append((args, kwargs))

    monkeypatch.setattr(routes, "run_research", fake_run_research)

    existing = Run(
        topic="Tesla Model 3 reliability",
        freshness="pm",
        status="completed",
        report={"metadata": {"research_depth": "standard"}, "overall": {"total": 1}},
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)
    db_session.add(EvidenceChunk(
        run_id=existing.id,
        url="https://news.example/reliability",
        source_type="news",
        snippet="Reliability improved.",
        label="positive",
        summary="reliability improved",
    ))
    await db_session.commit()

    response = await routes.create_run(
        routes.RunRequest(topic="Tesla Model 3 reliability concerns", freshness="pm"),
        db=db_session,
        settings=Settings(),
    )

    assert response.cached is False
    assert response.reused_run_id == existing.id
    copied = (await db_session.execute(
        select(EvidenceChunk).where(EvidenceChunk.run_id == response.run_id)
    )).scalars().all()
    assert [chunk.url for chunk in copied] == ["https://news.example/reliability"]
    await asyncio.sleep(0)
    assert launched[0][0][4] == frozenset({"https://news.example/reliability"})
    event_bus.deregister(response.run_id)


@pytest.mark.asyncio
async def test_create_run_applies_model_overrides(monkeypatch, db_session) -> None:
    launched: list[tuple] = []

    async def fake_run_research(*args, **kwargs) -> None:
        launched.append((args, kwargs))

    monkeypatch.setattr(routes, "run_research", fake_run_research)

    response = await routes.create_run(
        routes.RunRequest(
            topic="model override",
            freshness="pm",
            nemoclaw_model="custom-nc",
            lightweight_model="custom-light",
            suggestion_model="custom-suggest",
        ),
        db=db_session,
        settings=Settings(),
    )

    await asyncio.sleep(0)
    settings = launched[0][0][3]
    assert settings.nemoclaw_model == "custom-nc"
    assert settings.lightweight_model == "custom-light"
    assert settings.suggestion_model == "custom-suggest"
    event_bus.deregister(response.run_id)


@pytest.mark.asyncio
async def test_create_run_finds_matching_depth_cache_behind_newer_depth(monkeypatch, db_session) -> None:
    async def fake_run_research(*_a, **_kw) -> None:
        return None

    monkeypatch.setattr(routes, "run_research", fake_run_research)

    from datetime import UTC, datetime, timedelta
    matching = Run(
        topic="EV trucks",
        freshness="pm",
        status="completed",
        created_at=datetime.now(UTC) - timedelta(minutes=5),
        report={"metadata": {"research_depth": "deep"}, "overall": {"total": 10}},
    )
    newer_other_depth = Run(
        topic="EV trucks",
        freshness="pm",
        status="completed",
        created_at=datetime.now(UTC),
        report={"metadata": {"research_depth": "quick"}, "overall": {"total": 10}},
    )
    db_session.add_all([matching, newer_other_depth])
    await db_session.commit()
    await db_session.refresh(matching)

    response = await routes.create_run(
        routes.RunRequest(topic="EV trucks", freshness="pm", research_depth="deep"),
        db=db_session,
        settings=Settings(),
    )

    assert response.cached is True
    assert response.run_id == matching.id


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
async def test_expand_run_creates_new_run_with_requested_depth(monkeypatch, db_session) -> None:
    """POST /api/runs/{id}/expand must use the requested depth and inherit freshness."""
    launched: list[tuple] = []

    async def fake_run_research(*args, **_kw) -> None:
        launched.append((args, _kw))

    monkeypatch.setattr(routes, "run_research", fake_run_research)

    original = Run(
        topic="EVs",
        freshness="pm",
        status="completed",
        report={"metadata": {"research_depth": "standard", "use_case": "entertainment_product"}},
    )
    db_session.add(original)
    await db_session.commit()
    await db_session.refresh(original)
    db_session.add_all([
        RunEvent(run_id=original.id, seq=1, type="run_started", message="Run started", detail={}),
        RunEvent(run_id=original.id, seq=2, type="search_queried", message="Search queried", detail={"query": "q"}),
        RunEvent(run_id=original.id, seq=3, type="run_completed", message="Run completed", detail={}),
    ])
    await db_session.commit()

    settings = Settings(max_urls_per_run=10, max_items_per_run=50)
    response = await routes.expand_run(
        original.id,
        routes.ExpandRunRequest(research_depth="deep"),
        db_session,
        settings,
    )

    assert response.cached is False
    new_run = await db_session.get(Run, response.run_id)
    assert new_run is not None
    assert new_run.topic == "EVs"
    assert new_run.freshness == "pm"
    await asyncio.sleep(0)
    assert len(launched) == 1
    args, kwargs = launched[0]
    _run_id, _topic, _freshness, expanded_settings, _skip = args
    assert _freshness == "pm"
    assert expanded_settings.max_queries_per_run == 10
    assert expanded_settings.max_urls_per_run == 60
    assert expanded_settings.max_items_per_run == 180
    assert kwargs["research_depth"] == "deep"
    assert kwargs["use_case"] == "entertainment_product"
    assert kwargs["depth_budget"]["query_count"] == 10
    copied_events = (await db_session.execute(
        select(RunEvent).where(RunEvent.run_id == response.run_id).order_by(RunEvent.seq)
    )).scalars().all()
    assert [event.type for event in copied_events] == ["search_queried"]

    event_bus.deregister(response.run_id)


@pytest.mark.asyncio
async def test_expand_run_defaults_to_next_depth(monkeypatch, db_session) -> None:
    launched: list[tuple] = []

    async def fake_run_research(*args, **_kw) -> None:
        launched.append((args, _kw))

    monkeypatch.setattr(routes, "run_research", fake_run_research)

    original = Run(
        topic="EVs",
        freshness="pw",
        status="completed",
        report={"metadata": {"research_depth": "quick"}},
    )
    db_session.add(original)
    await db_session.commit()
    await db_session.refresh(original)

    response = await routes.expand_run(original.id, None, db_session, Settings())

    await asyncio.sleep(0)
    args, kwargs = launched[0]
    assert kwargs["research_depth"] == "standard"
    assert args[2] == "pw"
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
    response = await routes.start_nemoclaw(parent.id, None, db_session, settings)
    nc_run = await db_session.get(Run, response.run_id)
    assert nc_run is not None
    assert "[NemoClaw]" in nc_run.topic
    assert "AI safety" in nc_run.topic

    await asyncio.sleep(0)
    assert len(launched) == 1
    _, topic, parent_id, _ = launched[0]
    assert topic == "AI safety"
    assert parent_id == parent.id


@pytest.mark.asyncio
async def test_start_nemoclaw_applies_model_override(monkeypatch, db_session) -> None:
    launched: list[tuple] = []

    async def fake_run_nemoclaw(*args, **_kw) -> None:
        launched.append(args)

    import app.agents.nemoclaw_agent as nc_mod
    monkeypatch.setattr(nc_mod, "run_nemoclaw", fake_run_nemoclaw)

    parent = Run(topic="AI safety", freshness=None, status="completed")
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    response = await routes.start_nemoclaw(
        parent.id,
        routes.NemoClawRequest(nemoclaw_model="custom-nemoclaw"),
        db_session,
        Settings(),
    )

    await asyncio.sleep(0)
    assert launched[0][3].nemoclaw_model == "custom-nemoclaw"
    event_bus.deregister(response.run_id)

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


# ── Saved searches ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_saved_searches_crud_create_list_delete(db_session) -> None:
    """Full CRUD cycle: create → list → delete → confirm gone."""
    body = routes.SavedSearchRequest(
        name="Weekly check",
        topic="Electric vehicles",
        freshness="pw",
        research_depth="quick",
        use_case="generic",
    )
    created = await routes.create_saved_search(body, db_session, _auth=None)

    assert created["name"] == "Weekly check"
    assert created["topic"] == "Electric vehicles"
    assert created["freshness"] == "pw"
    assert created["research_depth"] == "quick"
    assert created["use_case"] == "generic"
    assert "id" in created and created["id"]

    listed = await routes.list_saved_searches(db_session)
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]

    result = await routes.delete_saved_search(created["id"], db_session, _auth=None)
    assert result["deleted"] == created["id"]

    listed_after = await routes.list_saved_searches(db_session)
    assert listed_after == []


@pytest.mark.asyncio
async def test_saved_search_delete_404_for_unknown_id(db_session) -> None:
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await routes.delete_saved_search("no-such-id", db_session, _auth=None)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_saved_search_validation_rejects_blank_name(db_session) -> None:
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        routes.SavedSearchRequest(name="  ", topic="topic")


@pytest.mark.asyncio
async def test_saved_search_validation_rejects_invalid_freshness(db_session) -> None:
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        routes.SavedSearchRequest(name="test", topic="topic", freshness="bad")


@pytest.mark.asyncio
async def test_saved_searches_list_returns_newest_first(db_session) -> None:
    for name in ["first", "second", "third"]:
        body = routes.SavedSearchRequest(name=name, topic=name)
        await routes.create_saved_search(body, db_session, _auth=None)

    listed = await routes.list_saved_searches(db_session)
    assert [s["name"] for s in listed] == ["third", "second", "first"]
