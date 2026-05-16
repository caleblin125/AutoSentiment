# AutoSentiment

Autonomous, **citation-backed** web research: a Python API runs multi-step investigation loops (search, fetch, chunk, retrieve, summarize) and streams progress to a React UI over **SSE**.

**Nemoclaw** (orchestrator model) **organizes and structures** what is searched and how work is ordered. **Smaller models** run behind a **queued, concurrency-capped** path for faster, lighter, cheaper **search-facing** LLM tasks (query expansion, snippet scoring, quick filters). See [`docs/IMPLEMENTATION.md`](docs/IMPLEMENTATION.md) for the two-tier flow.

This repo is scaffolded for a **short hackathon** — minimal moving parts: **FastAPI + SQLite**, in-process lightweight queue (no distributed worker cluster required for v0), **httpx** + HTML extraction (no Playwright in v0 unless you finish early).

## Hackathon environment (NemoClaw)

Official event context and how **`NEMCLAW_MODEL` / `LIGHTWEIGHT_MODEL`** map to the **NVIDIA NemoClaw** stack (OpenShell, inference routing) are summarized in **[`docs/HACKATHON_ENV.md`](docs/HACKATHON_ENV.md)**. The live Nemoclaw tab is **[shortesthack.com/?tab=nemoclaw](https://www.shortesthack.com/?tab=nemoclaw)** — use the in-browser instructions there with NemoClaw docs for authoritative setup.

## Repository layout

| Path | Role |
|------|------|
| [`backend/`](backend/) | FastAPI app, Nemoclaw planning, lightweight queue, storage, SSE |
| [`frontend/`](frontend/) | Vite + React + TypeScript UI |
| [`docs/IMPLEMENTATION.md`](docs/IMPLEMENTATION.md) | **What must be implemented** (acceptance criteria & checklist) |
| [`docs/HACKATHON_ENV.md`](docs/HACKATHON_ENV.md) | **NemoClaw / Hack-a-Claw** environment mapping |

Each backend submodule and the frontend include an **`IMPLEMENTATION.md`** with concrete tasks.

## Prerequisites

- Python 3.11+
- Node.js 20+ (or 18+ with a current npm)

## Quick start (after dependencies are installed)

**Backend** (from repo root):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**:

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` in `frontend/.env` if the API is not the default `http://localhost:8000` (see `frontend/IMPLEMENTATION.md`).

## Configuration

- Copy `backend/.env.example` to `backend/.env` and fill secrets (e.g. search/API keys). The app should fail fast with clear errors if a required key is missing.
- **Orchestrator (NemoClaw / planning route):** `NEMCLAW_MODEL` — must match the **model id or alias** from your hackathon NemoClaw inference setup. **Light tier:** `LIGHTWEIGHT_MODEL`, `LIGHT_QUEUE_MAX_PARALLEL` for cheaper search-facing calls. See [`docs/HACKATHON_ENV.md`](docs/HACKATHON_ENV.md).

## Vision (beyond the hackathon)

Persistent monitoring, marketplace-focused adapters, richer retrieval (embeddings), browser automation where allowed, and stronger source-quality scoring — see [`docs/IMPLEMENTATION.md`](docs/IMPLEMENTATION.md) for MVP boundaries.

## License

Specify in a `LICENSE` file when you add one.
