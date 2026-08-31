import React from 'react';
import { Flame, AlertCircle, Info } from 'lucide-react';

interface SeverityBadgeProps {
  severity?: string;
}

export const SeverityBadge: React.FC<SeverityBadgeProps> = ({ severity = 'NORMAL' }) => {
  const upper = severity.toUpperCase();

  if (upper === 'HIGH' || upper === 'CRITICAL') {
    return (
      <span className="badge badge-danger">
        <Flame size={12} />
        {upper}
      </span>
    );
  }

  if (upper === 'MEDIUM') {
    return (
      <span className="badge badge-warning">
        <AlertCircle size={12} />
        MEDIUM
      </span>
    );
  }

  if (upper === 'LOW') {
    return (
      <span className="badge badge-primary">
        <Info size={12} />
        LOW
      </span>
    );
  }

  return (
    <span className="badge badge-neutral">
      <Info size={12} />
      {upper}
    </span>
  );
};
