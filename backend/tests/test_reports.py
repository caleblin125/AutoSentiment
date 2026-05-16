from app.agents.types import SentimentLabel
from app.models import EvidenceChunk
from app.reports.builder import compute_counts, pick_top_quotes


def test_compute_counts_overall_and_by_source() -> None:
    chunks = [
        EvidenceChunk(id="p1", run_id="r", url="u1", source_type="reddit", snippet="s", label="positive", summary="likes it"),
        EvidenceChunk(id="n1", run_id="r", url="u2", source_type="reddit", snippet="s", label="negative", summary="bugs"),
        EvidenceChunk(id="z1", run_id="r", url="u3", source_type="news", snippet="s", label="neutral", summary="mixed"),
        EvidenceChunk(id="p2", run_id="r", url="u4", source_type="news", snippet="s", label="positive", summary="good value"),
    ]

    counts = compute_counts(chunks)

    assert counts["overall"] == {
        "positive": 0.5,
        "neutral": 0.25,
        "negative": 0.25,
        "total": 4,
    }
    assert counts["by_source"]["reddit"] == {
        "positive": 0.5,
        "neutral": 0.0,
        "negative": 0.5,
        "count": 2,
    }
    assert counts["by_source"]["news"] == {
        "positive": 0.5,
        "neutral": 0.5,
        "negative": 0.0,
        "count": 2,
    }
    assert counts["by_source"]["forum"]["count"] == 0


def test_pick_top_quotes_returns_expected_shape_and_limit() -> None:
    chunks = [
        EvidenceChunk(id=str(i), run_id="r", url=f"https://example.com/{i}", source_type="reddit", snippet="s", label="positive", summary=f"summary {i}")
        for i in range(6)
    ]

    quotes = pick_top_quotes(chunks, SentimentLabel.POSITIVE, n=3)

    assert len(quotes) == 3
    assert all("credible" in q for q in quotes)
    assert [q["evidence_id"] for q in quotes] == ["0", "1", "2"]


def test_pick_top_quotes_confidence_field_and_ranking() -> None:
    """Quotes should include confidence from confidence_map and rank higher-confidence first."""
    chunks = [
        EvidenceChunk(id="low",  run_id="r", url="https://example.com/a", source_type="reddit", snippet="s", label="positive", summary="low conf"),
        EvidenceChunk(id="high", run_id="r", url="https://example.com/b", source_type="reddit", snippet="s", label="positive", summary="high conf"),
    ]
    confidence_map = {"low": 0.5, "high": 0.95}

    quotes = pick_top_quotes(chunks, SentimentLabel.POSITIVE, confidence_map=confidence_map)

    # Both quotes should carry the confidence field.
    assert all("confidence" in q for q in quotes)
    # Higher-confidence item should rank first (credibility equal).
    assert quotes[0]["evidence_id"] == "high"
    assert quotes[0]["confidence"] == 0.95
    assert quotes[1]["confidence"] == 0.5


def test_pick_top_quotes_default_confidence_when_map_absent() -> None:
    """Without a confidence_map the confidence field should default to 0.8."""
    chunk = EvidenceChunk(id="x", run_id="r", url="https://example.com/x", source_type="reddit", snippet="s", label="positive", summary="s")
    quotes = pick_top_quotes([chunk], SentimentLabel.POSITIVE)
    assert quotes[0]["confidence"] == 0.8


def test_report_aspects_source_facts_and_graph_link_evidence() -> None:
    from app.reports.builder import build_idea_graph, compute_aspects, compute_source_facts

    chunks = [
        EvidenceChunk(id="1", run_id="r", url="https://reddit.com/r/cars/1", source_type="reddit", snippet="The price is too expensive but range is efficient.", label="negative", summary="price too expensive"),
        EvidenceChunk(id="2", run_id="r", url="https://news.example/story", source_type="news", snippet="Battery range and efficiency are strong.", label="positive", summary="efficient range"),
    ]

    aspects = compute_aspects(chunks, "Tesla Model 3")
    facts = compute_source_facts(chunks)
    graph = build_idea_graph("Tesla Model 3", chunks, ["pricing"], aspects)

    assert {aspect["name"] for aspect in aspects} >= {"cost", "efficiency"}
    # Every aspect must now carry evidence_ids for the frontend detail popover.
    for aspect in aspects:
        assert "evidence_ids" in aspect
        assert isinstance(aspect["evidence_ids"], list)
    assert facts[0]["count"] == 1
    aspect_nodes = [n for n in graph["nodes"] if n["kind"] == "aspect"]
    assert aspect_nodes, "graph must contain aspect nodes"
    # Aspect nodes in the graph must carry evidence_ids.
    for node in aspect_nodes:
        assert "evidence_ids" in node
    assert any(edge["kind"] == "source" for edge in graph["edges"])


