import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models import Base
from app.search_planner import build_search_plan, record_brave_query


@pytest.fixture(autouse=True)
def disable_llm_query_planning(monkeypatch):
    async def fail_fast(*_args, **_kwargs):
        raise RuntimeError("disabled in tests")

    monkeypatch.setattr("app.agents.ollama.ollama_generate", fail_fast)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_plan_uses_depth_budget_and_use_case(db_session) -> None:
    plan = await build_search_plan(
        "New sci-fi show",
        freshness="pm",
        research_depth="deep",
        use_case="entertainment_product",
        settings=Settings(),
        db=db_session,
    )

    assert plan.research_depth == "deep"
    assert plan.use_case == "entertainment_product"
    assert plan.estimated_brave_queries == 10
    assert plan.url_budget == 60
    assert any(query.purpose == "social reaction" for query in plan.queries)


@pytest.mark.asyncio
async def test_search_plan_tracks_monthly_quota(db_session) -> None:
    await record_brave_query(db_session)
    await record_brave_query(db_session)
    await db_session.commit()

    plan = await build_search_plan(
        "topic",
        freshness=None,
        research_depth="quick",
        use_case="generic",
        settings=Settings(),
        db=db_session,
    )

    assert plan.monthly_quota_used == 2
    assert plan.monthly_quota_remaining == 1998


@pytest.mark.asyncio
async def test_search_plan_deduplicates_model_queries(db_session) -> None:
    plan = await build_search_plan(
        "topic",
        freshness=None,
        research_depth="quick",
        use_case="generic",
        settings=Settings(),
        db=db_session,
        base_queries=["topic", " Topic  "],
    )

    assert [query.query for query in plan.queries].count("topic") == 1


@pytest.mark.asyncio
async def test_search_plan_uses_llm_queries_when_available(monkeypatch, db_session) -> None:
    async def fake_generate(*_args, **_kwargs):
        return {
            "queries": [
                {"query": "topic expert reviews", "purpose": "expert analysis", "source_target": "expert"},
                {"query": "topic public backlash", "purpose": "controversy", "source_target": "social"},
            ]
        }

    monkeypatch.setattr("app.agents.ollama.ollama_generate", fake_generate)

    plan = await build_search_plan(
        "topic",
        freshness="pw",
        research_depth="quick",
        use_case="generic",
        settings=Settings(),
        db=db_session,
    )

    assert plan.queries[0].query == "topic expert reviews"
    assert plan.queries[0].purpose == "expert analysis"
