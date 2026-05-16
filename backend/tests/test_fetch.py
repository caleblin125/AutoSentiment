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
async def test_fetch_items_can_reuse_shared_http_client(monkeypatch) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="<html>ignored</html>")

    monkeypatch.setattr(
        fetch.trafilatura,
        "extract",
        lambda _html: "This shared client paragraph is long enough to become a fetched news item.",
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        items = await fetch.fetch_items("https://news.example/story", client=client)

    assert calls == 1
    assert len(items) == 1
    assert items[0].snippet.startswith("This shared client paragraph")


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


@pytest.mark.asyncio
async def test_read_url_cache_returns_none_when_db_or_ttl_disabled() -> None:
    assert await fetch.read_url_cache(None, "https://x.example/", 60) is None

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models import Base
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            assert await fetch.read_url_cache(db, "https://x.example/", 0) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_url_cache_round_trip_writes_then_reads_items() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models import Base
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        url = "https://news.example/article"
        items = [
            fetch.FetchedItem(snippet="First paragraph", url=url, source_type=SourceType.NEWS),
            fetch.FetchedItem(snippet="Second paragraph", url=url, source_type=SourceType.NEWS),
        ]
        async with factory() as db:
            await fetch.write_url_cache(db, url, items)
            await db.commit()

        async with factory() as db:
            cached = await fetch.read_url_cache(db, url, ttl_seconds=3600)

        assert cached is not None
        assert [item.snippet for item in cached] == ["First paragraph", "Second paragraph"]
        assert cached[0].source_type == SourceType.NEWS
        assert cached[0].url == url
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_url_cache_expires_entries_past_ttl() -> None:
    from datetime import datetime, UTC, timedelta
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models import Base, FetchedURLCache
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        url = "https://news.example/expired"
        async with factory() as db:
            items = [fetch.FetchedItem(snippet="text", url=url, source_type=SourceType.NEWS)]
            await fetch.write_url_cache(db, url, items)
            # Backdate the row past the TTL window.
            row = (await db.execute(
                FetchedURLCache.__table__.select().where(FetchedURLCache.url_hash == fetch._url_hash(url))
            )).first()
            assert row is not None
            await db.execute(
                FetchedURLCache.__table__.update()
                .where(FetchedURLCache.url_hash == fetch._url_hash(url))
                .values(created_at=datetime.now(UTC) - timedelta(seconds=120))
            )
            await db.commit()

        async with factory() as db:
            assert await fetch.read_url_cache(db, url, ttl_seconds=60) is None
            assert await fetch.read_url_cache(db, url, ttl_seconds=300) is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_write_url_cache_overwrites_existing_entry() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models import Base
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        url = "https://news.example/refresh"
        async with factory() as db:
            await fetch.write_url_cache(
                db, url,
                [fetch.FetchedItem(snippet="old", url=url, source_type=SourceType.NEWS)],
            )
            await db.commit()
        async with factory() as db:
            await fetch.write_url_cache(
                db, url,
                [
                    fetch.FetchedItem(snippet="new-1", url=url, source_type=SourceType.NEWS),
                    fetch.FetchedItem(snippet="new-2", url=url, source_type=SourceType.NEWS),
                ],
            )
            await db.commit()
        async with factory() as db:
            cached = await fetch.read_url_cache(db, url, ttl_seconds=3600)
        assert cached is not None
        assert [c.snippet for c in cached] == ["new-1", "new-2"]
    finally:
        await engine.dispose()
