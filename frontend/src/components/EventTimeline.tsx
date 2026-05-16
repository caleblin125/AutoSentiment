/**
 * Subscribe to SSE and render agent events.
 * Implement with EventSource + parse JSON payloads (see frontend/IMPLEMENTATION.md).
 */
export function EventTimeline() {
  return (
    <section className="panel" aria-label="Run timeline">
      <h2>Timeline</h2>
      <p className="muted">
        Implement <code>EventSource</code> using <code>getRunEventsUrl(runId)</code>.
      </p>
    </section>
  )
}
