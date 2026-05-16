"""Queued, concurrency-capped execution for lightweight models (search-tier LLM work).

Jobs are **not** meant for heavy reasoning — use Nemoclaw for planning and for
final synthesis when quality requires it. This tier stays fast, cheap, and parallel
up to `light_queue_max_parallel`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

from app.agents.types import LightJobKind

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


class LightweightModelQueue:
    """In-process queue: lightweight model calls share a bounded worker pool.

    Hackathon: semaphore-backed dispatch in one process. Swap for Redis/Celery
    if you need cross-machine workers later.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sem = asyncio.Semaphore(max(1, settings.light_queue_max_parallel))

    async def run(self, kind: LightJobKind, payload: dict[str, Any]) -> dict[str, Any]:
        """Enqueue logic: wait for a worker slot, then run the lightweight model."""
        async with self._sem:
            return await self._invoke(kind, payload)

    async def _invoke(self, kind: LightJobKind, payload: dict[str, Any]) -> dict[str, Any]:
        """Route to provider using `settings.lightweight_model`. Implement in this module."""
        logger.debug("light_queue job kind=%s model=%s", kind, self._settings.lightweight_model)
        # TODO: HTTP/SDK call to lightweight model with short prompts (see tools/IMPLEMENTATION.md)
        del payload
        return {
            "kind": str(kind),
            "model": self._settings.lightweight_model,
            "status": "not_implemented",
        }
