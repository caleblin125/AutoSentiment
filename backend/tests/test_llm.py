import json

import httpx
import pytest

from app.agents.light_queue import SentimentQueue
from app.agents.nemoclaw import expand_queries, synthesize_report
from app.agents.ollama import ollama_generate
from app.agents.types import SentimentLabel
from app.core.config import Settings


@pytest.mark.asyncio
async def test_ollama_generate_posts_json_contract(monkeypatch) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"response": "{\"ok\": true}"})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: async_client(
            **{**kwargs, "transport": httpx.MockTransport(handler)}
        ),
    )

    result = await ollama_generate("prompt", system="system", model="model", base_url="http://ollama")

    assert result == {"ok": True}
    assert captured["url"] == "http://ollama/api/generate"
    assert captured["body"] == {
        "model": "model",
        "prompt": "prompt",
        "system": "system",
        "format": "json",
        "stream": False,
    }


@pytest.mark.asyncio
async def test_ollama_generate_raises_value_error_for_unparseable_response(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "not json"})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: async_client(
            **{**kwargs, "transport": httpx.MockTransport(handler)}
        ),
    )

    with pytest.raises(ValueError, match="not json"):
        await ollama_generate("prompt", system="system", model="model", base_url="http://ollama")


@pytest.mark.asyncio
async def test_sentiment_queue_returns_parse_error_on_model_failure(monkeypatch) -> None:
    async def failing_generate(*_args, **_kwargs):
        raise ValueError("bad")

    monkeypatch.setattr("app.agents.light_queue.ollama_generate", failing_generate)

    result = await SentimentQueue(Settings()).analyze("snippet")

    assert result.label == SentimentLabel.NEUTRAL
    assert result.summary == "parse error"


@pytest.mark.asyncio
async def test_nemoclaw_wrappers_parse_success_and_fallback(monkeypatch) -> None:
    async def fake_generate(prompt, **_kwargs):
        if "Generate 5 search queries" in prompt:
            return {"queries": ["a", "b", "c", "d", "e", "f"]}
        return {"themes": ["range", "price"], "narrative": "Mostly positive."}

    monkeypatch.setattr("app.agents.nemoclaw.ollama_generate", fake_generate)

    assert await expand_queries("topic", settings=Settings()) == ["a", "b", "c", "d", "e"]
    assert await synthesize_report(
        "topic",
        [{"label": "positive", "summary": "likes range", "source_type": "reddit"}],
        {"overall": {"positive": 1, "neutral": 0, "negative": 0, "total": 1}},
        settings=Settings(),
    ) == {"themes": ["range", "price"], "narrative": "Mostly positive."}

    async def failing_generate(*_args, **_kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr("app.agents.nemoclaw.ollama_generate", failing_generate)

    assert await expand_queries("topic", settings=Settings()) == [
        "topic",
        "topic reddit",
        "topic review",
        "topic news",
        "topic opinions",
    ]
