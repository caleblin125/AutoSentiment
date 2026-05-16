import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "autosentiment_tui.py"
SPEC = importlib.util.spec_from_file_location("autosentiment_tui", SCRIPT_PATH)
assert SPEC and SPEC.loader
tui = importlib.util.module_from_spec(SPEC)
sys.modules["autosentiment_tui"] = tui
SPEC.loader.exec_module(tui)


def test_parse_sse_lines_handles_multiple_events_and_bad_json() -> None:
    lines = [
        'data: {"type": "run_started", "message": "started"}\n',
        "\n",
        "data: not-json\n",
        "\n",
        'data: {"type": "run_completed", "detail": {"report": {}}}\n',
        "\n",
    ]

    events = list(tui.parse_sse_lines(lines))

    assert [event["type"] for event in events] == ["run_started", "run_completed"]


def test_format_report_includes_sentiment_themes_and_chronology() -> None:
    report = {
        "overall": {"positive": 0.5, "neutral": 0.25, "negative": 0.25, "total": 12},
        "themes": ["cost", "quality"],
        "narrative": "Mixed but useful.",
        "timeline": {"event_summary": "Started in January and peaked in March."},
    }

    text = tui.format_report(report)

    assert "Items: 12" in text
    assert "+50% ~25% -25%" in text
    assert "Themes: cost, quality" in text
    assert "Chronology: Started in January" in text


def test_format_run_row_handles_missing_report() -> None:
    row = tui.format_run_row({"id": "abcdef123456", "status": "running", "topic": "Topic"})

    assert row.startswith("abcdef12")
    assert "running" in row
    assert "no report" in row
