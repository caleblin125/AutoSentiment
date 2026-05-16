# Agent Task Queue

Last updated: 2026-05-16 20:40 UTC

## ✅ Cursor Agent — timeline overlap fix
- [x] [cursor] Fix EventTimeline URL list overlapping item_analyzed rows (max-height animation bug in url-list row)
- [x] [cursor] Fix frontend lint: SOURCE_TYPE_LABEL moved to lib/providers.ts
- [x] [cursor] Search pipeline optimization (all 9 tasks — parallel media APIs, batch cache, dedup, timing, degraded mode)

## ✅ PI Agent — COMPLETED THIS SESSION
- [x] [pi]  Shareable run URLs: `/?run=<id>` + 🔗 Link button + clipboard copy
- [x] [pi]  Setup script: `./setup.sh` (venv, pip, npm, .env, DB init, verify)
- [x] [pi]  Backend linting: ruff config + pre-commit hooks
- [x] [pi]  CI/CD pipeline: .github/workflows/ci.yml (test + lint + build + secret scan)

## ✅ ALREADY DONE (discovered during audit — Claude)
- [x] [claude] Graph position persistence (localStorage keyed per run_id) — already implemented
- [x] [claude] FetchedURLCache TTL eviction (7-day, on startup) — already implemented

## ✅ Claude Agent — all polish tasks done
- [x] [claude] Light theme: all new sub-components (EvidenceModal, ClaimsSection, SourceFacts) use CSS vars ✓
- [x] [claude] useEffect cleanups: EventTimeline is pure render (no cleanup needed); ForceGraph has cancelAnimationFrame ✓; useRunStream has eventSource.close() ✓
- [x] [claude] Error boundaries on ForceGraph ✓, EventTimeline ✓, HistoryPanel ✓
- [x] [claude] Saved searches frontend panel: fully wired (save/load/delete dropdown in RunView) ✓
- [x] [claude] FetchedURLCache TTL eviction: committed in 964c53f ✓

## ✅ Claude Agent — Phase 5 additions (this session)
- [x] [claude] Browser notification on run completion: Notification API, permission requested on first submit, fires only when tab is hidden
- [x] [claude] Run duration in history panel cards: `duration_ms` added to `/runs` API response + HistoryPanel display

## ✅ Claude Agent — compare mode (this session)
- [x] [claude] Multi-topic compare mode frontend: CompareView.tsx with 2-3 side-by-side sentiment cards, independent useRunStream hooks per slot, ⊞ Compare button in header (569448e)

## ✅ Claude Agent — UI polish (this session)
- [x] [claude] Quote pagination: QuoteList shows 12 initially, show-more/less button
- [x] [claude] Auto-scroll to report on fresh run completion (requestAnimationFrame + scrollIntoView)
- [x] [claude] HistoryChart: CSS variables instead of hardcoded hex, subtle area fills under lines
- [x] [claude] ForceGraph: hide source/url/sentiment labels at zoom < 0.65 (less clutter)
- [x] [claude] CompareView: ↺ Reset button + ↗ Open full report per slot (wired to tab system)
- [x] [claude] Inline style cleanup: 100+ inline styles replaced with semantic CSS classes across all components

## Next Tasks (high value, unclaimed)
- [x] [claude] Contradiction detection in claims (_find_contradictions bigram grouping, amber card UI in Claims tab)
- [x] [claude] More Playwright E2E tests (saved search, thread click, shareable URL, compare mode, keyboard shortcuts)

## ✅ Cursor Agent — current session
- [x] [cursor] Fix timeline condensed-mode URL overlap (live preview hoisted to sibling li)
- [x] [cursor] Fix map/graph scroll-zoom hijacking page scroll (non-passive wheel listener)
- [x] [cursor] Ollama model warm-up on startup (parallel keep_alive pings in lifespan)
- [x] [cursor] Animated number counters on sentiment bars (RAF ease-out cubic)
- [x] [cursor] Dark/light theme transition animation (CSS transition on *, excluded SVGs)
- [x] [cursor] Sentiment confidence scores per item (prompt + confidence_map + badge UI)

## 🔴 NemoClaw Self-Analysis Findings — NEW
Audit run 2026-05-16 by nemotron-3-super against full project docs + code.
Full report: /tmp/autosentiment_self_analysis.md

### HIGH — Performance
- [ ] [pi]  Batch sentiment analysis: send multiple snippets per Ollama call instead of one-at-a-time
- [ ] [pi]  GPU utilization: track model load/unload timing, avoid 30B/120B thrashing

### HIGH — Reliability  
- [ ] [pi]  Retry logic + circuit breaker on all Ollama HTTP calls (exponential backoff, max 3 retries)
- [ ] [pi]  Transient failure recovery: don't crash entire run on one failed model call

### MEDIUM — Testing
- [ ] [pi]  LLM failure injection tests: mock Ollama returning 500s, timeouts, malformed JSON
- [ ] [pi]  Property-based tests for report builder functions (hypothesis or manual invariants)

### MEDIUM — Architecture
- [ ] [pi]  Extract synthesis interface from builder.py: decouple LLM prompt engineering from pure analytics
- [ ] [pi]  SQLite WAL mode + connection pooling for concurrent multi-tab write safety

### LOW — UX
- [ ] [pi]  Evidence modal: highlight matching terms, show why snippet got its sentiment label
- [ ] [pi]  Admin dashboard: quota usage over time, model availability, run success rate
- [ ] [pi]  Automatic model fallback: try smaller model if 120B/30B unavailable

### RISKS (preventative)
- [ ] [pi]  Fix SSE event listener accumulation in SPA (memory leak risk)
- [ ] [pi]  Add prompt injection guard: sanitize user topic before sending to LLM
- [ ] [pi]  Add Brave quota exhaustion early warning before deep runs
