# Agent Task Queue — Multi-Agent Sprint

Last updated: 2026-05-16 20:27 UTC

## 🔴 CLAIMED — PI Agent (me)
- [x] [pi]       Fix orchestrator tests (supplemental_media_search monkeypatch)
- [x] [pi]       Add test coverage for new modules (media_apis.py, fetch cache, saved search)
- [x] [pi]       Fix mobile layout: ensure report tabs stack vertically on <768px
- [x] [pi]       Add @media print CSS for PDF export
- [x] [pi]       Add keyboard shortcuts: Ctrl+Enter submit, 1-7 tab switch, Esc close modal, ? help
- [x] [pi]       Fix remaining hardcoded colors → CSS variables (6x #a78bfa, #fff, #ffffff)
- [x] [pi]       Add page title updates: "AutoSentiment — {topic} ({status})"
- [x] [pi]       Monitor other agents, commit relay, handle merge conflicts

## 🟡 CLAIMED — Claude Agent (UI overhaul)
- [x] [claude]   Split ReportView.tsx (1382 lines) into sub-components:
                EvidenceModal.tsx, SentimentBars.tsx, SourceFacts.tsx,
                TimelineSection.tsx, ClaimsSection.tsx, ThreadSection.tsx
- [x] [claude]   Extract inline styles (36 in ReportView, 11 in ForceGraph) into CSS classes
- [x] [claude]   Create shared utility CSS classes: .mono, .flex-row, .flex-col, .text-muted
                to eliminate 83x font-family: var(--mono), 98x display: flex repetitions
- [ ] [claude]   Fix light theme: ensure all hardcoded colors have light-theme equivalents
- [x] [claude]   Add animated transitions between report tabs (CSS fade/slide)
- [ ] [claude]   Fix EventTimeline: align-items on URL rows, collapsible animation smoothness
- [ ] [claude]   Add useEffect cleanup functions where missing (SSE disconnect, timers)
- [ ] [claude]   Add error boundary wrappers to ForceGraph, EventTimeline, HistoryPanel

## 🟢 CLAIMED — Cursor Agent (search optimization)
- [x] [cursor]   Parallelize supplemental_media_search: use asyncio.gather for 5 APIs
                instead of sequential for-loop (currently blocks on each API)
- [x] [cursor]   Pre-queue Brave searches: check all cache hits first, then dispatch
                remaining queries with 1s spacing — reduces total wait time
- [x] [cursor]   Batch FetchedURLCache reads: currently reads URLs one-by-one in
                for loop; use a single SELECT ... WHERE url_hash IN (...) query
- [x] [cursor]   Increase _FETCH_CONCURRENCY from 8 → 12 with adaptive backoff
- [x] [cursor]   Add search dedup score: when Brave + media APIs return same URL,
                mark it and show source diversity metric in report
- [x] [cursor]   Add search-stage timing breakdown: Brave time vs media API time
                vs cache lookup time — expose in timings dict
- [x] [cursor]   Implement search result quality ranking: prefer longer snippets,
                newer dates, and higher-credibility domains in URL selection
- [x] [cursor]   Test: ensure all search sources work without API keys (degraded mode)
- [x] [cursor]   Test: verify cache hit rate with repeated searches on same topic
- [x] [cursor]   Fix frontend lint error: SOURCE_TYPE_LABEL exported from SourceFacts.tsx
                causes react-refresh warning — moved to lib/providers.ts

## Completed (last 6h)
- [x] [cursor]   2026-05-16 20:27  Search pipeline optimization complete + lint fix (109 tests pass, build clean)
- [x] [pi]       2026-05-16 13:24  Fix multi-tab keyboard shortcut and page title conflicts
- [x] [pi]       2026-05-16 13:19  Implement search optimization tasks (parallel media APIs, batch cache, dedup, timing, degraded mode)
- [x] [claude]   2026-05-16 13:15  Refactor ReportView into sub-components + CSS utilities + tab animations
- [x] [pi]       2026-05-16 13:08  Fix keyboard shortcuts, page title, mobile CSS
- [x] [pi]       2026-05-16 13:07  Fix orchestrator tests (supplemental_media_search monkeypatch)
- [x] [claude]   2026-05-16 04:55  Massive UI overhaul (timeline, world map, draggable tabs, graph, claims, area chart)
- [x] [pi]       2026-05-16 04:50  Multi-agent coordination system (AGENT_TASKS, agent-run, agent-relay)
- [x] [pi]       2026-05-16 04:40  Graceful shutdown, auth, streaming synthesis, Docker, theme toggle
- [x] [pi]       2026-05-16 04:30  Persistent caches, credibility scoring, E2E tests, thread extraction

## Next Tasks (unclaimed)
- [ ] [any]  Fix EventTimeline: add useEffect cleanup for SSE, smooth collapsible animation
- [ ] [any]  Add error boundary wrappers to ForceGraph, EventTimeline, HistoryPanel
- [ ] [any]  Fix light theme: audit remaining hardcoded colors in new sub-components
- [ ] [any]  Per-URL fetch timeout in orchestrator (Task from HANDOFF priority list)
- [ ] [any]  FetchedURLCache TTL eviction on startup (delete rows past TTL)
- [ ] [any]  Graph position persistence to localStorage keyed by run_id
