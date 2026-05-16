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
# Batch size for multi-snippet sentiment calls.
_BATCH_SIZE = 5


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

    async def analyze_batch(self, snippets: list[str]) -> list[SentimentResult]:
        """Classify multiple snippets in a single model call.

        Sends up to _BATCH_SIZE snippets per prompt, asking the model to return
        a JSON array of results. Dramatically reduces GPU round-trips for runs
        with many evidence items.
        """
        if not snippets:
            return []
        results: list[SentimentResult] = []
        for i in range(0, len(snippets), _BATCH_SIZE):
            batch = snippets[i:i + _BATCH_SIZE]
            async with self._sem:
                batch_results = await self._call_model_batch(batch)
            results.extend(batch_results)
        return results

    async def _call_model_batch(self, snippets: list[str]) -> list[SentimentResult]:
        truncated = [s[:_MAX_SNIPPET_CHARS] for s in snippets]
        system = (
            "You are a JSON-only sentiment classifier. "
            "Output must be a JSON object. No explanations, no markdown."
        )
        items = "\n".join(
            f"[{idx}] {text}" for idx, text in enumerate(truncated)
        )
        prompt = (
            "Classify the sentiment of each of the following texts.\n"
            "Return exactly one JSON object with a results array, one object per text, in order:\n"
            '{"results": [{"label": "positive"|"neutral"|"negative", '
            '"summary": "<3-5 words>", '
            '"confidence": <0.0-1.0>}]}\n\n'
            f"{items}"
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
                return self._normalize_batch_payload(payload, len(snippets))
            except GenerationCancelled:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue

        logger.exception("Batch sentiment call failed after %d attempts", _MAX_RETRIES + 1, exc_info=last_exc)
        return [
            SentimentResult(label=SentimentLabel.NEUTRAL, summary=_SUMMARY_BY_LABEL[SentimentLabel.NEUTRAL])
            for _ in snippets
        ]

    def _normalize_batch_payload(self, payload: object, expected_count: int) -> list[SentimentResult]:
        """Return exactly one result per requested snippet.

        Local models occasionally omit trailing batch items or wrap the array in
        different keys. Padding missing rows here prevents user-visible
        "batch miss" artifacts while still preserving every analyzable result.
        """
        items_raw: object
        if isinstance(payload, list):
            items_raw = payload
        elif isinstance(payload, dict):
            items_raw = (
                payload.get("results")
                or payload.get("items")
                or payload.get("sentiments")
                or payload.get("classifications")
                or []
            )
            if isinstance(items_raw, dict):
                items_raw = [
                    items_raw[key]
                    for key in sorted(items_raw, key=lambda value: int(value) if str(value).isdigit() else str(value))
                ]
        else:
            items_raw = []

        if not isinstance(items_raw, list):
            raise ValueError(f"Expected batch results list, got {type(items_raw)}")

        results = [
            self._parse_batch_item(item, idx)
            for idx, item in enumerate(items_raw[:expected_count])
        ]
        while len(results) < expected_count:
            results.append(SentimentResult(label=SentimentLabel.NEUTRAL, summary=_SUMMARY_BY_LABEL[SentimentLabel.NEUTRAL]))
        return results

    def _parse_batch_item(self, item, idx: int) -> SentimentResult:
        if not isinstance(item, dict):
            return SentimentResult(label=SentimentLabel.NEUTRAL, summary=_SUMMARY_BY_LABEL[SentimentLabel.NEUTRAL])
        label = _coerce_label(item.get("label"))
        summary = str(item.get("summary") or _SUMMARY_BY_LABEL[label]).strip()
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.8))))
        except (TypeError, ValueError):
            confidence = 0.8
        return SentimentResult(label=label, summary=summary[:160], confidence=confidence)

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
            "\"summary\": \"<3-5 words describing the author's opinion>\", "
            "\"confidence\": <0.0-1.0 float, how certain you are of the label>}\n\n"
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
                raw_conf = payload.get("confidence")
                try:
                    confidence = max(0.0, min(1.0, float(raw_conf)))  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    confidence = 0.8  # sensible default when model omits the field
                return SentimentResult(
                    label=label,
                    summary=summary[:160] or _SUMMARY_BY_LABEL[label],
                    confidence=confidence,
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
