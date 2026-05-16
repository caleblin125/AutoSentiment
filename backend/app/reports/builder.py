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


_CREDIBLE_DOMAINS = frozenset({
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com",
    "wsj.com", "bloomberg.com", "ft.com", "theguardian.com", "economist.com",
    "nature.com", "science.org", "sciencedirect.com", "pubmed.ncbi.nlm.nih.gov",
    "who.int", "cdc.gov", "europa.eu", "un.org",
    "mit.edu", "stanford.edu", "harvard.edu", "ieee.org", "acm.org",
})


def _is_credible(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.removeprefix("www.")
        return domain in _CREDIBLE_DOMAINS or any(domain.endswith(f".{d}") for d in _CREDIBLE_DOMAINS)
    except Exception:
        return False


def pick_top_quotes(chunks: list[EvidenceChunk], label: SentimentLabel, n: int = 5) -> list[dict]:
    """Return up to n quote dicts for the label, credible sources first."""
    matching = [c for c in chunks if str(c.label) == label.value]
    # Sort credible sources first so they appear at the top of the report.
    matching.sort(key=lambda c: (0 if _is_credible(c.url) else 1))
    return [
        {"summary": chunk.summary, "evidence_id": chunk.id, "url": chunk.url,
         "credible": _is_credible(chunk.url)}
        for chunk in matching[:n]
    ]


ASPECT_KEYWORDS = {
    "cost": {"cost", "price", "pricing", "expensive", "cheap", "value", "afford", "fee", "fees", "budget", "pay", "paid"},
    "efficiency": {"efficient", "efficiency", "fast", "slow", "speed", "latency", "battery", "range", "performance", "throughput"},
    "feasibility": {"feasible", "viable", "practical", "realistic", "possible", "deploy", "adoption", "implement"},
    "reliability": {"reliable", "reliability", "bug", "bugs", "failure", "broken", "quality", "issue", "issues", "crash", "flaw"},
    "support": {"support", "service", "repair", "warranty", "help", "customer", "helpdesk", "refund"},
    "safety": {"safe", "safety", "risk", "danger", "recall", "hazard", "secure", "security", "injury"},
    "trust": {"trust", "truth", "honest", "misleading", "accurate", "accuracy", "data", "source", "credible", "fake"},
    "policy": {"policy", "regulation", "legal", "law", "government", "approval", "ratings", "compliance", "ban"},
    "design": {"design", "style", "aesthetic", "look", "appearance", "ergonomic", "build", "material"},
    "innovation": {"innovative", "innovation", "technology", "cutting-edge", "breakthrough", "novel", "advanced"},
    "availability": {"available", "availability", "stock", "supply", "shortage", "delivery", "access", "global"},
    "competition": {"competitor", "competition", "rival", "alternative", "versus", "compared", "better", "worse"},
    "environment": {"environment", "environmental", "sustainable", "carbon", "green", "emission", "climate", "eco"},
    "usability": {"usable", "usability", "intuitive", "interface", "experience", "difficult", "complex", "simple"},
}

# Comprehensive English stop words — single tokens that carry no semantic signal.
STOP_WORDS: frozenset[str] = frozenset({
    # Articles / determiners
    "the", "a", "an", "this", "that", "these", "those", "its", "our", "their",
    "his", "her", "him", "she", "they", "them", "we", "you", "your", "ours",
    # Prepositions / conjunctions
    "for", "and", "but", "nor", "not", "yet", "so", "in", "on", "at", "to",
    "by", "of", "or", "as", "if", "is", "it", "be", "do", "go", "up", "out",
    "off", "via", "per", "vs", "etc", "i.e", "e.g",
    # Common verbs
    "are", "was", "were", "been", "has", "had", "have", "will", "would", "could",
    "should", "may", "might", "must", "can", "did", "does", "do", "get", "got",
    "use", "used", "make", "made", "say", "said", "see", "seen", "know", "went",
    "come", "came", "take", "took", "give", "gave", "let", "set", "put", "seem",
    "look", "keep", "show", "told", "feel", "try", "turn", "start", "keep",
    # Adverbs / adjectives (generic)
    "very", "just", "more", "most", "also", "even", "still", "back", "only",
    "then", "than", "when", "well", "here", "there", "where", "too", "now",
    "how", "why", "who", "what", "all", "any", "few", "new", "old", "big",
    "good", "bad", "one", "two", "own", "other", "such", "same", "much",
    "many", "some", "both", "each", "next", "last", "long", "high", "low",
    # Transitions / fillers
    "about", "after", "again", "against", "among", "because", "being", "could",
    "from", "from", "have", "into", "over", "that", "with", "while", "though",
    "although", "however", "therefore", "instead", "through", "between",
    "during", "before", "after", "since", "until", "unless", "without",
    "within", "along", "across", "around", "behind", "below", "above",
    # Opinion filler words
    "think", "really", "actually", "basically", "literally", "honestly",
    "definitely", "probably", "generally", "simply", "quite", "rather",
    "pretty", "maybe", "perhaps", "often", "never", "always", "every",
    # Short words that slip through the length filter
    "the", "and", "for", "not", "but", "nor", "yet",
})


def compute_aspects(chunks: list[EvidenceChunk], topic: str, limit: int = 8) -> list[dict]:
    """Summarize directional sentiment around recurring aspect keywords.

    Each returned aspect includes the top evidence IDs so the frontend can
    show a detail modal with source links when the node is clicked.
    """
    labels = [label.value for label in SentimentLabel]
    aspect_counts: dict[str, Counter] = defaultdict(Counter)
    aspect_evidence: dict[str, list[str]] = defaultdict(list)

    # Topic words are filtered out from free-form token discovery.
    topic_tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", topic.lower()))

    for chunk in chunks:
        text = f"{chunk.summary} {chunk.snippet}".lower()
        for aspect, keywords in ASPECT_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                aspect_counts[aspect][str(chunk.label)] += 1
                # Keep up to 5 evidence IDs per aspect for the detail popover.
                if len(aspect_evidence[aspect]) < 5:
                    aspect_evidence[aspect].append(chunk.id)

    for token, count in _topic_terms(topic, chunks).most_common(limit * 2):
        # Skip: in STOP_WORDS, short tokens (≤4 chars), or topic name words.
        if token in STOP_WORDS or len(token) <= 4 or token in topic_tokens:
            continue
        if token not in aspect_counts and count >= 2:
            aspect_counts[token]["neutral"] += count
            aspect_evidence[token] = [
                c.id for c in chunks
                if token in f"{c.summary} {c.snippet}".lower()
            ][:5]

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
                "evidence_ids": aspect_evidence.get(aspect, []),
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
        # Find chunks that mention this theme keyword in their summary.
        theme_evidence = [
            c.id for c in chunks
            if theme.lower() in f"{c.summary} {c.snippet}".lower()
        ][:5]
        nodes.append({
            "id": node_id,
            "label": theme,
            "kind": "theme",
            "weight": max(2, len(theme_evidence)),
            "evidence_ids": theme_evidence,
        })
        edges.append({"source": "topic", "target": node_id, "kind": "theme", "weight": 2})

    for aspect in aspects[:8]:
        node_id = f"aspect:{aspect['name']}"
        nodes.append({
            "id": node_id,
            "label": aspect["name"],
            "kind": "aspect",
            "weight": aspect["count"],
            "evidence_ids": aspect.get("evidence_ids", []),
        })
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
    """Extract candidate topic tokens from chunk summaries (not the topic itself)."""
    # Only scan chunk summaries — the topic words would trivially dominate otherwise.
    text = " ".join(chunk.summary for chunk in chunks)
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{3,}", text.lower())  # 5+ chars minimum
    return Counter(token for token in tokens if token not in STOP_WORDS)


async def build_report(chunks: list[EvidenceChunk], topic: str, *, settings: Settings) -> dict:
    """Assemble the full report dict (see SPEC.md §Report Structure).

    1. compute_counts — pure Python
    2. pick_top_quotes — pure Python
    3. synthesize_report (120B) — themes + narrative only
    """
    raise NotImplementedError
