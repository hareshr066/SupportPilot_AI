import React, { useEffect, useState } from 'react';
import { api, APIClientError } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import type { Repository, SyncStatusResponse } from '../types/api';
import { DEMO_REPOSITORIES } from '../data/demoFixtures';
import { ConnectRepoWizard } from '../components/ConnectRepoWizard';
import {
  FolderGit2,
  Plus,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  ExternalLink
} from 'lucide-react';

export const RepositoriesPage: React.FC = () => {
  const { demoMode } = useWorkspace();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Wizard State
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
        issues_processed: 25,
        comments_processed: 60,
        pull_requests_processed: 8,
      });
      setTimeout(() => setActiveSyncId(null), 2500);
      return;
    }

    try {
      const res = await api.syncRepository(repoId);
      setActiveSyncId(res.sync_run_id);
      setSyncStatus({
        sync_run_id: res.sync_run_id,
        repository_id: repoId,
        status: 'RUNNING',
        started_at: res.started_at,
        issues_processed: 0,
        comments_processed: 0,
        pull_requests_processed: 0,
      });

      const pollInterval = window.setInterval(async () => {
        try {
          const status = await api.getSyncStatus(res.sync_run_id);
          setSyncStatus(status);
          if (status.status === 'COMPLETED' || status.status === 'FAILED') {
            window.clearInterval(pollInterval);
            setActiveSyncId(null);
            fetchRepos();
          }
        } catch {
          window.clearInterval(pollInterval);
          setActiveSyncId(null);
        }
      }, 2000);
    } catch (err: unknown) {
      if (err instanceof APIClientError) {
        setError(`Sync error: ${err.message}`);
      } else {
        setError('Failed to initiate repository sync.');
      }
      setActiveSyncId(null);
    }
  };

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <h1 className="page-title">
              <FolderGit2 size={22} color="var(--primary)" />
              Repositories
            </h1>
            <span className="badge badge-neutral">{repositories.length} connected</span>
          </div>
          <p className="page-subtitle">
            Manage connected GitHub repositories, continuous issue indexing, and vector synchronization.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.6rem' }}>
          <button className="btn btn-secondary" onClick={fetchRepos} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spinner' : ''} />
            <span>Refresh</span>
          </button>
          <button className="btn btn-primary" onClick={() => setIsWizardOpen(true)}>
            <Plus size={14} />
            <span>Connect Repository</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <div>{error}</div>
        </div>
      )}

      {/* Sync Status Toast Banner if active */}
      {syncStatus && (
        <div
          className="panel"
          style={{
            borderLeft: '3px solid var(--primary)',
            padding: '0.75rem 1rem',
            marginBottom: '1.25rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '0.85rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            {syncStatus.status === 'RUNNING' ? (
              <div className="spinner" style={{ width: 14, height: 14 }} />
            ) : (
              <CheckCircle2 size={16} color="var(--success)" />
            )}
            <span>
              Sync Status: <strong>{syncStatus.status}</strong> — {syncStatus.issues_processed ?? 0} issues,{' '}
              {syncStatus.comments_processed ?? 0} comments indexed.
            </span>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
            Run: {syncStatus.sync_run_id}
          </span>
        </div>
      )}

      {/* Repositories Table */}
      <div className="panel">
        {loading ? (
          <div className="empty-state" style={{ padding: '3rem' }}>
            <div className="spinner" style={{ margin: '0 auto 0.65rem auto' }} />
            <p style={{ fontSize: '0.875rem' }}>Loading repositories...</p>
          </div>
        ) : repositories.length === 0 ? (
          <div className="empty-state" style={{ padding: '3rem' }}>
            <FolderGit2 size={36} style={{ color: 'var(--text-dim)', marginBottom: '0.65rem' }} />
            <p className="empty-state-title">No repositories connected yet</p>
            <p className="empty-state-subtitle">
              Connect your first GitHub repository to start indexing historical resolutions and automated ticket triage.
            </p>
            <button className="btn btn-primary" onClick={() => setIsWizardOpen(true)}>
              <span>Connect Repository</span>
            </button>
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Repository</th>
                  <th>Status</th>
                  <th>Issues Indexed</th>
                  <th>Webhook</th>
                  <th>Auto-Triage</th>
                  <th>Last Synced</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {repositories.map((repo) => (
                  <tr key={repo.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
                        <FolderGit2 size={16} color="var(--primary)" />
                        <span style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '0.875rem' }}>
                          {repo.full_name || `${repo.owner}/${repo.name}`}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginLeft: '1.5rem', marginTop: '0.15rem' }}>
                        ID: {repo.id} • GitHub Sync Ready
                      </div>
                    </td>
                    <td>
                      <span className="badge badge-success">
                        <CheckCircle2 size={11} /> Connected
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-main)' }}>
                        {repo.issue_count ?? 0}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${repo.webhook_enabled ? 'badge-primary' : 'badge-neutral'}`}>
                        {repo.webhook_enabled ? 'Active' : 'Disabled'}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${repo.auto_analysis_enabled ? 'badge-success' : 'badge-neutral'}`}>
                        {repo.auto_analysis_enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                      2 min ago
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '0.45rem' }}>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '0.3rem 0.65rem', fontSize: '0.775rem' }}
                          onClick={() => handleSyncRepository(repo.id)}
                          disabled={activeSyncId !== null}
                        >
                          <RefreshCw size={12} className={activeSyncId ? 'spinner' : ''} />
                          <span>Trigger Sync</span>
                        </button>

                        <a
                          href={`https://github.com/${repo.full_name || `${repo.owner}/${repo.name}`}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn btn-secondary"
                          style={{ padding: '0.3rem 0.55rem', fontSize: '0.775rem' }}
                        >
                          <ExternalLink size={12} />
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Connect Repo Modal */}
      <ConnectRepoWizard
        isOpen={isWizardOpen}
        onClose={() => setIsWizardOpen(false)}
        onSuccess={() => fetchRepos()}
      />
    </div>
  );
};
