# Agent Task Queue — Phase 5

Last updated: 2026-05-16 21:10 UTC

## 🔴 NOW — PI Agent
- [ ] [pi]  Setup script: single `./setup.sh` that creates venv, installs deps, copies .env.example
- [ ] [pi]  Backend linting: add ruff config + pre-commit hooks

## Next — PI Agent (after above)
- [ ] [pi]  Shareable run URLs: `/?run=<id>` loads read-only report, bookmarkable, no auth needed
- [ ] [pi]  Multi-topic compare mode: enter 2-3 topics, compare sentiment side-by-side
- [ ] [pi]  Ollama model warm-up: tiny prompt on startup to avoid cold-start latency
- [ ] [pi]  CI/CD pipeline: .github/workflows/ci.yml (test + lint + build)
- [ ] [pi]  More Playwright tests: saved search save/load, thread card click opens search

## 🟡 Claude
- [ ] [claude] Shareable run URL frontend: `/?run=<id>` read-only ReportView without RunView shell
- [ ] [claude] Multi-topic compare mode frontend: side-by-side ReportView panels

## Completed Phase 5
- [x] [claude] FetchedURLCache TTL eviction on startup (7-day cutoff, main.py lifespan hook)
- [x] [claude] Light theme: hardcoded color audit in EvidenceModal, ClaimsSection, SourceFacts — all use CSS vars ✓
- [x] [claude] useEffect cleanups: EventTimeline (no useEffect needed — pure render), ForceGraph (cancelAnimationFrame ✓), useRunStream (eventSource.close() ✓)
- [x] [claude] Error boundaries on ForceGraph ✓, EventTimeline ✓, HistoryPanel ✓
- [x] [claude] Saved searches frontend wiring: save/load/delete dropdown in RunView search form ✓
- [x] [claude] Graph node position persistence: localStorage keyed by `autosentiment_graph:${runId}` ✓

## Completed Phase 4 (verified)
- [x] [claude] ReportView sub-components, CSS utilities, tab animations, world map
- [x] [claude] All search optimization (parallel APIs, batch cache, timing, quality ranking, degraded mode)
- [x] [pi]    Keyboard shortcuts, page titles, mobile+print CSS, color fixes, task auditing
- [x] [pi]    Agent coordination system (AGENT_TASKS, agent-run, agent-relay)
