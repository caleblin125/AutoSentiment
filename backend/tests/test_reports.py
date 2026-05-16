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


def test_pick_top_quotes_returns_expected_shape_and_limit() -> None:
    chunks = [
        EvidenceChunk(id=str(i), run_id="r", url=f"https://example.com/{i}", source_type="reddit", snippet="s", label="positive", summary=f"summary {i}")
        for i in range(6)
    ]

    quotes = pick_top_quotes(chunks, SentimentLabel.POSITIVE, n=3)

    assert quotes == [
        {"summary": "summary 0", "evidence_id": "0", "url": "https://example.com/0"},
        {"summary": "summary 1", "evidence_id": "1", "url": "https://example.com/1"},
        {"summary": "summary 2", "evidence_id": "2", "url": "https://example.com/2"},
    ]
