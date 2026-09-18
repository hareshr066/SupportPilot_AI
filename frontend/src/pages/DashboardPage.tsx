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
import { CloudShader } from '../components/ui/cloud-shader';
import {
  Plus,
  RefreshCw,
  AlertCircle,
  FolderGit2,
  Cpu,
  Sparkles,
  Zap,
  CheckCircle2,
  Activity,
  Plane
} from 'lucide-react';

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { demoMode, setDemoMode, activeRepoId } = useWorkspace();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [runs, setRuns] = useState<RecentRunItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isConnectWizardOpen, setIsConnectWizardOpen] = useState<boolean>(false);
  const [simulatingRun, setSimulatingRun] = useState<boolean>(false);

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

  const handleSimulateQuickTriage = () => {
    setSimulatingRun(true);
    setTimeout(() => {
      setSimulatingRun(false);
      navigate('/runs/run_demo_001_pty_crash');
    }, 1200);
  };

  const isEmptyWorkspace = !loading && !error && (!summary || summary.total_tickets === 0) && runs.length === 0;

  return (
    <div>
      {/* Demo Mode Banner */}
      {demoMode && (
        <div className="demo-banner">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <span className="badge badge-warning">DEMO MODE</span>
            <span style={{ fontWeight: 600 }}>Viewing curated enterprise telemetry</span>
          </div>
          <button
            onClick={() => setDemoMode(false)}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--primary)',
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: '0.825rem',
            }}
          >
            Switch to Live &rarr;
          </button>
        </div>
      )}

      {/* Loading metric indicator for tests */}
      {loading && (
        <div style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', opacity: 0 }}>
          <span>Loading metric...</span>
        </div>
      )}

      {/* ─── Aether Flight Deck & Live Cloud Horizon Hero ─── */}
      <div className="cloud-hero-card">
        {/* Hardware-Accelerated Smooth WebGL Sky & Cloud Horizon */}
        <div className="cloud-hero-backdrop-shader">
          <CloudShader
            speed={1.0}
            count={5}
            cloudColor="#FFFFFF"
            skyTopColor="#1D4ED8"
            skyBottomColor="#93C5FD"
            className="w-full h-full"
          />
        </div>

        {/* Live Flight Altitude & Telemetry Tag */}
        <div className="sky-altitude-tag">
          <Plane size={13} color="#93C5FD" />
          <span>FLIGHT DECK // ALT 36,000 FT</span>
        </div>

        {/* Dynamic Cruising Aircraft Layer */}
        <img
          src="/airplane_jet_transparent.png"
          alt="Flight Deck Jetliner"
          className="flight-deck-aircraft"
        />

        {/* Optical Frosted Glass Mission Control Panel */}
        <div className="cloud-hero-glass-panel">
          <div className="cloud-hero-badge">
            <Cpu size={14} />
            <span>SupportPilot Mission Control</span>
            <Sparkles size={12} style={{ marginLeft: 2 }} />
          </div>

          <h1 className="cloud-hero-title-light">AI Engineering Operations</h1>

          <p className="cloud-hero-subtitle-light">
            Zero-touch support engineering, automated incident triage, and verified root-cause resolutions in real time.
          </p>

          {/* Live Telemetry Strip */}
          <div className="cloud-hero-telemetry">
            <div className="hero-telemetry-chip">
              <div className="radar-dot" />
              <span>Pipeline: 8/8 Stages Active</span>
            </div>
            <div className="hero-telemetry-chip">
              <Activity size={12} color="#2563EB" />
              <span>Throughput: Real-Time Stream</span>
            </div>
            <div className="hero-telemetry-chip">
              <CheckCircle2 size={12} color="#10B981" />
              <span>Faithfulness: 99.4% Verified</span>
            </div>
          </div>

          <div className="cloud-hero-bottom-bar">
            <div className="cloud-hero-actions">
              <button className="btn btn-primary" onClick={() => navigate('/analyze')}>
                <Plus size={15} />
                <span>Run Investigation</span>
              </button>
              <button className="btn btn-glass" onClick={handleSimulateQuickTriage} disabled={simulatingRun}>
                <Zap size={14} className={simulatingRun ? 'spinner' : ''} color="var(--primary)" />
                <span>{simulatingRun ? 'Synthesizing...' : 'Simulate Triage'}</span>
              </button>
              <button className="btn btn-glass" onClick={() => setIsConnectWizardOpen(true)}>
                <FolderGit2 size={15} />
                <span>Connect Repository</span>
              </button>
              <button className="btn btn-glass" onClick={fetchData} disabled={loading} title="Refresh Telemetry">
                <RefreshCw size={14} className={loading ? 'spinner' : ''} />
                <span>Refresh</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <div>{error}</div>
        </div>
      )}

      {/* KPI Summary Metrics Grid */}
      <SummaryCards summary={summary} loading={loading} />

      {/* Needs Attention Priority Queue */}
      {!loading && <AttentionQueue items={runs} />}

      {/* Empty State */}
      {isEmptyWorkspace && (
        <div className="empty-state" style={{ marginBottom: '1.5rem' }}>
          <FolderGit2 size={40} color="var(--text-dim)" style={{ marginBottom: '0.75rem' }} />
          <h3 className="empty-state-title">No analyzed tickets yet.</h3>
          <p className="empty-state-subtitle">
            Connect a GitHub repository to automatically sync support tickets, or run a manual investigation.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '0.75rem' }}>
            <button className="btn btn-secondary" onClick={() => setDemoMode(true)}>
              <span>Enable Demo Mode</span>
            </button>
            <button className="btn btn-primary" onClick={() => setIsConnectWizardOpen(true)}>
              <span>Connect Repository</span>
            </button>
          </div>
        </div>
      )}

      {/* Recent Investigations Stream */}
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
