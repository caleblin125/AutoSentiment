/**
 * Spring-physics force-directed graph.
 *
 * Interaction:
 *   Left-click source node → link popover with all URLs from that domain
 *   Left-click theme/aspect node → topic detail popover (evidence + links)
 *   Left-click sentiment node → calls onNodeClick to scroll to quotes
 *   Right-click + drag → reposition node
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { EvidenceChunk, GraphEdge, GraphNode, IdeaGraph } from '../lib/api'
import { getEvidence } from '../lib/api'

const W = 900
const H = 480

const REPULSION = 9500
const SPRING_K = 0.032
const SPRING_REST_BASE = 140
const DAMPING = 0.85
const CENTER_K = 0.003

interface Vec2 { x: number; y: number }
interface NodeSim { id: string; pos: Vec2; vel: Vec2; fixed: boolean }

const KIND_COLOR: Record<GraphNode['kind'], string> = {
  topic:     '#e8000d',
  theme:     '#8b5cf6',
  aspect:    '#ff6600',
  sentiment: '#4a6080',
  source:    '#00c8d4',
}

function nodeRadius(node: GraphNode): number {
  const base = node.kind === 'topic' ? 22 : node.kind === 'source' ? 12 : 13
  return Math.max(base, Math.min(base + 14, base + Math.sqrt(Math.max(0, node.weight)) * 1.5))
}

function shortLabel(label: string): string {
  return label.length > 20 ? `${label.slice(0, 17)}…` : label
}

// ── Force simulation ──────────────────────────────────────────────────────

function useForce(nodes: GraphNode[], edges: GraphEdge[]) {
  const simRef = useRef<NodeSim[]>([])
  const [positions, setPositions] = useState<Map<string, Vec2>>(new Map())
  const rafRef = useRef(0)
  const idxMap = useRef(new Map<string, number>())
  const rightDragRef = useRef<{ id: string } | null>(null)

  useLayoutEffect(() => {
    simRef.current = nodes.map((node, i) => {
      const angle = (2 * Math.PI * i) / Math.max(1, nodes.length)
      const r = Math.min(W, H) * 0.28
      return {
        id: node.id,
        pos: { x: W / 2 + r * Math.cos(angle), y: H / 2 + r * Math.sin(angle) },
        vel: { x: (Math.random() - 0.5) * 2, y: (Math.random() - 0.5) * 2 },
        fixed: false,
      }
    })
    idxMap.current = new Map(simRef.current.map((s, i) => [s.id, i]))
  }, [nodes])

  useEffect(() => {
    function tick() {
      const states = simRef.current
      if (!states.length) { rafRef.current = requestAnimationFrame(tick); return }

      const fx = new Float32Array(states.length)
      const fy = new Float32Array(states.length)

      for (let i = 0; i < states.length; i++) {
        for (let j = i + 1; j < states.length; j++) {
          const dx = states[i].pos.x - states[j].pos.x
          const dy = states[i].pos.y - states[j].pos.y
          const d2 = dx * dx + dy * dy + 1
          const f = REPULSION / d2
          const dist = Math.sqrt(d2)
          fx[i] += (dx / dist) * f; fy[i] += (dy / dist) * f
          fx[j] -= (dx / dist) * f; fy[j] -= (dy / dist) * f
        }
      }

      for (const edge of edges) {
        const si = idxMap.current.get(edge.source)
        const ti = idxMap.current.get(edge.target)
        if (si === undefined || ti === undefined) continue
        const dx = states[ti].pos.x - states[si].pos.x
        const dy = states[ti].pos.y - states[si].pos.y
        const dist = Math.sqrt(dx * dx + dy * dy) + 0.01
        const rest = SPRING_REST_BASE * (1 + 1 / Math.max(1, edge.weight))
        const f = SPRING_K * (dist - rest)
        fx[si] += (dx / dist) * f; fy[si] += (dy / dist) * f
        fx[ti] -= (dx / dist) * f; fy[ti] -= (dy / dist) * f
      }

      for (let i = 0; i < states.length; i++) {
        fx[i] += (W / 2 - states[i].pos.x) * CENTER_K
        fy[i] += (H / 2 - states[i].pos.y) * CENTER_K
      }

      const next = new Map<string, Vec2>()
      for (let i = 0; i < states.length; i++) {
        const s = states[i]
        if (!s.fixed) {
          s.vel.x = (s.vel.x + fx[i]) * DAMPING
          s.vel.y = (s.vel.y + fy[i]) * DAMPING
          s.pos.x = Math.max(36, Math.min(W - 36, s.pos.x + s.vel.x))
          s.pos.y = Math.max(24, Math.min(H - 24, s.pos.y + s.vel.y))
        }
        next.set(s.id, { x: s.pos.x, y: s.pos.y })
      }
      setPositions(next)
      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [nodes, edges])

  // Right-click drag handler
  function onContextMenu(nodeId: string, e: React.MouseEvent<SVGElement>) {
    e.preventDefault()
    const state = simRef.current.find(s => s.id === nodeId)
    if (!state) return
    state.fixed = true
    state.vel = { x: 0, y: 0 }
    rightDragRef.current = { id: nodeId }
    const svg = (e.currentTarget as SVGElement).ownerSVGElement
    if (!svg) return
    function onMove(me: MouseEvent) {
      if (!rightDragRef.current || rightDragRef.current.id !== nodeId) return
      const st = simRef.current.find(s => s.id === nodeId)
      if (!st) return
      if (!svg) return
      const pt = svg.createSVGPoint()
      pt.x = me.clientX; pt.y = me.clientY
      const svgPt = pt.matrixTransform(svg.getScreenCTM()!.inverse())
      st.pos = { x: svgPt.x, y: svgPt.y }
      st.vel = { x: 0, y: 0 }
    }

    function onUp() {
      rightDragRef.current = null
      const st = simRef.current.find(s => s.id === nodeId)
      if (st) st.fixed = false
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return { positions, onContextMenu }
}

// ── Popover for source node URLs ──────────────────────────────────────────

interface PopoverState { nodeId: string; x: number; y: number }

function NodePopover({ node, x, y, onClose }: {
  node: GraphNode; x: number; y: number; onClose: () => void
}) {
  const urls = node.urls ?? (node.url ? [node.url] : [])
  if (!urls.length) return null

  function providerLabel(url: string) {
    try {
      const u = new URL(url)
      const path = u.pathname.replace(/\/$/, '').split('/').slice(1, 3).join('/')
      return path ? `/${path}` : u.hostname
    } catch { return url }
  }

  return (
    <>
      <div style={{ position: 'fixed', inset: 0, zIndex: 99 }} onClick={onClose} />
      <div
        className="node-popover"
        style={{ left: Math.min(x, window.innerWidth - 340), top: Math.min(y, window.innerHeight - 200) }}
        onClick={e => e.stopPropagation()}
      >
        <div className="node-popover-title">{node.label} — {urls.length} source{urls.length !== 1 ? 's' : ''}</div>
        {urls.map(url => (
          <a
            key={url}
            href={url}
            target="_blank"
            rel="noreferrer"
            className="node-popover-link"
            title={url}
            onClick={onClose}
          >
            <img
              src={`https://www.google.com/s2/favicons?domain=${new URL(url).hostname}&sz=14`}
              alt="" width={14} height={14}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
            <span className="clip-text">{providerLabel(url)}</span>
          </a>
        ))}
      </div>
    </>
  )
}

// ── Topic detail popover (theme / aspect nodes) ───────────────────────────

interface TopicDetailState { node: GraphNode; x: number; y: number }

function TopicDetailPopover({ node, runId, x, y, onClose }: {
  node: GraphNode; runId: string; x: number; y: number; onClose: () => void
}) {
  const [chunks, setChunks] = useState<EvidenceChunk[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const ids = node.evidence_ids ?? []
    if (!ids.length) {
      queueMicrotask(() => setLoading(false))
      return
    }
    Promise.all(ids.map(id => getEvidence(runId, id)))
      .then(results => setChunks(results.filter(Boolean)))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [node, runId])

  const left = Math.min(x, window.innerWidth - 380)
  const top  = Math.min(y, window.innerHeight - 420)

  function faviconUrl(url: string) {
    try { return `https://www.google.com/s2/favicons?domain=${new URL(url).hostname}&sz=14` }
    catch { return '' }
  }

  return (
    <>
      <div style={{ position: 'fixed', inset: 0, zIndex: 199 }} onClick={onClose} />
      <div
        className="topic-detail-popover"
        style={{ left, top }}
        onClick={e => e.stopPropagation()}
      >
        <div className="topic-detail-header">
          <span className={`topic-detail-kind topic-detail-kind--${node.kind}`}>{node.kind}</span>
          <strong className="topic-detail-title">{node.label}</strong>
          <button className="topic-detail-close" onClick={onClose}>✕</button>
        </div>

        {loading && (
          <div style={{ padding: '12px 14px' }}>
            <div className="skeleton skeleton-line skeleton-line--full" />
            <div className="skeleton skeleton-line skeleton-line--medium" style={{ marginTop: 8 }} />
          </div>
        )}

        {!loading && chunks.length === 0 && (
          <p className="topic-detail-empty">No supporting evidence stored for this topic.</p>
        )}

        {chunks.map(chunk => {
          const summary = chunk.summary?.length > 180
            ? chunk.summary.slice(0, 177) + '…'
            : chunk.summary
          return (
          <div key={chunk.id} className="topic-detail-evidence">
            <p className="topic-detail-summary">"{summary}"</p>
            <div className="topic-detail-meta">
              <span className={`sentiment-chip sentiment-chip--${chunk.label}`} style={{ fontSize: 9 }}>
                {chunk.label}
              </span>
              <a
                href={chunk.url}
                target="_blank"
                rel="noreferrer"
                className="topic-detail-link"
                title={chunk.url}
              >
                <img src={faviconUrl(chunk.url)} alt="" width={12} height={12}
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                <span>{new URL(chunk.url).hostname.replace(/^www\./, '')}</span>
                <span>↗</span>
              </a>
            </div>
          </div>
        )})}
      </div>
    </>
  )
}

// ── Component ─────────────────────────────────────────────────────────────

interface Props {
  graph: IdeaGraph
  runId: string
  /** Called when the user left-clicks a sentiment node to scroll to quotes. */
  onNodeClick?: (node: GraphNode) => void
}

