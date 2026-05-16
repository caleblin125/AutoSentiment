import { useEffect, useState } from 'react'
import { getEvidence, type EvidenceChunk, type Quote, type Report } from '../lib/api'
import { ForceGraph } from './ForceGraph'
import { HistoryChart } from './HistoryChart'

interface Props {
  runId: string
  topic: string
  report: Report
}

// ── Favicon helpers (same as timeline) ────────────────────────────────────

const KNOWN_PROVIDERS: Record<string, string> = {
  'reddit.com': 'Reddit',
  'news.ycombinator.com': 'Hacker News',
  'youtube.com': 'YouTube',
  'youtu.be': 'YouTube',
  'x.com': 'X / Twitter',
  'twitter.com': 'X / Twitter',
  'quora.com': 'Quora',
  'nytimes.com': 'NY Times',
  'bbc.com': 'BBC',
  'bbc.co.uk': 'BBC',
  'theverge.com': 'The Verge',
  'techcrunch.com': 'TechCrunch',
  'wired.com': 'Wired',
  'bloomberg.com': 'Bloomberg',
  'reuters.com': 'Reuters',
  'wsj.com': 'WSJ',
  'apnews.com': 'AP News',
  'cnn.com': 'CNN',
  'insideevs.com': 'InsideEVs',
}

function domainFromUrl(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') }
  catch { return url }
}

function providerName(url: string): string {
  const d = domainFromUrl(url)
  for (const key of Object.keys(KNOWN_PROVIDERS)) {
    if (d === key || d.endsWith(`.${key}`)) return KNOWN_PROVIDERS[key]
  }
  return d.replace(/^(www|m|old|new)\./i, '')
}

function faviconUrl(url: string): string {
  return `https://www.google.com/s2/favicons?domain=${domainFromUrl(url)}&sz=16`
}

function SourceLogo({ url }: { url: string }) {
  return (
    <span className="source-logo-inline">
      <img
        src={faviconUrl(url)}
        alt=""
        width={14} height={14}
        onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
      />
      <span>{providerName(url)}</span>
    </span>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────

function TimingSummary({ timings }: { timings: Record<string, number> }) {
  const rows = [
    ['Query expansion', timings.query_expansion_ms],
    ['Search', timings.search_ms],
    ['Fetch', timings.fetch_ms],
    ['Sentiment', timings.sentiment_ms],
    ['Synthesis', timings.synthesis_ms],
    ['Total', timings.total_ms],
  ].filter(([, v]) => typeof v === 'number') as [string, number][]

  if (rows.length === 0) return null

  const slowest = rows.reduce((max, row) => (row[1] > max[1] ? row : max), rows[0])

  return (
    <div className="timing-grid">
      {rows.map(([label, value]) => (
        <div className={`timing-card ${slowest[0] === label ? 'timing-card--slowest' : ''}`} key={label}>
          <span>{label}</span>
          <strong>{formatDuration(value)}</strong>
        </div>
      ))}
    </div>
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
            <div className="quote-card-footer">
              <SourceLogo url={q.url} />
              <button className="cite-btn" onClick={() => onCite(q)}>snippet</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function AspectSummary({ aspects }: { aspects: NonNullable<Report['aspects']> }) {
  return (
    <div className="insight-section">
      <h3>Directional topics</h3>
      <div className="aspect-grid">
        {aspects.map(aspect => (
          <div className={`aspect-card aspect-card--${aspect.sentiment}`} key={aspect.name}>
            <strong>{aspect.name}</strong>
            <span>{aspect.sentiment} · {aspect.count} mentions</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function SourceFacts({ facts }: { facts: NonNullable<Report['source_facts']> }) {
  return (
    <div className="insight-section">
      <h3>Evidence sources</h3>
      <div className="source-fact-list">
        {facts.slice(0, 8).map(fact => (
          <div className="source-fact" key={fact.domain}>
            <div className="source-fact-header">
              <img
                src={`https://www.google.com/s2/favicons?domain=${fact.domain}&sz=16`}
                alt=""
                width={14} height={14}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
              <strong>
                {KNOWN_PROVIDERS[fact.domain] ??
                  fact.domain.replace(/^(www|m)\./i, '')}
              </strong>
            </div>
            <span>{fact.source_type} · {fact.count} items</span>
            <div className="source-fact-bar">
              <div style={{ flex: fact.labels?.positive ?? 0, background: '#22c55e' }} />
              <div style={{ flex: fact.labels?.neutral ?? 0, background: '#94a3b8' }} />
              <div style={{ flex: fact.labels?.negative ?? 0, background: '#ef4444' }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export function ReportView({ runId, topic, report }: Props) {
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
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setActiveChunk(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [activeChunk])

  const { overall, by_source, top_positive, top_negative, themes, narrative, timings, aspects, source_facts, graph } = report

  return (
    <section className="panel" aria-label="Report">
      <h2>Report</h2>

      {timings && <TimingSummary timings={timings} />}

      {/* Historical sentiment chart (only renders if 2+ past runs exist) */}
      <HistoryChart topic={topic} currentRunId={runId} />

      <div className="sentiment-bars">
        <SentimentBar label="Positive" value={overall.positive} color="#22c55e" />
        <SentimentBar label="Neutral"  value={overall.neutral}  color="#94a3b8" />
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

      {aspects && aspects.length > 0 && <AspectSummary aspects={aspects} />}
      {source_facts && source_facts.length > 0 && <SourceFacts facts={source_facts} />}

      {/* Force-directed idea graph */}
      {graph && graph.nodes.length > 0 && <ForceGraph graph={graph} />}

      <QuoteList title="Top positive" quotes={top_positive} onCite={openCitation} />
      <QuoteList title="Top negative" quotes={top_negative} onCite={openCitation} />
      {loadingChunk && <p className="muted">Loading evidence…</p>}

      {activeChunk && (
        <div className="modal-backdrop" onClick={() => setActiveChunk(null)}>
          <div
            className="evidence-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Evidence snippet"
            onClick={e => e.stopPropagation()}
          >
            <button className="modal-close" onClick={() => setActiveChunk(null)} aria-label="Close">✕</button>
            <div className="modal-source-header">
              <img
                src={faviconUrl(activeChunk.url)}
                alt=""
                width={16} height={16}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
              <a href={activeChunk.url} target="_blank" rel="noreferrer" className="modal-source-link">
                {providerName(activeChunk.url)}
              </a>
              <span className={`sentiment-chip sentiment-chip--sm sentiment-chip--${activeChunk.label}`}>
                {activeChunk.label}
              </span>
            </div>
            <p className="snippet">{activeChunk.snippet}</p>
            <a href={activeChunk.url} target="_blank" rel="noreferrer" className="view-source-link">
              View full source ↗
            </a>
          </div>
        </div>
      )}
    </section>
  )
}

// ── Utilities ──────────────────────────────────────────────────────────────

function pct(ratio: number): string {
  return `${Math.round(ratio * 100)}%`
}

function formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms)}ms`
}
