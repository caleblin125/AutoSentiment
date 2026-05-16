"""Shared Ollama httpx client — used by both nemoclaw.py (120B) and light_queue.py (30B).

Uses the streaming API so a cancel_check callable can interrupt generation
between tokens rather than waiting for the full response.
"""

import json
from collections.abc import Callable

import httpx


class GenerationCancelled(Exception):
    """Raised when cancel_check() returns True during token streaming."""


async def ollama_generate(
    prompt: str,
    *,
    system: str,
    model: str,
    base_url: str,
    cancel_check: Callable[[], bool] | None = None,
) -> dict:
    """Stream from Ollama /api/generate with format=json; return parsed response dict.

    Streams individual tokens so cancel_check is evaluated between each chunk,
    allowing fast cancellation without waiting for the full LLM response.

    Raises:
        GenerationCancelled: when cancel_check() returns True mid-stream.
        httpx.HTTPError: on network/HTTP failure.
        ValueError: if the accumulated response is not valid JSON.
    """
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

    raw = _pick_text(full_response, full_thinking)
    if not raw:
        raise ValueError("Empty response from model")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(raw) from exc


def _pick_text(response: str, thinking: str) -> str:
    """Prefer the response field; fall back to thinking for reasoning models."""
    if response.strip():
        return response.strip()
    return thinking.strip()
