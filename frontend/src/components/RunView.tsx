/**
 * Self-contained run view for one search tab.
 *
 * Accepts `initialRunId` for session restoration on reload.
 * Propagates current `runId` up so the parent can cancel it on tab close.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  cancelRun, createRun, createSavedSearch, deleteSavedSearch, expandRun,
  getRun, listSavedSearches, previewSearchPlan, startNemoClaw, suggestAngles,
  type Report, type ResearchDepth, type RunRequest, type SavedSearch, type SearchPlan, type UseCase,
} from '../lib/api'
import { useRunStream } from '../hooks/useRunStream'
import { ErrorBoundary } from './ErrorBoundary'
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

const USE_CASE_OPTIONS: Array<{ value: UseCase; label: string }> = [
  { value: 'generic', label: 'Generic' },
  { value: 'entertainment_product', label: 'Entertainment' },
  { value: 'public_current_event', label: 'Current event' },
  { value: 'brand_product', label: 'Brand/product' },
  { value: 'policy_civic', label: 'Policy/civic' },
  { value: 'financial_market', label: 'Financial' },
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
  const [useCase, setUseCase] = useState<UseCase>('generic')
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
  const [searchPlan, setSearchPlan] = useState<SearchPlan | null>(null)
  // Track the pre-expand runId so we can restore it if the expanded run is cancelled.
  const [preExpandRunId, setPreExpandRunId] = useState<string | null>(null)
  // Saved searches
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([])
  const [showSaveInput, setShowSaveInput] = useState(false)
  const [saveNameInput, setSaveNameInput] = useState('')
  const [savingSearch, setSavingSearch] = useState(false)
  const [showSavedDropdown, setShowSavedDropdown] = useState(false)
  const savedDropdownRef = useRef<HTMLDivElement>(null)

  const { events, status } = useRunStream(runId)
  const isExpandedRun = Boolean(preExpandRunId && runId && runId !== preExpandRunId)

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

  useEffect(() => {
    const trimmedTopic = topic.trim()
    if (trimmedTopic.length < 2) {
      queueMicrotask(() => setSearchPlan(null))
      return
    }
    const controller = new AbortController()
    const timeout = window.setTimeout(() => {
      previewSearchPlan({
        topic: trimmedTopic,
        ...(freshness ? { freshness: freshness as RunRequest['freshness'] } : {}),
        research_depth: researchDepth,
        use_case: useCase,
      })
        .then(plan => { if (!controller.signal.aborted) setSearchPlan(plan) })
        .catch(() => { if (!controller.signal.aborted) setSearchPlan(null) })
    }, 300)
    return () => {
      controller.abort()
      window.clearTimeout(timeout)
    }
  }, [topic, freshness, researchDepth, useCase])

  // Historic tabs only provide a run id. Hydrate the run metadata so completed
  // reports can render even when the original tab state is gone.
  useEffect(() => {
    if (!initialRunId) return
    getRun(initialRunId)
      .then(run => {
        setActiveTopic(run.topic)
        setFreshness(run.freshness ?? '')
        setResearchDepth(run.research_depth)
        const restoredUseCase = run.report?.metadata?.use_case
        if (restoredUseCase) setUseCase(restoredUseCase)
      })
      .catch(() => {})
  }, [initialRunId])

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
        use_case: useCase,
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

  // Load saved searches once on mount.
  useEffect(() => {
    listSavedSearches().then(setSavedSearches).catch(() => {})
  }, [])

  // Close saved-searches dropdown on outside click.
  useEffect(() => {
    if (!showSavedDropdown) return
    function handleClick(e: MouseEvent) {
      if (savedDropdownRef.current && !savedDropdownRef.current.contains(e.target as Node)) {
        setShowSavedDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showSavedDropdown])

  async function handleSaveSearch(e: React.FormEvent) {
    e.preventDefault()
    const name = saveNameInput.trim()
    if (!name || !topic.trim()) return
    setSavingSearch(true)
    try {
      const created = await createSavedSearch({
        name,
        topic: topic.trim(),
        ...(freshness ? { freshness: freshness as RunRequest['freshness'] } : {}),
        research_depth: researchDepth,
        use_case: useCase,
      })
      setSavedSearches(prev => [created, ...prev])
      setSaveNameInput('')
      setShowSaveInput(false)
    } catch { /* best-effort */ }
    finally { setSavingSearch(false) }
  }

  async function handleDeleteSaved(id: string) {
    try {
      await deleteSavedSearch(id)
      setSavedSearches(prev => prev.filter(s => s.id !== id))
    } catch { /* best-effort */ }
  }

  function handleLoadSaved(ss: SavedSearch) {
    setTopic(ss.topic)
    setFreshness(ss.freshness ?? '')
    setResearchDepth(ss.research_depth)
    setUseCase(ss.use_case)
    setShowSavedDropdown(false)
  }

  const isRunning   = status === 'running'
  const isCompleted = status === 'completed'
  const isCancelled = status === 'cancelled'
  const canCancelCurrentRun = isRunning || (isExpandedRun && !isCompleted && !isCancelled && status !== 'error')

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
            <select
              className="use-case-select"
              value={useCase}
              onChange={e => setUseCase(e.target.value as UseCase)}
              disabled={loading}
              title="Use case adjusts source mix and query planning"
            >
              {USE_CASE_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <button type="submit" disabled={loading || !topic.trim()}>
              {loading && <span className="spinner" aria-hidden="true" />}
              <span>{loading ? 'Starting…' : 'Analyze'}</span>
            </button>
          </form>
          <div className="budget-preview">
            <span>{searchPlan?.estimated_brave_queries ?? selectedDepth.queryCount} Brave queries</span>
            <span>{searchPlan?.url_budget ?? selectedDepth.urlCount} URLs</span>
            <span>{searchPlan?.item_budget ?? selectedDepth.itemCount} items</span>
            <span>{selectedDepth.synthesisSampleSize} synthesis samples</span>
            {searchPlan && <span>{searchPlan.monthly_quota_remaining} monthly queries left</span>}
          </div>
          {searchPlan?.quota_warning && <p className="quota-warning">{searchPlan.quota_warning}</p>}
          {searchPlan && (
            <div className="search-plan-preview" aria-label="Search plan preview">
              {searchPlan.queries.slice(0, 4).map(query => (
                <span key={`${query.purpose}:${query.query}`} title={query.query}>
                  {query.purpose}
                </span>
              ))}
            </div>
          )}
          {/* ── Saved searches row ── */}
          <div className="saved-search-row">
            {showSaveInput ? (
              <form className="save-search-form" onSubmit={handleSaveSearch}>
                <input
                  className="save-search-input"
                  type="text"
                  placeholder="Name this search…"
                  value={saveNameInput}
                  onChange={e => setSaveNameInput(e.target.value)}
                  autoFocus
                  disabled={savingSearch}
                />
                <button type="submit" disabled={savingSearch || !saveNameInput.trim()} className="btn-secondary">
                  {savingSearch ? '…' : 'Save'}
                </button>
                <button type="button" className="btn-secondary" onClick={() => setShowSaveInput(false)}>✕</button>
              </form>
            ) : (
              <button
                type="button"
                className="btn-secondary btn-save-search"
                onClick={() => { setSaveNameInput(topic.trim()); setShowSaveInput(true) }}
                disabled={!topic.trim()}
                title="Save this search configuration"
              >
                ★ Save
              </button>
            )}
            <div className="saved-dropdown-wrapper" ref={savedDropdownRef}>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowSavedDropdown(v => !v)}
                disabled={savedSearches.length === 0}
                title="Load a saved search"
              >
                Saved {savedSearches.length > 0 && `(${savedSearches.length})`} ▾
              </button>
              {showSavedDropdown && savedSearches.length > 0 && (
                <div className="saved-dropdown">
                  {savedSearches.map(ss => (
                    <div key={ss.id} className="saved-dropdown-item">
                      <button
                        type="button"
                        className="saved-item-load"
                        onClick={() => handleLoadSaved(ss)}
                        title={`${ss.topic} · ${ss.research_depth} · ${ss.use_case}`}
                      >
                        <span className="saved-item-name">{ss.name}</span>
                        <span className="saved-item-meta">{ss.topic}</span>
                      </button>
                      <button
                        type="button"
                        className="saved-item-delete"
                        onClick={() => handleDeleteSaved(ss.id)}
                        title="Delete this saved search"
                      >✕</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
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
            {isExpandedRun && !isCompleted && <span className="expanded-run-badge">expanded search</span>}

            {canCancelCurrentRun && (
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

      {/* Loading / stage indicator */}
      {runId && !report && status !== 'error' && status !== 'cancelled' && (
        <div className="panel">
          <LoadingStage events={events} status={status} />
        </div>
      )}

      {/* NemoClaw sidebar — shown when activated */}
      {ncRunId && <NemoClawPanel ncRunId={ncRunId} topic={activeTopic ?? ''} />}

      {runId && events.length > 0 && <EventTimeline events={events} status={status} />}

      {report && runId && activeTopic && (
        <ErrorBoundary>
          <ReportView
            runId={runId}
            topic={activeTopic}
            report={report}
            onSearchTopic={(subtopic) => { setTopic(subtopic); setCached(false); }}
          />
        </ErrorBoundary>
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

// ── Loading stage indicator ────────────────────────────────────────────

interface LoadEvent { type: string }

const STAGE_INFO: Record<string, { label: string; pct: number; detail: string }> = {
  run_started: { label: 'Planning search', pct: 5, detail: 'Expanding queries and planning search strategy' },
  search_queried: { label: 'Searching', pct: 15, detail: 'Querying Brave Search (rate-limited to 1/s)' },
  fetch_started: { label: 'Fetching sources', pct: 35, detail: 'Downloading and extracting article text' },
  url_fetched: { label: 'Fetching sources', pct: 55, detail: 'Processing retrieved articles' },
  item_analyzed: { label: 'Analyzing sentiment', pct: 70, detail: 'Running per-item sentiment analysis via LLM' },
  synthesis_started: { label: 'Synthesizing report', pct: 90, detail: 'Generating themes, narrative, and graph' },
}

function LoadingStage({ events, status }: { events: LoadEvent[]; status: string }) {
  const lastEvent = events.length > 0 ? events[events.length - 1].type : null
  const stage = lastEvent ? STAGE_INFO[lastEvent] : null
  const pct = stage?.pct ?? 0
  const label = stage?.label ?? (status === 'running' ? 'Starting…' : 'Initializing…')
  const detail = stage?.detail ?? 'Preparing analysis pipeline'

  return (
    <div className="loading-stage">
      <div className="loading-stage-header">
        <span className="status-spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
        <strong>{label}</strong>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text)', marginLeft: 'auto' }}>
          {pct}%
        </span>
      </div>
      <div className="loading-stage-bar">
        <div className="loading-stage-fill" style={{ width: `${pct}%` }} />
      </div>
      <p className="loading-stage-detail">{detail}</p>
      {events.length < 2 && (
        <>
          <div className="skeleton skeleton-line skeleton-line--medium" style={{ marginBottom: 8 }} />
          <div className="skeleton skeleton-line skeleton-line--full" />
        </>
      )}
    </div>
  )
}