def test_compute_claims_detects_contradictions() -> None:
    """Contradictions should be surfaced when positive and negative chunks share a subject phrase."""
    from app.reports.builder import compute_claims

    chunks = [
        EvidenceChunk(id="p1", run_id="r", url="https://techreview.com/a", source_type="news",
                      snippet="The battery life is excellent.", label="positive",
                      summary="battery life is excellent and lasts all day"),
        EvidenceChunk(id="n1", run_id="r", url="https://complaints.com/b", source_type="reddit",
                      snippet="The battery life is terrible.", label="negative",
                      summary="battery life is terrible drains quickly"),
    ]

    result = compute_claims(chunks)

    assert "contradictions" in result
    assert isinstance(result["contradictions"], list)
    # The phrase "battery life" should be detected as a contradiction subject.
    subjects = {c["subject"] for c in result["contradictions"]}
    assert any("battery" in s for s in subjects), f"Expected 'battery' in contradiction subjects, got {subjects}"
    # Each contradiction must have both sides' evidence.
    for contradiction in result["contradictions"]:
        assert "positive_evidence_id" in contradiction
        assert "negative_evidence_id" in contradiction
        assert "positive_domains" in contradiction
        assert "negative_domains" in contradiction


def test_compute_claims_no_contradictions_without_opposing_chunks() -> None:
    """When all chunks have the same label, no contradictions should be returned."""
    from app.reports.builder import compute_claims

    chunks = [
        EvidenceChunk(id="p1", run_id="r", url="https://example.com/a", source_type="news",
                      snippet="Great product all around.", label="positive", summary="great product overall"),
        EvidenceChunk(id="p2", run_id="r", url="https://example.com/b", source_type="news",
                      snippet="Really good value for money.", label="positive", summary="good value for money"),
    ]

    result = compute_claims(chunks)

    assert result["contradictions"] == []


def test_stop_words_filter_out_common_english_tokens() -> None:
    """Bogus tokens like 'for', 'not', 'its', 'use' must not appear as aspects."""
    from app.reports.builder import STOP_WORDS, compute_aspects

    bogus_tokens = ["for", "not", "its", "has", "use", "the", "and", "can", "but"]
    for token in bogus_tokens:
        assert token in STOP_WORDS, f"'{token}' should be in STOP_WORDS"

    # Build chunks where "for" appears many times — it must NOT become an aspect.
    chunks = [
        EvidenceChunk(
            id=str(i), run_id="r",
            url=f"https://example.com/{i}",
            source_type="news",
            snippet=f"This is very good for everyone not just for some people for all.",
            label="positive",
            summary=f"good for people",
        )
        for i in range(5)
    ]
    aspects = compute_aspects(chunks, "test topic")
    aspect_names = {a["name"] for a in aspects}
    for bogus in bogus_tokens:
        assert bogus not in aspect_names, f"'{bogus}' must not appear as an aspect"


def test_expand_platform_queries_has_diverse_sources() -> None:
    """Query expansion must include non-Reddit platforms and international queries."""
    from app.agents.orchestrator import _expand_platform_queries

    queries = _expand_platform_queries(["test topic review"], "test topic")
    query_str = " ".join(queries).lower()

    # Must include diverse platform sites beyond Reddit
    assert "quora.com" in query_str
    assert "youtube.com" in query_str
    assert "trustpilot.com" in query_str
    assert "news.ycombinator.com" in query_str

    # Reddit should be present but not dominant (≤1 explicit reddit query)
    reddit_queries = [q for q in queries if "reddit.com" in q.lower()]
    assert len(reddit_queries) <= 1, f"Too many Reddit queries: {reddit_queries}"

    # Must include international languages
    assert any("opinión" in q or "avis" in q or "Bewertung" in q for q in queries)


