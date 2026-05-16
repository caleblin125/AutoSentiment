"""Self-analysis: use the 120B NemoClaw model to audit the AutoSentiment project.

This is a meta-test — NemoClaw reads the project's own documentation and code
structure, then produces a structured assessment with feedback, suggestions,
problems, and concrete improvements.

Run with:
    cd backend && source .venv/bin/activate
    RUN_SELF_ANALYSIS=1 python3 -m pytest tests/test_self_analysis.py -v -s

The test is skipped by default to avoid burning LLM credits on every CI run.
When enabled, it prints the full analysis to stdout and writes it to
`/tmp/autosentiment_self_analysis.md`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Gather project context from key files (avoid huge files like App.css).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _read(path: str) -> str:
    p = _PROJECT_ROOT / path
    if p.exists():
        return p.read_text()[:10_000]  # cap each file at 10KB
    return f"(file not found: {path})"


def _count(path: str, ext: str) -> int:
    return len(list((_PROJECT_ROOT / path).rglob(f"*.{ext}")))


def _build_context() -> str:
    """Build a condensed project overview for the model to analyze."""
    py_files = _count("backend/app", "py")
    tsx_files = _count("frontend/src", "tsx")
    test_count = len(list((_PROJECT_ROOT / "backend/tests").rglob("test_*.py")))

    # Read key files (truncated).
    readme = _read("README.md")[:6000]
    objectives = _read("NEXT_AGENT_OBJECTIVES.md")[:6000]
    spec = _read("SPEC.md")[:4000]
    tasks = _read("AGENT_TASKS.md")[:3000]
    orchestrator = _read("backend/app/agents/orchestrator.py")[:4000]
    builder = _read("backend/app/reports/builder.py")[:3000]

    return f"""
## Project: AutoSentiment

### Overview
{readme}

### Architecture
- {py_files} Python backend modules (FastAPI + SQLAlchemy async + SQLite)
- {tsx_files} TypeScript frontend components (Vite + React)
- {test_count} backend test files
- LLM: nemotron-3-nano (30B sentiment), nemotron-3-super (120B synthesis/NemoClaw), deepseek-r1:14b (suggestions)
- Search: Brave Search API (1 req/s, 2k/month free plan) + 5 free media APIs (GDELT, HN, Wikipedia, arXiv, Reddit)

### Objectives & Status
{objectives}

### Original Spec
{spec}

### Current Task Queue
{tasks}

### Orchestrator (core pipeline)
```python
{orchestrator}
```

### Report Builder (analysis engine)
```python
{builder}
```
"""


_PROMPT = """You are an expert software architect and code reviewer auditing the AutoSentiment project.
The project is a multi-source public sentiment intelligence tool — it searches the web, fetches articles,
runs LLM-based sentiment analysis, and visualizes findings in a real-time dashboard.

Below is the project's documentation, code, and status. Analyze it thoroughly and produce a structured
assessment in this EXACT JSON format:

{
  "verdict": "1-2 sentence overall assessment of project health and maturity",
  "strengths": ["list", "of", "key", "strengths"],
  "problems": [
    {"severity": "high|medium|low", "area": "backend|frontend|ux|performance|reliability|testing|architecture", "description": "specific problem", "impact": "why it matters"}
  ],
  "suggestions": [
    {"priority": "high|medium|low", "area": "...", "description": "concrete improvement", "effort": "small|medium|large"}
  ],
  "missing_features": ["features the project clearly needs but doesn't have"],
  "risks": ["risks that could cause production issues or user dissatisfaction"],
  "architecture_notes": "assessment of the architecture — what's well-designed, what's concerning"
}

Be brutally honest. Point out real problems, not platitudes. Base everything on the actual code and docs provided.
Focus on: correctness, performance, UX, maintainability, scalability, security, and real-world usability.

