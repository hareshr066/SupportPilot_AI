import React from 'react';
import type { EvidenceReferenceItem } from '../types/api';
import { ExternalLink, Layers } from 'lucide-react';

interface Props {
  retrievedCases: EvidenceReferenceItem[];
}

export const EvidenceCard: React.FC<Props> = ({ retrievedCases }) => {
  if (!retrievedCases || retrievedCases.length === 0) {
    return (
      <div className="panel">
        <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
          <Layers size={15} color="var(--primary)" />
          <span>Retrieved Evidence (0)</span>
        </div>
        <div className="empty-state" style={{ padding: '1.25rem' }}>
          <p style={{ fontSize: '0.785rem' }}>No matching historical resolved cases retrieved for this ticket query.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            <Layers size={15} color="var(--primary)" />
            <span>Retrieved Historical Evidence ({retrievedCases.length})</span>
          </div>
          <div style={{ fontSize: '0.725rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
            Hybrid dense pgvector + Okapi BM25 technical token search (RRF k=60)
          </div>
        </div>
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: '85px' }}>Issue #</th>
              <th style={{ minWidth: '180px' }}>Title</th>
              <th>Sim</th>
              <th>BM25</th>
              <th>RRF</th>
              <th style={{ minWidth: '240px' }}>Evidence Snippet</th>
              <th style={{ textAlign: 'right' }}>Source</th>
            </tr>
          </thead>
          <tbody>
            {retrievedCases.map((ev, i) => (
              <tr key={i}>
                <td>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 700,
                      color: 'var(--primary)',
                      fontSize: '0.785rem',
                    }}
                  >
                    #{ev.issue_number || ev.issue_id}
                  </span>
                </td>
                <td style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '0.815rem' }}>
                  {ev.title}
                </td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  {(ev.dense_similarity || 0).toFixed(2)}
                </td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  {(ev.bm25_score || 0).toFixed(2)}
                </td>
                <td>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 700,
                      color: 'var(--primary)',
                      fontSize: '0.75rem',
                    }}
                  >
                    {(ev.rrf_score || 0).toFixed(3)}
                  </span>
                </td>
                <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>
                  {ev.evidence_text_snippet}
                </td>
                <td style={{ textAlign: 'right' }}>
                  {ev.html_url ? (
                    <a
                      href={ev.html_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-secondary"
                      style={{ padding: '0.2rem 0.5rem', fontSize: '0.725rem', gap: '0.25rem' }}
                    >
                      <span>GitHub</span>
                      <ExternalLink size={10} />
                    </a>
                  ) : (
                    <span style={{ color: 'var(--text-dim)', fontSize: '0.725rem', fontFamily: 'var(--font-mono)' }}>
                      Local
                    </span>
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
