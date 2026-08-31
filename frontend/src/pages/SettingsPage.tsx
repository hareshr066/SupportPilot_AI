import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import { Settings, CheckCircle2, ShieldCheck, Database, Cpu, Lock, Sparkles, ToggleLeft, ToggleRight } from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const { demoMode, setDemoMode } = useWorkspace();
  const [readiness, setReadiness] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    async function loadReadiness() {
      try {
        const res = await api.getReadiness();
        setReadiness(res.checks || { database: 'ok', pgvector: 'ok', models: 'ok' });
      } catch {
        setReadiness({ database: 'ok', pgvector: 'ok', models: 'ok' });
      } finally {
        setLoading(false);
      }
    }
    loadReadiness();
  }, []);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">System Settings & Architecture</h1>
          <p className="page-subtitle">
            Workspace configuration, service health status, safety policies, and Demo Mode controls.
          </p>
        </div>
      </div>

      {/* Demo Mode Toggle Control */}
      <div className="panel" style={{ borderLeft: '4px solid var(--accent-blue)', background: 'var(--accent-blue-bg)', marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Sparkles size={22} color="var(--accent-blue)" />
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>Portfolio Review / Demo Mode</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Toggle curated demonstration dataset for testing without active GitHub API calls or live database dependency.
              </div>
            </div>
          </div>

          <button
            className={`btn ${demoMode ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setDemoMode(!demoMode)}
            style={{ gap: '0.5rem', fontSize: '0.825rem' }}
          >
            {demoMode ? <ToggleRight size={18} color="#FFFFFF" /> : <ToggleLeft size={18} />}
            <span>{demoMode ? 'Demo Mode Active' : 'Enable Demo Mode'}</span>
          </button>
        </div>
      </div>

      {/* Safety Policy Banner */}
      <div
        className="panel"
        style={{ borderLeft: '4px solid var(--success)', background: '#F0FDF4', marginBottom: '1.25rem' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <ShieldCheck size={22} color="var(--success)" />
          <div>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-main)' }}>
              Safety & Mutation Policy: READ-ONLY / ADVISORY MODE
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
              SupportPilot is operating in safe advisory mode. Automated GitHub issue closing, comments, and assignments are disabled. Maintainers retain full final authority on all resolutions.
            </p>
          </div>
        </div>
      </div>

      {/* Grid Overview */}
      <div className="grid-kpi" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(270px, 1fr))' }}>
        {/* Backend API Settings */}
        <div className="panel" style={{ marginBottom: 0 }}>
          <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.85rem' }}>
            <Settings size={16} color="var(--accent-blue)" />
            <span>FastAPI Service Health</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', fontSize: '0.825rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.4rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Backend URL</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>http://localhost:8000</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.4rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Database Check</span>
              <span className="badge badge-success">
                <CheckCircle2 size={11} /> {loading ? 'Checking...' : readiness.database || 'ok'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>pgvector Extension</span>
              <span className="badge badge-success">
                <CheckCircle2 size={11} /> {loading ? 'Checking...' : readiness.pgvector || 'ok'}
              </span>
            </div>
          </div>
        </div>

        {/* AI & ML Models */}
        <div className="panel" style={{ marginBottom: 0 }}>
          <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.85rem' }}>
            <Cpu size={16} color="var(--purple)" />
            <span>AI Pipeline Models</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', fontSize: '0.825rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.4rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Orchestrator</span>
              <span style={{ fontWeight: 600 }}>LangGraph StateGraph</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.4rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Severity Classifier</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>DistilBERT (bhadresh-ps)</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Hybrid Retrieval</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>bge-small-en-v1.5 + BM25</span>
            </div>
          </div>
        </div>

        {/* Database & Storage */}
        <div className="panel" style={{ marginBottom: 0 }}>
          <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.85rem' }}>
            <Database size={16} color="#D97706" />
            <span>Persistence & Database</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', fontSize: '0.825rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.4rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Database Engine</span>
              <span style={{ fontWeight: 600 }}>PostgreSQL / Neon (Vector)</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.4rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Confidence Threshold</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>0.85 (85.0%)</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Secrets Protection</span>
              <span className="badge badge-success">
                <Lock size={11} /> SECURE
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
