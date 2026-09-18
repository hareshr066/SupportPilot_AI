import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import type { RecentRunItem } from '../types/api';
import { DEMO_RECENT_RUNS } from '../data/demoFixtures';
import { StatusBadge } from '../components/StatusBadge';
import { SeverityBadge } from '../components/SeverityBadge';
import { FileCode, RefreshCw, AlertCircle, ArrowRight } from 'lucide-react';

export const RunsPage: React.FC = () => {
  const navigate = useNavigate();
  const { demoMode, activeRepoId } = useWorkspace();
  const [runs, setRuns] = useState<RecentRunItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRuns = async () => {
    setLoading(true);
    setError(null);

    if (demoMode) {
      setTimeout(() => {
        setRuns(DEMO_RECENT_RUNS);
        setLoading(false);
      }, 200);
      return;
    }

    try {
      const repoId = activeRepoId === 'all' ? undefined : activeRepoId;
      const data = await api.listRuns(50, 0, repoId);
      setRuns(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to fetch pipeline runs.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRuns();
  }, [demoMode, activeRepoId]);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">
            <FileCode size={22} color="var(--primary)" />
            Investigations
          </h1>
          <p className="page-subtitle">
            Complete audit trail of all AI pipeline executions with stage-by-stage breakdowns.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.6rem' }}>
          <button className="btn btn-secondary" onClick={fetchRuns} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spinner' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <div>{error}</div>
        </div>
      )}

      <div className="panel">
        {loading ? (
          <div className="empty-state" style={{ padding: '3rem' }}>
            <div className="spinner" style={{ margin: '0 auto 0.75rem auto' }} />
            <p style={{ fontSize: '0.9rem' }}>Loading pipeline runs...</p>
          </div>
        ) : runs.length === 0 ? (
          <div className="empty-state">
            <p className="empty-state-title">No pipeline runs recorded yet</p>
            <p className="empty-state-subtitle">Submit a support ticket to trigger your first AI triage run.</p>
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Ticket</th>
                  <th>Repository</th>
                  <th>Severity</th>
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
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 600,
                          color: 'var(--primary)',
                          background: 'var(--primary-surface)',
                          padding: '0.2rem 0.5rem',
                          borderRadius: 'var(--radius-xs)',
                          fontSize: '0.775rem',
                        }}
                      >
                        {r.pipeline_run_id.slice(0, 14)}...
                      </span>
                    </td>
                    <td>
                      <div
                        style={{
                          fontWeight: 600,
                          color: 'var(--text-main)',
                          maxWidth: '320px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          fontSize: '0.875rem',
                        }}
                        title={r.title}
                      >
                        {r.title}
                      </div>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.825rem', color: 'var(--text-secondary)' }}>
                      {r.repository_name}
                    </td>
                    <td>
                      <SeverityBadge severity={r.severity} />
                    </td>
                    <td>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 700,
                          fontSize: '0.875rem',
                          color: r.calibrated_confidence >= 0.85 ? 'var(--success)' : 'var(--warning)',
                        }}
                      >
                        {(r.calibrated_confidence * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td>
                      <StatusBadge decision={r.final_decision} status={r.status} />
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.825rem', color: 'var(--text-dim)' }}>
                      {r.total_latency_ms} ms
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
                        <span>View</span>
                        <ArrowRight size={12} />
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
