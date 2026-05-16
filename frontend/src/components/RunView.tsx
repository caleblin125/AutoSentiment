/**
 * Self-contained run view for one search tab.
 *
 * Features:
 *  - Search form (topic + freshness)
 *  - History panel (past runs, click to replay)
 *  - Cancel button (shown while running)
 *  - Expand search button (shown when completed)
 *  - Live event timeline + report
 */
import { useEffect, useMemo, useState } from 'react'
import { cancelRun, createRun, expandRun, type RunRequest } from '../lib/api'
import { useRunStream } from '../hooks/useRunStream'
import { EventTimeline } from './EventTimeline'
import { ReportView } from './ReportView'
import { HistoryPanel } from './HistoryPanel'
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
  const [cancelling, setCancelling] = useState(false)
  const [expanding, setExpanding] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  // Bumped whenever a run completes so HistoryPanel knows to refresh.
  const [historyKey, setHistoryKey] = useState(0)

  const { events, status } = useRunStream(runId)

  const report = useMemo<Report | null>(() => {
    const completed = events.findLast(e => e.type === 'run_completed')
    return (completed?.detail as { report?: Report } | undefined)?.report ?? null
  }, [events])

  useEffect(() => {
    const label = activeTopic ?? 'New Search'
    const tabStatus = cached && status !== 'running' ? 'cached' : status
    onStatusChange(tabStatus, label)
    if (status === 'completed') {
      setHistoryKey(k => k + 1)
    }
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

  async function handleCancel() {
    if (!runId) return
    setCancelling(true)
    try { await cancelRun(runId) }
    catch { /* best-effort */ }
    finally { setCancelling(false) }
  }

  async function handleExpand() {
    if (!runId) return
    setExpanding(true)
    try {
      const { run_id } = await expandRun(runId)
      setRunId(run_id)
      setActiveTopic(activeTopic)
      setCached(false)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Expand failed')
    } finally {
      setExpanding(false)
    }
  }

  /** Load a historical run by its ID (replays stored events via SSE). */
  function loadHistoricRun(histRunId: string, histTopic: string) {
    setRunId(histRunId)
    setActiveTopic(histTopic)
    setCached(true)  // historical runs are always "from cache"
  }

  // 'idle' only exists when there's no runId yet — don't treat it as "running"
  const isRunning   = status === 'running'
  const isCompleted = status === 'completed'
  const isCancelled = status === 'cancelled'

  return (
    <div className="run-view">
      {/* ── Search bar + history ── */}
      <div className="panel search-panel">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
          <form className="search-form" onSubmit={handleSubmit}>
            <input
              className="search-input"
              type="text"
              placeholder="Topic, brand, event, or question…"
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

        {/* History picker — refreshKey bumped on each completion */}
        <HistoryPanel onLoadRun={loadHistoricRun} refreshKey={historyKey} />
      </div>

      {/* ── Run status strip ── */}
      {runId && (
        <div className={`run-status run-status--${status}`} aria-live="polite">
          <div style={{ minWidth: 0 }}>
            <strong>{statusLabel(status, events.length)}</strong>
            {activeTopic && <p className="run-topic clip-text" title={activeTopic}>{activeTopic}</p>}
            <p className="muted" style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>
              {runId.slice(0, 8)}…
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
            {cached && !isRunning && (
              <span className="cached-badge">⚡ cached</span>
            )}
            {isCancelled && (
              <span className="cancelled-badge">⊘ cancelled</span>
            )}

            {/* Cancel button — only while running */}
            {isRunning && runId && (
              <button
                className="btn-cancel"
                onClick={handleCancel}
                disabled={cancelling}
                title="Stop this analysis"
              >
                {cancelling ? <span className="spinner" style={{ borderTopColor: 'var(--rog-red)' }} /> : '⊘'}
                {cancelling ? 'Stopping…' : 'Cancel'}
              </button>
            )}

            {/* Expand search — only when completed */}
            {isCompleted && runId && (
              <button
                className="btn-expand"
                onClick={handleExpand}
                disabled={expanding}
                title="Expand: search wider (2× URLs, any time)"
              >
                {expanding
                  ? <><span className="spinner" style={{ borderTopColor: 'var(--rog-cyan)' }} /> Expanding…</>
                  : '⊕ Expand search'}
              </button>
            )}

            {isRunning && <span className="status-spinner" />}
          </div>
        </div>
      )}

      {/* Skeleton while waiting for first event */}
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
  if (status === 'cancelled') return 'Analysis cancelled'
  if (status === 'error') return 'Analysis stopped with an error'
  if (eventCount === 0) return 'Initialising…'
  return 'Analysis in progress'
}
