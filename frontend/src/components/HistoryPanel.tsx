/**
 * Collapsible history panel showing recent completed runs.
 * Clicking a run loads it into the current tab by replaying stored events.
 */
import { useEffect, useState } from 'react'
import { listRuns, type RunSummary } from '../lib/api'

interface Props {
  /** Called when the user picks a historical run to reload. */
  onLoadRun: (runId: string, topic: string) => void
}

function sentimentBar(overall: RunSummary['overall']) {
  if (!overall) return null
  return (
    <div style={{ display: 'flex', height: 4, borderRadius: 2, overflow: 'hidden', background: 'var(--surface-muted)', marginTop: 4 }}>
      <div style={{ flex: overall.positive, background: 'var(--positive)' }} />
      <div style={{ flex: overall.neutral,  background: 'var(--neutral)' }} />
      <div style={{ flex: overall.negative, background: 'var(--rog-red)' }} />
    </div>
  )
}

function formatDate(iso: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(iso))
}

export function HistoryPanel({ onLoadRun }: Props) {
  const [open, setOpen] = useState(false)
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    listRuns(undefined, 30)
      .then(data => setRuns(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [open])

  return (
    <div className="history-panel">
      <button
        className="btn-secondary history-toggle"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <span className="history-icon">◷</span>
        History
        <span className="history-chevron">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="history-dropdown">
          {loading && (
            <div style={{ padding: '12px 16px' }}>
              <div className="skeleton skeleton-line skeleton-line--medium" />
              <div className="skeleton skeleton-line skeleton-line--full" style={{ marginTop: 8 }} />
            </div>
          )}

          {!loading && runs.length === 0 && (
            <p style={{ padding: '12px 16px', color: 'var(--text)', fontSize: 13, margin: 0 }}>
              No past searches yet.
            </p>
          )}

          {!loading && runs.map(run => (
            <button
              key={run.id}
              className="history-item"
              onClick={() => { onLoadRun(run.id, run.topic); setOpen(false) }}
            >
              <div className="history-item-top">
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
                  </span>
                </div>
              )}
              {sentimentBar(run.overall)}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
