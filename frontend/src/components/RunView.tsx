/**
 * Self-contained run view for one search tab.
 * Manages its own runId, stream, and report state so multiple tabs
 * can run simultaneously without interfering with each other.
 */
import { useMemo, useState } from 'react'
import { createRun, type RunRequest } from '../lib/api'
import { useRunStream } from '../hooks/useRunStream'
import { EventTimeline } from './EventTimeline'
import { ReportView } from './ReportView'
import type { Report } from '../lib/api'

const FRESHNESS_OPTIONS = [
  { value: 'pm', label: 'Past month' },
  { value: 'pw', label: 'Past week' },
  { value: 'pd', label: 'Past 24 h' },
  { value: 'py', label: 'Past year' },
  { value: '', label: 'Any time' },
] as const

interface Props {
  onStatusChange: (status: string, label: string) => void
}

export function RunView({ onStatusChange }: Props) {
  const [topic, setTopic] = useState('')
  const [freshness, setFreshness] = useState<string>('pm')
  const [runId, setRunId] = useState<string | null>(null)
  const [activeTopic, setActiveTopic] = useState<string | null>(null)
  const [cached, setCached] = useState(false)
  const [loading, setLoading] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const { events, status } = useRunStream(runId)

  const report = useMemo<Report | null>(() => {
    const completed = events.findLast(e => e.type === 'run_completed')
    return (completed?.detail as { report?: Report } | undefined)?.report ?? null
  }, [events])

  // Propagate status+topic to parent (for tab label/dot).
  useMemo(() => {
    const label = activeTopic ?? 'New Search'
    onStatusChange(cached && status !== 'running' ? 'cached' : status, label)
  }, [status, activeTopic, cached, onStatusChange])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!topic.trim()) return
    setLoading(true)
    setFormError(null)
    try {
      const req: RunRequest = {
        topic: topic.trim(),
        ...(freshness ? { freshness: freshness as RunRequest['freshness'] } : {}),
      }
      const { run_id, cached: isCached } = await createRun(req)
      setRunId(run_id)
      setActiveTopic(req.topic)
      setCached(isCached)
      setTopic('')
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to start run')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="run-view">
      {/* ── Search bar ── */}
      <div className="panel search-panel">
        <form className="search-form" onSubmit={handleSubmit}>
          <input
            className="search-input"
            type="text"
            placeholder="Topic, brand, or question…"
            value={topic}
            onChange={e => setTopic(e.target.value)}
            disabled={loading}
            required
          />
          <select
            className="freshness-select"
            value={freshness}
            onChange={e => setFreshness(e.target.value)}
            disabled={loading}
          >
            {FRESHNESS_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button type="submit" disabled={loading || !topic.trim()}>
            {loading && <span className="spinner" aria-hidden="true" />}
            <span>{loading ? 'Starting…' : 'Analyze'}</span>
          </button>
        </form>
        {formError && <p className="error-msg">{formError}</p>}
      </div>

      {/* ── Run status strip ── */}
      {runId && (
        <div className={`run-status run-status--${status}`} aria-live="polite">
          <div>
            <strong>{statusLabel(status, events.length)}</strong>
            {activeTopic && <p className="run-topic">{activeTopic}</p>}
            <p className="muted">
              Run: <code>{runId.slice(0, 8)}…</code>
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {cached && (
              <span className="cached-badge">⚡ cached</span>
            )}
            {(status === 'running' || status === 'idle') && (
              <span className="status-spinner" />
            )}
          </div>
        </div>
      )}

      {/* ── Skeleton while waiting for first event ── */}
      {runId && events.length === 0 && status !== 'error' && (
        <div className="panel">
          <div className="skeleton skeleton-line skeleton-line--short" style={{ marginBottom: 12 }} />
          <div className="skeleton skeleton-line skeleton-line--full" />
          <div className="skeleton skeleton-line skeleton-line--medium" />
          <div className="skeleton skeleton-line skeleton-line--full" />
        </div>
      )}

      {runId && events.length > 0 && <EventTimeline events={events} status={status} />}
      {report && runId && activeTopic && (
        <ReportView runId={runId} topic={activeTopic} report={report} />
      )}
    </div>
  )
}

function statusLabel(status: string, eventCount: number): string {
  if (status === 'completed') return 'Analysis complete'
  if (status === 'error') return 'Run stopped with an error'
  if (eventCount === 0) return 'Initialising…'
  return 'Analysis in progress'
}
