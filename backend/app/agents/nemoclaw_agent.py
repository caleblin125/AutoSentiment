"""NemoClaw autonomous research agent.

Runs independently alongside the main pipeline, generating unique analytical
queries from the 120B model's perspective, fetching targeted content, and
producing expert-level insights that complement the sentiment analysis.

Unlike the standard pipeline (breadth-first opinion collection), NemoClaw:
  - Generates deep-dive angles (expert opinion, historical context, data/stats)
  - Uses the 120B model to reason about what angles are most illuminating
  - Streams its thinking as it works so the UI can show live progress
  - Produces a structured "expert analysis" rather than sentiment percentages
"""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import TYPE_CHECKING

from app.agents.ollama import ollama_generate
from app.agents.types import SSEEventType
from app.api import event_bus
from app.api.event_bus import clear_cancel, is_cancelled
from app.db.session import AsyncSessionLocal
from app.ingest.fetch import fetch_items
from app.models import Run, RunEvent
from app.tools.search import brave_search

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_AGENT_CONCURRENCY = 4


async def run_nemoclaw(
    nc_run_id: str,
    topic: str,
    parent_run_id: str,
    settings: Settings,
) -> None:
    """Full NemoClaw autonomous research pipeline.

    Stages:
    1. Generate 4 expert analytical angles via the 120B model
    2. Search Brave for each angle
    3. Fetch and read top 3 URLs per angle (parallel)
    4. Synthesise a structured expert analysis
    5. Emit RUN_COMPLETED with the findings
    """
    queue = event_bus.get(nc_run_id)
    seq = 0
    started_at = perf_counter()

    def _ms() -> float:
        return round((perf_counter() - started_at) * 1000, 1)

    async with AsyncSessionLocal() as db:
        async def emit(event_type: SSEEventType, message: str, detail: dict | None = None) -> None:
            nonlocal seq
            seq += 1
            enriched = {**(detail or {}), "elapsed_ms": _ms()}
            event = {"seq": seq, "type": event_type.value, "message": message, "detail": enriched}
            db.add(RunEvent(
                run_id=nc_run_id, seq=seq,
                type=event_type.value, message=message, detail=enriched,
            ))
            if queue:
                queue.put_nowait(event)

        try:
            run = await db.get(Run, nc_run_id)
            if run is None:
                return
            run.status = "running"
            await emit(SSEEventType.RUN_STARTED, "NemoClaw activated", {"topic": topic, "parent_run_id": parent_run_id})
            await db.commit()

            # ── Stage 1: Generate expert analytical angles ─────────────────
            angles = await _generate_angles(topic, settings)
            await emit(SSEEventType.SEARCH_QUERIED, f"Generated {len(angles)} analytical angles",
                       {"angles": angles})
            await db.commit()

            if is_cancelled(nc_run_id):
                raise _Done()

            # ── Stage 2: Search + fetch for each angle ──────────────────────
            all_snippets: list[dict] = []
            sem = asyncio.Semaphore(_AGENT_CONCURRENCY)

            for angle in angles:
                if is_cancelled(nc_run_id):
                    break

                await emit(SSEEventType.SEARCH_QUERIED, f"Researching: {angle}", {"query": angle})
                await db.commit()

                try:
                    urls = await brave_search(angle, freshness=None, count=5, settings=settings)
                except Exception:
                    urls = []

                fetch_tasks = [asyncio.create_task(_fetch_one(url, sem)) for url in urls[:3]]
                for fut in asyncio.as_completed(fetch_tasks):
                    if is_cancelled(nc_run_id):
                        for t in fetch_tasks:
                            t.cancel()
                        break
                    url, snippets, fetch_ms = await fut
                    all_snippets.extend(snippets[:2])
                    await emit(SSEEventType.URL_FETCHED, f"Read {len(snippets)} items",
                               {"url": url, "item_count": len(snippets), "fetch_ms": fetch_ms,
                                "domain": _domain(url)})
                    await db.commit()

            if is_cancelled(nc_run_id):
                raise _Done()

            # ── Stage 3: Expert synthesis ───────────────────────────────────
            await emit(SSEEventType.SYNTHESIS_STARTED, "NemoClaw synthesising expert analysis")
            await db.commit()

            analysis = await _expert_synthesis(topic, angles, all_snippets, settings)

            run = await db.get(Run, nc_run_id)
            if run is None:
                return
            run.status = "completed"
            run.report = analysis
            await emit(SSEEventType.RUN_COMPLETED, "NemoClaw analysis complete",
                       {"report": analysis})
            await db.commit()

        except _Done:
            run = await db.get(Run, nc_run_id)
            if run is not None:
                run.status = "cancelled"
            await emit(SSEEventType.RUN_CANCELLED, "NemoClaw stopped")
            await db.commit()
        except Exception:
            logger.exception("NemoClaw run failed: %s", nc_run_id)
            run = await db.get(Run, nc_run_id)
            if run is not None:
                run.status = "error"
            await emit(SSEEventType.RUN_ERROR, "NemoClaw error")
            await db.commit()
        finally:
            clear_cancel(nc_run_id)
            if queue:
                queue.put_nowait(None)


