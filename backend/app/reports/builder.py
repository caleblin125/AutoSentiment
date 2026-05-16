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

_HIGH_CREDIBILITY = frozenset({
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com",
    "wsj.com", "bloomberg.com", "ft.com", "economist.com",
    "nature.com", "science.org", "who.int", "cdc.gov",
})

_MEDIUM_CREDIBILITY = frozenset({
    "theguardian.com", "cnn.com", "washingtonpost.com", "politico.com",
    "npr.org", "aljazeera.com", "dw.com", "techcrunch.com",
    "theverge.com", "wired.com", "arstechnica.com",
    "sciencedirect.com", "pubmed.ncbi.nlm.nih.gov", "europa.eu", "un.org",
    "mit.edu", "stanford.edu", "harvard.edu", "ieee.org", "acm.org",
    "marketwatch.com", "cnbc.com", "investopedia.com", "barrons.com",
})


def _credibility_score(url: str) -> float:
    """Return a 0-1 credibility score based on domain reputation and signals."""
    try:
        domain = urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return 0.0
    if domain in _HIGH_CREDIBILITY or any(domain.endswith(f".{d}") for d in _HIGH_CREDIBILITY):
        return 0.95
    if domain in _MEDIUM_CREDIBILITY or any(domain.endswith(f".{d}") for d in _MEDIUM_CREDIBILITY):
        return 0.75
    if domain.endswith((".gov", ".edu")):
        return 0.85
    if domain.endswith(".org"):
        return 0.55
    # Social/forum domains get lower base scores.
    if any(s in domain for s in ("reddit", "twitter", "x.com", "facebook", "tiktok", "quora")):
        return 0.25
    if any(s in domain for s in ("youtube", "twitch", "medium", "substack")):
        return 0.35
    return 0.50  # Unknown domain: neutral.


def _is_credible(url: str) -> bool:
    return _credibility_score(url) >= 0.70


