import { useEffect, useRef, useState } from 'react'
import {
  getEvidence,
  type ArgumentItem,
  type EvidenceChunk,
  type GraphNode,
  type ImpactItem,
  type Quote,
  type Report,
} from '../lib/api'
import { ForceGraph } from './ForceGraph'
import { HistoryChart } from './HistoryChart'

interface Props { runId: string; topic: string; report: Report }

// ── Favicon / provider helpers ────────────────────────────────────────────

const KNOWN_PROVIDERS: Record<string, string> = {
  'reddit.com': 'Reddit', 'news.ycombinator.com': 'Hacker News', 'youtube.com': 'YouTube',
  'x.com': 'X / Twitter', 'twitter.com': 'X / Twitter', 'threads.net': 'Threads',
  'quora.com': 'Quora', 'facebook.com': 'Facebook', 'linkedin.com': 'LinkedIn',
  'tiktok.com': 'TikTok', 'nytimes.com': 'NY Times', 'bbc.com': 'BBC', 'bbc.co.uk': 'BBC',
  'theverge.com': 'The Verge', 'techcrunch.com': 'TechCrunch', 'wired.com': 'Wired',
  'bloomberg.com': 'Bloomberg', 'reuters.com': 'Reuters', 'wsj.com': 'WSJ',
  'apnews.com': 'AP News', 'cnn.com': 'CNN', 'insideevs.com': 'InsideEVs',
}

function domainFromUrl(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url }
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
    <span className="source-logo-inline" title={url}>
      <img src={faviconUrl(url)} alt="" width={14} height={14}
        onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
      <span className="clip-text">{providerName(url)}</span>
    </span>
  )
}

// ── Timing + performance analysis ────────────────────────────────────────

const TIMING_TIPS: Record<string, string> = {
  Expansion: 'Query expansion uses the 120B model. Switch to a faster model to reduce latency.',
  Search:    'Brave search is sequential (1 req/s rate limit). Reduce query count or cache more aggressively.',
  Fetch:     'URL fetching is parallel. Increase _FETCH_CONCURRENCY or reduce max_urls_per_run.',
  Sentiment: 'Per-item sentiment uses the 30B model in parallel. Increase light_queue_max_parallel or reduce max_items_per_run.',
  Synthesis: 'Report synthesis uses the 120B model. Switch to a faster model or reduce sample size.',
}

