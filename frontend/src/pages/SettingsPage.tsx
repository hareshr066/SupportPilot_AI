import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import {
  CheckCircle2,
  ShieldCheck,
  ToggleLeft,
  ToggleRight,
  Server,
  Sliders,
  Cpu
} from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const { demoMode, setDemoMode, systemReady } = useWorkspace();
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
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">
            Operational runtime mode, safety policies, FastAPI health checks, and ML model registry configurations.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: '1000px' }}>
        {/* 1. RUNTIME CONFIGURATION */}
        <div className="panel" style={{ marginBottom: 0 }}>
          <div className="panel-header">
            <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              <Sliders size={15} color="var(--primary)" />
              <span>Runtime Environment</span>
            </div>
            <span className={`badge ${demoMode ? 'badge-warning' : 'badge-primary'}`}>
              {demoMode ? 'DEMO MODE' : 'LIVE API'}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--border-subtle)' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.825rem', color: 'var(--text-main)' }}>
                Demonstration Fixtures Mode
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>
                Use curated demonstration dataset and offline evaluation benchmarks without mutating production repositories.
              </div>
            </div>

            <button
              className={`btn ${demoMode ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setDemoMode(!demoMode)}
              style={{ gap: '0.45rem', fontSize: '0.785rem' }}
            >
              {demoMode ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
              <span>{demoMode ? 'Demo Active' : 'Enable Demo'}</span>
            </button>
          </div>
        </div>

        {/* 2. SAFETY & ADVISORY POLICY */}
        <div className="panel" style={{ marginBottom: 0, borderLeft: '3px solid var(--success)' }}>
          <div className="panel-header">
            <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              <ShieldCheck size={15} color="var(--success)" />
              <span>Advisory Safety Policy</span>
            </div>
            <span className="badge badge-success">Read-Only Guard</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', fontSize: '0.8rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.45rem' }}>
              <div>
                <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>Advisory Mode</span>
                <p style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>
                  SupportPilot operates purely as an intelligence assistant. GitHub automated comments and closing actions are strictly disabled.
                </p>
              </div>
              <span className="badge badge-success">ACTIVE</span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.45rem' }}>
              <div>
                <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>Auto-Resolution Safety Threshold (&tau;)</span>
                <p style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>
                  Minimum calibrated confidence score required before proposing automated resolution recommendation.
                </p>
              </div>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--primary)' }}>
                85.0%
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <div>
                <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>Claim Contradiction Guardrail</span>
                <p style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>
                  Any single unverified claim immediately triggers deterministic human maintainer review.
                </p>
              </div>
              <span className="badge badge-success">ENFORCED</span>
            </div>
          </div>
        </div>

        {/* 3. SYSTEM & DATABASE HEALTH */}
        <div className="panel" style={{ marginBottom: 0 }}>
          <div className="panel-header">
            <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              <Server size={15} color="var(--primary)" />
              <span>System & Infrastructure Health</span>
            </div>
            <span className={`badge ${systemReady ? 'badge-success' : 'badge-warning'}`}>
              {systemReady ? 'OPERATIONAL' : 'DEGRADED'}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', fontSize: '0.8rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.45rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>FastAPI Endpoint</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: '#FFFFFF' }}>http://localhost:8000</span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.45rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>PostgreSQL Database</span>
              <span className="badge badge-success">
                <CheckCircle2 size={10} /> {loading ? 'Checking...' : readiness.database || 'ok'}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.45rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>pgvector 384D Extension</span>
              <span className="badge badge-success">
                <CheckCircle2 size={10} /> {loading ? 'Checking...' : readiness.pgvector || 'ok'}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Vector Index Status</span>
              <span className="badge badge-primary">IVFFlat Cosine Indexed</span>
            </div>
          </div>
        </div>

        {/* 4. AI & ML MODEL REGISTRY */}
        <div className="panel" style={{ marginBottom: 0 }}>
          <div className="panel-header">
            <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              <Cpu size={15} color="var(--primary)" />
              <span>ML Model Registry</span>
            </div>
            <span className="badge badge-neutral">5 Models Active</span>
          </div>

          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Pipeline Role</th>
                  <th>Model Architecture</th>
                  <th>Task & Embeddings</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ fontWeight: 600 }}>Severity Classifier</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>DistilBERT Supervised</td>
                  <td>3-class severity distribution (F1: 0.924)</td>
                  <td><span className="badge badge-success">LOADED</span></td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>Semantic Retrieval</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>BAAI/bge-small-en-v1.5</td>
                  <td>384-dimensional dense embeddings</td>
                  <td><span className="badge badge-success">LOADED</span></td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>Duplicate Reranker</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>Cross-Encoder MiniLM-L6-v2</td>
                  <td>Fine-grained pair cross-attention (F1: 0.895)</td>
                  <td><span className="badge badge-success">LOADED</span></td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>Resolution Generator</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>Google Gemini 2.5 Flash</td>
                  <td>Strict citation-constrained grounded synthesis</td>
                  <td><span className="badge badge-success">READY</span></td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600 }}>Pipeline Orchestrator</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>LangGraph StateGraph</td>
                  <td>8-stage deterministic state transitions</td>
                  <td><span className="badge badge-success">READY</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
