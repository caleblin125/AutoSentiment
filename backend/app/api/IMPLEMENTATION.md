# `app.api` — HTTP & SSE surface

## Must implement

- [ ] **`GET /api/health`** — DB connectivity check optional but useful (return 503 if DB down).
- [ ] **`POST /api/runs`** — Body: `{ "query": "..." }` (or richer payload later). Creates `Run`, returns `{ "run_id": "..." }`.
- [ ] **`GET /api/runs/{run_id}`** — Returns run metadata + final report when complete.
- [ ] **`GET /api/runs/{run_id}/events`** — **SSE** stream (`text/event-stream`):
  - Emit `data: {json}\n\n` for each agent/tool event.
  - On reconnect, support `Last-Event-ID` **or** document that clients only need live hackathon demo (optional).
- [ ] **Start agent** from `POST` handler: `asyncio.create_task(run_agent(run_id))` or background task — must not block the response.
- [ ] **Error model** — consistent JSON error shape for 4xx/5xx.

## SSE event shape (suggested)

```json
{
  "seq": 1,
  "type": "step_started",
  "message": "Searching …",
  "detail": {}
}
```

## Done when

Frontend can create a run, subscribe to SSE, and see a complete timeline ending in a grounded report payload.
