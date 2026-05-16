/**
 * Multi-topic sentiment comparison view.
 *
 * Shows 2-3 topics side by side. Each slot starts its own run and
 * streams events via useRunStream. When a run completes its report is
 * extracted from the SSE run_completed event detail.
 */
import { useEffect, useRef, useState } from 'react'
import type { Report, RunRequest } from '../lib/api'
import { createRun, getRun } from '../lib/api'
import { useRunStream } from '../hooks/useRunStream'

const MAX_SLOTS = 3

// ── Slot subcomponent ─────────────────────────────────────────────────────

interface SlotProps {
  index: number
  topic: string
  onTopicChange: (v: string) => void
  runId: string | null
  onRunStart: (runId: string) => void
  disabled: boolean
  onOpenFull?: (runId: string, topic: string) => void
}

function pct(v: number): string { return `${Math.round(v * 100)}%` }

function SentimentBars({ overall }: { overall: Report['overall'] }) {
  const pos = overall.positive
  const neu = overall.neutral
  const neg = overall.negative
  return (
    <div className="compare-bars">
      <div className="compare-bar-row">
        <span className="compare-bar-label">+</span>
        <div className="compare-bar-track">
          <div className="compare-bar-fill compare-bar-fill--pos" style={{ width: pct(pos) }} />
        </div>
        <span className="compare-bar-pct">{pct(pos)}</span>
      </div>
      <div className="compare-bar-row">
        <span className="compare-bar-label">~</span>
        <div className="compare-bar-track">
          <div className="compare-bar-fill compare-bar-fill--neu" style={{ width: pct(neu) }} />
        </div>
        <span className="compare-bar-pct">{pct(neu)}</span>
      </div>
      <div className="compare-bar-row">
        <span className="compare-bar-label">–</span>
        <div className="compare-bar-track">
          <div className="compare-bar-fill compare-bar-fill--neg" style={{ width: pct(neg) }} />
        </div>
        <span className="compare-bar-pct">{pct(neg)}</span>
      </div>
    </div>
  )
}

