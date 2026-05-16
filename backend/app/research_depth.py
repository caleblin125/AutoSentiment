from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Literal

from app.core.config import Settings

ResearchDepthName = Literal["quick", "standard", "deep", "exhaustive"]


@dataclass(frozen=True)
class ResearchDepthBudget:
    name: ResearchDepthName
    label: str
    query_count: int
    url_count: int
    item_count: int
    source_diversity_target: int
    synthesis_sample_size: int

    def clamped(self, settings: Settings) -> "ResearchDepthBudget":
        """Normalize invalid preset numbers while keeping Settings available for future policy."""
        return replace(
            self,
            query_count=max(1, self.query_count),
            url_count=max(1, self.url_count),
            item_count=max(1, self.item_count),
        )

    def apply_to_settings(self, settings: Settings) -> Settings:
        budget = self.clamped(settings)
        return settings.model_copy(
            update={
                "max_queries_per_run": budget.query_count,
                "max_urls_per_run": budget.url_count,
                "max_items_per_run": budget.item_count,
            }
        )

    def to_metadata(self) -> dict:
        return asdict(self)


DEPTH_PRESETS: dict[ResearchDepthName, ResearchDepthBudget] = {
    "quick": ResearchDepthBudget(
        name="quick",
        label="Quick",
        query_count=3,
        url_count=12,
        item_count=40,
        source_diversity_target=3,
        synthesis_sample_size=24,
    ),
    "standard": ResearchDepthBudget(
        name="standard",
        label="Standard",
        query_count=6,
        url_count=30,
        item_count=100,
        source_diversity_target=5,
        synthesis_sample_size=60,
    ),
    "deep": ResearchDepthBudget(
        name="deep",
        label="Deep",
        query_count=10,
        url_count=60,
        item_count=180,
        source_diversity_target=8,
        synthesis_sample_size=100,
    ),
    "exhaustive": ResearchDepthBudget(
        name="exhaustive",
        label="Exhaustive",
        query_count=16,
        url_count=100,
        item_count=300,
        source_diversity_target=12,
        synthesis_sample_size=160,
    ),
}

DEPTH_ORDER: tuple[ResearchDepthName, ...] = ("quick", "standard", "deep", "exhaustive")
DEFAULT_DEPTH: ResearchDepthName = "standard"


def get_depth_budget(name: str | None, settings: Settings) -> ResearchDepthBudget:
    preset_name = normalize_depth_name(name)
    return DEPTH_PRESETS[preset_name].clamped(settings)


def normalize_depth_name(name: str | None) -> ResearchDepthName:
    if name is None:
        return DEFAULT_DEPTH
    if name not in DEPTH_PRESETS:
        raise ValueError(f"research_depth must be one of: {', '.join(DEPTH_ORDER)}")
    return name  # type: ignore[return-value]


def next_depth_name(current: str | None) -> ResearchDepthName:
    current_name = normalize_depth_name(current)
    idx = DEPTH_ORDER.index(current_name)
    return DEPTH_ORDER[min(idx + 1, len(DEPTH_ORDER) - 1)]


def depth_from_report(report: dict | None) -> ResearchDepthName:
    if not report:
        return DEFAULT_DEPTH
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        return DEFAULT_DEPTH
    depth = metadata.get("research_depth")
    if not isinstance(depth, str):
        return DEFAULT_DEPTH
    try:
        return normalize_depth_name(depth)
    except ValueError:
        return DEFAULT_DEPTH
