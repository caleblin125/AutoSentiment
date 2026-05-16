/**
 * Live timeline of SSE events.
 *
 * All url_fetched events are merged into a single "fetch batch" row that
 * shows a progress counter and advances as URLs complete.
 */
import { Fragment, useState } from 'react'
import type { SSEEvent } from '../lib/api'

interface Props { events: SSEEvent[]; status: string }

// Domains considered highly credible for the credibility badge.
const HIGH_CREDIBILITY = new Set([
  'reuters.com', 'apnews.com', 'bbc.com', 'bbc.co.uk', 'nytimes.com',
  'wsj.com', 'bloomberg.com', 'ft.com', 'theguardian.com', 'economist.com',
  'nature.com', 'science.org', 'sciencedirect.com', 'pubmed.ncbi.nlm.nih.gov',
  'gov', 'who.int', 'cdc.gov', 'europa.eu', 'un.org',
  'mit.edu', 'stanford.edu', 'harvard.edu', 'ieee.org', 'acm.org',
])

function isHighCredibility(domain: string): boolean {
  return HIGH_CREDIBILITY.has(domain) || [...HIGH_CREDIBILITY].some(d => domain.endsWith(`.${d}`))
}

const KNOWN_PROVIDERS: Record<string, string> = {
  'reddit.com': 'Reddit', 'news.ycombinator.com': 'HN', 'youtube.com': 'YouTube',
  'x.com': 'X', 'twitter.com': 'X', 'threads.net': 'Threads', 'quora.com': 'Quora',
  'facebook.com': 'Facebook', 'linkedin.com': 'LinkedIn', 'tiktok.com': 'TikTok',
  'nytimes.com': 'NYT', 'bbc.com': 'BBC', 'bbc.co.uk': 'BBC',
  'theverge.com': 'Verge', 'techcrunch.com': 'TC', 'wired.com': 'Wired',
  'bloomberg.com': 'Bloomberg', 'reuters.com': 'Reuters', 'wsj.com': 'WSJ',
  'apnews.com': 'AP', 'cnn.com': 'CNN', 'insideevs.com': 'InsideEVs',
}

function providerName(domain: string): string {
  for (const key of Object.keys(KNOWN_PROVIDERS)) {
    if (domain === key || domain.endsWith(`.${key}`)) return KNOWN_PROVIDERS[key]
  }
  return domain.replace(/^(www|m|old|new)\./i, '').split('.')[0]
}

function faviconUrl(domain: string) {
  return `https://www.google.com/s2/favicons?domain=${domain}&sz=16`
}

function truncatePath(url: string): string {
  try {
    const u = new URL(url)
    const path = u.pathname
    return path.length > 40 ? path.slice(0, 38) + '…' : path
  } catch {
    return ''
  }
}

function formatElapsed(ms: unknown): string {
  if (typeof ms !== 'number' || ms < 0) return ''
  return ms < 1000 ? `+${Math.round(ms)}ms` : `+${(ms / 1000).toFixed(1)}s`
}

