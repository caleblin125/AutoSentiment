import { getApiBaseUrl } from './config'

/** POST /api/runs — implement in `frontend/IMPLEMENTATION.md`. */
export async function createRun(_query: string): Promise<{ run_id: string }> {
  void _query
  throw new Error('Not implemented — wire POST /api/runs (see frontend/IMPLEMENTATION.md)')
}

/** GET /api/runs/{id} — implement per IMPLEMENTATION.md. */
export async function getRun(_runId: string): Promise<unknown> {
  void _runId
  throw new Error('Not implemented — see frontend/IMPLEMENTATION.md')
}

/** URL for SSE: GET /api/runs/{id}/events */
export function getRunEventsUrl(runId: string): string {
  return `${getApiBaseUrl()}/api/runs/${encodeURIComponent(runId)}/events`
}
