import { RunForm } from './components/RunForm'
import { EventTimeline } from './components/EventTimeline'
import { ReportView } from './components/ReportView'
import { getApiBaseUrl } from './lib/config'
import './App.css'

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>AutoSentiment</h1>
        <p className="lede">
          Citation-backed web research UI — implement panels per{' '}
          <code>frontend/IMPLEMENTATION.md</code>.
        </p>
        <p className="muted">
          API: <code>{getApiBaseUrl()}</code>
        </p>
      </header>

      <main className="app-main">
        <RunForm />
        <EventTimeline />
        <ReportView />
      </main>
    </div>
  )
}

export default App
