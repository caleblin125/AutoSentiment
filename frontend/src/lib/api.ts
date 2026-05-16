import { API_BASE_URL } from './config'

// ── Request / response types ────────────────────────────────────────────────

export interface RunRequest {
  topic: string
  freshness?: 'pd' | 'pw' | 'pm' | 'py'
  research_depth?: ResearchDepth
  use_case?: UseCase
}

export type ResearchDepth = 'quick' | 'standard' | 'deep' | 'exhaustive'
export type UseCase = 'generic' | 'entertainment_product' | 'public_current_event' | 'brand_product' | 'policy_civic'

export interface DepthBudget {
  query_count: number
  url_count: number
  item_count: number
  source_diversity_target: number
  synthesis_sample_size: number
}

export interface RunCreated {
  run_id: string
  cached: boolean
}

export interface PlannedQuery {
  query: string
  purpose: string
  source_target: string
}

export interface SearchPlan {
  topic: string
  freshness: string | null
  research_depth: ResearchDepth
  use_case: UseCase
  query_budget: number
  url_budget: number
  item_budget: number
  source_diversity_target: number
  estimated_brave_queries: number
  monthly_quota_used: number
  monthly_quota_remaining: number
  quota_warning: string | null
  queries: PlannedQuery[]
}

export interface Run {
  id: string
  topic: string
  freshness: string | null
  research_depth: ResearchDepth
  status: 'pending' | 'running' | 'completed' | 'error'
  created_at: string
  report: Report | null
}

export interface ImpactItem { direction: 'positive' | 'negative'; description: string }
export interface ArgumentItem { claim: string; side: 'for' | 'against' }

export interface Report {
  metadata?: {
    topic?: string
    freshness?: string | null
    research_depth?: ResearchDepth
    use_case?: UseCase
    depth_budget?: Partial<DepthBudget>
    search_plan?: SearchPlan
  }
  overall: { positive: number; neutral: number; negative: number; total: number }
  by_source: Record<string, SourceStats | undefined>
  top_positive: Quote[]
  top_negative: Quote[]
  themes: string[]
  narrative: string
  impacts?: ImpactItem[]
  reasons?: string[]
  arguments?: ArgumentItem[]
  timings?: Record<string, number>
  aspects?: AspectInsight[]
  source_facts?: SourceFact[]
  timeline?: ReportTimeline
  fact_check?: FactCheck
  use_case_insights?: UseCaseInsights
  chart_data?: ChartData
  graph?: IdeaGraph
}

export interface UseCaseInsights {
  use_case: UseCase
  sections: Record<string, string | string[]>
}

export interface ChartData {
  source_mix: Array<{ source_type: string; count: number }>
  sentiment_over_time: Array<{ date: string; positive: number; neutral: number; negative: number; total: number }>
  aspect_matrix: Array<{ aspect: string; positive: number; neutral: number; negative: number; count: number }>
  claim_corroboration: Array<{ claim: string; supporting_sources: number; needs_verification: boolean }>
}

export interface FactClaim {
  claim: string
  claim_type: string
  confidence: number
  supporting_domains: string[]
  opposing_domains: string[]
  evidence_ids: string[]
  source_types: string[]
  needs_verification: boolean
}

export interface FactCheck {
  claims: FactClaim[]
  needs_verification: FactClaim[]
  summary: string
}

export interface TimelineEvent {
  date: string
  label: string
  description: string
  evidence_ids: string[]
  source_count: number
  certainty: 'explicit' | 'retrieved_at'
  source_text: string
}

export interface ReportTimeline {
  start_date: string | null
  end_date: string | null
  important_dates: TimelineEvent[]
  event_summary: string
  supporting_evidence_ids: string[]
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

export interface AspectInsight {
  name: string
  sentiment: 'positive' | 'neutral' | 'negative'
  count: number
  positive: number
  neutral: number
  negative: number
  evidence_ids?: string[]
}

export interface SourceFact {
  domain: string
  source_type: string
  count: number
  labels: Record<string, number>
}

export interface IdeaGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface GraphNode {
  id: string
  label: string
  kind: 'topic' | 'sentiment' | 'theme' | 'aspect' | 'source'
  weight: number
  url?: string
  urls?: string[]
  evidence_ids?: string[]
}

export interface GraphEdge {
  source: string
  target: string
  kind: string
  weight: number
}

// ── Run history ─────────────────────────────────────────────────────────────

export interface RunSummary {
  id: string
  topic: string
  status: 'pending' | 'running' | 'completed' | 'cancelled' | 'error'
  created_at: string
  overall: { positive: number; neutral: number; negative: number; total: number } | null
}

// ── SSE event types ─────────────────────────────────────────────────────────

export type SSEEventType =
  | 'run_started'
  | 'search_queried'
  | 'fetch_started'
  | 'url_fetched'
  | 'item_analyzed'
  | 'synthesis_started'
  | 'run_completed'
  | 'run_cancelled'
  | 'run_error'

export interface SSEEvent {
  seq: number
  type: SSEEventType
  message: string
  /** All detail fields, plus server-injected elapsed_ms (ms since run start). */
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

export async function previewSearchPlan(req: RunRequest): Promise<SearchPlan> {
  const params = new URLSearchParams({
    topic: req.topic,
    research_depth: req.research_depth ?? 'standard',
    use_case: req.use_case ?? 'generic',
  })
  if (req.freshness) params.set('freshness', req.freshness)
  const res = await fetch(`${API_BASE_URL}/api/search-plan?${params}`)
  if (!res.ok) throw new Error(`GET /api/search-plan failed: ${res.status}`)
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

export async function clearHistory(): Promise<void> {
  await fetch(`${API_BASE_URL}/api/runs`, { method: 'DELETE' })
}

export async function listRuns(topic?: string, limit = 20): Promise<RunSummary[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (topic) params.set('topic', topic)
  const res = await fetch(`${API_BASE_URL}/api/runs?${params}`)
  if (!res.ok) throw new Error(`GET /api/runs failed: ${res.status}`)
  return res.json()
}

export async function cancelRun(runId: string): Promise<void> {
  await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' })
}

export async function expandRun(runId: string, req?: { research_depth?: ResearchDepth; freshness?: RunRequest['freshness'] }): Promise<RunCreated> {
  const res = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/expand`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: req ? JSON.stringify(req) : undefined,
  })
  if (!res.ok) throw new Error(`POST /expand failed: ${res.status}`)
  return res.json()
}

export async function startNemoClaw(runId: string): Promise<RunCreated> {
  const res = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/nemoclaw`, { method: 'POST' })
  if (!res.ok) throw new Error(`POST /nemoclaw failed: ${res.status}`)
  return res.json()
}

export async function suggestAngles(q: string): Promise<string[]> {
  const res = await fetch(`${API_BASE_URL}/api/suggest?q=${encodeURIComponent(q)}`)
  if (!res.ok) return []
  const data = await res.json()
  return data.suggestions ?? []
}

export async function getDevStats(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE_URL}/api/dev/stats`)
  if (!res.ok) return {}
  return res.json()
}
