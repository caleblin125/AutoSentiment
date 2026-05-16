import httpx
import pytest

from app.core.config import Settings
from app.tools import search


@pytest.fixture(autouse=True)
def clear_search_cache() -> None:
    search._memory_cache.clear()


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


def test_is_cached_search_reports_valid_cache_entry() -> None:
    cache_key = search._make_cache_key("topic", "pm", 5)
    search._memory_cache[cache_key] = (search.monotonic(), ["https://example.com"])

    assert search.is_cached_search(" Topic ", freshness="pm", count=5)
    assert not search.is_cached_search("Topic", freshness="pw", count=5)


@pytest.mark.asyncio
async def test_brave_search_uses_cache_without_second_http_call(monkeypatch) -> None:
    calls = 0

    async def no_sleep(_seconds: int) -> None:
        return None

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"web": {"results": [{"url": "https://cached.example"}]}})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(search.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(
        search.httpx,
        "AsyncClient",
        lambda **kwargs: async_client(
            **{**kwargs, "transport": httpx.MockTransport(handler)}
        ),
    )

    settings = Settings(**{"brave_api_key": "dummy-test-token"})
    first = await search.brave_search("Cache Me", freshness="pm", count=5, settings=settings)
    second = await search.brave_search(" cache me ", freshness="pm", count=5, settings=settings)

    assert first == ["https://cached.example"]
    assert second == first
    assert calls == 1
