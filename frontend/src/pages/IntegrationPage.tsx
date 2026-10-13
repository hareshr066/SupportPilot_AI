import React, { useEffect, useState, useCallback } from 'react';
import { api } from '../api/client';
import type { Repository } from '../types/api';
import { useAuth } from '../context/AuthContext';
import { ConnectRepoWizard } from '../components/ConnectRepoWizard';
import {
  Plug,
  Plus,
  RefreshCw,
  Copy,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Terminal,
  Code,
  BookOpen,
  Zap,
  Globe,
  Key,
  FolderGit2,
  ExternalLink,
  AlertCircle,
  ArrowRight,
} from 'lucide-react';

// ── helpers ──────────────────────────────────────────────────────────────────

function useCopy(timeout = 2000) {
  const [copied, setCopied] = useState<string | null>(null);
  const copy = useCallback((id: string, text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(id);
      setTimeout(() => setCopied(null), timeout);
    });
  }, [timeout]);
  return { copied, copy };
}

function CodeBlock({ id, code, lang = 'bash', onCopy }: { id: string; code: string; lang?: string; onCopy: (id: string, text: string) => void; }) {
  return (
    <div style={{ position: 'relative', margin: '0.75rem 0' }}>
      <pre style={{
        background: '#0f172a',
        color: '#e2e8f0',
        borderRadius: 'var(--radius-sm)',
        padding: '0.85rem 1rem',
        fontSize: '0.78rem',
        lineHeight: 1.6,
        overflowX: 'auto',
        fontFamily: 'var(--font-mono)',
        margin: 0,
        border: '1px solid rgba(255,255,255,0.06)',
      }}>
        <span style={{ color: '#94a3b8', fontSize: '0.7rem', display: 'block', marginBottom: '0.35rem' }}>{lang}</span>
        {code}
      </pre>
      <button
        id={`copy-${id}`}
        onClick={() => onCopy(id, code)}
        style={{
          position: 'absolute',
          top: '0.5rem',
          right: '0.5rem',
          background: 'rgba(255,255,255,0.08)',
          border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: '4px',
          color: '#94a3b8',
          padding: '0.2rem 0.5rem',
          cursor: 'pointer',
          fontSize: '0.7rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.3rem',
        }}
      >
        <Copy size={11} />
        Copy
      </button>
    </div>
  );
}

// ── main ─────────────────────────────────────────────────────────────────────