def pick_top_quotes(
    chunks: list[EvidenceChunk],
    label: SentimentLabel,
    n: int = 5,
    confidence_map: dict[str, float] | None = None,
) -> list[dict]:
    """Return up to n quote dicts for the label.

    Ranking: credible sources first, then higher confidence, then insertion order.
    """
    conf = confidence_map or {}
    matching = [c for c in chunks if str(c.label) == label.value]
    matching.sort(key=lambda c: (0 if _is_credible(c.url) else 1, -(conf.get(c.id, 0.8))))
    return [
        {
            "summary": chunk.summary,
            "evidence_id": chunk.id,
            "url": chunk.url,
            "credible": _is_credible(chunk.url),
            "confidence": round(conf.get(chunk.id, 0.8), 2),
        }
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
        first_url = next((c.url for c in chunks if urlparse(c.url).netloc == domain), f"https://{domain}")
        urls = []
        for chunk in chunks:
            if urlparse(chunk.url).netloc == domain and chunk.url not in urls:
                urls.append(chunk.url)
            if len(urls) >= 8:
                break
        facts.append(
            {
                "domain": domain,
                "source_type": source_type,
                "count": counts["count"],
                "labels": labels,
                "credibility": round(_credibility_score(first_url), 2),
                "urls": urls,
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
        for iso_date, source_text in dates:
            event = events.setdefault(
                iso_date,
                {
                    "date": iso_date,
                    "label": _event_label(text, topic),
                    "description": _event_description(chunk),
                    "evidence_ids": [],
                    "source_count": 0,
                    "certainty": "explicit",
                    "source_text": source_text,
                    "_score": 0.0,
                },
            )
            event["source_count"] += 1
            event["_score"] += _event_relevance(chunk, topic)
            if chunk.id not in event["evidence_ids"] and len(event["evidence_ids"]) < 5:
                event["evidence_ids"].append(chunk.id)

    relevant = sorted(events.values(), key=lambda item: (-item["_score"], item["date"]))[:limit]
    ordered = sorted(relevant, key=lambda item: item["date"])
    for event in ordered:
        event.pop("_score", None)
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


def _event_relevance(chunk: EvidenceChunk, topic: str) -> float:
    text = f"{chunk.summary} {chunk.snippet}".lower()
    score = 1.0
    score += sum(1 for token in topic.lower().split() if len(token) > 2 and token in text) * 0.6
    score += _credibility_score(chunk.url)
    if re.search(r"\b(announced|released|launched|reported|filed|published|confirmed|delayed|cancelled|approved|recalled)\b", text):
        score += 1.0
    if re.search(r"[$%]|\b\d{2,}\b", text):
        score += 0.4
    return score


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
                    "supporting_urls": [],
                    "opposing_domains": [],
                    "evidence_ids": [],
                    "source_types": [],
                    "needs_verification": False,
                },
            )
            domain = urlparse(chunk.url).netloc.removeprefix("www.") or "unknown"
            if domain not in claim["supporting_domains"]:
                claim["supporting_domains"].append(domain)
            if chunk.url not in claim["supporting_urls"] and len(claim["supporting_urls"]) < 5:
                claim["supporting_urls"].append(chunk.url)
            if chunk.id not in claim["evidence_ids"]:
                claim["evidence_ids"].append(chunk.id)
            if chunk.source_type not in claim["source_types"]:
                claim["source_types"].append(chunk.source_type)

    claims = []
    for claim in grouped.values():
        corroboration = len(claim["supporting_domains"])
        directness = 1 if any(st in {"news", "web"} for st in claim["source_types"]) else 0
        # Weight credibility by the best supporting source.
        best_cred = max((_credibility_score(f"https://{d}") for d in claim["supporting_domains"]), default=0.35)
        claim["confidence"] = round(min(0.95, 0.2 + 0.15 * corroboration + 0.1 * directness + 0.15 * best_cred), 2)
        claim["needs_verification"] = corroboration < 2 and not any(
            domain.endswith((".gov", ".edu", ".org")) for domain in claim["supporting_domains"]
        ) and best_cred < 0.6
        claim["best_source_credibility"] = round(best_cred, 2)
        claims.append(claim)

    claims.sort(key=lambda item: (item["needs_verification"], -len(item["supporting_domains"])))
    contradictions = _find_contradictions(chunks, limit=6)
    return {
        "claims": claims[:limit],
        "needs_verification": [claim for claim in claims if claim["needs_verification"]][:limit],
        "contradictions": contradictions,
        "summary": _claim_summary(claims, contradictions),
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
    elif use_case == "financial_market":
        sections = {
            "market_pulse": _pulse_sentence(positive_share, negative_share),
            "key_drivers": _aspect_sentence(top_aspects, fallback="No dominant market themes identified."),
            "analyst_sentiment": _source_pulse(chunks, {"news", "web"}),
            "retail_sentiment": _source_pulse(chunks, {"reddit", "social", "forum"}),
            "risk_signals": _risk_sentence(negative_share, needs_verification),
            "verification_notes": f"{needs_verification} claim(s) need verification against SEC filings and primary financial data.",
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
    date_certainty: dict[str, Counter] = defaultdict(Counter)
    for chunk in chunks:
        date, certainty = _chunk_source_date(chunk)
        sentiment_by_date[date][str(chunk.label)] += 1
        date_certainty[date][certainty] += 1

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
                "certainty": date_certainty[date].most_common(1)[0][0],
            }
            for date, counts in sorted(sentiment_by_date.items())
        ],
        "location_sentiment": compute_location_sentiment(chunks),
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


def _chunk_source_date(chunk: EvidenceChunk) -> tuple[str, str]:
    """Return the best available source date and the certainty behind it."""
    dates = _extract_dates(f"{chunk.summary}. {chunk.snippet}")
    if dates:
        return dates[0][0], "explicit"
    if chunk.retrieved_at:
        return chunk.retrieved_at.date().isoformat(), "retrieved_at"
    return "unknown", "unknown"


_LOCATION_GAZETTEER = {
    "united states": (39.8, -98.6, ("united states", "u.s.", "us ", "usa", "america", "american")),
    "canada": (56.1, -106.3, ("canada", "canadian")),
    "united kingdom": (54.0, -2.5, ("united kingdom", "uk", "britain", "british", "london")),
    "europe": (50.1, 14.4, ("europe", "european", "eu ")),
    "china": (35.9, 104.2, ("china", "chinese", "beijing", "shanghai")),
    "japan": (36.2, 138.3, ("japan", "japanese", "tokyo")),
    "south korea": (36.5, 127.8, ("south korea", "korea", "korean", "seoul")),
    "india": (20.6, 78.9, ("india", "indian", "delhi", "mumbai")),
    "australia": (-25.3, 133.8, ("australia", "australian", "sydney", "melbourne")),
    "germany": (51.2, 10.5, ("germany", "german", "berlin")),
    "france": (46.2, 2.2, ("france", "french", "paris")),
    "brazil": (-14.2, -51.9, ("brazil", "brazilian")),
    "california": (36.8, -119.4, ("california",)),
    "new york": (43.0, -75.0, ("new york", "nyc")),
    "texas": (31.0, -99.9, ("texas", "houston", "austin", "dallas")),
}

_TLD_LOCATION_HINTS = {
    ".uk": "united kingdom",
    ".ca": "canada",
    ".au": "australia",
    ".jp": "japan",
    ".de": "germany",
    ".fr": "france",
    ".br": "brazil",
    ".in": "india",
    ".kr": "south korea",
    ".cn": "china",
}


def compute_location_sentiment(chunks: list[EvidenceChunk]) -> list[dict]:
    """Aggregate sentiment by mentioned or source-inferred geography.

    Location extraction is deliberately conservative. Direct text mentions get
    higher certainty; domain country-code hints are retained as low-certainty
    source-origin signals for the map.
    """
    buckets: dict[str, dict] = {}
    labels = [label.value for label in SentimentLabel]

    def ensure(location: str, certainty: str) -> dict:
        lat, lon, _aliases = _LOCATION_GAZETTEER[location]
        bucket = buckets.setdefault(location, {
            "location": location.title(),
            "lat": lat,
            "lon": lon,
            "certainty": certainty,
            "evidence_ids": [],
            "source_domains": [],
            **{label: 0 for label in labels},
        })
        if bucket["certainty"] != "mentioned" and certainty == "mentioned":
            bucket["certainty"] = certainty
        return bucket

    for chunk in chunks:
        text = f" {chunk.summary} {chunk.snippet} ".lower()
        domain = urlparse(chunk.url).netloc.removeprefix("www.").lower()
        matches: set[tuple[str, str]] = set()
        for location, (_lat, _lon, aliases) in _LOCATION_GAZETTEER.items():
            if any(re.search(rf"\b{re.escape(alias.strip())}\b", text) for alias in aliases):
                matches.add((location, "mentioned"))
        if not matches:
            for suffix, location in _TLD_LOCATION_HINTS.items():
                if domain.endswith(suffix):
                    matches.add((location, "source_domain"))
                    break
        for location, certainty in matches:
            bucket = ensure(location, certainty)
            label = str(chunk.label)
            if label in labels:
                bucket[label] += 1
            if chunk.id not in bucket["evidence_ids"]:
                bucket["evidence_ids"].append(chunk.id)
            if domain and domain not in bucket["source_domains"]:
                bucket["source_domains"].append(domain)

    results = []
    for bucket in buckets.values():
        total = sum(bucket[label] for label in labels)
        # Require at least 2 evidence items to filter noise — a single
        # mention of "California" in a globally-focused article shouldn't
        # create a map dot.
        if total < 2:
            continue
        # TLD-only matches (no text mention) need higher bar.
        if bucket["certainty"] == "source_domain" and total < 3:
            continue
        results.append({
            **bucket,
            "total": total,
            "evidence_ids": bucket["evidence_ids"][:8],
            "source_domains": bucket["source_domains"][:6],
        })
    return sorted(results, key=lambda row: row["total"], reverse=True)[:12]


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


def _find_contradictions(chunks: list[EvidenceChunk], limit: int = 6) -> list[dict]:
    """Detect opposing claims about the same subject from different evidence chunks.

    Strategy: group chunks by a shared 3–5-token noun phrase extracted from their
    summary. If the same phrase appears in both positive and negative chunks, it is a
    contradiction candidate. The pair with the most domain diversity is surfaced first.
    """
    from collections import defaultdict

    # Map subject_key → {label → [(chunk, summary)]}
    groups: dict[str, dict[str, list[tuple[EvidenceChunk, str]]]] = defaultdict(lambda: {"positive": [], "negative": []})

    for chunk in chunks:
        label = str(chunk.label)
        if label not in ("positive", "negative"):
            continue
        text = (chunk.summary or "").lower()
        # Extract meaningful 2–3-grams as subject keys.
        tokens = [w for w in re.findall(r"[a-z]{3,}", text) if w not in STOP_WORDS]
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]} {tokens[i + 1]}"
            groups[bigram][label].append((chunk, chunk.summary or ""))

    contradictions = []
    seen_pairs: set[tuple[str, str]] = set()

    for key, polarity_map in groups.items():
        pos_items = polarity_map["positive"]
        neg_items = polarity_map["negative"]
        if not pos_items or not neg_items:
            continue

        # Pick the most credible representative from each side.
        best_pos = max(pos_items, key=lambda t: _credibility_score(t[0].url))
        best_neg = max(neg_items, key=lambda t: _credibility_score(t[0].url))

        # Deduplicate: skip if both evidence IDs were already part of a contradiction.
        pair_key = tuple(sorted([best_pos[0].id, best_neg[0].id]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        pos_domains = list({urlparse(t[0].url).netloc.removeprefix("www.") for t in pos_items})[:3]
        neg_domains = list({urlparse(t[0].url).netloc.removeprefix("www.") for t in neg_items})[:3]
        contradictions.append({
            "subject": key,
            "positive_claim": best_pos[1],
            "negative_claim": best_neg[1],
            "positive_evidence_id": best_pos[0].id,
            "negative_evidence_id": best_neg[0].id,
            "positive_domains": pos_domains,
            "negative_domains": neg_domains,
            "strength": len(pos_items) + len(neg_items),
        })

    # Surface the strongest (most mentions on both sides) contradictions first.
    contradictions.sort(key=lambda c: -c["strength"])
    return contradictions[:limit]


def _claim_summary(claims: list[dict], contradictions: list[dict] | None = None) -> str:
    if not claims:
        return "No factual-looking claims were extracted from the evidence."
    needs = sum(1 for claim in claims if claim["needs_verification"])
    n_contradictions = len(contradictions) if contradictions else 0
    suffix = f" {n_contradictions} contradiction{'s' if n_contradictions != 1 else ''} detected." if n_contradictions else ""
    return f"Extracted {len(claims)} factual-looking claims; {needs} need additional verification.{suffix}"


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


def compute_threads(chunks: list[EvidenceChunk], topic: str, limit: int = 12) -> list[dict]:
    """Extract fine-grain recurring topic threads from evidence.

    Each thread is a cluster of related phrases that appear across multiple
    sources. Threads carry temporal provenance (when they appeared), source
    diversity, and sentiment distribution so users can trace how opinions
    evolved and click any thread to launch a deeper search.
    """
    # Build 2-gram and 3-gram frequency map from all evidence.
    topic_lower = topic.lower()
    topic_tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", topic_lower))
    ngram_map: dict[str, Counter] = defaultdict(Counter)
    ngram_docs: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        text = f"{chunk.summary} {chunk.snippet}".lower()
        tokens = [t for t in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", text)
                  if t not in STOP_WORDS and t not in topic_tokens]
        phrases: set[str] = set()
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]} {tokens[i + 1]}"
            if 8 <= len(bigram) <= 60:
                phrases.add(bigram)
        for i in range(len(tokens) - 2):
            trigram = f"{tokens[i]} {tokens[i + 1]} {tokens[i + 2]}"
            if 12 <= len(trigram) <= 80:
                phrases.add(trigram)
        for phrase in phrases:
            ngram_map[phrase][str(chunk.label)] += 1
            ngram_docs[phrase].append({
                "evidence_id": chunk.id,
                "source_type": chunk.source_type,
                "label": chunk.label,
                "date": chunk.retrieved_at.date().isoformat() if chunk.retrieved_at else "unknown",
                "domain": urlparse(chunk.url).netloc.removeprefix("www.") or "unknown",
                "snippet": chunk.summary[:120],
            })

    # Filter to recurring phrases (≥ 2 chunks).
    recurring = [(phrase, counts) for phrase, counts in ngram_map.items()
                 if sum(counts.values()) >= 2]
    recurring.sort(key=lambda item: sum(item[1].values()), reverse=True)

    # Cluster overlapping phrases into threads.
    threads: list[dict] = []
    used_phrases: set[str] = set()
    for phrase, counts in recurring:
        if phrase in used_phrases:
            continue
        # Find related phrases that share tokens.
        phrase_tokens = set(phrase.split())
        cluster = [phrase]
        cluster_counts = Counter(counts)
        for other, oc in recurring:
            if other == phrase or other in used_phrases:
                continue
            other_tokens = set(other.split())
            if phrase_tokens & other_tokens and len(phrase_tokens & other_tokens) >= 1:
                cluster.append(other)
                cluster_counts.update(oc)
                used_phrases.add(other)
        used_phrases.add(phrase)

        # Merge documents from all clustered phrases.
        all_docs: list[dict] = []
        seen_evidence: set[str] = set()
        for p in cluster:
            for doc in ngram_docs.get(p, []):
                if doc["evidence_id"] not in seen_evidence:
                    seen_evidence.add(doc["evidence_id"])
                    all_docs.append(doc)

        total = sum(cluster_counts.values())
        dominant = max(SentimentLabel, key=lambda l: cluster_counts[l.value])
        domains = list({doc["domain"] for doc in all_docs})[:5]
        dates = sorted({doc["date"] for doc in all_docs if doc["date"] != "unknown"})

        threads.append({
            "phrase": cluster[0],
            "cluster": cluster[:4],
            "total_mentions": total,
            "positive": cluster_counts["positive"] / max(1, total),
            "neutral": cluster_counts["neutral"] / max(1, total),
            "negative": cluster_counts["negative"] / max(1, total),
            "dominant_sentiment": dominant.value,
            "source_count": len(domains),
            "evidence_count": len(seen_evidence),
            "domains": domains,
            "date_range": [dates[0], dates[-1]] if dates else None,
            "evidence_ids": [doc["evidence_id"] for doc in all_docs[:6]],
            "sample_snippets": [doc["snippet"] for doc in all_docs[:3]],
            "search_query": phrase,
        })

        if len(threads) >= limit:
            break

    return threads


