import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useWorkspace } from '../context/WorkspaceContext';
import { Search, Activity, GitBranch, Plus } from 'lucide-react';

export const TopBar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { repositories, activeRepoId, setActiveRepoId, systemReady, demoMode } = useWorkspace();
  const [searchQuery, setSearchQuery] = useState<string>('');

  const getPageInfo = (): { title: string; subtitle?: string } => {
    const path = location.pathname;
    if (path === '/' || path === '/dashboard') {
      return { title: 'Overview' };
    }
    if (path.startsWith('/analyze') || path === '/tickets/new') {
      return { title: 'New Investigation' };
    }
    if (path.startsWith('/tickets')) {
      return { title: 'Tickets' };
    }
    if (path.startsWith('/runs/')) {
      return { title: 'Investigation Details' };
    }
    if (path === '/runs') {
      return { title: 'Investigations' };
    }
    if (path.startsWith('/escalations')) {
      return { title: 'Escalations' };
    }
    if (path.startsWith('/repositories')) {
      return { title: 'Repositories' };
    }
    if (path.startsWith('/evaluation')) {
      return { title: 'Evaluation' };
    }
    if (path.startsWith('/settings')) {
      return { title: 'Settings' };
    }
    return { title: 'SupportPilot' };
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    if (searchQuery.trim().startsWith('run_') || searchQuery.trim().startsWith('pipeline_')) {
      navigate(`/runs/${searchQuery.trim()}`);
    } else {
      navigate(`/tickets?search=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  const pageInfo = getPageInfo();
  const isAnalyzePage = location.pathname.startsWith('/analyze');

  return (
    <header className="topbar">
      <div className="topbar-left">
        <span style={{ fontWeight: 800, fontSize: '1.05rem', color: 'var(--text-main)', letterSpacing: '-0.02em' }}>
          {pageInfo.title}
        </span>
      </div>

      <div className="topbar-right">
        {/* Global Search */}
        <form onSubmit={handleSearchSubmit} className="search-bar">
          <Search size={14} color="var(--text-dim)" />
          <input
            type="text"
            className="search-input"
            placeholder="Search tickets, runs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </form>

        {/* Repository Scope */}
        <div className="repo-selector">
          <GitBranch size={14} color="var(--text-muted)" />
          <select
            className="repo-select-input"
            value={activeRepoId === 'all' ? 'all' : String(activeRepoId)}
            onChange={(e) => {
              const val = e.target.value;
              setActiveRepoId(val === 'all' ? 'all' : Number(val));
            }}
          >
            <option value="all">All Repos</option>
            {repositories.map((r) => (
              <option key={r.id} value={String(r.id)}>
                {r.full_name || `${r.owner}/${r.name}`}
              </option>
            ))}
          </select>
        </div>

        {/* Mode Badge */}
        {demoMode ? (
          <span className="badge badge-warning">DEMO</span>
        ) : (
          <span className="badge badge-primary">LIVE</span>
        )}

        {/* System Status */}
        <div className={`system-status ${systemReady ? '' : 'not-ready'}`}>
          <div className="system-status-dot" />
          <Activity size={12} />
          <span>{systemReady ? 'Healthy' : 'Degraded'}</span>
        </div>

        {/* Quick Action */}
        {!isAnalyzePage && (
          <button
            className="btn btn-primary"
            onClick={() => navigate('/analyze')}
            style={{ padding: '0.45rem 0.85rem' }}
          >
            <Plus size={14} />
            <span>Investigate</span>
          </button>
        )}
      </div>
    </header>
  );
};
