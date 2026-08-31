import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import type { DashboardSummary, RecentRunItem } from '../types/api';
import {
  DEMO_DASHBOARD_SUMMARY,
  DEMO_RECENT_RUNS
} from '../data/demoFixtures';
import { SummaryCards } from '../components/SummaryCards';
import { RecentRunsTable } from '../components/RecentRunsTable';
import { AttentionQueue } from '../components/AttentionQueue';
import { ConnectRepoWizard } from '../components/ConnectRepoWizard';
import {
  PlusCircle,
  RefreshCw,
  AlertCircle,
  FolderGit2,
  Sparkles,
  ShieldCheck
} from 'lucide-react';

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { demoMode, setDemoMode, activeRepoId } = useWorkspace();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [runs, setRuns] = useState<RecentRunItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isConnectWizardOpen, setIsConnectWizardOpen] = useState<boolean>(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);

    if (demoMode) {
      setTimeout(() => {
        setSummary(DEMO_DASHBOARD_SUMMARY);
        setRuns(DEMO_RECENT_RUNS);
        setLoading(false);
      }, 200);
      return;
    }

    try {
      const repoIdFilter = activeRepoId === 'all' ? undefined : activeRepoId;
      const [sumData, recentRuns] = await Promise.all([
        api.getDashboardSummary(),
        api.getRecentRuns(20, 0, repoIdFilter),
      ]);
      setSummary(sumData);
      setRuns(recentRuns);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('SupportPilot backend is currently unavailable.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [demoMode, activeRepoId]);

  const isEmptyWorkspace = !loading && !error && (!summary || summary.total_tickets === 0) && runs.length === 0;

  return (
    <div>
      {/* Demo Banner */}
      {demoMode && (
        <div className="demo-banner">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <ShieldCheck size={16} />
            <span>DEMO MODE — Displaying curated demonstration dataset for portfolio review.</span>
          </div>
          <button
            onClick={() => setDemoMode(false)}
            style={{ background: 'none', border: 'none', color: '#92400E', cursor: 'pointer', textDecoration: 'underline', fontWeight: 600, fontSize: '0.75rem' }}
          >
            Switch to Live Data
          </button>
        </div>
      )}

      {/* Page Header */}
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h1 className="page-title">SupportPilot Operations Dashboard</h1>
            <span className="badge badge-primary">
              <Sparkles size={10} /> Live Telemetry
            </span>
          </div>
          <p className="page-subtitle">
            Monitor support issues, AI triage decisions, claim verification, and human engineering handoffs.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-secondary" onClick={fetchData} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spinner' : ''} />
            Refresh
          </button>

          <button className="btn btn-secondary" onClick={() => setIsConnectWizardOpen(true)}>
            <FolderGit2 size={14} />
            Connect Repository
          </button>

          <button className="btn btn-primary" onClick={() => navigate('/analyze')}>
            <PlusCircle size={14} />
            Analyze Issue
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <div>{error}</div>
        </div>
      )}

      {/* KPI Section */}
      <SummaryCards summary={summary} loading={loading} />

      {/* Attention Queue (Needs Your Attention) */}
      {!loading && <AttentionQueue items={runs} />}

      {/* Empty State Banner if 0 tickets in normal workspace */}
      {isEmptyWorkspace && (
        <div className="empty-state" style={{ marginBottom: '1.5rem' }}>
          <FolderGit2 size={36} color="var(--text-dim)" style={{ marginBottom: '0.75rem' }} />
          <h3 className="empty-state-title">No issues have been analyzed yet</h3>
          <p className="empty-state-subtitle">
            Connect a GitHub repository to automatically sync support tickets, or run manual issue triage.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '0.75rem' }}>
            <button className="btn btn-secondary" onClick={() => setDemoMode(true)}>
              <Sparkles size={14} />
              <span>Enable Demo Mode</span>
            </button>
            <button className="btn btn-primary" onClick={() => setIsConnectWizardOpen(true)}>
              <FolderGit2 size={14} />
              <span>Connect Repository</span>
            </button>
          </div>
        </div>
      )}

      {/* Recent Issues / Runs Table */}
      <RecentRunsTable runs={runs} loading={loading} />

      {/* Connect Repo Modal */}
      <ConnectRepoWizard
        isOpen={isConnectWizardOpen}
        onClose={() => setIsConnectWizardOpen(false)}
        onSuccess={() => fetchData()}
      />
    </div>
  );
};
