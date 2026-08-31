import React from 'react';
import type { PipelineStageRun } from '../types/api';
import { CheckCircle2, Clock, XCircle, MinusCircle } from 'lucide-react';

interface Props {
  stages: PipelineStageRun[];
  isCompleted?: boolean;
}

const EXPECTED_STAGES = [
  { name: 'initialize_ticket', label: 'Ticket Initialization' },
  { name: 'classify_severity', label: 'Severity Classification' },
  { name: 'detect_duplicate', label: 'Duplicate Detection' },
  { name: 'discover_root_cause', label: 'Root Cause Correlation' },
  { name: 'retrieve_cases', label: 'Hybrid Retrieval' },
  { name: 'generate_resolution', label: 'Grounded Resolution' },
  { name: 'verify_claims', label: 'Claim Verification' },
  { name: 'calculate_confidence', label: 'Confidence Calibration' },
  { name: 'route_ticket', label: 'Deterministic Routing' },
  { name: 'make_decision', label: 'Final Decision' },
];

export const PipelineStageProgress: React.FC<Props> = ({ stages }) => {
  const stageMap = new Map<string, PipelineStageRun>();
  stages.forEach((s) => stageMap.set(s.stage, s));

  return (
    <div className="stage-timeline">
      {EXPECTED_STAGES.map((item) => {
        const stageRun = stageMap.get(item.name);
        const status = stageRun ? stageRun.status : 'PENDING';

        return (
          <div key={item.name} className="stage-item">
            <div className="stage-name">
              {status === 'SUCCEEDED' && <CheckCircle2 size={16} color="var(--success)" />}
              {status === 'RUNNING' && <div className="spinner" />}
              {status === 'FAILED' && <XCircle size={16} color="var(--danger)" />}
              {status === 'SKIPPED' && <MinusCircle size={16} color="var(--text-dim)" />}
              {status === 'PENDING' && <Clock size={16} color="var(--text-dim)" />}
              <span>{item.label}</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              {stageRun && stageRun.latency_ms > 0 && (
                <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                  {stageRun.latency_ms} ms
                </span>
              )}

              <span
                className={`badge ${
                  status === 'SUCCEEDED'
                    ? 'badge-success'
                    : status === 'RUNNING'
                    ? 'badge-purple'
                    : status === 'FAILED'
                    ? 'badge-danger'
                    : 'badge-neutral'
                }`}
              >
                {status}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};
