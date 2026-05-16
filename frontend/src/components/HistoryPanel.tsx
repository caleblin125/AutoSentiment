/**
 * Collapsible history panel showing all recent runs in all statuses.
 *
 * Auto-polls every 5s when open so running searches update in real time.
 * refreshKey prop can be bumped externally to force an immediate refresh.
 */
import { useEffect, useRef, useState } from 'react'
import { cancelRun, clearHistory, listRuns, type RunSummary } from '../lib/api'

interface Props {
  onOpenRun: (runId: string, topic: string) => void  // always opens in a new tab
  refreshKey?: number
}

const STATUS_ICON: Record<string, string> = {
  completed: '✓',
  running:   '●',
  pending:   '○',
  cancelled: '⊘',
  error:     '⚠',
}

const STATUS_COLOR: Record<string, string> = {
  completed: 'var(--positive)',
  running:   'var(--rog-cyan)',
  pending:   'var(--neutral)',
  cancelled: 'var(--text)',
  error:     'var(--rog-red)',
}

function formatDate(iso: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(iso))
}

function formatDuration(ms: number | null): string {
  if (ms == null || ms <= 0) return ''
  if (ms < 1000) return `${Math.round(ms)}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m${Math.round((ms % 60000) / 1000)}s`
}

function MiniBar({ overall }: { overall: RunSummary['overall'] }) {
  if (!overall) return null
  return (
    <div style={{ display: 'flex', height: 3, borderRadius: 2, overflow: 'hidden', background: 'var(--surface-muted)', marginTop: 4 }}>
      <div style={{ flex: overall.positive, background: 'var(--positive)' }} />
      <div style={{ flex: overall.neutral,  background: 'var(--neutral)' }} />
      <div style={{ flex: overall.negative, background: 'var(--rog-red)' }} />
    </div>
  )
}

export function HistoryPanel({ onOpenRun, refreshKey }: Props) {
  const [open, setOpen] = useState(false)
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function fetchRuns() {
    setLoading(true)
    try {
      const data = await listRuns(undefined, 40)
      setRuns(data)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  useEffect(() => {
    if (!open) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
      return
    }
    void Promise.resolve().then(fetchRuns)
    // Poll every 5s while open — catches status changes for running searches.
    pollRef.current = setInterval(fetchRuns, 5000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [open])

  // Immediate refresh when refreshKey changes (e.g. a search just completed).
  useEffect(() => {
    if (open && refreshKey !== undefined) void Promise.resolve().then(fetchRuns)
  }, [refreshKey, open])

  const hasRunning = runs.some(r => r.status === 'running' || r.status === 'pending')

  async function handleClear() {
    if (!confirm('Clear all completed / cancelled history?')) return
    await clearHistory()
    await fetchRuns()
  }

  return (
    <div className="history-panel">
      <button
        className="btn-secondary history-toggle"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <span className="history-icon">◷</span>
        History
        {hasRunning && <span className="history-running-dot" />}
        <span className="history-chevron">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="history-dropdown">
          {runs.length > 0 && (
            <div className="history-actions">
              <button className="history-clear-btn" onClick={handleClear}>
                ✕ Clear history
              </button>
            </div>
          )}
          {loading && runs.length === 0 && (
            <div style={{ padding: '12px 16px' }}>
              <div className="skeleton skeleton-line skeleton-line--medium" />
              <div className="skeleton skeleton-line skeleton-line--full" style={{ marginTop: 8 }} />
            </div>
          )}

          {!loading && runs.length === 0 && (
            <p style={{ padding: '12px 16px', color: 'var(--text)', fontSize: 13, margin: 0 }}>
              No searches yet.
            </p>
          )}

          {runs.map(run => {
            const isActive = run.status === 'running' || run.status === 'pending'
            return (
              <div key={run.id} className="history-item-wrap">
                <button
                  className="history-item"
                  onClick={() => { if (!isActive) { onOpenRun(run.id, run.topic); setOpen(false) } }}
                  disabled={isActive}
                  title={isActive ? 'Currently running' : run.topic}
                >
                  <div className="history-item-top">
                    <span
                      className="history-status-icon"
                      style={{ color: STATUS_COLOR[run.status] ?? 'var(--text)' }}
                    >
                      {run.status === 'running'
                        ? <span className="inline-spinner" style={{ width: 8, height: 8 }} />
                        : STATUS_ICON[run.status] ?? '?'}
                    </span>
                    <span className="history-topic" title={run.topic}>{run.topic}</span>
                    <span className="history-date">{formatDate(run.created_at)}</span>
                  </div>

                  {run.overall && (
                    <div className="history-item-stats">
                      <span style={{ color: 'var(--positive)', fontFamily: 'var(--mono)', fontSize: 10 }}>
                        +{Math.round(run.overall.positive * 100)}%
                      </span>
                      <span style={{ color: 'var(--neutral)', fontFamily: 'var(--mono)', fontSize: 10, margin: '0 6px' }}>
                        ~{Math.round(run.overall.neutral * 100)}%
                      </span>
                      <span style={{ color: 'var(--rog-red)', fontFamily: 'var(--mono)', fontSize: 10 }}>
                        -{Math.round(run.overall.negative * 100)}%
                      </span>
                      <span style={{ marginLeft: 'auto', color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: 10 }}>
                        {run.overall.total} items
                        {run.duration_ms ? <span className="history-duration"> · {formatDuration(run.duration_ms)}</span> : null}
                      </span>
                    </div>
                  )}
                  <MiniBar overall={run.overall} />
                </button>

                {/* Cancel button for active runs */}
                {isActive && (
                  <button
                    className="history-cancel-btn"
                    title="Cancel this run"
                    onClick={async e => {
                      e.stopPropagation()
                      try { await cancelRun(run.id) } catch { /* best-effort */ }
                      await fetchRuns()
                    }}
                  >
                    ✕
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
