# AutoSentiment Next Agent Objectives

Last updated: 2026-05-16.

This document is the working handoff for the next agent. Read `/home/asus/HANDOFF.md`, `README.md`, and this file before making changes. The product goal is to turn AutoSentiment into a commercially usable sentiment, evidence, and fact-analysis tool for entertainment products, brands, public events, and public-interest topics.

## Operating Rules

1. Commit regularly.
2. Make small, focused commits with clear messages.
3. Do not amend previous commits unless the user explicitly asks.
4. Before each commit, run the relevant automated tests and inspect `git status --short`.
5. When a bug or unexpected runtime issue appears, write or update a focused testbench for that specific issue and adjacent behavior before considering the fix complete.
6. Always run backend tests after backend changes:

```bash
cd /home/asus/AutoSentiment/backend
source .venv/bin/activate
python3 -m pytest tests/ -v
```

7. Always run frontend validation after frontend changes:

```bash
cd /home/asus/AutoSentiment/frontend
npm run lint
npm run build
```

8. For cross-cutting changes, run backend tests, frontend lint, and frontend build.
9. Do at least one manual smoke check for user-facing workflow changes. Start or restart servers as needed:

```bash
cd /home/asus/AutoSentiment/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd /home/asus/AutoSentiment/frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

10. Keep API keys private. Never commit `backend/.env`, `frontend/.env`, secrets, tokens, or real API keys.
11. Before committing, run a staged diff secret check:

```bash
git diff --cached | rg -n "sk-[A-Za-z0-9]|api[_-]?key\s*=\s*['\"][^'\"]+|BRAVE_API_KEY=.+|X-Subscription-Token.*[A-Za-z0-9]{20,}"
```

12. Respect the Brave free-plan limit. Brave is one query per second and about 2,000 queries per month. Do not add burst search behavior that violates this. Queue searches and dispatch them one at a time.
13. Do not revert unrelated user changes. There may be unrelated deleted docs or scratch files in the working tree.
14. Use `rg` and `rg --files` for discovery. Prefer `apply_patch` for manual edits.
15. Update `/home/asus/HANDOFF.md` or this file at the end of long sessions with what changed, what passed, and what remains.

## Current State

AutoSentiment already supports:

- FastAPI backend with async SQLite persistence.
- SSE event stream with replay.
- Create, cancel, expand, history, suggestions, dev stats, and NemoClaw endpoints.
- Brave search with 1/sec rate limit and per-request count clamping.
- Multi-source fetching and source classification.
- Ollama-backed query expansion, sentiment, synthesis, and suggestions.
- Per-item sentiment with bounded parallelism.
- Report generation with counts, quotes, source facts, aspects, idea graph, timing breakdown, and synthesis.
- React frontend with multi-tab search, history, live timeline, report display, evidence modal, graph, and dev tools.
- Backend test suite and frontend lint/build validation.

Known performance profile from recent successful runs:

- Brave search is not the main bottleneck.
- Fetching is usually modest unless individual URLs hang.
- Sentiment analysis and synthesis are the dominant runtime costs.
- Larger Brave query counts can improve source coverage but will not meaningfully speed up runs under the free-plan rate limit.

## Objective 1: Configurable Search Depth and Expandable Depth

Instead of only having the expand search option, add a setting at the start to decide how many queries to make and how in depth to make it. Allow for this to be adjusted to larger values after the initial search has been run so that the search can be expanded later. End of Objective.

Implementation requirements:

- Add a `search_depth` or `research_depth` field to `RunRequest`.
- Support presets such as `quick`, `standard`, `deep`, and `exhaustive`.
- Add explicit numeric controls where useful:
  - query count budget
  - URL budget
  - item budget
  - source diversity target
  - synthesis sample size
- Persist the chosen depth on the `Run` model or in `Run.report.metadata`.
- Include depth in cache keys so a quick run does not hide a deep run.
- Update `/api/runs/{id}/expand` to accept a larger requested depth instead of blindly doubling budgets.
- Make expansion inherit the original freshness unless the user explicitly changes it.
- Preserve existing evidence and run timeline when expanding.
- Add frontend controls to `RunForm` or per-run controls:
  - initial depth selector
  - "Expand depth" control after a completed run
  - visible budget preview before running
- Add tests:
  - route validation for depth values
  - cache behavior includes depth
  - orchestrator receives correct budgets
  - expand can request deeper search
  - expand inherits freshness by default
  - frontend build catches type/API changes

Commercial value:

- Lets casual users run fast searches.
- Lets analysts run deeper research only when needed.
- Prevents accidental Brave quota burn.

## Objective 2: Search Planning and Quota Management

Build a deliberate search planner rather than an ever-growing static query list.

Requirements:

- Centralize query planning in a testable module.
- Inputs should include topic, freshness, depth, target platforms, geography, language, and use case.
- Output should include ordered queries with purpose labels:
  - official/factual sources
  - public opinion
  - expert reviews
  - complaints
  - social/video/forums
  - international/local angles
- Track estimated Brave query cost before running.
- Show estimated query cost in the UI.
- Add a monthly quota tracker stored locally in SQLite:
  - total Brave queries this month
  - estimated remaining quota
  - warnings before deep runs
- Never exceed one Brave request per second.
- Add tests for query order, deduplication, quota accounting, and rate-limit behavior.

## Objective 3: Chronological Summary and Event Timeline

Add a chronological summary that explicitly states start, end, and important dates.

Requirements:

- Extract dates from fetched snippets, article text, titles, and metadata when available.
- Add a backend `timeline` report section:
  - `start_date`
  - `end_date`
  - `important_dates`
  - `event_summary`
  - `supporting_evidence_ids`
- Include both source publication dates and event dates when distinguishable.
- Make uncertainty explicit when dates are inferred.
- Add UI timeline visualization:
  - compact horizontal timeline for report overview
  - expandable chronological list
  - click event -> evidence modal/source links
- Prompt synthesis to separate chronology from sentiment.
- Add tests:
  - date extraction from common formats
  - no fabricated dates when none are present
  - timeline event links to evidence
  - frontend render/build

Commercial value:

- Entertainment teams can see when sentiment shifted around trailers, reviews, leaks, releases, controversies, interviews, or award announcements.
- Public users can understand how current events unfolded instead of only seeing aggregate sentiment.

## Objective 4: Fact and Evidence Layer

Separate opinion from factual claims and source-of-truth evidence.

Requirements:

- Add a fact extraction stage after fetch or after sentiment:
  - claim text
  - claim type
  - confidence
  - supporting source domains
  - opposing source domains
  - related evidence IDs
- Classify sources:
  - official
  - primary source
  - established news
  - trade publication
  - social media
  - forum/community
  - unknown
- Add credibility signals without pretending to decide truth automatically:
  - source type
  - corroboration count
  - recency
  - directness to original source
- Add a "Fact Check" section:
  - claims with supporting/opposing evidence
  - direct links to primary sources
  - "needs verification" bucket
- Add tests for source classification, claim grouping, and evidence linking.

Commercial value:

- Entertainment teams can distinguish audience perception from verifiable performance, release, box office, review, and platform data.
- Public users can see whether a popular claim is supported by credible sources.

## Objective 5: Entertainment Industry Product Mode

Add a product-specific mode for studios, publishers, game teams, labels, streamers, and brand teams.

Requirements:

- Add use-case selector:
  - entertainment product
  - public current event
  - brand/product
  - policy/civic topic
  - generic research
- For entertainment product mode, prioritize:
  - Reddit fandom/community
  - YouTube reviews/comments via pages and search results
  - Metacritic/OpenCritic/Rotten Tomatoes where legally accessible via normal web pages
  - Steam reviews for games where accessible
  - app store or platform storefront pages where accessible
  - entertainment trades and industry press
- Add domain-specific aspects:
  - story
  - casting
  - performance
  - pacing
  - gameplay
  - monetization
  - marketing
  - launch quality
  - fan trust
  - controversy
  - box office/commercial potential
- Add report sections:
  - audience pulse
  - critic/trade pulse
  - fandom concerns
  - conversion blockers
  - launch risks
  - recommended monitoring queries
- Add tests for mode-specific query planner and aspect extraction.

## Objective 6: Better Charts and Decision Data

Make charts useful for analysts, not just decorative.

Requirements:

- Add chart types:
  - sentiment over time
  - source mix
  - aspect sentiment matrix
  - credibility/source-type distribution
  - claim corroboration matrix
  - volume by date
  - platform comparison
- Add filters:
  - source type
  - date range
  - sentiment
  - aspect
  - credibility tier
  - language/region
- Add export:
  - JSON report
  - CSV evidence table
  - Markdown executive summary
- Add tests for data aggregation functions.

## Objective 7: Better Graph Visualization

Replace the current basic graph with an analyst-grade relationship explorer.

Requirements:

- Persist graph node positions per run.
- Add graph filters:
  - hide zero-count sentiment nodes
  - show only sources/aspects/themes/facts
  - show only credible sources
- Add node detail panels:
  - source domain -> URLs, evidence count, sentiment distribution
  - aspect -> representative quotes and source mix
  - fact/claim -> supporting/opposing evidence
  - event/date -> related sources and sentiment
- Add clustering:
  - topic center
  - chronological events
  - aspects
  - claims
  - sources
- Add tests for graph construction and source/evidence linking.

## Objective 8: Faster Runs

Use timing telemetry to optimize actual bottlenecks.

Requirements:

- Keep stage timing metrics in reports.
- Add item-level timing outlier detection.
- Add timeout around URL fetch operations.
- Add per-domain fetch caps to prevent one source from dominating.
- Tune `LIGHT_QUEUE_MAX_PARALLEL` based on observed model throughput.
- Cache sentiment by normalized snippet hash.
- Cache fetched URL text with timestamp.
- Cache Brave result URLs per query/freshness/depth.
- Bound synthesis prompt size by depth.
- Add tests:
  - cache hit behavior
  - timeout behavior
  - no duplicate sentiment calls for identical snippets
  - expanded runs reuse previous evidence

Important note:

- Increasing Brave to 50 queries per second is not valid for the free plan and would not fix the current bottleneck. The current slow stages are sentiment and synthesis. More Brave queries may improve coverage, but they should be queued at one request per second and only run when the selected depth justifies the quota cost.

## Objective 9: Better Evidence Storage and Inspection

Make every answer traceable.

Requirements:

- Store source title, domain, publication date, fetched date, author, and excerpt offsets when available.
- Store raw fetch metadata separately from analyzed chunks.
- Improve evidence modal:
  - full snippet
  - summary
  - labels/aspects
  - source title/domain
  - direct source link
  - related facts/events
- Add "why this was classified this way" where model output supports it.
- Add tests for evidence serialization and modal data shape.

## Objective 10: Reliability and Production Hardening

Prepare for commercial users and long-running operation.

Requirements:

- Add structured logging with run IDs.
- Add explicit error codes for:
  - missing Brave key
  - Brave quota/rate error
  - model unavailable
  - fetch timeout
  - synthesis failure
- Add startup diagnostics:
  - configured models
  - model availability check
  - Brave key present
  - database writable
- Add durable task state so runs survive backend restarts.
- Replace in-memory event bus with a persistent event stream or resumable DB polling fallback.
- Add auth before deploying outside localhost.
- Add tests for startup diagnostics and error reporting.

## Objective 11: Public Current Events Mode

Make the tool useful for general users trying to understand current events.

Requirements:

- Prioritize primary sources, official documents, reputable news, local sources, and public reaction separately.
- Add chronology first in the report.
- Add "what is known", "what is disputed", "what is opinion", and "what changed recently".
- Add source credibility explanation in plain language.
- Add warnings when sources are mostly social or mostly one-sided.
- Add tests for report shape and source mix warnings.

## Objective 12: UX Polish

Improve the interface without hiding analytical detail.

Requirements:

- Keep the submitted topic and selected depth visible in the run header.
- Add a compact executive summary at the top of completed reports.
- Add tabs inside the report:
  - Summary
  - Timeline
  - Evidence
  - Claims
  - Graph
  - Performance
- Add loading states that explain the current stage and estimated remaining work.
- Add "expand this run" flow that previews the additional query and quota cost.
- Improve mobile layout for report sections and graph.
- Add Playwright or component tests if frontend testing infrastructure is introduced.

## Minimum Done Definition For Each Objective

An objective is not done until:

- Backend behavior is covered by tests where applicable.
- Frontend typecheck/build passes where UI/API changed.
- Manual smoke test covers the user-visible workflow.
- No secrets are staged.
- The change is committed.
- This document or `/home/asus/HANDOFF.md` is updated if the work changes project direction, commands, known issues, or next steps.

## Progress Log

### 2026-05-16

Implemented the first pass of Objective 1 and several performance optimizations:

- Added backend research-depth presets: `quick`, `standard`, `deep`, `exhaustive`.
- Added initial run depth selection to the API and frontend.
- Added completed-run expansion to a requested deeper preset, defaulting to the next preset.
- Expansion now inherits the original run freshness unless the caller explicitly changes it.
- Report metadata now records topic, freshness, research depth, and depth budgets.
- Cache lookup now includes research depth and handles newer runs at different depths.
- Orchestrator now limits query count by the selected depth.
- Synthesis sample size is bounded by the selected depth.
- Brave search now has a 30-minute in-process cache keyed by query, freshness, and count.
- URL fetches are bounded by a 15-second orchestrator timeout.
- Duplicate sentiment snippets within a run share one model call.
- Added `backend/scripts/benchmark_pipeline.py` for local hot-path benchmarking.
- Fixed frontend lint issues encountered while validating.

Validation completed:

```bash
cd /home/asus/AutoSentiment/backend
source .venv/bin/activate
python3 -m pytest tests/ -v
python3 scripts/benchmark_pipeline.py
```

Benchmark result from the synthetic duplicate-sentiment case:

- baseline: 80 model calls
- optimized: 20 model calls
- model call reduction: 75%

```bash
cd /home/asus/AutoSentiment/frontend
npm run lint
npm run build
```

Manual smoke:

- Started uvicorn on `127.0.0.1:8010`.
- `GET /api/health` returned `{"status":"ok"}`.
- `GET /api/runs?limit=1` returned recent run metadata.
- Stopped the temporary uvicorn process.

## Current Recommended First Task

Continue with Objective 2. Build a quota-aware search planner on top of the depth presets so each run can show planned query cost, platform mix, and Brave monthly budget impact before it starts.
