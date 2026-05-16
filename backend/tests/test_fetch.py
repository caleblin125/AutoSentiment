import httpx
import pytest

from app.agents.types import SourceType
from app.ingest import fetch


@pytest.mark.asyncio
async def test_fetch_reddit_parses_comments_and_caps(monkeypatch) -> None:
    children = [
        {"kind": "more", "data": {"body": "skip"}},
        {"kind": "t1", "data": {"body": "  "}},
    ] + [
        {"kind": "t1", "data": {"body": f"comment {i}"}}
        for i in range(fetch.REDDIT_COMMENTS_PER_THREAD + 5)
    ]
    seen_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=[{}, {"data": {"children": children}}])

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        fetch.httpx,
        "AsyncClient",
        lambda **kwargs: async_client(
            **{**kwargs, "transport": httpx.MockTransport(handler)}
        ),
    )

    items = await fetch._fetch_reddit("https://www.reddit.com/r/test/comments/abc/title/")

    assert seen_urls == ["https://www.reddit.com/r/test/comments/abc/title.json"]
    assert len(items) == fetch.REDDIT_COMMENTS_PER_THREAD
    assert items[0].snippet == "comment 0"
    assert items[0].source_type == SourceType.REDDIT


@pytest.mark.asyncio
async def test_fetch_news_extracts_long_paragraphs(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>ignored</html>")

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        fetch.httpx,
        "AsyncClient",
        lambda **kwargs: async_client(
            **{**kwargs, "transport": httpx.MockTransport(handler)}
        ),
    )
    monkeypatch.setattr(
        fetch.trafilatura,
        "extract",
        lambda _html: "short\n\nThis paragraph is long enough to become a fetched news item.",
    )

    items = await fetch._fetch_news("https://news.example/story")

    assert len(items) == 1
    assert items[0].snippet == "This paragraph is long enough to become a fetched news item."
    assert items[0].source_type == SourceType.NEWS


@pytest.mark.asyncio
async def test_fetch_items_returns_empty_list_on_fetch_failure(monkeypatch) -> None:
    async def failing_fetch(_url: str):
        raise RuntimeError("network failed")

    monkeypatch.setattr(fetch, "_fetch_news", failing_fetch)

    assert await fetch.fetch_items("https://news.example/fail") == []


def test_classify_source_type_identifies_platforms() -> None:
    assert fetch.classify_source_type("https://www.reddit.com/r/test") == SourceType.REDDIT
    assert fetch.classify_source_type("https://news.ycombinator.com/item?id=1") == SourceType.FORUM
    assert fetch.classify_source_type("https://youtube.com/watch?v=1") == SourceType.VIDEO
    assert fetch.classify_source_type("https://x.com/example/status/1") == SourceType.SOCIAL
    assert fetch.classify_source_type("https://example.com/post") == SourceType.WEB
