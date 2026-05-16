import { useEffect } from 'react'
import type { EvidenceChunk } from '../lib/api'
import { faviconUrl, providerName } from '../lib/providers'

interface Props {
  chunk: EvidenceChunk
  onClose: () => void
}

function trimSnippet(text: string): string {
  const sentences = text.split(/(?<=[.!?])\s+/).filter(s => s.trim().length > 10)
  const first3 = sentences.slice(0, 3).join(' ')
  if (first3.length <= 350) return first3
  const cut = text.slice(0, 350)
  const lastPunct = Math.max(cut.lastIndexOf('.'), cut.lastIndexOf('!'), cut.lastIndexOf('?'))
  return lastPunct > 100 ? cut.slice(0, lastPunct + 1) : cut + '…'
}

export function EvidenceModal({ chunk, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const displaySnippet = trimSnippet(chunk.snippet)
  const words = chunk.snippet.toLowerCase().split(/\W+/).filter(w => w.length > 4)
  const freqMap = new Map<string, number>()
  words.forEach(w => freqMap.set(w, (freqMap.get(w) ?? 0) + 1))
  const keywords = [...freqMap.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([w]) => w)
  const sentenceCount = chunk.snippet.split(/[.!?]+/).filter(s => s.trim().length > 10).length

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="evidence-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Evidence snippet"
        onClick={e => e.stopPropagation()}
      >
        <button className="modal-close" onClick={onClose} aria-label="Close">✕</button>

        <div className="modal-source-header">
          <img src={faviconUrl(chunk.url)} alt="" width={16} height={16}
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          <a className="modal-source-link" href={chunk.url} target="_blank" rel="noreferrer">
            {providerName(chunk.url)}
          </a>
          <span className={`sentiment-chip sentiment-chip--${chunk.label}`}>{chunk.label}</span>
          <span className="modal-date">
            {new Date(chunk.retrieved_at).toLocaleDateString()}
          </span>
        </div>

        <p className="snippet">{displaySnippet}</p>

        <div className="snippet-analysis">
          <div className="snippet-analysis-block">
            <h4>Key terms</h4>
            <p>{keywords.join(', ') || '—'}</p>
          </div>
          <div className="snippet-analysis-block">
            <h4>Scope</h4>
            <p>{sentenceCount} sentence{sentenceCount !== 1 ? 's' : ''} · {chunk.source_type} · {chunk.snippet.split(' ').length} words</p>
          </div>
          <div className="snippet-analysis-block">
            <h4>Model summary</h4>
            <p>{chunk.summary}</p>
          </div>
          <div className="snippet-analysis-block">
            <h4>Sentiment</h4>
            <p className={`snippet-sentiment snippet-sentiment--${chunk.label}`}>
              {chunk.label.toUpperCase()}
            </p>
          </div>
        </div>

        {chunk.related && (
          <div className="snippet-related">
            {chunk.related.timeline_events.length > 0 && (
              <div>
                <h4>Related dates</h4>
                <p>{chunk.related.timeline_events.map(event => event.date).join(', ')}</p>
              </div>
            )}
            {chunk.related.claims.length > 0 && (
              <div>
                <h4>Related claims</h4>
                <p>{chunk.related.claims.map(claim => claim.claim).join(' · ')}</p>
              </div>
            )}
            {chunk.related.aspects.length > 0 && (
              <div>
                <h4>Related topics</h4>
                <p>{chunk.related.aspects.map(aspect => aspect.name).join(', ')}</p>
              </div>
            )}
          </div>
        )}

        <a href={chunk.url} target="_blank" rel="noreferrer" className="view-source-link">
          View full source ↗
        </a>
      </div>
    </div>
  )
}
