import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import type { RecentRunItem } from '../types/api';
import { DEMO_RECENT_RUNS } from '../data/demoFixtures';
import { SeverityBadge } from '../components/SeverityBadge';
import { ShieldAlert, AlertTriangle, ArrowRight, RefreshCw, CheckCircle2 } from 'lucide-react';

export const EscalationsPage: React.FC = () => {
  const navigate = useNavigate();
  const { demoMode } = useWorkspace();
  const [escalatedRuns, setEscalatedRuns] = useState<RecentRunItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEscalations = async () => {
    setLoading(true);
    setError(null);

    if (demoMode) {
      setTimeout(() => {
        const demoEscalations = DEMO_RECENT_RUNS.filter(
          (r) => r.final_decision === 'HUMAN_ESCALATION' || r.status === 'ESCALATED'
        );
        setEscalatedRuns(demoEscalations);
        setLoading(false);
      }, 200);
      return;
    }

    try {
      const runs = await api.getRecentRuns(50, 0, undefined, 'HUMAN_ESCALATION');
      setEscalatedRuns(runs);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to fetch escalation queue.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEscalations();
  }, [demoMode]);

  return (
    <div>
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <h1 className="page-title">
              <ShieldAlert size={22} color="var(--warning)" />
              Human Escalation Queue
            </h1>
            <span className="badge badge-warning">
              {escalatedRuns.length} Pending
            </span>
          </div>
          <p className="page-subtitle">
            Tickets requiring engineering review due to low confidence or verification gaps.
          </p>
        </div>

        <button className="btn btn-secondary" onClick={fetchEscalations} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'spinner' : ''} />
          <span>Refresh Queue</span>
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <AlertTriangle size={16} />
          <div>{error}</div>
        </div>
      )}

      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <ShieldAlert size={18} color="var(--warning)" />
            <span>Escalated Tickets ({escalatedRuns.length})</span>
          </div>
        </div>

        {loading ? (
          <div className="empty-state" style={{ padding: '2.5rem' }}>
            <div className="spinner" style={{ margin: '0 auto 0.5rem auto' }} />
            <p style={{ fontSize: '0.85rem' }}>Loading escalation queue...</p>
          </div>
        ) : escalatedRuns.length === 0 ? (
          <div className="empty-state">
            <CheckCircle2 size={32} color="var(--success)" style={{ marginBottom: '0.5rem' }} />
            <p className="empty-state-title">Escalation queue is clear</p>
            <p className="empty-state-subtitle">No pending human review tickets in your active workspace.</p>
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Ticket Title</th>
                  <th>Repository</th>
                  <th>Severity</th>
                  <th>Root Cause</th>
                  <th>Confidence</th>
                  <th>Reason</th>
                  <th style={{ textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {escalatedRuns.map((r) => (
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
                          maxWidth: '300px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          fontSize: '0.875rem',
                        }}
                        title={r.title}
                      >
                        {r.title}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                        {r.pipeline_run_id.slice(0, 16)}...
                      </div>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.825rem', color: 'var(--text-secondary)' }}>
                      {r.repository_name}
                    </td>
                    <td>
                      <SeverityBadge severity={r.severity} />
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.825rem', color: 'var(--text-secondary)' }}>
                      {r.root_cause_cluster}
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.875rem', color: '#FBBF24' }}>
                        {(r.calibrated_confidence * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td>
                      <span className="badge badge-warning">Verification Gap</span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '0.3rem 0.65rem', fontSize: '0.775rem' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/runs/${r.pipeline_run_id}`);
                        }}
                      >
                        <span>Review</span>
                        <ArrowRight size={11} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
