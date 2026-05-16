# AutoSentiment — Project Spec

Autonomous brand/topic sentiment analysis from Reddit and news. The user types a keyword and picks a time window; the system searches, fetches, runs per-item sentiment with a fast 30B model, synthesizes an aggregate report with a 120B model, and streams every step to the UI in real time.

## Hardware & Inference

- **DGX Spark** running **Ollama** (`OLLAMA_MAX_LOADED_MODELS=2`)
- **nemotron-3-nano** (30B) — per-item sentiment, fast and parallel
- **nemotron-3-super** (120B) — query expansion + final synthesis
- Both models stay resident in memory simultaneously (150B total < 200B capacity, no swap latency)
- All LLM calls go to Ollama via httpx — no external LLM SDK required

## Sources

| Source | Access method |
|--------|--------------|
| Reddit | Brave finds thread URLs → fetch `url.json` (no auth, public posts) |
| News | Brave finds article URLs → httpx + trafilatura body extraction |

**Brave rate limit:** 1 req/sec enforced by a dedicated `asyncio.Semaphore(1)` + 1-second sleep in the search tool. Separate from the LLM queue. Monthly cap (2000) is not a concern for hackathon volume.

## User Input

```json
{ "topic": "Tesla Model 3", "freshness": "pm" }
```

| `freshness` value | Meaning | Brave param |
|-------------------|---------|-------------|
| `pd` | Past 24 hours | `freshness=pd` |
| `pw` | Past week | `freshness=pw` |
| `pm` | Past month | `freshness=pm` |
| `py` | Past year | `freshness=py` |
| omitted | Any time | (param omitted) |

Default: `pm`.

## Database Schema (SQLite via SQLAlchemy async)

### `runs`
| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `topic` | TEXT | User-supplied keyword |
| `freshness` | TEXT | Brave freshness param, nullable |
| `status` | TEXT | `pending` → `running` → `completed` \| `error` |
| `created_at` | DATETIME | |
| `report` | JSON | Null until synthesis completes |

### `evidence_chunks`
| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `run_id` | TEXT FK | → runs.id |
| `url` | TEXT | Source URL |
| `source_type` | TEXT | `reddit` or `news` |
| `snippet` | TEXT | Extracted text sent to 30B model |
| `label` | TEXT | `positive`, `neutral`, or `negative` |
| `summary` | TEXT | 3–5 word description from 30B |
| `retrieved_at` | DATETIME | |

### `run_events`
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `run_id` | TEXT FK | → runs.id |
| `seq` | INTEGER | Monotonically increasing per run |
| `type` | TEXT | See SSE event types below |
| `message` | TEXT | Human-readable label |
| `detail` | JSON | Event-specific payload |
| `created_at` | DATETIME | |

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Returns `{"status": "ok"}` |
| POST | `/api/runs` | Create run, start agent in background, return `run_id` |
| GET | `/api/runs/{id}` | Run metadata + report when complete |
| GET | `/api/runs/{id}/events` | SSE stream (`text/event-stream`) |
| GET | `/api/runs/{id}/evidence/{chunk_id}` | Single evidence chunk for citation drawer |

### POST /api/runs — request body
```json
{ "topic": "Tesla Model 3", "freshness": "pm" }
```

### POST /api/runs — response
```json
{ "run_id": "uuid" }
```

### SSE event shape
```json
{ "seq": 1, "type": "item_analyzed", "message": "Reddit comment analyzed", "detail": { ... } }
```

## SSE Event Types

| `type` | `detail` fields | When emitted |
|--------|----------------|-------------|
| `run_started` | `topic`, `freshness` | Immediately after run created |
| `search_queried` | `query` | Before each Brave query |
| `url_fetched` | `url`, `source_type`, `item_count` | After extracting items from a URL |
| `item_analyzed` | `evidence_id`, `label`, `summary`, `url`, `source_type` | After each 30B call |
| `synthesis_started` | — | Before 120B synthesis call |
| `run_completed` | `report` | After report stored in DB |
| `run_error` | `message` | On unrecoverable error |

