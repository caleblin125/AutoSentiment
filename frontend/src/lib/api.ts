import { API_BASE_URL } from './config'

// ── Request / response types ────────────────────────────────────────────────

export interface RunRequest {
  topic: string
  freshness?: 'pd' | 'pw' | 'pm' | 'py'
}

export interface RunCreated {
  run_id: string
}

export interface Run {
  id: string
  topic: string
  freshness: string | null
  status: 'pending' | 'running' | 'completed' | 'error'
  created_at: string
  report: Report | null
}

export interface Report {
  overall: { positive: number; neutral: number; negative: number; total: number }
  by_source: {
    reddit?: SourceStats
    news?: SourceStats
  }
  top_positive: Quote[]
  top_negative: Quote[]
  themes: string[]
  narrative: string
}

export interface SourceStats {
  positive: number
  neutral: number
  negative: number
  count: number
}

export interface Quote {
  summary: string
  evidence_id: string
  url: string
}

export interface EvidenceChunk {
  id: string
  run_id: string
  url: string
  source_type: 'reddit' | 'news'
  snippet: string
  label: 'positive' | 'neutral' | 'negative'
  summary: string
  retrieved_at: string
}

// ── SSE event types ─────────────────────────────────────────────────────────

export type SSEEventType =
  | 'run_started'
  | 'search_queried'
  | 'url_fetched'
  | 'item_analyzed'
  | 'synthesis_started'
  | 'run_completed'
  | 'run_error'

export interface SSEEvent {
  seq: number
  type: SSEEventType
  message: string
  detail: Record<string, unknown>
}

// ── API functions ────────────────────────────────────────────────────────────

export async function createRun(req: RunRequest): Promise<RunCreated> {
  const res = await fetch(`${API_BASE_URL}/api/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`POST /api/runs failed: ${res.status}`)
  return res.json()
}

export async function getRun(runId: string): Promise<Run> {
  const res = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}`)
  if (!res.ok) throw new Error(`GET /api/runs/${runId} failed: ${res.status}`)
  return res.json()
}

export async function getEvidence(runId: string, chunkId: string): Promise<EvidenceChunk> {
  const res = await fetch(
    `${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/evidence/${encodeURIComponent(chunkId)}`
  )
  if (!res.ok) throw new Error(`GET evidence failed: ${res.status}`)
  return res.json()
}

export function getEventsUrl(runId: string): string {
  return `${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/events`
}
