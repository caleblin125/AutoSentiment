"""Shared Ollama httpx client — used by both nemoclaw.py (120B) and light_queue.py (30B).

Uses the streaming API so a cancel_check callable can interrupt generation
between tokens rather than waiting for the full response.
"""

import json
import re
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

    return _parse_model_json(_pick_text(full_response, full_thinking))


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

    Returns the parsed JSON result after streaming completes. The on_token
    callback receives each new text fragment as it arrives.
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
                token = chunk.get("response", "")
                if token and on_token:
                    on_token(token)
                full_response += token
                full_thinking += chunk.get("thinking", "")
                if chunk.get("done"):
                    break

    return _parse_model_json(_pick_text(full_response, full_thinking))


def _pick_text(response: str, thinking: str) -> str:
    """Prefer the response field; fall back to thinking for reasoning models."""
    if response.strip():
        return response.strip()
    return thinking.strip()


def _parse_model_json(text: str) -> dict:
    """Parse a JSON object even when the model adds prose or markdown fences.

    Ollama's ``format=json`` strongly nudges structured output, but small local
    models still occasionally include wrappers. Recovering the first balanced
    object prevents otherwise useful sentiment calls from becoming parse errors.
    """
    raw = text.strip()
    if not raw:
        raise ValueError("Empty response from model")

    candidates = [raw, *_json_candidates(raw)]
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(raw)


def _json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE):
        candidates.append(match.group(1).strip())

    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            char = text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:idx + 1])
                    break
        start = text.find("{", start + 1)
    return candidates
