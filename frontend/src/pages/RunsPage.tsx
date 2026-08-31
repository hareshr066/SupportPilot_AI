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
          <h1 className="page-title">AI Pipeline Execution Runs</h1>
          <p className="page-subtitle">
            Audit history of all state graph executions, stage latencies, claim verifications, and triage decisions.
          </p>
        </div>

        <button className="btn btn-secondary" onClick={fetchRuns} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'spinner' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <div>{error}</div>
        </div>
      )}

      <div className="panel">
        <div className="panel-header">
          <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <FileCode size={18} color="var(--primary)" />
            <span>Execution Runs ({runs.length})</span>
          </div>
        </div>

        {loading ? (
          <div className="empty-state">Loading pipeline execution runs...</div>
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
                  <th>Ticket Title</th>
                  <th>Repository</th>
                  <th>Severity</th>
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
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--accent-blue)' }}>
                      {r.pipeline_run_id.slice(0, 16)}...
                    </td>
                    <td style={{ fontWeight: 500 }}>{r.title}</td>
                    <td>{r.repository_name}</td>
                    <td>
                      <SeverityBadge severity={r.severity} />
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{r.root_cause_cluster}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      {(r.calibrated_confidence * 100).toFixed(1)}%
                    </td>
                    <td>
                      <StatusBadge decision={r.final_decision} status={r.status} />
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{r.total_latency_ms} ms</td>
                    <td>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/runs/${r.pipeline_run_id}`);
                        }}
                      >
                        Inspect <ArrowRight size={12} />
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