function CompareSlot({ index, topic, onTopicChange, runId, disabled, onOpenFull }: SlotProps) {
  const { events, status } = useRunStream(runId)
  const [report, setReport] = useState<Report | null>(null)

  // Extract the report from the run_completed event once it fires.
  useEffect(() => {
    if (status !== 'completed') return
    const completedEv = events.findLast(e => e.type === 'run_completed')
    if (completedEv?.detail?.report) {
      // Use Promise.resolve to defer the setState call out of the effect body,
      // satisfying the react-hooks/set-state-in-effect lint rule.
      Promise.resolve().then(() => setReport(completedEv.detail.report as Report))
      return
    }
    // Fallback: fetch via REST if the event didn't carry the report.
    if (runId) getRun(runId).then(run => { if (run.report) setReport(run.report) }).catch(() => {})
  }, [status, events, runId])

  // Reset report when a new run starts.
  useEffect(() => { Promise.resolve().then(() => setReport(null)) }, [runId])

  const loading = status === 'running' && !report
  const sentimentScore = report
    ? report.overall.positive - report.overall.negative
    : null

  return (
    <div className={`compare-slot compare-slot--${status}`}>
      {/* ── Topic input ── */}
      <div className="compare-slot-header">
        <span className="compare-slot-num">{index + 1}</span>
        <input
          className="compare-topic-input"
          type="text"
          placeholder={`Topic ${index + 1}…`}
          value={topic}
          onChange={e => onTopicChange(e.target.value)}
          disabled={disabled || status === 'running'}
        />
      </div>

      {/* ── Body ── */}
      <div className="compare-slot-body">
        {!runId && (
          <div className="compare-slot-empty">
            Enter a topic and click Compare
          </div>
        )}

        {loading && (
          <div className="compare-slot-loading">
            <span className="inline-spinner" aria-hidden="true" />
            <span>Analysing…</span>
            <span className="compare-event-count">{events.length} events</span>
          </div>
        )}

        {status === 'error' && !report && (
          <div className="compare-slot-error">Analysis failed</div>
        )}

        {status === 'cancelled' && !report && (
          <div className="compare-slot-error">Cancelled</div>
        )}

        {report && (
          <div className="compare-slot-report">
            {/* Score badge */}
            <div className="compare-score-row">
              <span
                className={`compare-score-badge compare-score-badge--${
                  sentimentScore! >= 0.1 ? 'pos' : sentimentScore! <= -0.1 ? 'neg' : 'neu'
                }`}
              >
                {sentimentScore! >= 0 ? '+' : ''}{Math.round(sentimentScore! * 100)}
              </span>
              <span className="compare-items-count">{report.overall.total} items</span>
            </div>

            <SentimentBars overall={report.overall} />

            {/* Top themes */}
            {report.themes.length > 0 && (
              <div className="compare-themes">
                <div className="compare-section-label">Themes</div>
                <ul className="compare-theme-list">
                  {report.themes.slice(0, 5).map(t => (
                    <li key={t} className="compare-theme-item">{t}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Narrative snippet */}
            {report.narrative && (
              <div className="compare-narrative">
                <div className="compare-section-label">Summary</div>
                <p className="compare-narrative-text">{report.narrative.slice(0, 220)}{report.narrative.length > 220 ? '…' : ''}</p>
              </div>
            )}

            {/* Open full report */}
            {onOpenFull && runId && (
              <button
                type="button"
                className="btn-secondary compare-open-full-btn"
                onClick={() => onOpenFull(runId, topic)}
              >
                ↗ Open full report
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main CompareView ──────────────────────────────────────────────────────

interface CompareViewProps {
  onOpenFull?: (runId: string, topic: string) => void
}

export function CompareView({ onOpenFull }: CompareViewProps) {
  const [topics, setTopics] = useState<string[]>(['', ''])
  const [runIds, setRunIds] = useState<(string | null)[]>([null, null])
  const [slotCount, setSlotCount] = useState(2)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  function setTopic(i: number, v: string) {
    setTopics(prev => { const n = [...prev]; n[i] = v; return n })
  }

  function addSlot() {
    if (slotCount >= MAX_SLOTS) return
    setSlotCount(s => s + 1)
    setTopics(prev => [...prev, ''])
    setRunIds(prev => [...prev, null])
  }

  async function handleCompare(e: React.FormEvent) {
    e.preventDefault()
    const filled = topics.slice(0, slotCount).map(t => t.trim()).filter(Boolean)
    if (filled.length < 2) { setError('Enter at least 2 topics to compare'); return }
    setError(null)
    setLoading(true)
    try {
      const reqs: RunRequest[] = filled.map(topic => ({ topic, research_depth: 'standard' }))
      const results = await Promise.all(reqs.map(r => createRun(r)))
      const newRunIds = [...Array(MAX_SLOTS).fill(null)]
      results.forEach((r, i) => { newRunIds[i] = r.run_id })
      setRunIds(newRunIds)
      setTopics(filled.concat(Array(MAX_SLOTS - filled.length).fill('')))
      setSlotCount(filled.length)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start runs')
    } finally {
      setLoading(false)
    }
  }

  function handleReset() {
    setTopics(['', ''])
    setRunIds([null, null])
    setSlotCount(2)
    setError(null)
  }

  const activeTopics = topics.slice(0, slotCount)
  const canCompare = activeTopics.filter(t => t.trim().length >= 2).length >= 2
  const hasResults = runIds.some(id => id !== null)

  return (
    <div className="compare-view">
      <div className="compare-header">
        <div className="compare-title-row">
          <h2 className="compare-title">Compare Topics</h2>
          {hasResults && (
            <button type="button" className="btn-secondary compare-reset-btn" onClick={handleReset}>
              ↺ Reset
            </button>
          )}
        </div>
        <form className="compare-form" onSubmit={handleCompare}>
          <div className="compare-inputs">
            {Array.from({ length: slotCount }, (_, i) => (
              <input
                key={i}
                ref={i === 0 ? inputRef : undefined}
                className="compare-form-input"
                type="text"
                placeholder={`Topic ${i + 1}…`}
                value={topics[i] ?? ''}
                onChange={e => setTopic(i, e.target.value)}
                disabled={loading}
              />
            ))}
            {slotCount < MAX_SLOTS && (
              <button type="button" className="btn-secondary compare-add-slot" onClick={addSlot} disabled={loading}>
                + topic
              </button>
            )}
          </div>
          {error && <p className="compare-form-error">{error}</p>}
          <button
            type="submit"
            className="btn-primary compare-submit"
            disabled={!canCompare || loading}
          >
            {loading ? 'Starting…' : '▶ Compare'}
          </button>
        </form>
      </div>

      <div className={`compare-grid compare-grid--${slotCount}`}>
        {Array.from({ length: slotCount }, (_, i) => (
          <CompareSlot
            key={i}
            index={i}
            topic={topics[i] ?? ''}
            onTopicChange={v => setTopic(i, v)}
            runId={runIds[i] ?? null}
            onRunStart={id => setRunIds(prev => { const n = [...prev]; n[i] = id; return n })}
            disabled={loading}
            onOpenFull={onOpenFull}
          />
        ))}
      </div>
    </div>
  )
}
