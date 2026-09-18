import React, { useState } from 'react';
import { Check, ShieldAlert, CheckCircle2, UserCheck, FileCheck } from 'lucide-react';
import { ConfidenceIndicator } from './ConfidenceIndicator';

interface Props {
  decision: string;
  recommendedTeam?: string;
  calibratedConfidence?: number;
  reasonCodes?: string[];
}

export const DecisionBanner: React.FC<Props> = ({
  decision,
  recommendedTeam,
  calibratedConfidence = 0.85,
  reasonCodes = [],
}) => {
  const [operatorApproved, setOperatorApproved] = useState<boolean>(false);
  const [operatorEscalated, setOperatorEscalated] = useState<boolean>(false);

  const isAutoResolve =
    decision === 'AUTO_RESOLVE_RECOMMENDATION' ||
    decision === 'AUTO_RESOLVE' ||
    decision === 'SUCCEEDED';

  return (
    <div
      className="panel"
      style={{
        borderLeft: `4px solid ${isAutoResolve ? 'var(--success)' : 'var(--warning)'}`,
        background: 'var(--bg-card)',
        marginBottom: '1.25rem',
        padding: '1.1rem 1.25rem',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        {/* Left Side: Decision status & rationale */}
        <div style={{ flex: '1 1 420px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
            {isAutoResolve ? (
              <CheckCircle2 size={18} color="var(--success)" />
            ) : (
              <ShieldAlert size={18} color="var(--warning)" />
            )}
            <h3
              style={{
                fontSize: '1rem',
                fontWeight: 700,
                letterSpacing: '-0.015em',
                color: isAutoResolve ? '#34D399' : '#FBBF24',
              }}
            >
              {isAutoResolve
                ? 'DECISION: AUTO-RESOLUTION RECOMMENDED'
                : 'DECISION: HUMAN REVIEW REQUIRED'}
            </h3>
            <span
              className={`badge ${isAutoResolve ? 'badge-success' : 'badge-warning'}`}
              style={{ fontSize: '0.685rem' }}
            >
              {isAutoResolve ? 'Ready for Deployment' : 'Review Handoff'}
            </span>
          </div>

          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
            {isAutoResolve
              ? 'Empirical safety criteria verified: Factual claim faithfulness rate = 100%, zero contradictions, and calibrated confidence ≥ 85% safety threshold.'
              : `Strict precedence safety override: Route ticket to ${
                  recommendedTeam || 'General Engineering Support'
                }. Review claim verification findings and root-cause candidate before taking operational action.`}
          </p>

          {reasonCodes.length > 0 && (
            <div style={{ display: 'flex', gap: '0.35rem', marginTop: '0.45rem', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '0.685rem', color: 'var(--text-dim)', alignSelf: 'center' }}>
                Reason Codes:
              </span>
              {reasonCodes.map((code, i) => (
                <span
                  key={i}
                  style={{
                    fontSize: '0.685rem',
                    fontFamily: 'var(--font-mono)',
                    background: 'rgba(255, 255, 255, 0.04)',
                    padding: '0.1rem 0.35rem',
                    borderRadius: '2px',
                    color: 'var(--text-muted)',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  {code}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Right Side: Confidence & Operator Controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', minWidth: '220px' }}>
          <ConfidenceIndicator confidence={calibratedConfidence} size="sm" />

          {/* Operator Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', justifyContent: 'flex-end' }}>
            {operatorApproved ? (
              <span className="badge badge-success" style={{ padding: '0.35rem 0.65rem' }}>
                <Check size={12} /> Approved by Operator
              </span>
            ) : operatorEscalated ? (
              <span className="badge badge-warning" style={{ padding: '0.35rem 0.65rem' }}>
                <UserCheck size={12} /> Escalated to Maintainer Queue
              </span>
            ) : (
              <>
                <button
                  className="btn btn-secondary"
                  onClick={() => setOperatorEscalated(true)}
                  style={{ fontSize: '0.75rem', padding: '0.35rem 0.65rem' }}
                >
                  <ShieldAlert size={12} color="#FBBF24" />
                  <span>Escalate</span>
                </button>

                <button
                  className="btn btn-success"
                  onClick={() => setOperatorApproved(true)}
                  style={{ fontSize: '0.75rem', padding: '0.35rem 0.65rem' }}
                >
                  <FileCheck size={12} />
                  <span>Approve</span>
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
