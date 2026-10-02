import React from 'react';
import { createPortal } from 'react-dom';
import { calculateTooltipPosition } from '../utils/tooltipPosition.js';

const TOOLTIP_WIDTH = 224;
const ESTIMATED_TOOLTIP_HEIGHT = 72;

export default function ParamLabel({ label, description, htmlFor }) {
  const tooltipId = React.useId();
  const triggerRef = React.useRef(null);
  const tooltipRef = React.useRef(null);
  const [isOpen, setIsOpen] = React.useState(false);
  const [position, setPosition] = React.useState(null);
  const labelText = htmlFor
    ? <label htmlFor={htmlFor}>{label}</label>
    : <span>{label}</span>;

  const updatePosition = React.useCallback(() => {
    if (!triggerRef.current || typeof window === 'undefined') return;
    const anchor = triggerRef.current.getBoundingClientRect();
    const tooltipBounds = tooltipRef.current?.getBoundingClientRect();
    setPosition(calculateTooltipPosition(
      anchor,
      {
        width: tooltipBounds?.width || TOOLTIP_WIDTH,
        height: tooltipBounds?.height || ESTIMATED_TOOLTIP_HEIGHT,
      },
      { width: window.innerWidth, height: window.innerHeight },
    ));
  }, []);

  const showTooltip = React.useCallback(() => {
    updatePosition();
    setIsOpen(true);
  }, [updatePosition]);

  React.useLayoutEffect(() => {
    if (!isOpen) return undefined;
    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [isOpen, updatePosition]);

  const visibleTooltip = isOpen && position && typeof document !== 'undefined'
    ? createPortal(
        <span
          ref={tooltipRef}
          id={tooltipId}
          role="tooltip"
          className="pointer-events-none fixed rounded-md border px-2.5 py-2 text-left text-xs leading-relaxed shadow-xl"
          style={{
            left: position.left,
            top: position.top,
            zIndex: 1000,
            width: TOOLTIP_WIDTH,
            color: 'var(--editor-text)',
            backgroundColor: 'var(--editor-panel)',
            borderColor: 'var(--editor-line)',
          }}
        >
          {description}
        </span>,
        document.body,
      )
    : null;

  return (
    <span className="relative inline-flex items-center gap-1.5 text-xs" style={{ color: 'var(--editor-muted)' }}>
      {labelText}
      {description ? (
        <>
          <button
            ref={triggerRef}
            type="button"
            aria-label={`About ${label}`}
            aria-describedby={tooltipId}
            className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border text-[9px] leading-none outline-none focus-visible:ring-1 focus-visible:ring-[#6b829e]"
            style={{ borderColor: 'var(--editor-line)', color: 'var(--editor-muted)' }}
            onMouseEnter={showTooltip}
            onMouseLeave={() => {
              if (document.activeElement !== triggerRef.current) setIsOpen(false);
            }}
            onFocus={showTooltip}
            onBlur={() => setIsOpen(false)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') event.currentTarget.blur();
            }}
          >
            i
          </button>
          {!isOpen ? (
            <span id={tooltipId} role="tooltip" className="sr-only">{description}</span>
          ) : null}
          {visibleTooltip}
        </>
      ) : null}
    </span>
  );
}
