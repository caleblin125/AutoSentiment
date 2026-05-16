import { useEffect, useState } from 'react'
import { getEvidence, type EvidenceChunk, type Quote, type Report } from '../lib/api'

interface Props {
  runId: string
  report: Report
}

export function ReportView({ runId, report }: Props) {
  const [activeChunk, setActiveChunk] = useState<EvidenceChunk | null>(null)
  const [loadingChunk, setLoadingChunk] = useState(false)

  async function openCitation(quote: Quote) {
    setLoadingChunk(true)
    try {
      const chunk = await getEvidence(runId, quote.evidence_id)
      setActiveChunk(chunk)
    } finally {
      setLoadingChunk(false)
    }
  }

  useEffect(() => {
    if (!activeChunk) return

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setActiveChunk(null)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeChunk])

  const { overall, by_source, top_positive, top_negative, themes, narrative } = report

  return (
    <section className="panel" aria-label="Report">
      <h2>Report</h2>

      <div className="sentiment-bars">
        <SentimentBar label="Positive" value={overall.positive} color="#22c55e" />
        <SentimentBar label="Neutral" value={overall.neutral} color="#94a3b8" />
        <SentimentBar label="Negative" value={overall.negative} color="#ef4444" />
        <p className="muted">{overall.total} items analyzed</p>
      </div>

      <table className="source-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Items</th>
            <th>Positive</th>
            <th>Neutral</th>
            <th>Negative</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(by_source).map(([src, stats]) => (
            <tr key={src}>
              <td>{src}</td>
              <td>{stats?.count ?? 0}</td>
              <td>{pct(stats?.positive ?? 0)}</td>
              <td>{pct(stats?.neutral ?? 0)}</td>
              <td>{pct(stats?.negative ?? 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {themes.length > 0 && (
        <div className="themes">
          <strong>Key themes:</strong> {themes.join(' · ')}
        </div>
      )}

      <p className="narrative">{narrative}</p>

      <QuoteList title="Top positive" quotes={top_positive} onCite={openCitation} />
      <QuoteList title="Top negative" quotes={top_negative} onCite={openCitation} />
      {loadingChunk && <p className="muted">Loading evidence...</p>}

      {activeChunk && (
        <div className="modal-backdrop" onClick={() => setActiveChunk(null)}>
          <div
            className="evidence-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Evidence"
            onClick={event => event.stopPropagation()}
          >
            <button className="modal-close" onClick={() => setActiveChunk(null)} aria-label="Close">
              x
            </button>
            <p className="snippet">{activeChunk.snippet}</p>
            <a href={activeChunk.url} target="_blank" rel="noreferrer">View source</a>
          </div>
        </div>
      )}
    </section>
  )
}

function SentimentBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="sentiment-row">
      <div className="sentiment-row__label">
        <span>{label}</span>
        <strong>{pct(value)}</strong>
      </div>
      <div className="sentiment-track">
        <div className="sentiment-fill" style={{ width: pct(value), backgroundColor: color }} />
      </div>
    </div>
  )
}

function QuoteList({ title, quotes, onCite }: {
  title: string
  quotes: Quote[]
  onCite: (q: Quote) => void
}) {
  if (quotes.length === 0) return null
  return (
    <div className="quote-list">
      <h3>{title}</h3>
      <div className="quote-grid">
        {quotes.map(q => (
          <article className="quote-card" key={q.evidence_id}>
            <p>"{q.summary}"</p>
            <button className="cite-btn" onClick={() => onCite(q)}>source</button>
          </article>
        ))}
      </div>
    </div>
  )
}

function pct(ratio: number): string {
  return `${Math.round(ratio * 100)}%`
}
