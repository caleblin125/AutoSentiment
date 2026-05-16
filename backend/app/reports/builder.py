"""Build the final report JSON from stored evidence chunks.

Percentages and breakdowns are computed here in Python.
The 120B model receives pre-computed counts and writes only themes + narrative.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from urllib.parse import urlparse
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


ASPECT_KEYWORDS = {
    "cost": {"cost", "price", "pricing", "expensive", "cheap", "value", "afford", "fee", "fees"},
    "efficiency": {"efficient", "efficiency", "fast", "slow", "speed", "latency", "battery", "range"},
    "feasibility": {"feasible", "viable", "practical", "realistic", "possible", "deploy", "adoption"},
    "reliability": {"reliable", "reliability", "bug", "bugs", "failure", "broken", "quality", "issue"},
    "support": {"support", "service", "repair", "warranty", "help", "customer"},
    "safety": {"safe", "safety", "risk", "danger", "recall", "crash"},
    "trust": {"trust", "truth", "honest", "misleading", "accurate", "accuracy", "data", "source"},
    "policy": {"policy", "regulation", "legal", "law", "government", "approval", "ratings"},
}
STOP_WORDS = {
    "about", "after", "again", "against", "among", "and", "are", "because", "been", "being",
    "but", "can", "could", "from", "have", "into", "more", "over", "that", "the", "their",
    "them", "then", "there", "this", "very", "with", "would", "should", "while", "your",
}


def compute_aspects(chunks: list[EvidenceChunk], topic: str, limit: int = 8) -> list[dict]:
    """Summarize directional sentiment around recurring aspect keywords."""
    labels = [label.value for label in SentimentLabel]
    aspect_counts: dict[str, Counter] = defaultdict(Counter)

    for chunk in chunks:
        text = f"{chunk.summary} {chunk.snippet}".lower()
        for aspect, keywords in ASPECT_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                aspect_counts[aspect][str(chunk.label)] += 1

    for token, count in _topic_terms(topic, chunks).most_common(limit):
        if token not in aspect_counts and count >= 2:
            aspect_counts[token]["neutral"] += count

    aspects = []
    for aspect, counts in aspect_counts.items():
        total = sum(counts.values())
        if not total:
            continue
        dominant = max(labels, key=lambda label: counts[label])
        aspects.append(
            {
                "name": aspect,
                "sentiment": dominant,
                "count": total,
                "positive": counts["positive"] / total,
                "neutral": counts["neutral"] / total,
                "negative": counts["negative"] / total,
            }
        )

    return sorted(aspects, key=lambda item: item["count"], reverse=True)[:limit]


def compute_source_facts(chunks: list[EvidenceChunk], limit: int = 10) -> list[dict]:
    """Aggregate evidence domains so opinions can be traced back to source material."""
    by_domain: dict[str, Counter] = defaultdict(Counter)
    for chunk in chunks:
        domain = urlparse(chunk.url).netloc or "unknown"
        by_domain[domain]["count"] += 1
        by_domain[domain][str(chunk.label)] += 1
        by_domain[domain][str(chunk.source_type)] += 1

    facts = []
    for domain, counts in by_domain.items():
        labels = {label.value: counts[label.value] for label in SentimentLabel}
        source_type = max(
            (source.value for source in SourceType),
            key=lambda source: counts[source],
        )
        facts.append(
            {
                "domain": domain,
                "source_type": source_type,
                "count": counts["count"],
                "labels": labels,
            }
        )
    return sorted(facts, key=lambda item: item["count"], reverse=True)[:limit]


def build_idea_graph(topic: str, chunks: list[EvidenceChunk], themes: list[str], aspects: list[dict]) -> dict:
    """Build a small graph linking topic, sentiment, themes, aspects, sources, and evidence.

    Source nodes carry a representative URL and up to 5 example URLs so the
    frontend can render a clickable link list inside the node popover.
    """
    nodes = [{"id": "topic", "label": topic, "kind": "topic", "weight": max(1, len(chunks))}]
    edges = []

    for label in SentimentLabel:
        node_id = f"sentiment:{label.value}"
        count = sum(1 for chunk in chunks if str(chunk.label) == label.value)
        nodes.append({"id": node_id, "label": label.value, "kind": "sentiment", "weight": count})
        edges.append({"source": "topic", "target": node_id, "kind": "sentiment", "weight": count})

    for theme in themes[:6]:
        node_id = f"theme:{theme}"
        nodes.append({"id": node_id, "label": theme, "kind": "theme", "weight": 2})
        edges.append({"source": "topic", "target": node_id, "kind": "theme", "weight": 2})

    for aspect in aspects[:8]:
        node_id = f"aspect:{aspect['name']}"
        nodes.append({"id": node_id, "label": aspect["name"], "kind": "aspect", "weight": aspect["count"]})
        edges.append({"source": "topic", "target": node_id, "kind": "aspect", "weight": aspect["count"]})
        edges.append({"source": node_id, "target": f"sentiment:{aspect['sentiment']}", "kind": "direction", "weight": aspect["count"]})

    # Collect up to 5 representative URLs per domain for the link popover.
    domain_urls: dict[str, list[str]] = defaultdict(list)
    for chunk in chunks:
        domain = urlparse(chunk.url).netloc or "unknown"
        if len(domain_urls[domain]) < 5 and chunk.url not in domain_urls[domain]:
            domain_urls[domain].append(chunk.url)

    for fact in compute_source_facts(chunks, limit=8):
        domain = fact["domain"]
        node_id = f"source:{domain}"
        urls = domain_urls.get(domain, [])
        nodes.append({
            "id": node_id,
            "label": domain,
            "kind": "source",
            "weight": fact["count"],
            "url": urls[0] if urls else None,
            "urls": urls,
        })
        edges.append({"source": "topic", "target": node_id, "kind": "source", "weight": fact["count"]})

    return {"nodes": nodes, "edges": edges}


def _topic_terms(topic: str, chunks: list[EvidenceChunk]) -> Counter:
    text = " ".join([topic, *(chunk.summary for chunk in chunks)])
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", text.lower())
    return Counter(token for token in tokens if token not in STOP_WORDS)


async def build_report(chunks: list[EvidenceChunk], topic: str, *, settings: Settings) -> dict:
    """Assemble the full report dict (see SPEC.md §Report Structure).

    1. compute_counts — pure Python
    2. pick_top_quotes — pure Python
    3. synthesize_report (120B) — themes + narrative only
    """
    raise NotImplementedError
