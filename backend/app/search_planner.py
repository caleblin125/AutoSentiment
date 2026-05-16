from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import BraveQuotaUsage
from app.research_depth import ResearchDepthBudget, get_depth_budget

UseCase = Literal[
    "generic",
    "entertainment_product",
    "public_current_event",
    "brand_product",
    "policy_civic",
]

VALID_USE_CASES: tuple[UseCase, ...] = (
    "generic",
    "entertainment_product",
    "public_current_event",
    "brand_product",
    "policy_civic",
)

BRAVE_MONTHLY_FREE_QUOTA = 2000


@dataclass(frozen=True)
class PlannedQuery:
    query: str
    purpose: str
    source_target: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SearchPlan:
    topic: str
    freshness: str | None
    research_depth: str
    use_case: UseCase
    query_budget: int
    url_budget: int
    item_budget: int
    source_diversity_target: int
    estimated_brave_queries: int
    monthly_quota_used: int
    monthly_quota_remaining: int
    quota_warning: str | None
    queries: list[PlannedQuery]

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "freshness": self.freshness,
            "research_depth": self.research_depth,
            "use_case": self.use_case,
            "query_budget": self.query_budget,
            "url_budget": self.url_budget,
            "item_budget": self.item_budget,
            "source_diversity_target": self.source_diversity_target,
            "estimated_brave_queries": self.estimated_brave_queries,
            "monthly_quota_used": self.monthly_quota_used,
            "monthly_quota_remaining": self.monthly_quota_remaining,
            "quota_warning": self.quota_warning,
            "queries": [query.to_dict() for query in self.queries],
        }


def normalize_use_case(value: str | None) -> UseCase:
    if value is None:
        return "generic"
    if value not in VALID_USE_CASES:
        raise ValueError(f"use_case must be one of: {', '.join(VALID_USE_CASES)}")
    return value  # type: ignore[return-value]


async def build_search_plan(
    topic: str,
    *,
    freshness: str | None,
    research_depth: str | None,
    use_case: str | None,
    settings: Settings,
    db: AsyncSession | None = None,
    base_queries: list[str] | None = None,
) -> SearchPlan:
    budget = get_depth_budget(research_depth, settings)
    normalized_use_case = normalize_use_case(use_case)
    monthly_used = await get_monthly_quota_used(db) if db is not None else 0
    queries = plan_queries(topic, budget, normalized_use_case, base_queries=base_queries)
    estimated = min(budget.query_count, len(queries))
    remaining = max(0, BRAVE_MONTHLY_FREE_QUOTA - monthly_used)
    warning = _quota_warning(estimated, remaining)
    return SearchPlan(
        topic=topic,
        freshness=freshness,
        research_depth=budget.name,
        use_case=normalized_use_case,
        query_budget=budget.query_count,
        url_budget=budget.url_count,
        item_budget=budget.item_count,
        source_diversity_target=budget.source_diversity_target,
        estimated_brave_queries=estimated,
        monthly_quota_used=monthly_used,
        monthly_quota_remaining=remaining,
        quota_warning=warning,
        queries=queries[:budget.query_count],
    )


def plan_queries(
    topic: str,
    budget: ResearchDepthBudget,
    use_case: UseCase,
    *,
    base_queries: list[str] | None = None,
) -> list[PlannedQuery]:
    candidates: list[PlannedQuery] = []
    for query in base_queries or []:
        candidates.append(PlannedQuery(query=query, purpose="model suggested", source_target="mixed"))

    candidates.extend(_purpose_queries(topic, use_case))

    seen: set[str] = set()
    deduped: list[PlannedQuery] = []
    for query in candidates:
        key = " ".join(query.query.casefold().split())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(query)
        if len(deduped) >= max(budget.query_count, budget.source_diversity_target):
            break
    return deduped


async def get_monthly_quota_used(db: AsyncSession | None) -> int:
    if db is None:
        return 0
    usage = await db.get(BraveQuotaUsage, current_quota_month())
    return usage.query_count if usage is not None else 0


