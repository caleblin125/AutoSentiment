"""30B model (nemotron-3-nano via Ollama) — per-item sentiment, queued and concurrency-capped."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.agents.ollama import ollama_generate
from app.agents.types import SentimentLabel, SentimentResult

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


class SentimentQueue:
    """Bounded-parallel queue for 30B sentiment calls.

    Each call sends one snippet to the model and returns a SentimentResult.
    Concurrency is capped at settings.light_queue_max_parallel.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sem = asyncio.Semaphore(max(1, settings.light_queue_max_parallel))

    async def analyze(self, snippet: str) -> SentimentResult:
        async with self._sem:
            return await self._call_model(snippet)

    async def _call_model(self, snippet: str) -> SentimentResult:
        """POST to Ollama /api/generate with the 30B model. Return label + 3-5 word summary."""
        system = "You are a sentiment classifier. Respond with JSON only. No explanation."
        prompt = (
            "Classify the sentiment of the following text.\n"
            "Return exactly: {\"label\": \"positive\" | \"neutral\" | \"negative\", "
            "\"summary\": \"<3-5 words describing the author's opinion>\"}\n\n"
            f"Text:\n{snippet}"
        )

        try:
            payload = await ollama_generate(
                prompt,
                system=system,
                model=self._settings.lightweight_model,
                base_url=self._settings.ollama_base_url,
            )
            return SentimentResult(
                label=SentimentLabel(str(payload["label"])),
                summary=str(payload["summary"]),
            )
        except Exception:
            logger.exception("Sentiment model call failed")
            return SentimentResult(label=SentimentLabel.NEUTRAL, summary="parse error")