def test_compute_timeline_extracts_explicit_dates_without_fabricating() -> None:
    from app.reports.builder import compute_timeline

    chunks = [
        EvidenceChunk(
            id="d1",
            run_id="r",
            url="https://example.com/launch",
            source_type="news",
            snippet="The trailer released on March 5, 2026 and reviews followed on 2026-03-10.",
            label="neutral",
            summary="trailer release",
        ),
        EvidenceChunk(
            id="d2",
            run_id="r",
            url="https://example.com/no-date",
            source_type="news",
            snippet="No calendar date appears here.",
            label="neutral",
            summary="general discussion",
        ),
    ]

    timeline = compute_timeline(chunks, "Movie")

    dates = [item["date"] for item in timeline["important_dates"]]
    assert "2026-03-05" in dates
    assert "2026-03-10" in dates
    assert timeline["start_date"] <= timeline["end_date"]
    assert "d1" in timeline["supporting_evidence_ids"]


def test_compute_timeline_ignores_retrieved_at_when_no_explicit_dates() -> None:
    from app.reports.builder import compute_timeline

    chunks = [
        EvidenceChunk(id="no-date", run_id="r", url="https://news.example/a", source_type="news",
                      snippet="People debated the product without naming a date.",
                      label="neutral", summary="discussion")
    ]

    timeline = compute_timeline(chunks, "Product")

    assert timeline["important_dates"] == []
    assert timeline["start_date"] is None
    assert "No explicit dates" in timeline["event_summary"]


def test_compute_claims_groups_factual_claims_and_flags_verification() -> None:
    from app.reports.builder import compute_claims

    chunks = [
        EvidenceChunk(
            id="c1",
            run_id="r",
            url="https://news.example/story",
            source_type="news",
            snippet="The film was released on March 5, 2026 and earned $10 million during previews.",
            label="neutral",
            summary="release data",
        ),
        EvidenceChunk(
            id="c2",
            run_id="r",
            url="https://reddit.com/r/movies/1",
            source_type="reddit",
            snippet="People are excited and think the soundtrack is good.",
            label="positive",
            summary="fans excited",
        ),
    ]

    fact_check = compute_claims(chunks)

    assert fact_check["claims"]
    claim = fact_check["claims"][0]
    assert claim["claim_type"] in {"event", "quantitative"}
    assert claim["evidence_ids"] == ["c1"]
    assert "news.example" in claim["supporting_domains"]
    assert fact_check["summary"].startswith("Extracted")


def test_use_case_insights_and_chart_data_support_entertainment_mode() -> None:
    from app.reports.builder import compute_aspects, compute_chart_data, compute_claims, compute_use_case_insights

    chunks = [
        EvidenceChunk(
            id="e1",
            run_id="r",
            url="https://reddit.com/r/show/1",
            source_type="reddit",
            snippet="The story and casting are strong in California, but the trailer marketing was confusing.",
            label="negative",
            summary="confusing marketing",
        ),
        EvidenceChunk(
            id="e2",
            run_id="r",
            url="https://trade.example/review",
            source_type="news",
            snippet="The film was released on March 5, 2026 and box office tracking increased in California.",
            label="positive",
            summary="tracking increased",
        ),
    ]

    aspects = compute_aspects(chunks, "New Show")
    fact_check = compute_claims(chunks)
    insights = compute_use_case_insights(chunks, "entertainment_product", aspects, fact_check)
    chart_data = compute_chart_data(chunks, aspects, fact_check)

    assert insights["use_case"] == "entertainment_product"
    assert "audience_pulse" in insights["sections"]
    assert chart_data["source_mix"]
    assert chart_data["aspect_matrix"]
    assert chart_data["location_sentiment"][0]["location"] == "California"
    assert chart_data["sentiment_over_time"][0]["date"] == "2026-03-05"
    assert chart_data["sentiment_over_time"][0]["certainty"] == "explicit"
    assert any(aspect["aspect"] in {"story", "casting", "marketing", "commercial potential"} for aspect in chart_data["aspect_matrix"])


