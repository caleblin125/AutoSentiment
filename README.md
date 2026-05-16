# AutoSentiment

**Multi-source public sentiment intelligence** — a locally-hosted research tool that aggregates public opinion from dozens of sources, runs LLM-based sentiment analysis, and visualises findings in a real-time ROG-themed dashboard.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              Browser (Vite + React)          │
│  Tabs │ Timeline │ Report │ NemoClaw Panel   │
└────────────────────┬────────────────────────┘
                     │ SSE + REST (FastAPI)
┌────────────────────▼────────────────────────┐
│              FastAPI Backend                 │
│  /api/runs  /api/suggest  /api/dev/stats     │
│  SSE event bus  ·  asyncio task pool         │
└──────┬──────────────┬────────────────────────┘
       │              │
┌──────▼──────┐ ┌──────▼──────────────────────┐
│ SQLite DB   │ │ Ollama (local LLM server)    │
│ (aiosqlite) │ │  nemotron-3-super:120b  ← NemoClaw  │
│             │ │  nemotron3:33b          ← sentiment │
└─────────────┘ │  deepseek-r1:14b        ← suggest   │
                └──────────────────────────────┘
                         │
                ┌────────▼────────┐
                │ Brave Search API │
                └─────────────────┘
```

### Pipeline (per run)

1. **Query expansion** — NemoClaw (120B) generates 5 search query variants
2. **Platform queries** — adds 20+ queries across Quora, YouTube, X, Threads, LinkedIn, Trustpilot, Reddit, HN, StackExchange, G2, ProductHunt + 8 international languages
3. **Brave search** — rate-limited to 1 req/s; deduplicates URLs
4. **Parallel fetch** — `asyncio.as_completed` with concurrency cap; extracts article text
5. **Sentiment analysis** — 33B model per item, bounded parallel queue
6. **Synthesis** — 120B model writes themes, narrative, impacts, reasons, arguments
7. **Report** — stored in SQLite, streamed to frontend

---

## Models

| Model | Role | Notes |
|---|---|---|
| `nemotron-3-super:120b` | NemoClaw — query expansion, synthesis, NemoClaw agent | ~87 GB |
| `nemotron3:33b` | Per-item sentiment analysis | ~28 GB |
| `deepseek-r1:14b` | Search angle suggestions (fast, low latency) | ~9 GB |

---

## Features

### Multi-tab search
- Open multiple concurrent searches in separate tabs
- Each tab runs an independent pipeline
- Tab state (runId, topic, status) persisted to `localStorage` — survives page reload

### Closing a tab cancels its task
- If a search is running when its tab is closed, a cancel signal is sent to the backend immediately

### Real-time timeline
- Every pipeline event streams via Server-Sent Events as it happens
- URL fetch events show clickable URLs with per-URL timing and item counts
- High-credibility sources (Reuters, BBC, Nature, .gov, etc.) marked with ★
- Collapsible — fold the timeline away once the report loads

### History panel
- Shows all recent searches in all states (running ●, completed ✓, cancelled ⊘, error ⚠)
- Auto-polls every 5 s when open
- Refreshes immediately after each run completes
- Click any completed run to replay its full event history in the current tab

### Cancel + Expand
- **Cancel** — cooperative cancel checked at each pipeline stage boundary
- **Expand** — creates a new run with 2× URL/item budget and no freshness restriction

### NemoClaw autonomous agent
Activated via **⬡ NemoClaw** button after a run completes.

- Uses the 120B model to generate 4 expert research angles independent of the main pipeline
- Searches those angles via Brave, fetches targeted content, and produces a structured expert analysis:
  - Summary · Verdict · Key findings · Opportunities · Risks
- Streams live activity so you can watch it work

### Idea graph
- Force-directed physics simulation (Verlet + Coulomb + Hooke)
- **Left-click source node** → URL popover with all domain links
- **Left-click theme/aspect node** → topic detail popover with supporting evidence and clickable source links
- **Left-click sentiment node** → scrolls to + pulses the matching quote section
- Right-click + drag → reposition any node

### Search suggestions
- After 700 ms of pause while typing, `deepseek-r1:14b` generates 5 research-angle suggestions
- Click a suggestion to fill the search box

### Performance report
- Timing breakdown per pipeline stage with a "slowest" indicator
- Expandable **optimization tips** panel explaining how to speed up each stage

### Dev mode
- Press **Ctrl+Shift+D** (or click ⚙ in the header) for the dev overlay
- Shows: live SSE queue count, run counts by status, model assignments, session size
- Auto-refreshes every 3 s

---

## Running

### Prerequisites
- Ollama with models pulled: `nemotron-3-super`, `nemotron3:33b`, `deepseek-r1:14b`
- Brave Search API key (free tier works)
- Python 3.12+ · Node.js 20+

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in BRAVE_API_KEY
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`

### Tests

```bash
cd backend && source .venv/bin/activate
python3 -m pytest tests/ -v
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `NEMCLAW_MODEL` | `nemotron-3-super` | 120B model for expansion + synthesis + NemoClaw |
| `LIGHTWEIGHT_MODEL` | `nemotron3:33b` | Sentiment model |
| `BRAVE_API_KEY` | — | Required for search |
| `MAX_URLS_PER_RUN` | `30` | URL budget per run |
| `MAX_ITEMS_PER_RUN` | `100` | Item budget per run |
| `LIGHT_QUEUE_MAX_PARALLEL` | `4` | Concurrent sentiment calls |

---

## Project structure

```
AutoSentiment/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── nemoclaw.py          # Query expansion, synthesis, suggestions
│   │   │   ├── nemoclaw_agent.py    # Autonomous NemoClaw research agent
│   │   │   ├── orchestrator.py      # Main pipeline orchestration
│   │   │   ├── light_queue.py       # Bounded parallel sentiment queue
│   │   │   └── types.py             # SSEEventType, SentimentLabel enums
│   │   ├── api/
│   │   │   ├── routes.py            # All HTTP endpoints
│   │   │   └── event_bus.py         # In-process SSE queue + cancel signalling
│   │   ├── db/session.py            # SQLite async session factory
│   │   ├── ingest/fetch.py          # URL fetching + text extraction
│   │   ├── models.py                # SQLAlchemy Run, RunEvent, EvidenceChunk
│   │   ├── reports/builder.py       # Report assembly (aspects, graph, quotes)
│   │   └── tools/search.py          # Brave Search wrapper
│   └── tests/                       # 37 async pytest tests
└── frontend/
    └── src/
        ├── components/
        │   ├── App.tsx              # Session persistence, tab management
        │   ├── TabBar.tsx           # Tab navigation + running count
        │   ├── RunView.tsx          # Per-tab search + controls
        │   ├── EventTimeline.tsx    # Collapsible live event stream
        │   ├── ReportView.tsx       # Full report display
        │   ├── ForceGraph.tsx       # Physics-based idea graph
        │   ├── HistoryPanel.tsx     # All-status history with auto-poll
        │   ├── NemoClawPanel.tsx    # NemoClaw autonomous agent UI
        │   ├── HistoryChart.tsx     # Sentiment trend over time
        │   └── DevOverlay.tsx       # Dev mode stats panel
        ├── hooks/useRunStream.ts    # SSE consumer hook
        └── lib/api.ts               # All typed API client functions
```
