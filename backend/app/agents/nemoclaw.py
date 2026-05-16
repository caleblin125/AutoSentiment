"""Nemoclaw — orchestrator model that organizes what to search and how to process it.

Nemoclaw does not replace the search API or httpx fetch; it produces a structured
`ResearchPlan` (sub-questions, search program, processing order) that downstream
code and the **lightweight model queue** execute.

In the **Hack-a-Claw / NemoClaw** environment, this corresponds to the **high-capability
planning route** configured during NemoClaw onboarding (`NEMCLAW_MODEL`). See
`docs/HACKATHON_ENV.md`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.types import ResearchPlan

if TYPE_CHECKING:
    from app.core.config import Settings


async def structure_research_plan(
    user_query: str,
    *,
    run_id: str,
    settings: Settings,
) -> ResearchPlan:
    """Call Nemoclaw (`settings.nemoclaw_model`) to structure the run.

    Implement LLM invocation, JSON grounding, and validation here. Until then,
    return a minimal deterministic plan so the pipeline can be wired.
    """
    del run_id, settings
    return ResearchPlan(
        sub_questions=[user_query],
        search_program=[user_query],
        processing_order=["discover", "ingest", "retrieve", "synthesize"],
        notes_for_light_tier={},
    )
