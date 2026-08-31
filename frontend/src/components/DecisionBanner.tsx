import React, { useState } from 'react';
import { CheckCircle2, AlertTriangle, ShieldAlert, Check, UserCheck } from 'lucide-react';

interface Props {
  decision: string;
  recommendedTeam?: string;
}

export const DecisionBanner: React.FC<Props> = ({ decision, recommendedTeam }) => {
  const [operatorApproved, setOperatorApproved] = useState<boolean>(false);
  const [operatorEscalated, setOperatorEscalated] = useState<boolean>(false);

  const isAutoResolve =
    decision === 'AUTO_RESOLVE_RECOMMENDATION' || decision === 'AUTO_RESOLVE' || decision === 'SUCCEEDED';

  return (
    <div
      className="panel"
      style={{
        borderLeft: `4px solid ${isAutoResolve ? 'var(--success)' : 'var(--warning)'}`,
        background: isAutoResolve ? 'rgba(16, 185, 129, 0.08)' : 'rgba(245, 158, 11, 0.08)',
        marginBottom: '1.5rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
          {isAutoResolve ? (
            <CheckCircle2 size={28} color="var(--success)" />
          ) : (
            <AlertTriangle size={28} color="var(--warning)" />
          )}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, letterSpacing: '-0.01em' }}>
                {isAutoResolve ? 'AI RECOMMENDS AUTOMATIC RESOLUTION' : 'HUMAN REVIEW REQUIRED'}
              </h3>
              <span
                className={`badge ${isAutoResolve ? 'badge-success' : 'badge-warning'}`}
                style={{ fontSize: '0.75rem' }}
              >
                {isAutoResolve ? 'High Faithfulness & Confidence' : 'Verification Failure / Low Confidence'}
              </span>
            </div>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              {isAutoResolve
                ? 'No GitHub mutation has been performed. This evidence-backed resolution is ready for maintainer review.'
                : `Escalated to engineering queue: ${recommendedTeam || 'General Support'}. Review claim verification and confidence scores below.`}
            </p>
          </div>
        </div>

        {/* Operator Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {operatorApproved ? (
            <span className="badge badge-success" style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem' }}>
              <Check size={14} /> Approved by Operator
            </span>
          ) : operatorEscalated ? (
            <span className="badge badge-warning" style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem' }}>
              <UserCheck size={14} /> Escalated to Engineering
            </span>
          ) : (
            <>
              <button
                className="btn btn-secondary"
                onClick={() => setOperatorEscalated(true)}
                style={{ fontSize: '0.8rem' }}
              >
                <ShieldAlert size={14} /> Escalate Ticket
              </button>
              <button
                className="btn btn-success"
                onClick={() => setOperatorApproved(true)}
                style={{ fontSize: '0.8rem' }}
              >
                <Check size={14} /> Approve Recommendation
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
