import React from 'react';
import type { DashboardSummary } from '../types/api';
import { Ticket, Zap, CheckCircle2, ShieldAlert, Flame, Clock } from 'lucide-react';

interface Props {
  summary: DashboardSummary | null;
  loading: boolean;
}

export const SummaryCards: React.FC<Props> = ({ summary, loading }) => {
  if (loading) {
    return (
      <div className="grid-kpi">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className="kpi-card" style={{ opacity: 0.6 }}>
            <div className="kpi-header">Loading metric...</div>
            <div className="kpi-value" style={{ color: 'var(--text-dim)' }}>
              ...
            </div>
            <div className="kpi-subtext">Fetching telemetry</div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid-kpi">
      {/* 1. Open Tickets */}
      <div className="kpi-card">
        <div className="kpi-header">
          <span>Open Tickets</span>
          <Ticket size={14} color="var(--primary)" />
        </div>
        <div className="kpi-value">{summary?.total_tickets ?? '0'}</div>
        <div className="kpi-subtext">Ingested issue repository</div>
      </div>

      {/* 2. Investigations */}
      <div className="kpi-card">
        <div className="kpi-header">
          <span>Investigations (24h)</span>
          <Clock size={14} color="var(--cyan)" />
        </div>
        <div className="kpi-value">{summary?.analyzed_today ?? '0'}</div>
        <div className="kpi-subtext">Automated triage runs</div>
      </div>

      {/* 3. Auto-Resolved */}
      <div className="kpi-card">
        <div className="kpi-header">
          <span style={{ color: 'var(--success)' }}>Auto-Resolved</span>
          <CheckCircle2 size={14} color="var(--success)" />
        </div>
        <div className="kpi-value" style={{ color: 'var(--success)' }}>
          {summary?.auto_resolution_recommendations ?? '0'}
        </div>
        <div className="kpi-subtext">Verified &gt;= 85% confidence</div>
      </div>

      {/* 4. Human Review */}
      <div className="kpi-card">
        <div className="kpi-header">
          <span style={{ color: 'var(--warning)' }}>Needs Review</span>
          <ShieldAlert size={14} color="var(--warning)" />
        </div>
        <div className="kpi-value" style={{ color: 'var(--warning)' }}>
          {summary?.human_escalations ?? '0'}
        </div>
        <div className="kpi-subtext">Confidence &lt; 85% or gaps</div>
      </div>

      {/* 5. High Severity */}
      <div className="kpi-card">
        <div className="kpi-header">
          <span style={{ color: 'var(--danger)' }}>High Severity</span>
          <Flame size={14} color="var(--danger)" />
        </div>
        <div className="kpi-value" style={{ color: 'var(--danger)' }}>
          {summary?.high_severity_tickets ?? '0'}
        </div>
        <div className="kpi-subtext">Critical priority issues</div>
      </div>

      {/* 6. Avg Latency */}
      <div className="kpi-card">
        <div className="kpi-header">
          <span>Avg Latency</span>
          <Zap size={14} color="var(--purple)" />
        </div>
        <div className="kpi-value">
          {summary?.average_pipeline_latency_ms !== undefined && summary.average_pipeline_latency_ms !== null
            ? `${summary.average_pipeline_latency_ms} ms`
            : '0 ms'}
        </div>
        <div className="kpi-subtext">8-stage LangGraph pipeline</div>
      </div>
    </div>
  );
};
