"""Agent entrypoint — Nemoclaw structures the run; lightweight models handle search-tier LLM tasks.

Intended flow (implement `run_research` per `agents/IMPLEMENTATION.md`):

1. **Nemoclaw** — `structure_research_plan(...)` → `ResearchPlan` (what to search, sub-questions, order).
2. **Lightweight queue** — `LightweightModelQueue.run(...)` for query expansion, snippet scoring, quick relevance filters.
3. **Tools** — search API + `httpx` fetch (no LLM required).
4. **Retrieve / report** — optionally more lightweight calls; final report may call Nemoclaw again for synthesis quality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.light_queue import LightweightModelQueue
from app.agents.nemoclaw import structure_research_plan
from app.agents.types import LightJobKind

if TYPE_CHECKING:
    from app.core.config import Settings


async def run_research(run_id: str, user_query: str, settings: Settings) -> None:
    """End-to-end research run: plan with Nemoclaw, then execute via tools + light tier."""
    plan = await structure_research_plan(user_query, run_id=run_id, settings=settings)
    queue = LightweightModelQueue(settings)

    for seed in plan.search_program[:3]:
        await queue.run(LightJobKind.SEARCH_QUERY_EXPAND, {"seed": seed, "plan": plan})

    # TODO: use plan.sub_questions + expanded queries for discover → ingest → retrieve;
    #       emit SSE events; call reports (optionally Nemoclaw again for final synthesis).
