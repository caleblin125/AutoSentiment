import json

import httpx
import pytest

from app.agents.light_queue import SentimentQueue
from app.agents.nemoclaw import expand_queries, synthesize_report, synthesize_report_streaming
from app.agents.ollama import ollama_generate, ollama_generate_streaming
from app.agents.types import SentimentLabel
from app.core.config import Settings


def _streaming_handler(response_text: str):
    """Return an httpx handler that yields a streaming NDJSON Ollama response."""
    body = json.dumps({"response": response_text, "done": True}).encode() + b"\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return handler


@pytest.mark.asyncio
async def test_ollama_generate_posts_json_contract(monkeypatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        body = json.dumps({"response": '{"ok": true}', "done": True}).encode() + b"\n"
        return httpx.Response(200, content=body)

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )

    result = await ollama_generate("prompt", system="system", model="model", base_url="http://ollama")

    assert result == {"ok": True}
    assert captured["url"] == "http://ollama/api/generate"
    # Streaming is now enabled.
    assert captured["body"]["stream"] is True
    assert captured["body"]["format"] == "json"
    assert captured["body"]["model"] == "model"
    assert captured["body"]["prompt"] == "prompt"
    assert captured["body"]["system"] == "system"


@pytest.mark.asyncio
async def test_ollama_generate_parses_json_from_thinking_when_response_empty(monkeypatch) -> None:
    """When response is empty and thinking contains JSON, fall back to thinking."""
    body = json.dumps({
        "response": "",
        "thinking": '{"label": "positive", "summary": "likes it"}',
        "done": True,
    }).encode() + b"\n"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )

    result = await ollama_generate("prompt", system="system", model="model", base_url="http://ollama")

    assert result == {"label": "positive", "summary": "likes it"}


@pytest.mark.asyncio
async def test_ollama_generate_raises_value_error_for_unparseable_response(monkeypatch) -> None:
    body = json.dumps({"response": "not json", "done": True}).encode() + b"\n"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )

    with pytest.raises(ValueError, match="not json"):
        await ollama_generate("prompt", system="system", model="model", base_url="http://ollama")


@pytest.mark.asyncio
async def test_ollama_generate_cancel_check_raises_cancelled(monkeypatch) -> None:
    """cancel_check=lambda: True must raise GenerationCancelled."""
    from app.agents.ollama import GenerationCancelled

    # Return multiple streaming chunks so the cancel_check fires.
    lines = b"".join(
        json.dumps({"response": c, "done": False}).encode() + b"\n"
        for c in ["a", "b", "c"]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=lines)

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )

    with pytest.raises(GenerationCancelled):
        await ollama_generate(
            "prompt", system="s", model="m", base_url="http://ollama",
            cancel_check=lambda: True,
        )


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
    result = await synthesize_report(
        "topic",
        [{"label": "positive", "summary": "likes range", "source_type": "reddit"}],
        {"overall": {"positive": 1, "neutral": 0, "negative": 0, "total": 1}},
        settings=Settings(),
    )
    assert result["themes"] == ["range", "price"]
    assert result["narrative"] == "Mostly positive."
    assert result["impacts"] == []
    assert result["reasons"] == []
    assert result["arguments"] == []

    async def failing_generate(*_args, **_kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr("app.agents.nemoclaw.ollama_generate", failing_generate)

    fallback = await expand_queries("topic", settings=Settings())
    # Fallback should have "topic" as first element and use review/news/etc (not reddit).
    assert fallback[0] == "topic"
    assert any("review" in q for q in fallback)
    assert len(fallback) == 5


@pytest.mark.asyncio
async def test_ollama_generate_streaming_calls_on_token_for_each_chunk(monkeypatch) -> None:
    """ollama_generate_streaming must invoke on_token for every non-empty chunk."""
    chunks = [
        {"response": "{", "done": False},
        {"response": '"themes"', "done": False},
        {"response": ": []}", "done": True},
    ]
    body = b"".join(json.dumps(c).encode() + b"\n" for c in chunks)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )

    received: list[str] = []
    result = await ollama_generate_streaming(
        "prompt", system="s", model="m", base_url="http://ollama",
        on_token=lambda tok: received.append(tok),
    )

    assert result == {"themes": []}
    assert received == ["{", '"themes"', ": []}"]


@pytest.mark.asyncio
async def test_ollama_generate_streaming_cancel_check_raises(monkeypatch) -> None:
    """cancel_check=lambda: True must raise GenerationCancelled during streaming."""
    from app.agents.ollama import GenerationCancelled

    lines = b"".join(
        json.dumps({"response": c, "done": False}).encode() + b"\n"
        for c in ["a", "b", "c"]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=lines)

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )

    with pytest.raises(GenerationCancelled):
        await ollama_generate_streaming(
            "prompt", system="s", model="m", base_url="http://ollama",
            cancel_check=lambda: True,
        )


@pytest.mark.asyncio
async def test_synthesize_report_streaming_streams_tokens_and_returns_structure(monkeypatch) -> None:
    """synthesize_report_streaming must fire on_token and return the parsed result."""
    synthesis_json = json.dumps({
        "themes": ["budget", "range"],
        "narrative": "Mostly positive.",
        "impacts": [{"direction": "positive", "description": "Good range"}],
        "reasons": ["fans love it"],
        "arguments": [{"claim": "great value", "side": "for"}],
    })
    # Split the JSON into two chunks to test that tokens accumulate correctly.
    mid = len(synthesis_json) // 2
    chunks = [
        {"response": synthesis_json[:mid], "done": False},
        {"response": synthesis_json[mid:], "done": True},
    ]
    body = b"".join(json.dumps(c).encode() + b"\n" for c in chunks)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )

    tokens: list[str] = []
    result = await synthesize_report_streaming(
        "Electric vehicles",
        [{"label": "positive", "summary": "great range", "source_type": "reddit"}],
        {"overall": {"positive": 0.8, "neutral": 0.1, "negative": 0.1, "total": 10}},
        settings=Settings(),
        on_token=lambda tok: tokens.append(tok),
    )

    assert result["themes"] == ["budget", "range"]
    assert result["narrative"] == "Mostly positive."
    assert result["impacts"][0]["direction"] == "positive"
    assert result["reasons"] == ["fans love it"]
    assert result["arguments"][0]["side"] == "for"
    # Tokens must have been streamed.
    assert tokens
    assert "".join(tokens) == synthesis_json


@pytest.mark.asyncio
async def test_synthesize_report_streaming_falls_back_on_model_failure(monkeypatch) -> None:
    """A model error must return a safe fallback dict, not raise."""
    async def failing(*_a, **_kw):
        raise RuntimeError("model down")

    monkeypatch.setattr("app.agents.nemoclaw.ollama_generate_streaming", failing)

    result = await synthesize_report_streaming(
        "topic", [], {"overall": {"total": 0}},
        settings=Settings(),
    )

    assert "themes" in result
    assert "narrative" in result
    assert isinstance(result["themes"], list)
    assert isinstance(result["narrative"], str)
