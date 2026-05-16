import pytest

from app.core.config import Settings
from app.research_depth import depth_from_report, get_depth_budget, next_depth_name, normalize_depth_name


def test_depth_budget_applies_expected_presets_to_settings() -> None:
    settings = Settings(max_queries_per_run=16, max_urls_per_run=30, max_items_per_run=100)

    deep = get_depth_budget("deep", settings)
    applied = deep.apply_to_settings(settings)

    assert deep.query_count == 10
    assert deep.url_count == 60
    assert deep.item_count == 180
    assert applied.max_queries_per_run == 10
    assert applied.max_urls_per_run == 60
    assert applied.max_items_per_run == 180


def test_depth_helpers_validate_and_advance_presets() -> None:
    assert normalize_depth_name(None) == "standard"
    assert next_depth_name("quick") == "standard"
    assert next_depth_name("standard") == "deep"
    assert next_depth_name("exhaustive") == "exhaustive"
    with pytest.raises(ValueError):
        normalize_depth_name("invalid")


def test_depth_from_report_defaults_safely() -> None:
    assert depth_from_report(None) == "standard"
    assert depth_from_report({"metadata": {"research_depth": "quick"}}) == "quick"
    assert depth_from_report({"metadata": {"research_depth": "invalid"}}) == "standard"
