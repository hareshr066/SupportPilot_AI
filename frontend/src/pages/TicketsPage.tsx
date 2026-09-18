import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import type { IssueItem } from '../types/api';
import { DEMO_ISSUES } from '../data/demoFixtures';
import { SeverityBadge } from '../components/SeverityBadge';
import { StatusBadge } from '../components/StatusBadge';
import {
  RefreshCw,
  AlertCircle,
  Plus,
  ArrowRight,
  Search,
  ExternalLink,
  ListFilter
} from 'lucide-react';

export const TicketsPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { demoMode, activeRepoId, repositories, setActiveRepoId } = useWorkspace();
  const [issues, setIssues] = useState<IssueItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [stateFilter, setStateFilter] = useState<string>('ALL');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [decisionFilter, setDecisionFilter] = useState<string>('ALL');
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
        if (decisionFilter !== 'ALL') {
          filtered = filtered.filter((i) => {
            if (decisionFilter === 'AUTO_RESOLVE') {
              return i.latest_decision?.includes('AUTO');
            }
            if (decisionFilter === 'ESCALATION') {
              return i.latest_decision?.includes('ESCALAT') || i.latest_decision?.includes('HUMAN');
            }
            return true;
          });
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
      if (decisionFilter !== 'ALL') {
        items = items.filter((i) => {
          if (decisionFilter === 'AUTO_RESOLVE') {
            return i.latest_decision?.includes('AUTO');
          }
          if (decisionFilter === 'ESCALATION') {
            return i.latest_decision?.includes('ESCALAT') || i.latest_decision?.includes('HUMAN');
          }
          return true;
        });
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
  }, [demoMode, activeRepoId, stateFilter, severityFilter, decisionFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchIssues();
  };

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h1 className="page-title">
              <ListFilter size={22} color="var(--primary)" />
              Tickets
            </h1>
            <span className="badge badge-neutral">{totalCount} total</span>
          </div>
          <p className="page-subtitle">
            Technical support issues and repository bug reports awaiting investigation.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.6rem' }}>
          <button className="btn btn-secondary" onClick={fetchIssues} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spinner' : ''} />
            <span>Refresh</span>
          </button>
          <button className="btn btn-primary" onClick={() => navigate('/analyze')}>
            <Plus size={14} />
            <span>Run Investigation</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <div>{error}</div>
        </div>
      )}

      {/* Filter Control Bar */}
      <div
        className="panel"
        style={{
          padding: '0.75rem 1rem',
          marginBottom: '1rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          flexWrap: 'wrap',
        }}
      >
        {/* Search */}
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', alignItems: 'center', flex: '1 1 200px' }}>
          <div className="search-bar" style={{ width: '100%' }}>
            <Search size={14} color="var(--text-dim)" />
            <input
              type="text"
              className="search-input"
              placeholder="Search title, issue number..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>
        </form>

        {/* State Filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>State:</span>
          <select
            className="form-select"
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            style={{ padding: '0.35rem 0.6rem', fontSize: '0.825rem', width: 'auto' }}
          >
            <option value="ALL">All States</option>
            <option value="OPEN">Open</option>
            <option value="CLOSED">Closed</option>
          </select>
        </div>

        {/* Severity Filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Severity:</span>
          <select
            className="form-select"
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            style={{ padding: '0.35rem 0.6rem', fontSize: '0.825rem', width: 'auto' }}
          >
            <option value="ALL">All Severities</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
        </div>

        {/* Triage Status Filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Triage:</span>
          <select
            className="form-select"
            value={decisionFilter}
            onChange={(e) => setDecisionFilter(e.target.value)}
            style={{ padding: '0.35rem 0.6rem', fontSize: '0.825rem', width: 'auto' }}
          >
            <option value="ALL">All Decisions</option>
            <option value="AUTO_RESOLVE">Auto-Resolved</option>
            <option value="ESCALATION">Human Escalation</option>
          </select>
        </div>

        {/* Repository Filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Repository:</span>
          <select
            className="form-select"
            value={activeRepoId === 'all' ? 'all' : String(activeRepoId)}
            onChange={(e) => {
              const val = e.target.value;
              setActiveRepoId(val === 'all' ? 'all' : Number(val));
            }}
            style={{ padding: '0.35rem 0.6rem', fontSize: '0.825rem', width: 'auto' }}
          >
            <option value="all">All Repositories</option>
            {repositories.map((r) => (
              <option key={r.id} value={String(r.id)}>
                {r.full_name || `${r.owner}/${r.name}`}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Tickets Table */}
      <div className="panel">
        {loading ? (
          <div className="empty-state" style={{ padding: '2.5rem' }}>
            <div className="spinner" style={{ margin: '0 auto 0.5rem auto' }} />
            <p style={{ fontSize: '0.85rem' }}>Loading tickets...</p>
          </div>
        ) : issues.length === 0 ? (
          <div className="empty-state" style={{ padding: '2rem' }}>
            <p className="empty-state-title">No tickets match your filters</p>
            <p className="empty-state-subtitle">Adjust search terms or state/severity filters.</p>
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: '80px' }}>ID</th>
                  <th>Title</th>
                  <th>Repository</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Created</th>
                  <th style={{ textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {issues.map((issue) => (
                  <tr
                    key={issue.id}
                    className="clickable-row"
                    onClick={() => {
                      if (issue.latest_run_id) {
                        navigate(`/runs/${issue.latest_run_id}`);
                      } else {
                        navigate(
                          `/analyze?repo=${issue.repository_id}&title=${encodeURIComponent(
                            issue.title
                          )}&issue=${issue.issue_number || issue.id}`
                        );
                      }
                    }}
                  >
                    <td>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 700,
                          color: 'var(--primary)',
                          fontSize: '0.825rem',
                        }}
                      >
                        #{issue.issue_number || issue.id}
                      </span>
                    </td>
                    <td>
                      <div
                        style={{
                          fontWeight: 600,
                          color: 'var(--text-main)',
                          maxWidth: '320px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          fontSize: '0.875rem',
                        }}
                        title={issue.title}
                      >
                        {issue.title}
                      </div>
                      {issue.html_url && (
                        <a
                          href={issue.html_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            fontSize: '0.75rem',
                            color: 'var(--text-dim)',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.2rem',
                            marginTop: '0.1rem',
                          }}
                        >
                          <span>GitHub</span>
                          <ExternalLink size={9} />
                        </a>
                      )}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.825rem', color: 'var(--text-secondary)' }}>
                      {issue.repository_name}
                    </td>
                    <td>
                      <SeverityBadge severity={issue.severity} />
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          issue.state.toLowerCase() === 'open' ? 'badge-primary' : 'badge-neutral'
                        }`}
                        style={{ marginRight: '0.35rem' }}
                      >
                        {issue.state}
                      </span>
                      {issue.latest_decision && (
                        <StatusBadge decision={issue.latest_decision} />
                      )}
                    </td>
                    <td>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 700,
                          fontSize: '0.875rem',
                          color: ((issue as any).calibrated_confidence ?? 0.88) >= 0.85 ? 'var(--success)' : '#FBBF24',
                        }}
                      >
                        {(((issue as any).calibrated_confidence ?? 0.88) * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                      {issue.created_at ? new Date(issue.created_at).toLocaleDateString() : 'Recent'}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '0.3rem 0.65rem', fontSize: '0.775rem' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (issue.latest_run_id) {
                            navigate(`/runs/${issue.latest_run_id}`);
                          } else {
                            navigate(
                              `/analyze?repo=${issue.repository_id}&title=${encodeURIComponent(
                                issue.title
                              )}&issue=${issue.issue_number || issue.id}`
                            );
                          }
                        }}
                      >
                        <span>{issue.latest_run_id ? 'View Run' : 'Investigate'}</span>
                        <ArrowRight size={10} />
                      </button>
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
