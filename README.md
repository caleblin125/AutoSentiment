# AutoSentiment

**Multi-source public sentiment intelligence** — a locally-hosted research tool that searches the web, runs LLM-based sentiment analysis on every result, and delivers a structured, traceable report in real time.

Type a topic. Pick a time window and research depth. AutoSentiment searches Brave, fetches full article and forum text, classifies every snippet as positive, neutral, or negative with a local 30B model, then uses a 120B model to synthesize themes, narrative, and a fact layer — all streamed live to a tabbed dashboard.

Every opinion links back to its source URL. Every claim shows corroborating domains. Every date is extracted from the text, never fabricated.

---

## Table of contents

- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Manual setup](#manual-setup)
- [Docker](#docker)
- [Configuration](#configuration)
- [Using the app](#using-the-app)
- [Use cases](#use-cases)
- [Running tests](#running-tests)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required

| Requirement | Notes |
|---|---|
| **Python 3.12+** | Backend |
| **Node.js 20+** | Frontend |
| **Ollama** or **llama.cpp server** | Local LLM inference — [ollama.ai](https://ollama.ai) |
| **Brave Search API key** | Free tier: 1 req/s, 2,000 queries/month — [brave.com/search/api](https://brave.com/search/api/) |

> **Note:** For llama.cpp, benchmark with `python3 scripts/benchmark_llamacpp.py` to compare throughput against Ollama.

### Ollama models

AutoSentiment uses three models served from Ollama. Pull them before starting:

```bash
ollama pull nemotron-3-super    # 120B — synthesis, query expansion, NemoClaw agent
ollama pull nemotron-3-nano     # 30B  — per-item sentiment classification
ollama pull deepseek-r1:14b     # 14B  — search angle suggestions
```

> **Hardware:** 120B + 30B simultaneously requires ~115 GB VRAM (tested on DGX Spark, 2× H100). For lower-VRAM setups, swap `nemotron-3-super` for a smaller model — see [Configuration](#configuration).

### Optional

- **Docker + Docker Compose** — for containerised deployment
- **NVIDIA GPU** with CUDA drivers — for GPU-accelerated Ollama

---

## Quick start

The fastest path from clone to running app:

```bash
git clone https://github.com/<your-org>/AutoSentiment.git
cd AutoSentiment

# Install all dependencies, create .env files, initialise the database
./setup.sh
```

`setup.sh` creates `backend/.venv`, installs Python and npm packages, copies `.env.example` to `.env`, and initialises the SQLite database.

After it completes:

1. **Add your Brave API key** to `backend/.env`:

   ```ini
   BRAVE_API_KEY=BSA_your_key_here
   ```

2. **Start the backend** (terminal 1):

   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Start the frontend** (terminal 2):

   ```bash
   cd frontend
   npm run dev
   ```

4. Open **http://localhost:5173**

---

## Manual setup

If you prefer step-by-step control over the automated script:

### Backend

```bash
cd backend

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Open .env and set BRAVE_API_KEY (required) and any other settings

# Initialise the database
python3 -c "import asyncio; from app.db.session import create_tables; asyncio.run(create_tables())"

# Start the API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend starts at **http://localhost:8000**. Check health: `curl http://localhost:8000/api/health`.

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Configure API URL (only needed if backend is not on localhost:8000)
cp .env.example .env
# Set VITE_API_URL=http://<backend-host>:8000

# Start the development server
npm run dev
```

The frontend starts at **http://localhost:5173**.

---

## Docker

Docker Compose runs the backend and frontend as containers. Ollama must be running externally (or use the GPU profile below).

### Without local Ollama (external Ollama server)

```bash
# Set required variables
export BRAVE_API_KEY=BSA_your_key_here
export OLLAMA_BASE_URL=http://your-ollama-host:11434   # default: localhost

docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:5173

### With local Ollama (GPU profile)

Starts an Ollama container alongside the app. Requires an NVIDIA GPU with the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed.

```bash
export BRAVE_API_KEY=BSA_your_key_here
docker compose --profile gpu up --build
```

Pull models into the Ollama container after it starts:

```bash
docker compose exec ollama ollama pull nemotron-3-super
docker compose exec ollama ollama pull nemotron-3-nano
docker compose exec ollama ollama pull deepseek-r1:14b
```

### Persistent data

The `backend_data` Docker volume stores the SQLite database. Data survives container restarts and `docker compose down`. To wipe all data: `docker compose down -v`.

---

## Configuration

All configuration lives in `backend/.env`. Copy `backend/.env.example` as a starting point.

| Variable | Default | Description |
|---|---|---|
| `BRAVE_API_KEY` | *(empty)* | **Required.** Brave Search API key |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama or llama.cpp server URL |
| `NEMCLAW_MODEL` | `nemotron-3-super` | 120B model — synthesis, expansion, NemoClaw |
| `LIGHTWEIGHT_MODEL` | `nemotron-3-nano` | 30B model — per-item sentiment |
| `SUGGESTION_MODEL` | `deepseek-r1:14b` | 14B model — search angle suggestions |
| `LIGHT_QUEUE_MAX_PARALLEL` | `4` | Max concurrent sentiment calls |
| `MAX_QUERIES_PER_RUN` | `16` | Default Brave query budget per run |
| `MAX_URLS_PER_RUN` | `30` | Default URL fetch budget per run |
| `MAX_ITEMS_PER_RUN` | `100` | Default evidence item budget per run |
| `AUTH_API_KEY` | *(empty)* | Optional. When set, requires `X-API-Key` header on all API requests |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed frontend origins |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` | SQLite path (rarely needs changing) |
| `FETCHED_URL_CACHE_TTL_SECONDS` | `86400` | Cross-run URL fetch cache TTL (seconds). Set `0` to disable |

### Using smaller models

If you don't have enough VRAM for 120B + 30B simultaneously, substitute smaller models:

```ini
NEMCLAW_MODEL=deepseek-r1:14b
LIGHTWEIGHT_MODEL=deepseek-r1:8b
LIGHT_QUEUE_MAX_PARALLEL=2
```

Quality of synthesis and query expansion will be lower, but the pipeline still works end-to-end.

### Frontend environment

`frontend/.env` (created from `frontend/.env.example`) has one variable:

```ini
VITE_API_URL=http://localhost:8000
```

Change this if the backend is on a different host or port.

---

## Using the app

### 1. Start a search

Enter a topic in the search bar — any keyword, phrase, product name, event, or person. Examples:

- `Tesla Model 3`
- `Dune Part Two`
- `California drought`
- `ChatGPT`
- `Apple Vision Pro`

### 2. Choose your settings

Before running, configure three optional settings:

**Freshness** — time window for results:
| Option | Coverage |
|---|---|
| Past 24 hours | Breaking news and very recent posts |
| Past week | Recent coverage |
| Past month | Standard (default) |
| Past year | Broader historical view |
| Any time | All available results |

**Research depth** — controls how many queries, URLs, and items are analysed:
| Preset | Queries | URLs | Items | Best for |
|---|---|---|---|---|
| Quick | 3 | 12 | 40 | Fast gut-check |
| Standard | 6 | 30 | 100 | Everyday research |
| Deep | 10 | 60 | 180 | Thorough analysis |
| Exhaustive | 16 | 100 | 300 | Maximum coverage |

**Use case** — shapes which report sections are emphasised:
- Generic (default)
- Entertainment product
- Current event / breaking news
- Brand or product research
- Policy / civic issue
- Financial / market

### 3. Preview the search plan

The search plan panel appears before you start. It shows each planned query with its purpose label (official sources, public opinion, expert review, complaints, social/video, international angles) and the estimated Brave query cost against your remaining monthly quota.

Click **Start** when ready.

### 4. Watch the live stream

The event stream panel shows each pipeline stage as it completes:
- Search queries executing
- URLs being fetched
- Sentiment classifications per item
- Report assembly
- Synthesis in progress

You can **cancel** at any time. The run saves all evidence collected so far and marks itself cancelled. Cancelled runs can be re-opened and expanded later.

### 5. Read the report

Completed runs open a tabbed report:

| Tab | Contents |
|---|---|
| **Summary** | Sentiment bars, decision cards for your use case, themes, narrative, and chart data |
| **Topics** | Recurring phrase threads with sentiment distribution, source domains, and date range. Click any thread to launch a deeper search on that subtopic. |
| **Timeline** | Dates extracted from evidence text with event cards and source links. Only explicit dates — nothing fabricated. |
| **Evidence** | Top quotes by sentiment. Click **Inspect** on any quote for the full snippet, key terms, model summary, related claims, and related topics. |
| **Claims** | Factual-looking claims with corroboration scores, supporting domains, and verification flags. |
| **Graph** | Force-directed idea graph. Left-click a node for a detail popover. Right-drag to reposition nodes. Use filters to hide zero-count nodes or show only credible sources. |
| **Performance** | Stage-by-stage timing breakdown and run metadata. |

### 6. Export results

From the report header, download:
- **JSON** — full structured report with all evidence
- **CSV** — evidence table for spreadsheet analysis
- **Markdown** — executive summary for sharing

### 7. Expand a run

Click **Expand** on any completed or cancelled run to re-run at a deeper depth preset. The expanded run inherits all existing evidence and only fetches new sources, so it finishes faster than starting fresh.

### 8. Saved searches

Click the star icon or **Save** button to bookmark a search configuration (topic + freshness + depth + use case). Saved searches appear in the history panel and can be replayed with one click.

### 9. Compare mode

Open multiple tabs using the **+** button in the tab bar. Each tab is an independent search. The compare panel lets you view two runs side by side.

### 10. NemoClaw autonomous agent

After a run completes, click **NemoClaw** to activate the autonomous research agent. NemoClaw generates expert research angles based on the initial report, searches independently, and produces structured analysis with a verdict and supporting findings.

### 13. NemoClaw self-analysis

Run NemoClaw against the project itself for an architectural audit:

```bash
cd backend && source .venv/bin/activate
RUN_SELF_ANALYSIS=1 pytest tests/test_self_analysis.py -v -s
```

The 120B model reads all project docs and code, then outputs a structured report with: verdict, strengths, problems (severity + area + impact), concrete suggestions (priority + effort), missing features, and risks. Results are also saved to `/tmp/autosentiment_self_analysis.md`.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Start / submit search |
| `Ctrl+T` | New tab |
| `Ctrl+W` | Close active tab |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Cycle tabs forward / backward |
| `1`–`7` | Switch report tabs (Summary, Topics, Timeline, Evidence, Claims, Graph, Performance) |
| `Escape` | Close modal / evidence inspector |
| `?` | Show keyboard shortcut help |
| `Ctrl+Shift+D` | Toggle dev overlay (SSE queue stats, model info) |

---

## Use cases

| Mode | What it surfaces | Best for |
|---|---|---|
| **Generic** | Broad sentiment + recurring themes | General topic research |
| **Entertainment** | Fandom pulse, critic coverage, box office sentiment, launch risk signals | Studios, publishers, game teams |
| **Current event** | Chronology, fact check, source credibility, disputed claims | Journalists, general public |
| **Brand / product** | Reviews, market position, support risk, competitor mentions | Brand teams, product managers |
| **Policy / civic** | Official documents, legal context, public reaction | Policy analysts, advocates |
| **Financial / market** | Analyst ratings, retail sentiment, market commentary | Investors, traders, analysts |

---

## Running tests

### Backend unit and integration tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

117 tests covering the pipeline, report builder, LLM client, search, fetch, API routes, media APIs, and property-based invariants. Two tests are skipped (require a live Ollama connection or E2E environment).

See [`backend/tests/README.md`](backend/tests/README.md) for a full description of every test file and what each test covers.

Run a single test file:

```bash
pytest tests/test_reports.py -v
pytest tests/test_orchestrator.py -v
```

### Frontend type check and lint

```bash
cd frontend
npx tsc --noEmit      # TypeScript check
npm run lint          # ESLint
npm run build         # Full production build (includes TS compilation)
```

### End-to-end tests (Playwright)

```bash
cd frontend
npm run test:e2e
```

E2E tests mock the backend via `page.route()` so they run without a live server.

### Performance benchmarks

```bash
cd backend
source .venv/bin/activate
python3 scripts/benchmark_pipeline.py      # Report builder hot-path
python3 scripts/benchmark_llamacpp.py      # Ollama vs llama.cpp throughput
```

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│               Browser (Vite + React 19)               │
│  Tabs · Timeline · Report (Summary/Topics/Timeline/  │
│  Evidence/Claims/Graph/Performance)                   │
└───────────────────────┬──────────────────────────────┘
                        │ SSE + REST (FastAPI)
┌───────────────────────▼──────────────────────────────┐
│                 FastAPI Backend                       │
│  /api/runs  /api/search-plan  /api/suggest            │
│  /api/diagnostics  ·  asyncio tasks  ·  SSE bus      │
└─────────┬───────────────────┬────────────────────────┘
          │                   │
┌─────────▼──────┐  ┌─────────▼──────────────────────┐
│  SQLite DB     │  │  Ollama server                   │
│  (aiosqlite)   │  │   nemotron-3-super:120b          │
│  WAL mode      │  │   nemotron-3-nano:30b            │
│  Brave quota   │  │   deepseek-r1:14b                │
│  tracker       │  └──────────────┬─────────────────-┘
└────────────────┘                 │
                          ┌────────▼────────┐
                          │ Brave Search API │
                          │  (1 req/s, 2k/mo)│
                          └─────────────────┘
```

### Pipeline (per run)

1. **Search planning** — purpose-labeled queries tailored to use case and freshness
2. **Query expansion** — 120B model generates additional search variants
3. **Brave search** — rate-limited to 1 req/s; 30-min in-process cache; monthly quota tracking
4. **Parallel fetch** — `asyncio.as_completed`, concurrency cap, 15s per-URL timeout; trafilatura text extraction
5. **Sentiment analysis** — 30B model per item in a bounded parallel queue; per-item failure recovery
6. **Report assembly** — pure Python: counts, quotes, aspects, source facts, timeline, claims, threads, force graph
7. **Synthesis** — 120B model writes themes and narrative from pre-computed analytics
8. **SSE streaming** — every stage event streamed to the browser in real time

---

## Project structure

```
AutoSentiment/
├── setup.sh                         # One-command setup
├── docker-compose.yml               # Containerised deployment
│
├── backend/
│   ├── .env.example                 # Template — copy to .env
│   ├── requirements.txt             # Python dependencies
│   ├── app/
│   │   ├── main.py                  # FastAPI app, lifespan, CORS
│   │   ├── agents/
│   │   │   ├── orchestrator.py      # Main pipeline + cancel + expand
│   │   │   ├── nemoclaw.py          # Query expansion, synthesis, suggestions
│   │   │   ├── nemoclaw_agent.py    # Autonomous NemoClaw research agent
│   │   │   ├── light_queue.py       # Bounded parallel sentiment queue
│   │   │   └── types.py             # Enums: SSEEventType, SentimentLabel, SourceType
│   │   ├── api/
│   │   │   ├── routes.py            # All HTTP endpoints + auth dependency
│   │   │   └── event_bus.py         # In-process SSE queue + cancel signalling
│   │   ├── core/config.py           # Pydantic settings (reads .env)
│   │   ├── db/session.py            # Async SQLAlchemy session factory + WAL mode
│   │   ├── ingest/fetch.py          # URL fetch, text extraction, source classification
│   │   ├── models.py                # SQLAlchemy models: Run, EvidenceChunk, etc.
│   │   ├── reports/builder.py       # Analytics: counts, quotes, aspects, claims, graph
│   │   ├── research_depth.py        # Depth presets (Quick/Standard/Deep/Exhaustive)
│   │   ├── search_planner.py        # Purpose-labeled query plans + quota tracking
│   │   └── tools/search.py          # Brave Search client with cache + rate limiter
│   ├── scripts/
│   │   ├── benchmark_pipeline.py    # Report builder hot-path benchmarks
│   │   └── benchmark_llamacpp.py    # Ollama vs llama.cpp comparison
│   └── tests/                       # 140 pytest tests
│
└── frontend/
    ├── .env.example                 # Template — copy to .env
    ├── package.json                 # npm scripts: dev, build, lint, test:e2e
    ├── playwright.config.ts         # E2E test config
    └── src/
        ├── components/
        │   ├── App.tsx              # Session management, tab routing, SSE reconnect
        │   ├── RunView.tsx          # Search form, depth/use-case selectors, live stage
        │   ├── ReportView.tsx       # Tabbed report layout
        │   ├── ForceGraph.tsx       # Physics-based idea graph
        │   ├── HistoryPanel.tsx     # Run history with filter + cancel
        │   ├── EvidenceModal.tsx    # Snippet inspector with keyword highlighting
        │   ├── ClaimsSection.tsx    # Fact-check + contradiction cards
        │   ├── SourceFacts.tsx      # Source-type accordion with URL links
        │   ├── CompareView.tsx      # Multi-topic side-by-side comparison
        │   ├── TabBar.tsx           # Draggable tab bar with running-count pill
        │   ├── HistoryChart.tsx     # Sentiment trend SVG chart
        │   ├── NemoClawPanel.tsx    # NemoClaw agent UI
        │   ├── ErrorBoundary.tsx    # React error boundary wrapper
        │   └── DevOverlay.tsx       # Dev stats panel (Ctrl+Shift+D)
        ├── hooks/useRunStream.ts    # SSE consumer hook
        ├── hooks/useKeyboardShortcuts.ts  # Keyboard shortcut handler
        └── lib/api.ts               # Typed API client + all TypeScript interfaces
```

---

## Troubleshooting

### Backend won't start

**`BRAVE_API_KEY is required`** — Add your key to `backend/.env`.

**`[Errno 2] No such file or directory: './data/app.db'`** — Run the database initialisation:
```bash
cd backend && source .venv/bin/activate
python3 -c "import asyncio; from app.db.session import create_tables; asyncio.run(create_tables())"
```

**`ModuleNotFoundError`** — The virtualenv is not activated or dependencies are missing:
```bash
cd backend && source .venv/bin/activate && pip install -r requirements.txt
```

### Runs fail immediately or error with no output

Check the diagnostics endpoint:
```bash
curl http://localhost:8000/api/diagnostics | python3 -m json.tool
```

This reports: DB status, Brave key presence, configured model names, and active run counts.

### Ollama connection errors

- Verify Ollama is running: `ollama list`
- Check `OLLAMA_BASE_URL` in `backend/.env` points to the correct host and port
- Ensure the configured models are pulled: `ollama pull nemotron-3-nano`

### Brave quota errors

The frontend shows remaining quota before each run. If you hit the monthly limit (2,000 queries):
- Wait for quota to reset on the 1st of the month
- Switch to a paid Brave plan
- Or test with a fresh API key

The pipeline gate (`if settings.brave_api_key:`) means the backend also logs `brave_key_missing` in the SSE stream if the key is absent.

### Search returns no results

- Increase the freshness window (e.g., from "Past week" to "Past month")
- Try a broader topic phrase
- Check quota remaining — Brave free tier returns HTTP 429 at the monthly limit

### Frontend shows "Backend offline"

- Confirm the backend is running on port 8000: `curl http://localhost:8000/api/health`
- Check `VITE_API_URL` in `frontend/.env` matches the actual backend address
- CORS: if running backend and frontend on different hosts, add the frontend origin to `CORS_ORIGINS` in `backend/.env`

### Docker: frontend can't reach backend

The Docker Compose setup wires `VITE_API_BASE_URL=http://backend:8000` (container name). This is for browser requests, so it must be reachable from the user's machine. If running on a remote host, set:
```yaml
VITE_API_BASE_URL: http://<server-ip>:8000
```
in `docker-compose.yml` under the `frontend` service.

### Dev overlay

Press **Ctrl+Shift+D** in the browser to open the dev overlay. It shows live SSE queue depth, run counts by status, and model assignments — useful for diagnosing stuck runs or model mismatches.
