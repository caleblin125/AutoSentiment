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
  { key: 'positive' as const, color: 'var(--positive)',   cls: 'pos', label: 'Positive' },
  { key: 'neutral'  as const, color: 'var(--neutral)',    cls: 'neu', label: 'Neutral'  },
  { key: 'negative' as const, color: 'var(--rog-red)',    cls: 'neg', label: 'Negative' },
]

interface Props { topic: string; currentRunId: string }

export function HistoryChart({ topic, currentRunId }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [hovered, setHovered] = useState<RunSummary | null>(null)

  useEffect(() => {
    listRuns(topic, 30)
      .then(data => setRuns([...data].reverse()))
      .catch(() => {/* non-fatal */})
  }, [topic, currentRunId])

  if (runs.length < 2) return null

  const plotW = CHART_W - PAD.left - PAD.right
  const plotH = CHART_H - PAD.top - PAD.bottom
  const n = runs.length
  const baseline = PAD.top + plotH

  function xScale(i: number) {
    return PAD.left + (n === 1 ? plotW / 2 : (plotW / (n - 1)) * i)
  }
  function yScale(v: number) {
    return PAD.top + plotH - v * plotH
  }

  function polyPoints(key: 'positive' | 'neutral' | 'negative') {
    return runs.map((r, i) => `${xScale(i)},${yScale(r.overall?.[key] ?? 0)}`).join(' ')
  }

  function areaPoints(key: 'positive' | 'neutral' | 'negative') {
    const pts = runs.map((r, i) => `${xScale(i)},${yScale(r.overall?.[key] ?? 0)}`).join(' ')
    // Close path along the bottom baseline
    return `${pts} ${xScale(n - 1)},${baseline} ${xScale(0)},${baseline}`
  }

  function formatDate(iso: string) {
    return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso))
  }

  return (
    <div className="insight-section history-chart-section">
      <h3>Sentiment history <span className="graph-hint">{n} runs</span></h3>
      <div className="history-chart-wrap">
        <svg
          className="history-chart"
          viewBox={`0 0 ${CHART_W} ${CHART_H}`}
          aria-label="Historical sentiment trend"
        >
          {/* Y-axis gridlines */}
          {[0, 0.25, 0.5, 0.75, 1].map(v => (
            <g key={v}>
              <line
                x1={PAD.left} y1={yScale(v)}
                x2={CHART_W - PAD.right} y2={yScale(v)}
                className="chart-gridline"
              />
              <text x={PAD.left - 6} y={yScale(v) + 4} className="chart-tick">{Math.round(v * 100)}%</text>
            </g>
          ))}

          {/* Area fills (under lines, semi-transparent) */}
          {LINES.map(({ key, color }) => (
            <polygon
              key={`area-${key}`}
              points={areaPoints(key)}
              fill={color}
              fillOpacity={0.07}
              stroke="none"
            />
          ))}

          {/* Lines */}
          {LINES.map(({ key, color }) => (
            <polyline
              key={key}
              points={polyPoints(key)}
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
                    className="chart-dot"
                    onMouseEnter={() => setHovered(run)}
                    onMouseLeave={() => setHovered(null)}
                  />
                )
              })}
              {run.id === currentRunId && (
                <line
                  x1={xScale(i)} y1={PAD.top}
                  x2={xScale(i)} y2={CHART_H - PAD.bottom}
                  className="chart-current-run"
                />
              )}
            </g>
          ))}

          {/* X-axis labels: first and last only */}
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
