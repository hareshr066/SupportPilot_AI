import React from 'react';
import type { ClaimVerificationItem } from '../types/api';
import { Check, AlertTriangle, X, HelpCircle, ExternalLink, ShieldCheck, ShieldAlert } from 'lucide-react';

interface Props {
  claims: ClaimVerificationItem[];
  overallStatus?: string;
}

export const ClaimVerificationCard: React.FC<Props> = ({ claims, overallStatus }) => {
  const getVerdictBadge = (verdict: string) => {
    switch (verdict.toUpperCase()) {
      case 'SUPPORTED':
        return (
          <span className="badge badge-success" style={{ fontSize: '0.685rem' }}>
            <Check size={10} /> SUPPORTED
          </span>
        );
      case 'UNSUPPORTED':
        return (
          <span className="badge badge-warning" style={{ fontSize: '0.685rem' }}>
            <AlertTriangle size={10} /> UNSUPPORTED
          </span>
        );
      case 'CONTRADICTED':
        return (
          <span className="badge badge-danger" style={{ fontSize: '0.685rem' }}>
            <X size={10} /> CONTRADICTED
          </span>
        );
      case 'UNCLEAR':
      default:
        return (
          <span className="badge badge-neutral" style={{ fontSize: '0.685rem' }}>
            <HelpCircle size={10} /> {verdict || 'UNCLEAR'}
          </span>
        );
    }
  };

  const getVerdictClass = (verdict: string) => {
    switch (verdict.toUpperCase()) {
      case 'SUPPORTED':
        return 'verdict-supported';
      case 'UNSUPPORTED':
        return 'verdict-unsupported';
      case 'CONTRADICTED':
        return 'verdict-contradicted';
      default:
        return 'verdict-unclear';
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            <ShieldCheck size={15} color="var(--primary)" />
            <span>Factual Claim Verification ({claims.length})</span>
          </div>
          <div style={{ fontSize: '0.725rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
            Atomic assertions verified against historical repository ground truth.
          </div>
        </div>

        {overallStatus && (
          <span
            className={`badge ${
              overallStatus === 'VERIFIED' ? 'badge-success' : 'badge-warning'
            }`}
          >
            {overallStatus === 'VERIFIED' ? 'VERIFIED' : overallStatus}
          </span>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
        {claims && claims.length > 0 ? (
          claims.map((claim, idx) => (
            <div
              key={claim.claim_id || idx}
              className={`claim-card ${getVerdictClass(claim.verdict)}`}
            >
              <div className="claim-header">
                <div style={{ flex: 1, paddingRight: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.2rem' }}>
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.685rem',
                        color: 'var(--text-dim)',
                      }}
                    >
                      {claim.claim_id || `C-${idx + 1}`}
                    </span>

                    {claim.is_critical && (
                      <span className="badge badge-danger" style={{ fontSize: '0.625rem', padding: '0.05rem 0.35rem' }}>
                        <ShieldAlert size={9} /> CRITICAL
                      </span>
                    )}

                    {claim.is_destructive && (
                      <span className="badge badge-danger" style={{ fontSize: '0.625rem', padding: '0.05rem 0.35rem' }}>
                        DESTRUCTIVE
                      </span>
                    )}
                  </div>

                  <div className="claim-text">"{claim.claim_text}"</div>
                </div>

                <div>{getVerdictBadge(claim.verdict)}</div>
              </div>

              {claim.explanation && (
                <div
                  style={{
                    fontSize: '0.75rem',
                    color: 'var(--text-muted)',
                    marginTop: '0.35rem',
                    padding: '0.35rem 0.55rem',
                    background: 'rgba(0, 0, 0, 0.25)',
                    borderRadius: 'var(--radius-xs)',
                  }}
                >
                  <strong style={{ color: 'var(--text-secondary)' }}>Finding: </strong>
                  {claim.explanation}
                </div>
              )}

              {claim.source_ids && claim.source_ids.length > 0 && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    marginTop: '0.35rem',
                    flexWrap: 'wrap',
                  }}
                >
                  <span style={{ fontSize: '0.685rem', color: 'var(--text-dim)' }}>Citations:</span>
                  {claim.source_ids.map((src, i) => (
                    <span
                      key={i}
                      style={{
                        fontSize: '0.685rem',
                        fontFamily: 'var(--font-mono)',
                        background: 'rgba(56, 189, 248, 0.08)',
                        border: '1px solid rgba(56, 189, 248, 0.2)',
                        padding: '0.1rem 0.35rem',
                        borderRadius: '2px',
                        color: 'var(--primary)',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.2rem',
                      }}
                    >
                      <ExternalLink size={9} /> {src}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))
        ) : (
          <div className="empty-state" style={{ padding: '1.25rem' }}>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.785rem' }}>
              All resolution steps grounded in repository historical ground truth.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
