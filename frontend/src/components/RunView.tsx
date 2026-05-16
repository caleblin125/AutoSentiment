/**
 * Self-contained run view for one search tab.
 *
 * Accepts `initialRunId` for session restoration on reload.
 * Propagates current `runId` up so the parent can cancel it on tab close.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  cancelRun, createRun, expandRun, startNemoClaw, suggestAngles,
  type Report, type ResearchDepth, type RunRequest,
} from '../lib/api'
import { useRunStream } from '../hooks/useRunStream'
import { EventTimeline } from './EventTimeline'
import { ReportView } from './ReportView'
import { HistoryPanel } from './HistoryPanel'
import { NemoClawPanel } from './NemoClawPanel'

const FRESHNESS_OPTIONS = [
  { value: 'pm', label: 'Past month' },
  { value: 'pw', label: 'Past week' },
  { value: 'pd', label: 'Past 24 h' },
  { value: 'py', label: 'Past year' },
  { value: '',   label: 'Any time' },
] as const

const DEPTH_OPTIONS: Array<{
  value: ResearchDepth
  label: string
  queryCount: number
  urlCount: number
  itemCount: number
  synthesisSampleSize: number
}> = [
  { value: 'quick', label: 'Quick', queryCount: 3, urlCount: 12, itemCount: 40, synthesisSampleSize: 24 },
  { value: 'standard', label: 'Standard', queryCount: 6, urlCount: 30, itemCount: 100, synthesisSampleSize: 60 },
  { value: 'deep', label: 'Deep', queryCount: 10, urlCount: 60, itemCount: 180, synthesisSampleSize: 100 },
  { value: 'exhaustive', label: 'Exhaustive', queryCount: 16, urlCount: 100, itemCount: 300, synthesisSampleSize: 160 },
]

interface Props {
  onStatusChange: (status: string, label: string, runId?: string) => void
  onOpenRunInNewTab: (runId: string, topic: string) => void
  initialRunId?: string
  devMode?: boolean
}

export function RunView({ onStatusChange, onOpenRunInNewTab, initialRunId, devMode }: Props) {
  const [topic, setTopic] = useState('')
  const [freshness, setFreshness] = useState<string>('pm')
  const [researchDepth, setResearchDepth] = useState<ResearchDepth>('standard')
  const [runId, setRunId] = useState<string | null>(initialRunId ?? null)
  const [activeTopic, setActiveTopic] = useState<string | null>(null)
  const [cached, setCached] = useState(false)
  const [loading, setLoading] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [expanding, setExpanding] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [historyKey, setHistoryKey] = useState(0)
  const [ncRunId, setNcRunId] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [suggestLoading, setSuggestLoading] = useState(false)
  // Track the pre-expand runId so we can restore it if the expanded run is cancelled.
  const [preExpandRunId, setPreExpandRunId] = useState<string | null>(null)

  const { events, status } = useRunStream(runId)

  const report = useMemo<Report | null>(() => {
    const completed = events.findLast(e => e.type === 'run_completed')
    return (completed?.detail as { report?: Report } | undefined)?.report ?? null
  }, [events])
  const activeDepth = report?.metadata?.research_depth ?? researchDepth
  const selectedDepth = DEPTH_OPTIONS.find(o => o.value === researchDepth) ?? DEPTH_OPTIONS[1]
  const activeDepthOption = DEPTH_OPTIONS.find(o => o.value === activeDepth) ?? selectedDepth
  const activeDepthIndex = DEPTH_OPTIONS.findIndex(o => o.value === activeDepthOption.value)
  const selectedDepthIndex = DEPTH_OPTIONS.findIndex(o => o.value === selectedDepth.value)
  const nextDepthOption = DEPTH_OPTIONS[Math.min(
    activeDepthIndex + 1,
    DEPTH_OPTIONS.length - 1,
  )]
  const expandDepthOption = selectedDepthIndex > activeDepthIndex ? selectedDepth : nextDepthOption

  // Restore the pre-expand run when an expanded run is cancelled.
  useEffect(() => {
    if (status === 'cancelled' && preExpandRunId) {
      queueMicrotask(() => {
        setRunId(preExpandRunId)
        setPreExpandRunId(null)
      })
    }
  }, [status, preExpandRunId])

  // Propagate status + label + runId to parent (for tab state + close-kills-task).
  useEffect(() => {
    const label = activeTopic ?? 'New Search'
    const tabStatus = cached && status !== 'running' ? 'cached' : status
    onStatusChange(tabStatus, label, runId ?? undefined)
    if (status === 'completed') {
      queueMicrotask(() => setHistoryKey(k => k + 1))
    }
  }, [status, activeTopic, cached, runId, onStatusChange])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!topic.trim()) return
    setLoading(true)
    setFormError(null)
    setNcRunId(null)
    setShowSuggestions(false)
    try {
      const req: RunRequest = {
        topic: topic.trim(),
        ...(freshness ? { freshness: freshness as RunRequest['freshness'] } : {}),
        research_depth: researchDepth,
      }
      const { run_id, cached: isCached } = await createRun(req)
      setRunId(run_id)
      setActiveTopic(req.topic)
      setCached(isCached)
      setTopic('')
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to start run')
    } finally {
      setLoading(false)
    }
  }

  async function handleCancel() {
    if (!runId) return
    setCancelling(true)
    try { await cancelRun(runId) }
    catch { /* best-effort */ }
    finally { setCancelling(false) }
  }

  async function handleExpand() {
    if (!runId) return
    setExpanding(true)
    setNcRunId(null)
    setPreExpandRunId(runId)  // remember so we can restore on cancel
    try {
      const { run_id } = await expandRun(runId, { research_depth: expandDepthOption.value })
      setRunId(run_id)
      setResearchDepth(expandDepthOption.value)
      setCached(false)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Expand failed')
      setPreExpandRunId(null)
    } finally {
      setExpanding(false)
    }
  }

  async function handleNemoClaw() {
    if (!runId) return
    try {
      const { run_id } = await startNemoClaw(runId)
      setNcRunId(run_id)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'NemoClaw failed to start')
    }
  }


  // Suggestions fetched on explicit button click only.
  const handleSuggest = useCallback(async () => {
    if (!topic.trim() || suggestLoading) return
    setSuggestLoading(true)
    try {
      const results = await suggestAngles(topic)
      setSuggestions(results)
      setShowSuggestions(results.length > 0)
    } finally {
      setSuggestLoading(false)
    }
  }, [topic, suggestLoading])

  function handleTopicChange(e: React.ChangeEvent<HTMLInputElement>) {
    setTopic(e.target.value)
    // Clear stale suggestions when user edits the query.
    if (showSuggestions) setShowSuggestions(false)
  }

  const isRunning   = status === 'running'
  const isCompleted = status === 'completed'
  const isCancelled = status === 'cancelled'

  return (
    <div className="run-view">
      {/* ── Search bar + history ── */}
      <div className="panel search-panel">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, position: 'relative' }}>
          <form className="search-form" onSubmit={handleSubmit} autoComplete="off">
            <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
              <input
                className="search-input"
                type="text"
                placeholder="Topic, brand, event, or question…"
                value={topic}
                onChange={handleTopicChange}
                disabled={loading}
                required
              />
              {showSuggestions && suggestions.length > 0 && (
                <div className="suggestions-dropdown">
                  <div className="suggestions-header">
                    <span>AI suggestions</span>
                    <button
                      type="button"
                      className="suggestions-close"
                      onClick={() => setShowSuggestions(false)}
                    >✕</button>
                  </div>
                  {suggestions.map((s, i) => (
                    <button
                      key={i}
                      type="button"
                      className="suggestion-item"
                      onClick={() => {
                        setTopic(s)
                        setShowSuggestions(false)
                      }}
                    >
                      <span className="suggestion-icon">⊕</span>
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              type="button"
              className="btn-suggest"
              onClick={handleSuggest}
              disabled={!topic.trim() || suggestLoading}
              title="Get AI research angle suggestions"
            >
              {suggestLoading ? <span className="spinner" style={{ width: 12, height: 12 }} /> : '💡'}
            </button>
            <select
              className="freshness-select"
              value={freshness}
              onChange={e => setFreshness(e.target.value)}
              disabled={loading}
            >
              {FRESHNESS_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <select
              className="depth-select"
              value={researchDepth}
              onChange={e => setResearchDepth(e.target.value as ResearchDepth)}
              disabled={loading}
              title="Research depth controls query, URL, item, and synthesis budgets"
            >
              {DEPTH_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <button type="submit" disabled={loading || !topic.trim()}>
              {loading && <span className="spinner" aria-hidden="true" />}
              <span>{loading ? 'Starting…' : 'Analyze'}</span>
            </button>
          </form>
          <div className="budget-preview">
            <span>{selectedDepth.queryCount} Brave queries</span>
            <span>{selectedDepth.urlCount} URLs</span>
            <span>{selectedDepth.itemCount} items</span>
            <span>{selectedDepth.synthesisSampleSize} synthesis samples</span>
          </div>
          {formError && <p className="error-msg">{formError}</p>}
        </div>

        <HistoryPanel onOpenRun={onOpenRunInNewTab} refreshKey={historyKey} />
      </div>

      {/* ── Run status strip ── */}
      {runId && (
        <div className={`run-status run-status--${status}`} aria-live="polite">
          <div style={{ minWidth: 0 }}>
            <strong>{statusLabel(status, events.length)}</strong>
            {activeTopic && <p className="run-topic clip-text" title={activeTopic}>{activeTopic}</p>}
            <p className="run-topic-meta">
              {activeDepthOption.label} depth · {activeDepthOption.queryCount} queries · {activeDepthOption.urlCount} URLs · {activeDepthOption.itemCount} items
            </p>
            {devMode && (
              <p className="muted" style={{ fontFamily: 'var(--mono)', fontSize: 10 }}>
                run: {runId}
              </p>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            {cached && !isRunning && <span className="cached-badge">⚡ cached</span>}
            {isCancelled && <span className="cancelled-badge">⊘ cancelled</span>}

            {isRunning && (
              <button className="btn-cancel" onClick={handleCancel} disabled={cancelling}>
                {cancelling ? <span className="spinner" style={{ borderTopColor: 'var(--rog-red)' }} /> : '⊘'}
                {cancelling ? 'Stopping…' : 'Cancel'}
              </button>
            )}

            {isCompleted && !ncRunId && (
              <button
                className="btn-nemoclaw"
                onClick={handleNemoClaw}
                title="Launch NemoClaw autonomous deep-dive"
              >
                ⬡ NemoClaw
              </button>
            )}

            {isCompleted && (
              <button
                className="btn-expand"
                onClick={handleExpand}
                disabled={expanding}
                title={`Expand to ${expandDepthOption.label}: ${expandDepthOption.queryCount} queries, ${expandDepthOption.urlCount} URLs, ${expandDepthOption.itemCount} items`}
              >
                {expanding
                  ? <><span className="spinner" style={{ borderTopColor: 'var(--rog-cyan)' }} /> Expanding…</>
                  : `⊕ Expand to ${expandDepthOption.label}`}
              </button>
            )}

            {isRunning && <span className="status-spinner" />}
          </div>
        </div>
      )}

      {/* Skeleton while waiting */}
      {runId && events.length === 0 && status !== 'error' && (
        <div className="panel">
          <div className="skeleton skeleton-line skeleton-line--short" style={{ marginBottom: 12 }} />
          <div className="skeleton skeleton-line skeleton-line--full" />
          <div className="skeleton skeleton-line skeleton-line--medium" />
        </div>
      )}

      {/* NemoClaw sidebar — shown when activated */}
      {ncRunId && <NemoClawPanel ncRunId={ncRunId} topic={activeTopic ?? ''} />}

      {runId && events.length > 0 && <EventTimeline events={events} status={status} />}

      {report && runId && activeTopic && (
        <ReportView runId={runId} topic={activeTopic} report={report} />
      )}
    </div>
  )
}

function statusLabel(status: string, eventCount: number): string {
  if (status === 'completed') return 'Analysis complete'
  if (status === 'cancelled') return 'Analysis cancelled'
  if (status === 'error')    return 'Analysis stopped with an error'
  if (eventCount === 0)      return 'Initialising…'
  return 'Analysis in progress'
}
