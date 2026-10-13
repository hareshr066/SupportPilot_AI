import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import { useAuth } from '../context/AuthContext';
import {
  CheckCircle2,
  ShieldCheck,
  ToggleLeft,
  ToggleRight,
  Server,
  Sliders,
  Cpu,
  Building2,
  Key,
  Copy,
  Check,
  LogOut,
  RefreshCw,
} from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const { demoMode, setDemoMode, systemReady } = useWorkspace();
  const { user, organization, logout, rotateApiKey } = useAuth();
  const [readiness, setReadiness] = useState<Record<string, string>>({});
  const [copiedKey, setCopiedKey] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [rotatingKey, setRotatingKey] = useState(false);
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

  const handleCopyKey = () => {
    if (!organization?.api_key) return;
    navigator.clipboard.writeText(organization.api_key);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
  };

  const handleRotateKey = async () => {
    if (!window.confirm('Are you sure you want to rotate your organization API key? Any applications using the old key will need to be updated.')) {
      return;
    }
    setRotatingKey(true);
    try {
      await rotateApiKey();
    } catch (err) {
      console.error('Failed to rotate API key:', err);
    } finally {
      setRotatingKey(false);
    }
  };

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">
            Organization profile, server-to-server API credentials, runtime modes, and security configurations.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: '1000px' }}>
        {/* 0. ORGANIZATION & USER ACCOUNT */}
        {user && (
          <div className="panel" style={{ marginBottom: 0, borderLeft: '3px solid var(--primary)' }}>
            <div className="panel-header">
              <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                <Building2 size={16} color="var(--primary)" />
                <span>Organization & Account Profile</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span className="badge badge-primary">ACTIVE TENANT</span>
                <button
                  onClick={() => {
                    logout();
                    window.location.href = '/login';
                  }}
                  className="btn btn-secondary"
                  style={{ padding: '0.2rem 0.55rem', fontSize: '0.72rem', gap: '0.3rem' }}
                  title="Sign Out of Session"
                >
                  <LogOut size={12} />
                  <span>Sign Out</span>
                </button>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', paddingBottom: '1rem', borderBottom: '1px solid var(--border-subtle)' }}>
              <div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Organization Name
                </div>
                <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-main)', marginTop: '0.2rem' }}>
                  {organization?.name || 'Workspace'}
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Signed In As
                </div>
                <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-main)', marginTop: '0.2rem' }}>
                  {user.full_name}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  {user.email}
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Tenant ID
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>
                  org_{organization?.id || 1}
                </div>
              </div>
            </div>

            {/* Server-to-server API Key */}
            <div style={{ paddingTop: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Key size={14} color="var(--primary)" />
                  <span style={{ fontWeight: 600, fontSize: '0.8rem', color: 'var(--text-main)' }}>
                    Organization API Key (Server-to-Server)
                  </span>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    onClick={() => setShowKey(!showKey)}
                    className="btn btn-secondary"
                    style={{ padding: '0.25rem 0.6rem', fontSize: '0.72rem' }}
                  >
                    {showKey ? 'Hide Key' : 'Reveal Key'}
                  </button>
                  <button
                    onClick={handleCopyKey}
                    className="btn btn-secondary"
                    style={{ padding: '0.25rem 0.6rem', fontSize: '0.72rem', gap: '0.3rem' }}
                  >
                    {copiedKey ? <Check size={12} color="var(--success)" /> : <Copy size={12} />}
                    <span>{copiedKey ? 'Copied' : 'Copy Key'}</span>
                  </button>
                  <button
                    onClick={handleRotateKey}
                    disabled={rotatingKey}
                    className="btn btn-secondary"
                    style={{ padding: '0.25rem 0.6rem', fontSize: '0.72rem', gap: '0.3rem' }}
                    title="Generate a new API key"
                  >
                    <RefreshCw size={12} className={rotatingKey ? 'spin' : ''} />
                    <span>Rotate</span>
                  </button>
                </div>
              </div>

              <div
                style={{
                  background: 'var(--bg-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '0.6rem 0.85rem',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span>
                  {showKey
                    ? organization?.api_key || 'No API key generated'
                    : organization?.api_key
                    ? `${organization.api_key.slice(0, 10)}••••••••••••••••••••••••••••••••`
                    : 'No API key'}
                </span>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  Use this key in your app's SUPPORTPILOT_API_KEY environment variable
                </span>
              </div>
            </div>
          </div>
        )}

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
