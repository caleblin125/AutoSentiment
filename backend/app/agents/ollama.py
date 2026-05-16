"""Shared Ollama httpx client — used by nemoclaw.py (120B) and light_queue.py (30B).

Features:
- Streaming API with cancel_check for fast interruption
- Exponential backoff retry (3 attempts) with jitter
- Circuit breaker: after 5 consecutive failures, fails fast for 30s
- JSON recovery from malformed model output
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable

import httpx

logger = logging.getLogger(__name__)


class GenerationCancelled(Exception):
    """Raised when cancel_check() returns True during token streaming."""


# ── Circuit breaker ──────────────────────────────────────────────────────────

_CIRCUIT_STATE: dict[str, tuple[int, float]] = {}  # model -> (consecutive_failures, opened_at)

_CIRCUIT_THRESHOLD = 5
_CIRCUIT_COOLDOWN = 30.0  # seconds
_MAX_RETRIES = 3
_BASE_BACKOFF = 1.0  # seconds


def _circuit_breaker_check(model: str) -> None:
    """Raise RuntimeError if the circuit is open for this model."""
    state = _CIRCUIT_STATE.get(model)
    if state is None:
        return
    failures, opened_at = state
    if failures >= _CIRCUIT_THRESHOLD:
        if time.monotonic() - opened_at < _CIRCUIT_COOLDOWN:
            raise RuntimeError(
                f"Circuit breaker open for model '{model}' — "
                f"{failures} consecutive failures, retry in "
                f"{_CIRCUIT_COOLDOWN - (time.monotonic() - opened_at):.0f}s"
            )
        # Cooldown expired, reset.
        _CIRCUIT_STATE.pop(model, None)


def _circuit_breaker_record_success(model: str) -> None:
    _CIRCUIT_STATE.pop(model, None)


def _circuit_breaker_record_failure(model: str) -> None:
    prev = _CIRCUIT_STATE.get(model, (0, 0.0))
    _CIRCUIT_STATE[model] = (prev[0] + 1, time.monotonic())


# ── Retry wrapper ────────────────────────────────────────────────────────────


async def _with_retry(
    model: str,
    fn: Callable[[], dict | list],
    retriable: Callable[[Exception], bool],
) -> dict | list:
    """Execute fn with exponential backoff retry and circuit breaker check."""
    _circuit_breaker_check(model)

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            result = await fn()
            _circuit_breaker_record_success(model)
            return result
        except GenerationCancelled:
            raise  # never retry cancellations
        except Exception as exc:
            last_exc = exc
            if not retriable(exc) or attempt == _MAX_RETRIES:
                _circuit_breaker_record_failure(model)
                raise
            delay = _BASE_BACKOFF * (2 ** attempt) + (time.monotonic() % 0.5)
            logger.warning(
                "Ollama call failed (attempt %d/%d) for model '%s': %s. Retrying in %.1fs",
                attempt + 1, _MAX_RETRIES + 1, model, exc, delay,
            )
            await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]


def _is_retriable(exc: Exception) -> bool:
    """Returns True for transient failures worth retrying."""
    msg = str(exc).lower()
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500  # server errors
    if isinstance(exc, json.JSONDecodeError):
        return False  # bad prompt, not retriable
    if "connect" in msg or "timeout" in msg or "refused" in msg or "reset" in msg:
        return True
    return False


# ── Core generate functions ──────────────────────────────────────────────────


async def ollama_generate(
    prompt: str,
    *,
    system: str,
    model: str,
    base_url: str,
    cancel_check: Callable[[], bool] | None = None,
) -> dict | list:
    """Stream from Ollama /api/generate with format=json; return parsed response dict.

    Retries up to 3 times with exponential backoff on transient failures.
    Circuit breaker opens after 5 consecutive failures.
    """
    async def _call() -> dict:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{base_url.rstrip('/')}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "system": system,
                    "format": "json",
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                full_response = ""
                full_thinking = ""
                async for line in response.aiter_lines():
                    if cancel_check and cancel_check():
                        raise GenerationCancelled()
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    full_response += chunk.get("response", "")
                    full_thinking += chunk.get("thinking", "")
                    if chunk.get("done"):
                        break
        return _parse_model_json(_pick_text(full_response, full_thinking))

    return await _with_retry(model, _call, _is_retriable)


async def ollama_generate_streaming(
    prompt: str,
    *,
    system: str,
    model: str,
    base_url: str,
    cancel_check: Callable[[], bool] | None = None,
    on_token: Callable[[str], None] | None = None,
) -> dict:
    """Stream from Ollama, calling on_token for each response chunk.

    Retries up to 3 times with exponential backoff on transient failures.
    """
    async def _call() -> dict:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{base_url.rstrip('/')}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "system": system,
                    "format": "json",
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                full_response = ""
                full_thinking = ""
                async for line in response.aiter_lines():
                    if cancel_check and cancel_check():
                        raise GenerationCancelled()
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = chunk.get("response", "")
                    if token and on_token:
                        on_token(token)
                    full_response += token
                    full_thinking += chunk.get("thinking", "")
                    if chunk.get("done"):
                        break
        return _parse_model_json(_pick_text(full_response, full_thinking))

    return await _with_retry(model, _call, _is_retriable)


def _pick_text(response: str, thinking: str) -> str:
    """Prefer the response field; fall back to thinking for reasoning models."""
    if response.strip():
        return response.strip()
    return thinking.strip()


def _parse_model_json(text: str) -> dict | list:
    raw = text.strip()
    if not raw:
        raise ValueError("Empty response from model")
    candidates = [raw, *_json_candidates(raw)]
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict | list):
            return parsed
    raise ValueError(raw)


def _json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE):
        candidates.append(match.group(1).strip())
    candidates.extend(_balanced_json_candidates(text, "{", "}"))
    candidates.extend(_balanced_json_candidates(text, "[", "]"))
    return candidates


def _balanced_json_candidates(text: str, open_char: str, close_char: str) -> list[str]:
    candidates: list[str] = []
    start = text.find(open_char)
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            char = text[idx]
            if in_string:
                if escaped: escaped = False
                elif char == "\\": escaped = True
                elif char == '"': in_string = False
                continue
            if char == '"': in_string = True
            elif char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:idx + 1])
                    break
        start = text.find(open_char, start + 1)
    return candidates
