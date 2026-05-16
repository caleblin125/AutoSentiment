/**
 * App root — manages tabs, session persistence, and global state.
 *
 * Session persistence: tab list + active tab saved to localStorage so the
 * user continues where they left off on reload.
 *
 * Close tab = kill task: when a tab with a running task is closed, the
 * backend cancel endpoint is called before removing it from state.
 */
import { useCallback, useEffect, useState } from 'react'
import { TabBar } from './components/TabBar'
import { RunView } from './components/RunView'
import { DevOverlay } from './components/DevOverlay'
import type { Tab } from './components/TabBar'
import { cancelRun } from './lib/api'
import './App.css'

const SESSION_KEY = 'autosentiment_session'
const MAX_PERSISTED_TABS = 10

interface PersistedTab {
  id: string; label: string; status: Tab['status']; runId?: string; topic?: string
}
interface PersistedSession { tabs: PersistedTab[]; activeId: string }

let _tabSeq = 1
function newTab(): Tab {
  return { id: `tab-${_tabSeq++}`, label: 'New Search', status: 'idle' }
}

function loadSession(): PersistedSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    return JSON.parse(raw) as PersistedSession
  } catch {
    return null
  }
}

function saveSession(tabs: Tab[], activeId: string) {
  try {
    const data: PersistedSession = {
      tabs: tabs.slice(0, MAX_PERSISTED_TABS).map(t => ({
        id: t.id, label: t.label, status: t.status, runId: t.runId,
      })),
      activeId,
    }
    localStorage.setItem(SESSION_KEY, JSON.stringify(data))
  } catch {
    // storage quota — ignore
  }
}

function TabPanel({
  tab,
  activeId,
  handleStatusChange,
  openRunInNewTab,
  devMode,
}: {
  tab: Tab
  activeId: string
  handleStatusChange: (tabId: string, status: string, label: string, runId?: string) => void
  openRunInNewTab: (runId: string, topic: string) => void
  devMode: boolean
}) {
  const onStatusChange = useCallback(
    (status: string, label: string, runId?: string) => handleStatusChange(tab.id, status, label, runId),
    [handleStatusChange, tab.id],
  )

  return (
    <div
      className="app-body"
      role="tabpanel"
      aria-labelledby={`tab-${tab.id}`}
      style={tab.id !== activeId ? { display: 'none' } : undefined}
    >
      <RunView
        onStatusChange={onStatusChange}
        onOpenRunInNewTab={openRunInNewTab}
        initialRunId={tab.runId}
        devMode={devMode}
      />
    </div>
  )
}

export default function App() {
  const [devMode, setDevMode] = useState(false)

  // ── Restore session from localStorage ───────────────────────────────────
  const [tabs, setTabs] = useState<Tab[]>(() => {
    const session = loadSession()
    if (session?.tabs?.length) {
      // Bump _tabSeq past persisted IDs.
      session.tabs.forEach(t => {
        const n = parseInt(t.id.replace('tab-', ''))
        if (!isNaN(n) && n >= _tabSeq) _tabSeq = n + 1
      })
      return session.tabs.map(t => ({
        ...t,
        // Treat previously-running tabs as their terminal state on reload.
        status: t.status === 'running' ? 'idle' : t.status,
      }))
    }
    return [newTab()]
  })

  const [activeId, setActiveId] = useState<string>(() => {
    const session = loadSession()
    return session?.activeId ?? tabs[0].id
  })

  // ── Persist whenever tabs or active tab changes ──────────────────────────
  useEffect(() => {
    saveSession(tabs, activeId)
  }, [tabs, activeId])

  // ── Dev mode toggle (Ctrl+Shift+D) ───────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault()
        setDevMode(d => !d)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // ── Stable per-tab callback (status + label + runId) ────────────────────
  const handleStatusChange = useCallback((tabId: string, status: string, label: string, runId?: string) => {
    setTabs(prev => prev.map(t =>
      t.id === tabId
        ? {
            ...t,
            status: status as Tab['status'],
            label: label !== 'New Search' ? label : t.label,
            runId: runId ?? t.runId,
          }
        : t
    ))
  }, [])

  // ── Open a historic run in a new tab ─────────────────────────────────────
  const openRunInNewTab = useCallback((runId: string, topic: string) => {
    const tab = newTab()
    tab.label = topic
    tab.runId = runId
    tab.status = 'completed'
    setTabs(prev => [...prev, tab])
    setActiveId(tab.id)
    // The RunView for this new tab will receive initialRunId and replay events.
    // We store the runId in the tab so the TabBar shows the correct status.
  }, [])

  function addTab() {
    const tab = newTab()
    setTabs(prev => [...prev, tab])
    setActiveId(tab.id)
  }

  async function closeTab(id: string) {
    // Cancel any running task on this tab before removing it.
    const tab = tabs.find(t => t.id === id)
    if (tab?.runId && tab.status === 'running') {
      cancelRun(tab.runId).catch(() => {})
    }
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

  const runningCount = tabs.filter(t => t.status === 'running').length

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-logo">
          <div className="app-logo-mark">AS</div>
          <h1>Auto<span>Sentiment</span></h1>
        </div>
        <p className="app-lede">Multi-source public sentiment intelligence</p>
        <button
          className="dev-toggle-btn"
          onClick={() => setDevMode(d => !d)}
          title="Dev mode (Ctrl+Shift+D)"
          aria-pressed={devMode}
        >
          {devMode ? '⚙ dev on' : '⚙'}
        </button>
      </header>

      <TabBar
        tabs={tabs}
        activeId={activeId}
        runningCount={runningCount}
        onSelect={setActiveId}
        onAdd={addTab}
        onClose={closeTab}
      />

      {tabs.map(tab => (
        <TabPanel
          key={tab.id}
          tab={tab}
          activeId={activeId}
          handleStatusChange={handleStatusChange}
          openRunInNewTab={openRunInNewTab}
          devMode={devMode}
        />
      ))}

      {devMode && <DevOverlay onClose={() => setDevMode(false)} />}
    </div>
  )
}
