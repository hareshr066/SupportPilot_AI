import React from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Clock } from 'lucide-react';

interface StatusBadgeProps {
  status?: string;
  decision?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, decision }) => {
  const value = decision || status || 'UNKNOWN';

  if (value === 'AUTO_RESOLVE_RECOMMENDATION' || value === 'AUTO_RESOLVE' || value === 'SUCCEEDED') {
    return (
      <span className="badge badge-success">
        <CheckCircle2 size={12} />
        Auto-Resolution Recommended
      </span>
    );
  }

  if (value === 'HUMAN_ESCALATION' || value === 'ROUTE_TO_TEAM' || value === 'ESCALATED') {
    return (
      <span className="badge badge-warning">
        <AlertTriangle size={12} />
        Human Review Required
      </span>
    );
  }

  if (value === 'FAILED') {
    return (
      <span className="badge badge-danger">
        <XCircle size={12} />
        Analysis Failed
      </span>
    );
  }

  return (
    <span className="badge badge-neutral">
      <Clock size={12} />
      {value}
    </span>
  );
};
