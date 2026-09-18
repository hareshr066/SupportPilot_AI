import React, { useState, useCallback, useRef } from 'react';

interface BackgroundRippleEffectProps {
  rows?: number;
  cols?: number;
  cellSize?: number;
  interactive?: boolean;
  className?: string;
  rippleColor?: string;
  borderColor?: string;
}

export const BackgroundRippleEffect: React.FC<BackgroundRippleEffectProps> = ({
  rows = 11,
  cols = 32,
  cellSize = 52,
  interactive = true,
  className = '',
  // rippleColor is reserved for future CSS variable usage
  rippleColor: _rippleColor = 'rgba(99, 102, 241, 0.12)',
  borderColor = 'rgba(99, 102, 241, 0.06)',
}) => {
  const [rippleOrigin, setRippleOrigin] = useState<{ row: number; col: number } | null>(null);
  const [rippleKey, setRippleKey] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleCellInteraction = useCallback(
    (row: number, col: number) => {
      if (!interactive) return;
      setRippleOrigin({ row, col });
      setRippleKey((prev) => prev + 1);
    },
    [interactive]
  );

  const getDelay = (row: number, col: number): number => {
    if (!rippleOrigin) return 0;
    const distance = Math.sqrt(
      Math.pow(row - rippleOrigin.row, 2) + Math.pow(col - rippleOrigin.col, 2)
    );
    return distance * 40;
  };

  return (
    <div
      ref={containerRef}
      className={`ripple-grid-container ${className}`}
      style={{
        position: 'absolute',
        inset: 0,
        overflow: 'hidden',
        display: 'grid',
        gridTemplateColumns: `repeat(${cols}, ${cellSize}px)`,
        gridTemplateRows: `repeat(${rows}, ${cellSize}px)`,
        justifyContent: 'center',
        alignContent: 'center',
        zIndex: 0,
        pointerEvents: interactive ? 'auto' : 'none',
      }}
    >
      {Array.from({ length: rows * cols }, (_, index) => {
        const row = Math.floor(index / cols);
        const col = index % cols;
        const delay = rippleOrigin ? getDelay(row, col) : 0;

        return (
          <div
            key={`${row}-${col}-${rippleKey}`}
            onClick={() => handleCellInteraction(row, col)}
            onMouseEnter={() => handleCellInteraction(row, col)}
            style={{
              width: cellSize,
              height: cellSize,
              border: `1px solid ${borderColor}`,
              transition: 'background-color 0.3s ease, opacity 0.3s ease',
              cursor: interactive ? 'pointer' : 'default',
              animation: rippleOrigin
                ? `cellRipple 600ms ease-out ${delay}ms both`
                : undefined,
              background: 'transparent',
            }}
            data-row={row}
            data-col={col}
          />
        );
      })}
    </div>
  );
};