## Agent Flow

```
POST /api/runs
  └─ asyncio.create_task(run_research(run_id, topic, freshness))

run_research:
  1. [120B] expand_queries(topic) → 5 search queries
       e.g. "Tesla Model 3", "Tesla Model 3 reddit", "Tesla Model 3 review",
            "Tesla Model 3 problems", "Tesla Model 3 owners"
  2. [Brave, 1/sec] search each query with freshness → collect up to MAX_URLS_PER_RUN unique URLs
  3. For each URL:
       - Reddit URL → fetch url.json → extract top-level comments (cap 20/thread)
       - News URL   → httpx GET → trafilatura extract → split into paragraphs
       - emit url_fetched
  4. For each item (cap MAX_ITEMS_PER_RUN total):
       - [30B] sentiment_call(snippet) → { label, summary }
       - store EvidenceChunk in DB
       - emit item_analyzed
  5. [120B] synthesize(all labels + summaries) → report JSON
  6. Store report on Run, set status=completed, emit run_completed
```

## SSE Internal Event Bus

The orchestrator runs as a background `asyncio` task and cannot write directly to an HTTP response. The SSE endpoint and the orchestrator communicate via a per-run `asyncio.Queue` stored in a module-level registry.

```
app/api/event_bus.py  ← shared module, imported by both routes.py and orchestrator.py
```

```python
# event_bus.py interface (implement this first — both tracks depend on it)
_queues: dict[str, asyncio.Queue] = {}

def register(run_id: str) -> asyncio.Queue   # called by SSE endpoint before starting agent
def get(run_id: str) -> asyncio.Queue | None # called by orchestrator to push events
def deregister(run_id: str) -> None          # called by SSE endpoint on client disconnect
```

**Protocol:**
- SSE endpoint calls `register(run_id)`, then streams by calling `await q.get()` in a loop
- Orchestrator calls `get(run_id)` and pushes serialised event dicts with `q.put_nowait(...)`
- Orchestrator puts `None` as a sentinel when the run completes or errors — SSE endpoint closes on sentinel

## LLM Prompt Contracts

All calls use Ollama's `/api/generate` endpoint with `"format": "json"` to enforce structured output. Use `"stream": false`.

### 30B — per-item sentiment (`nemotron-3-nano`)

```
POST {OLLAMA_BASE_URL}/api/generate
{
  "model": "<lightweight_model>",
  "format": "json",
  "stream": false,
  "system": "You are a sentiment classifier. Respond with JSON only. No explanation.",
  "prompt": "Classify the sentiment of the following text.\nReturn exactly: {\"label\": \"positive\" | \"neutral\" | \"negative\", \"summary\": \"<3-5 words describing the author's opinion>\"}\n\nText:\n<snippet>"
}
```

Parse `response.response` as JSON → `SentimentResult`. If parsing fails, default to `neutral` with summary `"parse error"`.

### 120B — query expansion (`nemotron-3-super`)

```
POST {OLLAMA_BASE_URL}/api/generate
{
  "model": "<nemoclaw_model>",
  "format": "json",
  "stream": false,
  "system": "You are a search query generator. Respond with JSON only.",
  "prompt": "Generate 5 search queries to find public opinions, reviews, and discussions about: <topic>\nInclude variants targeting Reddit, reviews, and news.\nReturn exactly: {\"queries\": [\"...\", \"...\", \"...\", \"...\", \"...\"]}"
}
```

Parse `response.response` → `list[str]`. Fall back to `[topic, topic + " reddit", topic + " review"]` on parse failure.

### 120B — synthesis (`nemotron-3-super`)

