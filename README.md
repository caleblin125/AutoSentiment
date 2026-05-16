# AutoSentiment

**Multi-source public sentiment intelligence** — a locally-hosted research tool that aggregates public opinion from dozens of sources, runs LLM-based sentiment analysis, and visualises findings in a real-time ROG-themed dashboard.

Designed for entertainment product teams, brand analysts, financial researchers, journalists, and the general public. AutoSentiment turns unstructured web opinion into structured, traceable reports with source-level provenance.

---

## Purpose

AutoSentiment answers "what does the internet think about X?" by:

1. **Searching** Brave Search across 10+ purpose-labeled queries (official sources, public opinion, expert reviews, social media, forums, international angles)
2. **Fetching** full article/comment text from each URL
3. **Classifying** every snippet as positive, neutral, or negative via local LLM
4. **Synthesizing** themes, narrative, chronology, factual claims, topic threads, and an idea graph
5. **Presenting** everything in a tabbed report with source links, evidence inspection, and export

Every opinion is traceable back to its source URL. Every claim shows corroborating domains. Every date comes from explicit text.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│               Browser (Vite + React)                  │
│  Tabs │ Timeline │ Report (Summary/Topics/Timeline/  │
│  Evidence/Claims/Graph/Performance)                   │
└───────────────────────┬──────────────────────────────┘
                        │ SSE + REST (FastAPI)
┌───────────────────────▼──────────────────────────────┐
│                 FastAPI Backend                       │
│  /api/runs  /api/search-plan  /api/suggest            │
│  /api/diagnostics  SSE event bus  ·  asyncio tasks    │
└─────────┬───────────────────┬────────────────────────┘
          │                   │
┌─────────▼──────┐  ┌─────────▼──────────────────────┐
│  SQLite DB     │  │  Ollama / llama.cpp server       │
│  (aiosqlite)   │  │   nemotron-3-super:120b → NemoClaw│
│  Brave quota   │  │   nemotron-3-nano:30b  → sentiment│
│  tracker       │  │   deepseek-r1:14b      → suggest  │
└────────────────┘  └──────────────────────────────────┘
                            │
                   ┌────────▼────────┐
                   │ Brave Search API │
                   │  (1 req/s, 2k/mo)│
                   └─────────────────┘