def test_chart_data_falls_back_to_source_domain_location_and_retrieved_time() -> None:
    from datetime import datetime

    from app.reports.builder import compute_chart_data

    chunks = [
        EvidenceChunk(
            id=f"loc{i}",
            run_id="r",
            url=f"https://example{i}.co.uk/story",
            source_type="news",
            snippet="Analysts said demand improved without naming a location.",
            label="positive",
            summary="demand improved",
            retrieved_at=datetime(2026, 4, 8, 12, 0, 0),
        )
        for i in range(3)
    ]

    chart_data = compute_chart_data(chunks, [], {"claims": []})

    assert chart_data["sentiment_over_time"] == [{
        "date": "2026-04-08",
        "positive": 3,
        "neutral": 0,
        "negative": 0,
        "total": 3,
        "certainty": "retrieved_at",
    }]
    assert chart_data["location_sentiment"][0]["location"] == "United Kingdom"
    assert chart_data["location_sentiment"][0]["certainty"] == "source_domain"


def _make_chunk(
    cid: str,
    url: str,
    snippet: str,
    label: str = "neutral",
    summary: str | None = None,
    source_type: str = "news",
) -> EvidenceChunk:
    return EvidenceChunk(
        id=cid,
        run_id="r",
        url=url,
        source_type=source_type,
        snippet=snippet,
        label=label,
        summary=summary or snippet[:80],
    )


def test_compute_threads_returns_empty_when_no_recurring_phrases() -> None:
    """Single-mention phrases must not become threads."""
    from app.reports.builder import compute_threads

    chunks = [
        _make_chunk("a", "https://news.example/a", "The release date was leaked early."),
        _make_chunk("b", "https://reddit.com/r/show/b", "Totally different content about pricing strategy."),
    ]

    threads = compute_threads(chunks, "Show")

    assert threads == [] or all(t["total_mentions"] >= 2 for t in threads)


def test_compute_threads_clusters_recurring_phrases_with_provenance() -> None:
    """Recurring phrases across sources form a thread with sentiment, domains, dates."""
    from app.reports.builder import compute_threads

    chunks = [
        _make_chunk("a", "https://news.example/r1", "Fans complained about microtransactions and unfair pricing.", label="negative", summary="microtransactions unfair pricing"),
        _make_chunk("b", "https://reddit.com/r/games/2", "The microtransactions feel predatory and pricing is unfair.", label="negative", summary="microtransactions unfair pricing"),
        _make_chunk("c", "https://trade.example/3", "Critics also flagged microtransactions as predatory monetization.", label="negative", summary="microtransactions predatory"),
    ]

    threads = compute_threads(chunks, "Game")

    assert threads, "Expected at least one thread"
    top = threads[0]
    assert top["total_mentions"] >= 2
    assert top["evidence_count"] >= 2
    assert top["source_count"] >= 2
    assert top["dominant_sentiment"] == "negative"
    assert 0.0 <= top["positive"] <= 1.0
    assert 0.0 <= top["negative"] <= 1.0
    assert abs((top["positive"] + top["neutral"] + top["negative"]) - 1.0) < 1e-6
    assert top["search_query"]
    assert top["domains"]
    assert any("microtransactions" in p or "pricing" in p for p in top["cluster"])


def test_compute_threads_excludes_topic_tokens_from_phrases() -> None:
    """Topic tokens themselves must not seed threads (otherwise every chunk would match)."""
    from app.reports.builder import compute_threads

    chunks = [
        _make_chunk("a", "https://news.example/a", "Cyberpunk story missions feel rushed and incomplete."),
        _make_chunk("b", "https://news.example/b", "Cyberpunk story missions also drag at times."),
    ]

    threads = compute_threads(chunks, "Cyberpunk")

    for t in threads:
        assert "cyberpunk" not in t["phrase"].lower(), f"Topic token leaked into thread: {t['phrase']}"


def test_compute_threads_respects_limit() -> None:
    """The limit kwarg caps thread output."""
    from app.reports.builder import compute_threads

    chunks = []
    for i in range(8):
        phrase = f"alpha{i} beta{i}"
        chunks.append(_make_chunk(f"x{i}a", f"https://news.example/{i}a", f"This article notes {phrase} discussed across players."))
        chunks.append(_make_chunk(f"x{i}b", f"https://reddit.com/r/x/{i}b", f"Players also mention {phrase} in another way."))

    threads = compute_threads(chunks, "Game", limit=3)

    assert len(threads) <= 3


