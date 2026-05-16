# Test Suite

142 tests across 11 files. All tests run without a live Ollama or Brave connection — external calls are monkeypatched. Two tests that require a live Ollama server are skipped automatically.

## Running tests

```bash
cd backend
source .venv/bin/activate

# All tests
pytest tests/ -v

# Single file
pytest tests/test_reports.py -v

# Single test by name
pytest tests/test_orchestrator.py::test_run_research_completes_and_persists_report -v

# Stop on first failure
pytest tests/ -x

# Quiet summary
pytest tests/ -q
```

---

## File overview

| File | Tests | What it covers |
|---|---|---|
| `test_fetch.py` | 14 | URL fetching, Reddit JSON parsing, trafilatura extraction, URL cache |
| `test_llm.py` | 15 | Ollama HTTP client, sentiment parsing, streaming, failure fallbacks |
| `test_media_apis.py` | 5 | Supplemental media search (HN, YouTube, Pushshift), parallel fetch, error tolerance |
| `test_orchestrator.py` | 22 | Full pipeline runs, cancel, URL dedup, cache reuse, quality ranking, per-item failure recovery |
| `test_reports.py` | 42 | Every report builder function: counts, quotes, aspects, claims, timeline, threads, graph, location |
| `test_research_depth.py` | 3 | Depth preset budgets, validation, next-depth advancement |
| `test_routes.py` | 22 | HTTP endpoints: create/cancel/expand run, SSE stream, diagnostics, caching, NemoClaw |
| `test_search.py` | 6 | Brave search client, response parsing, rate limiting, in-process cache |
| `test_search_planner.py` | 3 | Query planning, monthly quota tracking, model query deduplication |
| `test_self_analysis.py` | 1 | NemoClaw self-analysis integration (skipped without live Ollama) |
| `test_tui.py` | 3 | Terminal UI helpers: SSE parsing, report formatting |

---

## File details

### `test_fetch.py`

Tests URL fetching and source classification. All HTTP calls are monkeypatched — no network required.

- **Reddit fetch** — parses listing JSON, extracts post body and top-level comments, caps snippet length, follows external URLs linked in comments, skips Reddit-internal and media-host links
- **News fetch** — trafilatura body extraction from HTML responses, minimum-length paragraph filtering
- **Shared HTTP client** — verifies connection reuse across multiple fetch calls
- **Failure handling** — returns empty list when fetch throws, not an exception
- **Source type classification** — `classify_source_type()` identifies Reddit, news, forum, YouTube, etc. from URL patterns
- **URL cache** — SQLite-backed cross-run cache: round-trip write/read, TTL expiry, batch read, overwrite on collision, disabled when TTL is zero

### `test_llm.py`

Tests the Ollama HTTP client and sentiment queue. All httpx calls are monkeypatched.

- **JSON contract** — `ollama_generate` sends correct model/prompt/stream=false payload
- **Response parsing** — handles JSON embedded in `<think>` tags, JSON in fenced code blocks, raises `ValueError` for unparseable responses
- **Cancel check** — raises `asyncio.CancelledError` mid-generation when cancel flag is set
- **Sentiment queue** — returns neutral on model failure, normalises label casing, parses confidence, applies default 0.8 when field missing, clamps out-of-range confidence to `[0, 1]`
- **NemoClaw wrappers** — `expand_queries` and `synthesize_narrative` parse successful responses and fall back gracefully on errors
- **Streaming** — `ollama_generate_streaming` calls `on_token` callback for each chunk, raises on cancel
- **Synthesis streaming** — `synthesize_report_streaming` yields tokens to frontend SSE, falls back on model failure

### `test_media_apis.py`

Tests the supplemental media search (enabled via `ENABLE_MEDIA_API_SEARCH=true`).

- **Multi-source parse** — Hacker News, YouTube RSS, Pushshift Reddit responses all parsed correctly
- **Parallel execution** — all sources queried concurrently, not serially
- **Source map** — returned items carry correct `source_type` labels
- **Error tolerance** — one failing source doesn't abort others
- **Reddit cap** — limits Reddit results to avoid skewing sentiment distribution

### `test_orchestrator.py`

Tests the main pipeline end-to-end and its sub-functions. Uses an in-memory SQLite session via `session_factory` fixture.

- **Full pipeline** — `run_research` completes, persists report, emits `run_complete` SSE event
- **Error handling** — unhandled exception marks run as `error`, emits `run_error` SSE event
- **Query expansion** — `_expand_platform_queries` adds diverse platforms (Quora, YouTube, Trustpilot, HN, international)
- **URL diversity** — `_select_diverse_urls` preserves non-Reddit sources even when Reddit dominates results
- **Synthesis sampling** — `_summaries_for_synthesis` respects item cap and balances labels
- **Parallel fetch** — respects `max_items_per_run` cap, emits `fetch_complete` events
- **Cancel** — cooperative cancel during search stops the run and emits `cancelled_by_user`
- **Query budget** — respects `max_queries_per_run` setting
- **Snippet deduplication** — identical snippets from different URLs are not re-analysed
- **Brave cache** — cached search results do not count against the monthly quota
- **Fetch timeout** — `_fetch_url_timed` returns empty list on timeout, does not raise
- **URL quality scoring** — credible domains get +2, cross-source +1; quality ranking sorts credible URLs first
- **Cross-run URL cache** — second run reuses fetched text from first run for same URLs; skipped when TTL is zero
- **Per-item failure recovery** — one failed sentiment call does not crash the run; remaining items complete normally

### `test_reports.py`

