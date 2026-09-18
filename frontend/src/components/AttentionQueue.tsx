import React from 'react';
import { useNavigate } from 'react-router-dom';
import type { RecentRunItem } from '../types/api';
import { SeverityBadge } from './SeverityBadge';
import { StatusBadge } from './StatusBadge';
import { ArrowRight, CheckCircle2, ShieldAlert } from 'lucide-react';

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
      <div
        className="panel"
        style={{
          borderLeft: '3px solid var(--success)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '1.25rem 1.5rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <CheckCircle2 size={22} color="var(--success)" />
          <div>
            <span style={{ fontWeight: 700, color: '#FFFFFF', fontSize: '1rem' }}>
              All Clear
            </span>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginLeft: '0.65rem' }}>
              No pending engineering reviews.
            </span>
          </div>
        </div>
        <span className="badge badge-success">0 Pending</span>
      </div>
    );
  }

  return (
    <div className="panel" style={{ borderLeft: '3px solid var(--warning)' }}>
      <div className="panel-header">
        <div>
          <div className="panel-title">
            <ShieldAlert size={18} color="var(--warning)" />
            <span>Needs Attention</span>
            <span className="badge badge-warning" style={{ marginLeft: '0.4rem' }}>
              {escalatedItems.length}
            </span>
          </div>
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Issues requiring engineering review before resolution.
          </div>
        </div>
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: '90px' }}>Severity</th>
              <th style={{ minWidth: '280px' }}>Ticket</th>
              <th>Repository</th>
              <th>Confidence</th>
              <th>Decision</th>
              <th style={{ textAlign: 'right' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {escalatedItems.map((item) => {
              const isHigh = item.severity === 'HIGH' || item.severity === 'CRITICAL';
              return (
                <tr
                  key={item.pipeline_run_id}
                  className="clickable-row"
                  onClick={() => {
                    if (onReview) onReview(item.pipeline_run_id);
                    navigate(`/runs/${item.pipeline_run_id}`);
                  }}
                  style={{
                    backgroundColor: isHigh ? 'rgba(248, 113, 113, 0.04)' : undefined,
                  }}
                >
                  <td>
                    <SeverityBadge severity={item.severity} />
                  </td>
                  <td>
                    <div
                      style={{
                        fontWeight: 600,
                        color: 'var(--text-main)',
                        maxWidth: '340px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        fontSize: '0.925rem',
                      }}
                      title={item.title}
                    >
                      {item.title}
                    </div>
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                    {item.repository_name}
                  </td>
                  <td>
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 700,
                        fontSize: '0.95rem',
                        color: item.calibrated_confidence >= 0.85 ? 'var(--success)' : 'var(--warning)',
                      }}
                    >
                      {(item.calibrated_confidence * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td>
                    <StatusBadge decision={item.final_decision} status={item.status} />
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.35rem 0.7rem', fontSize: '0.8rem' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (onReview) onReview(item.pipeline_run_id);
                        navigate(`/runs/${item.pipeline_run_id}`);
                      }}
                    >
                      <span>Review</span>
                      <ArrowRight size={12} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
