"""Build the final report JSON from stored evidence chunks.

Percentages and breakdowns are computed here in Python.
The 120B model receives pre-computed counts and writes only themes + narrative.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.types import SentimentLabel, SourceType
from app.models import EvidenceChunk

if TYPE_CHECKING:
    from app.core.config import Settings


def compute_counts(chunks: list[EvidenceChunk]) -> dict:
    """Return overall and by_source percentage breakdowns. No LLM involved."""
    labels = [label.value for label in SentimentLabel]
    sources = [source.value for source in SourceType]
    total = len(chunks)

    overall_counts = dict.fromkeys(labels, 0)
    source_counts = {
        source: {
            "count": 0,
            **dict.fromkeys(labels, 0),
        }
        for source in sources
    }

    for chunk in chunks:
        label = str(chunk.label)
        source_type = str(chunk.source_type)

        if label in overall_counts:
            overall_counts[label] += 1

        if source_type in source_counts:
            source_counts[source_type]["count"] += 1
            if label in source_counts[source_type]:
                source_counts[source_type][label] += 1

    overall = {
        label: (overall_counts[label] / total if total else 0.0)
        for label in labels
    }
    overall["total"] = total

    by_source = {}
    for source_type, counts in source_counts.items():
        count = counts["count"]
        by_source[source_type] = {
            label: (counts[label] / count if count else 0.0)
            for label in labels
        }
        by_source[source_type]["count"] = count

    return {"overall": overall, "by_source": by_source}


def pick_top_quotes(chunks: list[EvidenceChunk], label: SentimentLabel, n: int = 5) -> list[dict]:
    """Return up to n {summary, evidence_id, url} dicts for the given label."""
    return [
        {"summary": chunk.summary, "evidence_id": chunk.id, "url": chunk.url}
        for chunk in chunks
        if str(chunk.label) == label.value
    ][:n]


async def build_report(chunks: list[EvidenceChunk], topic: str, *, settings: Settings) -> dict:
    """Assemble the full report dict (see SPEC.md §Report Structure).

    1. compute_counts — pure Python
    2. pick_top_quotes — pure Python
    3. synthesize_report (120B) — themes + narrative only
    """
    raise NotImplementedError
