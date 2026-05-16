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

const EVENT_PREFIX: Record<string, string> = {
  run_started: 'Start',
  search_queried: 'Search',
  url_fetched: 'Fetch',
  synthesis_started: 'Synthesis',
  run_completed: 'Done',
  run_error: 'Error',
}

export function EventTimeline({ events, status }: Props) {
  const bottomRef = useRef<HTMLSpanElement | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'nearest' })
  }, [events])

  return (
    <section className="panel" aria-label="Run timeline">
      <h2>Timeline</h2>
      {events.length === 0 && (
        <div className="timeline-empty">
          {status === 'error' ? (
            <span>No events were received before the stream closed.</span>
          ) : (
            <>
              <span className="inline-spinner" aria-hidden="true" />
              <span>Waiting for the first backend event...</span>
            </>
          )}
        </div>
      )}
      <ul className="timeline">
        {events.map((ev, index) => (
          <li key={ev.seq} className={`timeline-event timeline-event--${ev.type}`}>
            <time className="event-time">{formatTime(ev.detail.received_at)}</time>
            {ev.type === 'item_analyzed' ? (
              <span className="timeline-message">
                <span
                  className="sentiment-chip"
                  style={{ background: LABEL_COLOR[(ev.detail.label as string) ?? 'neutral'] }}
                >
                  <strong>{ev.detail.label as string}</strong>
                </span>
                <span aria-hidden="true">—</span>
                <span>{ev.detail.summary as string}</span>
              </span>
            ) : (
              <span className="timeline-message">
                <span className="event-prefix">{EVENT_PREFIX[ev.type] ?? 'Event'}</span>
                <span>{eventMessage(ev)}</span>
              </span>
            )}
            {index === events.length - 1 && <span ref={bottomRef} />}
          </li>
        ))}
      </ul>
    </section>
  )
}

function eventMessage(event: SSEEvent): string {
  if (event.type === 'run_error' && typeof event.detail.message === 'string') {
    return event.detail.message
  }
  return event.message
}

function formatTime(value: unknown): string {
  if (typeof value !== 'string') return ''
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value))
}
