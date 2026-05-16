import { useEffect, useRef, useState } from 'react'
import {
  getEvidence,
  type ArgumentItem,
  type EvidenceChunk,
  type GraphNode,
  type ImpactItem,
  type Quote,
  type Report,
  type ThreadItem,
} from '../lib/api'
import { ForceGraph } from './ForceGraph'

interface Props { runId: string; topic: string; report: Report; onSearchTopic?: (topic: string) => void }

// ── Favicon / provider helpers ────────────────────────────────────────────

const KNOWN_PROVIDERS: Record<string, string> = {
  'reddit.com': 'Reddit', 'news.ycombinator.com': 'Hacker News', 'youtube.com': 'YouTube',
  'x.com': 'X / Twitter', 'twitter.com': 'X / Twitter', 'threads.net': 'Threads',
  'quora.com': 'Quora', 'facebook.com': 'Facebook', 'linkedin.com': 'LinkedIn',
  'tiktok.com': 'TikTok', 'nytimes.com': 'NY Times', 'bbc.com': 'BBC', 'bbc.co.uk': 'BBC',
  'theverge.com': 'The Verge', 'techcrunch.com': 'TechCrunch', 'wired.com': 'Wired',
  'bloomberg.com': 'Bloomberg', 'reuters.com': 'Reuters', 'wsj.com': 'WSJ',
  'apnews.com': 'AP News', 'cnn.com': 'CNN', 'insideevs.com': 'InsideEVs',
  'finance.yahoo.com': 'Yahoo Finance', 'seekingalpha.com': 'Seeking Alpha',
  'marketwatch.com': 'MarketWatch', 'fool.com': 'Motley Fool', 'cnbc.com': 'CNBC',
  'investopedia.com': 'Investopedia', 'benzinga.com': 'Benzinga', 'barrons.com': "Barron's",
  'ft.com': 'Financial Times', 'economist.com': 'The Economist',
  'sec.gov': 'SEC Filing', 'investors.com': "Investor's Business Daily",
  'tipranks.com': 'TipRanks', 'stocktwits.com': 'StockTwits',
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

  const urlHits = timings.fetch_cache_hits ?? 0
  const urlMisses = timings.fetch_cache_misses ?? 0
  const sentHits = timings.sentiment_cache_hits ?? 0
  const sentCalls = timings.sentiment_model_calls ?? 0
  const showCacheStats = (urlHits + urlMisses + sentHits + sentCalls) > 0

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
      {showCacheStats && (
        <div className="timing-cache-stats">
          <span className="timing-cache-label">Cache efficiency</span>
          <span className="timing-cache-pill timing-cache-pill--hit">
            {urlHits} URL {urlHits === 1 ? 'hit' : 'hits'}
          </span>
          <span className="timing-cache-pill timing-cache-pill--miss">
            {urlMisses} URL {urlMisses === 1 ? 'miss' : 'misses'}
          </span>
          <span className="timing-cache-pill timing-cache-pill--hit">
            {sentHits} sentiment {sentHits === 1 ? 'hit' : 'hits'}
          </span>
          <span className="timing-cache-pill timing-cache-pill--miss">
            {sentCalls} model {sentCalls === 1 ? 'call' : 'calls'}
          </span>
        </div>
      )}
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
              <details
                key={fact.domain}
                className="source-fact"
              >
                <summary className="source-fact-header">
                  <img
                    src={`https://www.google.com/s2/favicons?domain=${fact.domain}&sz=14`}
                    alt="" width={14} height={14}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                  <strong className="clip-text" title={fact.domain}>
                    {KNOWN_PROVIDERS[fact.domain] ?? fact.domain.replace(/^www\./, '')}
                  </strong>
                </summary>
                <span style={{ fontSize: 10, color: 'var(--text)', fontFamily: 'var(--mono)' }}>
                  {fact.count} items
                  {fact.credibility !== undefined && (
                    <span style={{ marginLeft: 6, color: fact.credibility >= 0.7 ? 'var(--positive)' : fact.credibility >= 0.4 ? 'var(--neutral)' : 'var(--rog-red)' }}>
                      {Math.round(fact.credibility * 100)}% cred
                    </span>
                  )}
                </span>
                <div className="source-fact-bar">
                  <div style={{ flex: (fact.labels?.positive ?? 0) / dtotal, background: 'var(--positive)' }} />
                  <div style={{ flex: (fact.labels?.neutral  ?? 0) / dtotal, background: 'var(--neutral)' }} />
                  <div style={{ flex: (fact.labels?.negative ?? 0) / dtotal, background: 'var(--rog-red)' }} />
                </div>
                <div className="source-link-list">
                  {(fact.urls?.length ? fact.urls : [fakeUrl]).map(url => (
                    <a key={url} href={url} target="_blank" rel="noreferrer" title={url}>
                      {providerName(url)}
                    </a>
                  ))}
                </div>
              </details>
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
      <h3>Source mix</h3>
      <div className="source-group-list">
        {groups.map(g => <SourceGroupCard key={g.type} group={g} />)}
      </div>
    </div>
  )
}

