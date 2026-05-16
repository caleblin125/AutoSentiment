"""120B model (nemotron-3-super via Ollama) — query expansion and final synthesis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.ollama import ollama_generate

if TYPE_CHECKING:
    from app.core.config import Settings


async def expand_queries(topic: str, *, settings: Settings) -> list[str]:
    """Call the 120B model to produce 5 search query variants for the topic."""
    system = "You are a search query generator. Respond with JSON only."
    prompt = (
        "Generate 5 search queries to find public opinions, reviews, and discussions "
        f"about: {topic}\n"
        "Include variants targeting Reddit, reviews, and news.\n"
        "Return exactly: {\"queries\": [\"...\", \"...\", \"...\", \"...\", \"...\"]}"
    )
    fallback = [topic, f"{topic} reddit", f"{topic} review", f"{topic} news", f"{topic} opinions"]

    try:
        payload = await ollama_generate(
            prompt,
            system=system,
            model=settings.nemoclaw_model,
            base_url=settings.ollama_base_url,
        )
        queries = payload["queries"]
        if not isinstance(queries, list):
            return fallback
        queries = [str(query).strip() for query in queries if str(query).strip()]
        return queries[:5] or fallback
    except Exception:
        return fallback


async def synthesize_report(
    topic: str,
    chunks_summary: list[dict],
    counts: dict,
    *,
    settings: Settings,
) -> dict:
    """Call the 120B model to produce themes list and narrative paragraph.

    `chunks_summary` is a list of {label, summary, url, source_type} dicts.
    `counts` is the pre-computed percentage breakdown — the model must not recalculate it.
    Returns a dict with keys: themes (list[str]), narrative (str).
    """
    overall = counts.get("overall", {})
    total = int(overall.get("total", 0))
    pos_pct = round(float(overall.get("positive", 0.0)) * 100)
    neu_pct = round(float(overall.get("neutral", 0.0)) * 100)
    neg_pct = round(float(overall.get("negative", 0.0)) * 100)

    sample_opinions = "\n".join(
        f"- {chunk.get('label', 'neutral')}: {chunk.get('summary', '')} "
        f"({chunk.get('source_type', 'unknown')})"
        for chunk in chunks_summary
    )
    if not sample_opinions:
        sample_opinions = "- neutral: no sample opinions available (unknown)"

    system = "You are a research analyst summarising public sentiment. Respond with JSON only."
    prompt = (
        f"Topic: {topic}\n"
        f"Analysed {total} items: {pos_pct}% positive, {neu_pct}% neutral, "
        f"{neg_pct}% negative.\n\n"
        f"Sample opinions:\n{sample_opinions}\n\n"
        "Return exactly: {\"themes\": [\"theme1\", \"theme2\", \"theme3\"], "
        "\"narrative\": \"2-3 sentence plain-English summary of overall sentiment "
        "and key drivers\"}"
    )

    try:
        payload = await ollama_generate(
            prompt,
            system=system,
            model=settings.nemoclaw_model,
            base_url=settings.ollama_base_url,
        )
        themes = payload.get("themes", [])
        if not isinstance(themes, list):
            themes = []
        return {
            "themes": [str(theme) for theme in themes],
            "narrative": str(payload.get("narrative", "Synthesis unavailable.")),
        }
    except Exception:
        return {"themes": [], "narrative": "Synthesis unavailable."}