Project context:
"""


@pytest.mark.skipif(
    os.getenv("RUN_SELF_ANALYSIS") != "1",
    reason="Set RUN_SELF_ANALYSIS=1 to run the self-analysis test (uses LLM credits).",
)
@pytest.mark.asyncio
async def test_nemoclaw_self_analysis() -> None:
    """Feed project docs to the 120B model, get a structured audit back."""
    from app.agents.ollama import ollama_generate
    from app.core.config import Settings

    settings = Settings()
    context = _build_context()

    print("\n" + "=" * 72)
    print("  AutoSentiment — NemoClaw Self-Analysis")
    print("  Model:", settings.nemoclaw_model)
    print("  Context size:", len(context), "chars")
    print("=" * 72 + "\n")
    print("Sending to model → waiting for response (this may take 2-5 minutes)...\n")

    prompt = _PROMPT + context

    try:
        raw = await ollama_generate(
            prompt,
            system="You are a senior software architect. Respond with JSON only. No markdown, no explanation.",
            model=settings.nemoclaw_model,
            base_url=settings.ollama_base_url,
        )
    except Exception as exc:
        pytest.fail(f"Model call failed: {exc}")

    # Parse the response.
    if isinstance(raw, str):
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from the response.
            import re
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pytest.fail(f"Could not parse model response as JSON:\n{raw[:500]}")
            else:
                pytest.fail(f"No JSON found in response:\n{raw[:500]}")
    else:
        result = raw

    # Validate structure.
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "verdict" in result, f"Missing 'verdict' key: {list(result.keys())}"
    assert "problems" in result, "Missing 'problems' key"
    assert "suggestions" in result, "Missing 'suggestions' key"

    # ── Print the analysis ───────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  VERDICT")
    print("=" * 72)
    print(f"\n  {result.get('verdict', 'N/A')}\n")

    print("=" * 72)
    print("  STRENGTHS")
    print("=" * 72)
    for s in result.get("strengths", []):
        print(f"  ✓ {s}")

    print("\n" + "=" * 72)
    print("  PROBLEMS")
    print("=" * 72)
    for p in result.get("problems", []):
        sev = p.get("severity", "?").upper()
        area = p.get("area", "?")
        desc = p.get("description", "?")
        impact = p.get("impact", "")
        print(f"  [{sev}] [{area}] {desc}")
        if impact:
            print(f"         → {impact}")

    print("\n" + "=" * 72)
    print("  SUGGESTIONS")
    print("=" * 72)
    for s in result.get("suggestions", []):
        pri = s.get("priority", "?").upper()
        area = s.get("area", "?")
        desc = s.get("description", "?")
        effort = s.get("effort", "?")
        print(f"  [{pri}] [{area}] ({effort} effort) {desc}")

    print("\n" + "=" * 72)
    print("  MISSING FEATURES")
    print("=" * 72)
    for f in result.get("missing_features", []):
        print(f"  ✗ {f}")

    print("\n" + "=" * 72)
    print("  RISKS")
    print("=" * 72)
    for r in result.get("risks", []):
        print(f"  ⚠ {r}")

    print("\n" + "=" * 72)
    print("  ARCHITECTURE NOTES")
    print("=" * 72)
    print(f"\n  {result.get('architecture_notes', 'N/A')}\n")

    # ── Write to file ────────────────────────────────────────────────────
    output_path = Path("/tmp/autosentiment_self_analysis.md")
    lines = [
        "# AutoSentiment — NemoClaw Self-Analysis",
        "",
        f"**Model**: {settings.nemoclaw_model}",
        f"**Date**: {__import__('datetime').datetime.now().isoformat()}",
        "",
        "## Verdict",
        "",
        result.get("verdict", "N/A"),
        "",
        "## Strengths",
        "",
    ]
    for s in result.get("strengths", []):
        lines.append(f"- {s}")
    lines += ["", "## Problems", ""]
    for p in result.get("problems", []):
        lines.append(f"- **[{p.get('severity', '?').upper()}] [{p.get('area', '?')}]** {p.get('description', '?')}")
        if p.get("impact"):
            lines.append(f"  - Impact: {p['impact']}")
    lines += ["", "## Suggestions", ""]
    for s in result.get("suggestions", []):
        lines.append(f"- **[{s.get('priority', '?').upper()}] [{s.get('area', '?')}]** ({s.get('effort', '?')} effort) {s.get('description', '?')}")
    lines += ["", "## Missing Features", ""]
    for f in result.get("missing_features", []):
        lines.append(f"- {f}")
    lines += ["", "## Risks", ""]
    for r in result.get("risks", []):
        lines.append(f"- {r}")
    lines += ["", "## Architecture Notes", "", result.get("architecture_notes", "N/A")]

    output_path.write_text("\n".join(lines))
    print(f"\n  Full analysis written to {output_path}")
    print("=" * 72 + "\n")
