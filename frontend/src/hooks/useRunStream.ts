import { useEffect, useState } from 'react'
import { getEventsUrl, type SSEEvent } from '../lib/api'

type StreamStatus = 'idle' | 'running' | 'completed' | 'error'
interface StreamState {
  runId: string | null
  events: SSEEvent[]
  status: StreamStatus
}

export function useRunStream(runId: string | null): { events: SSEEvent[]; status: StreamStatus } {
  const [streamState, setStreamState] = useState<StreamState>({
    runId: null,
    events: [],
    status: 'idle',
  })

  useEffect(() => {
    if (!runId) {
      return
    }

    const eventSource = new EventSource(getEventsUrl(runId))

    eventSource.onmessage = (message: MessageEvent) => {
      const parsed = JSON.parse(message.data) as SSEEvent
      const event: SSEEvent = {
        ...parsed,
        detail: {
          ...parsed.detail,
          // The API event shape has no timestamp, so stamp receipt time for the timeline.
          received_at: new Date().toISOString(),
        },
      }
      const nextStatus: StreamStatus =
        event.type === 'run_completed'
          ? 'completed'
          : event.type === 'run_error'
            ? 'error'
            : 'running'

      setStreamState(prev => ({
        runId,
        events: prev.runId === runId ? [...prev.events, event] : [event],
        status: nextStatus,
      }))

      if (nextStatus === 'completed' || nextStatus === 'error') {
        eventSource.close()
      }
    }

    eventSource.onerror = () => {
      setStreamState(prev => ({
        runId,
        events: prev.runId === runId ? prev.events : [],
        status: 'error',
      }))
      eventSource.close()
    }

    return () => {
      eventSource.close()
    }
  }, [runId])

  if (!runId) {
    return { events: [], status: 'idle' }
  }

  if (streamState.runId !== runId) {
    return { events: [], status: 'running' }
  }

  return { events: streamState.events, status: streamState.status }
}
