/**
 * NemoClaw autonomous research panel.
 *
 * Streams NemoClaw's live activity then renders its expert analysis report.
 * Appears below the status strip when activated with the ⬡ NemoClaw button.
 */
import { useMemo } from 'react'
import { useRunStream } from '../hooks/useRunStream'

interface Props {
  ncRunId: string
  topic: string
}

interface NemoClawCategory {
  name: string
  side: 'positive' | 'negative' | 'neutral'
  items: string[]
}

interface NemoClawReport {
  type: 'nemoclaw'
  summary: string
  key_findings: string[]
  categories: NemoClawCategory[]
  verdict: string
}

export function NemoClawPanel({ ncRunId, topic }: Props) {
  const { events, status } = useRunStream(ncRunId)

  const report = useMemo<NemoClawReport | null>(() => {
    const completed = events.findLast(e => e.type === 'run_completed')
    const r = (completed?.detail as { report?: NemoClawReport } | undefined)?.report
    return r?.type === 'nemoclaw' ? r : null
  }, [events])

  const liveMessages = events
    .filter(e => e.type === 'search_queried' || e.type === 'url_fetched')
    .slice(-5)

  return (
    <div className={`nemoclaw-panel nemoclaw-panel--${status}`}>
      <div className="nemoclaw-header">
        <span className="nemoclaw-logo">⬡</span>
        <div>
          <strong className="nemoclaw-title">NemoClaw</strong>
          <span className="nemoclaw-subtitle">Autonomous expert research · {topic}</span>
        </div>
        <span className={`nemoclaw-status nemoclaw-status--${status}`}>
          {status === 'running' && <><span className="status-spinner" style={{ width: 10, height: 10 }} /> Researching</>}
          {status === 'completed' && '✓ Complete'}
          {status === 'cancelled' && '⊘ Stopped'}
          {status === 'error'    && '⚠ Error'}
          {status === 'idle'     && '…'}
        </span>
      </div>

      {/* Live activity feed */}
      {status === 'running' && liveMessages.length > 0 && (
        <div className="nemoclaw-live">
          {liveMessages.map(ev => (
            <div key={ev.seq} className="nemoclaw-live-item">
              <span className="nemoclaw-live-type">{ev.type === 'search_queried' ? '⌕' : '↓'}</span>
              <span className="nemoclaw-live-msg">{ev.message}</span>
              {ev.type === 'search_queried' && typeof ev.detail.query === 'string' && (
                <span className="nemoclaw-live-query">"{ev.detail.query}"</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Expert analysis output */}
      {report && (
        <div className="nemoclaw-report">
          <p className="nemoclaw-summary">{report.summary}</p>

          {report.verdict && (
            <div className="nemoclaw-verdict">
              <span className="nemoclaw-verdict-label">Expert verdict</span>
              <p>{report.verdict}</p>
            </div>
          )}

          <div className="nemoclaw-columns">
            {report.key_findings.length > 0 && (
              <div className="nemoclaw-col">
                <h4>Key findings</h4>
                <ul>
                  {report.key_findings.map((f, i) => <li key={i}>{f}</li>)}
                </ul>
              </div>
            )}
            {report.categories.map((cat, ci) => {
              const color = cat.side === 'positive' ? 'var(--positive)'
                          : cat.side === 'negative' ? 'var(--rog-red)'
                          : 'var(--rog-cyan)'
              return (
                <div className="nemoclaw-col" key={ci}>
                  <h4 style={{ color }}>{cat.name}</h4>
                  <ul>
                    {cat.items.map((item, i) => (
                      <li key={i} style={{ color }}>{item}</li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {status === 'running' && !report && events.length === 0 && (
        <div style={{ padding: '12px 16px' }}>
          <div className="skeleton skeleton-line skeleton-line--full" />
          <div className="skeleton skeleton-line skeleton-line--medium" style={{ marginTop: 8 }} />
        </div>
      )}
    </div>
  )
}
