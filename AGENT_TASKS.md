# Agent Task Queue — Remaining

Last audit: 2026-05-16 22:00 UTC (verified against git log + code)

## ✅ DONE — NemoClaw Self-Analysis Fixes
- [x] Retry logic + circuit breaker on all Ollama calls (exponential backoff, 3 attempts)
- [x] Batch sentiment analysis (analyze_batch, 5 snippets per call)
- [x] Prompt injection guard on topic input
- [x] Evidence modal: keyword highlighting, sentiment justification, confidence
- [x] SQLite WAL mode (already enabled)
- [x] Per-item sentiment failure recovery

## ✅ DONE — All prior phases
- [x] Search optimization (parallel media APIs, batch cache, timing, quality ranking, degraded mode)
- [x] UI overhaul (component splitting, CSS utilities, world map, draggable tabs, graph, claims, area chart)
- [x] Reliability (structured logging, error codes, durable recovery, auth skeleton, graceful shutdown)
- [x] UX polish (report tabs, keyboard shortcuts, mobile+print CSS, shareable URLs, depth badges, theme toggle)
- [x] Compare mode, saved searches, browser notifications, run duration
- [x] Docker, setup script, CI/CD, ruff+pre-commit, E2E smoke test

## 🔴 REMAINING — Real work left

### Tests (orchestrator hangs)
- [ ] Fix 8 orchestrator tests that hang when run together (SQLite session contention) — all pass individually
- [ ] LLM failure injection tests (mock Ollama returning 500s, timeouts, malformed JSON)
- [ ] Property-based tests for report builder functions

### Architecture cleanup
- [ ] Extract synthesis interface from builder.py (decouple LLM prompts from analytics)
- [ ] Extract inline CSS styles from components (30+ remaining in ReportView, ForceGraph)

### Features
- [ ] Admin dashboard: quota usage over time, model availability, run success rates
- [ ] Automatic model fallback: try smaller model if 30B/120B unavailable
- [ ] GPU utilization tracking: model load/unload timing to avoid 30B/120B thrashing

### Performance
- [ ] Orchestrator batch sentiment mode (analyze_batch exists but not wired into pipeline yet)
- [ ] Brave result cache TTL cleanup (stale entries evicted on startup — 7-day cutoff)
