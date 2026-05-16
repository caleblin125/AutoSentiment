import { useEffect, useState } from 'react'
import { getEvidence, type EvidenceChunk, type GraphNode, type IdeaGraph, type Quote, type Report } from '../lib/api'

interface Props {
  runId: string
  report: Report
}

export function ReportView({ runId, report }: Props) {
  const [activeChunk, setActiveChunk] = useState<EvidenceChunk | null>(null)
  const [loadingChunk, setLoadingChunk] = useState(false)

  async function openCitation(quote: Quote) {
    setLoadingChunk(true)
    try {
      const chunk = await getEvidence(runId, quote.evidence_id)
      setActiveChunk(chunk)
    } finally {
      setLoadingChunk(false)
    }
  }

  useEffect(() => {
    if (!activeChunk) return

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setActiveChunk(null)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeChunk])

  const { overall, by_source, top_positive, top_negative, themes, narrative, timings, aspects, source_facts, graph } = report

  return (
    <section className="panel" aria-label="Report">
      <h2>Report</h2>

      {timings && <TimingSummary timings={timings} />}

      <div className="sentiment-bars">
        <SentimentBar label="Positive" value={overall.positive} color="#22c55e" />
        <SentimentBar label="Neutral" value={overall.neutral} color="#94a3b8" />
        <SentimentBar label="Negative" value={overall.negative} color="#ef4444" />
        <p className="muted">{overall.total} items analyzed</p>
      </div>

      <table className="source-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Items</th>
            <th>Positive</th>
            <th>Neutral</th>
            <th>Negative</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(by_source).map(([src, stats]) => (
            <tr key={src}>
              <td>{src}</td>
              <td>{stats?.count ?? 0}</td>
              <td>{pct(stats?.positive ?? 0)}</td>
              <td>{pct(stats?.neutral ?? 0)}</td>
              <td>{pct(stats?.negative ?? 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {themes.length > 0 && (
        <div className="themes">
          <strong>Key themes:</strong> {themes.join(' · ')}
        </div>
      )}

      <p className="narrative">{narrative}</p>

      {aspects && aspects.length > 0 && <AspectSummary aspects={aspects} />}
      {source_facts && source_facts.length > 0 && <SourceFacts facts={source_facts} />}
      {graph && graph.nodes.length > 0 && <IdeaGraphView graph={graph} />}

      <QuoteList title="Top positive" quotes={top_positive} onCite={openCitation} />
      <QuoteList title="Top negative" quotes={top_negative} onCite={openCitation} />
      {loadingChunk && <p className="muted">Loading evidence...</p>}

      {activeChunk && (
        <div className="modal-backdrop" onClick={() => setActiveChunk(null)}>
          <div
            className="evidence-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Evidence"
            onClick={event => event.stopPropagation()}
          >
            <button className="modal-close" onClick={() => setActiveChunk(null)} aria-label="Close">
              x
            </button>
            <p className="snippet">{activeChunk.snippet}</p>
            <a href={activeChunk.url} target="_blank" rel="noreferrer">View source</a>
          </div>
        </div>
      )}
    </section>
  )
}

function TimingSummary({ timings }: { timings: Record<string, number> }) {
  const rows = [
    ['Search', timings.search_ms],
    ['Fetch', timings.fetch_ms],
    ['Sentiment', timings.sentiment_ms],
    ['Synthesis', timings.synthesis_ms],
    ['Total', timings.total_ms],
  ].filter(([, value]) => typeof value === 'number') as [string, number][]

  if (rows.length === 0) return null

  const slowest = rows.reduce((max, row) => row[1] > max[1] ? row : max, rows[0])

  return (
    <div className="timing-grid">
      {rows.map(([label, value]) => (
        <div className={`timing-card ${slowest?.[0] === label ? 'timing-card--slowest' : ''}`} key={label}>
          <span>{label}</span>
          <strong>{formatDuration(value)}</strong>
        </div>
      ))}
    </div>
  )
}

function AspectSummary({ aspects }: { aspects: NonNullable<Report['aspects']> }) {
  return (
    <div className="insight-section">
      <h3>Directional topics</h3>
      <div className="aspect-grid">
        {aspects.map(aspect => (
          <div className={`aspect-card aspect-card--${aspect.sentiment}`} key={aspect.name}>
            <strong>{aspect.name}</strong>
            <span>{aspect.sentiment} · {aspect.count} mentions</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function SourceFacts({ facts }: { facts: NonNullable<Report['source_facts']> }) {
  return (
    <div className="insight-section">
      <h3>Evidence sources</h3>
      <div className="source-fact-list">
        {facts.slice(0, 8).map(fact => (
          <div className="source-fact" key={fact.domain}>
            <strong>{fact.domain}</strong>
            <span>{fact.source_type} · {fact.count} items</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function IdeaGraphView({ graph }: { graph: IdeaGraph }) {
  const layout = layoutGraph(graph.nodes)
  return (
    <div className="insight-section">
      <h3>Idea graph</h3>
      <svg className="idea-graph" viewBox="0 0 900 520" role="img" aria-label="Topic relationship graph">
        {graph.edges.map(edge => {
          const source = layout.get(edge.source)
          const target = layout.get(edge.target)
          if (!source || !target) return null
          return (
            <line
              key={`${edge.source}-${edge.target}-${edge.kind}`}
              className={`graph-edge graph-edge--${edge.kind}`}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              strokeWidth={Math.max(1, Math.min(6, edge.weight / 8))}
            />
          )
        })}
        {graph.nodes.map(node => {
          const point = layout.get(node.id)
          if (!point) return null
          const radius = nodeRadius(node)
          return (
            <g key={node.id} className={`graph-node graph-node--${node.kind}`}>
              <circle cx={point.x} cy={point.y} r={radius} />
              <text
                className="graph-node-label"
                x={point.x + radius + 8}
                y={point.y + 4}
              >
                {shortLabel(node.label)}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function SentimentBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="sentiment-row">
      <div className="sentiment-row__label">
        <span>{label}</span>
        <strong>{pct(value)}</strong>
      </div>
      <div className="sentiment-track">
        <div className="sentiment-fill" style={{ width: pct(value), backgroundColor: color }} />
      </div>
    </div>
  )
}

function QuoteList({ title, quotes, onCite }: {
  title: string
  quotes: Quote[]
  onCite: (q: Quote) => void
}) {
  if (quotes.length === 0) return null
  return (
    <div className="quote-list">
      <h3>{title}</h3>
      <div className="quote-grid">
        {quotes.map(q => (
          <article className="quote-card" key={q.evidence_id}>
            <p>"{q.summary}"</p>
            <button className="cite-btn" onClick={() => onCite(q)}>source</button>
          </article>
        ))}
      </div>
    </div>
  )
}

function pct(ratio: number): string {
  return `${Math.round(ratio * 100)}%`
}

function formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms)}ms`
}

function layoutGraph(nodes: GraphNode[]): Map<string, { x: number; y: number }> {
  const layout = new Map<string, { x: number; y: number }>()
  const topic = nodes.find(node => node.kind === 'topic')
  if (topic) layout.set(topic.id, { x: 90, y: 260 })

  const columns: Record<GraphNode['kind'], { x: number; top: number; bottom: number }> = {
    topic: { x: 90, top: 260, bottom: 260 },
    aspect: { x: 300, top: 80, bottom: 430 },
    theme: { x: 475, top: 100, bottom: 420 },
    sentiment: { x: 650, top: 150, bottom: 370 },
    source: { x: 760, top: 100, bottom: 420 },
  }

  for (const kind of ['aspect', 'theme', 'sentiment', 'source'] as const) {
    const group = nodes
      .filter(node => node.kind === kind && (node.weight > 0 || kind !== 'sentiment'))
      .sort((a, b) => b.weight - a.weight)
      .slice(0, kind === 'source' ? 6 : 8)
    const column = columns[kind]
    group.forEach((node, index) => {
      const step = group.length > 1 ? (column.bottom - column.top) / (group.length - 1) : 0
      layout.set(node.id, { x: column.x, y: group.length === 1 ? (column.top + column.bottom) / 2 : column.top + step * index })
    })
  }
  return layout
}

function nodeRadius(node: GraphNode): number {
  return Math.max(10, Math.min(28, 8 + Math.sqrt(Math.max(1, node.weight)) * 2))
}

function shortLabel(label: string): string {
  return label.length > 28 ? `${label.slice(0, 25)}...` : label
}
