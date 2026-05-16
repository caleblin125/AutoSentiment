import httpx
import pytest

from app.tools import media_apis


@pytest.mark.asyncio
async def test_supplemental_media_search_parses_hn_and_reddit(monkeypatch) -> None:
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

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )

    urls = await media_apis.supplemental_media_search("topic", limit=5)

    assert "https://gdelt.example/story" in urls
    assert "https://example.com/story" in urls
    assert "https://news.ycombinator.com/item?id=123" in urls
    assert "https://en.wikipedia.org/wiki/Topic" in urls
    assert "https://arxiv.org/abs/2601.00001" in urls


@pytest.mark.asyncio
async def test_supplemental_media_search_uses_reddit_as_limited_fallback(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "api.gdeltproject.org" in str(request.url):
            return httpx.Response(200, json={"articles": []})
        if "hn.algolia.com" in str(request.url):
            return httpx.Response(200, json={"hits": []})
        if "wikipedia.org" in str(request.url):
            return httpx.Response(200, json=["topic", [], [], []])
        if "export.arxiv.org" in str(request.url):
            return httpx.Response(200, text='<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
        if "reddit.com" in str(request.url):
            return httpx.Response(200, json={"data": {"children": [
                {"data": {"permalink": f"/r/test/comments/{idx}/title/"}} for idx in range(20)
            ]}})
        return httpx.Response(404)

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: orig(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )

    urls = await media_apis.supplemental_media_search("topic", limit=12)

    assert urls
    assert all("reddit.com" in url for url in urls)
    assert len(urls) <= 3
