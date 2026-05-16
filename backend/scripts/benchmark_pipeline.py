"""Local performance benchmark for pipeline hot spots.

Run from `backend/`:

    source .venv/bin/activate
    python3 scripts/benchmark_pipeline.py

The benchmark avoids network and Ollama calls. It measures the in-run
sentiment de-duplication change against a baseline that analyzes every item.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.orchestrator import _analyze_item, _analyze_item_cached
from app.agents.types import SentimentLabel, SentimentResult, SourceType
from app.ingest.fetch import FetchedItem


class FakeSentimentQueue:
    def __init__(self, delay_seconds: float = 0.02) -> None:
        self.delay_seconds = delay_seconds
        self.calls = 0

    async def analyze(self, _snippet: str) -> SentimentResult:
        self.calls += 1
        await asyncio.sleep(self.delay_seconds)
        return SentimentResult(label=SentimentLabel.NEUTRAL, summary="benchmark")


def _items(total: int = 80, unique: int = 20) -> list[FetchedItem]:
    return [
        FetchedItem(
            snippet=f"Repeated opinion snippet {idx % unique}",
            url=f"https://example.com/{idx}",
            source_type=SourceType.NEWS,
        )
        for idx in range(total)
    ]


async def _run_baseline(items: list[FetchedItem]) -> dict:
    queue = FakeSentimentQueue()
    started = perf_counter()
    await asyncio.gather(*[_analyze_item(queue, item) for item in items])
    return {
        "elapsed_ms": round((perf_counter() - started) * 1000, 2),
        "model_calls": queue.calls,
    }


async def _run_optimized(items: list[FetchedItem]) -> dict:
    queue = FakeSentimentQueue()
    sentiment_tasks: dict[str, asyncio.Task] = {}
    started = perf_counter()
    await asyncio.gather(*[_analyze_item_cached(queue, item, sentiment_tasks) for item in items])
    return {
        "elapsed_ms": round((perf_counter() - started) * 1000, 2),
        "model_calls": queue.calls,
        "cache_hits": len(items) - queue.calls,
    }


async def main() -> None:
    items = _items()
    baseline = await _run_baseline(items)
    optimized = await _run_optimized(items)
    print(json.dumps({
        "scenario": "sentiment_dedup_80_items_20_unique",
        "baseline": baseline,
        "optimized": optimized,
        "model_call_reduction_pct": round(
            100 * (baseline["model_calls"] - optimized["model_calls"]) / baseline["model_calls"],
            2,
        ),
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
