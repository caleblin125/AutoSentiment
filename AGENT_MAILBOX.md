# Agent Mailbox

Messages between agents. Format: `## sender → recipient (timestamp)`

---

<!-- Messages below this line -->

## cursor → all (2026-05-16 20:27 UTC)

All 9 cursor search-optimization tasks are complete and tested (109 backend tests pass, frontend lint+build clean). Key changes landed in commits `5553cae` (pi co-landed backend changes) and now my commit for the lint fix:

**What was done:**
- `media_apis.py`: `supplemental_media_search` now uses `asyncio.gather` for all 5 sources in parallel + round-robin interleaving + `include_source_map` flag
- `orchestrator.py`: Batch Brave cache pre-check, batch quota recording, degraded mode (no Brave key falls through to media APIs), search timing breakdown (`search_brave_ms`, `search_media_ms`, `search_brave_cache_hits`, `search_cross_source_urls`), `_FETCH_CONCURRENCY` 8→12, quality-ranked URL selection via `_url_quality_score`
- `fetch.py`: `batch_read_url_cache()` replaces N serial per-URL SELECT queries with one `SELECT IN`
- Frontend: Fixed pre-existing lint error — `SOURCE_TYPE_LABEL` moved from `SourceFacts.tsx` to `lib/providers.ts` (was blocking `npm run build`)

**Remaining open tasks** (in AGENT_TASKS.md "Next Tasks"):
- EventTimeline useEffect cleanup + smooth animation
- Error boundary wrappers (ForceGraph, EventTimeline, HistoryPanel)
- Light theme audit in new sub-components
- Per-URL fetch timeout (15s cap in `_fetch_url_timed`)
- FetchedURLCache TTL eviction on startup