def test_compute_location_sentiment_extracts_mentioned_country() -> None:
    """Locations named ≥2 times in chunks should appear in the location data."""
    from app.reports.builder import compute_location_sentiment

    chunks = [
        _make_chunk("a", "https://example.com/1", "The United States market saw strong growth.", label="positive"),
        _make_chunk("b", "https://example.com/2", "Sales in the United States were record-breaking.", label="positive"),
        _make_chunk("c", "https://example.com/3", "Germany reported mixed consumer sentiment.", label="neutral"),
    ]
    results = compute_location_sentiment(chunks)
    locations = {r["location"].lower() for r in results}

    # US appears twice — should pass the ≥2 threshold.
    assert any("united states" in loc for loc in locations), f"Expected United States in {locations}"
    # Germany appears once — should be filtered out.
    assert not any("germany" in loc for loc in locations), "Germany should be filtered (single mention)"


def test_compute_location_sentiment_requires_two_items_minimum() -> None:
    """A single mention should not create a map point."""
    from app.reports.builder import compute_location_sentiment

    chunks = [
        _make_chunk("x", "https://reuters.co.uk/story", "Canada had a record quarter.", label="positive"),
    ]
    results = compute_location_sentiment(chunks)
    assert results == [], "One chunk should not produce a location"


def test_compute_location_sentiment_returns_lat_lon() -> None:
    """Each returned location must have numeric lat and lon fields."""
    from app.reports.builder import compute_location_sentiment

    chunks = [
        _make_chunk("a", "https://example.com/1", "Japan's market rebounded strongly.", label="positive"),
        _make_chunk("b", "https://example.com/2", "Japan continues recovery trajectory.", label="positive"),
    ]
    results = compute_location_sentiment(chunks)
    if results:
        loc = results[0]
        assert isinstance(loc["lat"], (int, float)), "lat must be numeric"
        assert isinstance(loc["lon"], (int, float)), "lon must be numeric"
        assert -90 <= loc["lat"] <= 90
        assert -180 <= loc["lon"] <= 180


def test_compute_threads_date_range_uses_retrieved_at_dates() -> None:
    """Threads expose a date_range derived from chunk retrieval dates."""
    from datetime import datetime, UTC
    from app.reports.builder import compute_threads

    early = _make_chunk("e1", "https://news.example/e1", "Patch notes reveal balance changes and improved netcode.")
    early.retrieved_at = datetime(2026, 1, 5, tzinfo=UTC)
    late = _make_chunk("e2", "https://reddit.com/r/g/e2", "Players still talk about balance changes after the patch.")
    late.retrieved_at = datetime(2026, 3, 12, tzinfo=UTC)

    threads = compute_threads([early, late], "Game")

    assert threads, "Expected at least one thread"
    matching = [t for t in threads if t["date_range"]]
    assert matching, "Expected at least one thread with a date_range"
    top = matching[0]
    start, end = top["date_range"]
    assert start <= end
    assert start in {"2026-01-05", "2026-03-12"}
    assert end in {"2026-01-05", "2026-03-12"}


# ---------------------------------------------------------------------------
# Property-based invariant tests (no Hypothesis — manual multi-case approach)
# Each test exercises the same invariant with several different inputs to act
# as a lightweight parametrized property check without adding a new dependency.
# ---------------------------------------------------------------------------

import itertools


def _make_chunks_mixed(labels: list[str], source_type: str = "news") -> list[EvidenceChunk]:
    """Build a list of chunks with the given label sequence."""
    return [
        EvidenceChunk(
            id=f"pb{i}",
            run_id="r",
            url=f"https://example.com/{i}",
            source_type=source_type,
            snippet=f"Snippet number {i}.",
            label=label,
            summary=f"Summary {i}.",
        )
        for i, label in enumerate(labels)
    ]


# --- compute_counts invariants ---

