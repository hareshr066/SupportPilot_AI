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
          <h1 className="page-title">Human Escalation Queue</h1>
          <p className="page-subtitle">
            Support tickets requiring engineering maintainer review due to claim verification gaps or confidence below threshold.
          </p>
        </div>

        <button className="btn btn-secondary" onClick={fetchEscalations} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'spinner' : ''} /> Refresh Queue
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
          <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <ShieldAlert size={18} color="#D97706" />
            <span>Escalated Tickets ({escalatedRuns.length})</span>
          </div>
        </div>

        {loading ? (
          <div className="empty-state">Loading escalation queue...</div>
        ) : escalatedRuns.length === 0 ? (
          <div className="empty-state">
            <CheckCircle2 size={36} color="var(--success)" style={{ marginBottom: '0.5rem' }} />
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
                  <th>Root Cause Cluster</th>
                  <th>Calibrated Confidence</th>
                  <th>Reason Code</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {escalatedRuns.map((r) => (
                  <tr key={r.pipeline_run_id} className="clickable-row" onClick={() => navigate(`/runs/${r.pipeline_run_id}`)}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{r.title}</div>
                      <div style={{ fontSize: '0.725rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                        Run ID: {r.pipeline_run_id.slice(0, 16)}...
                      </div>
                    </td>
                    <td>{r.repository_name}</td>
                    <td>
                      <SeverityBadge severity={r.severity} />
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{r.root_cause_cluster}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      {(r.calibrated_confidence * 100).toFixed(1)}%
                    </td>
                    <td>
                      <span className="badge badge-warning">Verification Failure / Low Confidence</span>
                    </td>
                    <td>
                      <button className="btn btn-secondary" style={{ padding: '0.25rem 0.55rem', fontSize: '0.75rem' }}>
                        Review Package <ArrowRight size={12} />
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