```
POST {OLLAMA_BASE_URL}/api/generate
{
  "model": "<nemoclaw_model>",
  "format": "json",
  "stream": false,
  "system": "You are a research analyst summarising public sentiment. Respond with JSON only.",
  "prompt": "Topic: <topic>\nAnalysed <total> items: <pos_pct>% positive, <neu_pct>% neutral, <neg_pct>% negative.\n\nSample opinions:\n<bulleted list of 'label: summary (source_type)'>\n\nReturn exactly: {\"themes\": [\"theme1\", \"theme2\", \"theme3\"], \"narrative\": \"2-3 sentence plain-English summary of overall sentiment and key drivers\"}"
}
```

The model writes `themes` and `narrative` only — it never sees raw counts to recalculate.

## Reddit JSON Fields

Append `.json` to any Reddit thread URL. The response is a 2-element array:
- `response[1]["data"]["children"]` — the comments list
- Each child: `child["kind"]` must equal `"t1"` (skip `"more"` entries)
- Text lives at: `child["data"]["body"]`
- Sort signal (optional filter): `child["data"]["score"]`

## Report Structure

```json
{
  "overall": {
    "positive": 0.45,
    "neutral": 0.30,
    "negative": 0.25,
    "total": 87
  },
  "by_source": {
    "reddit": { "positive": 0.50, "neutral": 0.25, "negative": 0.25, "count": 67 },
    "news":   { "positive": 0.35, "neutral": 0.40, "negative": 0.25, "count": 20 }
  },
  "top_positive": [
    { "summary": "loves the range", "evidence_id": "uuid", "url": "https://..." }
  ],
  "top_negative": [
    { "summary": "frequent software bugs", "evidence_id": "uuid", "url": "https://..." }
  ],
  "themes": ["battery performance", "software updates", "pricing"],
  "narrative": "Overall sentiment toward Tesla Model 3 is cautiously positive..."
}
```

**Percentages are computed in Python from stored labels — the 120B model never does arithmetic.**
The 120B synthesis prompt receives the pre-computed counts and the top quotes; it writes the themes list and narrative only.

## Frontend

| Component | Role |
|-----------|------|
| `RunForm` | Topic text input + freshness dropdown (5 options) + submit button |
| `EventTimeline` | Append-only SSE event list; `item_analyzed` events render as colored sentiment chips (green/grey/red) |
| `ReportView` | Percentage breakdown, source split, top positive/negative quotes, themes list, narrative paragraph |
| Evidence modal | Opens on citation click; shows stored snippet + "View source" link to original URL |

State lives in `App.tsx`: active `run_id`, array of received SSE events, report JSON.
`useRunStream` hook owns the `EventSource` lifecycle.

## Configuration (`.env`)

