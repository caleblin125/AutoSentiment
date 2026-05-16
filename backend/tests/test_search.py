import httpx
import pytest

from app.core.config import Settings
from app.tools import search


@pytest.mark.asyncio
async def test_brave_search_sends_expected_request_and_parses_web_results(monkeypatch) -> None:
    captured = {}

    async def no_sleep(_seconds: int) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["token"] = request.headers.get("X-Subscription-Token")
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {"url": "https://a.example"},
                        {"title": "missing url"},
                        {"url": "https://b.example"},
                    ]
                }
            },
        )

    async_client = httpx.AsyncClient
    monkeypatch.setattr(search.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(
        search.httpx,
        "AsyncClient",
        lambda **kwargs: async_client(
            **{**kwargs, "transport": httpx.MockTransport(handler)}
        ),
    )

    urls = await search.brave_search(
        "Tesla Model 3",
        freshness="pm",
        count=7,
        settings=Settings(brave_api_key="dummy-test-token"),
    )

    assert urls == ["https://a.example", "https://b.example"]
    assert captured["method"] == "GET"
    assert captured["token"] == "dummy-test-token"
    assert "q=Tesla+Model+3" in captured["url"]
    assert "count=7" in captured["url"]
    assert "freshness=pm" in captured["url"]


@pytest.mark.asyncio
async def test_brave_search_clamps_count_to_brave_max(monkeypatch) -> None:
    captured = {}

    async def no_sleep(_seconds: int) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"web": {"results": []}})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(search.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(
        search.httpx,
        "AsyncClient",
        lambda **kwargs: async_client(
            **{**kwargs, "transport": httpx.MockTransport(handler)}
        ),
    )

    await search.brave_search("topic", count=30, settings=Settings(brave_api_key="dummy-test-token"))

    assert "count=20" in captured["url"]


@pytest.mark.asyncio
async def test_brave_search_fails_fast_when_api_key_missing(monkeypatch) -> None:
    async def no_sleep(_seconds: int) -> None:
        return None

    monkeypatch.setattr(search.asyncio, "sleep", no_sleep)

    with pytest.raises(RuntimeError, match="BRAVE_API_KEY is not configured"):
        await search.brave_search("topic", settings=Settings(brave_api_key=""))


def test_extract_result_urls_supports_legacy_top_level_shape() -> None:
    assert search._extract_result_urls({"results": [{"url": "https://example.com"}]}) == [
        "https://example.com"
    ]
