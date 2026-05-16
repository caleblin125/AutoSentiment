"""30B model (nemotron-3-nano via Ollama) — per-item sentiment, queued and concurrency-capped."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from app.agents.ollama import GenerationCancelled, ollama_generate
from app.agents.types import SentimentLabel, SentimentResult

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_SUMMARY_BY_LABEL = {
    SentimentLabel.POSITIVE: "positive signal",
    SentimentLabel.NEUTRAL: "neutral signal",
    SentimentLabel.NEGATIVE: "negative signal",
}


class SentimentQueue:
    """Bounded-parallel queue for 30B sentiment calls.

    Each call sends one snippet to the model and returns a SentimentResult.
    Concurrency is capped at settings.light_queue_max_parallel.
    cancel_check is evaluated between streaming tokens for fast interruption.
    """

    def __init__(self, settings: Settings, cancel_check: Callable[[], bool] | None = None) -> None:
        self._settings = settings
        self._sem = asyncio.Semaphore(max(1, settings.light_queue_max_parallel))
        self._cancel_check = cancel_check

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
                cancel_check=self._cancel_check,
            )
            label = _coerce_label(payload.get("label"))
            summary = str(payload.get("summary") or _SUMMARY_BY_LABEL[label]).strip()
            return SentimentResult(
                label=label,
                summary=summary[:160] or _SUMMARY_BY_LABEL[label],
            )
        except GenerationCancelled:
            raise
        except Exception:
            logger.exception("Sentiment model call failed")
            return SentimentResult(label=SentimentLabel.NEUTRAL, summary="parse error")


def _coerce_label(value: object) -> SentimentLabel:
    normalized = str(value or "").strip().lower()
    if normalized in {"pos", "positive", "favorable", "favourable", "supportive"}:
        return SentimentLabel.POSITIVE
    if normalized in {"neg", "negative", "unfavorable", "unfavourable", "critical"}:
        return SentimentLabel.NEGATIVE
    return SentimentLabel.NEUTRAL
