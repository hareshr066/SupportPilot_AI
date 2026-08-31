import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWorkspace } from '../context/WorkspaceContext';
import { Search, Activity, GitBranch, ShieldCheck } from 'lucide-react';

export const TopBar: React.FC = () => {
  const navigate = useNavigate();
  const { repositories, activeRepoId, setActiveRepoId, systemReady, demoMode } = useWorkspace();
  const [searchQuery, setSearchQuery] = useState<string>('');

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    if (searchQuery.trim().startsWith('run_')) {
      navigate(`/runs/${searchQuery.trim()}`);
    } else {
      navigate(`/tickets?search=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  return (
    <header className="topbar">
      <div className="topbar-left">
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
            <option value="all">All Connected Repositories</option>
            {repositories.map((r) => (
              <option key={r.id} value={String(r.id)}>
                {r.full_name || `${r.owner}/${r.name}`}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="topbar-right">
        <form onSubmit={handleSearchSubmit} className="search-bar">
          <Search size={14} color="var(--text-dim)" />
          <input
            type="text"
            className="search-input"
            placeholder="Search issues, runs or titles..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </form>

        <div className={`system-status ${systemReady ? '' : 'not-ready'}`}>
          <div className="system-status-dot" />
          <Activity size={12} />
          <span>{systemReady ? 'API Operational' : 'API Degraded'}</span>
        </div>

        {demoMode && (
          <div className="badge badge-warning" style={{ gap: '0.2rem' }}>
            <ShieldCheck size={12} />
            <span>Demo Mode</span>
          </div>
        )}
      </div>
    </header>
  );
};
