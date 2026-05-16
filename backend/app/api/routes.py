"""HTTP and SSE routes — extend per api/IMPLEMENTATION.md."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

# TODO: POST /runs, GET /runs/{id}, GET /runs/{id}/events (SSE)
