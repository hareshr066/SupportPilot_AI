import React from 'react';
import { NavLink } from 'react-router-dom';
import { useWorkspace } from '../context/WorkspaceContext';
import {
  LayoutDashboard,
  PlusCircle,
  FolderGit2,
  ListFilter,
  BarChart3,
  Settings,
  Terminal,
  FileCode,
  Sparkles
} from 'lucide-react';

export const Sidebar: React.FC = () => {
  const { demoMode } = useWorkspace();

  return (
    <aside className="app-sidebar">
      <div>
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <div className="sidebar-icon">
              <Terminal size={16} />
            </div>
            <div>
              <div className="sidebar-title">SupportPilot</div>
              <div className="sidebar-subtitle">AI Support Infrastructure</div>
            </div>
          </div>
          {demoMode && (
            <div style={{ marginTop: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.7rem', color: '#D97706', fontWeight: 600, background: '#FFFBEB', padding: '0.15rem 0.45rem', borderRadius: '4px', border: '1px solid #FDE68A' }}>
              <Sparkles size={11} />
              <span>Demo Mode Active</span>
            </div>
          )}
        </div>

        <nav className="sidebar-nav">
          <NavLink
            to="/"
            end
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <LayoutDashboard size={15} />
            <span>Overview</span>
          </NavLink>

          <NavLink
            to="/analyze"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <PlusCircle size={15} />
            <span>Analyze Issue</span>
          </NavLink>

          <NavLink
            to="/tickets"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <ListFilter size={15} />
            <span>Issues</span>
          </NavLink>

          <NavLink
            to="/repositories"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <FolderGit2 size={15} />
            <span>Repositories</span>
          </NavLink>

          <NavLink
            to="/runs"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <FileCode size={15} />
            <span>AI Runs</span>
          </NavLink>

          <NavLink
            to="/evaluation"
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <BarChart3 size={15} />
            <span>Evaluation</span>
          </NavLink>
        </nav>
      </div>

      <div className="sidebar-footer">
        <NavLink
          to="/settings"
          className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
        >
          <Settings size={15} />
          <span>Settings</span>
        </NavLink>
      </div>
    </aside>
  );
};
