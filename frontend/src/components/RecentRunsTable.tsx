import React from 'react';
import { useNavigate } from 'react-router-dom';
import type { RecentRunItem } from '../types/api';
import { StatusBadge } from './StatusBadge';
import { SeverityBadge } from './SeverityBadge';
import { ArrowRight, Inbox } from 'lucide-react';

interface Props {
  runs: RecentRunItem[];
  loading: boolean;
  onFilterChange?: (filters: { severity?: string; decision?: string }) => void;
}

export const RecentRunsTable: React.FC<Props> = ({ runs, loading }) => {
  const navigate = useNavigate();

  if (loading) {
    return (
      <div className="panel">
        <div className="panel-title">Recent Ticket Analyses</div>
        <div className="empty-state">Loading recent pipeline runs...</div>
      </div>
    );
  }

  if (!runs || runs.length === 0) {
    return (
      <div className="panel">
        <div className="panel-title">Recent Ticket Analyses</div>
        <div className="empty-state">
          <Inbox size={32} className="empty-state-icon" />
          <p style={{ fontWeight: 600, color: 'var(--text-main)' }}>No analyzed tickets yet.</p>
          <p style={{ fontSize: '0.8rem', marginTop: '0.3rem' }}>
            Submit a support ticket to start automated AI triage and resolution generation.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <div className="panel-title">Recent Ticket Analyses ({runs.length})</div>
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Ticket Title</th>
              <th>Repository</th>
              <th>Severity</th>
              <th>Duplicate</th>
              <th>Root Cause Cluster</th>
              <th>Confidence</th>
              <th>Decision</th>
              <th>Latency</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr
                key={r.pipeline_run_id}
                className="clickable-row"
                onClick={() => navigate(`/runs/${r.pipeline_run_id}`)}
              >
                <td>
                  <div style={{ fontWeight: 600 }}>{r.title}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                    ID: {r.pipeline_run_id.slice(0, 16)}...
                  </div>
                </td>
                <td>{r.repository_name}</td>
                <td>
                  <SeverityBadge severity={r.severity} />
                </td>
                <td>
                  {r.duplicate_detected === 'YES' ? (
                    <span className="badge badge-danger">YES</span>
                  ) : (
                    <span className="badge badge-neutral">NO</span>
                  )}
                </td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                  {r.root_cause_cluster}
                </td>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                  {(r.calibrated_confidence * 100).toFixed(1)}%
                </td>
                <td>
                  <StatusBadge decision={r.final_decision} status={r.status} />
                </td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                  {r.total_latency_ms} ms
                </td>
                <td>
                  <button
                    className="btn btn-secondary"
                    style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/runs/${r.pipeline_run_id}`);
                    }}
                  >
                    View <ArrowRight size={12} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
