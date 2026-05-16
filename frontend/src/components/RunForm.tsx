import { useState } from 'react'
import { createRun, type ResearchDepth, type RunRequest } from '../lib/api'

interface Props {
  onRunCreated: (runId: string, topic: string) => void
}

const FRESHNESS_OPTIONS = [
  { value: 'pm', label: 'Past month' },
  { value: 'pw', label: 'Past week' },
  { value: 'pd', label: 'Past 24 hours' },
  { value: 'py', label: 'Past year' },
  { value: '', label: 'Any time' },
] as const

const DEPTH_OPTIONS: Array<{ value: ResearchDepth; label: string }> = [
  { value: 'quick', label: 'Quick' },
  { value: 'standard', label: 'Standard' },
  { value: 'deep', label: 'Deep' },
  { value: 'exhaustive', label: 'Exhaustive' },
]

export function RunForm({ onRunCreated }: Props) {
  const [topic, setTopic] = useState('')
  const [freshness, setFreshness] = useState<string>('pm')
  const [researchDepth, setResearchDepth] = useState<ResearchDepth>('standard')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!topic.trim()) return
    setLoading(true)
    setError(null)
    try {
      const req: RunRequest = {
        topic: topic.trim(),
        ...(freshness ? { freshness: freshness as RunRequest['freshness'] } : {}),
        research_depth: researchDepth,
      }
      const { run_id } = await createRun(req)
      onRunCreated(run_id, req.topic)
      setTopic('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start run')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel" aria-label="New research run">
      <h2>New run</h2>
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Topic or brand (e.g. Tesla Model 3)"
          value={topic}
          onChange={e => setTopic(e.target.value)}
          disabled={loading}
          required
        />
        <select value={freshness} onChange={e => setFreshness(e.target.value)} disabled={loading}>
          {FRESHNESS_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select value={researchDepth} onChange={e => setResearchDepth(e.target.value as ResearchDepth)} disabled={loading}>
          {DEPTH_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <button type="submit" disabled={loading || !topic.trim()}>
          {loading && <span className="spinner" aria-hidden="true" />}
          <span>{loading ? 'Starting' : 'Analyze'}</span>
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  )
}
