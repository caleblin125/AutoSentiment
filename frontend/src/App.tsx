import { useMemo, useState } from 'react'
import { RunForm } from './components/RunForm'
import { EventTimeline } from './components/EventTimeline'
import { ReportView } from './components/ReportView'
import { useRunStream } from './hooks/useRunStream'
import type { Report } from './lib/api'
import './App.css'

export default function App() {
  const [runId, setRunId] = useState<string | null>(null)
  const { events, status } = useRunStream(runId)

  const report = useMemo(() => {
    const completed = events.findLast(event => event.type === 'run_completed')
    return (completed?.detail as { report?: Report } | undefined)?.report ?? null
  }, [events])

  function handleRunCreated(id: string) {
    setRunId(id)
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>AutoSentiment</h1>
        <p className="lede">Citation-backed brand &amp; topic sentiment from Reddit and news.</p>
      </header>

      <main className="app-main">
        <RunForm onRunCreated={handleRunCreated} />
        {runId && (
          <section className={`run-status run-status--${status}`} aria-live="polite">
            <div>
              <strong>{statusLabel(status, events.length)}</strong>
              <p className="muted">Run: <code>{runId}</code></p>
            </div>
            {(status === 'running' || status === 'idle') && <span className="status-spinner" />}
          </section>
        )}
        {runId && <EventTimeline events={events} status={status} />}
        {report && runId && <ReportView runId={runId} report={report} />}
      </main>
    </div>
  )
}

function statusLabel(status: string, eventCount: number): string {
  if (status === 'completed') return 'Report complete'
  if (status === 'error') return 'Run stopped with an error'
  if (eventCount === 0) return 'Starting research run'
  return 'Research in progress'
}
