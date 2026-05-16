/**
 * Dev mode overlay — shows backend perf stats, active SSE queues, model timing.
 * Toggled with Ctrl+Shift+D or the ⚙ button in the header.
 */
import { useEffect, useState } from 'react'
import { getDevStats } from '../lib/api'

interface Props { onClose: () => void }

export function DevOverlay({ onClose }: Props) {
  const [stats, setStats] = useState<Record<string, unknown>>({})
  const [lastFetch, setLastFetch] = useState<Date | null>(null)

  async function fetchStats() {
    const s = await getDevStats()
    setStats(s)
    setLastFetch(new Date())
  }

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, 3000)
    return () => clearInterval(interval)
  }, [])

  const runCounts = stats.run_counts as Record<string, number> | undefined
  const activeQueues = stats.active_sse_queues as number | undefined

  return (
    <div className="dev-overlay">
      <div className="dev-panel">
        <div className="dev-panel-header">
          <span className="dev-panel-title">⚙ Dev Mode</span>
          <span className="dev-panel-hint">Ctrl+Shift+D to toggle</span>
          <button className="dev-close" onClick={onClose}>✕</button>
        </div>

        <div className="dev-section">
          <div className="dev-section-title">Backend — Active SSE Connections</div>
          <div className="dev-stat">
            <span>Live SSE queues</span>
            <strong style={{ color: activeQueues ? 'var(--rog-cyan)' : 'var(--text)' }}>
              {activeQueues ?? '—'}
            </strong>
          </div>
        </div>

        {runCounts && (
          <div className="dev-section">
            <div className="dev-section-title">Run Counts</div>
            {Object.entries(runCounts).map(([status, count]) => (
              <div className="dev-stat" key={status}>
                <span style={{ textTransform: 'capitalize' }}>{status}</span>
                <strong style={{
                  color: status === 'running' ? 'var(--rog-cyan)' :
                         status === 'error'   ? 'var(--rog-red)' :
                         status === 'completed' ? 'var(--positive)' : 'var(--text)',
                }}>
                  {count}
                </strong>
              </div>
            ))}
          </div>
        )}

        <div className="dev-section">
          <div className="dev-section-title">Models (from .env)</div>
          <div className="dev-stat"><span>NemoClaw (synthesis)</span><strong>nemotron-3-super:120b</strong></div>
          <div className="dev-stat"><span>Sentiment (per item)</span><strong>nemotron3:33b</strong></div>
          <div className="dev-stat"><span>Suggestions</span><strong>deepseek-r1:14b</strong></div>
        </div>

        <div className="dev-section">
          <div className="dev-section-title">Session</div>
          <div className="dev-stat">
            <span>localStorage key</span>
            <strong style={{ fontFamily: 'var(--mono)' }}>autosentiment_session</strong>
          </div>
          <div className="dev-stat">
            <span>Session size</span>
            <strong style={{ fontFamily: 'var(--mono)' }}>
              {(localStorage.getItem('autosentiment_session')?.length ?? 0)} chars
            </strong>
          </div>
          <button
            className="btn-secondary"
            style={{ marginTop: 8, fontSize: 11, height: 26, padding: '0 10px', width: '100%' }}
            onClick={() => { localStorage.removeItem('autosentiment_session'); window.location.reload() }}
          >
            Clear session + reload
          </button>
        </div>

        {lastFetch && (
          <div className="dev-footer">
            Updated {lastFetch.toLocaleTimeString()} · auto-refreshes every 3s
          </div>
        )}
      </div>
    </div>
  )
}
