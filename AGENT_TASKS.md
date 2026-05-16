# Agent Task Queue

Last updated: 2026-05-16 20:40 UTC

## ✅ PI Agent — COMPLETED THIS SESSION
- [x] [pi]  Shareable run URLs: `/?run=<id>` + 🔗 Link button + clipboard copy
- [x] [pi]  Setup script: `./setup.sh` (venv, pip, npm, .env, DB init, verify)
- [x] [pi]  Backend linting: ruff config + pre-commit hooks
- [x] [pi]  CI/CD pipeline: .github/workflows/ci.yml (test + lint + build + secret scan)

## ✅ ALREADY DONE (discovered during audit — Claude)
- [x] [claude] Graph position persistence (localStorage keyed per run_id) — already implemented
- [x] [claude] FetchedURLCache TTL eviction (7-day, on startup) — already implemented

## 🟡 Claude Agent — remaining UI polish
- [ ] [claude] Light theme: audit remaining hardcoded colors
- [ ] [claude] useEffect cleanups: EventTimeline SSE disconnect, ForceGraph simulation
- [ ] [claude] Error boundaries on ForceGraph, EventTimeline, HistoryPanel

## Next Tasks (high value, unclaimed)
- [ ] [FREE]  Multi-topic compare mode: enter 2-3 topics, compare side-by-side
- [ ] [FREE]  Saved searches frontend panel (model + API already exist)
- [ ] [FREE]  Sentiment confidence scores per item (prompt template change)
- [ ] [FREE]  Contradiction detection in claims (opposing claim pairs)
- [ ] [FREE]  Browser notification on run completion
- [ ] [FREE]  More Playwright E2E tests (saved search, thread click, shareable URL)
- [ ] [FREE]  Ollama model warm-up on startup (tiny prompt to avoid cold start)
- [ ] [FREE]  Frontend dark/light theme transition animation
- [ ] [FREE]  Run duration shown in history panel cards
- [ ] [FREE]  Animated number counters on sentiment bars
