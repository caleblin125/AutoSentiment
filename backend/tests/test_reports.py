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
            snippet="The film was released on March 5, 2026 and box office tracking increased.",
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

    chunk = EvidenceChunk(
        id="loc1",
        run_id="r",
        url="https://example.co.uk/story",
        source_type="news",
        snippet="Analysts said demand improved without naming a location.",
        label="positive",
        summary="demand improved",
        retrieved_at=datetime(2026, 4, 8, 12, 0, 0),
    )

    chart_data = compute_chart_data([chunk], [], {"claims": []})

    assert chart_data["sentiment_over_time"] == [{
        "date": "2026-04-08",
        "positive": 1,
        "neutral": 0,
        "negative": 0,
        "total": 1,
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
