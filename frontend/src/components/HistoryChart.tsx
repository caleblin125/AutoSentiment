/**
 * SVG line chart showing sentiment ratios (positive / neutral / negative)
 * across historical runs for the same topic.
 *
 * Runs are shown oldest → newest left to right.
 * Hover over a dot to see the exact percentages for that run.
 */
import { useEffect, useState } from 'react'
import { listRuns, type RunSummary } from '../lib/api'

const CHART_W = 860
const CHART_H = 140
const PAD = { top: 12, right: 16, bottom: 32, left: 40 }

const LINES = [
  { key: 'positive' as const, color: '#22c55e', label: 'Positive' },
  { key: 'neutral'  as const, color: '#94a3b8', label: 'Neutral' },
  { key: 'negative' as const, color: '#ef4444', label: 'Negative' },
]

interface Props { topic: string; currentRunId: string }

export function HistoryChart({ topic, currentRunId }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [hovered, setHovered] = useState<RunSummary | null>(null)

  useEffect(() => {
    listRuns(topic, 30)
      .then(data => setRuns([...data].reverse())   // oldest first
      )
      .catch(() => {/* non-fatal */})
  }, [topic, currentRunId])   // re-fetch when a new run for this topic completes

  if (runs.length < 2) return null   // chart only makes sense with 2+ points

  const plotW = CHART_W - PAD.left - PAD.right
  const plotH = CHART_H - PAD.top - PAD.bottom
  const n = runs.length

  function xScale(i: number) {
    return PAD.left + (n === 1 ? plotW / 2 : (plotW / (n - 1)) * i)
  }
  function yScale(v: number) {
    return PAD.top + plotH - v * plotH
  }

  function polyline(key: 'positive' | 'neutral' | 'negative') {
    return runs
      .map((r, i) => {
        const v = r.overall?.[key] ?? 0
        return `${xScale(i)},${yScale(v)}`
      })
      .join(' ')
  }

  function formatDate(iso: string) {
    return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso))
  }

  return (
    <div className="insight-section history-chart-section">
      <h3>Sentiment history <span className="graph-hint">{n} runs</span></h3>
      <div style={{ position: 'relative' }}>
        <svg
          className="history-chart"
          viewBox={`0 0 ${CHART_W} ${CHART_H}`}
          aria-label="Historical sentiment trend"
        >
          {/* Y-axis ticks */}
          {[0, 0.25, 0.5, 0.75, 1].map(v => (
            <g key={v}>
              <line
                x1={PAD.left} y1={yScale(v)}
                x2={CHART_W - PAD.right} y2={yScale(v)}
                stroke="#e2e8f0" strokeWidth={1}
              />
              <text x={PAD.left - 6} y={yScale(v) + 4} className="chart-tick">{Math.round(v * 100)}%</text>
            </g>
          ))}

          {/* Lines */}
          {LINES.map(({ key, color }) => (
            <polyline
              key={key}
              points={polyline(key)}
              fill="none"
              stroke={color}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}

          {/* Dots */}
          {runs.map((run, i) => (
            <g key={run.id}>
              {LINES.map(({ key, color }) => {
                const v = run.overall?.[key] ?? 0
                return (
                  <circle
                    key={key}
                    cx={xScale(i)} cy={yScale(v)} r={4}
                    fill={color}
                    stroke="#fff" strokeWidth={1.5}
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setHovered(run)}
                    onMouseLeave={() => setHovered(null)}
                  />
                )
              })}
              {/* Highlight current run */}
              {run.id === currentRunId && (
                <line
                  x1={xScale(i)} y1={PAD.top}
                  x2={xScale(i)} y2={CHART_H - PAD.bottom}
                  stroke="#2563eb" strokeWidth={1} strokeDasharray="3 3"
                />
              )}
            </g>
          ))}

          {/* X-axis labels: only first and last */}
          {[0, n - 1].map(i => (
            <text
              key={i}
              x={xScale(i)}
              y={CHART_H - 4}
              className="chart-tick"
              textAnchor={i === 0 ? 'start' : 'end'}
            >
              {formatDate(runs[i].created_at)}
            </text>
          ))}
        </svg>

        {/* Tooltip */}
        {hovered && hovered.overall && (
          <div className="chart-tooltip">
            <strong>{formatDate(hovered.created_at)}</strong>
            {LINES.map(({ key, color, label }) => (
              <span key={key} style={{ color }}>
                {label}: {Math.round((hovered.overall![key] ?? 0) * 100)}%
              </span>
            ))}
            <span className="muted">{hovered.overall.total} items</span>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="graph-legend">
        {LINES.map(({ key, color, label }) => (
          <span key={key} className="graph-legend-item">
            <span className="graph-legend-dot" style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  )
}
