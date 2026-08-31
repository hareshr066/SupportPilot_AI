import React from 'react';
import { useNavigate } from 'react-router-dom';
import type { RecentRunItem } from '../types/api';
import { SeverityBadge } from './SeverityBadge';
import { AlertTriangle, ArrowRight, ShieldAlert } from 'lucide-react';

interface AttentionQueueProps {
  items: RecentRunItem[];
  onReview?: (runId: string) => void;
}

export const AttentionQueue: React.FC<AttentionQueueProps> = ({ items, onReview }) => {
  const navigate = useNavigate();

  const escalatedItems = items.filter(
    (item) => item.final_decision === 'HUMAN_ESCALATION' || item.status === 'ESCALATED'
  );

  if (escalatedItems.length === 0) {
    return (
      <div className="panel">
        <div className="panel-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertTriangle size={16} color="var(--success)" />
            <h3 className="panel-title">Needs Your Attention</h3>
          </div>
          <span className="badge badge-success">0 Action Items</span>
        </div>
        <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.825rem' }}>
          All analyzed issues are resolved or within automated confidence thresholds. No manual intervention required.
        </div>
      </div>
    );
  }

  return (
    <div className="panel" style={{ borderLeft: '4px solid #D97706' }}>
      <div className="panel-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <ShieldAlert size={18} color="#D97706" />
          <h3 className="panel-title">Needs Your Attention ({escalatedItems.length})</h3>
        </div>
        <span className="badge badge-warning">Human Escalation Required</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
        {escalatedItems.map((item) => (
          <div
            key={item.pipeline_run_id}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0.75rem 0.9rem',
              background: '#FFFBEB',
              border: '1px solid #FDE68A',
              borderRadius: 'var(--radius-sm)'
            }}
          >
            <div style={{ flex: 1, paddingRight: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.2rem' }}>
                <SeverityBadge severity={item.severity} />
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                  {item.repository_name} {item.issue_number ? `#${item.issue_number}` : ''}
                </span>
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--text-main)' }}>
                {item.title}
              </div>
              <div style={{ fontSize: '0.725rem', color: '#92400E', marginTop: '0.2rem' }}>
                Reason: Verification failure or confidence below threshold ({Math.round(item.calibrated_confidence * 100)}%)
              </div>
            </div>

            <button
              className="btn btn-secondary"
              onClick={() => {
                if (onReview) onReview(item.pipeline_run_id);
                navigate(`/runs/${item.pipeline_run_id}`);
              }}
              style={{ fontSize: '0.775rem', gap: '0.3rem', borderColor: '#FCD34D', background: '#FFFFFF' }}
            >
              <span>Review Handoff</span>
              <ArrowRight size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