async def record_brave_query(db: AsyncSession) -> int:
    month = current_quota_month()
    usage = await db.get(BraveQuotaUsage, month)
    if usage is None:
        usage = BraveQuotaUsage(month=month, query_count=0)
        db.add(usage)
    usage.query_count += 1
    usage.updated_at = datetime.now(UTC)
    await db.flush()
    return usage.query_count


def current_quota_month() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _quota_warning(estimated_queries: int, remaining_queries: int) -> str | None:
    if estimated_queries > remaining_queries:
        return "This run exceeds the remaining tracked Brave quota."
    if remaining_queries - estimated_queries < 100:
        return "This run leaves fewer than 100 tracked Brave queries for the month."
    return None


def _purpose_queries(topic: str, use_case: UseCase) -> list[PlannedQuery]:
    generic = [
        PlannedQuery(topic, "broad overview", "mixed"),
        PlannedQuery(f"{topic} official announcement data", "official/factual sources", "official"),
        PlannedQuery(f"{topic} news analysis", "established news", "news"),
        PlannedQuery(f"{topic} reddit discussion", "public opinion", "reddit"),
        PlannedQuery(f"{topic} reviews criticism", "reviews and complaints", "reviews"),
        PlannedQuery(f"{topic} expert assessment", "expert reviews", "expert"),
        PlannedQuery(f"{topic} YouTube review discussion", "video/social reaction", "video"),
        PlannedQuery(f"{topic} forum discussion", "forums and communities", "forum"),
        PlannedQuery(f"{topic} controversy timeline", "chronology and events", "timeline"),
        PlannedQuery(f"{topic} facts data source", "fact-checking evidence", "primary sources"),
    ]
    if use_case == "entertainment_product":
        return [
            PlannedQuery(topic, "broad product overview", "mixed"),
            PlannedQuery(f"{topic} trailer reaction", "marketing reaction", "video"),
            PlannedQuery(f"{topic} reddit fan discussion", "fandom reaction", "reddit"),
            PlannedQuery(f"{topic} critic review", "critic pulse", "critics"),
            PlannedQuery(f"{topic} box office streaming ratings", "commercial data", "industry data"),
            PlannedQuery(f"{topic} controversy backlash", "launch risk", "news/social"),
            PlannedQuery(f"{topic} YouTube review", "creator reaction", "video"),
            PlannedQuery(f"{topic} metacritic rotten tomatoes", "review aggregators", "review data"),
            PlannedQuery(f"{topic} industry trade report", "trade coverage", "trade press"),
            PlannedQuery(f"{topic} audience complaints", "conversion blockers", "public opinion"),
            *generic,
        ]
    if use_case == "public_current_event":
        return [
            PlannedQuery(topic, "event overview", "mixed"),
            PlannedQuery(f"{topic} official statement document", "primary sources", "official"),
            PlannedQuery(f"{topic} timeline what happened", "chronology", "news"),
            PlannedQuery(f"{topic} local news", "local sources", "local news"),
            PlannedQuery(f"{topic} Reuters AP BBC", "wire and established news", "news"),
            PlannedQuery(f"{topic} misinformation fact check", "disputed claims", "fact-check"),
            PlannedQuery(f"{topic} public reaction reddit", "public reaction", "reddit"),
            PlannedQuery(f"{topic} expert analysis", "expert context", "expert"),
            *generic,
        ]
    if use_case == "policy_civic":
        return [
            PlannedQuery(f"{topic} official policy document", "primary documents", "official"),
            PlannedQuery(f"{topic} legal analysis", "legal context", "expert"),
            PlannedQuery(f"{topic} public comment reaction", "public reaction", "social"),
            *generic,
        ]
    if use_case == "brand_product":
        return [
            PlannedQuery(f"{topic} customer reviews complaints", "customer experience", "reviews"),
            PlannedQuery(f"{topic} pricing value competitors", "market position", "market"),
            PlannedQuery(f"{topic} support warranty issues", "support risk", "reviews"),
            *generic,
        ]
    return generic
