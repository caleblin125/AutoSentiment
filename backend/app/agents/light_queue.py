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

# Snippet length sent to the model — long inputs degrade JSON compliance.
_MAX_SNIPPET_CHARS = 900
# Retries on transient failures (connection errors, empty responses).
_MAX_RETRIES = 2


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
        """POST to Ollama /api/generate with the 30B model. Return label + 3-5 word summary.

        Retries up to _MAX_RETRIES times on transient failures with a short backoff.
        The snippet is truncated to _MAX_SNIPPET_CHARS to keep JSON compliance high.
        """
        truncated = snippet[:_MAX_SNIPPET_CHARS]
        system = (
            "You are a JSON-only sentiment classifier. "
            "Output must be valid JSON. No explanations, no markdown."
        )
        prompt = (
            "Classify the sentiment of the following text.\n"
            "Return exactly: {\"label\": \"positive\" | \"neutral\" | \"negative\", "
            "\"summary\": \"<3-5 words describing the author's opinion>\"}\n\n"
            f"Text:\n{truncated}"
        )

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
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
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    logger.warning("Sentiment call failed (attempt %d), retrying: %s", attempt + 1, exc)
                    continue

        logger.exception("Sentiment model call failed after %d attempts", _MAX_RETRIES + 1, exc_info=last_exc)
        return SentimentResult(label=SentimentLabel.NEUTRAL, summary=_SUMMARY_BY_LABEL[SentimentLabel.NEUTRAL])


def _coerce_label(value: object) -> SentimentLabel:
    normalized = str(value or "").strip().lower()
    if normalized in {"pos", "positive", "favorable", "favourable", "supportive"}:
        return SentimentLabel.POSITIVE
    if normalized in {"neg", "negative", "unfavorable", "unfavourable", "critical"}:
        return SentimentLabel.NEGATIVE
    return SentimentLabel.NEUTRAL
