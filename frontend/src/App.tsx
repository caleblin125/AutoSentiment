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
import { CompareView } from './components/CompareView'
import { DevOverlay } from './components/DevOverlay'
import type { Tab } from './components/TabBar'
import { cancelRun, getRun } from './lib/api'
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
      {tab.type === 'compare' ? (
        <CompareView onOpenFull={openRunInNewTab} />
      ) : (
        <RunView
          onStatusChange={onStatusChange}
          onOpenRunInNewTab={openRunInNewTab}
          initialRunId={tab.runId}
          devMode={devMode}
        />
      )}
    </div>
  )
}

export default function App() {
  const [devMode, setDevMode] = useState(false)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    return (localStorage.getItem('autosentiment_theme') as 'dark' | 'light') ?? 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('autosentiment_theme', theme)
  }, [theme])

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
        // Optimistically keep running if the tab has a runId; RunView will correct via handleStatusChange.
        status: t.status === 'running' && t.runId ? 'running' : t.status === 'running' ? 'idle' : t.status,
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

  // ── Keyboard shortcuts ───────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+Shift+D: toggle dev mode
      if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault()
        setDevMode(d => !d)
        return
      }
      // Ctrl+T: new tab
      if (e.ctrlKey && !e.shiftKey && e.key === 't') {
        e.preventDefault()
        addTab()
        return
      }
      // Ctrl+W: close active tab
      if (e.ctrlKey && !e.shiftKey && e.key === 'w') {
        e.preventDefault()
        closeActiveTab()
        return
      }
      // Ctrl+Tab / Ctrl+Shift+Tab: cycle tabs
      if (e.ctrlKey && e.key === 'Tab') {
        e.preventDefault()
        setTabs(prev => {
          const idx = prev.findIndex(t => t.id === activeId)
          if (idx === -1) return prev
          const next = e.shiftKey
            ? (idx - 1 + prev.length) % prev.length
            : (idx + 1) % prev.length
          setActiveId(prev[next].id)
          return prev
        })
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [activeId, tabs])  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Shareable URL: ?run=<id> loads a read-only report ──────────────────
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const sharedRunId = params.get('run')
    if (!sharedRunId) return
    // Avoid loading the same shared run twice.
    if (tabs.some(t => t.runId === sharedRunId)) return
    getRun(sharedRunId).then(run => {
      openRunInNewTab(sharedRunId, run.topic)
    }).catch(() => {})
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

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
  }, [])

  function addTab() {
    const tab = newTab()
    setTabs(prev => [...prev, tab])
    setActiveId(tab.id)
  }

  function closeActiveTab() {
    closeTab(activeId)
  }

  function addCompareTab() {
    const tab = newTab()
    tab.label = 'Compare'
    tab.type = 'compare'
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

  function reorderTabs(dragId: string, dropId: string) {
    setTabs(prev => {
      const from = prev.findIndex(t => t.id === dragId)
      const to   = prev.findIndex(t => t.id === dropId)
      if (from === -1 || to === -1 || from === to) return prev
      const next = [...prev]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next
    })
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-logo">
          <div className="app-logo-mark">AS</div>
          <h1>Auto<span>Sentiment</span></h1>
        </div>
        <p className="app-lede">Multi-source public sentiment intelligence</p>
        <div className="app-header-actions">
          <button
            className="btn-secondary compare-open-btn"
            onClick={addCompareTab}
            title="Compare 2-3 topics side by side"
          >
            ⊞ Compare
          </button>
          <button
            className="theme-toggle-btn"
            onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? '☀' : '🌙'}
          </button>
          <button
            className="dev-toggle-btn"
            onClick={() => setDevMode(d => !d)}
            title="Dev mode (Ctrl+Shift+D)"
            aria-pressed={devMode}
          >
            {devMode ? '⚙ dev on' : '⚙'}
          </button>
        </div>
      </header>

      <TabBar
        tabs={tabs}
        activeId={activeId}
        runningCount={runningCount}
        onSelect={setActiveId}
        onAdd={addTab}
        onClose={closeTab}
        onReorder={reorderTabs}
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