function ThreadDetail({ thread, runId, onSearchTopic }: {
  thread: ThreadItem
  runId: string
  onSearchTopic?: (topic: string) => void
}) {
  const [chunkState, setChunkState] = useState<{ key: string; chunks: EvidenceChunk[] }>({ key: '', chunks: [] })
  const chunks = chunkState.key === thread.phrase ? chunkState.chunks : []
  const loading = thread.evidence_ids.length > 0 && chunkState.key !== thread.phrase

  useEffect(() => {
    const ids = thread.evidence_ids.slice(0, 8)
    if (!ids.length) return
    let active = true
    Promise.all(ids.map(id => getEvidence(runId, id)))
      .then(results => {
        if (active) setChunkState({ key: thread.phrase, chunks: results.filter(Boolean) })
      })
      .catch(() => {})
    return () => { active = false }
  }, [runId, thread])

  return (
    <aside className="thread-detail">
      <div className="thread-detail-header">
        <div>
          <span className="thread-detail-kicker">Topic detail</span>
          <h4>{thread.phrase}</h4>
        </div>
        <span className={`sentiment-chip sentiment-chip--${thread.dominant_sentiment}`}>
          {thread.dominant_sentiment}
        </span>
      </div>
      <p className="thread-detail-summary">
        {thread.total_mentions} mentions across {thread.source_count} source{thread.source_count !== 1 ? 's' : ''}
        {thread.date_range ? ` from ${thread.date_range[0]} to ${thread.date_range[1]}` : ''}.
      </p>
      <div className="thread-detail-points">
        {thread.sample_snippets.slice(0, 4).map((snippet, idx) => (
          <p key={`${idx}:${snippet}`}>{snippet}</p>
        ))}
      </div>
      <div className="thread-detail-sources">
        <strong>Verifiable sources</strong>
        {loading && <span className="muted">Loading source links…</span>}
        {!loading && chunks.length === 0 && (
          <div className="thread-domain-row">
            {thread.domains.map(domain => <span key={domain} className="thread-domain-tag">{domain}</span>)}
          </div>
        )}
        {chunks.map(chunk => (
          <a key={chunk.id} href={chunk.url} target="_blank" rel="noreferrer" title={chunk.url}>
            <SourceLogo url={chunk.url} />
            <span className={`sentiment-chip sentiment-chip--${chunk.label}`}>{chunk.label}</span>
          </a>
        ))}
      </div>
      <button className="btn-secondary" onClick={() => onSearchTopic?.(thread.search_query)}>
        Search this topic
      </button>
    </aside>
  )
}

