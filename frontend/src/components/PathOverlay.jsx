import React from 'react';

import { appendDraftPathPoint } from '../utils/editorPathOperations.js';

function normalizedPosition(event, element) {
  const rect = element.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
    y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
  };
}

function toPolyline(points, width, height) {
  return points.map((point) => `${point.x * width},${point.y * height}`).join(' ');
}

export default function PathOverlay({
  active,
  redrawPathId = null,
  paths = [],
  visible = true,
  width,
  height,
  onAddPath,
  onRedrawPath,
  onCancelRedraw,
  selectedPathId,
  onSelectPath,
  onDeletePath,
  onStartRedraw,
  selectionEnabled = true,
}) {
  const overlayRef = React.useRef(null);
  const previewOutlineRef = React.useRef(null);
  const previewRef = React.useRef(null);
  const draftRef = React.useRef(null);

  const updatePreview = React.useCallback((points) => {
    const polyline = toPolyline(points, width, height);
    if (previewOutlineRef.current) {
      previewOutlineRef.current.setAttribute('points', polyline);
    }
    if (previewRef.current) {
      previewRef.current.setAttribute('points', polyline);
    }
  }, [height, width]);

  const finishDrawing = React.useCallback((event, cancelled = false) => {
    const draft = draftRef.current;
    if (!draft) return;
    draftRef.current = null;
    updatePreview([]);
    if (cancelled) {
      if (redrawPathId) onCancelRedraw?.();
    } else if (draft.length >= 2) {
      if (redrawPathId) onRedrawPath?.(redrawPathId, draft);
      else onAddPath?.(draft);
    }
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, [onAddPath, onCancelRedraw, onRedrawPath, redrawPathId, updatePreview]);

  if (!visible) return null;

  const selectedPath = paths.find((path) => path.id === selectedPathId);
  const selectedStart = selectedPath?.points[0];

  return (
    <div
      data-name="path-overlay"
      data-active={active ? 'true' : 'false'}
      className="absolute inset-0"
      style={{
        zIndex: 32,
        pointerEvents: 'none',
        touchAction: 'none',
      }}
    >
      <svg
        ref={overlayRef}
        aria-label="Draw Path surface"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="absolute inset-0"
        style={{
          pointerEvents: active ? 'auto' : 'none',
          cursor: active ? 'crosshair' : 'default',
        }}
        onPointerDown={(event) => {
          if (!active) return;
          event.preventDefault();
          event.stopPropagation();
          event.currentTarget.setPointerCapture(event.pointerId);
          const start = normalizedPosition(event, overlayRef.current);
          draftRef.current = [start];
          updatePreview(draftRef.current);
        }}
        onPointerMove={(event) => {
          if (!draftRef.current || !overlayRef.current) return;
          const next = appendDraftPathPoint(
            draftRef.current,
            normalizedPosition(event, overlayRef.current),
            width,
            height,
          );
          if (next === draftRef.current) return;
          draftRef.current = next;
          updatePreview(next);
        }}
        onPointerUp={(event) => finishDrawing(event)}
        onPointerCancel={(event) => finishDrawing(event, true)}
      >
        {paths.map((path) => {
          const start = path.points[0];
          const selected = path.id === selectedPathId;
          return (
            <g key={path.id} data-name="saved-path" data-path-id={path.id} data-selected={selected ? 'true' : 'false'}>
              <polyline
                data-name="path-contrast-outline"
                points={toPolyline(path.points, width, height)}
                fill="none"
                stroke="rgba(0,0,0,0.82)"
                strokeWidth={selected ? 8 : 6}
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
                opacity={path.id === redrawPathId ? 0.25 : 0.9}
                style={{ pointerEvents: 'none' }}
              />
              <polyline
                data-name="path-visible-stroke"
                points={toPolyline(path.points, width, height)}
                fill="none"
                stroke={selected ? '#f2f2f2' : '#89b4df'}
                strokeWidth={selected ? 4 : 2}
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
                opacity={path.id === redrawPathId ? 0.35 : 0.9}
                style={{ pointerEvents: 'none' }}
              />
              {!active && selectionEnabled ? (
                <polyline
                  data-name="path-hit-area"
                  points={toPolyline(path.points, width, height)}
                  fill="none"
                  stroke="transparent"
                  strokeWidth="16"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                  style={{ pointerEvents: 'stroke', cursor: 'pointer' }}
                  onPointerDown={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onSelectPath?.(path.id);
                  }}
                />
              ) : null}
              {start ? (
                <text
                  x={start.x * width + 8}
                  y={start.y * height - 8}
                  fill="#FFFFFF"
                  fontSize="11"
                  fontFamily="monospace"
                  style={{ pointerEvents: 'none', textShadow: '0 1px 3px #000' }}
                >
                  {path.alias}
                </text>
              ) : null}
            </g>
          );
        })}
        <polyline
          ref={previewOutlineRef}
          data-name="draft-path-outline"
          points=""
          fill="none"
          stroke="rgba(0,0,0,0.82)"
          strokeWidth="7"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
          style={{ pointerEvents: 'none' }}
        />
        <polyline
          ref={previewRef}
          data-name="draft-path"
          points=""
          fill="none"
          stroke="#d7a77f"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
          style={{ pointerEvents: 'none' }}
        />
      </svg>
      {!active && selectionEnabled && selectedStart ? (
        <div
          data-name="path-actions"
          className="absolute flex gap-1"
          style={{
            left: Math.min(width - 88, Math.max(4, selectedStart.x * width + 8)),
            top: Math.min(height - 28, Math.max(4, selectedStart.y * height + 8)),
            pointerEvents: 'auto',
          }}
        >
          <button
            type="button"
            aria-label={`Redraw ${selectedPath.alias}`}
            className="rounded px-2 py-1 text-[10px] font-medium"
            style={{ color: '#FFFFFF', backgroundColor: 'rgba(24,24,30,0.95)', border: '1px solid rgba(255,255,255,0.2)' }}
            onClick={() => onStartRedraw?.(selectedPath.id)}
          >
            Redraw
          </button>
          <button
            type="button"
            aria-label={`Delete ${selectedPath.alias}`}
            className="rounded px-2 py-1 text-[11px] font-medium"
            style={{ color: '#FFFFFF', backgroundColor: 'rgba(24,24,30,0.95)', border: '1px solid rgba(255,255,255,0.2)' }}
            onClick={() => onDeletePath?.(selectedPath.id)}
          >
            ×
          </button>
        </div>
      ) : null}
    </div>
  );
}
