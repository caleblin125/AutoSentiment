"""Search planner — generates purpose-labeled Brave queries.

Two strategies:
  1. Template-based (fast, always works) — purpose-specific query templates
  2. LLM-generated (smart, context-aware) — nemotron writes optimized queries

The LLM path is tried first and falls back to templates on failure.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import BraveQuotaUsage
from app.research_depth import ResearchDepthBudget, get_depth_budget

logger = logging.getLogger(__name__)

UseCase = Literal[
    "generic", "entertainment_product", "public_current_event",
    "brand_product", "policy_civic", "financial_market",
]

VALID_USE_CASES: tuple[UseCase, ...] = (
    "generic", "entertainment_product", "public_current_event",
    "brand_product", "policy_civic", "financial_market",
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
            "topic": self.topic, "freshness": self.freshness,
            "research_depth": self.research_depth, "use_case": self.use_case,
            "query_budget": self.query_budget, "url_budget": self.url_budget,
            "item_budget": self.item_budget,
            "source_diversity_target": self.source_diversity_target,
            "estimated_brave_queries": self.estimated_brave_queries,
            "monthly_quota_used": self.monthly_quota_used,
            "monthly_quota_remaining": self.monthly_quota_remaining,
            "quota_warning": self.quota_warning,
            "queries": [q.to_dict() for q in self.queries],
        }


def normalize_use_case(value: str | None) -> UseCase:
    if value is None:
        return "generic"
    if value not in VALID_USE_CASES:
        raise ValueError(f"use_case must be one of: {', '.join(VALID_USE_CASES)}")
    return value  # type: ignore[return-value]


async def build_search_plan(
    topic: str, *, freshness: str | None, research_depth: str | None,
    use_case: str | None, settings: Settings,
    db: AsyncSession | None = None,
    base_queries: list[str] | None = None,
) -> SearchPlan:
    budget = get_depth_budget(research_depth, settings)
    normalized_use_case = normalize_use_case(use_case)
    monthly_used = await get_monthly_quota_used(db) if db is not None else 0

    # Try LLM-generated queries first, fall back to templates.
    queries = await generate_smart_queries(
        topic, budget, normalized_use_case, freshness, settings,
        base_queries=base_queries,
    )

    estimated = min(budget.query_count, len(queries))
    remaining = max(0, BRAVE_MONTHLY_FREE_QUOTA - monthly_used)
    warning = _quota_warning(estimated, remaining)
    return SearchPlan(
        topic=topic, freshness=freshness, research_depth=budget.name,
        use_case=normalized_use_case, query_budget=budget.query_count,
        url_budget=budget.url_count, item_budget=budget.item_count,
        source_diversity_target=budget.source_diversity_target,
        estimated_brave_queries=estimated, monthly_quota_used=monthly_used,
        monthly_quota_remaining=remaining, quota_warning=warning,
        queries=queries[:budget.query_count],
    )


async def generate_smart_queries(
    topic: str, budget: ResearchDepthBudget, use_case: UseCase,
    freshness: str | None, settings: Settings,
    *, base_queries: list[str] | None = None,
) -> list[PlannedQuery]:
    """Generate Brave-optimized search queries using the 120B model.

    Falls back to template queries if the model is unavailable or fails.
    """
    count = min(budget.query_count, 12)  # never ask for more than 12
    freshness_label = {"pd": "past day", "pw": "past week", "pm": "past month", "py": "past year"}.get(freshness or "", "any time")

    use_case_guidance = {
        "generic": "cover broad sentiment, news, reviews, and public discussion",
        "entertainment_product": "cover fan reaction, critic reviews, box office/commercial data, casting, trailers, controversy",
        "public_current_event": "cover official sources, primary documents, reputable news, chronology, fact-checking, public reaction",
        "brand_product": "cover customer reviews, pricing, competitors, support quality, market position",
        "policy_civic": "cover official documents, legal analysis, public comment, expert opinion",
        "financial_market": "cover analyst ratings, earnings, SEC filings, retail investor sentiment, market data, sector trends",
    }
    guidance = use_case_guidance.get(use_case, use_case_guidance["generic"])

    system = "You are a search query engineer. Output must be valid JSON. No explanations."
    prompt = (
        f"Generate {count} Brave Search queries to research public sentiment about: \"{topic}\"\n"
        f"Time window: {freshness_label}\n"
        f"Use case: {use_case.replace('_', ' ')} — {guidance}\n\n"
        "Write each query as a concise, natural search phrase that would return high-quality web results.\n"
        "Include a diverse mix: broad overview, specific angles, different platforms, contrary opinions.\n"
        "Avoid template-like prefixes (no \"reddit discussion of...\"). Just write the natural search phrase.\n\n"
        "Return exactly this JSON format:\n"
        '{"queries": [{"query": "...", "purpose": "...", "source_target": "..."}]}\n\n'
        "Purpose should be short: \"broad overview\", \"expert analysis\", \"public opinion\", "
        "\"official sources\", \"reviews\", \"social reaction\", \"commercial data\", \"controversy\", "
        "\"chronology\", \"fact check\", \"international angle\".\n"
        "Source target should be one: mixed, official, news, reddit, reviews, expert, video, forum, social, "
        "financial data, financial news, market data."
    )

    # Try base queries first (from 120B expand_queries).
    if base_queries:
        candidates = [PlannedQuery(query=q, purpose="model suggested", source_target="mixed") for q in base_queries[:count]]
    else:
        candidates = []

    # Try LLM generation.
    try:
        from app.agents.ollama import ollama_generate
        payload = await asyncio.wait_for(
            ollama_generate(
                prompt, system=system, model=settings.nemoclaw_model,
                base_url=settings.ollama_base_url,
            ),
            timeout=5.0,
        )
        raw = payload.get("queries", [])
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("query"):
                    candidates.append(PlannedQuery(
                        query=str(item["query"]).strip(),
                        purpose=str(item.get("purpose", "model suggested")).strip() or "model suggested",
                        source_target=str(item.get("source_target", "mixed")).strip() or "mixed",
                    ))
    except Exception:
        logger.warning("LLM query generation failed, using templates only")

    # Fill remaining slots with template queries if needed.
    if len(candidates) < count:
        candidates.extend(_purpose_queries(topic, use_case)[:count - len(candidates)])

    # Deduplicate.
    seen: set[str] = set()
    deduped: list[PlannedQuery] = []
    for q in candidates:
        key = " ".join(q.query.casefold().split())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)
        if len(deduped) >= max(budget.query_count, budget.source_diversity_target):
            break
    if len(deduped) < budget.query_count:
        for q in _purpose_queries(topic, use_case):
            key = " ".join(q.query.casefold().split())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(q)
            if len(deduped) >= budget.query_count:
                break
    return deduped


async def get_monthly_quota_used(db: AsyncSession | None) -> int:
    if db is None: return 0
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
    """Template fallback queries — used when LLM is unavailable."""
    generic = [
        PlannedQuery(topic, "broad overview", "mixed"),
        PlannedQuery(f"{topic} official data", "official sources", "official"),
        PlannedQuery(f"{topic} news analysis", "established news", "news"),
        PlannedQuery(f"{topic} reviews opinions", "reviews", "reviews"),
        PlannedQuery(f"{topic} expert assessment", "expert analysis", "expert"),
        PlannedQuery(f"{topic} forum community", "public opinion", "forum"),
    ]
    if use_case == "entertainment_product":
        return [
            PlannedQuery(topic, "broad overview", "mixed"),
            PlannedQuery(f"{topic} trailer reaction", "social reaction", "video"),
            PlannedQuery(f"{topic} fan discussion", "public opinion", "reddit"),
            PlannedQuery(f"{topic} critic review", "expert analysis", "reviews"),
            PlannedQuery(f"{topic} box office streaming", "commercial data", "news"),
            PlannedQuery(f"{topic} controversy backlash", "controversy", "social"),
            PlannedQuery(f"{topic} audience complaints", "conversion blockers", "public opinion"),
            *generic,
        ]
    if use_case == "public_current_event":
        return [
            PlannedQuery(f"{topic} official statement", "official sources", "official"),
            PlannedQuery(f"{topic} timeline events", "chronology", "news"),
            PlannedQuery(f"{topic} fact check", "fact check", "news"),
            PlannedQuery(f"{topic} public reaction", "public opinion", "social"),
            *generic,
        ]
    if use_case == "financial_market":
        return [
            PlannedQuery(f"{topic} stock analyst rating", "commercial data", "financial data"),
            PlannedQuery(f"{topic} earnings SEC filing", "official sources", "official"),
            PlannedQuery(f"{topic} investor sentiment", "public opinion", "social"),
            PlannedQuery(f"{topic} market analysis", "expert analysis", "financial news"),
            *generic,
        ]
    if use_case == "policy_civic":
        return [
            PlannedQuery(f"{topic} policy document", "official sources", "official"),
            PlannedQuery(f"{topic} legal analysis", "expert analysis", "news"),
            PlannedQuery(f"{topic} public comment", "public opinion", "social"),
            *generic,
        ]
    if use_case == "brand_product":
        return [
            PlannedQuery(f"{topic} customer reviews", "reviews", "reviews"),
            PlannedQuery(f"{topic} pricing competitors", "commercial data", "mixed"),
            PlannedQuery(f"{topic} support issues", "public opinion", "forum"),
            *generic,
        ]
    return generic
