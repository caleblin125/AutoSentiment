import asyncio
import json
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
from app.models import EvidenceChunk, Run

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


class RunResponse(BaseModel):
    run_id: str


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
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return recent completed runs, optionally filtered by exact topic match.

    Used by the frontend to build the historical sentiment chart.
    """
    stmt = (
        select(Run)
        .where(Run.status == "completed")
        .order_by(desc(Run.created_at))
        .limit(limit)
    )
    if topic:
        stmt = stmt.where(Run.topic == topic)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [
        {
            "id": run.id,
            "topic": run.topic,
            "created_at": run.created_at.isoformat(),
            "overall": run.report.get("overall") if run.report else None,
        }
        for run in runs
    ]


@router.post("/runs", response_model=RunResponse)
async def create_run(
    body: RunRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RunResponse:
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


@router.get("/runs/{run_id}/evidence/{chunk_id}")
async def get_evidence(
    run_id: str, chunk_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    chunk = await db.get(EvidenceChunk, chunk_id)
    if chunk is None or chunk.run_id != run_id:
        raise HTTPException(status_code=404, detail="Evidence chunk not found")
    return _evidence_to_dict(chunk)