```
NEMCLAW_MODEL=nemotron-3-super
LIGHTWEIGHT_MODEL=nemotron-3-nano
LIGHT_QUEUE_MAX_PARALLEL=4
OLLAMA_BASE_URL=http://localhost:11434
BRAVE_API_KEY=
MAX_URLS_PER_RUN=30
MAX_ITEMS_PER_RUN=100
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

## Caps & Budgets

| Parameter | Default | Env var |
|-----------|---------|---------|
| Brave queries per run | 5 | (hardcoded from expansion) |
| Max unique URLs fetched | 30 | `MAX_URLS_PER_RUN` |
| Max items sent to 30B | 100 | `MAX_ITEMS_PER_RUN` |
| Comments per Reddit thread | 20 | (hardcoded) |
| Brave rate | 1/sec | (hardcoded semaphore) |
| LLM concurrency (30B) | 4 | `LIGHT_QUEUE_MAX_PARALLEL` |

## Team Tracks (4 people, parallel)

All tracks can start immediately. The only hard dependency is that **Track A must finish the event bus before Track C wires the orchestrator**, and **Track C wires last** (after A, B, and D have working pieces).

---

### Track A — API + Orchestrator
*Files: `app/api/event_bus.py` (new), `app/api/routes.py`, `app/agents/orchestrator.py`, `app/reports/builder.py`*

1. Create `app/api/event_bus.py` — `register`, `get`, `deregister` (see §SSE Internal Event Bus). **Commit this first so other tracks can import it.**
2. Implement `POST /api/runs` — create `Run` in DB, call `asyncio.create_task(run_research(...))`, return `run_id`
3. Implement `GET /api/runs/{id}` — return run row + report
4. Implement `GET /api/runs/{id}/events` SSE — `register` queue, stream with `await q.get()`, close on `None` sentinel
5. Implement `GET /api/runs/{id}/evidence/{chunk_id}` — return evidence chunk row
6. Implement `reports/builder.py` — `compute_counts`, `pick_top_quotes` (pure Python, no LLM)
7. **Last:** wire `run_research` in `orchestrator.py` using B's fetch functions and C's LLM functions

---

### Track B — Data Pipeline
*Files: `app/tools/search.py`, `app/ingest/fetch.py`, `app/retrieve/search.py`*

1. Implement `brave_search` — httpx POST to Brave API, semaphore + `await asyncio.sleep(1)` rate limit, return list of URLs
2. Implement `_fetch_reddit` — httpx GET `url.json`, parse `response[1]["data"]["children"]`, filter `kind=="t1"`, return up to 20 `FetchedItem`s
3. Implement `_fetch_news` — httpx GET, `trafilatura.extract`, split on `\n\n` into paragraph chunks, return `FetchedItem` list
4. Implement `fetch_items` dispatcher — `is_reddit_url` → reddit path, else news path
5. `retrieve/search.py` is already implemented (simple SQLAlchemy selects) — verify it works

Test each function in isolation with a real URL before handing off to Track C.

---

### Track C — LLM Calls
*Files: `app/agents/light_queue.py`, `app/agents/nemoclaw.py`*

1. Write a shared `ollama_generate(prompt, system, model, base_url) -> dict` helper (put it in `app/agents/ollama.py`, new file)
2. Implement `SentimentQueue._call_model` — call 30B via helper, parse JSON, return `SentimentResult`; handle parse errors gracefully
3. Implement `expand_queries` — call 120B via helper, parse `queries` list, return it; fall back to 3 default variants on failure
4. Implement `synthesize_report` — call 120B via helper, parse `themes` + `narrative`, return dict

Test each call with a hardcoded string before the orchestrator uses them. Verify Ollama is serving both models (`ollama list`).

---

### Track D — Frontend
*Files: `frontend/src/hooks/useRunStream.ts` (new), `frontend/src/App.tsx`, all components, `src/index.css`*

1. Create `useRunStream.ts` hook — takes `runId | null`, manages `EventSource` lifecycle, returns `{ events, status }`
2. Wire `App.tsx` to use `useRunStream` instead of the inline `startStream` function
3. Polish `EventTimeline` — layout, timestamp on each event, chip colours, auto-scroll to bottom
4. Polish `ReportView` — percentage bars (CSS width from ratio), source breakdown table, quote list styling
5. Polish `RunForm` — loading spinner, disabled state, error display
6. Implement evidence modal — backdrop, close on Escape, snippet text, source link
7. Responsive layout + overall CSS pass

Can develop against a local mock SSE endpoint (a simple script that streams fake events) until Track A's SSE route is live.

---

### Integration Checkpoints

| When | What |
|------|------|
| Track A finishes event_bus.py | Commit + notify — B and C can import it in orchestrator wiring |
| Track B finishes fetch_items | Write a quick test: `asyncio.run(fetch_items("https://reddit.com/r/teslamotors/..."))` and print results |
| Track C finishes all 3 LLM calls | Write a quick test: call each function with a hardcoded input, verify output shape |
| Track D has mock SSE working | Share the mock endpoint so frontend looks live during the demo rehearsal |
| All of A/B/C done | Track A wires `run_research` — first real end-to-end run |
