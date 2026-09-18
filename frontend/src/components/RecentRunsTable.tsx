import React from 'react';
import { useNavigate } from 'react-router-dom';
import type { RecentRunItem } from '../types/api';
import { StatusBadge } from './StatusBadge';
import { SeverityBadge } from './SeverityBadge';
import { ArrowRight, Inbox, FileCode } from 'lucide-react';

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
        <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
          <FileCode size={18} color="var(--primary)" />
          <span>Recent Investigations</span>
        </div>
        <div className="empty-state" style={{ padding: '2rem' }}>
          <div className="spinner" style={{ margin: '0 auto 0.65rem auto' }} />
          <p style={{ fontSize: '0.9rem' }}>Loading investigations...</p>
        </div>
      </div>
    );
  }

  if (!runs || runs.length === 0) {
    return (
      <div className="panel">
        <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
          <FileCode size={18} color="var(--primary)" />
          <span>Recent Investigations</span>
        </div>
        <div className="empty-state">
          <Inbox size={32} style={{ color: 'var(--text-dim)', marginBottom: '0.5rem' }} />
          <p className="empty-state-title">No investigations yet</p>
          <p className="empty-state-subtitle">
            Submit a support ticket to start automated AI triage and resolution generation.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
          <FileCode size={18} color="var(--primary)" />
          <span>Recent Investigations</span>
          <span className="badge badge-neutral" style={{ marginLeft: '0.4rem' }}>
            {runs.length}
          </span>
        </div>
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ minWidth: '280px' }}>Ticket</th>
              <th>Repository</th>
              <th>Severity</th>
              <th>Root Cause</th>
              <th>Confidence</th>
              <th>Decision</th>
              <th>Latency</th>
              <th style={{ textAlign: 'right' }}>Action</th>
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
                    title={r.title}
                  >
                    {r.title}
                  </div>
                  <div style={{ fontSize: '0.775rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', marginTop: '0.15rem' }}>
                    {r.pipeline_run_id.slice(0, 16)}...
                  </div>
                </td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                  {r.repository_name}
                </td>
                <td>
                  <SeverityBadge severity={r.severity} />
                </td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                  {r.root_cause_cluster || 'core'}
                </td>
                <td>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 700,
                      fontSize: '0.95rem',
                      color: r.calibrated_confidence >= 0.85 ? 'var(--success)' : 'var(--warning)',
                    }}
                  >
                    {(r.calibrated_confidence * 100).toFixed(1)}%
                  </span>
                </td>
                <td>
                  <StatusBadge decision={r.final_decision} status={r.status} />
                </td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem', color: 'var(--text-dim)' }}>
                  {r.total_latency_ms} ms
                </td>
                <td style={{ textAlign: 'right' }}>
                  <button
                    className="btn btn-secondary"
                    style={{ padding: '0.35rem 0.7rem', fontSize: '0.8rem' }}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/runs/${r.pipeline_run_id}`);
                    }}
                  >
                    <span>View</span>
                    <ArrowRight size={12} />
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
