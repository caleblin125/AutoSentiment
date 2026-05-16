"""Build the final report JSON from stored evidence chunks.

Percentages and breakdowns are computed here in Python.
The 120B model receives pre-computed counts and writes only themes + narrative.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
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
    "story": {"story", "plot", "writing", "script", "narrative", "ending", "character", "characters"},
    "casting": {"cast", "casting", "actor", "actress", "performance", "chemistry"},
    "pacing": {"pacing", "slow", "rushed", "drag", "boring", "runtime"},
    "gameplay": {"gameplay", "controls", "combat", "mechanics", "level", "missions"},
    "monetization": {"monetization", "microtransaction", "battle pass", "dlc", "paywall", "loot"},
    "marketing": {"trailer", "teaser", "campaign", "poster", "marketing", "promotion"},
    "fan trust": {"fans", "fandom", "trust", "betrayed", "canon", "adaptation"},
    "commercial potential": {"box office", "streaming", "sales", "preorder", "viewership", "ratings"},
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


MONTH_LOOKUP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def compute_timeline(chunks: list[EvidenceChunk], topic: str, limit: int = 8) -> dict:
    """Extract explicit dates from evidence and summarize the observed chronology.

    The function only uses dates present in text or retrieval timestamps. It does
    not infer missing event dates from model prose.
    """
    events: dict[str, dict] = {}
    for chunk in chunks:
        text = f"{chunk.summary}. {chunk.snippet}"
        dates = _extract_dates(text)
        if not dates and chunk.retrieved_at:
            dates = [(chunk.retrieved_at.date().isoformat(), "source retrieved")]
        for iso_date, source_text in dates:
            event = events.setdefault(
                iso_date,
                {
                    "date": iso_date,
                    "label": _event_label(text, topic),
                    "description": _event_description(chunk),
                    "evidence_ids": [],
                    "source_count": 0,
                    "certainty": "explicit" if source_text != "source retrieved" else "retrieved_at",
                    "source_text": source_text,
                },
            )
            event["source_count"] += 1
            if chunk.id not in event["evidence_ids"] and len(event["evidence_ids"]) < 5:
                event["evidence_ids"].append(chunk.id)

    ordered = sorted(events.values(), key=lambda item: item["date"])[:limit]
    start_date = ordered[0]["date"] if ordered else None
    end_date = ordered[-1]["date"] if ordered else None
    if ordered:
        event_summary = (
            f"Observed chronology for {topic} runs from {start_date} to {end_date}, "
            f"with {len(ordered)} dated evidence point{'s' if len(ordered) != 1 else ''}."
        )
    else:
        event_summary = "No explicit dates were found in the analyzed evidence."

    return {
        "start_date": start_date,
        "end_date": end_date,
        "important_dates": ordered,
        "event_summary": event_summary,
        "supporting_evidence_ids": [
            evidence_id
            for event in ordered
            for evidence_id in event["evidence_ids"]
        ][:12],
    }


def compute_claims(chunks: list[EvidenceChunk], limit: int = 10) -> dict:
    """Extract factual-looking claims and attach source/evidence signals.

    This is deliberately conservative: it groups repeated declarative
    statements and exposes corroboration signals without declaring truth.
    """
    grouped: dict[str, dict] = {}
    for chunk in chunks:
        for sentence in _claim_sentences(chunk.snippet):
            key = _normalize_claim(sentence)
            if not key:
                continue
            claim = grouped.setdefault(
                key,
                {
                    "claim": sentence,
                    "claim_type": _claim_type(sentence),
                    "confidence": 0.0,
                    "supporting_domains": [],
                    "opposing_domains": [],
                    "evidence_ids": [],
                    "source_types": [],
                    "needs_verification": False,
                },
            )
            domain = urlparse(chunk.url).netloc.removeprefix("www.") or "unknown"
            if domain not in claim["supporting_domains"]:
                claim["supporting_domains"].append(domain)
            if chunk.id not in claim["evidence_ids"]:
                claim["evidence_ids"].append(chunk.id)
            if chunk.source_type not in claim["source_types"]:
                claim["source_types"].append(chunk.source_type)

    claims = []
    for claim in grouped.values():
        corroboration = len(claim["supporting_domains"])
        directness = 1 if any(st in {"news", "web"} for st in claim["source_types"]) else 0
        claim["confidence"] = min(0.95, 0.35 + 0.15 * corroboration + 0.1 * directness)
        claim["needs_verification"] = corroboration < 2 and not any(
            domain.endswith((".gov", ".edu", ".org")) for domain in claim["supporting_domains"]
        )
        claims.append(claim)

    claims.sort(key=lambda item: (item["needs_verification"], -len(item["supporting_domains"])))
    return {
        "claims": claims[:limit],
        "needs_verification": [claim for claim in claims if claim["needs_verification"]][:limit],
        "summary": _claim_summary(claims),
    }


def compute_use_case_insights(
    chunks: list[EvidenceChunk],
    use_case: str,
    aspects: list[dict],
    fact_check: dict,
) -> dict:
    """Create mode-specific report sections for commercial and public workflows."""
    labels = Counter(str(chunk.label) for chunk in chunks)
    total = max(1, len(chunks))
    negative_share = labels["negative"] / total
    positive_share = labels["positive"] / total
    top_aspects = [aspect["name"] for aspect in aspects[:5]]
    needs_verification = len(fact_check.get("needs_verification", []))

    if use_case == "entertainment_product":
        sections = {
            "audience_pulse": _pulse_sentence(positive_share, negative_share),
            "critic_trade_pulse": _source_pulse(chunks, {"news", "web"}),
            "fandom_concerns": _aspect_sentence(top_aspects, fallback="No recurring fandom concerns identified."),
            "conversion_blockers": _aspect_sentence(
                [a["name"] for a in aspects if a["sentiment"] == "negative"][:4],
                fallback="No major conversion blockers were detected.",
            ),
            "launch_risks": _risk_sentence(negative_share, needs_verification),
            "recommended_monitoring_queries": [
                "trailer reaction",
                "audience complaints",
                "critic review",
                "box office streaming ratings",
            ],
        }
    elif use_case == "public_current_event":
        sections = {
            "what_is_known": fact_check.get("summary", "No factual claims extracted."),
            "what_is_disputed": f"{needs_verification} extracted claim(s) need additional verification.",
            "what_is_opinion": _aspect_sentence(top_aspects, fallback="No recurring opinion themes identified."),
            "what_changed_recently": "Use the chronology section to inspect dated developments and source links.",
            "source_warning": _source_warning(chunks),
        }
    else:
        sections = {
            "audience_pulse": _pulse_sentence(positive_share, negative_share),
            "key_drivers": _aspect_sentence(top_aspects, fallback="No dominant drivers identified."),
            "verification_notes": f"{needs_verification} claim(s) need additional verification.",
        }

    return {"use_case": use_case, "sections": sections}


def compute_chart_data(chunks: list[EvidenceChunk], aspects: list[dict], fact_check: dict) -> dict:
    labels = [label.value for label in SentimentLabel]
    source_mix = Counter(str(chunk.source_type) for chunk in chunks)
    sentiment_by_date: dict[str, Counter] = defaultdict(Counter)
    for chunk in chunks:
        date = chunk.retrieved_at.date().isoformat() if chunk.retrieved_at else "unknown"
        sentiment_by_date[date][str(chunk.label)] += 1

    return {
        "source_mix": [
            {"source_type": source, "count": count}
            for source, count in source_mix.most_common()
        ],
        "sentiment_over_time": [
            {
                "date": date,
                **{label: counts[label] for label in labels},
                "total": sum(counts.values()),
            }
            for date, counts in sorted(sentiment_by_date.items())
        ],
        "aspect_matrix": [
            {
                "aspect": aspect["name"],
                "positive": aspect["positive"],
                "neutral": aspect["neutral"],
                "negative": aspect["negative"],
                "count": aspect["count"],
            }
            for aspect in aspects
        ],
        "claim_corroboration": [
            {
                "claim": claim["claim"],
                "supporting_sources": len(claim["supporting_domains"]),
                "needs_verification": claim["needs_verification"],
            }
            for claim in fact_check.get("claims", [])
        ],
    }


def _extract_dates(text: str) -> list[tuple[str, str]]:
    dates: list[tuple[str, str]] = []
    for match in re.finditer(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b", text):
        year, month, day = match.groups()
        dates.append((f"{int(year):04d}-{int(month):02d}-{int(day):02d}", match.group(0)))
    month_names = "|".join(MONTH_LOOKUP.keys())
    pattern = rf"\b({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,\s*|\s+)(20\d{{2}})\b"
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        month_name, day, year = match.groups()
        month = MONTH_LOOKUP[month_name.lower()]
        dates.append((f"{int(year):04d}-{month:02d}-{int(day):02d}", match.group(0)))
    seen = set()
    deduped = []
    for iso, source in dates:
        if iso in seen:
            continue
        try:
            datetime.fromisoformat(iso)
        except ValueError:
            continue
        seen.add(iso)
        deduped.append((iso, source))
    return deduped


def _claim_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    factual_markers = re.compile(
        r"\b(is|are|was|were|has|have|had|will|reported|announced|released|launched|costs?|priced|increased|decreased)\b|[$%]|\b\d{4}\b",
        re.IGNORECASE,
    )
    claims = []
    for sentence in sentences:
        cleaned = " ".join(sentence.split())
        if 35 <= len(cleaned) <= 240 and factual_markers.search(cleaned):
            claims.append(cleaned)
    return claims[:3]


def _normalize_claim(sentence: str) -> str:
    words = re.findall(r"[a-zA-Z0-9$%]+", sentence.lower())
    meaningful = [w for w in words if w not in STOP_WORDS]
    return " ".join(meaningful[:18])


def _claim_type(sentence: str) -> str:
    lowered = sentence.lower()
    if any(token in lowered for token in ("$", "%", "price", "cost", "revenue", "box office", "sales")):
        return "quantitative"
    if any(token in lowered for token in ("announced", "released", "launched", "reported")):
        return "event"
    return "factual"


def _claim_summary(claims: list[dict]) -> str:
    if not claims:
        return "No factual-looking claims were extracted from the evidence."
    needs = sum(1 for claim in claims if claim["needs_verification"])
    return f"Extracted {len(claims)} factual-looking claims; {needs} need additional verification."


def _pulse_sentence(positive_share: float, negative_share: float) -> str:
    if negative_share >= 0.5:
        return "Audience pulse is predominantly negative and should be treated as a risk signal."
    if positive_share >= 0.5:
        return "Audience pulse is predominantly positive and can support confident positioning."
    return "Audience pulse is mixed; investigate the strongest directional topics before acting."


def _source_pulse(chunks: list[EvidenceChunk], source_types: set[str]) -> str:
    scoped = [chunk for chunk in chunks if chunk.source_type in source_types]
    if not scoped:
        return "No critic, trade, or established web sources were captured in this run."
    labels = Counter(str(chunk.label) for chunk in scoped)
    dominant = labels.most_common(1)[0][0]
    return f"{len(scoped)} critic/trade/web item(s) captured; dominant sentiment is {dominant}."


def _aspect_sentence(aspects: list[str], fallback: str) -> str:
    if not aspects:
        return fallback
    return "Key recurring topics: " + ", ".join(aspects) + "."


def _risk_sentence(negative_share: float, needs_verification: int) -> str:
    risks = []
    if negative_share >= 0.4:
        risks.append("high negative sentiment")
    if needs_verification:
        risks.append(f"{needs_verification} unverified factual claim(s)")
    return ", ".join(risks).capitalize() + "." if risks else "No severe launch risk signal detected."


def _source_warning(chunks: list[EvidenceChunk]) -> str:
    if not chunks:
        return "No sources were analyzed."
    social_count = sum(1 for chunk in chunks if chunk.source_type in {"reddit", "social", "forum"})
    if social_count / len(chunks) > 0.75:
        return "Most evidence comes from social/community sources; verify key claims against primary sources."
    return "Source mix includes non-social evidence, but primary-source verification is still recommended."


def _event_label(text: str, topic: str) -> str:
    cleaned = re.sub(re.escape(topic), "", text, flags=re.IGNORECASE).strip(" .")
    sentence = re.split(r"(?<=[.!?])\s+", cleaned)[0] if cleaned else topic
    return sentence[:90] + ("…" if len(sentence) > 90 else "")


def _event_description(chunk: EvidenceChunk) -> str:
    return chunk.summary[:140] + ("…" if len(chunk.summary) > 140 else "")


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
