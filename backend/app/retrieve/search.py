"""Retrieve stored evidence chunks for a run — used by the report builder and citation API."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvidenceChunk


async def get_chunks_for_run(run_id: str, db: AsyncSession) -> list[EvidenceChunk]:
    result = await db.execute(select(EvidenceChunk).where(EvidenceChunk.run_id == run_id))
    return list(result.scalars().all())


async def get_chunk(chunk_id: str, db: AsyncSession) -> EvidenceChunk | None:
    return await db.get(EvidenceChunk, chunk_id)
