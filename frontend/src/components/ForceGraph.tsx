/**
 * Spring-physics force-directed graph.
 *
 * Physics model (Verlet-style, runs in rAF loop):
 *   - Coulomb repulsion between every pair of nodes
 *   - Hooke attraction along each edge (rest length proportional to inverse weight)
 *   - Weak centering force toward viewport origin
 *   - Velocity damping each frame
 *
 * Nodes are draggable: pointer-captured so drags don't stutter even when the
 * cursor leaves the node circle.
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { GraphEdge, GraphNode, IdeaGraph } from '../lib/api'

const W = 900
const H = 480

const REPULSION = 9000
const SPRING_K = 0.035
const SPRING_REST_BASE = 130
const DAMPING = 0.86
const CENTER_K = 0.004

interface Vec2 { x: number; y: number }
interface NodeSim { id: string; pos: Vec2; vel: Vec2; fixed: boolean }

// ── colours ────────────────────────────────────────────────────────────────
const KIND_COLOR: Record<GraphNode['kind'], string> = {
  topic: '#2563eb',
  theme: '#8b5cf6',
  aspect: '#f59e0b',
  sentiment: '#94a3b8',
  source: '#14b8a6',
}

const KIND_RADIUS_BASE: Record<GraphNode['kind'], number> = {
  topic: 22,
  theme: 14,
  aspect: 13,
  sentiment: 11,
  source: 11,
}

function nodeRadius(node: GraphNode): number {
  const base = KIND_RADIUS_BASE[node.kind] ?? 11
  return Math.max(base, Math.min(base + 14, base + Math.sqrt(Math.max(0, node.weight)) * 1.6))
}

function shortLabel(label: string): string {
  return label.length > 22 ? `${label.slice(0, 19)}…` : label
}

// ── force simulation hook ─────────────────────────────────────────────────
function useForce(nodes: GraphNode[], edges: GraphEdge[]) {
  const simRef = useRef<NodeSim[]>([])
  const [positions, setPositions] = useState<Map<string, Vec2>>(new Map())
  const rafRef = useRef(0)
  const idToIdx = useRef(new Map<string, number>())

  // Reinitialise when node set changes.
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
    idToIdx.current = new Map(simRef.current.map((s, i) => [s.id, i]))
  }, [nodes])

  useEffect(() => {
    function tick() {
      const states = simRef.current
      if (states.length === 0) { rafRef.current = requestAnimationFrame(tick); return }

      const fx = new Float32Array(states.length)
      const fy = new Float32Array(states.length)

      // Coulomb repulsion between every pair.
      for (let i = 0; i < states.length; i++) {
        for (let j = i + 1; j < states.length; j++) {
          const dx = states[i].pos.x - states[j].pos.x
          const dy = states[i].pos.y - states[j].pos.y
          const d2 = dx * dx + dy * dy + 1
          const f = REPULSION / d2
          const dist = Math.sqrt(d2)
          fx[i] += (dx / dist) * f
          fy[i] += (dy / dist) * f
          fx[j] -= (dx / dist) * f
          fy[j] -= (dy / dist) * f
        }
      }

      // Hooke spring attraction along each edge.
      for (const edge of edges) {
        const si = idToIdx.current.get(edge.source)
        const ti = idToIdx.current.get(edge.target)
        if (si === undefined || ti === undefined) continue
        const dx = states[ti].pos.x - states[si].pos.x
        const dy = states[ti].pos.y - states[si].pos.y
        const dist = Math.sqrt(dx * dx + dy * dy) + 0.01
        // Heavier edges pull nodes closer together.
        const rest = SPRING_REST_BASE * (1 + 1 / Math.max(1, edge.weight))
        const stretch = dist - rest
        const f = SPRING_K * stretch
        fx[si] += (dx / dist) * f
        fy[si] += (dy / dist) * f
        fx[ti] -= (dx / dist) * f
        fy[ti] -= (dy / dist) * f
      }

      // Centering force.
      const cx = W / 2
      const cy = H / 2
      for (let i = 0; i < states.length; i++) {
        fx[i] += (cx - states[i].pos.x) * CENTER_K
        fy[i] += (cy - states[i].pos.y) * CENTER_K
      }

      // Verlet integration + boundary clamp.
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

  function onPointerDown(nodeId: string, e: React.PointerEvent<SVGElement>) {
    e.preventDefault()
    ;(e.currentTarget as SVGElement).setPointerCapture(e.pointerId)
    const state = simRef.current.find(s => s.id === nodeId)
    if (!state) return
    state.fixed = true
    state.vel = { x: 0, y: 0 }
  }

  function onPointerMove(nodeId: string, e: React.PointerEvent<SVGElement>) {
    const state = simRef.current.find(s => s.id === nodeId)
    if (!state?.fixed) return
    const svg = (e.currentTarget as SVGElement).ownerSVGElement
    if (!svg) return
    const pt = svg.createSVGPoint()
    pt.x = e.clientX
    pt.y = e.clientY
    const svgPt = pt.matrixTransform(svg.getScreenCTM()!.inverse())
    state.pos = { x: svgPt.x, y: svgPt.y }
    state.vel = { x: 0, y: 0 }
  }

  function onPointerUp(nodeId: string, e: React.PointerEvent<SVGElement>) {
    ;(e.currentTarget as SVGElement).releasePointerCapture(e.pointerId)
    const state = simRef.current.find(s => s.id === nodeId)
    if (state) state.fixed = false
  }

  return { positions, onPointerDown, onPointerMove, onPointerUp }
}

// ── component ──────────────────────────────────────────────────────────────
interface Props { graph: IdeaGraph }

export function ForceGraph({ graph }: Props) {
  const { positions, onPointerDown, onPointerMove, onPointerUp } = useForce(graph.nodes, graph.edges)

  return (
    <div className="insight-section">
      <h3>Idea graph <span className="graph-hint">drag to rearrange</span></h3>
      <svg
        className="idea-graph idea-graph--force"
        viewBox={`0 0 ${W} ${H}`}
        aria-label="Topic relationship graph"
      >
        <defs>
          {/* Arrow marker for directed edges */}
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#cbd5e1" />
          </marker>
        </defs>

        {/* Edges */}
        {graph.edges.map(edge => {
          const s = positions.get(edge.source)
          const t = positions.get(edge.target)
          if (!s || !t) return null
          const sw = Math.max(1, Math.min(5, edge.weight / 8))
          return (
            <line
              key={`${edge.source}→${edge.target}`}
              className={`graph-edge graph-edge--${edge.kind}`}
              x1={s.x} y1={s.y}
              x2={t.x} y2={t.y}
              strokeWidth={sw}
              markerEnd={edge.kind === 'direction' ? 'url(#arrow)' : undefined}
            />
          )
        })}

        {/* Nodes */}
        {graph.nodes.map(node => {
          const pos = positions.get(node.id)
          if (!pos) return null
          const r = nodeRadius(node)
          const color = KIND_COLOR[node.kind] ?? '#94a3b8'
          return (
            <g
              key={node.id}
              className="graph-node"
              style={{ cursor: 'grab' }}
              onPointerDown={e => onPointerDown(node.id, e)}
              onPointerMove={e => onPointerMove(node.id, e)}
              onPointerUp={e => onPointerUp(node.id, e)}
            >
              <circle
                cx={pos.x} cy={pos.y} r={r}
                fill={color}
                stroke="#fff"
                strokeWidth={2}
              />
              <text
                x={pos.x + r + 6}
                y={pos.y + 4}
                className="graph-node-label"
              >
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
    </div>
  )
}
