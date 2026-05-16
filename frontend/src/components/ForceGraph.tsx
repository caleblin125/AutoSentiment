/**
 * Spring-physics force-directed graph.
 *
 * Interaction:
 *   Left-click source node → link popover with all URLs from that domain
 *   Left-click theme/aspect node → topic detail popover (evidence + links)
 *   Left-click sentiment node → calls onNodeClick to scroll to quotes
 *   Right-click + drag → reposition / pin node
 *   Scroll wheel → zoom
 *   Left-drag background → pan
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { EvidenceChunk, GraphEdge, GraphNode, IdeaGraph } from '../lib/api'
import { getEvidence } from '../lib/api'

const W = 900
const H = 480

const REPULSION = 9500
const SPRING_K = 0.028
const SPRING_REST_BASE = 130
const DAMPING = 0.82
const CENTER_K = 0.0008  // weakened — let graph spread naturally
const BOUNDARY_FORCE = 0.15  // soft push-back near edges, not hard clamp

interface Vec2 { x: number; y: number }
interface NodeSim { id: string; pos: Vec2; vel: Vec2; fixed: boolean }

const KIND_COLOR: Record<string, string> = {
  topic:     '#e8000d',
  theme:     '#8b5cf6',
  aspect:    '#ff6600',
  sentiment: '#4a6080',
  source:    '#00c8d4',
  url:       '#1a9a9a',
}

const KIND_LABEL: Record<string, string> = {
  topic: 'Search topic',
  theme: 'Theme',
  aspect: 'Directional topic',
  sentiment: 'Sentiment',
  source: 'Source domain',
  url: 'Source link',
}

function nodeRadius(node: GraphNode): number {
  if (node.kind === 'url') return 5
  const base = node.kind === 'topic' ? 22 : node.kind === 'source' ? 12 : 13
  return Math.max(base, Math.min(base + 14, base + Math.sqrt(Math.max(0, node.weight)) * 1.5))
}

function shortLabel(label: string): string {
  return label.length > 20 ? `${label.slice(0, 17)}…` : label
}

function domainLabel(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') }
  catch { return url }
}

// ── Force simulation ──────────────────────────────────────────────────────

function useForce(nodes: GraphNode[], edges: GraphEdge[], storageKey: string) {
  const simRef = useRef<NodeSim[]>([])
  const [positions, setPositions] = useState<Map<string, Vec2>>(new Map())
  const rafRef = useRef(0)
  const tickRef = useRef(0)
  const idxMap = useRef(new Map<string, number>())
  const rightDragRef = useRef<{ id: string } | null>(null)
  const [resetCount, setResetCount] = useState(0)

  function resetLayout() {
    try { localStorage.removeItem(storageKey) } catch { /* ignore */ }
    setResetCount(c => c + 1)
  }

  useLayoutEffect(() => {
    simRef.current = nodes.map((node, i) => {
      const saved = resetCount === 0 ? restorePosition(storageKey, node.id) : null
      const angle = (2 * Math.PI * i) / Math.max(1, nodes.length)
      const r = Math.min(W, H) * 0.28
      return {
        id: node.id,
        pos: saved ?? { x: W / 2 + r * Math.cos(angle), y: H / 2 + r * Math.sin(angle) },
        vel: { x: (Math.random() - 0.5) * 2, y: (Math.random() - 0.5) * 2 },
        fixed: false,
      }
    })
    idxMap.current = new Map(simRef.current.map((s, i) => [s.id, i]))
    tickRef.current = 0
  }, [nodes, storageKey, resetCount])

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
      let totalSpeed = 0
      for (let i = 0; i < states.length; i++) {
        const s = states[i]
        if (!s.fixed) {
          s.vel.x = (s.vel.x + fx[i]) * DAMPING
          s.vel.y = (s.vel.y + fy[i]) * DAMPING
          // Soft boundary: push back gently from edges instead of hard clamp.
          const margin = 60
          if (s.pos.x < margin) s.vel.x += BOUNDARY_FORCE * (margin - s.pos.x) / margin
          if (s.pos.x > W - margin) s.vel.x -= BOUNDARY_FORCE * (s.pos.x - (W - margin)) / margin
          if (s.pos.y < margin) s.vel.y += BOUNDARY_FORCE * (margin - s.pos.y) / margin
          if (s.pos.y > H - margin) s.vel.y -= BOUNDARY_FORCE * (s.pos.y - (H - margin)) / margin
          s.pos.x += s.vel.x
          s.pos.y += s.vel.y
        }
        totalSpeed += Math.abs(s.vel.x) + Math.abs(s.vel.y)
        next.set(s.id, { x: s.pos.x, y: s.pos.y })
      }
      setPositions(next)
      persistPositions(storageKey, states)
      tickRef.current += 1
      const averageSpeed = totalSpeed / Math.max(1, states.length)
      // Continue simulation: high-activity phase (first 240 ticks), then
      // gentle continuation every 4 frames to respond to user drags.
      if (tickRef.current < 240 && averageSpeed > 0.015) {
        rafRef.current = requestAnimationFrame(tick)
      } else if (averageSpeed > 0.001) {
        // Keep settling slowly — no freeze on partial motion.
        rafRef.current = requestAnimationFrame(tick)
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [nodes, edges, storageKey, resetCount])

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
      setPositions(new Map(simRef.current.map(state => [state.id, { x: state.pos.x, y: state.pos.y }])))
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

  return { positions, onContextMenu, resetLayout }
}

