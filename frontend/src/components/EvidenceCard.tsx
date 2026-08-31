import React from 'react';
import type { EvidenceReferenceItem } from '../types/api';
import { ExternalLink, Database } from 'lucide-react';

interface Props {
  retrievedCases: EvidenceReferenceItem[];
}

export const EvidenceCard: React.FC<Props> = ({ retrievedCases }) => {
  if (!retrievedCases || retrievedCases.length === 0) {
    return (
      <div className="panel">
        <div className="panel-title">Retrieved Historical Evidence Cases</div>
        <div className="empty-state" style={{ padding: '1.5rem' }}>
          <Database size={24} className="empty-state-icon" />
          <p style={{ fontSize: '0.85rem' }}>No matching historical cases retrieved for this query.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">Retrieved Historical Evidence Cases ({retrievedCases.length})</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Hybrid dense + BM25 reciprocal rank fusion (RRF) retrieval matches from indexed repository issues
          </div>
        </div>
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Issue #</th>
              <th>Title</th>
              <th>Dense Sim</th>
              <th>BM25</th>
              <th>RRF Score</th>
              <th>Evidence Snippet</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {retrievedCases.map((ev, i) => (
              <tr key={i}>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                  #{ev.issue_number || ev.issue_id}
                </td>
                <td style={{ fontWeight: 500 }}>{ev.title}</td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                  {(ev.dense_similarity || 0).toFixed(3)}
                </td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                  {(ev.bm25_score || 0).toFixed(2)}
                </td>
                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--primary)' }}>
                  {(ev.rrf_score || 0).toFixed(3)}
                </td>
                <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)', maxWidth: '300px' }}>
                  {ev.evidence_text_snippet}
                </td>
                <td>
                  {ev.html_url ? (
                    <a
                      href={ev.html_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-secondary"
                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                    >
                      GitHub <ExternalLink size={12} />
                    </a>
                  ) : (
                    <span style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>Indexed DB</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
