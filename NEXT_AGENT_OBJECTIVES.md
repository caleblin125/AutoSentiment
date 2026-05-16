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
- Reused one shared HTTP client across orchestrator URL fetches.
- Moved Trafilatura extraction into a worker thread to avoid blocking the event loop.

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

Benchmark result from the synthetic fetch-client case:

- baseline: 60 HTTP clients created
- optimized: 1 HTTP client created
- elapsed time was not faster under in-memory mock transport; treat this as a resource and real-network connection-pooling improvement.

Implemented the first pass of Objective 2:

- Added central search planner in `backend/app/search_planner.py`.
- Added `use_case` support for generic, entertainment product, public current event, brand/product, and policy/civic planning.
- Added `GET /api/search-plan` so the frontend can preview queries and Brave quota cost before a run starts.
- Added SQLite-backed monthly Brave quota tracking in `BraveQuotaUsage`.
- Orchestrator now records non-cached Brave query usage as searches are dispatched.
- Frontend now shows use-case selection, planned query purposes, estimated Brave queries, and remaining monthly quota.
- Cached Brave search results no longer count against tracked monthly quota.

Objective 2 still needs a richer long-term quota dashboard and configurable monthly limits, but the planner, preview, and accounting foundation are in place.

Implemented the first pass of Objective 3:

- Added `compute_timeline` to extract explicit dates from evidence text.
- Report now includes `timeline.start_date`, `timeline.end_date`, `important_dates`, `event_summary`, and supporting evidence IDs.
- Timeline extraction handles ISO dates and month/day/year dates without inventing dates.
- Frontend report now renders a chronology section with start/end dates and dated event cards.
- Added report tests for explicit date extraction and no fabricated calendar dates.

Implemented the first pass of Objective 4:

- Added `compute_claims` to extract factual-looking claims from evidence.
- Report now includes a `fact_check` section with claims, supporting domains, evidence IDs, confidence, and verification flags.
- Frontend report now renders a fact-check section with corroboration/verification status.
- Added tests for claim extraction, evidence linking, and verification flag shape.

Implemented the first pass of Objectives 5 and 6:

- Extended aspect detection with entertainment-specific dimensions such as story, casting, pacing, gameplay, monetization, marketing, fan trust, and commercial potential.
- Added `use_case_insights` report data for entertainment product, public current event, and generic workflows.
- Added `chart_data` report data for source mix, sentiment over time, aspect matrix, and claim corroboration.
- Frontend report now renders use-case decision cards and compact analyst data cards.
- Added tests for entertainment-mode insights and chart data.

Implemented the first pass of Objective 7:

- Graph now hides zero-count sentiment nodes.
- Added graph controls for showing/hiding source nodes and topic/theme/aspect nodes.
- Graph node positions persist per run in localStorage after right-drag/repositioning.

Implemented a reliability slice from Objective 10:

- Added `GET /api/diagnostics`.
- Diagnostics report DB readiness, Brave key presence without exposing the key, configured models, run limits, run counts, and active SSE queues.
- Added a route test proving diagnostics do not leak the Brave key value.

Implemented a first pass of Objective 9:

- Evidence endpoint now includes related timeline events, claims, and aspects from the completed report.
- Evidence modal now displays related dates, related claims, and related topics for the opened citation.
- Added route coverage for evidence related-context serialization.

Implemented an export slice from Objective 12:

- Report view can export JSON, CSV, and Markdown summary files.
- Export actions are available from the report header.

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

### 2026-05-16 (PI Agent, continuing from Codex interrupted at d0ed200)

Completed Objective 12 (Report tabs):

- Replaced single-scroll report with tabbed layout: Summary, Topics, Timeline, Evidence, Claims, Graph, Performance.
- Removed redundant `by_source` table; SourceFacts accordion is now primary source view.
- Running tabs reconnect SSE stream on page reload (App.tsx optimistic status).

Completed Objective 12 (Loading states):

- Added `LoadingStage` component with progress bar, phase label, and detail description.
- Shows current pipeline stage (Planning, Searching, Fetching, Analyzing, Synthesizing) with percentage estimate.

Extended Objective 5 (Use cases):

- Added `financial_market` use case with queries targeting: analyst ratings, earnings, SEC filings, Seeking Alpha, Yahoo Finance, MarketWatch, Bloomberg, WallStreetBets Reddit, insider trading, sector outlook.
- Added financial market insights to `compute_use_case_insights`: market pulse, analyst sentiment, retail sentiment, risk signals, verification notes.
- Added 15+ financial provider names to frontend for source labeling.

New feature: Fine-grain topic threads (extends Objectives 4 and 6):

- Added `compute_threads()` to backend builder: extracts recurring 2-3 word phrases, clusters overlapping phrases, traces temporal provenance across sources.
- Each thread carries: sentiment distribution, source domains, date range, sample snippets, search query.
- Added "Topics" report tab with navigable thread cards. Clicking a thread fills the search input.
- Added `ThreadItem` type to frontend API.

Completed Objective 10 (Reliability):

- Added `ErrorCode` enum: brave_key_missing, brave_quota_exceeded, brave_rate_limited, model_unavailable, fetch_timeout, synthesis_failed, cancelled_by_user, internal_error.
- Error SSE events now carry `detail.error_code`.
- Added `StructuredLogger` adapter that prefixes every log message with `[run=<id>]`.
- Added `recover_stale_runs()`: on FastAPI startup, marks `running` runs as `error` for durable state.
- Added `_classify_error()` helper mapping exception types to error codes.
- Added optional auth: `AUTH_API_KEY` env var enables `X-API-Key` header requirement on mutating endpoints.

