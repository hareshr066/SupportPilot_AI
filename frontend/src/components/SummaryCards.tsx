import React from 'react';
import type { DashboardSummary } from '../types/api';
import { Ticket, Clock, CheckCircle2, AlertTriangle, Flame, Zap } from 'lucide-react';

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
            <div className="kpi-value">...</div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid-kpi">
      <div className="kpi-card">
        <div className="kpi-header">
          <span>Total Tickets</span>
          <Ticket size={16} color="var(--primary)" />
        </div>
        <div className="kpi-value">{summary?.total_tickets ?? '—'}</div>
        <div className="kpi-subtext">Ingested & triage history</div>
      </div>

      <div className="kpi-card">
        <div className="kpi-header">
          <span>Analyzed Today</span>
          <Clock size={16} color="var(--purple)" />
        </div>
        <div className="kpi-value">{summary?.analyzed_today ?? '—'}</div>
        <div className="kpi-subtext">Active 24h volume</div>
      </div>

      <div className="kpi-card">
        <div className="kpi-header">
          <span>Auto-Resolutions</span>
          <CheckCircle2 size={16} color="var(--success)" />
        </div>
        <div className="kpi-value" style={{ color: 'var(--success)' }}>
          {summary?.auto_resolution_recommendations ?? '—'}
        </div>
        <div className="kpi-subtext">Safe recommendation rate</div>
      </div>

      <div className="kpi-card">
        <div className="kpi-header">
          <span>Human Escalations</span>
          <AlertTriangle size={16} color="var(--warning)" />
        </div>
        <div className="kpi-value" style={{ color: 'var(--warning)' }}>
          {summary?.human_escalations ?? '—'}
        </div>
        <div className="kpi-subtext">Requires team investigation</div>
      </div>

      <div className="kpi-card">
        <div className="kpi-header">
          <span>High Severity</span>
          <Flame size={16} color="var(--danger)" />
        </div>
        <div className="kpi-value" style={{ color: 'var(--danger)' }}>
          {summary?.high_severity_tickets ?? '—'}
        </div>
        <div className="kpi-subtext">Priority technical issues</div>
      </div>

      <div className="kpi-card">
        <div className="kpi-header">
          <span>Avg Latency</span>
          <Zap size={16} color="var(--primary)" />
        </div>
        <div className="kpi-value">
          {summary?.average_pipeline_latency_ms
            ? `${summary.average_pipeline_latency_ms} ms`
            : '0 ms'}
        </div>
        <div className="kpi-subtext">End-to-end pipeline execution</div>
      </div>
    </div>
  );
};
