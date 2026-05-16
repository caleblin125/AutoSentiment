import { useState } from 'react'
import type { Contradiction, FactCheck } from '../lib/api'
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

function ContradictionCard({ item, onCite }: { item: Contradiction; onCite?: (id: string) => void }) {
  return (
    <div className="contradiction-card">
      <div className="contradiction-header">
        <span className="contradiction-subject">{item.subject}</span>
        <span className="contradiction-badge">⇄ conflicting sources</span>
      </div>
      <div className="contradiction-sides">
        <div className="contradiction-side contradiction-side--pos">
          <span className="contradiction-polarity">Positive</span>
          <p className="contradiction-claim">{item.positive_claim}</p>
          <div className="contradiction-domains">
            {item.positive_domains.map(d => (
              <span key={d} className="contradiction-domain">
                <img src={`https://www.google.com/s2/favicons?domain=${d}&sz=12`} alt="" width={10} height={10}
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                {d}
              </span>
            ))}
          </div>
          {onCite && (
            <button className="contradiction-cite-btn" onClick={() => onCite(item.positive_evidence_id)}>
              inspect ↗
            </button>
          )}
        </div>
        <div className="contradiction-vs">vs</div>
        <div className="contradiction-side contradiction-side--neg">
          <span className="contradiction-polarity">Negative</span>
          <p className="contradiction-claim">{item.negative_claim}</p>
          <div className="contradiction-domains">
            {item.negative_domains.map(d => (
              <span key={d} className="contradiction-domain">
                <img src={`https://www.google.com/s2/favicons?domain=${d}&sz=12`} alt="" width={10} height={10}
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                {d}
              </span>
            ))}
          </div>
          {onCite && (
            <button className="contradiction-cite-btn" onClick={() => onCite(item.negative_evidence_id)}>
              inspect ↗
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function FactCheckSection({ factCheck, onCite }: { factCheck: FactCheck; onCite?: (id: string) => void }) {
  const [showAll, setShowAll] = useState(false)
  if (!factCheck.claims.length && !factCheck.contradictions?.length) return null
  const displayed = showAll ? factCheck.claims : factCheck.claims.slice(0, 4)
  const needsCheck = factCheck.claims.filter(c => c.needs_verification).length
  const corroborated = factCheck.claims.length - needsCheck
  const contradictions = factCheck.contradictions ?? []

  return (
    <div className="insight-section">
      <h3>Claim Corroboration</h3>
      <div className="claim-summary-row">
        <span className="claim-summary-stat claim-summary-stat--ok">✓ {corroborated} corroborated</span>
        <span className="claim-summary-stat claim-summary-stat--verify">⚠ {needsCheck} need verification</span>
        {contradictions.length > 0 && (
          <span className="claim-summary-stat claim-summary-stat--conflict">⇄ {contradictions.length} conflicting</span>
        )}
        <p className="fact-check-summary">{factCheck.summary}</p>
      </div>

      {contradictions.length > 0 && (
        <div className="contradiction-section">
          <h4 className="contradiction-section-title">Conflicting Evidence</h4>
          {contradictions.map((item, i) => (
            <ContradictionCard key={`${item.subject}:${i}`} item={item} onCite={onCite} />
          ))}
        </div>
      )}

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
