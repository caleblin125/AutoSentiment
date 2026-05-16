# AutoSentiment OpenCode Handoff

Last updated: 2026-05-16 16:36 America/Los_Angeles.

## Immediate Runtime State

- Repo: `/home/asus/AutoSentiment`
- Branch: `main`
- Backend restarted and verified:
  - URL: `http://localhost:8000`
  - Health check: `GET /api/health` returns `{"status":"ok"}`
  - Log: `/tmp/autosentiment-backend.log`
  - Current process command includes `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Frontend restarted and verified:
  - URL: `http://localhost:5173`
  - Health check: `curl -o /dev/null -w 'HTTP %{http_code}' http://localhost:5173` returns `HTTP 200`
  - Log: `/tmp/autosentiment-frontend.log`
  - Current process command includes `vite --host 0.0.0.0 --port 5173`
- Agent coordination files are local-only and ignored by Git:
  - `AGENT_ACTIVE.md`
  - `AGENT_LOG.md`
  - `AGENT_MAILBOX.md`
  - `AGENT_TASKS.md`
  - `NEXT_AGENT_OBJECTIVES.md`
  - `agent-run`
  - `agent-relay`
  - `.claude/`

## User Instructions To Preserve

- Automatically test changes.
- When a bug is found, write a testbench for that specific problem and adjacent cases.
- Commit focused changes after testing.
- Keep API keys private and out of Git history. Do not commit `.env`, local DBs, logs, or real keys.
- Do not rewrite Git history.
- Do not delete local agent files unless explicitly asked; remove from Git tracking only when needed.
- Keep code clean and readable. Add comments only where they clarify non-obvious behavior.
- Continue improving commercial usefulness for entertainment/product/public-event analysis: useful charts, source diversity, evidence, fact checking, chronology, graph exploration, and location sentiment.

## Current Product Summary

AutoSentiment is a local FastAPI + React application for citation-backed sentiment, evidence, and fact analysis.

Implemented capabilities include:
- Multi-tab frontend with run history, saved searches, session restore, export actions, and model controls.
- Research depth presets: Quick, Standard, Deep, Exhaustive.
- Expand/search-more flow that keeps existing analysis visible until expanded analysis completes.
- Brave Search quota tracking and one-request-at-a-time usage.
- Supplemental no-key source APIs: GDELT, Hacker News Algolia, Wikipedia OpenSearch, arXiv, and limited Reddit fallback.
- URL/source diversity cap so Reddit does not dominate when other platforms are available.
- Report tabs: Summary, Topics, Timeline, Evidence, Claims, Graph, Performance.
- Topic detail panels with summaries and verifiable source links.
- Source Mix grouped by category, outlet/domain, and source links.
- Source-time sentiment history based on actual source/mentioned dates, not run dates.
- Heuristic location sentiment map with certainty labels.
- Graph mode with sentiment-colored source nodes, theme/aspect evidence popovers, zoom/pan, pinning, filtering, and source link popovers.
- NemoClaw autonomous analysis and model selection surfaces.
- Local TUI and testbench infrastructure from prior work.

## Most Recent Fix

Commit `ff3a7a4 Fix short sentiment batch results` fixed user-visible `batch miss` summaries.

Root cause:
- The sentiment batch analyzer sometimes received fewer model results than snippets submitted.
- The orchestrator filled missing entries with literal summary text `batch miss`.
- The shared Ollama JSON parser only accepted top-level objects, even though batch prompts sometimes produced top-level arrays.

Fix:
- Batch prompt now requests `{"results": [...]}`.
- Batch parser accepts wrapped results, top-level arrays, numbered dictionaries, and alternate keys such as `items`, `sentiments`, and `classifications`.
- Short batch responses are padded with neutral `neutral signal` results.
- Internal fallback summaries no longer expose `batch miss` or `batch parse error`.
- Existing local DB rows with `summary='batch miss'` were updated to `neutral signal`; `backend/data/app.db` remains ignored and uncommitted.

Tests run for that fix:

```bash
cd /home/asus/AutoSentiment/backend
source .venv/bin/activate
python3 -m pytest tests/test_llm.py tests/test_reliability.py -q
python3 -m pytest tests/test_orchestrator.py::test_run_research_deduplicates_identical_sentiment_snippets -q
```

Results:
- `31 passed` for LLM/reliability.
- Orchestrator regression passed.

## Most Recent Runtime Incident

