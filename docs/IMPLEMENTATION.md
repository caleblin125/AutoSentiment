# What Must Be Implemented

This document is the **source of truth** for scope. Module-level details live in `backend/app/**/IMPLEMENTATION.md` and `frontend/IMPLEMENTATION.md`.

## Product goal

An autonomous research assistant that gathers web evidence, stores **citation-backed** extracts, and streams run progress to the UI. Hackathon stack: **FastAPI + SQLite + SSE**, **Vite + React + TypeScript**, **httpx** (no Playwright in v0 unless time allows).

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
| Agent | Plan/act/observe loop with budgets (max steps, timeout); emit events |
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

- Celery/Redis, separate worker processes, Playwright
- pgvector / dedicated vector DB
- Full auth multi-tenancy (API key or open dev is fine)
- Marketplace-specific scrapers beyond generic listing-like pages

## Suggested order of work

1. Health check + CORS + SQLite session  
2. SSE endpoint that emits mock events, then real agent events  
3. Ingest path: URL → cleaned text → chunks → DB  
4. Retrieval + grounded summary  
5. Wire React run page to live SSE + report JSON  

Cross-check **per-package** `IMPLEMENTATION.md` files before marking an area done.