function TimelineSummary({ timeline }: { timeline: NonNullable<Report['timeline']> }) {
  if (!timeline.important_dates.length) return null
  return (
    <div className="insight-section">
      <h3>Chronology</h3>
      <div className="timeline-summary">
        <div className="timeline-range">
          <span>Start</span>
          <strong>{timeline.start_date ?? 'unknown'}</strong>
          <span>End</span>
          <strong>{timeline.end_date ?? 'unknown'}</strong>
        </div>
        <p>{timeline.event_summary}</p>
        <div className="timeline-events">
          {timeline.important_dates.map(event => (
            <div className="timeline-event-card" key={`${event.date}:${event.label}`}>
              <time>{event.date}</time>
              <strong>{event.label}</strong>
              <span>{event.description}</span>
              <small>{event.source_count} source{event.source_count !== 1 ? 's' : ''} · {event.certainty}</small>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function FactCheckSection({ factCheck }: { factCheck: NonNullable<Report['fact_check']> }) {
  if (!factCheck.claims.length) return null
  return (
    <div className="insight-section">
      <h3>Fact check</h3>
      <p className="fact-check-summary">{factCheck.summary}</p>
      <div className="claim-list">
        {factCheck.claims.slice(0, 6).map((claim, idx) => (
          <div className={`claim-card${claim.needs_verification ? ' claim-card--verify' : ''}`} key={`${claim.claim}:${idx}`}>
            <div className="claim-card-header">
              <span>{claim.claim_type}</span>
              <strong>{Math.round(claim.confidence * 100)}%</strong>
            </div>
            <p>{claim.claim}</p>
            <small>
              {claim.supporting_domains.slice(0, 3).join(', ') || 'No supporting domains'} · {claim.needs_verification ? 'needs verification' : 'corroborated'}
            </small>
          </div>
        ))}
      </div>
    </div>
  )
}

function UseCaseInsightsSection({ insights }: { insights: NonNullable<Report['use_case_insights']> }) {
  const entries = Object.entries(insights.sections)
  if (!entries.length) return null
  return (
    <div className="insight-section">
      <h3>{insights.use_case.replaceAll('_', ' ')}</h3>
      <div className="decision-grid">
        {entries.map(([key, value]) => (
          <div className="decision-card" key={key}>
            <strong>{key.replaceAll('_', ' ')}</strong>
            <p>{Array.isArray(value) ? value.join(' · ') : value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function ChartDataSection({ chartData }: { chartData: NonNullable<Report['chart_data']> }) {
  const topSources = chartData.source_mix.slice(0, 5)
  const topAspects = chartData.aspect_matrix.slice(0, 6)
  if (!topSources.length && !topAspects.length) return null
  return (
    <div className="insight-section">
      <h3>Decision data</h3>
      <div className="decision-grid">
        {topSources.length > 0 && (
          <div className="decision-card">
            <strong>Source mix</strong>
            {topSources.map(source => (
              <div className="mini-metric" key={source.source_type}>
                <span>{SOURCE_TYPE_LABEL[source.source_type] ?? source.source_type}</span>
                <b>{source.count}</b>
              </div>
            ))}
          </div>
        )}
        {topAspects.length > 0 && (
          <div className="decision-card">
            <strong>Aspect matrix</strong>
            {topAspects.map(aspect => (
              <div className="mini-metric" key={aspect.aspect}>
                <span>{aspect.aspect}</span>
                <b>{aspect.count}</b>
              </div>
            ))}
          </div>
        )}
        {chartData.claim_corroboration.length > 0 && (
          <div className="decision-card">
            <strong>Claim corroboration</strong>
            {chartData.claim_corroboration.slice(0, 4).map((claim, idx) => (
              <div className="mini-metric" key={`${idx}:${claim.claim}`}>
                <span title={claim.claim}>{claim.needs_verification ? 'Needs check' : 'Supported'}</span>
                <b>{claim.supporting_sources}</b>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function SourceTimeSentimentChart({ series }: {
  series: NonNullable<Report['chart_data']>['sentiment_over_time']
}) {
  const rows = series.filter(row => row.date !== 'unknown').slice(-18)
  const maxTotal = Math.max(1, ...rows.map(row => row.total))
  if (!rows.length) return null
  return (
    <div className="insight-section">
      <h3>Sentiment over source time</h3>
      <div className="source-time-chart" role="img" aria-label="Sentiment by source publication or mentioned date">
        {rows.map(row => {
          const pos = row.total ? row.positive / row.total : 0
          const neu = row.total ? row.neutral / row.total : 0
          const neg = row.total ? row.negative / row.total : 0
          return (
            <div className="source-time-row" key={row.date}>
              <time>{row.date}</time>
              <div className="source-time-stack" style={{ width: `${Math.max(8, (row.total / maxTotal) * 100)}%` }}>
                <span style={{ flex: pos, background: 'var(--positive)' }} />
                <span style={{ flex: neu, background: 'var(--neutral)' }} />
                <span style={{ flex: neg, background: 'var(--rog-red)' }} />
              </div>
              <b>{row.total}</b>
              <small>{row.certainty ?? 'source date'}</small>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function LocationSentimentMap({ locations }: {
  locations: NonNullable<NonNullable<Report['chart_data']>['location_sentiment']>
}) {
  const [selected, setSelected] = useState(locations[0]?.location ?? '')
  const points = locations.map(location => {
    const x = ((location.lon + 180) / 360) * 1000
    const y = ((90 - location.lat) / 180) * 500
    const dominant = location.negative > location.positive && location.negative >= location.neutral
      ? 'negative'
      : location.positive >= location.neutral ? 'positive' : 'neutral'
    return { ...location, x, y, dominant }
  })
  if (!points.length) return null
  const minX = Math.min(...points.map(p => p.x))
  const maxX = Math.max(...points.map(p => p.x))
  const minY = Math.min(...points.map(p => p.y))
  const maxY = Math.max(...points.map(p => p.y))
  const pad = 120
  const viewBox = [
    Math.max(0, minX - pad),
    Math.max(0, minY - pad),
    Math.min(1000, maxX + pad) - Math.max(0, minX - pad),
    Math.min(500, maxY + pad) - Math.max(0, minY - pad),
  ].join(' ')
  const selectedPoint = points.find(point => point.location === selected) ?? points[0]

  return (
    <div className="insight-section">
      <h3>Sentiment by location</h3>
      <div className="location-map-layout">
        <svg className="location-map" viewBox={viewBox} role="img" aria-label="Geographic sentiment map">
          {[...Array(7)].map((_, i) => <line key={`lat-${i}`} x1="0" x2="1000" y1={i * 83.3} y2={i * 83.3} />)}
          {[...Array(9)].map((_, i) => <line key={`lon-${i}`} x1={i * 125} x2={i * 125} y1="0" y2="500" />)}
          <path d="M80 210 C170 150 260 165 330 210 C390 245 470 230 545 190 C650 130 750 170 850 215 C910 240 950 270 930 310 C880 370 760 345 680 315 C575 278 480 300 385 335 C260 380 130 340 80 290 Z" />
          {points.map(point => (
            <g
              key={point.location}
              className={`location-point location-point--${point.dominant}`}
              role="button"
              tabIndex={0}
              aria-label={point.location}
              onClick={() => setSelected(point.location)}
              onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') setSelected(point.location) }}
            >
              <circle cx={point.x} cy={point.y} r={Math.max(7, Math.min(22, 6 + point.total * 2))} />
              <text x={point.x + 10} y={point.y - 8}>{point.location}</text>
            </g>
          ))}
        </svg>
        <aside className="location-map-detail">
          <strong>{selectedPoint.location}</strong>
          <span className={`sentiment-chip sentiment-chip--${selectedPoint.dominant}`}>{selectedPoint.dominant}</span>
          <p>{selectedPoint.total} mapped item{selectedPoint.total !== 1 ? 's' : ''} · {selectedPoint.certainty === 'mentioned' ? 'location mentioned in text' : 'inferred from source domain'}</p>
          <div className="mini-metric"><span>Positive</span><b>{selectedPoint.positive}</b></div>
          <div className="mini-metric"><span>Neutral</span><b>{selectedPoint.neutral}</b></div>
          <div className="mini-metric"><span>Negative</span><b>{selectedPoint.negative}</b></div>
          {selectedPoint.source_domains.length > 0 && (
            <small>{selectedPoint.source_domains.slice(0, 4).join(', ')}</small>
          )}
        </aside>
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

        {chunk.related && (
          <div className="snippet-related">
            {chunk.related.timeline_events.length > 0 && (
              <div>
                <h4>Related dates</h4>
                <p>{chunk.related.timeline_events.map(event => event.date).join(', ')}</p>
              </div>
            )}
            {chunk.related.claims.length > 0 && (
              <div>
                <h4>Related claims</h4>
                <p>{chunk.related.claims.map(claim => claim.claim).join(' · ')}</p>
              </div>
            )}
            {chunk.related.aspects.length > 0 && (
              <div>
                <h4>Related topics</h4>
                <p>{chunk.related.aspects.map(aspect => aspect.name).join(', ')}</p>
              </div>
            )}
          </div>
        )}

        <a href={chunk.url} target="_blank" rel="noreferrer" className="view-source-link">
          View full source ↗
        </a>
      </div>
    </div>
  )
}

// ── Report tabs ────────────────────────────────────────────────────────

type ReportTab = 'summary' | 'topics' | 'timeline' | 'evidence' | 'claims' | 'graph' | 'performance'

const REPORT_TABS: Array<{ id: ReportTab; label: string }> = [
  { id: 'summary', label: 'Summary' },
  { id: 'topics', label: 'Topics' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'claims', label: 'Claims' },
  { id: 'graph', label: 'Graph' },
  { id: 'performance', label: 'Performance' },
]

// ── Main component ────────────────────────────────────────────────────────

export function ReportView({ runId, topic, report, onSearchTopic }: Props) {
  const [activeChunk, setActiveChunk] = useState<EvidenceChunk | null>(null)
  const [loadingChunk, setLoadingChunk] = useState(false)
  const [highlightedId, setHighlightedId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<ReportTab>('summary')
  const [selectedThread, setSelectedThread] = useState<ThreadItem | null>(null)
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
    timings, aspects, source_facts, timeline, fact_check, threads, use_case_insights, chart_data, graph, impacts, reasons, arguments: args,
  } = report

  function exportReport(format: 'json' | 'csv' | 'markdown') {
    const slug = topic.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'report'
    if (format === 'json') {
      downloadText(`${slug}.json`, JSON.stringify(report, null, 2), 'application/json')
    } else if (format === 'csv') {
      const rows = [
        ['section', 'item', 'value'],
        ['overall', 'positive', String(overall.positive)],
        ['overall', 'neutral', String(overall.neutral)],
        ['overall', 'negative', String(overall.negative)],
        ...Object.entries(by_source).map(([source, stats]) => ['source', source, String(stats?.count ?? 0)]),
        ...(report.aspects ?? []).map(aspect => ['aspect', aspect.name, `${aspect.sentiment}:${aspect.count}`]),
        ...(report.fact_check?.claims ?? []).map(claim => ['claim', claim.claim_type, claim.claim]),
      ]
      downloadText(`${slug}.csv`, rows.map(csvRow).join('\n'), 'text/csv')
    } else {
      const markdown = [
        `# ${topic}`,
        '',
        `Items analyzed: ${overall.total}`,
        `Positive: ${pct(overall.positive)} · Neutral: ${pct(overall.neutral)} · Negative: ${pct(overall.negative)}`,
        '',
        '## Summary',
        narrative,
        '',
        '## Key themes',
        themes.map(theme => `- ${theme}`).join('\n') || '- None',
        '',
        '## Chronology',
        report.timeline?.event_summary ?? 'No chronology available.',
        '',
        '## Fact check',
        report.fact_check?.summary ?? 'No factual claims extracted.',
      ].join('\n')
      downloadText(`${slug}.md`, markdown, 'text/markdown')
    }
  }

  return (
    <section className="panel" aria-label="Report">
      <div className="report-header">
        <h2>Report {timings?.total_ms != null && <span className="duration-badge">{fmtDuration(timings.total_ms)}</span>}</h2>
        <div className="export-actions">
          <button className="btn-secondary" onClick={() => { navigator.clipboard.writeText(`# ${topic}\n\n${narrative}\n\nPositive: ${pct(overall.positive)} · Neutral: ${pct(overall.neutral)} · Negative: ${pct(overall.negative)}\n\nThemes: ${themes.join(', ')}\n\nAnalyzed ${overall.total} items across ${Object.keys(by_source).filter(k => (by_source[k]?.count ?? 0) > 0).length} source types.`).catch(() => {}) }}>📋 Copy</button>
          <button className="btn-secondary" onClick={() => exportReport('json')}>JSON</button>
          <button className="btn-secondary" onClick={() => exportReport('csv')}>CSV</button>
          <button className="btn-secondary" onClick={() => exportReport('markdown')}>MD</button>
        </div>
      </div>

      {/* ── Report tabs ── */}
      <nav className="report-tabs" role="tablist" aria-label="Report sections">
        {REPORT_TABS.map(tab => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`report-tab${activeTab === tab.id ? ' report-tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* ── Summary tab ── */}
      {activeTab === 'summary' && (
        <div className="report-tab-panel" role="tabpanel">
          {/* Executive summary card */}
          <div className="exec-summary">
            <div className="exec-summary-score">
              <span className="exec-summary-big">{Math.round(overall.positive * 100)}%</span>
              <span className="exec-summary-label">positive</span>
            </div>
            <div className="exec-summary-body">
              <p>{narrative.slice(0, 200)}{narrative.length > 200 ? '…' : ''}</p>
              <div className="exec-summary-meta">
                <span>{overall.total} sources analyzed</span>
                {themes.length > 0 && <span>Top: {themes.slice(0, 3).join(', ')}</span>}
                {timings && <span>Completed in {fmtDuration(timings.total_ms ?? 0)}</span>}
              </div>
            </div>
          </div>

          <div className="sentiment-bars">
            <SentimentBar label="Positive" value={overall.positive} color="var(--positive)" />
            <SentimentBar label="Neutral"  value={overall.neutral}  color="var(--neutral)" />
            <SentimentBar label="Negative" value={overall.negative} color="var(--rog-red)" />
            <p className="muted" style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>
              {overall.total} items analyzed
            </p>
          </div>

          {use_case_insights && <UseCaseInsightsSection insights={use_case_insights} />}

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

          {chart_data?.sentiment_over_time && (
            <SourceTimeSentimentChart series={chart_data.sentiment_over_time} />
          )}

          {chart_data?.location_sentiment && chart_data.location_sentiment.length > 0 && (
            <LocationSentimentMap locations={chart_data.location_sentiment} />
          )}

          {chart_data && <ChartDataSection chartData={chart_data} />}
        </div>
      )}

      {/* ── Topics tab ── */}
      {activeTab === 'topics' && (
        <div className="report-tab-panel" role="tabpanel">
          {threads && threads.length > 0 ? (
            <div className="insight-section">
              <h3>Recurring topic threads</h3>
              <div className="thread-layout">
                <div className="thread-grid">
                  {threads.map(thread => {
                    const isSelected = (selectedThread ?? threads[0]).phrase === thread.phrase
                    return (
                      <button
                        type="button"
                        className={`thread-card${isSelected ? ' thread-card--selected' : ''}`}
                        key={thread.phrase}
                        onClick={() => setSelectedThread(thread)}
                        title={thread.search_query}
                      >
                        <div className="thread-card-header">
                          <strong className="clip-text">{thread.phrase}</strong>
                          <span className={`sentiment-chip sentiment-chip--${thread.dominant_sentiment}`}>
                            {thread.dominant_sentiment}
                          </span>
                        </div>
                        <div className="thread-card-bar">
                          <div style={{ flex: thread.positive, background: 'var(--positive)' }} />
                          <div style={{ flex: thread.neutral, background: 'var(--neutral)' }} />
                          <div style={{ flex: thread.negative, background: 'var(--rog-red)' }} />
                        </div>
                        <div className="thread-card-meta">
                          <span>{thread.evidence_count} mentions</span>
                          <span>{thread.source_count} sources</span>
                          {thread.date_range && (
                            <span>{thread.date_range[0]} → {thread.date_range[1]}</span>
                          )}
                        </div>
                        {thread.sample_snippets.length > 0 && (
                          <div className="thread-card-snippets">
                            {thread.sample_snippets.slice(0, 2).map((snip, i) => (
                              <p key={i} className="clip-text">"{snip}"</p>
                            ))}
                          </div>
                        )}
                        <div className="thread-card-domains">
                          {thread.domains.map(d => (
                            <span key={d} className="thread-domain-tag">{d}</span>
                          ))}
                        </div>
                      </button>
                    )
                  })}
                </div>
                <ThreadDetail
                  thread={selectedThread ?? threads[0]}
                  runId={runId}
                  onSearchTopic={onSearchTopic}
                />
              </div>
            </div>
          ) : (
            <p className="empty-tab-msg">No recurring topic threads extracted. More evidence may be needed.</p>
          )}
        </div>
      )}

      {/* ── Timeline tab ── */}
      {activeTab === 'timeline' && (
        <div className="report-tab-panel" role="tabpanel">
          {timeline ? <TimelineSummary timeline={timeline} /> : <p className="empty-tab-msg">No chronology data available for this run.</p>}
        </div>
      )}

      {/* ── Evidence tab ── */}
      {activeTab === 'evidence' && (
        <div className="report-tab-panel" role="tabpanel">
          {source_facts && source_facts.length > 0 && <SourceFacts facts={source_facts} />}
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
          {aspects && aspects.length > 0 && <AspectSummary aspects={aspects} />}
        </div>
      )}

      {/* ── Claims tab ── */}
      {activeTab === 'claims' && (
        <div className="report-tab-panel" role="tabpanel">
          {fact_check ? <FactCheckSection factCheck={fact_check} /> : <p className="empty-tab-msg">No claims extracted for this run.</p>}
        </div>
      )}

      {/* ── Graph tab ── */}
      {activeTab === 'graph' && (
        <div className="report-tab-panel" role="tabpanel">
          {graph && graph.nodes.length > 0 ? (
            <ForceGraph graph={graph} runId={runId} onNodeClick={handleGraphNodeClick} />
          ) : (
            <p className="empty-tab-msg">No graph data available for this run.</p>
          )}
        </div>
      )}

      {/* ── Performance tab ── */}
      {activeTab === 'performance' && (
        <div className="report-tab-panel" role="tabpanel">
          {timings ? (
            <>
              <TimingSummary timings={timings} />
              <div style={{ marginTop: 16, padding: '12px 16px', background: 'var(--panel)', borderRadius: 6 }}>
                <h4 style={{ margin: '0 0 8px' }}>Run metadata</h4>
                <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text)', display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 12px' }}>
                  <span>Topic:</span><span>{topic}</span>
                  {report.metadata?.research_depth && <><span>Depth:</span><span>{report.metadata.research_depth}</span></>}
                  {report.metadata?.use_case && <><span>Use case:</span><span>{report.metadata.use_case}</span></>}
                  <span>Items:</span><span>{overall.total}</span>
                </div>
              </div>
            </>
          ) : (
            <p className="empty-tab-msg">No performance data available.</p>
          )}
        </div>
      )}

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
function csvRow(row: string[]): string {
  return row.map(cell => `"${cell.replaceAll('"', '""')}"`).join(',')
}
function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