def test_compute_counts_fractions_sum_to_one_invariant() -> None:
    """Invariant: positive + neutral + negative == 1.0 for any non-empty chunk list."""
    cases = [
        ["positive"] * 5,
        ["negative"] * 3,
        ["neutral"] * 7,
        ["positive", "negative", "neutral"],
        ["positive"] * 10 + ["negative"] * 3 + ["neutral"] * 7,
        ["negative"] * 1,
        ["positive", "positive", "neutral"],
    ]
    for labels in cases:
        counts = compute_counts(_make_chunks_mixed(labels))
        total_frac = counts["overall"]["positive"] + counts["overall"]["neutral"] + counts["overall"]["negative"]
        assert abs(total_frac - 1.0) < 1e-9, (
            f"Fractions sum to {total_frac} for labels {labels}"
        )


def test_compute_counts_total_matches_chunk_count_invariant() -> None:
    """Invariant: overall['total'] always equals len(chunks)."""
    for n in [1, 2, 5, 10, 20]:
        labels = (["positive", "negative", "neutral"] * n)[:n]
        chunks = _make_chunks_mixed(labels)
        assert compute_counts(chunks)["overall"]["total"] == n


def test_compute_counts_empty_chunks_returns_zeros() -> None:
    """Invariant: empty input produces all-zero fractions and total == 0."""
    counts = compute_counts([])
    assert counts["overall"]["total"] == 0
    assert counts["overall"]["positive"] == 0.0
    assert counts["overall"]["negative"] == 0.0
    assert counts["overall"]["neutral"] == 0.0


def test_compute_counts_fractions_in_unit_interval_invariant() -> None:
    """Invariant: every fraction is in [0, 1]."""
    for labels in [
        ["positive"] * 3 + ["negative"] * 2,
        ["neutral"] * 1,
        ["positive", "negative"],
    ]:
        counts = compute_counts(_make_chunks_mixed(labels))
        for key in ("positive", "neutral", "negative"):
            val = counts["overall"][key]
            assert 0.0 <= val <= 1.0, f"overall[{key}]={val} out of range"
        for src_data in counts["by_source"].values():
            for key in ("positive", "neutral", "negative"):
                val = src_data[key]
                assert 0.0 <= val <= 1.0, f"by_source [{key}]={val} out of range"


# --- pick_top_quotes invariants ---

def test_pick_top_quotes_never_exceeds_n_invariant() -> None:
    """Invariant: result length <= n regardless of input size."""
    chunks = [
        EvidenceChunk(id=str(i), run_id="r", url=f"https://example.com/{i}",
                      source_type="reddit", snippet="s", label="positive", summary="s")
        for i in range(20)
    ]
    for n in [0, 1, 3, 5, 7, 10, 25]:
        result = pick_top_quotes(chunks, SentimentLabel.POSITIVE, n=n)
        assert len(result) <= n, f"pick_top_quotes returned {len(result)} for n={n}"


def test_pick_top_quotes_only_returns_matching_label_invariant() -> None:
    """Invariant: all returned quotes have the requested label."""
    chunks = _make_chunks_mixed(["positive", "negative", "neutral", "positive", "negative"])
    for label in (SentimentLabel.POSITIVE, SentimentLabel.NEGATIVE, SentimentLabel.NEUTRAL):
        result = pick_top_quotes(chunks, label, n=10)
        for q in result:
            chunk = next(c for c in chunks if c.id == q["evidence_id"])
            assert str(chunk.label) == label.value, (
                f"Quote for {label.value} references chunk with label {chunk.label}"
            )


def test_pick_top_quotes_empty_when_no_matching_label() -> None:
    """Invariant: returns [] when no chunks carry the requested label."""
    chunks = _make_chunks_mixed(["positive", "positive"])
    assert pick_top_quotes(chunks, SentimentLabel.NEGATIVE) == []
    assert pick_top_quotes(chunks, SentimentLabel.NEUTRAL) == []


def test_pick_top_quotes_credible_sources_rank_before_non_credible_invariant() -> None:
    """Invariant: credible source always ranks before a non-credible one at equal confidence."""
    chunks = [
        EvidenceChunk(id="social", run_id="r", url="https://reddit.com/r/x/1",
                      source_type="reddit", snippet="s", label="positive", summary="reddit opinion"),
        EvidenceChunk(id="credible", run_id="r", url="https://reuters.com/story",
                      source_type="news", snippet="s", label="positive", summary="reuters coverage"),
    ]
    confidence_map = {"social": 0.9, "credible": 0.9}
    result = pick_top_quotes(chunks, SentimentLabel.POSITIVE, n=2, confidence_map=confidence_map)
    assert len(result) == 2
    assert result[0]["evidence_id"] == "credible", "Reuters (credible) must rank before reddit (non-credible)"
    assert result[0]["credible"] is True
    assert result[1]["credible"] is False


