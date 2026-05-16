import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Optional
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import event_bus
from app.agents.orchestrator import run_research
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import EvidenceChunk, Run, RunEvent, SavedSearch
from app.research_depth import (
    DEFAULT_DEPTH,
    depth_from_report,
    get_depth_budget,
    next_depth_name,
    normalize_depth_name,
)
from app.search_planner import build_search_plan, normalize_use_case

router = APIRouter()

VALID_FRESHNESS = {"pd", "pw", "pm", "py"}


# ── Auth dependency (disabled when AUTH_API_KEY is empty) ───────────────

async def require_auth(
    settings: Settings = Depends(get_settings),
    x_api_key: str = Header(default="", alias="X-API-Key"),
) -> None:
    if not settings.auth_api_key:
        return  # auth disabled — localhost mode
    if x_api_key != settings.auth_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class RunRequest(BaseModel):
    topic: str
    freshness: Optional[str] = "pm"  # pd | pw | pm | py | None
    research_depth: str = DEFAULT_DEPTH
    use_case: str = "generic"
    nemoclaw_model: Optional[str] = None
    lightweight_model: Optional[str] = None
    suggestion_model: Optional[str] = None

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("topic is required")
        if len(value) > 500:
            raise ValueError("topic must be 500 characters or fewer")
        # Strip prompt injection patterns: system overrides, delimiter attacks, role switching.
        blocked = (
            "<|system|>", "<|user|>", "<|assistant|>", "<|im_start|>", "<|im_end|>",
            "ignore previous", "ignore all previous", "disregard prior",
            "you are now", "act as", "pretend you are", "new instructions:",
            "[/INST]", "[INST]", "<<SYS>>", "<</SYS>>",
        )
        lower = value.lower()
        for pattern in blocked:
            if pattern in lower:
                raise ValueError("topic contains disallowed content")
        return value

    @field_validator("freshness")
    @classmethod
    def validate_freshness(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in VALID_FRESHNESS:
            raise ValueError("freshness must be one of: pd, pw, pm, py")
        return value

    @field_validator("research_depth")
    @classmethod
    def validate_research_depth(cls, value: str) -> str:
        return normalize_depth_name(value)

    @field_validator("use_case")
    @classmethod
    def validate_use_case(cls, value: str) -> str:
        return normalize_use_case(value)


class ExpandRunRequest(BaseModel):
    research_depth: Optional[str] = None
    freshness: Optional[str] = None
    use_case: Optional[str] = None
    nemoclaw_model: Optional[str] = None
    lightweight_model: Optional[str] = None

    @field_validator("research_depth")
    @classmethod
    def validate_research_depth(cls, value: Optional[str]) -> Optional[str]:
        return normalize_depth_name(value) if value is not None else None

    @field_validator("freshness")
    @classmethod
    def validate_freshness(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in VALID_FRESHNESS:
            raise ValueError("freshness must be one of: pd, pw, pm, py")
        return value

    @field_validator("use_case")
    @classmethod
    def validate_use_case(cls, value: Optional[str]) -> Optional[str]:
        return normalize_use_case(value) if value is not None else None


CACHE_TTL_HOURS = 2

class RunResponse(BaseModel):
    run_id: str
    cached: bool = False
    reused_run_id: Optional[str] = None


class NemoClawRequest(BaseModel):
    nemoclaw_model: Optional[str] = None


def _settings_with_model_overrides(settings: Settings, **models: str | None) -> Settings:
    updates = {key: value.strip() for key, value in models.items() if isinstance(value, str) and value.strip()}
    return settings.model_copy(update=updates) if updates else settings


def _topic_similarity(a: str, b: str) -> float:
    left = " ".join(a.casefold().split())
    right = " ".join(b.casefold().split())
    if not left or not right:
        return 0.0
    left_tokens = {token for token in left.split() if len(token) > 2}
    right_tokens = {token for token in right.split() if len(token) > 2}
    token_score = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    sequence_score = SequenceMatcher(None, left, right).ratio()
    return max(token_score, sequence_score)


async def _find_similar_completed_run(
    db: AsyncSession,
    topic: str,
    freshness: str | None,
    research_depth: str,
) -> Run | None:
    result = await db.execute(
        select(Run)
        .where(Run.status == "completed")
        .where(Run.freshness == freshness)
        .order_by(desc(Run.created_at))
        .limit(30)
    )
    for run in result.scalars().all():
        if depth_from_report(run.report) != research_depth:
            continue
        if _topic_similarity(topic, run.topic) >= 0.72:
            return run
    return None


async def _copy_seed_context(
    db: AsyncSession,
    source_run_id: str,
    target_run_id: str,
    *,
    copy_events: bool,
) -> set[str]:
    """Copy prior evidence, and optionally non-terminal timeline events, into a new run."""
    skip_urls: set[str] = set()
    if copy_events:
        events = (
            await db.execute(
                select(RunEvent).where(RunEvent.run_id == source_run_id).order_by(RunEvent.seq)
            )
        ).scalars().all()
        seq = 0
        omitted = {"run_started", "run_completed", "run_cancelled", "run_error"}
        for ev in events:
            if ev.type in omitted:
                continue
            seq += 1
            db.add(RunEvent(
                run_id=target_run_id,
                seq=seq,
                type=ev.type,
                message=ev.message,
                detail=ev.detail,
            ))

    chunks = (
        await db.execute(select(EvidenceChunk).where(EvidenceChunk.run_id == source_run_id))
    ).scalars().all()
    for chunk in chunks:
        skip_urls.add(chunk.url)
        db.add(EvidenceChunk(
            run_id=target_run_id,
            url=chunk.url,
            source_type=chunk.source_type,
            snippet=chunk.snippet,
            label=chunk.label,
            summary=chunk.summary,
        ))
    return skip_urls


def _run_to_dict(run: Run) -> dict:
    research_depth = depth_from_report(run.report)
    return {
        "id": run.id,
        "topic": run.topic,
        "freshness": run.freshness,
        "research_depth": research_depth,
        "status": run.status,
        "created_at": run.created_at.isoformat(),
        "report": run.report,
    }


def _evidence_to_dict(chunk: EvidenceChunk, report: dict | None = None) -> dict:
    payload = {
        "id": chunk.id,
        "run_id": chunk.run_id,
        "url": chunk.url,
        "source_type": chunk.source_type,
        "snippet": chunk.snippet,
        "label": chunk.label,
        "summary": chunk.summary,
        "retrieved_at": chunk.retrieved_at.isoformat(),
    }
    if report:
        payload["related"] = _related_report_context(chunk.id, report)
    return payload


def _related_report_context(chunk_id: str, report: dict) -> dict:
    timeline = report.get("timeline") or {}
    fact_check = report.get("fact_check") or {}
    aspects = report.get("aspects") or []
    return {
        "timeline_events": [
            event for event in timeline.get("important_dates", [])
            if chunk_id in event.get("evidence_ids", [])
        ],
        "claims": [
            claim for claim in fact_check.get("claims", [])
            if chunk_id in claim.get("evidence_ids", [])
        ],
        "aspects": [
            aspect for aspect in aspects
            if chunk_id in aspect.get("evidence_ids", [])
        ],
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/diagnostics")
async def diagnostics(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return local readiness diagnostics without exposing secrets."""
    from sqlalchemy import text

    db_writable = True
    db_error = None
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - defensive
        db_writable = False
        db_error = str(exc)

    run_counts = {}
    from sqlalchemy import func as sqlfunc
    for st in ("pending", "running", "completed", "cancelled", "error"):
        result = await db.execute(select(sqlfunc.count()).where(Run.status == st))
        run_counts[st] = result.scalar_one()

    return {
        "status": "ok" if db_writable else "degraded",
        "database": {"writable": db_writable, "error": db_error},
        "brave": {"api_key_present": bool(settings.brave_api_key)},
        "models": {
            "nemoclaw_model": settings.nemoclaw_model,
            "lightweight_model": settings.lightweight_model,
            "suggestion_model": settings.suggestion_model,
            "ollama_base_url": settings.ollama_base_url,
        },
        "limits": {
            "max_queries_per_run": settings.max_queries_per_run,
            "max_urls_per_run": settings.max_urls_per_run,
            "max_items_per_run": settings.max_items_per_run,
            "light_queue_max_parallel": settings.light_queue_max_parallel,
        },
        "run_counts": run_counts,
        "active_sse_queues": len(event_bus._queues),
    }


@router.get("/runs")
async def list_runs(
    topic: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=40, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return recent runs in all statuses for the history panel.

    Accepts optional `topic` (substring match) and `status` filters.
    """
    stmt = select(Run).order_by(desc(Run.created_at)).limit(limit)
    if topic:
        stmt = stmt.where(Run.topic.ilike(f"%{topic}%"))
    if status:
        stmt = stmt.where(Run.status == status)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [
        {
            "id": run.id,
            "topic": run.topic,
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "overall": run.report.get("overall") if run.report else None,
            "duration_ms": run.report.get("timings", {}).get("total_ms") if run.report else None,
        }
        for run in runs
    ]


@router.get("/suggest")
async def suggest_topics(
    q: str = Query(min_length=1, max_length=200),
    model: Optional[str] = Query(default=None, max_length=120),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Use the small model to generate research angle suggestions for a query."""
    from app.agents.nemoclaw import suggest_angles
    effective_settings = settings.model_copy(update={"suggestion_model": model}) if model else settings
    suggestions = await suggest_angles(q, settings=effective_settings)
    return {"suggestions": suggestions}


@router.get("/search-plan")
async def preview_search_plan(
    topic: str = Query(min_length=1, max_length=200),
    freshness: Optional[str] = Query(default="pm"),
    research_depth: str = Query(default=DEFAULT_DEPTH),
    use_case: str = Query(default="generic"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Preview planned search cost and source mix before spending Brave quota."""
    if freshness is not None and freshness not in VALID_FRESHNESS:
        raise HTTPException(status_code=422, detail="freshness must be one of: pd, pw, pm, py")
    try:
        plan = await build_search_plan(
            topic.strip(),
            freshness=freshness,
            research_depth=research_depth,
            use_case=use_case,
            settings=settings,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return plan.to_dict()


@router.delete("/runs")
async def clear_history(db: AsyncSession = Depends(get_db)) -> dict:
    """Delete all non-running runs (completed, cancelled, error) from the history."""
    from sqlalchemy import delete as sql_delete
    # Delete events and evidence for completed/cancelled/error runs first.
    terminal_runs_result = await db.execute(
        select(Run.id).where(Run.status.in_(["completed", "cancelled", "error"]))
    )
    terminal_ids = [r for (r,) in terminal_runs_result.all()]
    if terminal_ids:
        await db.execute(
            sql_delete(RunEvent).where(RunEvent.run_id.in_(terminal_ids))
        )
        await db.execute(
            sql_delete(EvidenceChunk).where(EvidenceChunk.run_id.in_(terminal_ids))
        )
        await db.execute(
            sql_delete(Run).where(Run.id.in_(terminal_ids))
        )
    await db.commit()
    return {"deleted": len(terminal_ids)}


@router.post("/runs", response_model=RunResponse)
async def create_run(
    body: RunRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _auth: None = Depends(require_auth),
) -> RunResponse:
    depth_budget = get_depth_budget(body.research_depth, settings)

    # Case-insensitive cache check for the same topic + freshness + depth (TTL = CACHE_TTL_HOURS).
    # Depth is stored in report metadata to avoid a schema migration on existing local DBs.
    cutoff = datetime.now(UTC) - timedelta(hours=CACHE_TTL_HOURS)
    cached_stmt = (
        select(Run)
        .where(Run.topic.ilike(body.topic))  # case-insensitive match
        .where(Run.freshness == body.freshness)
        .where(Run.status == "completed")
        .where(Run.created_at >= cutoff)
        .order_by(desc(Run.created_at))
        .limit(10)
    )
    cached_result = await db.execute(cached_stmt)
    cached_run = next(
        (
            run
            for run in cached_result.scalars().all()
            if depth_from_report(run.report) == body.research_depth
        ),
        None,
    )
    if cached_run is not None:
        return RunResponse(run_id=cached_run.id, cached=True)

    similar_run = await _find_similar_completed_run(db, body.topic, body.freshness, body.research_depth)
    run = Run(topic=body.topic, freshness=body.freshness, status="pending")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    skip_urls: set[str] = set()
    if similar_run is not None:
        skip_urls = await _copy_seed_context(db, similar_run.id, run.id, copy_events=False)
        await db.commit()

    effective_settings = _settings_with_model_overrides(
        depth_budget.apply_to_settings(settings),
        nemoclaw_model=body.nemoclaw_model,
        lightweight_model=body.lightweight_model,
        suggestion_model=body.suggestion_model,
    )
    event_bus.register(run.id)
    asyncio.create_task(
        run_research(
            run.id,
            run.topic,
            run.freshness,
            effective_settings,
            frozenset(skip_urls),
            research_depth=depth_budget.name,
            depth_budget=depth_budget.to_metadata(),
            use_case=body.use_case,
        )
    )

    return RunResponse(run_id=run.id, reused_run_id=similar_run.id if similar_run else None)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_dict(run)


@router.get("/runs/{run_id}/events")
async def stream_events(run_id: str, db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    def _ev_to_json(ev: RunEvent) -> str:
        return json.dumps({
            "seq": ev.seq, "type": ev.type,
            "message": ev.message, "detail": ev.detail or {},
        })

    # Completed/errored/cancelled runs: full replay from DB.
    if run.status in ("completed", "error", "cancelled"):
        ev_result = await db.execute(
            select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
        )
        stored = ev_result.scalars().all()

        async def replay():
            for ev in stored:
                yield f"data: {_ev_to_json(ev)}\n\n"

        return StreamingResponse(replay(), media_type="text/event-stream")

    # Running/pending: replay any pre-seeded stored events (e.g. from expand)
    # then switch to the live queue so no events are missed.
    ev_result = await db.execute(
        select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
    )
    stored_events = ev_result.scalars().all()

    queue = event_bus.get(run_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Event stream not found")

    async def event_generator():
        try:
            for ev in stored_events:
                yield f"data: {_ev_to_json(ev)}\n\n"
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            event_bus.deregister(run_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db),
                     _auth: None = Depends(require_auth)) -> dict:
    """Signal the orchestrator to stop at its next stage boundary."""
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in ("pending", "running"):
        return {"cancelled": False, "status": run.status}
    event_bus.request_cancel(run_id)
    return {"cancelled": True, "run_id": run_id}


@router.post("/runs/{run_id}/expand")
async def expand_run(
    run_id: str,
    body: ExpandRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _auth: None = Depends(require_auth),
) -> RunResponse:
    """Create an expanded run that builds on top of existing evidence.

    - Copies all EvidenceChunks from the original run so synthesis begins with
      everything already found rather than starting from scratch.
    - Passes the original URLs as skip_urls so the pipeline fetches only NEW sources.
    - Uses the requested deeper budget, or the next preset above the original.
    - Inherits freshness by default so expansion is broader without silently
      changing the time window.
    """
    body = body or ExpandRunRequest()
    original = await db.get(Run, run_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Run not found")

    original_depth = depth_from_report(original.report)
    requested_depth = body.research_depth or next_depth_name(original_depth)
    depth_budget = get_depth_budget(requested_depth, settings)
    expanded_settings = _settings_with_model_overrides(
        depth_budget.apply_to_settings(settings),
        nemoclaw_model=body.nemoclaw_model,
        lightweight_model=body.lightweight_model,
    )
    expanded_freshness = body.freshness if body.freshness is not None else original.freshness
    original_metadata = original.report.get("metadata", {}) if original.report else {}
    original_use_case = (
        original_metadata.get("use_case")
        if isinstance(original_metadata, dict)
        else None
    )
    expanded_use_case = body.use_case or (original_use_case if isinstance(original_use_case, str) else "generic")

    run = Run(topic=original.topic, freshness=expanded_freshness, status="pending")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Copy non-terminal events and evidence so the expanded timeline continues
    # without duplicate "run started" or stale "done" rows.
    skip_urls = await _copy_seed_context(db, run_id, run.id, copy_events=True)
    await db.commit()

    event_bus.register(run.id)
    asyncio.create_task(
        run_research(
            run.id,
            run.topic,
            expanded_freshness,
            expanded_settings,
            frozenset(skip_urls),
            research_depth=depth_budget.name,
            depth_budget=depth_budget.to_metadata(),
            use_case=expanded_use_case,
        )
    )

    return RunResponse(run_id=run.id)


@router.post("/runs/{run_id}/nemoclaw")
async def start_nemoclaw(
    run_id: str,
    body: NemoClawRequest | None = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _auth: None = Depends(require_auth),
) -> RunResponse:
    """Launch NemoClaw as an autonomous research agent alongside the main run.

    NemoClaw generates its own unique analytical queries, fetches targeted URLs,
    and synthesises expert-level insights independent of the standard pipeline.
    """
    parent = await db.get(Run, run_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent run not found")

    nc_run = Run(
        topic=f"[NemoClaw] {parent.topic}",
        freshness=None,
        status="pending",
    )
    db.add(nc_run)
    await db.commit()
    await db.refresh(nc_run)

    event_bus.register(nc_run.id)
    from app.agents.nemoclaw_agent import run_nemoclaw
    body = body or NemoClawRequest()
    effective_settings = _settings_with_model_overrides(settings, nemoclaw_model=body.nemoclaw_model)
    asyncio.create_task(run_nemoclaw(nc_run.id, parent.topic, parent.id, effective_settings))

    return RunResponse(run_id=nc_run.id)


@router.get("/dev/stats")
async def dev_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Lightweight stats endpoint for the dev-mode overlay."""
    from sqlalchemy import func as sqlfunc
    run_counts = {}
    for st in ("pending", "running", "completed", "cancelled", "error"):
        result = await db.execute(select(sqlfunc.count()).where(Run.status == st))
        run_counts[st] = result.scalar_one()
    active_queues = len(event_bus._queues)
    return {
        "run_counts": run_counts,
        "active_sse_queues": active_queues,
    }


@router.get("/runs/{run_id}/evidence/{chunk_id}")
async def get_evidence(
    run_id: str, chunk_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    chunk = await db.get(EvidenceChunk, chunk_id)
    if chunk is None or chunk.run_id != run_id:
        raise HTTPException(status_code=404, detail="Evidence chunk not found")
    run = await db.get(Run, run_id)
    return _evidence_to_dict(chunk, run.report if run else None)


# ── Saved searches ────────────────────────────────────────────────────────────

class SavedSearchRequest(BaseModel):
    name: str
    topic: str
    freshness: Optional[str] = None
    research_depth: str = "standard"
    use_case: str = "generic"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v[:80]

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("topic must not be blank")
        return v

    @field_validator("freshness")
    @classmethod
    def validate_freshness(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v not in VALID_FRESHNESS:
            raise ValueError(f"freshness must be one of {VALID_FRESHNESS}")
        return v

    @field_validator("research_depth")
    @classmethod
    def validate_research_depth(cls, v: str) -> str:
        return normalize_depth_name(v)

    @field_validator("use_case")
    @classmethod
    def validate_use_case(cls, v: str) -> str:
        return normalize_use_case(v)


def _saved_search_to_dict(ss: SavedSearch) -> dict:
    return {
        "id": ss.id,
        "name": ss.name,
        "topic": ss.topic,
        "freshness": ss.freshness,
        "research_depth": ss.research_depth,
        "use_case": ss.use_case,
        "created_at": ss.created_at.isoformat(),
    }


@router.get("/saved-searches")
async def list_saved_searches(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.execute(select(SavedSearch).order_by(desc(SavedSearch.created_at)))).scalars().all()
    return [_saved_search_to_dict(r) for r in rows]


@router.post("/saved-searches")
async def create_saved_search(
    body: SavedSearchRequest,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_auth),
) -> dict:
    ss = SavedSearch(
        name=body.name,
        topic=body.topic,
        freshness=body.freshness,
        research_depth=body.research_depth,
        use_case=body.use_case,
    )
    db.add(ss)
    await db.commit()
    await db.refresh(ss)
    return _saved_search_to_dict(ss)


@router.delete("/saved-searches/{search_id}")
async def delete_saved_search(
    search_id: str,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_auth),
) -> dict:
    ss = await db.get(SavedSearch, search_id)
    if ss is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    await db.delete(ss)
    await db.commit()
    return {"deleted": search_id}
