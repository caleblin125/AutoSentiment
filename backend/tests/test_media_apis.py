import asyncio

import httpx
import pytest

from app.tools import media_apis


def _make_handler():
    """Return an httpx handler that serves one result per source."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "api.gdeltproject.org" in str(request.url):
            return httpx.Response(200, json={"articles": [
                {"url": "https://gdelt.example/story"},
            ]})
        if "hn.algolia.com" in str(request.url):
            return httpx.Response(200, json={"hits": [
                {"url": "https://example.com/story"},
                {"objectID": "123", "url": None},
            ]})
        if "wikipedia.org" in str(request.url):
            return httpx.Response(200, json=[
                "topic", ["Topic"], [""], ["https://en.wikipedia.org/wiki/Topic"],
            ])
        if "export.arxiv.org" in str(request.url):
            return httpx.Response(200, text="""<?xml version="1.0" encoding="UTF-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom">
                  <entry><id>https://arxiv.org/abs/2601.00001</id></entry>
                </feed>""")
        if "reddit.com" in str(request.url):
            return httpx.Response(200, json={"data": {"children": [
                {"data": {"permalink": "/r/test/comments/abc/title/"}},
            ]}})
        return httpx.Response(404)
    return handler


@pytest.mark.asyncio
async def test_supplemental_media_search_parses_all_sources(monkeypatch) -> None:
    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(_make_handler())}),
    )

    urls = await media_apis.supplemental_media_search("topic", limit=10)

    assert "https://gdelt.example/story" in urls
    assert "https://example.com/story" in urls
    assert "https://news.ycombinator.com/item?id=123" in urls
    assert "https://en.wikipedia.org/wiki/Topic" in urls
    assert "https://arxiv.org/abs/2601.00001" in urls


@pytest.mark.asyncio
async def test_supplemental_media_search_runs_sources_in_parallel(monkeypatch) -> None:
    """All 5 sources should be dispatched simultaneously (not sequentially)."""
    start_times: list[float] = []

    async def slow_gdelt(*_a, **_kw) -> list[str]:
        start_times.append(asyncio.get_event_loop().time())
        await asyncio.sleep(0.05)
        return ["https://gdelt.example/a"]

    async def fast_hn(*_a, **_kw) -> list[str]:
        start_times.append(asyncio.get_event_loop().time())
        return ["https://hn.example/b"]

    async def fast_wiki(*_a, **_kw) -> list[str]:
        return []

    async def fast_arxiv(*_a, **_kw) -> list[str]:
        return []

    async def fast_reddit(*_a, **_kw) -> list[str]:
        return []

    monkeypatch.setattr(media_apis, "_search_gdelt", slow_gdelt)
    monkeypatch.setattr(media_apis, "_search_hacker_news", fast_hn)
    monkeypatch.setattr(media_apis, "_search_wikipedia", fast_wiki)
    monkeypatch.setattr(media_apis, "_search_arxiv", fast_arxiv)
    monkeypatch.setattr(media_apis, "_search_reddit", fast_reddit)

    urls = await media_apis.supplemental_media_search("topic", limit=5)

    assert "https://gdelt.example/a" in urls
    assert "https://hn.example/b" in urls
    # Both GDELT and HN should have started before GDELT's sleep finished,
    # confirming parallel dispatch (start times very close together).
    assert len(start_times) == 2
    assert abs(start_times[1] - start_times[0]) < 0.04


@pytest.mark.asyncio
async def test_supplemental_media_search_include_source_map(monkeypatch) -> None:
    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(_make_handler())}),
    )

    result = await media_apis.supplemental_media_search("topic", limit=10, include_source_map=True)

    assert isinstance(result, tuple)
    urls, source_map = result
    assert urls
    assert "https://gdelt.example/story" in source_map
    assert "gdelt" in source_map["https://gdelt.example/story"]
    assert "https://example.com/story" in source_map
    assert "hn" in source_map["https://example.com/story"]


@pytest.mark.asyncio
async def test_supplemental_media_search_tolerates_source_errors(monkeypatch) -> None:
    async def boom(*_a, **_kw) -> list[str]:
        raise RuntimeError("network error")

    async def ok(*_a, **_kw) -> list[str]:
        return ["https://ok.example/item"]

    monkeypatch.setattr(media_apis, "_search_gdelt", boom)
    monkeypatch.setattr(media_apis, "_search_hacker_news", ok)
    monkeypatch.setattr(media_apis, "_search_wikipedia", boom)
    monkeypatch.setattr(media_apis, "_search_arxiv", boom)
    monkeypatch.setattr(media_apis, "_search_reddit", boom)

    urls = await media_apis.supplemental_media_search("topic", limit=5)

    assert urls == ["https://ok.example/item"]


@pytest.mark.asyncio
async def test_supplemental_media_search_caps_reddit(monkeypatch) -> None:
    """Reddit should contribute at most ~25% of the final URL count."""
    async def empty(*_a, **_kw) -> list[str]:
        return []

    async def many_reddit(_client, _query, limit: int) -> list[str]:
        return [f"https://www.reddit.com/r/t/{i}" for i in range(20)][:limit]

    monkeypatch.setattr(media_apis, "_search_gdelt", empty)
    monkeypatch.setattr(media_apis, "_search_hacker_news", empty)
    monkeypatch.setattr(media_apis, "_search_wikipedia", empty)
    monkeypatch.setattr(media_apis, "_search_arxiv", empty)
    monkeypatch.setattr(media_apis, "_search_reddit", many_reddit)

    urls = await media_apis.supplemental_media_search("topic", limit=12)

    assert urls
    assert all("reddit.com" in u for u in urls)
    # reddit_limit = max(2, 12 // 4) = 3
    assert len(urls) <= 3
