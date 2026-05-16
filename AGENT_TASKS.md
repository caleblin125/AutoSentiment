# Agent Task Queue — Multi-Agent Sprint

Last updated: 2026-05-16 05:00 UTC

## 🔴 CLAIMED — PI Agent (me)
- [x] [pi]       Fix orchestrator tests (supplemental_media_search monkeypatch)
- [ ] [pi]       Add test coverage for new modules (media_apis.py, fetch cache, saved search)
- [ ] [pi]       Fix mobile layout: ensure report tabs stack vertically on <768px
- [ ] [pi]       Add @media print CSS for PDF export
- [ ] [pi]       Add keyboard shortcuts: Ctrl+Enter submit, 1-7 tab switch, Esc close modal, ? help
- [ ] [pi]       Fix remaining hardcoded colors → CSS variables (6x #a78bfa, #fff, #ffffff)
- [ ] [pi]       Add page title updates: "AutoSentiment — {topic} ({status})"
- [ ] [pi]       Monitor other agents, commit relay, handle merge conflicts

## 🟡 CLAIMED — Claude Agent (UI overhaul)
- [ ] [claude]   Split ReportView.tsx (1382 lines) into sub-components:
                EvidenceModal.tsx, SentimentBars.tsx, SourceFacts.tsx,
                TimelineSection.tsx, ClaimsSection.tsx, ThreadSection.tsx
- [ ] [claude]   Extract inline styles (36 in ReportView, 11 in ForceGraph) into CSS classes
- [ ] [claude]   Create shared utility CSS classes: .mono, .flex-row, .flex-col, .text-muted
                to eliminate 83x font-family: var(--mono), 98x display: flex repetitions
- [ ] [claude]   Fix light theme: ensure all hardcoded colors have light-theme equivalents
- [ ] [claude]   Add animated transitions between report tabs (CSS fade/slide)
- [ ] [claude]   Fix EventTimeline: align-items on URL rows, collapsible animation smoothness
- [ ] [claude]   Add useEffect cleanup functions where missing (SSE disconnect, timers)
- [ ] [claude]   Add error boundary wrappers to ForceGraph, EventTimeline, HistoryPanel

## 🟢 CLAIMED — Cursor Agent (search optimization)
- [ ] [cursor]   Parallelize supplemental_media_search: use asyncio.gather for 5 APIs
                instead of sequential for-loop (currently blocks on each API)
- [ ] [cursor]   Pre-queue Brave searches: check all cache hits first, then dispatch
                remaining queries with 1s spacing — reduces total wait time
- [ ] [cursor]   Batch FetchedURLCache reads: currently reads URLs one-by-one in
                for loop; use a single SELECT ... WHERE url_hash IN (...) query
- [ ] [cursor]   Increase _FETCH_CONCURRENCY from 8 → 12 with adaptive backoff
- [ ] [cursor]   Add search dedup score: when Brave + media APIs return same URL,
                mark it and show source diversity metric in report
- [ ] [cursor]   Add search-stage timing breakdown: Brave time vs media API time
                vs cache lookup time — expose in timings dict
- [ ] [cursor]   Implement search result quality ranking: prefer longer snippets,
                newer dates, and higher-credibility domains in URL selection
- [ ] [cursor]   Test: ensure all search sources work without API keys (degraded mode)
- [ ] [cursor]   Test: verify cache hit rate with repeated searches on same topic

## Completed (last 6h)
- [x] [claude]   2026-05-16 04:55  Massive UI overhaul (timeline, world map, draggable tabs, graph, claims, area chart)
- [x] [pi]       2026-05-16 04:50  Multi-agent coordination system (AGENT_TASKS, agent-run, agent-relay)
- [x] [pi]       2026-05-16 04:40  Graceful shutdown, auth, streaming synthesis, Docker, theme toggle
- [x] [pi]       2026-05-16 04:30  Persistent caches, credibility scoring, E2E tests, thread extraction
