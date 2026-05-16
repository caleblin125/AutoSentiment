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
  const ncRunCount = runCounts ? (runCounts['running'] ?? 0) : 0

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
          <div className="dev-section-title">Models</div>
          <div className="dev-stat">
            <span>NemoClaw · Query expansion + Synthesis</span>
            <strong style={{ color: '#a78bfa' }}>nemotron-3-super:120b</strong>
          </div>
          <div className="dev-stat">
            <span>Sentiment · Per-item classification</span>
            <strong style={{ color: 'var(--rog-cyan)' }}>nemotron3:33b</strong>
          </div>
          <div className="dev-stat">
            <span>Suggestions · Search angle generation</span>
            <strong style={{ color: 'var(--positive)' }}>deepseek-r1:14b</strong>
          </div>
        </div>

        <div className="dev-section">
          <div className="dev-section-title">NemoClaw Agent</div>
          <div className="dev-stat">
            <span>Backend</span>
            <strong style={{ fontFamily: 'var(--mono)' }}>Ollama /api/generate (streaming)</strong>
          </div>
          <div className="dev-stat">
            <span>Cancel method</span>
            <strong style={{ fontFamily: 'var(--mono)' }}>cancel_check per token</strong>
          </div>
          <div className="dev-stat">
            <span>Agent runs active</span>
            <strong style={{ color: ncRunCount > 0 ? '#a78bfa' : 'var(--text)' }}>
              {ncRunCount > 0 ? `${ncRunCount} running` : 'idle'}
            </strong>
          </div>
          <div className="dev-stat">
            <span>Tools</span>
            <strong style={{ fontFamily: 'var(--mono)', fontSize: 10 }}>
              ollama_generate · brave_search · fetch_items
            </strong>
          </div>
          <div className="dev-stat">
            <span>Query strategy</span>
            <strong style={{ fontFamily: 'var(--mono)', fontSize: 10 }}>
              date-aware · 4 expert angles
            </strong>
          </div>
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
