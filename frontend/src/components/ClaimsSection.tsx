import { useState } from 'react'
import type { FactCheck } from '../lib/api'
import { faviconUrl, providerName } from '../lib/providers'

function ClaimCard({ claim, idx }: { claim: FactCheck['claims'][number]; idx: number }) {
  const [open, setOpen] = useState(false)
  const corroboration = (claim.supporting_domains ?? []).length
  const maxSources = 6
  const confidence = Math.round((claim.confidence ?? 0) * 100)
  const urls: string[] = claim.supporting_urls ?? []

  return (
    <div className={`claim-card2${claim.needs_verification ? ' claim-card2--verify' : ' claim-card2--ok'}`} key={`${claim.claim}:${idx}`}>
      <button className="claim-card2-header" onClick={() => setOpen(o => !o)}>
        <div className="claim-card2-meta">
          <span className={`claim-badge claim-badge--${claim.needs_verification ? 'verify' : 'ok'}`}>
            {claim.needs_verification ? '⚠ needs check' : '✓ corroborated'}
          </span>
          <span className="claim-type-badge">{claim.claim_type}</span>
          <span className="claim-confidence">{confidence}% confidence</span>
        </div>
        <div className="claim-corroboration-bar" title={`${corroboration} source${corroboration !== 1 ? 's' : ''}`}>
          {Array.from({ length: Math.max(1, Math.min(maxSources, corroboration)) }).map((_, i) => (
            <span key={i} className={`claim-corroboration-dot${i < corroboration ? ' claim-corroboration-dot--filled' : ''}`} />
          ))}
          <span className="claim-source-count">{corroboration} source{corroboration !== 1 ? 's' : ''}</span>
        </div>
        <span className="claim-toggle-icon">{open ? '▲' : '▼'}</span>
      </button>
      <p className="claim-text">{claim.claim}</p>
      {open && (
        <div className="claim-sources">
          {urls.length > 0 ? urls.map(url => (
            <a key={url} href={url} target="_blank" rel="noreferrer" className="claim-source-link" title={url}>
              <img src={faviconUrl(url)} alt="" width={12} height={12}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              <span className="clip-text">{providerName(url)}</span>
              <span className="claim-source-path">{(() => { try { const u = new URL(url); return u.pathname.slice(0, 30) || '/'; } catch { return ''; } })()}</span>
              <span className="claim-source-arrow">↗</span>
            </a>
          )) : (claim.supporting_domains ?? []).map((domain: string) => (
            <a key={domain} href={`https://${domain}`} target="_blank" rel="noreferrer" className="claim-source-link">
              <img src={`https://www.google.com/s2/favicons?domain=${domain}&sz=12`} alt="" width={12} height={12}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              <span>{domain}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

export function FactCheckSection({ factCheck }: { factCheck: FactCheck }) {
  const [showAll, setShowAll] = useState(false)
  if (!factCheck.claims.length) return null
  const displayed = showAll ? factCheck.claims : factCheck.claims.slice(0, 4)
  const needsCheck = factCheck.claims.filter(c => c.needs_verification).length
  const corroborated = factCheck.claims.length - needsCheck

  return (
    <div className="insight-section">
      <h3>Claim Corroboration</h3>
      <div className="claim-summary-row">
        <span className="claim-summary-stat claim-summary-stat--ok">✓ {corroborated} corroborated</span>
        <span className="claim-summary-stat claim-summary-stat--verify">⚠ {needsCheck} need verification</span>
        <p className="fact-check-summary">{factCheck.summary}</p>
      </div>
      <div className="claim-list2">
        {displayed.map((claim, idx) => <ClaimCard key={`${idx}:${claim.claim}`} claim={claim} idx={idx} />)}
      </div>
      {factCheck.claims.length > 4 && (
        <button className="btn-secondary show-all-btn" onClick={() => setShowAll(a => !a)}>
          {showAll ? '▲ Show fewer' : `▼ Show all ${factCheck.claims.length} claims`}
        </button>
      )}
    </div>
  )
}