Tests every function in `reports/builder.py`. No external calls — pure Python logic.

- **`compute_counts`** — overall and by-source sentiment percentages, fraction invariants (sum to 1.0), total matches chunk count, zeros on empty input
- **`pick_top_quotes`** — shape and limit, confidence field and ranking, default confidence, credible sources rank before non-credible at equal confidence, required keys, confidence in `[0, 1]`
- **`compute_aspects`** — extracts cost/efficiency/safety/etc. from snippet keywords, each aspect carries `evidence_ids`, limit respected, valid sentiment values, count >= 1
- **`compute_source_facts`** — groups facts by domain with counts
- **`build_idea_graph`** — contains aspect nodes and source edges, aspect nodes carry `evidence_ids`
- **`compute_claims`** — detects contradictions when opposing chunks share a subject phrase, no contradictions when all chunks have same label, groups declarative claims, flags single-source claims for verification, confidence in `[0, 0.95]`, limit respected, required keys, empty input returns empty lists
- **Stop word filter** — common English tokens (`for`, `not`, `the`, etc.) are excluded from aspects
- **`_expand_platform_queries`** — includes Quora, YouTube, Trustpilot, HN, international language queries; no more than one explicit Reddit query
- **`compute_timeline`** — extracts ISO and natural-language dates from evidence text, does not fabricate dates, returns `None` start/end when no dates found
- **`compute_use_case_insights`** — entertainment mode produces `audience_pulse`, `conversion_blockers`, `launch_risks`
- **`compute_chart_data`** — `sentiment_over_time` with `explicit` certainty, `location_sentiment` from named locations and from source domain TLD
- **`compute_threads`** — recurring phrases across sources form threads with sentiment, domains, date range; single-mention phrases excluded; topic tokens excluded from phrase seeds; limit respected; thread sentiment fractions sum to 1.0
- **`compute_location_sentiment`** — extracts named countries appearing ≥ 2 times, returns valid lat/lon
- **Property-based invariants** — each of the above functions is tested against multiple inputs to verify structural guarantees hold universally (not just for one fixture)

### `test_research_depth.py`

- **Preset budgets** — Quick, Standard, Deep, and Exhaustive presets apply correct query/URL/item caps to settings
- **Validation** — `validate_depth` accepts valid strings, rejects unknown values
- **Advancement** — `next_depth` returns the next deeper preset, or `None` at Exhaustive

### `test_routes.py`

Tests all HTTP API endpoints via FastAPI's `AsyncClient`. Uses an in-memory SQLite session fixture.

- **`POST /api/runs`** — persists a pending run, registers SSE queue, schedules pipeline task
- **`GET /api/runs/{id}`** — returns serialisable run dict with status and report
- **`GET /api/runs/{id}/evidence`** — returns evidence chunks with `related` report context (timeline events, claims, aspects)
- **`GET /api/runs/{id}/stream`** — yields SSE `data:` lines, deregisters queue on disconnect, replays stored events for completed/cancelled runs
- **`POST /api/runs` request validation** — rejects blank topic, unknown freshness, unknown depth or use-case
- **`GET /api/search-plan`** — returns quota remaining and planned queries without starting a run
- **`GET /api/diagnostics`** — reports DB status and model config; never exposes key values
- **Run caching** — returns existing completed run when same topic/freshness/depth was run recently; cache is depth-sensitive; reuses evidence from a matching completed run
- **Model overrides** — `X-NemoClaw-Model` and `X-Lightweight-Model` headers override configured models
- **`POST /api/runs/{id}/cancel`** — signals event bus, returns `cancelled` status; no-ops for completed runs
- **`POST /api/runs/{id}/expand`** — creates new run at requested depth; defaults to next depth when not specified
- **`GET /api/runs`** — lists runs of all statuses
- **`POST /api/runs/{id}/nemoclaw`** — creates a sub-run linked to the parent, applies model overrides

### `test_search_planner.py`

- **Depth-aware planning** — plan uses correct query count and URL budget for the requested depth preset
- **Quota tracking** — used queries are recorded in `BraveQuotaUsage` and subtracted from monthly remaining
- **Deduplication** — model-generated queries that duplicate template queries are removed before counting

### `test_self_analysis.py`

Single integration test: runs the full NemoClaw self-analysis loop against a live Ollama server. **Skipped automatically** when Ollama is not available. Run manually to verify end-to-end LLM behaviour after model changes.

### `test_tui.py`

Tests the terminal UI helper functions used by the optional CLI interface.

- **SSE parsing** — `parse_sse_lines` handles multi-event streams and skips malformed JSON without crashing
- **Report formatting** — `format_report` includes sentiment bars, themes, and chronology
- **Run row formatting** — `format_run_row` handles runs with no report (pending/running/error states)

---

## Fixtures

Shared fixtures are defined at the top of each test file (no `conftest.py`).

| Fixture | Used in | Purpose |
|---|---|---|
| `session_factory` | `test_orchestrator.py` | Returns an async SQLAlchemy session factory backed by an in-memory SQLite DB |
| `db_session` | `test_routes.py` | Provides an `AsyncClient` and async session wired to the FastAPI app |

---

## Adding new tests

- Put tests in the file that matches the module under test
- Use `monkeypatch` to stub external calls (Ollama, Brave, httpx); never make real network calls in unit tests
- Async tests need `@pytest.mark.asyncio` and an `async def` signature
- The `_make_chunk` helper in `test_reports.py` builds `EvidenceChunk` objects with one line — use it rather than repeating constructor kwargs
