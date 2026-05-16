"""NemoClaw — query expansion, synthesis, and search-angle suggestions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.ollama import ollama_generate

if TYPE_CHECKING:
    from app.core.config import Settings

# Fastest available model for low-latency suggestion generation.
_SUGGEST_MODEL = "deepseek-r1:14b"


async def suggest_angles(query: str, *, settings: Settings) -> list[str]:
    """Return 5 refined research-angle suggestions for the given query string.

    Uses the fast small model for sub-second latency when the user is typing.
    """
    system = "You generate research topic suggestions. Respond with JSON only, no markdown."
    prompt = (
        f"The user is researching: \"{query}\"\n"
        "Suggest 5 specific, searchable research angles or related sub-topics "
        "that would yield useful public-sentiment data. Be concise and concrete.\n"
        "Return exactly: {\"suggestions\": [\"...\", \"...\", \"...\", \"...\", \"...\"]}"
    )
    fallback = [
        f"{query} public opinion",
        f"{query} user reviews",
        f"{query} expert analysis",
        f"{query} recent controversy",
        f"{query} market sentiment",
    ]
    try:
        payload = await ollama_generate(
            prompt,
            system=system,
            model=_SUGGEST_MODEL,
            base_url=settings.ollama_base_url,
        )
        suggestions = payload.get("suggestions", [])
        if isinstance(suggestions, list):
            cleaned = [str(s).strip() for s in suggestions if str(s).strip()]
            return cleaned[:5] or fallback
    except Exception:
        pass
    return fallback


async def expand_queries(
    topic: str,
    *,
    settings: Settings,
    freshness: str | None = None,
    cancel_check: "Callable[[], bool] | None" = None,
) -> list[str]:
    """Call the 120B model to produce 5 search query variants for the topic.

    freshness controls time-scoping:
      pm = past month  → queries must NOT include years > 1 month ago
      pw = past week   → queries must NOT include specific years
      pd = past day    → queries must NOT include specific years
      py = past year   → allow current + prior year only
      None             → no date restriction
    """
    from collections.abc import Callable  # noqa: PLC0415
    from datetime import date
    today = date.today().strftime("%B %Y")

    freshness_rule = {
        "pm": f"Today is {today}. ONLY include queries for the past month. Do NOT add years like 2023 or 2024. Omit any year suffix entirely or use '{date.today().year}' at most.",
        "pw": f"Today is {today}. ONLY include queries for the past week. Omit specific years.",
        "pd": f"Today is {today}. ONLY include queries for the past 24 hours. Omit specific years.",
        "py": f"Today is {today}. Include queries for the past year; use only {date.today().year} or {date.today().year - 1} if a year is needed.",
    }.get(freshness or "", f"Today is {today}.")

    system = "You are a search query generator. Respond with JSON only."
    prompt = (
        f"Generate 5 search queries to find public opinions, reviews, and discussions "
        f"about: {topic}\n"
        f"{freshness_rule}\n"
        "Include variants targeting reviews, news, and discussion forums.\n"
        "Return exactly: {\"queries\": [\"...\", \"...\", \"...\", \"...\", \"...\"]}"
    )
    fallback = [topic, f"{topic} review", f"{topic} news", f"{topic} opinions", f"{topic} discussion"]

    try:
        payload = await ollama_generate(
            prompt, system=system,
            model=settings.nemoclaw_model,
            base_url=settings.ollama_base_url,
            cancel_check=cancel_check,
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
    cancel_check: "Callable[[], bool] | None" = None,
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
        "Return exactly this JSON (no extra keys, no markdown):\n"
        "{\n"
        '  "themes": ["theme1", "theme2", "theme3"],\n'
        '  "narrative": "2-3 sentence plain-English summary",\n'
        '  "impacts": [\n'
        '    {"direction": "positive", "description": "..."},\n'
        '    {"direction": "negative", "description": "..."}\n'
        "  ],\n"
        '  "reasons": ["reason the sentiment is what it is", "..."],\n'
        '  "arguments": [\n'
        '    {"claim": "...", "side": "for"},\n'
        '    {"claim": "...", "side": "against"}\n'
        "  ]\n"
        "}"
    )

    try:
        payload = await ollama_generate(
            prompt,
            system=system,
            model=settings.nemoclaw_model,
            base_url=settings.ollama_base_url,
            cancel_check=cancel_check,
        )
        themes = payload.get("themes", [])
        if not isinstance(themes, list):
            themes = []
        impacts = payload.get("impacts", [])
        if not isinstance(impacts, list):
            impacts = []
        reasons = payload.get("reasons", [])
        if not isinstance(reasons, list):
            reasons = []
        arguments = payload.get("arguments", [])
        if not isinstance(arguments, list):
            arguments = []
        return {
            "themes": [str(t) for t in themes],
            "narrative": str(payload.get("narrative", "Synthesis unavailable.")),
            "impacts": [i for i in impacts if isinstance(i, dict)],
            "reasons": [str(r) for r in reasons],
            "arguments": [a for a in arguments if isinstance(a, dict)],
        }
    except Exception:
        return {"themes": [], "narrative": "Synthesis unavailable.", "impacts": [], "reasons": [], "arguments": []}
