import React from 'react';
import type { ClaimVerificationItem } from '../types/api';
import { CheckCircle2, AlertTriangle, XCircle, HelpCircle, ExternalLink } from 'lucide-react';

interface Props {
  claims: ClaimVerificationItem[];
  overallStatus?: string;
}

export const ClaimVerificationCard: React.FC<Props> = ({ claims, overallStatus }) => {
  const getVerdictBadge = (verdict: string) => {
    switch (verdict) {
      case 'SUPPORTED':
        return (
          <span className="badge badge-success">
            <CheckCircle2 size={12} /> ✓ Supported
          </span>
        );
      case 'UNSUPPORTED':
        return (
          <span className="badge badge-warning">
            <AlertTriangle size={12} /> ⚠ UNSUPPORTED
          </span>
        );
      case 'CONTRADICTED':
        return (
          <span className="badge badge-danger">
            <XCircle size={12} /> ✗ Contradicted
          </span>
        );
      default:
        return (
          <span className="badge badge-neutral">
            <HelpCircle size={12} /> ? {verdict}
          </span>
        );
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">Claim Verification & Faithfulness</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Empirical verification of AI-generated resolution claims against historical repository evidence
          </div>
        </div>
        {overallStatus && (
          <span className={`badge ${overallStatus === 'VERIFIED' ? 'badge-success' : 'badge-warning'}`}>
            Faithfulness Status: {overallStatus}
          </span>
        )}
      </div>

      <div>
        {claims && claims.length > 0 ? (
          claims.map((claim, idx) => (
            <div key={claim.claim_id || idx} className="claim-card">
              <div className="claim-header">
                <span className="claim-text">"{claim.claim_text}"</span>
                {getVerdictBadge(claim.verdict)}
              </div>
              {claim.explanation && (
                <p style={{ fontSize: '0.825rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
                  {claim.explanation}
                </p>
              )}
              {claim.source_ids && claim.source_ids.length > 0 && (
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.4rem', flexWrap: 'wrap' }}>
                  {claim.source_ids.map((src, i) => (
                    <span
                      key={i}
                      style={{
                        fontSize: '0.725rem',
                        fontFamily: 'var(--font-mono)',
                        background: 'rgba(255,255,255,0.05)',
                        padding: '0.15rem 0.4rem',
                        borderRadius: '4px',
                        color: 'var(--text-dim)',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.2rem',
                      }}
                    >
                      <ExternalLink size={10} /> Citation {src}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))
        ) : (
          <div className="empty-state" style={{ padding: '1.5rem' }}>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              All resolution claims verified against historical repository evidence.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
