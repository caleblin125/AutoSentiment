import { useCallback, useRef, useState } from 'react'
import { TabBar } from './components/TabBar'
import { RunView } from './components/RunView'
import type { Tab } from './components/TabBar'
import './App.css'

let _tabSeq = 1
function newTab(): Tab {
  return { id: `tab-${_tabSeq++}`, label: 'New Search', status: 'idle' }
}

export default function App() {
  const [tabs, setTabs] = useState<Tab[]>([newTab()])
  const [activeId, setActiveId] = useState(tabs[0].id)

  // Stable per-tab status/label update callback.
  const handleStatusChange = useCallback((tabId: string, status: string, label: string) => {
    setTabs(prev => prev.map(t =>
      t.id === tabId
        ? { ...t, status: status as Tab['status'], label: label !== 'New Search' ? label : t.label }
        : t
    ))
  }, [])

  // Keep per-tab callbacks stable with a ref map so RunView doesn't re-render.
  const cbCache = useRef(new Map<string, (s: string, l: string) => void>())

  function getTabCb(tabId: string) {
    if (!cbCache.current.has(tabId)) {
      cbCache.current.set(tabId, (s, l) => handleStatusChange(tabId, s, l))
    }
    return cbCache.current.get(tabId)!
  }

  function addTab() {
    const tab = newTab()
    setTabs(prev => [...prev, tab])
    setActiveId(tab.id)
  }

  function closeTab(id: string) {
    cbCache.current.delete(id)
    setTabs(prev => {
      const next = prev.filter(t => t.id !== id)
      if (next.length === 0) {
        const fresh = newTab()
        setActiveId(fresh.id)
        return [fresh]
      }
      if (id === activeId) setActiveId(next[next.length - 1].id)
      return next
    })
  }

  return (
    <div className="app">
      {/* ── Top navigation bar ── */}
      <header className="app-header">
        <div className="app-logo">
          <div className="app-logo-mark">AS</div>
          <h1>Auto<span>Sentiment</span></h1>
        </div>
        <p className="app-lede">Multi-source public sentiment intelligence</p>
      </header>

      {/* ── Tab bar ── */}
      <TabBar
        tabs={tabs}
        activeId={activeId}
        onSelect={setActiveId}
        onAdd={addTab}
        onClose={closeTab}
      />

      {/* ── Tab bodies (all rendered; inactive are hidden to preserve state) ── */}
      {tabs.map(tab => (
        <div
          key={tab.id}
          className="app-body"
          role="tabpanel"
          aria-labelledby={`tab-${tab.id}`}
          style={tab.id !== activeId ? { display: 'none' } : undefined}
        >
          <RunView onStatusChange={getTabCb(tab.id)} />
        </div>
      ))}
    </div>
  )
}