def test_pick_top_quotes_result_keys_invariant() -> None:
    """Invariant: every returned dict always has the required keys."""
    required_keys = {"summary", "evidence_id", "url", "credible", "confidence"}
    chunks = _make_chunks_mixed(["positive"] * 4)
    for n in [1, 2, 4]:
        result = pick_top_quotes(chunks, SentimentLabel.POSITIVE, n=n)
        for q in result:
            assert required_keys <= q.keys(), f"Missing keys: {required_keys - q.keys()}"
            assert 0.0 <= q["confidence"] <= 1.0, f"confidence {q['confidence']} out of range"


# --- _find_contradictions invariants ---

def test_find_contradictions_strength_ge_two_invariant() -> None:
    """Invariant: every contradiction has strength >= 2 (at least one from each side)."""
    from app.reports.builder import _find_contradictions  # type: ignore[attr-defined]

    chunks = [
        EvidenceChunk(id="p1", run_id="r", url="https://reuters.com/a", source_type="news",
                      snippet="s", label="positive", summary="battery life is excellent"),
        EvidenceChunk(id="n1", run_id="r", url="https://reddit.com/r/x/1", source_type="reddit",
                      snippet="s", label="negative", summary="battery life is terrible"),
        EvidenceChunk(id="p2", run_id="r", url="https://bbc.com/b", source_type="news",
                      snippet="s", label="positive", summary="battery life is excellent"),
    ]
    contradictions = _find_contradictions(chunks)
    for c in contradictions:
        assert c["strength"] >= 2, f"strength={c['strength']} is less than 2"


def test_find_contradictions_at_most_limit_invariant() -> None:
    """Invariant: result length never exceeds the limit argument."""
    from app.reports.builder import _find_contradictions  # type: ignore[attr-defined]

    chunks = []
    for i in range(12):
        summary = f"theme{i} aspect{i} always good for users"
        chunks.append(EvidenceChunk(id=f"p{i}", run_id="r", url=f"https://news.example/p{i}",
                                    source_type="news", snippet="s", label="positive", summary=summary))
        chunks.append(EvidenceChunk(id=f"n{i}", run_id="r", url=f"https://reddit.com/r/x/n{i}",
                                    source_type="reddit", snippet="s", label="negative", summary=summary))

    for limit in [1, 3, 6, 10]:
        result = _find_contradictions(chunks, limit=limit)
        assert len(result) <= limit, f"limit={limit} but got {len(result)} contradictions"


def test_find_contradictions_all_positive_yields_none_invariant() -> None:
    """Invariant: homogeneous-label input cannot produce any contradiction."""
    from app.reports.builder import _find_contradictions  # type: ignore[attr-defined]

    for label in ("positive", "negative", "neutral"):
        chunks = _make_chunks_mixed([label] * 6)
        for c in chunks:
            c.summary = "electric vehicle range improves consistently over time"
        assert _find_contradictions(chunks) == [], f"Unexpected contradiction for all-{label} input"


def test_find_contradictions_required_keys_invariant() -> None:
    """Invariant: every contradiction dict has all required keys."""
    from app.reports.builder import _find_contradictions  # type: ignore[attr-defined]

    required = {"subject", "positive_claim", "negative_claim",
                "positive_evidence_id", "negative_evidence_id",
                "positive_domains", "negative_domains", "strength"}
    chunks = [
        EvidenceChunk(id="p1", run_id="r", url="https://bbc.com/a", source_type="news",
                      snippet="s", label="positive", summary="battery range excellent improvement"),
        EvidenceChunk(id="n1", run_id="r", url="https://reddit.com/b", source_type="reddit",
                      snippet="s", label="negative", summary="battery range terrible drains fast"),
    ]
    for c in _find_contradictions(chunks):
        assert required <= c.keys(), f"Missing keys: {required - c.keys()}"
        assert c["positive_evidence_id"] != c["negative_evidence_id"]
        assert c["strength"] >= 1


# --- compute_aspects invariants ---

