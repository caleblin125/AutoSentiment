import httpx
import pytest

from app.tools import media_apis


@pytest.mark.asyncio
async def test_supplemental_media_search_parses_hn_and_reddit(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "hn.algolia.com" in str(request.url):
            return httpx.Response(200, json={"hits": [
                {"url": "https://example.com/story"},
                {"objectID": "123", "url": None},
            ]})
        if "reddit.com" in str(request.url):
            return httpx.Response(200, json={"data": {"children": [
                {"data": {"permalink": "/r/test/comments/abc/title/"}},
            ]}})
        return httpx.Response(404)

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )

    urls = await media_apis.supplemental_media_search("topic", limit=5)

    assert "https://example.com/story" in urls
    assert "https://news.ycombinator.com/item?id=123" in urls
    assert "https://www.reddit.com/r/test/comments/abc/title/" in urls
