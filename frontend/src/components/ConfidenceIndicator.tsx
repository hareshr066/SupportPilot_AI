import React from 'react';

interface ConfidenceIndicatorProps {
  confidence: number; // 0.0 to 1.0
  threshold?: number; // default 0.85
  showThreshold?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export const ConfidenceIndicator: React.FC<ConfidenceIndicatorProps> = ({
  confidence,
  threshold = 0.85,
  showThreshold = true,
  size = 'md',
}) => {
  const pct = Math.min(Math.max(confidence * 100, 0), 100);
  const threshPct = threshold * 100;
  const isPassing = confidence >= threshold;

  const barColor = isPassing ? 'var(--success)' : 'var(--warning)';

  return (
    <div className={`confidence-indicator confidence-${size}`}>
      <div className="confidence-header">
        <div className="confidence-label-group">
          <span className="confidence-title">Calibrated Confidence</span>
          <span className="confidence-value" style={{ color: barColor }}>
            {pct.toFixed(1)}%
          </span>
        </div>
        {showThreshold && (
          <div className="confidence-threshold">
            Safety threshold: <strong>{threshPct.toFixed(0)}%</strong>
          </div>
        )}
      </div>

      <div className="confidence-track">
        <div
          className="confidence-fill"
          style={{
            width: `${pct}%`,
            backgroundColor: barColor,
          }}
        />
        {showThreshold && (
          <div
            className="confidence-marker"
            style={{ left: `${threshPct}%` }}
            title={`Safety Threshold: ${threshPct}%`}
          />
        )}
      </div>
    </div>
  );
};