function TimingSummary({ timings }: { timings: Record<string, number> }) {
  const [showTips, setShowTips] = useState(false)
  const rows = [
    ['Expansion', timings.query_expansion_ms],
    ['Search', timings.search_ms],
    ['Fetch', timings.fetch_ms],
    ['Sentiment', timings.sentiment_ms],
    ['Synthesis', timings.synthesis_ms],
    ['Total', timings.total_ms],
  ].filter(([, v]) => typeof v === 'number') as [string, number][]
  if (!rows.length) return null

  const mainRows = rows.filter(([l]) => l !== 'Total')
  const slowest = mainRows.length
    ? mainRows.reduce((max, r) => (r[1] > max[1] ? r : max), mainRows[0])
    : rows[0]

  return (
    <div className="timing-section">
      <div className="timing-header">
        <h3>Performance</h3>
        <button className="btn-secondary" style={{ fontSize: 11, height: 26, padding: '0 10px' }}
          onClick={() => setShowTips(t => !t)}>
          {showTips ? '▲ hide tips' : '▼ optimization tips'}
        </button>
      </div>
      <div className="timing-grid">
        {rows.map(([label, value]) => (
          <div className={`timing-card${slowest[0] === label ? ' timing-card--slowest' : ''}`} key={label}>
            <span>{label}</span>
            <strong>{fmtDuration(value)}</strong>
            {slowest[0] === label && <span className="timing-slow-badge">slowest</span>}
          </div>
        ))}
      </div>
      {showTips && (
        <div className="timing-tips">
          {mainRows.map(([label]) => (
            <div key={label} className={`timing-tip${slowest[0] === label ? ' timing-tip--highlight' : ''}`}>
              <strong>{label}:</strong> {TIMING_TIPS[label] ?? '—'}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Sentiment bars ────────────────────────────────────────────────────────

function SentimentBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="sentiment-row">
      <div className="sentiment-row__label">
        <span>{label}</span>
        <strong style={{ fontFamily: 'var(--mono)' }}>{pct(value)}</strong>
      </div>
      <div className="sentiment-track">
        <div className="sentiment-fill" style={{ width: pct(value), background: color }} />
      </div>
    </div>
  )
}

// ── Impact / Reasons / Arguments ──────────────────────────────────────────

function AnalysisSection({ impacts, reasons, arguments: args }: {
  impacts?: ImpactItem[]
  reasons?: string[]
  arguments?: ArgumentItem[]
}) {
  const hasAny = (impacts?.length ?? 0) + (reasons?.length ?? 0) + (args?.length ?? 0) > 0
  if (!hasAny) return null

  return (
    <div className="insight-section">
      <h3>Analysis</h3>
      <div className="analysis-grid">
        {impacts && impacts.length > 0 && (
          <div className="analysis-card">
            <h4>Impacts</h4>
            {impacts.map((im, i) => (
              <div key={i} className="impact-item">
                <span className="impact-icon">{im.direction === 'positive' ? '▲' : '▼'}</span>
                <span style={{ color: im.direction === 'positive' ? 'var(--positive)' : 'var(--rog-red)' }}>
                  {im.description}
                </span>
              </div>
            ))}
          </div>
        )}

        {reasons && reasons.length > 0 && (
          <div className="analysis-card">
            <h4>Key Reasons</h4>
            <ul>
              {reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </div>
        )}

        {args && args.length > 0 && (
          <div className="analysis-card" style={{ gridColumn: args.length > 2 ? '1 / -1' : undefined }}>
            <h4>Arguments</h4>
            {args.map((a, i) => (
              <div key={i} className={`arg-item arg-item--${a.side}`}>
                <strong>{a.side === 'for' ? '▶ For' : '◀ Against'}</strong>
                <p>{a.claim}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Aspect summary ────────────────────────────────────────────────────────

function AspectSummary({ aspects }: { aspects: NonNullable<Report['aspects']> }) {
  return (
    <div className="insight-section">
      <h3>Directional topics</h3>
      <div className="aspect-grid">
        {aspects.map(a => (
          <div className={`aspect-card aspect-card--${a.sentiment}`} key={a.name}>
            <strong>{a.name}</strong>
            <span>{a.sentiment} · {a.count} mentions</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Source facts (grouped by source type with expandable subtypes) ────────

import { useState as _useState } from 'react'  // already imported above; alias for clarity

const SOURCE_TYPE_LABEL: Record<string, string> = {
  reddit: 'Reddit',
  news:   'News Media',
  social: 'Social Media',
  forum:  'Forums',
  video:  'Video',
  web:    'Web / Blogs',
}

const SOURCE_TYPE_ICON: Record<string, string> = {
  reddit: '⬤',
  news:   '📰',
  social: '💬',
  forum:  '🗣',
  video:  '▶',
  web:    '🌐',
}

interface SourceGroup {
  type: string
  label: string
  count: number
  positive: number
  neutral: number
  negative: number
  domains: NonNullable<Report['source_facts']>
}

function groupSourceFacts(facts: NonNullable<Report['source_facts']>): SourceGroup[] {
  const byType = new Map<string, SourceGroup>()
  for (const f of facts) {
    if (f.count === 0) continue  // skip zero-item sources
    const type = f.source_type
    if (!byType.has(type)) {
      byType.set(type, {
        type, label: SOURCE_TYPE_LABEL[type] ?? type,
        count: 0, positive: 0, neutral: 0, negative: 0, domains: [],
      })
    }
    const g = byType.get(type)!
    g.count += f.count
    g.positive += f.labels?.positive ?? 0
    g.neutral  += f.labels?.neutral  ?? 0
    g.negative += f.labels?.negative ?? 0
    g.domains.push(f)
  }
  return [...byType.values()].sort((a, b) => b.count - a.count)
}

function SourceGroupCard({ group }: { group: SourceGroup }) {
  const [open, setOpen] = _useState(false)
  const total = group.positive + group.neutral + group.negative || 1
  const icon = SOURCE_TYPE_ICON[group.type] ?? '●'

  return (
    <div className="source-group">
      <button className="source-group-header" onClick={() => setOpen(o => !o)}>
        <span className="source-group-icon">{icon}</span>
        <span className="source-group-label">{group.label}</span>
        <span className="source-group-count">{group.count} items · {group.domains.length} sources</span>
        <div className="source-group-bar">
          <div style={{ flex: group.positive / total, background: 'var(--positive)' }} />
          <div style={{ flex: group.neutral  / total, background: 'var(--neutral)' }} />
          <div style={{ flex: group.negative / total, background: 'var(--rog-red)' }} />
        </div>
        <span className="source-group-chevron">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="source-group-domains">
          {group.domains.sort((a, b) => b.count - a.count).map(fact => {
            const fakeUrl = `https://${fact.domain}`
            const dtotal = (fact.labels?.positive ?? 0) + (fact.labels?.neutral ?? 0) + (fact.labels?.negative ?? 0) || 1
            return (
              <a
                key={fact.domain}
                className="source-fact"
                href={fakeUrl}
                target="_blank"
                rel="noreferrer"
              >
                <div className="source-fact-header">
                  <img
                    src={`https://www.google.com/s2/favicons?domain=${fact.domain}&sz=14`}
                    alt="" width={14} height={14}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                  <strong className="clip-text" title={fact.domain}>
                    {KNOWN_PROVIDERS[fact.domain] ?? fact.domain.replace(/^www\./, '')}
                  </strong>
                </div>
                <span style={{ fontSize: 10, color: 'var(--text)', fontFamily: 'var(--mono)' }}>
                  {fact.count} items
                </span>
                <div className="source-fact-bar">
                  <div style={{ flex: (fact.labels?.positive ?? 0) / dtotal, background: 'var(--positive)' }} />
                  <div style={{ flex: (fact.labels?.neutral  ?? 0) / dtotal, background: 'var(--neutral)' }} />
                  <div style={{ flex: (fact.labels?.negative ?? 0) / dtotal, background: 'var(--rog-red)' }} />
                </div>
              </a>
            )
          })}
        </div>
      )}
    </div>
  )
}

function SourceFacts({ facts }: { facts: NonNullable<Report['source_facts']> }) {
  const groups = groupSourceFacts(facts)
  if (!groups.length) return null
  return (
    <div className="insight-section">
      <h3>Evidence sources</h3>
      <div className="source-group-list">
        {groups.map(g => <SourceGroupCard key={g.type} group={g} />)}
      </div>
    </div>
  )
}

// ── Quotes ────────────────────────────────────────────────────────────────

function QuoteList({ title, quotes, onCite, highlightedId, sectionRef }: {
  title: string
  quotes: Quote[]
  onCite: (q: Quote) => void
  highlightedId?: string | null
  sectionRef?: React.RefObject<HTMLDivElement | null>
}) {
  if (!quotes.length) return null
  return (
    <div className="quote-list" ref={sectionRef}>
      <h3>{title}</h3>
      <div className="quote-grid">
        {quotes.map(q => (
          <article
            className={`quote-card${highlightedId === q.evidence_id ? ' quote-card--highlighted' : ''}`}
            key={q.evidence_id}
          >
            <p title={q.summary}>"{q.summary}"</p>
            <div className="quote-card-footer">
              <a href={q.url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>
                <SourceLogo url={q.url} />
              </a>
              <div style={{ display: 'flex', gap: 6 }}>
                <a
                  href={q.url}
                  target="_blank"
                  rel="noreferrer"
                  className="cite-btn"
                  style={{ textDecoration: 'none' }}
                  title="Open source in new tab"
                >
                  ↗ source
                </a>
                <button className="cite-btn" onClick={() => onCite(q)}>inspect</button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

// ── Evidence modal ────────────────────────────────────────────────────────

function EvidenceModal({ chunk, onClose }: { chunk: EvidenceChunk; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Trim to first 3 meaningful sentences or 350 chars, whichever is shorter.
  function trimSnippet(text: string): string {
    const sentences = text.split(/(?<=[.!?])\s+/).filter(s => s.trim().length > 10)
    const first3 = sentences.slice(0, 3).join(' ')
    if (first3.length <= 350) return first3
    const cut = text.slice(0, 350)
    const lastPunct = Math.max(cut.lastIndexOf('.'), cut.lastIndexOf('!'), cut.lastIndexOf('?'))
    return lastPunct > 100 ? cut.slice(0, lastPunct + 1) : cut + '…'
  }

  const displaySnippet = trimSnippet(chunk.snippet)

  // Keyword extraction from the FULL snippet for accurate analysis.
  const words = chunk.snippet.toLowerCase().split(/\W+/).filter(w => w.length > 4)
  const freqMap = new Map<string, number>()
  words.forEach(w => freqMap.set(w, (freqMap.get(w) ?? 0) + 1))
  const keywords = [...freqMap.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([w]) => w)

  const sentenceCount = chunk.snippet.split(/[.!?]+/).filter(s => s.trim().length > 10).length

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="evidence-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Evidence snippet"
        onClick={e => e.stopPropagation()}
      >
        <button className="modal-close" onClick={onClose} aria-label="Close">✕</button>

        {/* Source header */}
        <div className="modal-source-header">
          <img src={faviconUrl(chunk.url)} alt="" width={16} height={16}
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          <a className="modal-source-link" href={chunk.url} target="_blank" rel="noreferrer">
            {providerName(chunk.url)}
          </a>
          <span className={`sentiment-chip sentiment-chip--${chunk.label}`}>{chunk.label}</span>
          <span style={{ marginLeft: 'auto', color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: 11 }}>
            {new Date(chunk.retrieved_at).toLocaleDateString()}
          </span>
        </div>

        {/* Trimmed snippet — link to full source for complete text */}
        <p className="snippet">{displaySnippet}</p>

        {/* Structured analysis */}
        <div className="snippet-analysis">
          <div className="snippet-analysis-block">
            <h4>Key terms</h4>
            <p>{keywords.join(', ') || '—'}</p>
          </div>
          <div className="snippet-analysis-block">
            <h4>Scope</h4>
            <p>{sentenceCount} sentence{sentenceCount !== 1 ? 's' : ''} · {chunk.source_type} · {chunk.snippet.split(' ').length} words</p>
          </div>
          <div className="snippet-analysis-block">
            <h4>Model summary</h4>
            <p>{chunk.summary}</p>
          </div>
          <div className="snippet-analysis-block">
            <h4>Sentiment</h4>
            <p style={{ color: chunk.label === 'positive' ? 'var(--positive)' : chunk.label === 'negative' ? 'var(--rog-red)' : 'var(--neutral)', fontWeight: 700 }}>
              {chunk.label.toUpperCase()}
            </p>
          </div>
        </div>

        <a href={chunk.url} target="_blank" rel="noreferrer" className="view-source-link">
          View full source ↗
        </a>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────

export function ReportView({ runId, topic, report }: Props) {
  const [activeChunk, setActiveChunk] = useState<EvidenceChunk | null>(null)
  const [loadingChunk, setLoadingChunk] = useState(false)
  const [highlightedId, setHighlightedId] = useState<string | null>(null)
  const posRef = useRef<HTMLDivElement | null>(null)
  const negRef = useRef<HTMLDivElement | null>(null)

  async function openCitation(quote: Quote) {
    setLoadingChunk(true)
    try { setActiveChunk(await getEvidence(runId, quote.evidence_id)) }
    finally { setLoadingChunk(false) }
  }

  /**
   * Handle clicks on graph nodes — scroll to the relevant quote section
   * and highlight the best-matching quote for 3 seconds.
   */
  function handleGraphNodeClick(node: GraphNode) {
    const label = node.label.toLowerCase()
    const allQuotes = [...top_positive, ...top_negative]

    // Decide which section to scroll to and which quote to highlight.
    let targetRef: React.RefObject<HTMLDivElement | null>
    let matchQuote: Quote | undefined

    if (node.id === 'sentiment:positive' || node.label.toLowerCase() === 'positive') {
      targetRef = posRef
      matchQuote = top_positive[0]
    } else if (node.id === 'sentiment:negative' || node.label.toLowerCase() === 'negative') {
      targetRef = negRef
      matchQuote = top_negative[0]
    } else {
      // Theme or aspect — find the quote whose summary contains the label
      matchQuote = allQuotes.find(q => q.summary.toLowerCase().includes(label))
      // Scroll to the section that contains the match
      const inPos = top_positive.some(q => q.evidence_id === matchQuote?.evidence_id)
      targetRef = inPos ? posRef : negRef
      if (!matchQuote) {
        // No match — just scroll to positive section
        targetRef = posRef
        matchQuote = top_positive[0]
      }
    }

    targetRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })

    if (matchQuote) {
      setHighlightedId(matchQuote.evidence_id)
      setTimeout(() => setHighlightedId(null), 3000)
    }
  }

  const {
    overall, by_source, top_positive, top_negative, themes, narrative,
    timings, aspects, source_facts, graph, impacts, reasons, arguments: args,
  } = report

  return (
    <section className="panel" aria-label="Report">
      <h2>Report</h2>

      {timings && <TimingSummary timings={timings} />}
      <HistoryChart topic={topic} currentRunId={runId} />

      {/* Sentiment bars */}
      <div className="sentiment-bars">
        <SentimentBar label="Positive" value={overall.positive} color="var(--positive)" />
        <SentimentBar label="Neutral"  value={overall.neutral}  color="var(--neutral)" />
        <SentimentBar label="Negative" value={overall.negative} color="var(--rog-red)" />
        <p className="muted" style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>
          {overall.total} items analyzed
        </p>
      </div>

      {/* Source breakdown */}
      <table className="source-table">
        <thead>
          <tr>
            <th>Source</th><th>Items</th><th>Positive</th><th>Neutral</th><th>Negative</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(by_source)
            .filter(([, stats]) => (stats?.count ?? 0) > 0)
            .map(([src, stats]) => (
              <tr key={src}>
                <td>{SOURCE_TYPE_LABEL[src] ?? src}</td>
                <td style={{ fontFamily: 'var(--mono)' }}>{stats?.count ?? 0}</td>
                <td style={{ color: 'var(--positive)', fontFamily: 'var(--mono)' }}>{pct(stats?.positive ?? 0)}</td>
                <td style={{ fontFamily: 'var(--mono)' }}>{pct(stats?.neutral ?? 0)}</td>
                <td style={{ color: 'var(--rog-red)', fontFamily: 'var(--mono)' }}>{pct(stats?.negative ?? 0)}</td>
              </tr>
            ))}
        </tbody>
      </table>

      {themes.length > 0 && (
        <div className="themes">
          <strong style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--rog-cyan)', textTransform: 'uppercase', letterSpacing: 1 }}>
            Key themes:
          </strong>{' '}
          {themes.join(' · ')}
        </div>
      )}

      <p className="narrative">{narrative}</p>

      <AnalysisSection impacts={impacts} reasons={reasons} arguments={args} />

      {aspects && aspects.length > 0 && <AspectSummary aspects={aspects} />}
      {source_facts && source_facts.length > 0 && <SourceFacts facts={source_facts} />}

      {/* Graph — theme/aspect click → topic detail popover; sentiment click → scroll to quotes */}
      {graph && graph.nodes.length > 0 && (
        <ForceGraph graph={graph} runId={runId} onNodeClick={handleGraphNodeClick} />
      )}

      <QuoteList
        title="Top positive"
        quotes={top_positive}
        onCite={openCitation}
        highlightedId={highlightedId}
        sectionRef={posRef}
      />
      <QuoteList
        title="Top negative"
        quotes={top_negative}
        onCite={openCitation}
        highlightedId={highlightedId}
        sectionRef={negRef}
      />

      {loadingChunk && (
        <div style={{ padding: '8px 0' }}>
          <div className="skeleton skeleton-line skeleton-line--medium" />
        </div>
      )}

      {activeChunk && (
        <EvidenceModal chunk={activeChunk} onClose={() => setActiveChunk(null)} />
      )}
    </section>
  )
}

// ── Utilities ─────────────────────────────────────────────────────────────

function pct(r: number): string { return `${Math.round(r * 100)}%` }
function fmtDuration(ms: number): string { return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms` }