export function ForceGraph({ graph, runId, onNodeClick }: Props) {
  const { positions, onContextMenu } = useForce(graph.nodes, graph.edges)
  const [popover, setPopover] = useState<PopoverState | null>(null)
  const [topicDetail, setTopicDetail] = useState<TopicDetailState | null>(null)
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const popoverNode = popover ? graph.nodes.find(n => n.id === popover.nodeId) : null

  function handleLeftClick(node: GraphNode, e: React.MouseEvent) {
    e.stopPropagation()
    if (node.kind === 'source' && (node.urls?.length || node.url)) {
      setTopicDetail(null)
      setPopover({ nodeId: node.id, x: e.clientX + 12, y: e.clientY + 4 })
    } else if (node.kind === 'theme' || node.kind === 'aspect') {
      setPopover(null)
      setTopicDetail({ node, x: e.clientX + 12, y: e.clientY + 4 })
    } else if (node.kind === 'sentiment') {
      onNodeClick?.(node)
    } else if (node.url) {
      window.open(node.url, '_blank')
    }
  }

  function handleMouseEnter(node: GraphNode, e: React.MouseEvent) {
    if (node.kind !== 'theme' && node.kind !== 'aspect') return
    const x = e.clientX, y = e.clientY
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    hoverTimerRef.current = setTimeout(() => {
      setTopicDetail(prev => prev?.node.id === node.id ? prev : { node, x: x + 14, y: y + 4 })
    }, 180)
  }

  function handleMouseLeave() {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
  }

  return (
    <div className="insight-section">
      <h3>
        Idea graph
        <span className="graph-hint">left-click theme/sentiment = jump to quotes · left-click source = links · right-drag = reposition</span>
      </h3>

      <svg
        className="idea-graph idea-graph--force"
        viewBox={`0 0 ${W} ${H}`}
        aria-label="Topic relationship graph"
        onContextMenu={e => e.preventDefault()}
      >
        <defs>
          <marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L7,3 z" fill="rgba(0,212,232,0.3)" />
          </marker>
        </defs>

        {/* Edges */}
        {graph.edges.map(edge => {
          const s = positions.get(edge.source)
          const t = positions.get(edge.target)
          if (!s || !t) return null
          return (
            <line
              key={`${edge.source}→${edge.target}`}
              className={`graph-edge graph-edge--${edge.kind}`}
              x1={s.x} y1={s.y} x2={t.x} y2={t.y}
              strokeWidth={Math.max(1, Math.min(4, edge.weight / 10))}
              markerEnd={edge.kind === 'direction' ? 'url(#arrow)' : undefined}
            />
          )
        })}

        {/* Nodes */}
        {graph.nodes.map(node => {
          const pos = positions.get(node.id)
          if (!pos) return null
          const r = nodeRadius(node)
          const color = KIND_COLOR[node.kind] ?? '#4a6080'
          const hasLinks = node.kind === 'source' && (node.urls?.length || node.url)
          const isClickable = hasLinks || node.kind === 'sentiment' || node.kind === 'theme' || node.kind === 'aspect'
          return (
            <g
              key={node.id}
              className="graph-node"
              style={{ cursor: isClickable ? 'pointer' : 'default' }}
              onClick={e => handleLeftClick(node, e)}
              onContextMenu={e => onContextMenu(node.id, e)}
              onMouseEnter={e => handleMouseEnter(node, e)}
              onMouseLeave={handleMouseLeave}
            >
              <circle cx={pos.x} cy={pos.y} r={r} fill={color} stroke="#0c1018" strokeWidth={2} />
              {/* Link indicator dot */}
              {hasLinks && (
                <circle cx={pos.x + r - 4} cy={pos.y - r + 4} r={3.5}
                  fill="var(--rog-cyan)" stroke="#0c1018" strokeWidth={1} />
              )}
              <text x={pos.x + r + 5} y={pos.y + 4} className="graph-node-label">
                {shortLabel(node.label)}
              </text>
            </g>
          )
        })}
      </svg>

      {/* Legend */}
      <div className="graph-legend">
        {(Object.entries(KIND_COLOR) as [GraphNode['kind'], string][]).map(([kind, color]) => (
          <span key={kind} className="graph-legend-item">
            <span className="graph-legend-dot" style={{ background: color }} />
            {kind}
          </span>
        ))}
      </div>

      {/* Source URL popover */}
      {popover && popoverNode && (
        <NodePopover
          node={popoverNode}
          x={popover.x} y={popover.y}
          onClose={() => setPopover(null)}
        />
      )}

      {/* Topic detail popover (theme / aspect nodes) */}
      {topicDetail && (
        <TopicDetailPopover
          node={topicDetail.node}
          runId={runId}
          x={topicDetail.x} y={topicDetail.y}
          onClose={() => setTopicDetail(null)}
        />
      )}
    </div>
  )
}
