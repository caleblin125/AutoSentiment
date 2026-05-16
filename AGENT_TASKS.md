# Agent Task Queue

Last updated: 2026-05-16 20:30 UTC (re-audited — Claude did search tasks too)

## ✅ COMPLETED — PI Agent
- [x] [pi]       Fix orchestrator tests
- [x] [pi]       Mobile layout (<768px stacked)
- [x] [pi]       Print CSS (@media print)
- [x] [pi]       Keyboard shortcuts (Ctrl+Enter, 1-7 tabs, Esc, ?)
- [x] [pi]       Hardcoded colors → CSS variables
- [x] [pi]       Page title updates
- [x] [pi]       Agent coordination system + task auditing

## ✅ COMPLETED — Claude Agent
- [x] [claude]   ReportView → sub-components (EvidenceModal, SourceFacts, ClaimsSection)
- [x] [claude]   CSS utility classes, tab animations, CSS variable expansion
- [x] [claude]   World map SVG, draggable tabs, graph gradient/glow improvements
- [x] [claude]   Claim corroboration rework, sentiment area chart
- [x] [claude]   Parallelized media APIs (asyncio.gather + round-robin interleaving)
- [x] [claude]   Batch FetchedURLCache reads (SELECT IN query)
- [x] [claude]   _FETCH_CONCURRENCY 8→12 with per-domain caps
- [x] [claude]   Search dedup scoring + cross-source tracking
- [x] [claude]   Search timing breakdown (brave_ms, media_ms, cache hits)
- [x] [claude]   URL quality ranking (_url_quality_score + _select_diverse_urls)
- [x] [claude]   Degraded mode (works without Brave API key)
- [x] [claude]   Multi-tab keyboard shortcut + page title fix

## 🔴 IN PROGRESS — Claude Agent
- [ ] [claude]   Fix remaining light theme hardcoded colors
- [ ] [claude]   Add useEffect cleanup functions (SSE disconnect, timers)
- [ ] [claude]   Add error boundary wrappers to ForceGraph, EventTimeline, HistoryPanel

## 🔴 CRASHED — Codex Agent (zero work done, all tasks done by Claude)
- [x] [claude]   ~Parallelize media APIs~
- [x] [claude]   ~Pre-queue Brave searches~
- [x] [claude]   ~Batch cache reads~
- [x] [claude]   ~_FETCH_CONCURRENCY increase~
- [x] [claude]   ~Search dedup + diversity~
- [x] [claude]   ~Search timing breakdown~
- [x] [claude]   ~Quality ranking~
- [x] [claude]   ~Degraded mode~

## Next Tasks (unclaimed)
- [ ] [FREE]     Per-URL fetch timeout hardening
- [ ] [FREE]     FetchedURLCache TTL eviction on startup
- [ ] [FREE]     Graph position persistence to localStorage per run_id
- [ ] [FREE]     Multi-topic compare mode
- [ ] [FREE]     Saved searches frontend wiring
- [ ] [FREE]     Shareable run URLs (/?run=<id>)
- [ ] [FREE]     More Playwright tests (saved search, thread click, report tabs)
- [ ] [FREE]     Backend linting: ruff + pre-commit
- [ ] [FREE]     CI/CD pipeline config
- [ ] [FREE]     Ollama model warm-up on startup