def build_idea_graph(topic: str, chunks: list[EvidenceChunk], themes: list[str], aspects: list[dict]) -> dict:
    """Build a sentiment-colored graph: red center (topic), colored sources
    (green=positive, gray=neutral, red=negative), aspects and themes orbit.

    No separate sentiment nodes — source color IS the sentiment signal.
    Sources cluster near the center based on their dominant sentiment direction.
    """
    nodes: list[dict] = [{"id": "topic", "label": topic, "kind": "topic", "weight": max(1, len(chunks))}]
    edges: list[dict] = []

    # ── Theme and aspect nodes connect to topic ────────────────────────
    for theme in themes[:6]:
        theme_evidence = [
            c.id for c in chunks
            if theme.lower() in f"{c.summary} {c.snippet}".lower()
        ][:5]
        nodes.append({
            "id": f"theme:{theme}", "label": theme, "kind": "theme",
            "weight": max(2, len(theme_evidence)), "evidence_ids": theme_evidence,
        })
        edges.append({"source": "topic", "target": f"theme:{theme}", "kind": "theme", "weight": 2})

    for aspect in aspects[:8]:
        nodes.append({
            "id": f"aspect:{aspect['name']}", "label": aspect["name"], "kind": "aspect",
            "weight": aspect["count"], "evidence_ids": aspect.get("evidence_ids", []),
        })
        edges.append({"source": "topic", "target": f"aspect:{aspect['name']}", "kind": "aspect", "weight": aspect["count"]})

    # ── Source nodes: colored by dominant sentiment, clustered near topic ──
    domain_urls: dict[str, list[str]] = defaultdict(list)
    domain_sentiment: dict[str, Counter] = defaultdict(Counter)
    for chunk in chunks:
        domain = urlparse(chunk.url).netloc or "unknown"
        domain_sentiment[domain][str(chunk.label)] += 1
        if len(domain_urls[domain]) < 5 and chunk.url not in domain_urls[domain]:
            domain_urls[domain].append(chunk.url)

    for fact in compute_source_facts(chunks, limit=8):
        domain = fact["domain"]
        urls = domain_urls.get(domain, [])
        # Determine dominant sentiment for coloring.
        dom_counts = domain_sentiment.get(domain, Counter())
        dominant = max(dom_counts, key=dom_counts.get) if dom_counts else "neutral"
        nodes.append({
            "id": f"source:{domain}", "label": domain, "kind": "source",
            "weight": fact["count"], "url": urls[0] if urls else None, "urls": urls,
            "sentiment": dominant,
        })
        # Connect source to topic — spring rest distance varies by sentiment
        # so sources cluster in directionality zones.
        edges.append({"source": "topic", "target": f"source:{domain}", "kind": "source", "weight": fact["count"]})
        # Connect source to themes/aspects where its evidence appears.
        source_evidence = {c.id for c in chunks if urlparse(c.url).netloc == domain}
        for theme in themes[:6]:
            theme_ids = {c.id for c in chunks if theme.lower() in f"{c.summary} {c.snippet}".lower()}
            if source_evidence & theme_ids:
                edges.append({"source": f"theme:{theme}", "target": f"source:{domain}", "kind": "source", "weight": 1})
        for aspect in aspects[:8]:
            aspect_ids = set(aspect.get("evidence_ids", []))
            if source_evidence & aspect_ids:
                edges.append({"source": f"aspect:{aspect['name']}", "target": f"source:{domain}", "kind": "source", "weight": 1})
        # URL sub-node for each source.
        if urls:
            url = urls[0]
            url_id = f"url:{url[:60]}"
            path = urlparse(url).path.rstrip("/") or "/"
            nodes.append({
                "id": url_id, "label": path[:28] + "…" if len(path) > 28 else (path or domain),
                "kind": "url", "weight": 1, "url": url, "urls": [url],
            })
            edges.append({"source": f"source:{domain}", "target": url_id, "kind": "source", "weight": 1})

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