```

### Pipeline (per run)

1. **Search planning** — purpose-labeled queries (official/factual, public opinion, expert reviews, complaints, social/video, international) tailored to use case
2. **Query expansion** — 120B model generates additional query variants
3. **Brave search** — rate-limited to 1 req/s with 30-min in-process cache; records monthly quota usage
4. **Parallel fetch** — `asyncio.as_completed` with concurrency cap and 15s per-URL timeout; trafilatura extraction in worker threads
5. **Sentiment analysis** — 30B model per item, bounded parallel queue with snippet deduplication
6. **Report assembly** — pure Python: counts, quotes, aspects, source facts, timeline, claims, threads, graph
7. **Synthesis** — 120B model writes themes + narrative from pre-computed counts
8. **SSE streaming** — every stage event streamed to frontend in real time

---

## Use Cases

| Mode | Focus | Best for |
|------|-------|----------|
| **Generic** | Broad sentiment + themes | General topic research |
| **Entertainment** | Fandom, critics, box office, launch risk | Studios, publishers, game teams |
| **Current event** | Chronology, fact check, source credibility | Journalists, general public |
| **Brand/product** | Reviews, market position, support risk | Brand teams, product managers |
| **Policy/civic** | Official documents, legal, public reaction | Policy analysts, advocates |
| **Financial** | Market data, analyst ratings, retail sentiment, SEC filings | Investors, traders, analysts |

---

## Features

### Research depth presets
Choose from Quick, Standard, Deep, or Exhaustive before running. Each preset controls query count, URL budget, item budget, source diversity, and synthesis sample size. Expand a completed run to a deeper preset without repeating work.

### Search planning & quota management
Before a run starts, the UI previews planned queries, purpose labels, estimated Brave query cost, and remaining monthly quota. SQLite-backed quota tracker prevents accidental overuse under the free plan.

### Multi-tab search
Open multiple concurrent searches in separate tabs. Tab state persists to localStorage and survives page reload. Running tabs reconnect their SSE stream on reload.

### Tabbed report
Completed reports use a tabbed layout:
- **Summary** — sentiment bars, use-case decision cards, themes, narrative, chart data
- **Topics** — fine-grain recurring phrase threads with source count, date range, and sentiment. Click any thread to search for deeper sentiment on that subtopic.
- **Timeline** — extracted dates with event cards, certainty labels, and supporting evidence links
- **Evidence** — top quotes by sentiment with source logos, inspect modal, and source-fact accordion grouped by type
- **Claims** — factual-looking claims with corroboration scores, supporting domains, and verification flags
- **Graph** — force-directed idea graph with node repositioning, filters, and click-to-inspect popovers
- **Performance** — stage-by-stage timing breakdown, optimization tips, and run metadata

### Evidence inspection modal
Click "inspect" on any quote to see: full snippet, key terms, scope, model summary, sentiment, related dates, related claims, and related topics — all linked to source URLs.

### Chronological timeline
Extracts explicit dates from evidence text (ISO and natural formats). Reports start date, end date, important dated events with labels, descriptions, and source counts. Does not fabricate dates.

### Fact & evidence layer
Groups declarative claims across sources. Shows corroborating domains, source types, confidence scores, and verification flags. Separates opinion from factual-looking claims without declaring truth.

### Topic threads
Fine-grain recurring phrases appearing across multiple sources. Each thread shows sentiment distribution, source domains, date range, and sample snippets. Click any thread to launch a new sentiment search on that subtopic.

### Cancel + Expand
- **Cancel** — cooperative cancel checked at pipeline stage boundaries; works between LLM tokens and within 12s Brave search timeout
- **Expand** — creates a new run with deeper budget, copies existing evidence, and fetches only new sources. Inherits original freshness by default.

### NemoClaw autonomous agent
Activatable after completion — generates expert research angles, searches independently, and produces structured analysis with verdict + findings.

### Idea graph
Force-directed physics graph with node filters (hide zero-count sentiment, show only credible sources). Left-click for detail popovers with evidence links. Right-drag to reposition. Positions persist per run.

### Export
JSON report, CSV evidence table, and Markdown executive summary — downloadable from the report header.

### Diagnostics
`GET /api/diagnostics` reports DB readiness, Brave key presence (without exposing the key), configured models, run counts, active SSE queues.

### Structured logging & error codes
Every log message includes `[run=<id>]`. Error SSE events carry explicit codes: `brave_key_missing`, `brave_quota_exceeded`, `model_unavailable`, `fetch_timeout`, `synthesis_failed`, `cancelled_by_user`.

### Durable task state
On backend restart, any runs left in `running` state are marked `error` so the database reflects reality.

### Auth (optional)
Set `AUTH_API_KEY` in `.env` to require `X-API-Key` header on all mutating endpoints. Leave empty for localhost use.

### Dev mode
Press **Ctrl+Shift+D** for the dev overlay: SSE queue count, run counts by status, model assignments, session size.

---

## Models

| Model | Role | VRAM | Notes |
|---|---|---|---|
| `nemotron-3-super:120b` | Query expansion, synthesis, NemoClaw | ~87 GB | Highest quality |
| `nemotron-3-nano:30b` | Per-item sentiment | ~28 GB | Fast, parallel |
| `deepseek-r1:14b` | Search angle suggestions | ~9 GB | Low latency |

Accleration via direct llama.cpp server can be benchmarked with:

```bash
cd backend && source .venv/bin/activate
python3 scripts/benchmark_llamacpp.py --model nemotron-3-nano
```

---

## Running

### Prerequisites
- Ollama with models: `nemotron-3-super:120b`, `nemotron-3-nano:30b`, `deepseek-r1:14b`
- Or llama.cpp server with equivalent GGUF models
- Brave Search API key (free tier: 1 req/s, 2,000 queries/month)
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
npm run dev -- --host 0.0.0.0 --port 5173
```

Open `http://localhost:5173`.

### Tests

```bash
cd backend && source .venv/bin/activate
python3 -m pytest tests/ -v        # 60 tests
cd frontend && npm run lint && npm run build  # TypeScript + ESLint
```

