import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import type { IssueItem } from '../types/api';
import { DEMO_ISSUES } from '../data/demoFixtures';
import { SeverityBadge } from '../components/SeverityBadge';
import { StatusBadge } from '../components/StatusBadge';
import { ListFilter, RefreshCw, AlertCircle, PlusCircle, ExternalLink, ArrowRight, Search } from 'lucide-react';

export const TicketsPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { demoMode, activeRepoId } = useWorkspace();
  const [issues, setIssues] = useState<IssueItem[]>([]);
  const [, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [stateFilter, setStateFilter] = useState<string>('ALL');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [searchInput, setSearchInput] = useState<string>(searchParams.get('search') || '');

  const fetchIssues = async () => {
    setLoading(true);
    setError(null);

    if (demoMode) {
      setTimeout(() => {
        let filtered = DEMO_ISSUES;
        if (stateFilter !== 'ALL') {
          filtered = filtered.filter((i) => i.state.toUpperCase() === stateFilter.toUpperCase());
        }
        if (severityFilter !== 'ALL') {
          filtered = filtered.filter((i) => i.severity.toUpperCase() === severityFilter.toUpperCase());
        }
        if (searchInput.trim()) {
          const s = searchInput.toLowerCase();
          filtered = filtered.filter(
            (i) => i.title.toLowerCase().includes(s) || i.repository_name.toLowerCase().includes(s)
          );
        }
        setIssues(filtered);
        setTotalCount(filtered.length);
        setLoading(false);
      }, 200);
      return;
    }

    try {
      const repoId = activeRepoId === 'all' ? undefined : activeRepoId;
      const st = stateFilter === 'ALL' ? undefined : stateFilter.toLowerCase();
      const res = await api.getIssues(50, 0, repoId, st, searchInput.trim() || undefined);
      
      let items = res.issues;
      if (severityFilter !== 'ALL') {
        items = items.filter((i) => i.severity.toUpperCase() === severityFilter.toUpperCase());
      }
      setIssues(items);
      setTotalCount(res.total);
    } catch (err: any) {
      setError(err.message || 'Failed to load issues from backend.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIssues();
  }, [demoMode, activeRepoId, stateFilter, severityFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchIssues();
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Support Issues</h1>
          <p className="page-subtitle">
            Ingested GitHub issues and automated support triage history across your repositories.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-secondary" onClick={fetchIssues} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spinner' : ''} /> Refresh
          </button>
          <button className="btn btn-primary" onClick={() => navigate('/analyze')}>
            <PlusCircle size={14} /> Analyze Issue
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <div>{error}</div>
        </div>
      )}

      {/* Filter & Search Bar */}
      <div className="panel" style={{ padding: '0.85rem 1.1rem', marginBottom: '1.25rem' }}>
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', flexWrap: 'wrap' }}>
          <div className="search-bar" style={{ width: '260px' }}>
            <Search size={14} color="var(--text-dim)" />
            <input
              type="text"
              className="search-input"
              placeholder="Filter by issue title..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            <ListFilter size={14} /> State:
            <select
              className="form-select"
              style={{ width: 'auto', padding: '0.3rem 0.65rem', fontSize: '0.8rem' }}
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
            >
              <option value="ALL">All States</option>
              <option value="OPEN">Open</option>
              <option value="CLOSED">Closed</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Severity:
            <select
              className="form-select"
              style={{ width: 'auto', padding: '0.3rem 0.65rem', fontSize: '0.8rem' }}
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
            >
              <option value="ALL">All Severities</option>
              <option value="HIGH">High / Critical</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>

          <button type="submit" className="btn btn-secondary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.775rem' }}>
            Apply Filter
          </button>
        </form>
      </div>

      {/* Issues Table Panel */}
      <div className="panel">
        <div className="panel-header">
          <h3 className="panel-title">Ingested Issues ({issues.length})</h3>
        </div>

        {loading ? (
          <div className="empty-state">Loading issues...</div>
        ) : issues.length === 0 ? (
          <div className="empty-state">
            <p className="empty-state-title">No issues found matching criteria</p>
            <p className="empty-state-subtitle">
              Try adjusting your filters or connect a repository to ingest GitHub issue history.
            </p>
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Issue #</th>
                  <th>Title</th>
                  <th>Repository</th>
                  <th>State</th>
                  <th>Severity</th>
                  <th>AI Triage Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {issues.map((iss) => (
                  <tr
                    key={iss.id}
                    className="clickable-row"
                    onClick={() => {
                      if (iss.latest_run_id) {
                        navigate(`/runs/${iss.latest_run_id}`);
                      }
                    }}
                  >
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      #{iss.issue_number}
                    </td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{iss.title}</div>
                      <div style={{ fontSize: '0.725rem', color: 'var(--text-dim)', marginTop: '0.1rem' }}>
                        {iss.body_snippet}
                      </div>
                    </td>
                    <td>{iss.repository_name}</td>
                    <td>
                      <span className={`badge ${iss.state === 'OPEN' ? 'badge-success' : 'badge-neutral'}`}>
                        {iss.state}
                      </span>
                    </td>
                    <td>
                      <SeverityBadge severity={iss.severity} />
                    </td>
                    <td>
                      {iss.latest_decision ? (
                        <StatusBadge decision={iss.latest_decision} />
                      ) : (
                        <span className="badge badge-neutral">Not Analyzed</span>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.4rem' }}>
                        {iss.html_url && (
                          <a
                            href={iss.html_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn btn-secondary"
                            style={{ padding: '0.2rem 0.45rem', fontSize: '0.725rem' }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <ExternalLink size={12} />
                          </a>
                        )}
                        {iss.latest_run_id ? (
                          <button
                            className="btn btn-primary"
                            style={{ padding: '0.2rem 0.5rem', fontSize: '0.725rem' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(`/runs/${iss.latest_run_id}`);
                            }}
                          >
                            Audit Run <ArrowRight size={11} />
                          </button>
                        ) : (
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '0.2rem 0.5rem', fontSize: '0.725rem' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate('/analyze');
                            }}
                          >
                            Analyze
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
