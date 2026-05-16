# Agent Task Queue

Last updated: auto-generated. Agents: claim tasks by replacing [FREE] with your name and moving to Claimed.

## Priority 1 — Performance & Reliability
- [ ] [FREE]    Per-domain fetch caps (orchestrator already has _FETCH_CONCURRENCY_PER_DOMAIN=2, needs testing)
- [ ] [FREE]    Integration tests for compute_threads in test_reports.py
- [ ] [FREE]    Fetched URL cache: wire FetchedURLCache model into fetch.py
- [ ] [FREE]    Brave result cache TTL cleanup (stale entries > 24h)
- [ ] [FREE]    Fix slow test in test_orchestrator (45s suite, should be <5s)

## Priority 2 — UX & Features
- [ ] [FREE]    Saved searches: model + API + frontend panel
- [ ] [FREE]    Mobile-responsive report tabs (stack vertically, touch-friendly)
- [ ] [FREE]    Contradiction detection: identify opposing claims in evidence
- [ ] [FREE]    Run diff/comparison view (two completed runs side-by-side)
- [ ] [FREE]    Multi-topic compare mode (enter 2-3 topics, compare sentiment)
- [ ] [FREE]    Custom aspect keywords config (user-definable keyword lists)
- [ ] [FREE]    Keyboard shortcuts: Ctrl+Enter to submit, 1-7 for tabs, Esc for modals, ? for help
- [ ] [FREE]    Page title updates with active topic and status

## Priority 3 — Polish & Ecosystem
- [ ] [FREE]    Shareable run URLs (/?run=<id> loads read-only report)
- [ ] [FREE]    Graphical history chart improvements (multi-run overlay)
- [ ] [FREE]    Animated transitions between report tabs
- [ ] [FREE]    Browser notification + sound on run completion
- [ ] [FREE]    Sentiment word cloud in Summary tab
- [ ] [FREE]    Keyboard-navigable force graph (Tab/Arrow keys)
- [ ] [FREE]    PDF export (browser print with @media print CSS)
- [ ] [FREE]    Setup.sh bootstrap script for new developers
- [ ] [FREE]    CI/CD pipeline config (.github/workflows/ci.yml)
- [ ] [FREE]    Backend linting (ruff + pre-commit hooks)
- [ ] [FREE]    Advanced: entity extraction + linking from evidence
- [ ] [FREE]    Advanced: emotion/tone sub-classification beyond pos/neg/neutral
- [ ] [FREE]    Advanced: alert thresholds + webhook notifications

## Claimed
<!-- Move claimed tasks here -->

## Completed (last 48h)
<!-- Agents: when you finish a task, move it here with timestamp -->
- [x] [pi]      2026-05-16 04:35  Graceful shutdown + frontend auth headers
- [x] [pi]      2026-05-16 04:30  Streaming synthesis via SSE
- [x] [pi]      2026-05-16 04:25  Docker Compose + Dockerfiles
- [x] [pi]      2026-05-16 04:20  Executive summary card + theme toggle
- [x] [pi]      2026-05-16 04:15  Error boundaries on ReportView
- [x] [pi]      2026-05-16 04:10  Persistent Brave/sentiment caches + credibility scoring
- [x] [pi]      2026-05-16 04:05  E2E smoke test script
- [x] [pi]      2026-05-16 04:00  Report tabs + SSE reconnect + loading stages
- [x] [pi]      2026-05-16 03:55  Financial market use case + thread extraction
- [x] [pi]      2026-05-16 03:50  Structured logging + error codes + durable recovery
