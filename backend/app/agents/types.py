"""Shared structures for Nemoclaw planning and downstream stages."""

from dataclasses import dataclass, field
from enum import StrEnum


class LightJobKind(StrEnum):
    """Kinds of work dispatched to the lightweight model tier (search-adjacent, cheap)."""

    SEARCH_QUERY_EXPAND = "search_query_expand"
    SERP_INTENT_OR_CLASSIFY = "serp_intent_or_classify"
    SNIPPET_RELEVANCE_SCORE = "snippet_relevance_score"
    CHUNK_QUICK_FILTER = "chunk_quick_filter"


@dataclass
class ResearchPlan:
    """What Nemoclaw decides should be searched and how processing is structured.

    Nemoclaw fills this; ingest/retrieve/report stages consume it. Field names are
    illustrative — adjust to your API contract as you implement.
    """

    sub_questions: list[str]
    """Focused research slices derived from the user question."""

    search_program: list[str]
    """High-level search angles or seed queries (may be expanded by lightweight models)."""

    processing_order: list[str] = field(default_factory=list)
    """Ordered stage identifiers, e.g. discover → ingest → retrieve → synthesize."""

    notes_for_light_tier: dict[str, str] = field(default_factory=dict)
    """Optional hints passed into lightweight jobs (limits, languages, domains)."""
