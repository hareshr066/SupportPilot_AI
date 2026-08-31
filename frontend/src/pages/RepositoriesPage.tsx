import React, { useEffect, useState } from 'react';
import { api, APIClientError } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import type { Repository, SyncStatusResponse } from '../types/api';
import { DEMO_REPOSITORIES } from '../data/demoFixtures';
import { ConnectRepoWizard } from '../components/ConnectRepoWizard';
import { GitFork, Plus, RefreshCw, CheckCircle2, AlertCircle, ExternalLink } from 'lucide-react';

export const RepositoriesPage: React.FC = () => {
  const { demoMode } = useWorkspace();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Wizard state
  const [isWizardOpen, setIsWizardOpen] = useState<boolean>(false);

  // Sync Progress State
  const [activeSyncId, setActiveSyncId] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncStatusResponse | null>(null);

  const fetchRepos = async () => {
    setLoading(true);
    setError(null);

    if (demoMode) {
      setTimeout(() => {
        setRepositories(DEMO_REPOSITORIES);
        setLoading(false);
      }, 200);
      return;
    }

    try {
      const data = await api.getRepositories();
      setRepositories(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to fetch repositories.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRepos();
  }, [demoMode]);

  const handleSyncRepository = async (repoId: number) => {
    setError(null);
    if (demoMode) {
      setActiveSyncId('sync_demo_99');
      setSyncStatus({
        sync_run_id: 'sync_demo_99',
        repository_id: repoId,
        status: 'COMPLETED',
        started_at: new Date().toISOString(),
        completed_at: new Date().toISOString(),
        issues_processed: 42,
        comments_processed: 120,
        pull_requests_processed: 18,
      });
      setTimeout(() => setActiveSyncId(null), 2000);
      return;
    }

    try {
      const syncRes = await api.syncRepository(repoId);
      setActiveSyncId(syncRes.sync_run_id);
      pollSyncStatus(syncRes.sync_run_id);
    } catch (err: unknown) {
      if (err instanceof APIClientError) {
        setError(err.message);
      } else {
        setError('Failed to start repository sync.');
      }
    }
  };

  const pollSyncStatus = (syncRunId: string) => {
    const interval = window.setInterval(async () => {
      try {
        const st = await api.getSyncStatus(syncRunId);
        setSyncStatus(st);
        if (['COMPLETED', 'FAILED', 'PARTIAL'].includes(st.status)) {
          window.clearInterval(interval);
          setActiveSyncId(null);
          fetchRepos();
        }
      } catch (err) {
        console.error('Sync polling error', err);
        window.clearInterval(interval);
      }
    }, 1500);
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Repositories</h1>
          <p className="page-subtitle">
            Connect GitHub repositories to sync historical resolved issues, generate embeddings, and build hybrid RAG vector indexes.
          </p>
        </div>

        <button className="btn btn-primary" onClick={() => setIsWizardOpen(true)}>
          <Plus size={14} /> Connect Repository
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <div>{error}</div>
        </div>
      )}

      {/* Sync Status Banner */}
      {syncStatus && (
        <div
          className="panel"
          style={{ borderLeft: '4px solid var(--accent-blue)', background: 'var(--accent-blue-bg)' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <RefreshCw size={18} className={activeSyncId ? 'spinner' : ''} color="var(--accent-blue)" />
              <div>
                <div style={{ fontWeight: 600 }}>Sync Run: {syncStatus.sync_run_id}</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Processed: {syncStatus.issues_processed} issues | {syncStatus.comments_processed} comments |{' '}
                  {syncStatus.pull_requests_processed} PRs
                </div>
              </div>
            </div>
            <span className="badge badge-purple">{syncStatus.status}</span>
          </div>
        </div>
      )}

      {/* Repository Table */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">Connected Repositories ({repositories.length})</div>
          <button className="btn btn-secondary" onClick={fetchRepos} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spinner' : ''} /> Refresh
          </button>
        </div>

        {loading ? (
          <div className="empty-state">Loading repositories...</div>
        ) : repositories.length === 0 ? (
          <div className="empty-state">
            <GitFork size={36} color="var(--text-dim)" style={{ marginBottom: '0.5rem' }} />
            <p className="empty-state-title">No repositories connected yet.</p>
            <p className="empty-state-subtitle">Connect your first GitHub repository to enable automatic issue triage.</p>
            <button className="btn btn-primary" onClick={() => setIsWizardOpen(true)}>
              <Plus size={14} /> Connect Repository
            </button>
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Full Name</th>
                  <th>Issues Ingested</th>
                  <th>Webhook Status</th>
                  <th>Auto Triage</th>
                  <th>Last Synced</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {repositories.map((repo) => (
                  <tr key={repo.id}>
                    <td style={{ fontWeight: 600 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <span>{repo.full_name || `${repo.owner}/${repo.name}`}</span>
                        {repo.html_url && (
                          <a href={repo.html_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-dim)' }}>
                            <ExternalLink size={12} />
                          </a>
                        )}
                      </div>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{repo.issue_count}</td>
                    <td>
                      <span className="badge badge-success">
                        <CheckCircle2 size={11} /> Active
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${repo.auto_analysis_enabled ? 'badge-success' : 'badge-neutral'}`}>
                        {repo.auto_analysis_enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      {repo.last_synced_at ? new Date(repo.last_synced_at).toLocaleString() : 'Never'}
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '0.25rem 0.55rem', fontSize: '0.75rem' }}
                        onClick={() => handleSyncRepository(repo.id)}
                        disabled={!!activeSyncId}
                      >
                        <RefreshCw size={12} /> Trigger Sync
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ConnectRepoWizard
        isOpen={isWizardOpen}
        onClose={() => setIsWizardOpen(false)}
        onSuccess={() => fetchRepos()}
      />
    </div>
  );
};