### Benchmarks

```bash
cd backend && source .venv/bin/activate
python3 scripts/benchmark_pipeline.py       # Pipeline hot-path benchmarks
python3 scripts/benchmark_llamacpp.py       # Ollama vs llama.cpp comparison
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama or llama.cpp server |
| `NEMCLAW_MODEL` | `nemotron-3-super` | 120B model for expansion + synthesis |
| `LIGHTWEIGHT_MODEL` | `nemotron-3-nano` | 30B model for per-item sentiment |
| `BRAVE_API_KEY` | — | **Required.** Brave Search API key |
| `MAX_QUERIES_PER_RUN` | `16` | Default query budget (overridden by depth) |
| `MAX_URLS_PER_RUN` | `100` | Default URL budget |
| `MAX_ITEMS_PER_RUN` | `300` | Default item budget |
| `LIGHT_QUEUE_MAX_PARALLEL` | `4` | Concurrent sentiment calls |
| `AUTH_API_KEY` | — | Optional. Set to enable API key auth |

---

## Project structure

```
AutoSentiment/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── orchestrator.py      # Main pipeline + error codes + structured logging
│   │   │   ├── nemoclaw.py          # Query expansion, synthesis, suggestions
│   │   │   ├── nemoclaw_agent.py    # Autonomous NemoClaw research agent
│   │   │   ├── light_queue.py       # Bounded parallel sentiment queue
│   │   │   └── types.py             # SSEEventType, SentimentLabel, SourceType enums
│   │   ├── api/
│   │   │   ├── routes.py            # HTTP endpoints + auth dependency
│   │   │   └── event_bus.py         # In-process SSE queue + cancel signalling
│   │   ├── core/config.py           # Pydantic settings
│   │   ├── db/session.py            # SQLite async session factory
│   │   ├── ingest/fetch.py          # URL fetch + source classification
│   │   ├── models.py                # SQLAlchemy Run, RunEvent, EvidenceChunk, BraveQuotaUsage
│   │   ├── reports/builder.py       # Counts, quotes, aspects, source facts, timeline, claims, threads, graph
│   │   ├── research_depth.py        # Depth presets + budget clamping
│   │   ├── search_planner.py        # Purpose-labeled query plans + Brave quota tracking
│   │   └── tools/search.py          # Brave search with cache + rate limiting
│   ├── scripts/
│   │   ├── benchmark_pipeline.py    # Hot-path benchmarks
│   │   └── benchmark_llamacpp.py    # Ollama vs llama.cpp comparison
│   └── tests/
│       ├── test_fetch.py            # Source classification + fetch
│       ├── test_llm.py              # Ollama streaming + cancel_check
│       ├── test_orchestrator.py     # Pipeline stages + cancel + expand
│       ├── test_reports.py          # Builder functions + timeline + claims + threads
│       ├── test_research_depth.py   # Depth validation + next depth
│       ├── test_routes.py           # API endpoint behaviour + cache + diagnostics
│       ├── test_search.py           # Brave search + caching
│       └── test_search_planner.py   # Query planning + quota accounting
└── frontend/
    └── src/
        ├── components/
        │   ├── App.tsx              # Session persistence, tab management, SSE reconnect
        │   ├── TabBar.tsx           # Tab navigation + running count
        │   ├── RunView.tsx          # Search form, depth/use-case selectors, budget preview, loading stage
        │   ├── EventTimeline.tsx    # Collapsible live event stream
        │   ├── ReportView.tsx       # Tabbed report (Summary/Topics/Timeline/Evidence/Claims/Graph/Performance)
        │   ├── ForceGraph.tsx       # Physics-based idea graph with filters + node repositioning
        │   ├── HistoryPanel.tsx     # All-status history with auto-poll
        │   ├── NemoClawPanel.tsx    # NemoClaw autonomous agent UI
        │   ├── HistoryChart.tsx     # Sentiment trend over time
        │   └── DevOverlay.tsx       # Dev mode stats panel
        ├── hooks/useRunStream.ts    # SSE consumer hook
        └── lib/api.ts               # Typed API client + all interfaces
```
