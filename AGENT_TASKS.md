# Agent Task Queue

Last updated: 2026-05-16 20:28 UTC (audited against git log)

## 🔴 PI Agent (me) — COMPLETE
- [x] [pi]       Fix orchestrator tests (supplemental_media_search monkeypatch)
- [x] [pi]       Fix mobile layout: report tabs stack vertically on <768px
- [x] [pi]       Add @media print CSS for PDF export
- [x] [pi]       Add keyboard shortcuts: Ctrl+Enter submit, 1-7 tab switch, Esc close modal
- [x] [pi]       Fix hardcoded colors → CSS variables (nemoclaw-purple, #fff, #ffffff)
- [x] [pi]       Add page title updates: "AutoSentiment — {topic} ({status})"

## 🟡 Claude Agent — IN PROGRESS
- [x] [claude]   Split ReportView.tsx into sub-components (EvidenceModal, SourceFacts, ClaimsSection)
- [x] [claude]   Create shared CSS utility classes, tab animations, CSS variable expansion
- [x] [claude]   World map with continental SVG, draggable tabs, graph improvements
- [x] [claude]   Claim corroboration rework, sentiment area chart
- [ ] [claude]   Fix light theme: ensure all remaining hardcoded colors have light equivalents
- [ ] [claude]   Add useEffect cleanup functions (SSE disconnect, timers)
- [ ] [claude]   Add error boundary wrappers to ForceGraph, EventTimeline, HistoryPanel

## 🔴 Codex Agent — CRASHED (ran out of credits, did zero work)
- [ ] [FREE]     Parallelize supplemental_media_search: asyncio.gather instead of sequential
- [ ] [FREE]     Pre-queue Brave searches: batch cache hit check first, then dispatch
- [ ] [FREE]     Batch FetchedURLCache reads: single SELECT IN query
- [ ] [FREE]     Increase _FETCH_CONCURRENCY from 8 → 12 with adaptive backoff
- [ ] [FREE]     Add search dedup scoring + source diversity metric
- [ ] [FREE]     Add search-stage timing breakdown in timings dict
- [ ] [FREE]     Implement search result quality ranking
- [ ] [FREE]     Test degraded mode (no API keys) end-to-end
- [ ] [FREE]     Test cache hit rate with repeated searches

## Next Tasks (unclaimed)
- [ ] [FREE]     Per-URL fetch timeout hardening in orchestrator
- [ ] [FREE]     FetchedURLCache TTL eviction on startup
- [ ] [FREE]     Graph position persistence to localStorage per run_id
- [ ] [FREE]     Multi-topic compare mode (2-3 topics side by side)
- [ ] [FREE]     Saved searches UI wiring (model exists, frontend panel needed)
- [ ] [FREE]     Shareable run URLs (/?run=<id> loads read-only report)
- [ ] [FREE]     Add Playwright tests for saved searches, thread clicks, report tabs
- [ ] [FREE]     Backend linting: add ruff + pre-commit hooks
- [ ] [FREE]     CI/CD pipeline config (.github/workflows/ci.yml)
- [ ] [FREE]     Ollama model warm-up on backend startup

## Completed (verified against git log)
- [x] [pi]       2026-05-16 20:26  Fix orchestrator test hangs
- [x] [claude]   2026-05-16 20:24  Multi-tab keyboard shortcut + page title fix
- [x] [claude]   2026-05-16 20:15  Refactor ReportView sub-components + CSS utilities + tab animations
- [x] [pi]       2026-05-16 20:08  Keyboard shortcuts, page title, mobile+print CSS, color fixes
- [x] [pi]       2026-05-16 20:07  Orchestrator test fix
- [x] [pi]       2026-05-16 04:50  Multi-agent coordination system
- [x] [claude]   2026-05-16 04:55  Massive UI overhaul (timeline, world map, draggable tabs, graph, claims)
- [x] [pi]       2026-05-16 04:40  Graceful shutdown, auth, streaming synthesis, Docker, theme toggle
- [x] [pi]       2026-05-16 04:30  Persistent caches, credibility scoring, E2E tests, thread extraction