The browser showed `NetworkError when attempting to fetch resource` immediately after a restart attempt. Both backend and frontend had exited, so the frontend could not reach any API resource.

Resolution:
- Restarted backend and frontend with `setsid` so the processes survive after the launching shell exits.
- Verified:
  - `curl http://localhost:8000/api/health` returned `{"status":"ok"}`.
  - `curl http://localhost:8000/api/models` returned the Ollama model list.
  - `curl -o /dev/null -w 'HTTP %{http_code}' http://localhost:5173` returned `HTTP 200`.

If the same browser error returns, first check whether both ports are alive:

```bash
ps -eo pid,cmd | rg 'uvicorn app.main|vite --host|npm run dev'
curl -sS --max-time 5 http://localhost:8000/api/health
curl -sS --max-time 5 -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:5173
tail -80 /tmp/autosentiment-backend.log
tail -80 /tmp/autosentiment-frontend.log
```

## Run Commands

Restart backend:

```bash
cd /home/asus/AutoSentiment/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Restart frontend:

```bash
cd /home/asus/AutoSentiment/frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

Durable background restart pattern:

```bash
setsid bash -lc 'cd /home/asus/AutoSentiment/backend && source .venv/bin/activate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000' \
  > /tmp/autosentiment-backend.log 2>&1 < /dev/null &

setsid bash -lc 'cd /home/asus/AutoSentiment/frontend && exec npm run dev -- --host 0.0.0.0 --port 5173' \
  > /tmp/autosentiment-frontend.log 2>&1 < /dev/null &
```

Verify runtime:

```bash
curl -s http://localhost:8000/api/health
curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:5173
```

## Validation Commands

Backend focused or full:

```bash
cd /home/asus/AutoSentiment/backend
source .venv/bin/activate
python3 -m pytest tests/test_llm.py tests/test_reliability.py -q
python3 -m pytest tests/ -q
```

Frontend:

```bash
cd /home/asus/AutoSentiment/frontend
npm run lint
npm run build
npm run test:e2e
```

Secret scan before commit:

```bash
git diff --cached --unified=0 | rg -n "^\\+.*(sk-[A-Za-z0-9]|api[_-]?key\\s*=\\s*['\\\"][^'\\\"]+|BRAVE_API_KEY=.+|X-Subscription-Token.*[A-Za-z0-9]{20,})" || true
```

## Important Files

- `SPEC.md`: project specification.
- `prompt.txt`: original track/objective prompt.
- `README.md`: user-facing setup and product docs.
- `docs/HANDOFF.md`: previous general handoff.
- `OPENCODE_HANDOFF.md`: this handoff.
- `backend/app/agents/orchestrator.py`: pipeline orchestration.
- `backend/app/agents/light_queue.py`: per-item and batch sentiment analysis.
- `backend/app/agents/ollama.py`: shared Ollama JSON and streaming wrapper.
- `backend/app/tools/search.py`: Brave Search integration and rate limiting.
- `backend/app/tools/media_apis.py`: no-key supplemental APIs.
- `backend/app/reports/builder.py`: counts, charts, topics, graph, chronology, location sentiment.
- `frontend/src/components/RunView.tsx`: run creation, expansion, model controls, status area.
- `frontend/src/components/ReportView.tsx`: report tabs and report sections.
- `frontend/src/components/ForceGraph.tsx`: interactive graph view.
- `frontend/src/components/EventTimeline.tsx`: live run timeline and fetched URL batching.

## Known Risks And Priorities

1. SQLite is still the largest production risk for commercial multi-user use. PostgreSQL migration is the next serious hardening step.
2. Location sentiment is heuristic. It labels certainty, but a real extraction/geocoding layer would be more reliable.
3. LLM search plan preview can take up to five seconds before template fallback if Ollama is saturated or unavailable.
4. The aggregate backend suite can run long; if it appears stuck, run focused tests first and investigate rather than leaving pytest running.
5. Continue source diversification beyond Reddit and add tests that fail when one platform dominates source mix.
6. Add endpoint/frontend tests for `/api/models` if model selector behavior is changed.
7. Consider adding observability around batch result length mismatch counts so future model output drift is visible without leaking internal messages into reports.

## Git Hygiene Notes

- Do not use destructive Git commands.
- Agent files are ignored and should stay local-only.
- Keep `backend/data/app.db`, logs, build output, caches, and `.env` files untracked.
- Prefer small commits with messages that describe behavior changes.