function formatDuration(ms: unknown): string {
  if (typeof ms !== 'number') return ''
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`
}

function formatWallTime(value: unknown): string {
  if (typeof value !== 'string') return ''
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric', minute: '2-digit', second: '2-digit',
  }).format(new Date(value))
}

// ── Fold url_fetched events into the fetch_started row ────────────────────

interface FetchedUrl {
  url: string
  domain: string
  item_count: number
  fetch_ms: number
}

interface FoldedFetch extends SSEEvent {
  _fetchCount: number
  _totalUrls: number
  _domains: string[]
  _latestElapsed: number
  _urls: FetchedUrl[]
}

type FoldedEvent = SSEEvent | FoldedFetch

function isFolded(ev: FoldedEvent): ev is FoldedFetch {
  return '_fetchCount' in ev
}

function foldEvents(events: SSEEvent[]): FoldedEvent[] {
  const result: FoldedEvent[] = []
  let batchIdx = -1

  for (const ev of events) {
    if (ev.type === 'fetch_started') {
      const folded: FoldedFetch = {
        ...ev,
        _fetchCount: 0,
        _totalUrls: (ev.detail.url_count as number | undefined) ?? 0,
        _domains: [],
        _latestElapsed: (ev.detail.elapsed_ms as number | undefined) ?? 0,
        _urls: [],
      }
      result.push(folded)
      batchIdx = result.length - 1
    } else if (ev.type === 'url_fetched' && batchIdx >= 0) {
      const batch = result[batchIdx] as FoldedFetch
      const domain = ev.detail.domain as string | undefined
      const url = ev.detail.url as string | undefined
      const fetchedUrl: FetchedUrl | undefined = url && domain ? {
        url,
        domain,
        item_count: (ev.detail.item_count as number | undefined) ?? 0,
        fetch_ms: (ev.detail.fetch_ms as number | undefined) ?? 0,
      } : undefined
      result[batchIdx] = {
        ...batch,
        _fetchCount: batch._fetchCount + 1,
        _domains: domain ? [...batch._domains, domain].slice(-8) : batch._domains,
        _latestElapsed: (ev.detail.elapsed_ms as number | undefined) ?? batch._latestElapsed,
        _urls: fetchedUrl ? [...batch._urls, fetchedUrl] : batch._urls,
      }
    } else {
      result.push(ev)
    }
  }
  return result
}

// ── Row renderers ─────────────────────────────────────────────────────────

// FetchBatchRow returns a tuple: [headerContent, expandedListOrNull]
// EventRow renders them as separate <li> elements so the URL list
// spans the full row width and genuinely pushes subsequent rows down.
function useFetchExpanded() {
  return useState(false)
}

function FetchBatchHeader({ ev, expanded, setExpanded }: {
  ev: FoldedFetch
  expanded: boolean
  setExpanded: (x: boolean) => void
}) {
  const pct = ev._totalUrls > 0 ? Math.min(100, (ev._fetchCount / ev._totalUrls) * 100) : 0
  const done = ev._fetchCount >= ev._totalUrls && ev._totalUrls > 0
  const domains = [...new Set(ev._domains)].slice(0, 6)
  const recentUrls = ev._urls.slice(-3)

  return (
    <div className="fetch-batch-message">
      <span className="fetch-batch-header">
        <span className="event-prefix event-prefix--fetch">
          {done ? 'Fetched' : 'Fetching'}
        </span>
        <span className="count-badge" style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>
          {ev._fetchCount}/{ev._totalUrls} URLs
        </span>
        {domains.map(d => (
          <span key={d} className="event-source-badge">
            <img src={faviconUrl(d)} alt="" width={12} height={12}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
            {providerName(d)}
          </span>
        ))}
        {ev._urls.length > 0 && (
          <button
            className="url-expand-toggle"
            onClick={e => { e.stopPropagation(); setExpanded(!expanded) }}
            title={expanded ? 'Hide URLs' : 'Show fetched URLs'}
          >
            {expanded ? '▲ hide' : `▼ ${ev._urls.length} URLs`}
          </button>
        )}
      </span>
      {!done && (
        <div className="fetch-progress-bar">
          <div className="fetch-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      )}
      {!expanded && recentUrls.length > 0 && (
        <div className="fetch-url-live">
          {recentUrls.map(u => (
            <a key={u.url} href={u.url} target="_blank" rel="noreferrer" className="fetch-url-link" title={u.url}>
              <img src={faviconUrl(u.domain)} alt="" width={11} height={11}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              <span className="fetch-url-domain">{providerName(u.domain)}</span>
              {u.item_count > 0 && <span className="url-item-badge">{u.item_count}</span>}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

function ItemAnalyzedRow({ ev }: { ev: SSEEvent }) {
  const label = ev.detail.label as string
  const domain = ev.detail.domain as string | undefined
  const url = ev.detail.url as string | undefined
  const summary = ev.detail.summary as string
  const credible = domain ? isHighCredibility(domain) : false

  const badgeContent = (
    <>
      <img src={faviconUrl(domain ?? '')} alt="" width={12} height={12}
        onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
      {providerName(domain ?? '')}
      {credible && <span className="credibility-star" title="High-credibility source">★</span>}
    </>
  )

  return (
    <span className="timeline-message">
      <span className={`sentiment-chip sentiment-chip--${label}`}>{label}</span>
      <span className="event-body" title={summary}>{summary}</span>
      {domain && url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className={`event-source-badge event-source-badge--link${credible ? ' event-source-badge--credible' : ''}`}
          title={url}
        >
          {badgeContent}
        </a>
      ) : domain ? (
        <span className={`event-source-badge${credible ? ' event-source-badge--credible' : ''}`} title={domain}>
          {badgeContent}
        </span>
      ) : null}
      {typeof ev.detail.duration_ms === 'number' && (
        <span className="duration-badge">{formatDuration(ev.detail.duration_ms)}</span>
      )}
    </span>
  )
}

function SearchRow({ ev }: { ev: SSEEvent }) {
  const q = ev.detail.query as string
  return (
    <span className="timeline-message">
      <span className="event-prefix event-prefix--search">Search</span>
      <span className="event-body query-text" title={q}>"{q}"</span>
    </span>
  )
}

function GenericRow({ ev }: { ev: SSEEvent }) {
  const prefixMap: Record<string, string> = {
    run_started: 'Start', synthesis_started: 'Synthesis',
    run_completed: 'Done', run_cancelled: 'Cancelled', run_error: 'Error',
  }
  const prefix = prefixMap[ev.type] ?? ev.type
  const msg = ev.type === 'run_error' && typeof ev.detail.message === 'string'
    ? ev.detail.message : ev.message
  return (
    <span className="timeline-message">
      <span className="event-prefix">{prefix}</span>
      <span className="event-body" title={msg}>{msg}</span>
    </span>
  )
}

function EventRow({ ev }: { ev: FoldedEvent }) {
  const [expanded, setExpanded] = useFetchExpanded()
  const elapsed = !isFolded(ev) ? ev.detail.elapsed_ms : ev._latestElapsed
  const received = !isFolded(ev) ? ev.detail.received_at : undefined

  if (isFolded(ev)) {
    return (
      <Fragment>
        <li className={`timeline-event timeline-event--${ev.type}`}>
          <span className="event-elapsed">{formatElapsed(elapsed)}</span>
          <time className="event-time">{formatWallTime(received)}</time>
          <FetchBatchHeader ev={ev} expanded={expanded} setExpanded={setExpanded} />
        </li>
        {expanded && (
          <li className="timeline-url-list-row">
            <div className="fetch-url-list">
              {ev._urls.map(u => (
                <a key={u.url} href={u.url} target="_blank" rel="noreferrer" className="fetch-url-link" title={u.url}>
                  <img src={faviconUrl(u.domain)} alt="" width={11} height={11}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                  <span className="fetch-url-domain">{providerName(u.domain)}</span>
                  <span className="fetch-url-path">{truncatePath(u.url)}</span>
                  {u.item_count > 0 && <span className="url-item-badge">{u.item_count}</span>}
                  <span className="duration-badge">{formatDuration(u.fetch_ms)}</span>
                </a>
              ))}
            </div>
          </li>
        )}
      </Fragment>
    )
  }

  return (
    <li className={`timeline-event timeline-event--${ev.type}`}>
      <span className="event-elapsed">{formatElapsed(elapsed)}</span>
      <time className="event-time">{formatWallTime(received)}</time>
      {ev.type === 'item_analyzed'   ? <ItemAnalyzedRow ev={ev} />        :
       ev.type === 'search_queried'  ? <SearchRow ev={ev} />              :
       ev.type === 'fetch_started'   ? null                               :
       <GenericRow ev={ev} />}
    </li>
  )
}

export function EventTimeline({ events, status }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [showCredibleModal, setShowCredibleModal] = useState(false)
  const folded = foldEvents(events)

  const credibleItems = events.filter(e =>
    e.type === 'item_analyzed' && isHighCredibility((e.detail.domain as string | undefined) ?? '')
  )
  const credibleDomains = [...new Set(
    credibleItems.map(e => (e.detail.domain as string | undefined) ?? '').filter(Boolean)
  )]
  const credibleCount = credibleItems.length
  const lastEvent = folded.length > 0 ? folded[folded.length - 1] : null

  return (
    <section className="panel" aria-label="Run timeline">
      <div className="timeline-header">
        <h2>Timeline</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {credibleCount > 0 && (
            <button
              className="credibility-count credibility-count--btn"
              title="Click to see credible sources"
              onClick={() => setShowCredibleModal(m => !m)}
            >
              ★ {credibleCount} credible
            </button>
          )}
          <span className="timeline-count">{folded.length} events</span>
          <button
            className="timeline-collapse-btn"
            onClick={() => setCollapsed(c => !c)}
            title={collapsed ? 'Expand timeline' : 'Collapse timeline'}
          >
            {collapsed ? '▶ expand' : '▼ collapse'}
          </button>
        </div>
      </div>

      {/* Credible-sources list */}
      {showCredibleModal && credibleDomains.length > 0 && (
        <div className="credible-modal">
          <div className="credible-modal-header">
            <strong>High-credibility sources in this run</strong>
            <button className="topic-detail-close" onClick={() => setShowCredibleModal(false)}>✕</button>
          </div>
          <ul className="credible-modal-list">
            {credibleDomains.map(d => (
              <li key={d} className="credible-modal-item">
                <img src={faviconUrl(d)} alt="" width={12} height={12}
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                <a href={`https://${d}`} target="_blank" rel="noreferrer">{d}</a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Collapsed: show most recent event */}
      {collapsed && lastEvent && (
        <div className="timeline-collapsed-preview">
          <EventRow ev={lastEvent} />
        </div>
      )}

      {!collapsed && (
        <>
          {folded.length === 0 && (
            <div className="timeline-empty">
              {status === 'error' ? (
                <span>No events received before the stream closed.</span>
              ) : (
                <><span className="inline-spinner" aria-hidden="true" /><span>Waiting for backend…</span></>
              )}
            </div>
          )}
          <ul className="timeline">
            {folded.map(ev => (
              ev !== null && <EventRow key={ev.seq} ev={ev} />
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
