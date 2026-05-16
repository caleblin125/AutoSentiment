import { useEffect, useRef, useState } from 'react'
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts'
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
import { providerName, faviconUrl } from '../lib/providers'
import { ErrorBoundary } from './ErrorBoundary'
import { EvidenceModal } from './EvidenceModal'
import { FactCheckSection } from './ClaimsSection'
import { SourceFacts } from './SourceFacts'
import { SOURCE_TYPE_LABEL } from '../lib/providers'
import { ForceGraph } from './ForceGraph'

interface Props { runId: string; topic: string; report: Report; onSearchTopic?: (topic: string) => void; autoScroll?: boolean }

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
        <button className="btn-secondary btn-secondary--compact"
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

function SentimentBar({ label, value, variant }: { label: string; value: number; variant: 'pos' | 'neu' | 'neg' }) {
  const [displayed, setDisplayed] = useState(0)
  const rafRef = useRef(0)
  // Track the current rendered value in a ref so the effect can read it without
  // needing to include `displayed` in the dependency array (which would
  // restart the animation on every frame).
  const currentRef = useRef(0)

  useEffect(() => {
    const from = currentRef.current
    const target = value
    const duration = 700  // ms
    const start = performance.now()

    const animate = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      // Ease-out cubic: decelerates into the final value
      const eased = 1 - (1 - t) ** 3
      const next = from + (target - from) * eased
      currentRef.current = next
      setDisplayed(next)
      if (t < 1) rafRef.current = requestAnimationFrame(animate)
    }
    rafRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(rafRef.current)
  }, [value]) // re-animates whenever the report data changes

  return (
    <div className="sentiment-row">
      <div className="sentiment-row__label">
        <span>{label}</span>
        <strong className="mono">{pct(displayed)}</strong>
      </div>
      <div className="sentiment-track">
        <div className={`sentiment-fill sentiment-fill--${variant}`} style={{ width: pct(displayed) }} />
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
                <span className={`impact-text impact-text--${im.direction}`}>
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
          <div className={`analysis-card${args.length > 2 ? ' analysis-card--wide' : ''}`}>
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
  // Deduplicate by date+label to prevent repeated events from expand merges
  const seen = new Set<string>()
  const uniqueDates = timeline.important_dates.filter(event => {
    const key = `${event.date}:${event.label?.slice(0, 40)}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })

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
          {uniqueDates.map(event => (
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
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const rows = series.filter(row => row.date !== 'unknown').slice(-20)
  if (!rows.length) return null

  const maxTotal = Math.max(1, ...rows.map(r => r.total))
  const SVG_W = 620
  const SVG_H = 120
  const PAD_L = 8
  const PAD_R = 8
  const PAD_T = 8
  const PAD_B = 28

  const plotW = SVG_W - PAD_L - PAD_R
  const plotH = SVG_H - PAD_T - PAD_B
  const step = rows.length > 1 ? plotW / (rows.length - 1) : plotW

  // Build stacked area path data
  const posPoints = rows.map((r, i) => ({ x: PAD_L + i * step, y: PAD_T + plotH - (r.total ? r.positive / r.total : 0) * plotH }))
  const negPoints = rows.map((r, i) => ({ x: PAD_L + i * step, y: PAD_T + plotH - (r.total ? r.negative / r.total : 0) * plotH }))
  const baseline = `L ${PAD_L + (rows.length - 1) * step},${PAD_T + plotH} L ${PAD_L},${PAD_T + plotH}`

  const posPath = posPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x},${p.y}`).join(' ') + ` ${baseline} Z`
  const negPath = negPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x},${p.y}`).join(' ') + ` ${baseline} Z`

  const selectedRow = rows.find(r => r.date === selectedDate) ?? null

  return (
    <div className="insight-section">
      <h3>Sentiment over source time</h3>
      <div className="source-timeline-wrap">
        <svg
          className="source-timeline-svg"
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          aria-label="Sentiment over source dates"
        >
          <defs>
            <linearGradient id="grad-pos" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--positive)" stopOpacity="0.55" />
              <stop offset="100%" stopColor="var(--positive)" stopOpacity="0.08" />
            </linearGradient>
            <linearGradient id="grad-neg" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--rog-red)" stopOpacity="0.4" />
              <stop offset="100%" stopColor="var(--rog-red)" stopOpacity="0.05" />
            </linearGradient>
          </defs>

          {/* Baseline */}
          <line x1={PAD_L} y1={PAD_T + plotH} x2={PAD_L + plotW} y2={PAD_T + plotH}
            stroke="var(--border)" strokeWidth={1} />

          {/* Positive area */}
          <path d={posPath} fill="url(#grad-pos)" />
          {/* Positive line */}
          <polyline points={posPoints.map(p => `${p.x},${p.y}`).join(' ')}
            fill="none" stroke="var(--positive)" strokeWidth={1.5} strokeLinejoin="round" />

          {/* Negative area */}
          <path d={negPath} fill="url(#grad-neg)" />
          {/* Negative line */}
          <polyline points={negPoints.map(p => `${p.x},${p.y}`).join(' ')}
            fill="none" stroke="var(--rog-red)" strokeWidth={1.5} strokeLinejoin="round" />

          {/* Data points + interaction */}
          {rows.map((row, i) => {
            const x = PAD_L + i * step
            const yPos = PAD_T + plotH - (row.total ? row.positive / row.total : 0) * plotH
            const r = Math.max(3, Math.min(7, 2 + (row.total / maxTotal) * 5))
            const isSelected = row.date === selectedDate
            return (
              <g key={row.date} className="source-timeline-point" style={{ cursor: 'pointer' }}
                onClick={() => setSelectedDate(d => d === row.date ? null : row.date)}>
                <rect x={x - 10} y={PAD_T} width={20} height={plotH} fill="transparent" />
                <circle cx={x} cy={yPos} r={isSelected ? r + 2 : r}
                  fill={isSelected ? 'var(--rog-cyan)' : 'var(--positive)'}
                  stroke="var(--panel)" strokeWidth={1.5} />
                {/* X-axis label (every 3rd for space) */}
                {(i % Math.max(1, Math.floor(rows.length / 7)) === 0 || i === rows.length - 1) && (
                  <text x={x} y={SVG_H - 6} textAnchor="middle" className="source-timeline-label">
                    {row.date.slice(5)}
                  </text>
                )}
              </g>
            )
          })}
        </svg>

        {selectedRow && (
          <div className="source-timeline-tooltip">
            <strong>{selectedRow.date}</strong>
            <div className="source-timeline-bars">
              <div><span className="sent-label--pos">pos</span><b>{selectedRow.positive}</b></div>
              <div><span className="sent-label--neu">neu</span><b>{selectedRow.neutral}</b></div>
              <div><span className="sent-label--neg">neg</span><b>{selectedRow.negative}</b></div>
              <div><span>total</span><b>{selectedRow.total}</b></div>
            </div>
            <small>{selectedRow.certainty ?? 'source date'}</small>
            <button className="source-timeline-close" onClick={() => setSelectedDate(null)}>✕</button>
          </div>
        )}

        <div className="source-timeline-legend">
          <span><span className="stle-dot stle-dot--pos" /> Positive</span>
          <span><span className="stle-dot stle-dot--neg" /> Negative</span>
          <span className="stle-hint">Click points to inspect</span>
        </div>
      </div>
    </div>
  )
}

// Simplified world continent paths (equirectangular, 1000×500)
// Derived from public domain Natural Earth 110m data
const CONTINENT_PATHS = [
  // North America
  "M42,69 L97,83 L120,70 L156,114 L156,128 L175,161 L194,183 L250,170 L258,192 L244,208 L236,208 L250,215 L275,185 L278,183 L286,153 L306,128 L333,128 L353,103 L356,89 L322,78 L278,78 L244,50 L167,56 L111,75 L56,56 Z",
  // Greenland
  "M372,50 L378,83 L356,89 L353,75 L375,17 L444,14 L450,36 L436,50 Z",
  // South America
  "M275,181 L278,228 L286,228 L328,219 L403,264 L403,272 L389,325 L347,344 L319,403 L311,406 L292,389 L278,264 L278,250 L275,181 Z",
  // Europe (simplified)
  "M475,147 L486,128 L472,106 L478,97 L486,89 L500,89 L503,108 L511,108 L528,100 L522,92 L558,94 L556,100 L567,92 L583,83 L581,69 L572,50 L569,53 L550,100 L561,147 L544,144 L508,131 L475,147 Z",
  // Africa
  "M461,150 L453,211 L458,225 L464,239 L508,264 L533,264 L533,311 L547,347 L550,347 L542,331 L597,319 L614,264 L642,217 L617,217 L594,164 L569,158 L525,147 L508,131 L475,147 L461,150 Z",
  // Asia (West + Central)
  "M575,147 L581,136 L589,144 L622,139 L633,131 L658,147 L683,181 L667,69 L633,61 L583,83 L575,147 Z",
  // South/Southeast Asia
  "M683,181 L722,228 L753,189 L778,222 L800,222 L806,208 L839,167 L858,147 L861,69 L839,56 L800,72 L722,189 L683,181 Z",
  // East Asia + Russia Pacific
  "M858,147 L864,164 L892,125 L897,106 L950,106 L950,75 L906,56 L861,69 L858,147 Z",
  // Russia/Siberia
  "M583,83 L583,50 L667,61 L703,61 L778,36 L861,47 L897,106 L861,69 L839,56 L800,72 L722,189 L667,69 L633,61 L583,83 Z",
  // Australia
  "M817,311 L861,283 L878,283 L903,281 L925,322 L917,353 L906,356 L889,356 L869,342 L847,339 L819,344 L817,311 Z",
  // Japan
  "M864,156 L869,147 L878,150 L875,158 Z",
  // UK/Ireland
  "M472,106 L478,97 L486,89 L486,108 L475,111 L472,106 Z",
]

function LocationSentimentMap({ locations }: {
  locations: NonNullable<NonNullable<Report['chart_data']>['location_sentiment']>
}) {
  const [selected, setSelected] = useState(locations[0]?.location ?? '')
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [isMapPanning, setIsMapPanning] = useState(false)
  const panRef = useRef<{ sx: number; sy: number; sp: { x: number; y: number } } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  // Non-passive wheel listener so preventDefault() stops page scroll.
  // Must be before any early return to satisfy the Rules of Hooks.
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      setZoom(z => Math.max(0.5, Math.min(6, z * (e.deltaY > 0 ? 0.85 : 1.18))))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  const points = locations.map(location => {
    const x = ((location.lon + 180) / 360) * 1000
    const y = ((90 - location.lat) / 180) * 500
    const dominant = location.negative > location.positive && location.negative >= location.neutral
      ? 'negative' : location.positive >= location.neutral ? 'positive' : 'neutral'
    return { ...location, x, y, dominant }
  })
  if (!points.length) return null

  const selectedPoint = points.find(p => p.location === selected) ?? points[0]

  function handleSvgMouseDown(e: React.MouseEvent<SVGSVGElement>) {
    if (e.button !== 0) return
    if ((e.target as SVGElement).closest('.location-point')) return
    panRef.current = { sx: e.clientX, sy: e.clientY, sp: pan }
    setIsMapPanning(true)
    const onMove = (me: MouseEvent) => {
      if (!panRef.current) return
      setPan({ x: panRef.current.sp.x + (me.clientX - panRef.current.sx) / zoom, y: panRef.current.sp.y + (me.clientY - panRef.current.sy) / zoom })
    }
    const onUp = () => { panRef.current = null; setIsMapPanning(false); window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return (
    <div className="insight-section">
      <h3>Sentiment by location</h3>
      <div className="location-map-controls">
        <button className="btn-secondary graph-ctrl-btn" onClick={() => setZoom(z => Math.min(6, z * 1.3))} title="Zoom in">+</button>
        <button className="btn-secondary graph-ctrl-btn" onClick={() => setZoom(z => Math.max(0.5, z * 0.77))} title="Zoom out">−</button>
        <button className="btn-secondary graph-ctrl-btn" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }} title="Reset view">⟳</button>
        <span className="map-hint">Scroll to zoom · Drag to pan · Click to inspect</span>
      </div>
      <div className="location-map-layout">
        <svg
          ref={svgRef}
          className="location-map"
          viewBox={`${-pan.x} ${-pan.y} ${1000 / zoom} ${500 / zoom}`}
          role="img"
          aria-label="Geographic sentiment map"
          onMouseDown={handleSvgMouseDown}
          style={{ cursor: isMapPanning ? 'grabbing' : 'grab' }}
        >
          {/* Grid lines */}
          {[...Array(7)].map((_, i) => <line key={`lat-${i}`} x1="0" x2="1000" y1={i * 83.3} y2={i * 83.3} />)}
          {[...Array(9)].map((_, i) => <line key={`lon-${i}`} x1={i * 125} x2={i * 125} y1="0" y2="500" />)}
          {/* World land masses */}
          {CONTINENT_PATHS.map((d, i) => <path key={i} d={d} className="map-landmass" />)}
          {/* Sentiment points */}
          {points.map(point => (
            <g
              key={point.location}
              className={`location-point location-point--${point.dominant}`}
              role="button"
              tabIndex={0}
              aria-label={point.location}
              onClick={() => setSelected(point.location)}
              onKeyDown={ev => { if (ev.key === 'Enter' || ev.key === ' ') setSelected(point.location) }}
            >
              <circle
                cx={point.x} cy={point.y}
                r={Math.max(6, Math.min(18, 5 + point.total * 1.5)) / zoom}
                strokeWidth={2 / zoom}
                className={point.location === selected ? 'location-point-selected' : ''}
              />
              <text x={point.x + 11 / zoom} y={point.y - 7 / zoom} fontSize={11 / zoom} className="map-location-label">
                {point.location}
              </text>
            </g>
          ))}
        </svg>
        <aside className="location-map-detail">
          <strong>{selectedPoint.location}</strong>
          <span className={`sentiment-chip sentiment-chip--${selectedPoint.dominant}`}>{selectedPoint.dominant}</span>
          <p>{selectedPoint.total} mapped item{selectedPoint.total !== 1 ? 's' : ''}</p>
          <small className="map-certainty">{selectedPoint.certainty === 'mentioned' ? 'mentioned in text' : 'inferred from domain'}</small>
          <div className="mini-metric"><span>Positive</span><b className="sent-val--pos">{selectedPoint.positive}</b></div>
          <div className="mini-metric"><span>Neutral</span><b>{selectedPoint.neutral}</b></div>
          <div className="mini-metric"><span>Negative</span><b className="sent-val--neg">{selectedPoint.negative}</b></div>
          {(selectedPoint.source_domains ?? []).length > 0 && (
            <div className="location-source-links">
              {(selectedPoint.source_domains ?? []).slice(0, 4).map((d: string) => (
                <a key={d} href={`https://${d}`} target="_blank" rel="noreferrer" className="location-domain-link">
                  <img src={`https://www.google.com/s2/favicons?domain=${d}&sz=12`} alt="" width={12} height={12}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                  {d}
                </a>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

// ── Quotes ────────────────────────────────────────────────────────────────

const QUOTES_INITIAL = 12

function QuoteList({ title, quotes, onCite, highlightedId, sectionRef }: {
  title: string
  quotes: Quote[]
  onCite: (q: Quote) => void
  highlightedId?: string | null
  sectionRef?: React.RefObject<HTMLDivElement | null>
}) {
  const [showAll, setShowAll] = useState(false)
  if (!quotes.length) return null
  const visible = showAll ? quotes : quotes.slice(0, QUOTES_INITIAL)
  const hidden = quotes.length - visible.length
  return (
    <div className="quote-list" ref={sectionRef}>
      <h3>{title} <span className="quote-count-badge">{quotes.length}</span></h3>
      <div className="quote-grid">
        {visible.map(q => (
          <article
            className={`quote-card${highlightedId === q.evidence_id ? ' quote-card--highlighted' : ''}`}
            key={q.evidence_id}
          >
            <p title={q.summary}>"{q.summary}"</p>
            <div className="quote-card-footer">
              <a href={q.url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>
                <SourceLogo url={q.url} />
              </a>
              <div className="quote-actions">
                {q.confidence != null && (
                  <span
                    className="confidence-badge"
                    title={`Model confidence: ${Math.round(q.confidence * 100)}%`}
                    style={{ opacity: 0.55 + q.confidence * 0.45 }}
                  >
                    {Math.round(q.confidence * 100)}%
                  </span>
                )}
                <a href={q.url} target="_blank" rel="noreferrer" className="cite-btn cite-btn--link" title="Open source in new tab">
                  ↗ source
                </a>
                <button className="cite-btn" onClick={() => onCite(q)}>inspect</button>
              </div>
            </div>
          </article>
        ))}
      </div>
      {hidden > 0 && (
        <button className="show-all-btn" onClick={() => setShowAll(true)}>
          Show {hidden} more
        </button>
      )}
      {showAll && quotes.length > QUOTES_INITIAL && (
        <button className="show-all-btn" onClick={() => setShowAll(false)}>
          Show less
        </button>
      )}
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

export function ReportView({ runId, topic, report, onSearchTopic, autoScroll }: Props) {
  const [activeChunk, setActiveChunk] = useState<EvidenceChunk | null>(null)
  const [loadingChunk, setLoadingChunk] = useState(false)
  const [highlightedId, setHighlightedId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<ReportTab>('summary')
  const [selectedThread, setSelectedThread] = useState<ThreadItem | null>(null)
  const posRef = useRef<HTMLDivElement | null>(null)
  const negRef = useRef<HTMLDivElement | null>(null)
  const sectionRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (autoScroll && sectionRef.current) {
      const id = requestAnimationFrame(() =>
        sectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      )
      return () => cancelAnimationFrame(id)
    }
  }, [autoScroll])

  // Report tab keyboard shortcuts (keys 1-7)
  useKeyboardShortcuts({
    Tab1: () => setActiveTab('summary'), Tab2: () => setActiveTab('topics'),
    Tab3: () => setActiveTab('timeline'), Tab4: () => setActiveTab('evidence'),
    Tab5: () => setActiveTab('claims'), Tab6: () => setActiveTab('graph'),
    Tab7: () => setActiveTab('performance'),
    Escape: () => { setActiveChunk(null); setSelectedThread(null) },
  })

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

  const [summaryExpanded, setSummaryExpanded] = useState(false)
  const SUMMARY_TRUNCATE = 240

  return (
    <section className="panel" aria-label="Report" ref={sectionRef}>
      <div className="report-header">
        <h2>Report {timings?.total_ms != null && <span className="duration-badge">{fmtDuration(timings.total_ms)}</span>}</h2>
        <div className="export-actions">
          <button className="btn-secondary" onClick={() => {
            const url = `${window.location.origin}${window.location.pathname}?run=${runId}`
            navigator.clipboard.writeText(url).catch(() => {})
          }} title="Copy shareable link">🔗 Link</button>
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
              <p>
                {summaryExpanded || narrative.length <= SUMMARY_TRUNCATE
                  ? narrative
                  : narrative.slice(0, SUMMARY_TRUNCATE) + '…'}
                {narrative.length > SUMMARY_TRUNCATE && (
                  <button className="summary-expand-btn" onClick={() => setSummaryExpanded(x => !x)}>
                    {summaryExpanded ? ' Show less' : ' Read more'}
                  </button>
                )}
              </p>
              <div className="exec-summary-meta">
                <span>{overall.total} sources analyzed</span>
                {themes.length > 0 && <span>Top: {themes.slice(0, 3).join(', ')}</span>}
                {timings && <span>Completed in {fmtDuration(timings.total_ms ?? 0)}</span>}
              </div>
            </div>
          </div>

          <div className="sentiment-bars">
            <SentimentBar label="Positive" value={overall.positive} variant="pos" />
            <SentimentBar label="Neutral"  value={overall.neutral}  variant="neu" />
            <SentimentBar label="Negative" value={overall.negative} variant="neg" />
            <p className="muted mono text-xs">{overall.total} items analyzed</p>
          </div>

          {use_case_insights && <UseCaseInsightsSection insights={use_case_insights} />}

          {themes.length > 0 && (
            <div className="themes">
              <strong className="themes-label">Key themes:</strong>{' '}
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
                          <div className="thread-bar-pos" style={{ flex: thread.positive }} />
                          <div className="thread-bar-neu" style={{ flex: thread.neutral }} />
                          <div className="thread-bar-neg" style={{ flex: thread.negative }} />
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
          {fact_check
            ? <FactCheckSection factCheck={fact_check} onCite={async (id) => { try { setActiveChunk(await getEvidence(runId, id)) } catch { /* best-effort */ } }} />
            : <p className="empty-tab-msg">No claims extracted for this run.</p>}
        </div>
      )}

      {/* ── Graph tab ── */}
      {activeTab === 'graph' && (
        <div className="report-tab-panel" role="tabpanel">
          {graph && graph.nodes.length > 0 ? (
            <ErrorBoundary>
              <ForceGraph graph={graph} runId={runId} onNodeClick={handleGraphNodeClick} />
            </ErrorBoundary>
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
              <div className="run-metadata-box">
                <h4 className="run-metadata-title">Run metadata</h4>
                <div className="run-metadata-grid">
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
        <div className="loading-chunk-wrap">
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