def test_compute_aspects_at_most_limit_invariant() -> None:
    """Invariant: result length never exceeds the limit kwarg."""
    from app.reports.builder import compute_aspects

    chunks = _make_chunks_mixed(["positive"] * 4 + ["negative"] * 4)
    for chunk in chunks:
        chunk.snippet = (
            "The cost, safety, design, reliability, efficiency, trust, "
            "environment, and policy are all relevant considerations."
        )
    for limit in [1, 3, 5, 8]:
        result = compute_aspects(chunks, "Product", limit=limit)
        assert len(result) <= limit, f"limit={limit} but got {len(result)} aspects"


def test_compute_aspects_valid_sentiment_values_invariant() -> None:
    """Invariant: every aspect's sentiment is one of the four expected values."""
    from app.reports.builder import compute_aspects

    valid = {"positive", "negative", "neutral", "mixed"}
    labels = ["positive"] * 3 + ["negative"] * 3
    chunks = _make_chunks_mixed(labels)
    for chunk in chunks:
        chunk.snippet = "battery efficiency and safety cost design reliability"
    aspects = compute_aspects(chunks, "EV", limit=8)
    for a in aspects:
        assert a["sentiment"] in valid, f"Invalid aspect sentiment: {a['sentiment']}"


def test_compute_aspects_count_positive_invariant() -> None:
    """Invariant: every returned aspect has count >= 1 (otherwise it would be filtered)."""
    from app.reports.builder import compute_aspects

    chunks = _make_chunks_mixed(["positive", "negative", "neutral"])
    for chunk in chunks:
        chunk.snippet = "safety reliability cost trust policy"
    aspects = compute_aspects(chunks, "Topic", limit=10)
    for a in aspects:
        assert a["count"] >= 1, f"Aspect {a['name']} has count={a['count']}"
        assert "evidence_ids" in a


# --- compute_claims invariants ---

def test_compute_claims_confidence_in_range_invariant() -> None:
    """Invariant: every claim has confidence in [0, 0.95]."""
    from app.reports.builder import compute_claims

    labels = ["positive", "negative", "neutral", "positive"]
    chunks = _make_chunks_mixed(labels)
    for i, c in enumerate(chunks):
        c.snippet = f"The product was released on 2026-01-{10 + i} and costs $99."
    result = compute_claims(chunks)
    for claim in result["claims"]:
        assert 0.0 <= claim["confidence"] <= 0.95, (
            f"confidence={claim['confidence']} out of [0, 0.95]"
        )


def test_compute_claims_at_most_limit_invariant() -> None:
    """Invariant: returned claims list never exceeds the limit argument."""
    from app.reports.builder import compute_claims

    chunks = []
    for i in range(30):
        chunks.append(EvidenceChunk(
            id=f"c{i}", run_id="r", url=f"https://news.example/{i}",
            source_type="news",
            snippet=f"Claim {i}: the product has exactly {i + 1} defects reported.",
            label="negative",
            summary=f"defects reported claim {i}",
        ))
    for limit in [1, 5, 10]:
        result = compute_claims(chunks, limit=limit)
        assert len(result["claims"]) <= limit, (
            f"limit={limit} but got {len(result['claims'])} claims"
        )


def test_compute_claims_required_keys_invariant() -> None:
    """Invariant: every claim dict has all required keys."""
    from app.reports.builder import compute_claims

    required_claim_keys = {
        "claim", "claim_type", "confidence", "supporting_domains",
        "supporting_urls", "opposing_domains", "evidence_ids",
        "source_types", "needs_verification",
    }
    required_result_keys = {"claims", "needs_verification", "contradictions", "summary"}
    chunks = _make_chunks_mixed(["positive", "negative", "neutral"])
    for c in chunks:
        c.snippet = "The company released 2 million units on March 1, 2026."
    result = compute_claims(chunks)
    assert required_result_keys <= result.keys()
    for claim in result["claims"]:
        assert required_claim_keys <= claim.keys(), f"Missing: {required_claim_keys - claim.keys()}"


def test_compute_claims_empty_input_returns_empty_lists() -> None:
    """Invariant: empty chunk list produces empty claim/contradiction lists."""
    from app.reports.builder import compute_claims

    result = compute_claims([])
    assert result["claims"] == []
    assert result["contradictions"] == []
    assert result["needs_verification"] == []
