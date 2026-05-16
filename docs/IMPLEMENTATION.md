# What Must Be Implemented

This document is the **source of truth** for scope. Module-level details live in `backend/app/**/IMPLEMENTATION.md` and `frontend/IMPLEMENTATION.md`.

## Product goal

An autonomous research assistant that gathers web evidence, stores **citation-backed** extracts, and streams progress to the UI. Hackathon stack: **FastAPI + SQLite + SSE**, **Vite + React + TypeScript**, **httpx** (no Playwright in v0 unless time allows).

## Two-tier model process

| Tier | Model | Role |
|------|--------|------|
| **Nemoclaw** | Orchestrator (`NEMCLAW_MODEL`) | Structures **what** gets searched and **how** processing proceeds: sub-questions, search program, stage ordering, hints for downstream code. |
| **Lightweight queue** | Smaller/cheaper models (`LIGHTWEIGHT_MODEL`, concurrency `LIGHT_QUEUE_MAX_PARALLEL`) | **Queued, bounded-parallel** LLM calls for *search-facing* work: query expansion, snippet scoring, quick relevance filters — *not* heavy synthesis. |

**Flow:** user question → **Nemoclaw** emits a `ResearchPlan` → discovery/ingest uses the plan + tool APIs → lightweight tier assists search/retrieval **without** replacing Nemoclaw’s strategic layout → final grounded report may call **Nemoclaw** again for quality-controlled synthesis (see `reports/IMPLEMENTATION.md`).

Implementation anchors: `backend/app/agents/nemoclaw.py`, `backend/app/agents/light_queue.py`, `backend/app/agents/orchestrator.py`, `backend/app/agents/types.py`.

**Hackathon environment:** [shortesthack.com — Nemoclaw tab](https://www.shortesthack.com/?tab=nemoclaw) + **[`HACKATHON_ENV.md`](HACKATHON_ENV.md)** (NemoClaw / OpenShell, model IDs, tracks).

## End-to-end acceptance criteria (MVP)

1. **Create run** — User submits a research question or topic; backend creates a `run` record.
2. **Stream progress** — UI receives **SSE** events (step labels, tool start/end, errors) for that run.
3. **Fetch & extract** — Agent uses search + HTTP fetch + HTML text extraction; chunks and rows land in SQLite with stable IDs.
4. **Grounded report** — Final artifact is structured JSON/Markdown sections where factual sentences reference `evidence_id`(s).
5. **Inspect sources** — UI can open stored excerpts for each citation (snippet, URL, retrieved_at).

## Backend checklist

| Area | Must implement |
|------|----------------|
| API | `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/events` (SSE) |
| Nemoclaw | `structure_research_plan` — real LLM call, validated `ResearchPlan` |
| Light queue | `LightweightModelQueue` — provider calls for `LightJobKind` jobs, respect `LIGHT_QUEUE_MAX_PARALLEL` |
| Agent | `run_research` wires plan → light jobs → tools → ingest → retrieve → report; budgets + SSE events |
| Tools | Search provider adapter; `httpx` fetch; HTML → text/chunks |
| Storage | SQLite models: runs, events, evidence chunks, raw_artifacts optional |
| Retrieve | SQLite **FTS5** or fallback text match over chunks for grounding |
| Reports | Prompt/templates that only cite stored evidence IDs |
| CORS | Allow frontend origin in dev |

## Frontend checklist

| Area | Must implement |
|------|----------------|
| Run form | Submit question; show `run_id` |
| Stream | `EventSource` against SSE URL; append timeline |
| Report | Render sections; citation chips linking to evidence drawer/modal |
| State | TanStack Query optional; minimal React state is OK for hackathon |

## Out of scope for hackathon v0

- **Distributed** job queues (Celery/Redis workers across machines) — use the in-process `LightweightModelQueue` first.
- pgvector / dedicated vector DB
- Full auth multi-tenancy (API key or open dev is fine)
- Marketplace-specific scrapers beyond generic listing-like pages

## Suggested order of work

1. Health check + CORS + SQLite session  
2. Nemoclaw + light queue **stubs** emitting events (prove tier split in SSE)  
3. SSE endpoint that emits mock events, then real agent events  
4. Ingest path: URL → cleaned text → chunks → DB  
5. Retrieval + grounded summary  
6. Wire React run page to live SSE + report JSON  

Cross-check **per-package** `IMPLEMENTATION.md` files before marking an area done.