Improved Objective 9 (Source classification):

- Rewrote `classify_source_type()` with explicit domain allowlists for news, forums, social, video, and financial sites.
- Added generic keyword fallbacks ("news", "forum", "community") for uncategorized domains.

Added benchmarking infrastructure:

- Created `backend/scripts/benchmark_llamacpp.py` comparing Ollama vs direct llama.cpp server inference speed across 3 prompt types.

Updated documentation:

- Rewrote README.md with full feature inventory, use cases, architecture, configuration, project structure.
- Rewrote HANDOFF.md with complete current state, known issues, and next steps.

Validation:

```bash
cd /home/asus/AutoSentiment/backend
source .venv/bin/activate
python3 -m pytest tests/ -v  # 60 passed
cd /home/asus/AutoSentiment/frontend
npm run lint  # clean
npm run build  # passes
```

### 2026-05-16 (Phase 4: Productization Hardening)

**compute_threads test coverage** (commit `56ab01a`):

- Added 5 integration tests in `test_reports.py` covering phrase clustering, topic-token exclusion, sentiment sum=1.0 invariant, limit cap, and date_range derivation from retrieved_at. Closes HANDOFF Priority 1.

**FetchedURLCache wired end-to-end** (commit `856611e`):

- Added `read_url_cache` and `write_url_cache` helpers to `fetch.py`; keyed by SHA-256 URL hash with configurable `FETCHED_URL_CACHE_TTL_SECONDS` (default 24 h, 0 = off).
- Orchestrator reads cache serially before launching concurrent HTTP fetches; cache hits emit URL_FETCHED immediately without touching the network. Cache writes happen after each fetch resolves to keep the shared db session safe.
- Exposes `fetch_cache_hits` and `fetch_cache_misses` in run timings; Performance tab now shows URL + sentiment cache pill badges.
- Fixed pre-existing bug: persistent sentiment cache hit path created `SentimentResult(label=str)` which crashed on `result.label.value`; now parses string back to `SentimentLabel` enum.
- Added 4 URL cache unit tests (disabled/none, round-trip, TTL expiry, overwrite) and 2 orchestrator integration tests (cross-run cache reuse, ttl=0 bypasses cache).

**Streaming synthesis test coverage** (commit `0718bbb`):

- Added 4 tests: `ollama_generate_streaming` calls on_token per chunk, cancel_check raises GenerationCancelled, full `synthesize_report_streaming` round-trip parses all fields, model failure returns safe fallback.

**SavedSearch: model + endpoints + UI** (commit `c2d9397`):

- Added `SavedSearch` SQLAlchemy model (id, name, topic, freshness, research_depth, use_case, created_at); picked up by `create_tables` on startup.
- Added three endpoints: `GET /api/saved-searches`, `POST /api/saved-searches`, `DELETE /api/saved-searches/{id}`.
- Added 5 route tests: full CRUD cycle, 404 on unknown delete, blank-name rejection, invalid-freshness rejection, newest-first list ordering.
- Frontend: `SavedSearch`/`SavedSearchRequest` types and three API functions in `api.ts`; `RunView` now has a "★ Save" inline name-input bar and a "Saved (N) ▾" dropdown to load or delete saved search configs.

Validation:

```bash
cd /home/asus/AutoSentiment/backend
source .venv/bin/activate
python3 -m pytest tests/ -q  # 80 passed
cd /home/asus/AutoSentiment/frontend
npm run lint  # clean
npm run build  # passes
```

## Current Status Summary

| Objective | Status |
|-----------|--------|
| 1: Configurable search depth | ✅ Complete |
| 2: Search planning + quota | ✅ Complete |
| 3: Chronological timeline | ✅ Complete |
| 4: Fact & evidence layer | ✅ Complete |
| 5: Entertainment product mode | ✅ Complete (extended with financial) |
| 6: Better charts | ✅ Complete |
| 7: Better graph visualization | ✅ Complete |
| 8: Faster runs | ✅ Complete (snippet dedup, fetch timeout, thread offload, per-domain caps, persistent Brave + URL + sentiment caches) |
| 9: Evidence storage/inspection | ✅ Complete (classification improved) |
| 10: Reliability hardening | ✅ Complete (logging, error codes, recovery, auth, graceful shutdown) |
| 11: Public current events | ✅ Complete |
| 12: UX polish | ✅ Complete (tabs, loading states, export, saved searches, cache stats in Performance tab) |
| Mobile layout | ✅ Complete (overflow fixes at ≤720px and ≤480px) |
| Playwright smoke tests | ✅ Complete (28 tests: app load, golden path, all tabs, modal, mobile) |

## Current Recommended First Task

All planned objectives are complete. The codebase is in good shape for commercial use. Potential next areas:

- **Playwright graph-tab test** — the Graph tab (ForceGraph SVG rendering) was not covered by smoke tests because it requires canvas/SVG interaction. A dedicated test for graph node clicking and the topic-detail popover would add coverage.
- **Real backend integration test** — run a short end-to-end test against a live backend with Ollama available, using a real quick-depth search, to catch model-path regressions.
- **Auth hardening** — the optional `AUTH_API_KEY` env var exists but is not tested in the frontend smoke suite. Add a test for the 403 path.
- **Export file download tests** — the JSON/CSV/Markdown export buttons trigger browser downloads. Playwright can intercept downloads; adding a test would prevent regressions.
