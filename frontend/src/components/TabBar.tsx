export interface Tab {
  id: string
  label: string
  status: 'idle' | 'running' | 'completed' | 'cancelled' | 'error' | 'cached'
  runId?: string   // tracks active runId so close can cancel the task
}

interface Props {
  tabs: Tab[]
  activeId: string
  runningCount: number
  onSelect: (id: string) => void
  onAdd: () => void
  onClose: (id: string) => void
}

export function TabBar({ tabs, activeId, runningCount, onSelect, onAdd, onClose }: Props) {
  return (
    <div className="tab-bar" role="tablist">
      {tabs.map(tab => (
        <button
          key={tab.id}
          id={`tab-${tab.id}`}
          role="tab"
          aria-selected={tab.id === activeId}
          className={`tab${tab.id === activeId ? ' tab--active' : ''}`}
          onClick={() => onSelect(tab.id)}
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

      {/* Global running count pill */}
      {runningCount > 0 && (
        <span className="running-count-pill" title={`${runningCount} analysis running`}>
          <span className="running-count-spinner" />
          {runningCount} running
        </span>
      )}
    </div>
  )
}
