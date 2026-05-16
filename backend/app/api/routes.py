import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import event_bus
from app.agents.orchestrator import run_research
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import EvidenceChunk, Run, RunEvent

router = APIRouter()

VALID_FRESHNESS = {"pd", "pw", "pm", "py"}


class RunRequest(BaseModel):
    topic: str
    freshness: Optional[str] = "pm"  # pd | pw | pm | py | None

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("topic is required")
        return value

    @field_validator("freshness")
    @classmethod
    def validate_freshness(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in VALID_FRESHNESS:
            raise ValueError("freshness must be one of: pd, pw, pm, py")
        return value


CACHE_TTL_HOURS = 2

class RunResponse(BaseModel):
    run_id: str
    cached: bool = False


def _run_to_dict(run: Run) -> dict:
    return {
        "id": run.id,
        "topic": run.topic,
        "freshness": run.freshness,
        "status": run.status,
        "created_at": run.created_at.isoformat(),
        "report": run.report,
    }


def _evidence_to_dict(chunk: EvidenceChunk) -> dict:
    return {
        "id": chunk.id,
        "run_id": chunk.run_id,
        "url": chunk.url,
        "source_type": chunk.source_type,
        "snippet": chunk.snippet,
        "label": chunk.label,
        "summary": chunk.summary,
        "retrieved_at": chunk.retrieved_at.isoformat(),
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
        }
        for run in runs
    ]


@router.get("/suggest")
async def suggest_topics(
    q: str = Query(min_length=1, max_length=200),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Use the small model to generate research angle suggestions for a query."""
    from app.agents.nemoclaw import suggest_angles
    suggestions = await suggest_angles(q, settings=settings)
    return {"suggestions": suggestions}


@router.post("/runs", response_model=RunResponse)
async def create_run(
    body: RunRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RunResponse:
    # Return a recent completed run for the same topic+freshness instead of
    # running a full pipeline again (cache TTL = CACHE_TTL_HOURS).
    cutoff = datetime.now(UTC) - timedelta(hours=CACHE_TTL_HOURS)
    cached_stmt = (
        select(Run)
        .where(Run.topic == body.topic)
        .where(Run.freshness == body.freshness)
        .where(Run.status == "completed")
        .where(Run.created_at >= cutoff)
        .order_by(desc(Run.created_at))
        .limit(1)
    )
    cached_result = await db.execute(cached_stmt)
    cached_run = cached_result.scalar_one_or_none()
    if cached_run is not None:
        return RunResponse(run_id=cached_run.id, cached=True)

    run = Run(topic=body.topic, freshness=body.freshness, status="pending")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    event_bus.register(run.id)
    asyncio.create_task(run_research(run.id, run.topic, run.freshness, settings))

    return RunResponse(run_id=run.id)


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

    # Completed/errored runs replay stored events from the DB so cached runs
    # can be fully replayed by the frontend without needing a live queue.
    if run.status in ("completed", "error", "cancelled"):
        ev_result = await db.execute(
            select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
        )
        stored = ev_result.scalars().all()

        async def replay():
            for ev in stored:
                yield f"data: {json.dumps({'seq': ev.seq, 'type': ev.type, 'message': ev.message, 'detail': ev.detail or {}})}\n\n"

        return StreamingResponse(replay(), media_type="text/event-stream")

    queue = event_bus.get(run_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Event stream not found")

    async def event_generator():
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            event_bus.deregister(run_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)) -> dict:
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
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RunResponse:
    """Create a wider follow-up run for the same topic.

    The expanded run uses double the URL/item limits and drops the freshness
    restriction (any time) so it casts a broader net than the original.
    """
    original = await db.get(Run, run_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Run not found")

    expanded_settings = settings.model_copy(update={
        "max_urls_per_run": settings.max_urls_per_run * 2,
        "max_items_per_run": settings.max_items_per_run * 2,
    })
    run = Run(topic=original.topic, freshness=None, status="pending")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    event_bus.register(run.id)
    asyncio.create_task(run_research(run.id, run.topic, None, expanded_settings))

    return RunResponse(run_id=run.id)


@router.post("/runs/{run_id}/nemoclaw")
async def start_nemoclaw(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
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
    asyncio.create_task(run_nemoclaw(nc_run.id, parent.topic, parent.id, settings))

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
    return _evidence_to_dict(chunk)
