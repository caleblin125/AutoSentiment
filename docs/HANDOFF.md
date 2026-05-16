# AutoSentiment Handoff

Last updated: 2026-05-16 16:15 America/Los_Angeles.

## Operating Instructions For Next Agent

- Work in `/home/asus/AutoSentiment`.
- Read `SPEC.md`, `prompt.txt`, `README.md`, `NEXT_AGENT_OBJECTIVES.md`, and this file before changing behavior.
- Automatically test changes. When a bug appears, add or update a testbench for that bug and adjacent cases.
- Commit focused changes after tests pass. Do not leave a dirty tree at handoff.
- Never commit secrets. Keep Brave and auth keys in `backend/.env` or environment variables only. Secret-scan staged diffs before commit.
- Preserve user or other-agent changes. Do not revert unrelated work without explicit permission.
- Prefer clean, readable code with comments only where they clarify non-obvious behavior.

## Current Product State

AutoSentiment is a local FastAPI + React application for citation-backed sentiment and evidence analysis across brands, entertainment products, public events, policy topics, and financial markets.

Core features currently implemented:
- Research depth presets: Quick, Standard, Deep, Exhaustive, with expansion after a completed run.
- Expand search keeps the prior report visible while new evidence is gathered, then swaps in the merged report on completion.
- Brave Search is rate limited and quota-tracked. Supplemental no-key sources include GDELT, Hacker News Algolia, Wikipedia OpenSearch, arXiv, and limited Reddit fallback.
- Source diversity is enforced before extraction so Reddit cannot consume the run budget when other sources exist.
- Reports include Summary, Topics, Timeline, Evidence, Claims, Graph, and Performance tabs.
- Timeline rows fold fetched URLs into expandable batches and no longer visually overlap subsequent rows.
- Source-time sentiment history uses explicit dates from evidence text, falling back to retrieval date with certainty labels.
- Location sentiment is heuristically mapped from mentioned locations or source domain TLDs and shown on an interactive map with certainty.
- Source Mix is hierarchical by category, outlet/domain, and source links.
- Topics open a detail panel with summary points and verifiable source links.
- Graph mode uses sentiment-colored source nodes rather than separate positive/neutral/negative circles. Theme/aspect nodes open detail popovers.
- Model controls can use `/api/models` to list local Ollama models and set NemoClaw, sentiment, and suggestion model overrides.
- TUI, NemoClaw self-analysis, saved searches, session restore, export, and comparison workflows exist from prior work.

## Recent Work In This Session

- Fixed search planner tests so they do not call live Ollama during unit tests.
- Added `asyncio.wait_for(..., timeout=5.0)` around LLM search-query planning so a missing Ollama server falls back to templates instead of hanging.
- Added coverage for successful LLM-generated search plans.
- Completed frontend model dropdown wiring with a reusable `ModelSelect` component.
- Cleaned graph typings after the graph redesign removed sentiment nodes from the `GraphNode.kind` union.
- Updated Playwright fixture data to match the current graph schema.

## Validation Commands

Run from a clean shell:

```bash
cd /home/asus/AutoSentiment/backend
source .venv/bin/activate
python3 -m pytest tests/ -q

cd /home/asus/AutoSentiment/frontend
npm run lint
npm run build
npm run test:e2e
```

Before committing:

```bash
git diff --cached | rg -n "sk-[A-Za-z0-9]|api[_-]?key\s*=\s*['\"][^'\"]+|BRAVE_API_KEY=.+|X-Subscription-Token.*[A-Za-z0-9]{20,}" || true
```

## Run Commands

Backend:

```bash
cd /home/asus/AutoSentiment/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd /home/asus/AutoSentiment/frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

## Known Risks And Next Priorities

1. Search plan preview now may ask the LLM for smarter queries. It has a 5 second fallback, but UX may still feel slower than pure template previews if Ollama is busy.
2. Location extraction is heuristic. It labels certainty but should eventually use a real geocoder/location extractor.
3. SQLite remains the main production bottleneck. PostgreSQL is the likely next production hardening step.
4. Continue reducing Reddit dominance with additional official/public APIs and better ranking.
5. Add tests for `/api/models` and model dropdown behavior if this feature is expanded.
6. Continue graph UX work: clearer clustering, source credibility overlays, and evidence-driven navigation.

## Current Verification Snapshot

Most recent checks run during this handoff:
- Backend targeted planner/report tests: passed.
- Frontend lint: passed.
- Frontend production build: passed.

Run the full backend and Playwright suites before the final commit if additional files are changed.