export const IntegrationPage: React.FC = () => {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null);
  const [expandedSection, setExpandedSection] = useState<string>('quickstart');
  const { copied, copy } = useCopy();

  const fetchRepos = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getRepositories();
      setRepositories(data);
      if (data.length > 0 && !selectedRepo) {
        setSelectedRepo(data[0]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load repositories.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchRepos(); }, []);

  const { organization } = useAuth();
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'https://your-supportpilot-api.com';
  const apiKey = organization?.api_key || 'sp_live_YOUR_API_KEY';
  const appName = selectedRepo ? (selectedRepo.full_name?.split('/')[0] || selectedRepo.owner) : 'YourApp';

  // ── code snippets ─────────────────────────────────────────────────────────

  const curlSnippet = `curl -X POST ${apiBase}/api/v1/tickets \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: ${apiKey}" \\
  -d '{
    "title": "User cannot log in after password reset",
    "description": "After clicking reset link, user is redirected to /login but gets a 403 error. Steps: 1) Request reset, 2) Click link, 3) Enter new password — error appears.",
    "application": "${appName}",
    "severity": "high",
    "reporter_email": "user@example.com"
  }'`;

  const pythonSnippet = `import requests

SUPPORTPILOT_API = "${apiBase}"
API_KEY = "${apiKey}"  # your organization API key

def submit_support_ticket(title: str, description: str, severity: str = "medium"):
    resp = requests.post(
        f"{SUPPORTPILOT_API}/api/v1/tickets",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
        json={
            "title": title,
            "description": description,
            "application": "${appName}",
            "severity": severity,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"Ticket created: {data['ticket_id']}")  # e.g. SP-42
    return data["ticket_id"]`;

  const jsSnippet = `// supportpilot.js — drop this in your Node/Next.js/Express backend
const SUPPORTPILOT_API = '${apiBase}';
const SUPPORTPILOT_KEY = process.env.SUPPORTPILOT_API_KEY; // never expose in frontend!

export async function submitTicket({ title, description, severity = 'medium', reporterEmail }) {
  const res = await fetch(\`\${SUPPORTPILOT_API}/api/v1/tickets\`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': SUPPORTPILOT_KEY,
    },
    body: JSON.stringify({
      title,
      description,
      application: '${appName}',
      severity,
      reporter_email: reporterEmail,
    }),
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err?.error?.message || 'SupportPilot ticket submission failed');
  }

  const data = await res.json();
  return data.ticket_id; // e.g. "SP-42"
}`;

  const webhookSnippet = `# In your app's error boundary / exception handler:
from your_module.supportpilot import submit_support_ticket

try:
    risky_operation()
except Exception as exc:
    ticket_id = submit_support_ticket(
        title=f"Unhandled error: {type(exc).__name__}",
        description=str(exc),
        severity="critical",
    )
    logger.error(f"Support ticket filed: {ticket_id}")
    raise`;

  const envSnippet = `# Add to your .env (never commit this file)
SUPPORTPILOT_API_URL=${apiBase}
SUPPORTPILOT_API_KEY=${apiKey}
SUPPORTPILOT_APP_NAME=${appName}`;

  // ── accordion toggle ──────────────────────────────────────────────────────

  const toggle = (id: string) =>
    setExpandedSection(prev => (prev === id ? '' : id));

  const Section: React.FC<{
    id: string;
    icon: React.ReactNode;
    title: string;
    subtitle?: string;
    children: React.ReactNode;
  }> = ({ id, icon, title, subtitle, children }) => {
    const open = expandedSection === id;
    return (
      <div
        className="panel"
        style={{ marginBottom: 0, cursor: 'pointer', transition: 'box-shadow 0.15s' }}
      >
        <div
          onClick={() => toggle(id)}
          className="panel-header"
          style={{ cursor: 'pointer', userSelect: 'none' }}
        >
          <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {icon}
            <div>
              <div>{title}</div>
              {subtitle && (
                <div style={{ fontSize: '0.75rem', fontWeight: 400, color: 'var(--text-muted)', marginTop: '1px' }}>
                  {subtitle}
                </div>
              )}
            </div>
          </div>
          {open ? <ChevronDown size={16} color="var(--text-muted)" /> : <ChevronRight size={16} color="var(--text-muted)" />}
        </div>
        {open && (
          <div style={{ padding: '0 0.25rem 0.5rem 0.25rem' }}>
            {children}
          </div>
        )}
      </div>
    );
  };

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Page header */}
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <h1 className="page-title">
              <Plug size={22} color="var(--primary)" />
              Integration Hub
            </h1>
            <span className="badge badge-primary">For Developers</span>
          </div>
          <p className="page-subtitle">
            Connect your GitHub repository, then add SupportPilot to your app in minutes — tickets are automatically triaged by AI the moment they arrive.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.6rem' }}>
          <button className="btn btn-secondary" onClick={fetchRepos} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spinner' : ''} />
            <span>Refresh</span>
          </button>
          <button className="btn btn-primary" id="connect-repo-btn" onClick={() => setIsWizardOpen(true)}>
            <Plus size={14} />
            <span>Connect Repository</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner" style={{ marginBottom: '1rem' }}>
          <AlertCircle size={16} />
          <div>{error}</div>
        </div>
      )}

      {/* ── Top: Connected repos + repo selector ───────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '1rem', marginBottom: '1rem' }}>

        {/* Left: connected repos list */}
        <div className="panel" style={{ marginBottom: 0 }}>
          <div className="panel-header">
            <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              <FolderGit2 size={15} color="var(--primary)" />
              <span>Connected Repositories</span>
            </div>
            <span className="badge badge-neutral">{repositories.length}</span>
          </div>

          {loading ? (
            <div style={{ padding: '1.5rem', textAlign: 'center' }}>
              <div className="spinner" style={{ margin: '0 auto 0.5rem' }} />
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Loading…</p>
            </div>
          ) : repositories.length === 0 ? (
            <div style={{ padding: '1.5rem', textAlign: 'center' }}>
              <FolderGit2 size={28} style={{ color: 'var(--text-dim)', margin: '0 auto 0.5rem' }} />
              <p style={{ fontSize: '0.825rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
                No repository connected yet.
              </p>
              <button className="btn btn-primary" style={{ width: '100%' }} onClick={() => setIsWizardOpen(true)}>
                <Plus size={13} /> Connect your first repo
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {repositories.map(repo => (
                <button
                  key={repo.id}
                  id={`select-repo-${repo.id}`}
                  onClick={() => setSelectedRepo(repo)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.55rem',
                    padding: '0.55rem 0.75rem',
                    borderRadius: 'var(--radius-sm)',
                    background: selectedRepo?.id === repo.id ? 'rgba(37, 99, 235, 0.08)' : 'transparent',
                    border: selectedRepo?.id === repo.id
                      ? '1px solid rgba(37, 99, 235, 0.3)'
                      : '1px solid transparent',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.12s',
                    width: '100%',
                  }}
                >
                  <FolderGit2 size={14} color={selectedRepo?.id === repo.id ? 'var(--primary)' : 'var(--text-muted)'} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: '0.825rem',
                      fontWeight: 600,
                      color: selectedRepo?.id === repo.id ? 'var(--primary)' : 'var(--text-main)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {repo.full_name || `${repo.owner}/${repo.name}`}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                      {repo.issue_count ?? 0} issues indexed
                    </div>
                  </div>
                  <CheckCircle2 size={13} color="var(--success)" />
                </button>
              ))}
              <button
                className="btn btn-secondary"
                style={{ marginTop: '0.25rem', fontSize: '0.775rem' }}
                onClick={() => setIsWizardOpen(true)}
              >
                <Plus size={12} /> Add another
              </button>
            </div>
          )}
        </div>

        {/* Right: quick status for selected repo */}
        {selectedRepo ? (
          <div className="panel" style={{ marginBottom: 0 }}>
            <div className="panel-header">
              <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                <Zap size={15} color="var(--primary)" />
                <span>Integration Status — {selectedRepo.full_name || `${selectedRepo.owner}/${selectedRepo.name}`}</span>
              </div>
              <a
                href={selectedRepo.html_url || `https://github.com/${selectedRepo.full_name}`}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-secondary"
                style={{ padding: '0.25rem 0.55rem', fontSize: '0.75rem' }}
              >
                <ExternalLink size={11} /> GitHub
              </a>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
              {[
                { label: 'Repository ID', value: `#${selectedRepo.id}`, mono: true },
                { label: 'Issues Indexed', value: String(selectedRepo.issue_count ?? 0), mono: true },
                { label: 'Auto-Triage', value: selectedRepo.auto_analysis_enabled ? 'Enabled' : 'Disabled', color: selectedRepo.auto_analysis_enabled ? 'var(--success)' : 'var(--text-muted)' },
              ].map(stat => (
                <div
                  key={stat.label}
                  style={{
                    background: 'var(--bg-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '0.65rem 0.85rem',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>{stat.label}</div>
                  <div style={{
                    fontSize: '1rem',
                    fontWeight: 700,
                    fontFamily: stat.mono ? 'var(--font-mono)' : undefined,
                    color: stat.color || 'var(--text-main)',
                  }}>
                    {stat.value}
                  </div>
                </div>
              ))}
            </div>

            {/* API endpoint info */}
            <div style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', padding: '0.75rem 1rem' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.4rem', fontWeight: 600 }}>
                📡 Your Ticket Submission Endpoint
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                <code style={{ fontSize: '0.8rem', color: 'var(--primary)', fontFamily: 'var(--font-mono)', background: 'rgba(37,99,235,0.08)', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
                  POST {apiBase}/api/v1/tickets
                </code>
                <button
                  className="btn btn-secondary"
                  style={{ padding: '0.2rem 0.55rem', fontSize: '0.72rem' }}
                  onClick={() => copy('endpoint', `${apiBase}/api/v1/tickets`)}
                >
                  {copied === 'endpoint' ? <CheckCircle2 size={11} color="var(--success)" /> : <Copy size={11} />}
                  {copied === 'endpoint' ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.4rem', marginBottom: 0 }}>
                Send tickets from your backend with <code style={{ fontFamily: 'var(--font-mono)' }}>"application": "{appName}"</code> — SupportPilot will route them to this repository automatically.
              </p>
            </div>
          </div>
        ) : (
          <div className="panel" style={{ marginBottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '180px' }}>
            <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
              <Plug size={32} style={{ margin: '0 auto 0.6rem', opacity: 0.3 }} />
              <p style={{ fontSize: '0.85rem' }}>Connect a repository to see your integration details.</p>
              <button className="btn btn-primary" style={{ marginTop: '0.75rem' }} onClick={() => setIsWizardOpen(true)}>
                <Plus size={13} /> Connect Repository <ArrowRight size={13} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Integration Docs accordion ─────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>

        {/* 1. Get your API key */}
        <Section
          id="apikey"
          icon={<Key size={15} color="var(--primary)" />}
          title="Step 1 — Get your API Key"
          subtitle="Secure your ticket submissions"
        >
          <div style={{ fontSize: '0.825rem', color: 'var(--text-muted)', marginBottom: '0.75rem', lineHeight: 1.6 }}>
            Your SupportPilot API key is set in the server's <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--primary)' }}>.env</code> file as{' '}
            <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--primary)' }}>SUPPORTPILOT_API_KEY</code>.
            Pass it with every request — either as <strong>X-API-Key</strong> header or <strong>Authorization: Bearer</strong> header.
            Store it securely in your app's environment variables, never hard-code it.
          </div>
          <CodeBlock id="env" code={envSnippet} lang=".env" onCopy={copy} />
          <div
            style={{
              background: 'rgba(37, 99, 235, 0.05)',
              border: '1px solid rgba(37, 99, 235, 0.15)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.6rem 0.85rem',
              fontSize: '0.78rem',
              color: 'var(--text-muted)',
            }}
          >
            💡 If <code style={{ fontFamily: 'var(--font-mono)' }}>SUPPORTPILOT_API_KEY</code> is not set, the server runs in dev mode and accepts all requests — only do this locally.
          </div>
        </Section>

        {/* 2. Quick start — cURL */}
        <Section
          id="quickstart"
          icon={<Terminal size={15} color="var(--primary)" />}
          title="Step 2 — Submit your first ticket (cURL)"
          subtitle="Test the integration in 30 seconds"
        >
          <p style={{ fontSize: '0.825rem', color: 'var(--text-muted)', marginBottom: '0.6rem', lineHeight: 1.6 }}>
            Run this from your terminal to create a real ticket. Replace <code style={{ fontFamily: 'var(--font-mono)' }}>YOUR_API_KEY</code> with your key.
          </p>
          <CodeBlock id="curl" code={curlSnippet} lang="bash" onCopy={copy} />
          <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            You'll get back a ticket ID like <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--primary)' }}>"ticket_id": "SP-42"</code> — the AI pipeline starts immediately in the background.
          </p>
        </Section>

        {/* 3. Python */}
        <Section
          id="python"
          icon={<Code size={15} color="var(--primary)" />}
          title="Python Integration"
          subtitle="Django, Flask, FastAPI, scripts"
        >
          <CodeBlock id="python" code={pythonSnippet} lang="python" onCopy={copy} />
        </Section>

        {/* 4. JavaScript / Node.js */}
        <Section
          id="js"
          icon={<Globe size={15} color="var(--primary)" />}
          title="JavaScript / Node.js Integration"
          subtitle="Express, Next.js, any backend"
        >
          <div
            style={{
              background: 'rgba(217, 119, 6, 0.06)',
              border: '1px solid rgba(217, 119, 6, 0.2)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.55rem 0.85rem',
              fontSize: '0.78rem',
              color: 'var(--text-muted)',
              marginBottom: '0.5rem',
            }}
          >
            ⚠️ Always call this from your <strong>server-side backend</strong>. Never expose your API key in client-side (browser) JavaScript.
          </div>
          <CodeBlock id="js" code={jsSnippet} lang="javascript" onCopy={copy} />
        </Section>

        {/* 5. Error handler pattern */}
        <Section
          id="errorhandler"
          icon={<Zap size={15} color="var(--primary)" />}
          title="Automatic Error Reporting Pattern"
          subtitle="File tickets from exception handlers"
        >
          <p style={{ fontSize: '0.825rem', color: 'var(--text-muted)', marginBottom: '0.6rem', lineHeight: 1.6 }}>
            The most powerful integration: catch unhandled exceptions in your app and automatically create a SupportPilot ticket with the full error context.
          </p>
          <CodeBlock id="webhook" code={webhookSnippet} lang="python" onCopy={copy} />
        </Section>

        {/* 6. API Reference */}
        <Section
          id="apiref"
          icon={<BookOpen size={15} color="var(--primary)" />}
          title="API Reference"
          subtitle="Full request / response schema"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            {/* Request schema */}
            <div>
              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.4rem' }}>
                POST /api/v1/tickets — Request Body
              </div>
              <div className="table-container">
                <table className="data-table" style={{ fontSize: '0.78rem' }}>
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th>Type</th>
                      <th>Required</th>
                      <th>Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['title', 'string', '✅ Yes', 'Short one-line summary of the issue'],
                      ['description', 'string', '✅ Yes', 'Full description with steps to reproduce'],
                      ['application', 'string', '✅ Yes', `Your app name — must match "${appName}" to route to this repo`],
                      ['severity', 'string', '❌ No', 'low | medium | high | critical (default: medium)'],
                      ['reporter_email', 'string', '❌ No', 'End-user email for escalation routing'],
                      ['external_ticket_id', 'string', '❌ No', 'Your own ticket/issue ID for idempotency'],
                    ].map(([field, type, req, desc]) => (
                      <tr key={String(field)}>
                        <td><code style={{ fontFamily: 'var(--font-mono)', color: 'var(--primary)' }}>{field}</code></td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{type}</td>
                        <td>{req}</td>
                        <td style={{ color: 'var(--text-muted)' }}>{desc}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Response schema */}
            <div>
              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.4rem' }}>
                Response — 201 Created
              </div>
              <CodeBlock
                id="response"
                code={`{
  "ticket_id": "SP-42",          // stable public ticket identifier
  "status": "RECEIVED",          // initial status; AI analysis starts in background
  "application": "${appName}",
  "title": "User cannot log in after password reset",
  "description": "...",
  "created_at": "2024-01-15T10:30:00Z"
}`}
                lang="json"
                onCopy={copy}
              />
            </div>

            {/* Idempotency */}
            <div
              style={{
                background: 'var(--bg-subtle)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.75rem 1rem',
                fontSize: '0.8rem',
              }}
            >
              <strong>Idempotency:</strong>{' '}
              <span style={{ color: 'var(--text-muted)' }}>
                Pass <code style={{ fontFamily: 'var(--font-mono)' }}>Idempotency-Key: your-unique-id</code> header or include{' '}
                <code style={{ fontFamily: 'var(--font-mono)' }}>external_ticket_id</code> in the body to safely retry without creating duplicate tickets.
              </span>
            </div>
          </div>
        </Section>
      </div>

      {/* Wizard */}
      <ConnectRepoWizard
        isOpen={isWizardOpen}
        onClose={() => setIsWizardOpen(false)}
        onSuccess={() => fetchRepos()}
      />
    </div>
  );
};
