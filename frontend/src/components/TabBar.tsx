import { useRef, useState } from 'react'

export interface Tab {
  id: string
  label: string
  status: 'idle' | 'running' | 'expanding' | 'completed' | 'cancelled' | 'error' | 'cached'
  runId?: string   // tracks active runId so close can cancel the task
}

interface Props {
  tabs: Tab[]
  activeId: string
  runningCount: number
  onSelect: (id: string) => void
  onAdd: () => void
  onClose: (id: string) => void
  onReorder: (dragId: string, dropId: string) => void
}

export function TabBar({ tabs, activeId, runningCount, onSelect, onAdd, onClose, onReorder }: Props) {
  const [dragId, setDragId] = useState<string | null>(null)
  const [dragOverId, setDragOverId] = useState<string | null>(null)
  const dragNodeRef = useRef<HTMLButtonElement | null>(null)

  function handleDragStart(e: React.DragEvent<HTMLButtonElement>, id: string) {
    setDragId(id)
    dragNodeRef.current = e.currentTarget
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', id)
    // Ghost image: use the tab itself
    setTimeout(() => { if (dragNodeRef.current) dragNodeRef.current.style.opacity = '0.4' }, 0)
  }

  function handleDragEnd() {
    if (dragNodeRef.current) dragNodeRef.current.style.opacity = ''
    setDragId(null)
    setDragOverId(null)
    dragNodeRef.current = null
  }

  function handleDragOver(e: React.DragEvent<HTMLButtonElement>, id: string) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (id !== dragId) setDragOverId(id)
  }

  function handleDrop(e: React.DragEvent<HTMLButtonElement>, dropId: string) {
    e.preventDefault()
    const fromId = e.dataTransfer.getData('text/plain')
    if (fromId && fromId !== dropId) onReorder(fromId, dropId)
    setDragId(null)
    setDragOverId(null)
  }

  return (
    <div className="tab-bar" role="tablist">
      {tabs.map(tab => (
        <button
          key={tab.id}
          id={`tab-${tab.id}`}
          role="tab"
          aria-selected={tab.id === activeId}
          draggable
          className={[
            'tab',
            tab.id === activeId ? 'tab--active' : '',
            tab.id === dragOverId ? 'tab--drag-over' : '',
            tab.id === dragId ? 'tab--dragging' : '',
          ].filter(Boolean).join(' ')}
          onClick={() => onSelect(tab.id)}
          onDragStart={e => handleDragStart(e, tab.id)}
          onDragEnd={handleDragEnd}
          onDragOver={e => handleDragOver(e, tab.id)}
          onDrop={e => handleDrop(e, tab.id)}
        >
          <span className={`tab-status-dot tab-status-dot--${tab.status}`} />
          <span className="tab-label" title={tab.label}>{tab.label}</span>
          {tabs.length > 1 && (
            <button
              className="tab-close"
              aria-label={`Close ${tab.label}`}
              onClick={e => { e.stopPropagation(); onClose(tab.id) }}
            >
              ✕
            </button>
          )}
        </button>
      ))}
      <button className="tab-add" aria-label="New search tab" onClick={onAdd} title="New search">＋</button>

      {runningCount > 0 && (
        <span className="running-count-pill" title={`${runningCount} analysis running`}>
          <span className="running-count-spinner" />
          {runningCount} running
        </span>
      )}
    </div>
  )
}
