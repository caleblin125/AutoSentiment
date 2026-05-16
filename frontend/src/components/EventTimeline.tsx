/**
 * Live timeline of SSE events.
 *
 * All url_fetched events are merged into a single "fetch batch" row that
 * shows a progress counter and advances as URLs complete.
 */
import { useEffect, useRef, useState } from 'react'
import type { SSEEvent } from '../lib/api'

interface Props { events: SSEEvent[]; status: string }

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

function FetchBatchRow({ ev }: { ev: FoldedFetch }) {
  const [expanded, setExpanded] = useState(false)
  const pct = ev._totalUrls > 0 ? Math.min(100, (ev._fetchCount / ev._totalUrls) * 100) : 0
  const done = ev._fetchCount >= ev._totalUrls && ev._totalUrls > 0
  const domains = [...new Set(ev._domains)].slice(0, 6)
  const recentUrls = ev._urls.slice(-5)

  return (
    <span className="timeline-message fetch-batch-message">
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
            onClick={e => { e.stopPropagation(); setExpanded((x: boolean) => !x) }}
            title={expanded ? 'Hide URLs' : 'Show fetched URLs'}
          >
            {expanded ? '▲ hide' : `▼ ${ev._urls.length} URLs`}
          </button>
        )}
      </span>

      {!done && (
        <div className="fetch-progress-bar" style={{ width: '100%' }}>
          <div className="fetch-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      )}

      {/* Live URL feed — last 5 when collapsed, all when expanded */}
      {!expanded && recentUrls.length > 0 && (
        <div className="fetch-url-live">
          {recentUrls.map(u => (
            <a key={u.url} href={u.url} target="_blank" rel="noreferrer" className="fetch-url-link" title={u.url}>
              <img src={faviconUrl(u.domain)} alt="" width={11} height={11}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              <span className="clip-text">{u.url}</span>
              {u.item_count > 0 && <span className="url-item-badge">{u.item_count}</span>}
            </a>
          ))}
        </div>
      )}

      {expanded && (
        <div className="fetch-url-list">
          {ev._urls.map(u => (
            <a key={u.url} href={u.url} target="_blank" rel="noreferrer" className="fetch-url-link" title={u.url}>
              <img src={faviconUrl(u.domain)} alt="" width={11} height={11}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              <span className="clip-text">{u.url}</span>
              {u.item_count > 0 && <span className="url-item-badge">{u.item_count}</span>}
              <span className="duration-badge" style={{ marginLeft: 'auto', flexShrink: 0 }}>{formatDuration(u.fetch_ms)}</span>
            </a>
          ))}
        </div>
      )}
    </span>
  )
}

function ItemAnalyzedRow({ ev }: { ev: SSEEvent }) {
  const label = ev.detail.label as string
  const domain = ev.detail.domain as string | undefined
  const summary = ev.detail.summary as string
  return (
    <span className="timeline-message">
      <span
        className={`sentiment-chip sentiment-chip--${label}`}
        style={{ background: undefined }}
      >
        {label}
      </span>
      <span className="event-body" title={summary}>{summary}</span>
      {domain && (
        <span className="event-source-badge" title={domain}>
          <img src={faviconUrl(domain)} alt="" width={12} height={12}
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          {providerName(domain)}
        </span>
      )}
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

function EventRow({ ev, isLast }: { ev: FoldedEvent; isLast: boolean }) {
  const bottomRef = useRef<HTMLSpanElement | null>(null)
  useEffect(() => {
    if (isLast) bottomRef.current?.scrollIntoView({ block: 'nearest' })
  }, [isLast])

  const elapsed = !isFolded(ev) ? ev.detail.elapsed_ms : ev._latestElapsed
  const received = !isFolded(ev) ? ev.detail.received_at : undefined

  return (
    <li className={`timeline-event timeline-event--${ev.type}`}>
      <span className="event-elapsed">{formatElapsed(elapsed)}</span>
      <time className="event-time">{formatWallTime(received)}</time>
      {isFolded(ev)                  ? <FetchBatchRow ev={ev} />         :
       ev.type === 'item_analyzed'   ? <ItemAnalyzedRow ev={ev} />        :
       ev.type === 'search_queried'  ? <SearchRow ev={ev} />              :
       ev.type === 'fetch_started'   ? null                               : // handled above
       <GenericRow ev={ev} />}
      {isLast && <span ref={bottomRef} />}
    </li>
  )
}

export function EventTimeline({ events, status }: Props) {
  const folded = foldEvents(events)
  return (
    <section className="panel" aria-label="Run timeline">
      <h2>Timeline</h2>
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
        {folded.map((ev, i) => (
          ev !== null && <EventRow key={ev.seq} ev={ev} isLast={i === folded.length - 1} />
        ))}
      </ul>
    </section>
  )
}
