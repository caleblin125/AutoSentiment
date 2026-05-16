import { useState } from 'react'
import type { SourceFact } from '../lib/api'
import { KNOWN_PROVIDERS, providerName } from '../lib/providers'

export const SOURCE_TYPE_LABEL: Record<string, string> = {
  reddit: 'Reddit',
  news:   'News Media',
  social: 'Social Media',
  forum:  'Forums',
  video:  'Video',
  web:    'Web / Blogs',
}

const SOURCE_TYPE_ICON: Record<string, string> = {
  reddit: '⬤',
  news:   '📰',
  social: '💬',
  forum:  '🗣',
  video:  '▶',
  web:    '🌐',
}

interface SourceGroup {
  type: string
  label: string
  count: number
  positive: number
  neutral: number
  negative: number
  domains: SourceFact[]
}

function groupSourceFacts(facts: SourceFact[]): SourceGroup[] {
  const byType = new Map<string, SourceGroup>()
  for (const f of facts) {
    if (f.count === 0) continue
    const type = f.source_type
    if (!byType.has(type)) {
      byType.set(type, {
        type, label: SOURCE_TYPE_LABEL[type] ?? type,
        count: 0, positive: 0, neutral: 0, negative: 0, domains: [],
      })
    }
    const g = byType.get(type)!
    g.count += f.count
    g.positive += f.labels?.positive ?? 0
    g.neutral  += f.labels?.neutral  ?? 0
    g.negative += f.labels?.negative ?? 0
    g.domains.push(f)
  }
  return [...byType.values()].sort((a, b) => b.count - a.count)
}

function SourceGroupCard({ group }: { group: SourceGroup }) {
  const [open, setOpen] = useState(false)
  const total = group.positive + group.neutral + group.negative || 1
  const icon = SOURCE_TYPE_ICON[group.type] ?? '●'

  return (
    <div className="source-group">
      <button className="source-group-header" onClick={() => setOpen(o => !o)}>
        <span className="source-group-icon">{icon}</span>
        <span className="source-group-label">{group.label}</span>
        <span className="source-group-count">{group.count} items · {group.domains.length} sources</span>
        <div className="source-group-bar">
          <div style={{ flex: group.positive / total, background: 'var(--positive)' }} />
          <div style={{ flex: group.neutral  / total, background: 'var(--neutral)' }} />
          <div style={{ flex: group.negative / total, background: 'var(--rog-red)' }} />
        </div>
        <span className="source-group-chevron">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="source-group-domains">
          {group.domains.sort((a, b) => b.count - a.count).map(fact => {
            const fakeUrl = `https://${fact.domain}`
            const dtotal = (fact.labels?.positive ?? 0) + (fact.labels?.neutral ?? 0) + (fact.labels?.negative ?? 0) || 1
            return (
              <details key={fact.domain} className="source-fact">
                <summary className="source-fact-header">
                  <img
                    src={`https://www.google.com/s2/favicons?domain=${fact.domain}&sz=14`}
                    alt="" width={14} height={14}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                  <strong className="clip-text" title={fact.domain}>
                    {KNOWN_PROVIDERS[fact.domain] ?? fact.domain.replace(/^www\./, '')}
                  </strong>
                </summary>
                <span className="source-fact-count">
                  {fact.count} items
                  {fact.credibility !== undefined && (
                    <span className={`source-cred source-cred--${fact.credibility >= 0.7 ? 'high' : fact.credibility >= 0.4 ? 'mid' : 'low'}`}>
                      {Math.round(fact.credibility * 100)}% cred
                    </span>
                  )}
                </span>
                <div className="source-fact-bar">
                  <div style={{ flex: (fact.labels?.positive ?? 0) / dtotal, background: 'var(--positive)' }} />
                  <div style={{ flex: (fact.labels?.neutral  ?? 0) / dtotal, background: 'var(--neutral)' }} />
                  <div style={{ flex: (fact.labels?.negative ?? 0) / dtotal, background: 'var(--rog-red)' }} />
                </div>
                <div className="source-link-list">
                  {(fact.urls?.length ? fact.urls : [fakeUrl]).map(url => (
                    <a key={url} href={url} target="_blank" rel="noreferrer" title={url}>
                      {providerName(url)}
                    </a>
                  ))}
                </div>
              </details>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function SourceFacts({ facts }: { facts: SourceFact[] }) {
  const groups = groupSourceFacts(facts)
  if (!groups.length) return null
  return (
    <div className="insight-section">
      <h3>Source mix</h3>
      <div className="source-group-list">
        {groups.map(g => <SourceGroupCard key={g.type} group={g} />)}
      </div>
    </div>
  )
}