function restorePosition(storageKey: string, nodeId: string): Vec2 | null {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Record<string, Vec2>
    const pos = parsed[nodeId]
    if (!pos || typeof pos.x !== 'number' || typeof pos.y !== 'number') return null
    return pos
  } catch {
    return null
  }
}

function persistPositions(storageKey: string, states: NodeSim[]) {
  try {
    const payload: Record<string, Vec2> = {}
    for (const state of states) payload[state.id] = { x: state.pos.x, y: state.pos.y }
    localStorage.setItem(storageKey, JSON.stringify(payload))
  } catch {
    // Ignore storage quota and private browsing failures.
  }
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
          <div className="topic-detail-loading">
            <div className="skeleton skeleton-line skeleton-line--full" />
            <div className="skeleton skeleton-line skeleton-line--medium skeleton-line--mb" />
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
              <span className={`sentiment-chip sentiment-chip--${chunk.label} sentiment-chip--xs`}>
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
  const [hiddenKinds, setHiddenKinds] = useState<Set<GraphNode['kind']>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState<Vec2>({ x: 0, y: 0 })
  const [isPanning, setIsPanning] = useState(false)
  const panRef = useRef<{ startX: number; startY: number; startPan: Vec2 } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(() => graph.nodes[0] ?? null)
  const [focusMode, setFocusMode] = useState(false)
  const [showMinimap, setShowMinimap] = useState(true)

  const visibleNodes = useMemo(() => graph.nodes.filter(node => {
    if (node.kind === 'sentiment' && node.weight <= 0) return false
    if (hiddenKinds.has(node.kind as GraphNode['kind'])) return false
    return true
  }), [graph.nodes, hiddenKinds])

  const visibleEdges = useMemo(() => {
    const visibleIds = new Set(visibleNodes.map(node => node.id))
    return graph.edges.filter(edge => visibleIds.has(edge.source) && visibleIds.has(edge.target))
  }, [graph.edges, visibleNodes])

  const { positions, onContextMenu, resetLayout } = useForce(visibleNodes, visibleEdges, `autosentiment_graph:${runId}`)
  const [popover, setPopover] = useState<PopoverState | null>(null)
  const [topicDetail, setTopicDetail] = useState<TopicDetailState | null>(null)
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const searchLower = searchQuery.toLowerCase().trim()
  const matchingIds = useMemo(() => {
    if (!searchLower) return null
    return new Set(visibleNodes.filter(n => n.label.toLowerCase().includes(searchLower)).map(n => n.id))
  }, [visibleNodes, searchLower])

  // Focus mode: when active, only the selected node and its direct neighbors are visible.
  const neighborIds = useMemo(() => {
    if (!focusMode || !selectedNode) return null
    const ids = new Set([selectedNode.id])
    for (const e of visibleEdges) {
      if (e.source === selectedNode.id) ids.add(e.target)
      if (e.target === selectedNode.id) ids.add(e.source)
    }
    return ids
  }, [focusMode, selectedNode, visibleEdges])

  const popoverNode = popover ? graph.nodes.find(n => n.id === popover.nodeId) : null

  function toggleKind(kind: GraphNode['kind']) {
    setHiddenKinds(prev => {
      const next = new Set(prev)
      if (next.has(kind)) next.delete(kind)
      else next.add(kind)
      return next
    })
  }

  function handleLeftClick(node: GraphNode, e: React.MouseEvent) {
    e.stopPropagation()
    setSelectedNode(prev => {
      // Clicking the same node again toggles focus mode off
      if (prev?.id === node.id) { setFocusMode(f => !f); return node }
      setFocusMode(true)
      return node
    })
    if (node.kind === 'url') {
      if (node.url) window.open(node.url, '_blank', 'noreferrer')
    } else if (node.kind === 'source' && (node.urls?.length || node.url)) {
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

  // Attach a non-passive wheel listener so preventDefault() actually works.
  // React's synthetic onWheel is passive by default in modern browsers,
  // which means e.preventDefault() inside it is ignored and the page scrolls.
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      setZoom(z => Math.max(0.45, Math.min(4, z * (e.deltaY > 0 ? 0.88 : 1.13))))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, []) // svgRef.current is stable after mount

  // Pan via left-click drag on background (SVG element directly)
  function handleSvgMouseDown(e: React.MouseEvent<SVGSVGElement>) {
    if (e.button !== 0) return
    if ((e.target as SVGElement).closest('.graph-node')) return
    setFocusMode(false)
    panRef.current = { startX: e.clientX, startY: e.clientY, startPan: pan }
    setIsPanning(true)
    const onMove = (me: MouseEvent) => {
      if (!panRef.current) return
      setPan({
        x: panRef.current.startPan.x + (me.clientX - panRef.current.startX) / zoom,
        y: panRef.current.startPan.y + (me.clientY - panRef.current.startY) / zoom,
      })
    }
    const onUp = () => {
      panRef.current = null
      setIsPanning(false)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  function handleResetView() {
    setZoom(1)
    setPan({ x: 0, y: 0 })
    resetLayout()
  }

  function handleFitView() {
    if (!positions.size) return
    const posArr = Array.from(positions.values())
    const xs = posArr.map(p => p.x)
    const ys = posArr.map(p => p.y)
    const minX = Math.min(...xs) - 60, maxX = Math.max(...xs) + 60
    const minY = Math.min(...ys) - 50, maxY = Math.max(...ys) + 50
    const newZoom = Math.max(0.3, Math.min(2.5, Math.min(W / (maxX - minX), H / (maxY - minY))))
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2
    setZoom(newZoom)
    setPan({ x: W / (2 * newZoom) - cx, y: H / (2 * newZoom) - cy })
  }

  return (
    <div className="insight-section">
      <h3>Idea graph</h3>

      {/* Controls row */}
      <div className="graph-controls">
        <input
          type="search"
          className="graph-search"
          placeholder="Search nodes…"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
        />
        <button
          type="button"
          className="btn-secondary graph-ctrl-btn"
          onClick={() => setZoom(z => Math.min(4, z * 1.25))}
          title="Zoom in"
        >+</button>
        <button
          type="button"
          className="btn-secondary graph-ctrl-btn"
          onClick={() => setZoom(z => Math.max(0.45, z * 0.8))}
          title="Zoom out"
        >−</button>
        <button
          type="button"
          className="btn-secondary graph-ctrl-btn"
          onClick={handleFitView}
          title="Fit all nodes in view"
        >⊡</button>
        <button
          type="button"
          className="btn-secondary graph-ctrl-btn"
          onClick={handleResetView}
          title="Reset zoom and layout"
        >⟳</button>
        {focusMode && (
          <button
            type="button"
            className="btn-secondary graph-ctrl-btn graph-ctrl-btn--focus"
            onClick={() => setFocusMode(false)}
            title="Exit focus mode (Escape)"
          >
            <span className="graph-focus-dot" />Focus
          </button>
        )}
        <button
          type="button"
          className={`btn-secondary graph-ctrl-btn${showMinimap ? ' graph-ctrl-btn--active' : ''}`}
          onClick={() => setShowMinimap(v => !v)}
          title="Toggle minimap"
        >⊞</button>
        <span className="graph-hint">
          Click to focus · Right-drag pin · Scroll zoom · Drag bg to pan
        </span>
      </div>

      <div className="graph-workspace">
        <div style={{ position: 'relative', minWidth: 0 }}>
        <svg
          ref={svgRef}
          className="idea-graph idea-graph--force"
          viewBox={`${-pan.x} ${-pan.y} ${W / zoom} ${H / zoom}`}
          aria-label="Topic relationship graph"
          onContextMenu={e => e.preventDefault()}
          onMouseDown={handleSvgMouseDown}
          style={{ cursor: isPanning ? 'grabbing' : 'grab' }}
        >
          <defs>
            <marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
              <path d="M0,0 L0,6 L7,3 z" fill="var(--rog-cyan)" opacity="0.35" />
            </marker>
            {/* Per-kind radial gradients for nicer nodes */}
            {Object.entries(KIND_COLOR).map(([kind, color]) => (
              <radialGradient key={kind} id={`grad-${kind}`} cx="35%" cy="30%" r="70%">
                <stop offset="0%" stopColor={color} stopOpacity="1" />
                <stop offset="100%" stopColor={color} stopOpacity="0.6" />
              </radialGradient>
            ))}
            <filter id="glow-topic" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
            <filter id="glow-node" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="2.5" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {visibleEdges.map(edge => {
            const s = positions.get(edge.source)
            const t = positions.get(edge.target)
            if (!s || !t) return null
            const dimmedBySearch = matchingIds && !matchingIds.has(edge.source) && !matchingIds.has(edge.target)
            const dimmedByFocus = neighborIds && !neighborIds.has(edge.source) && !neighborIds.has(edge.target)
            const dimmed = dimmedBySearch || dimmedByFocus
            const isActive = focusMode && selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id)
            // Quadratic bezier — slight perpendicular curve for organic look
            const mx = (s.x + t.x) / 2 - (t.y - s.y) * 0.1
            const my = (s.y + t.y) / 2 + (t.x - s.x) * 0.1
            const d = `M ${s.x} ${s.y} Q ${mx} ${my} ${t.x} ${t.y}`
            const sw = Math.max(1, Math.min(4, edge.weight / 10))
            return (
              <path
                key={`${edge.source}→${edge.target}`}
                className={`graph-edge graph-edge--${edge.kind}${isActive ? ' graph-edge--active' : ''}`}
                d={d}
                fill="none"
                strokeWidth={isActive ? sw + 0.5 : sw}
                markerEnd={edge.kind === 'direction' ? 'url(#arrow)' : undefined}
                opacity={dimmed ? 0.1 : 1}
              >
                <title>{edge.kind} · weight {edge.weight}</title>
              </path>
            )
          })}

          {visibleNodes.map(node => {
            const pos = positions.get(node.id)
            if (!pos) return null
            const r = nodeRadius(node)
            const isUrl = node.kind === 'url'
            const hasLinks = (node.kind === 'source' || isUrl) && (node.urls?.length || node.url)
            const isClickable = hasLinks || node.kind === 'sentiment' || node.kind === 'theme' || node.kind === 'aspect'
            const dimmedBySearch = matchingIds && !matchingIds.has(node.id)
            const dimmedByFocus = neighborIds && !neighborIds.has(node.id)
            const dimmed = dimmedBySearch || dimmedByFocus
            const isSelected = selectedNode?.id === node.id
            const filter = node.kind === 'topic' ? 'url(#glow-topic)' : isSelected ? 'url(#glow-node)' : undefined

            return (
              <g
                key={node.id}
                className={`graph-node${isSelected ? ' graph-node--selected' : ''}`}
                style={{ cursor: isClickable ? 'pointer' : 'default', opacity: dimmed ? 0.14 : 1 }}
                onClick={e => handleLeftClick(node, e)}
                onContextMenu={e => onContextMenu(node.id, e)}
                onMouseEnter={e => handleMouseEnter(node, e)}
                onMouseLeave={handleMouseLeave}
                filter={filter}
              >
                {/* Pulsing ring on selected node */}
                {isSelected && (
                  <circle
                    className="graph-pulse-ring"
                    cx={pos.x} cy={pos.y}
                    r={r + 7}
                    fill="none"
                    stroke={KIND_COLOR[node.kind] ?? 'var(--rog-cyan)'}
                    strokeWidth={1.5}
                  />
                )}
                {isUrl ? (
                  // URL nodes: small diamond shape for visual distinction
                  <rect
                    x={pos.x - r} y={pos.y - r} width={r * 2} height={r * 2}
                    rx={1.5}
                    fill={`url(#grad-url)`}
                    stroke="var(--graph-node-stroke)" strokeWidth={1}
                    transform={`rotate(45 ${pos.x} ${pos.y})`}
                  />
                ) : (
                  <circle cx={pos.x} cy={pos.y} r={r} fill={`url(#grad-${node.kind})`}
                    stroke={isSelected ? 'var(--rog-cyan)' : 'var(--graph-node-stroke)'}
                    strokeWidth={isSelected ? 2.5 : node.kind === 'topic' ? 2.5 : 1.5}
                  />
                )}
                {/* Favicon on source nodes */}
                {node.kind === 'source' && node.url && (() => {
                  const fv = (() => { try { return `https://www.google.com/s2/favicons?domain=${new URL(node.url!).hostname}&sz=14` } catch { return '' } })()
                  if (!fv) return null
                  return (
                    <image
                      href={fv}
                      x={pos.x - r + 2} y={pos.y - r + 2}
                      width={r * 2 - 4} height={r * 2 - 4}
                      onError={e => { (e.target as SVGImageElement).style.display = 'none' }}
                    />
                  )
                })()}
                {hasLinks && !isUrl && (
                  <circle cx={pos.x + r - 4} cy={pos.y - r + 4} r={3.5}
                    fill="var(--rog-cyan)" stroke="var(--graph-node-stroke)" strokeWidth={1} />
                )}
                {matchingIds?.has(node.id) && (
                  <circle cx={pos.x} cy={pos.y} r={r + 5} fill="none"
                    stroke="var(--rog-cyan)" strokeWidth={2} strokeDasharray="4 2" opacity={0.8} />
                )}
                {!isUrl && (zoom >= 0.65 || node.kind === 'topic' || node.kind === 'theme' || node.kind === 'aspect' || isSelected) && (
                  <text x={pos.x + r + 5} y={pos.y + 4} className="graph-node-label">
                    {shortLabel(node.label)}
                  </text>
                )}
                {isUrl && isSelected && (
                  <text x={pos.x + r + 4} y={pos.y + 3} className="graph-node-label graph-node-label--url">
                    {shortLabel(node.label)}
                  </text>
                )}
              </g>
            )
          })}
        </svg>

        {/* Minimap — corner thumbnail showing full graph + current viewport */}
        {showMinimap && positions.size > 0 && (() => {
          const MM_W = 160, MM_H = 96
          const scX = MM_W / W, scY = MM_H / H
          const vpX = -pan.x, vpY = -pan.y
          const vpW = W / zoom, vpH = H / zoom
          return (
            <div className="graph-minimap" title="Minimap — click to close">
              <svg
                width={MM_W} height={MM_H}
                onClick={() => setShowMinimap(false)}
                style={{ cursor: 'pointer', display: 'block' }}
              >
                {visibleEdges.map(edge => {
                  const s = positions.get(edge.source), t = positions.get(edge.target)
                  if (!s || !t) return null
                  return <line key={`mm-${edge.source}-${edge.target}`}
                    x1={s.x * scX} y1={s.y * scY} x2={t.x * scX} y2={t.y * scY}
                    stroke="var(--border)" strokeWidth={0.5} opacity={0.6} />
                })}
                {visibleNodes.map(node => {
                  const pos = positions.get(node.id)
                  if (!pos) return null
                  const isFocused = !neighborIds || neighborIds.has(node.id)
                  return <circle key={`mm-${node.id}`}
                    cx={pos.x * scX} cy={pos.y * scY}
                    r={node.kind === 'topic' ? 4 : node.kind === 'url' ? 1 : 2.5}
                    fill={KIND_COLOR[node.kind] ?? '#888'}
                    opacity={isFocused ? (node.id === selectedNode?.id ? 1 : 0.75) : 0.2} />
                })}
                {/* Viewport rectangle */}
                <rect
                  x={Math.max(0, vpX * scX)} y={Math.max(0, vpY * scY)}
                  width={Math.min(MM_W - Math.max(0, vpX * scX), vpW * scX)}
                  height={Math.min(MM_H - Math.max(0, vpY * scY), vpH * scY)}
                  fill="var(--rog-cyan)" fillOpacity={0.07}
                  stroke="var(--rog-cyan)" strokeWidth={1} strokeOpacity={0.5}
                />
              </svg>
            </div>
          )
        })()}
        </div>

        {selectedNode && (
          <aside className="graph-detail-panel">
            <span className={`topic-detail-kind topic-detail-kind--${selectedNode.kind}`}>
              {KIND_LABEL[selectedNode.kind]}
            </span>
            <h4>{selectedNode.label}</h4>
            <div className="graph-detail-metrics">
              <span>Weight</span><strong>{Math.round(selectedNode.weight)}</strong>
              <span>Connections</span><strong>{graph.edges.filter(e => e.source === selectedNode.id || e.target === selectedNode.id).length}</strong>
              <span>Evidence</span><strong>{selectedNode.evidence_ids?.length ?? 0}</strong>
              <span>Links</span><strong>{selectedNode.urls?.length ?? (selectedNode.url ? 1 : 0)}</strong>
            </div>
            {selectedNode.urls?.slice(0, 5).map(url => (
              <a key={url} href={url} target="_blank" rel="noreferrer" className="graph-detail-link">
                {domainLabel(url)}
              </a>
            ))}
            {(selectedNode.kind === 'theme' || selectedNode.kind === 'aspect') && selectedNode.evidence_ids?.length ? (
              <button
                type="button"
                className="btn-secondary btn-secondary--compact graph-evidence-btn"
                onClick={() => setTopicDetail({ node: selectedNode, x: 200, y: 200 })}
              >
                View evidence ↗
              </button>
            ) : null}
          </aside>
        )}
      </div>

      {/* Interactive legend */}
      <div className="graph-legend">
        {(Object.entries(KIND_COLOR) as [string, string][]).map(([kind, color]) => (
          <button
            key={kind}
            type="button"
            className={`graph-legend-item graph-legend-btn${hiddenKinds.has(kind as GraphNode['kind']) ? ' graph-legend-btn--hidden' : ''}`}
            onClick={() => toggleKind(kind as GraphNode['kind'])}
            title={hiddenKinds.has(kind as GraphNode['kind']) ? `Show ${kind} nodes` : `Hide ${kind} nodes`}
          >
            <span className="graph-legend-dot" style={{ background: hiddenKinds.has(kind as GraphNode['kind']) ? 'var(--border)' : color }} />
            {KIND_LABEL[kind]}
          </button>
        ))}
        <span className="graph-legend-hint">Right-drag pin · Scroll zoom · Click to open · Drag bg to pan</span>
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
