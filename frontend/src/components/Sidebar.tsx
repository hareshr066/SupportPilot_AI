import React from 'react';
import { NavLink } from 'react-router-dom';
import { useWorkspace } from '../context/WorkspaceContext';
import {
  LayoutDashboard,
  FolderGit2,
  ListFilter,
  BarChart3,
  Settings,
  Terminal,
  FileCode,
  ShieldAlert,
  Activity,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';

export const Sidebar: React.FC = () => {
  const { demoMode, setDemoMode, systemReady } = useWorkspace();

  return (
    <aside className="app-sidebar">
      <div>
        {/* Brand Header */}
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <div className="sidebar-icon">
              <Terminal size={18} strokeWidth={2.5} />
            </div>
            <div>
              <div className="sidebar-title">SupportPilot</div>
              <div className="sidebar-subtitle">AI Operations Platform</div>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="sidebar-nav">
          <NavLink
            to="/"
            end
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <LayoutDashboard size={17} />
            <span>Overview</span>
          </NavLink>

          <NavLink
            to="/tickets"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <ListFilter size={17} />
            <span>Tickets</span>
          </NavLink>

          <NavLink
            to="/runs"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <FileCode size={17} />
            <span>Investigations</span>
          </NavLink>

          <NavLink
            to="/escalations"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <ShieldAlert size={17} />
            <span>Escalations</span>
          </NavLink>

          <NavLink
            to="/repositories"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <FolderGit2 size={17} />
            <span>Repositories</span>
          </NavLink>

          <NavLink
            to="/evaluation"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <BarChart3 size={17} />
            <span>Evaluation</span>
          </NavLink>
        </nav>
      </div>

      {/* Footer */}
      <div className="sidebar-footer">
        <NavLink
          to="/settings"
          className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          style={{ marginBottom: '0.25rem' }}
        >
          <Settings size={17} />
          <span>Settings</span>
        </NavLink>

        {/* Mode Toggle */}
        <div
          style={{
            background: 'rgba(255, 255, 255, 0.95)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-pill)',
            padding: '0.45rem 0.85rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: 'var(--shadow-xs)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: demoMode ? 'var(--warning)' : 'var(--primary)',
                boxShadow: demoMode
                  ? '0 0 8px rgba(217, 119, 6, 0.5)'
                  : '0 0 8px rgba(37, 99, 235, 0.5)',
              }}
            />
            <span
              style={{
                fontSize: '0.8rem',
                fontWeight: 700,
                fontFamily: 'var(--font-mono)',
                color: demoMode ? 'var(--warning)' : 'var(--primary)',
              }}
            >
              {demoMode ? 'DEMO' : 'LIVE'}
            </span>
          </div>
          <button
            onClick={() => setDemoMode(!demoMode)}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              fontSize: '0.775rem',
              fontWeight: 600,
              cursor: 'pointer',
              textDecoration: 'underline',
              padding: 0,
            }}
          >
            {demoMode ? 'Go Live' : 'Demo'}
          </button>
        </div>

        {/* Connection Status */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '0.8rem',
            color: 'var(--text-muted)',
            padding: '0.15rem 0.35rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Activity size={14} color={systemReady ? 'var(--success)' : 'var(--warning)'} />
            <span style={{ fontWeight: 600 }}>API Service</span>
          </div>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.3rem',
              fontWeight: 700,
              color: systemReady ? 'var(--success)' : 'var(--warning)',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.75rem',
            }}
          >
            {systemReady ? (
              <>
                <CheckCircle2 size={12} /> READY
              </>
            ) : (
              <>
                <AlertCircle size={12} /> DEGRADED
              </>
            )}
          </span>
        </div>
      </div>
    </aside>
  );
};
