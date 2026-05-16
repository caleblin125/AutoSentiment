/**
 * Live timeline of SSE events for an active research run.
 *
 * Each row shows:
 *  - Elapsed time from run start (server-side elapsed_ms) in a fixed column
 *  - Wall-clock receipt time (small, muted)
 *  - Event type chip (search / fetch / sentiment chip / …)
 *  - Event-specific detail (query text, domain+favicon, duration badge, etc.)
 *
 * Auto-scrolls to the latest event.
 */
import { useEffect, useRef } from 'react'
import type { SSEEvent } from '../lib/api'

interface Props {
  events: SSEEvent[]
  status: string
}

const LABEL_COLOR: Record<string, string> = {
  positive: '#22c55e',
  neutral: '#94a3b8',
  negative: '#ef4444',
}

const KNOWN_PROVIDERS: Record<string, string> = {
  'reddit.com': 'Reddit',
  'news.ycombinator.com': 'Hacker News',
  'youtube.com': 'YouTube',
  'youtu.be': 'YouTube',
  'x.com': 'X / Twitter',
  'twitter.com': 'X / Twitter',
  'quora.com': 'Quora',
  'facebook.com': 'Facebook',
  'instagram.com': 'Instagram',
  'tiktok.com': 'TikTok',
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
  'stackoverflow.com': 'Stack Overflow',
  'stackexchange.com': 'Stack Exchange',
}

function providerName(domain: string): string {
  // Walk from longest match to shortest (handles subdomains).
  for (const key of Object.keys(KNOWN_PROVIDERS)) {
    if (domain === key || domain.endsWith(`.${key}`)) return KNOWN_PROVIDERS[key]
  }
  // Strip common subdomains for a cleaner display.
  return domain.replace(/^(www|m|old|new)\./i, '')
}

function faviconUrl(domain: string): string {
  return `https://www.google.com/s2/favicons?domain=${domain}&sz=16`
}

function formatElapsed(ms: unknown): string {
  if (typeof ms !== 'number' || ms < 0) return ''
  if (ms < 1000) return `+${Math.round(ms)}ms`
  return `+${(ms / 1000).toFixed(1)}s`
}

function formatDuration(ms: unknown): string {
  if (typeof ms !== 'number') return ''
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatWallTime(value: unknown): string {
  if (typeof value !== 'string') return ''
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value))
}

// ── Per-event renderers ────────────────────────────────────────────────────

function ItemAnalyzedRow({ ev }: { ev: SSEEvent }) {
  const label = ev.detail.label as string
  const domain = ev.detail.domain as string | undefined
  return (
    <span className="timeline-message">
      <span
        className="sentiment-chip"
        style={{ background: LABEL_COLOR[label] ?? LABEL_COLOR.neutral }}
      >
        <strong>{label}</strong>
      </span>
      <span className="event-body">{ev.detail.summary as string}</span>
      {domain && (
        <span className="event-source-badge">
          <img src={faviconUrl(domain)} alt="" width={14} height={14} onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          {providerName(domain)}
        </span>
      )}
      {typeof ev.detail.duration_ms === 'number' && (
        <span className="duration-badge">{formatDuration(ev.detail.duration_ms)}</span>
      )}
    </span>
  )
}

function UrlFetchedRow({ ev }: { ev: SSEEvent }) {
  const domain = ev.detail.domain as string | undefined
  const itemCount = ev.detail.item_count as number | undefined
  return (
    <span className="timeline-message">
      <span className="event-prefix event-prefix--fetch">Fetch</span>
      {domain && (
        <>
          <img
            src={faviconUrl(domain)}
            alt=""
            width={14} height={14}
            style={{ flexShrink: 0 }}
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
          <span className="event-body">{providerName(domain)}</span>
        </>
      )}
      {typeof itemCount === 'number' && (
        <span className="count-badge">{itemCount} item{itemCount !== 1 ? 's' : ''}</span>
      )}
      {typeof ev.detail.fetch_ms === 'number' && (
        <span className="duration-badge">{formatDuration(ev.detail.fetch_ms)}</span>
      )}
    </span>
  )
}

function FetchStartedRow({ ev }: { ev: SSEEvent }) {
  return (
    <span className="timeline-message">
      <span className="event-prefix event-prefix--fetch">Fetching</span>
      <span className="event-body">{ev.detail.url_count as number} URLs in parallel</span>
    </span>
  )
}

function SearchRow({ ev }: { ev: SSEEvent }) {
  return (
    <span className="timeline-message">
      <span className="event-prefix event-prefix--search">Search</span>
      <span className="event-body query-text">"{ev.detail.query as string}"</span>
    </span>
  )
}

function GenericRow({ ev }: { ev: SSEEvent }) {
  const prefixMap: Record<string, string> = {
    run_started: 'Start',
    synthesis_started: 'Synthesis',
    run_completed: 'Done',
    run_error: 'Error',
  }
  const prefix = prefixMap[ev.type] ?? ev.type
  const message =
    ev.type === 'run_error' && typeof ev.detail.message === 'string'
      ? ev.detail.message
      : ev.message
  return (
    <span className="timeline-message">
      <span className="event-prefix">{prefix}</span>
      <span className="event-body">{message}</span>
    </span>
  )
}

function EventRow({ ev, isLast }: { ev: SSEEvent; isLast: boolean }) {
  const bottomRef = useRef<HTMLSpanElement | null>(null)
  useEffect(() => {
    if (isLast) bottomRef.current?.scrollIntoView({ block: 'nearest' })
  }, [isLast])

  const elapsed = ev.detail.elapsed_ms
  const received = ev.detail.received_at

  return (
    <li className={`timeline-event timeline-event--${ev.type}`}>
      <span className="event-elapsed">{formatElapsed(elapsed)}</span>
      <time className="event-time">{formatWallTime(received)}</time>
      {ev.type === 'item_analyzed'   ? <ItemAnalyzedRow ev={ev} /> :
       ev.type === 'url_fetched'     ? <UrlFetchedRow ev={ev} />   :
       ev.type === 'fetch_started'   ? <FetchStartedRow ev={ev} /> :
       ev.type === 'search_queried'  ? <SearchRow ev={ev} />       :
       <GenericRow ev={ev} />}
      {isLast && <span ref={bottomRef} />}
    </li>
  )
}

// ── Component ──────────────────────────────────────────────────────────────

export function EventTimeline({ events, status }: Props) {
  return (
    <section className="panel" aria-label="Run timeline">
      <h2>Timeline</h2>
      {events.length === 0 && (
        <div className="timeline-empty">
          {status === 'error' ? (
            <span>No events received before the stream closed.</span>
          ) : (
            <>
              <span className="inline-spinner" aria-hidden="true" />
              <span>Waiting for the first backend event…</span>
            </>
          )}
        </div>
      )}
      <ul className="timeline">
        {events.map((ev, i) => (
          <EventRow key={ev.seq} ev={ev} isLast={i === events.length - 1} />
        ))}
      </ul>
    </section>
  )
}
