# Frontend — what must be implemented

Canonical MVP list: [`../docs/IMPLEMENTATION.md`](../docs/IMPLEMENTATION.md).

## Suggested file layout (add as you build)

| Path | Purpose |
|------|---------|
| `src/lib/config.ts` | Read `import.meta.env.VITE_API_URL` with fallback `http://localhost:8000` |
| `src/lib/api.ts` | `createRun`, `getRun`, URL builder for SSE |
| `src/hooks/useRunStream.ts` | `EventSource` lifecycle, parse JSON lines, error/reconnect policy |
| `src/components/RunForm.tsx` | Submit query → `POST /api/runs` |
| `src/components/EventTimeline.tsx` | Append-only list of SSE events |
| `src/components/ReportView.tsx` | Render `sections[]`; citation chips → modal with evidence |
| `src/App.tsx` | Compose form + timeline + report for active run |

## Must implement

- [ ] **Env**: document `VITE_API_URL` in `.env.example`; never commit real secrets.
- [ ] **Create run**: `POST` JSON body `{ "query": "..." }`; store returned `run_id`.
- [ ] **SSE client**: `new EventSource(\`${api}/api/runs/${id}/events\`)` or fetch-based SSE if you need custom headers.
- [ ] **Parse events**: expect `data: {json}` lines; render `type` + `message` + optional `detail`.
- [ ] **Report UI**: map `citation_ids` to evidence fetched via `GET /api/runs/{id}` (or dedicated evidence endpoint if backend adds one).
- [ ] **UX**: loading / error / completed states; basic responsive layout.

## Done when

A demo user can submit one query, watch the stream, and read a report with working citation previews.
