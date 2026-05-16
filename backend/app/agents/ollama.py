"""Shared Ollama httpx client — used by both nemoclaw.py (120B) and light_queue.py (30B)."""

import json

import httpx


async def ollama_generate(
    prompt: str,
    *,
    system: str,
    model: str,
    base_url: str,
) -> dict:
    """POST to Ollama /api/generate with format=json. Returns parsed response dict.

    Raises httpx.HTTPError on network failure.
    Raises ValueError if the response body is not valid JSON.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "system": system,
                "format": "json",
                "stream": False,
            },
        )
        response.raise_for_status()
        payload = response.json()

    raw_response = payload.get("response", "")
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ValueError(raw_response) from exc
