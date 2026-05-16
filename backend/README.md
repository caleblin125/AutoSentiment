# Backend (FastAPI)

## What to build

See **[`../docs/IMPLEMENTATION.md`](../docs/IMPLEMENTATION.md)** for MVP acceptance criteria and **[`../docs/HACKATHON_ENV.md`](../docs/HACKATHON_ENV.md)** for the NemoClaw / Hack-a-Claw environment.

Per-module task lists:

- [`app/agents/IMPLEMENTATION.md`](app/agents/IMPLEMENTATION.md) *(Nemoclaw + lightweight queue)*
- [`app/api/IMPLEMENTATION.md`](app/api/IMPLEMENTATION.md)
- [`app/ingest/IMPLEMENTATION.md`](app/ingest/IMPLEMENTATION.md)
- [`app/retrieve/IMPLEMENTATION.md`](app/retrieve/IMPLEMENTATION.md)
- [`app/memory/IMPLEMENTATION.md`](app/memory/IMPLEMENTATION.md)
- [`app/reports/IMPLEMENTATION.md`](app/reports/IMPLEMENTATION.md)
- [`app/tools/IMPLEMENTATION.md`](app/tools/IMPLEMENTATION.md)
- [`app/models/IMPLEMENTATION.md`](app/models/IMPLEMENTATION.md)
- [`app/core/IMPLEMENTATION.md`](app/core/IMPLEMENTATION.md)
- [`app/db/IMPLEMENTATION.md`](app/db/IMPLEMENTATION.md)

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI: `http://localhost:8000/docs`
