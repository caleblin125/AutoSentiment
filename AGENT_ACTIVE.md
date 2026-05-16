# Active Agent Sessions

Last updated: 2026-05-16 05:00 UTC

| Agent | Session | Claimed Task | Working File | Status | Since |
|-------|---------|-------------|--------------|--------|-------|
| pi | main | UI polish (CSS vars, keyboard shortcuts, mobile, print, page titles) | App.css, RunView.tsx | active | 05:00 |
| claude | autosentiment-claude | Component splitting, CSS cleanup, inline style migration | ReportView.tsx, App.css | active | 04:55 |
| cursor | autosentiment-cursor | Search optimization (parallel media APIs, cache batching, dedup) | orchestrator.py, media_apis.py, search.py | active | 05:00 |

## Conflict Rules
1. **pi** owns: App.css (utility classes), RunView.tsx, tests/, documentation
2. **claude** owns: ReportView.tsx sub-components, ForceGraph.tsx, EventTimeline.tsx, HistoryPanel.tsx, App.css (component-specific styles)
3. **cursor** owns: orchestrator.py, media_apis.py, search.py, fetch.py, models/
4. If overlap on App.css: pi adds utility classes at top; claude adds component styles after
5. Before committing, check AGENT_ACTIVE.md. If another agent committed, git pull first.
6. Leave messages in AGENT_MAILBOX.md for cross-agent communication.