class _Done(Exception):
    """Clean exit when cancelled."""


async def _generate_angles(topic: str, settings: Settings) -> list[str]:
    """Ask the 120B model for 4 unique expert research angles with current date context."""
    from datetime import date
    today = date.today().strftime("%B %Y")  # e.g. "May 2026"

    system = "You are an expert research strategist. Respond with JSON only."
    prompt = (
        f"Topic: \"{topic}\"\n"
        f"Today's date: {today}\n\n"
        "Generate 4 highly specific, UP-TO-DATE research angles that reveal expert and analytical "
        "perspectives beyond basic public opinion. Use the current date to ask for recent data, "
        "2025-2026 studies, latest news, and current trends. Focus on: "
        "recent data/statistics, expert critique, current controversies, "
        "latest regulatory/policy developments, or technical deep dives.\n"
        "Each angle should be a specific search query using 'recent', 'latest', '2025', '2026' where appropriate.\n"
        "Return: {\"angles\": [\"...\", \"...\", \"...\", \"...\"]}"
    )
    fallback = [
        f"{topic} latest expert analysis 2026",
        f"{topic} recent data statistics study 2025 2026",
        f"{topic} current criticism expert perspective",
        f"{topic} latest regulatory policy developments",
    ]
    try:
        payload = await ollama_generate(
            prompt, system=system,
            model=settings.nemoclaw_model,
            base_url=settings.ollama_base_url,
        )
        angles = payload.get("angles", [])
        if isinstance(angles, list):
            cleaned = [str(a).strip() for a in angles if str(a).strip()]
            return cleaned[:4] or fallback
    except Exception:
        pass
    return fallback


async def _fetch_one(url: str, sem: asyncio.Semaphore) -> tuple[str, list[dict], float]:
    started = perf_counter()
    async with sem:
        try:
            items = await fetch_items(url)
            snippets = [{"text": item.snippet, "url": item.url} for item in items[:3]]
        except Exception:
            snippets = []
    return url, snippets, round((perf_counter() - started) * 1000, 1)


async def _expert_synthesis(
    topic: str,
    angles: list[str],
    snippets: list[dict],
    settings: Settings,
) -> dict:
    """Ask NemoClaw to produce an expert analysis with topic-specific controversy categories."""
    evidence_text = "\n".join(f"- {s['text'][:300]}" for s in snippets[:20])
    if not evidence_text:
        evidence_text = "No evidence gathered."

    system = "You are a senior research analyst. Respond with JSON only."
    prompt = (
        f"Topic: \"{topic}\"\n"
        f"Research angles explored: {', '.join(angles)}\n\n"
        f"Evidence gathered:\n{evidence_text}\n\n"
        "Produce an expert analysis. For the 'categories' field, identify the 2-3 most "
        "controversial, debated, or important dimensions SPECIFIC to this topic. "
        "Do NOT use generic 'Opportunities' and 'Risks' — instead find the actual fault lines "
        "of debate. Examples: for a tech product use 'Performance claims vs Real-world results'; "
        "for a political figure use 'Supporter arguments vs Critic arguments'; "
        "for a health topic use 'Scientific consensus vs Public perception'.\n\n"
        "Return:\n"
        "{\n"
        '  "summary": "3-4 sentence expert overview",\n'
        '  "key_findings": ["finding 1", "finding 2", "finding 3"],\n'
        '  "categories": [\n'
        '    {"name": "Specific controversy dimension 1", "side": "positive", "items": ["point 1", "point 2"]},\n'
        '    {"name": "Specific controversy dimension 2", "side": "negative", "items": ["point 1", "point 2"]}\n'
        "  ],\n"
        '  "verdict": "one-line expert verdict"\n'
        "}"
    )
    try:
        payload = await ollama_generate(
            prompt, system=system,
            model=settings.nemoclaw_model,
            base_url=settings.ollama_base_url,
        )
        categories = payload.get("categories", [])
        if not isinstance(categories, list):
            categories = []
        return {
            "type": "nemoclaw",
            "summary": str(payload.get("summary", "Analysis unavailable.")),
            "key_findings": [str(f) for f in payload.get("key_findings", [])],
            "categories": [c for c in categories if isinstance(c, dict)],
            "verdict": str(payload.get("verdict", "")),
        }
    except Exception:
        return {
            "type": "nemoclaw",
            "summary": "Expert synthesis unavailable.",
            "key_findings": [], "categories": [], "verdict": "",
        }


def _domain(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc.removeprefix("www.")
