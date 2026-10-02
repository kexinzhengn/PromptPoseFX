import React from 'react';
import { createFrameControls } from '../../../shared/controlRuntime.mjs';
import {
  findNearestJoint,
  formatJointName,
  resolvePointCreation,
} from '../utils/jointPicker.js';
import JointHoverLabel from './JointHoverLabel.jsx';

function normalizedPosition(event, element) {
  const rect = element.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
    y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
  };
}

export default function PointOverlay({
  editorState,
  width,
  height,
  currentFrame,
  getJointsAtFrame,
  addMode,
  onAddPoint,
  onJointClick,
  onMovePoint,
  onCommitPoint,
  selectedPointId,
  onSelectPoint,
  onDeletePoint,
  visible = true,
}) {
  const overlayRef = React.useRef(null);
  const dragRef = React.useRef(null);
  const editorStateRef = React.useRef(editorState);
  const [hoveredJointName, setHoveredJointName] = React.useState(null);
  editorStateRef.current = editorState;

  const displayedPoints = React.useMemo(() => {
    if (!editorState || !width || !height) return [];
    const bindings = Object.fromEntries(
      editorState.points.map((point) => [
        point.id,
        { type: 'point', id: point.id },
      ]),
    );
    const controls = createFrameControls({
      bindings,
      editorState,
      width,
      height,
      currentFrame,
      getJointsAtFrame,
    });
    return editorState.points.flatMap((point) => {
      const resolved = controls.getPoint(point.id);
      return resolved.valid
        ? [{ point, x: resolved.x / width, y: resolved.y / height }]
        : [];
    });
  }, [editorState, width, height, currentFrame, getJointsAtFrame]);

  const handleCreate = React.useCallback((event) => {
    if (!overlayRef.current) return;
    if (event.target.closest?.('[data-name="fixed-point"]')) return;
    const position = normalizedPosition(event, overlayRef.current);
    const creation = resolvePointCreation({
      joints: getJointsAtFrame(currentFrame),
      x: position.x * width,
      y: position.y * height,
      addMode,
    });
    if (!creation) return;
    event.preventDefault();
    event.stopPropagation();
    if (creation.type === 'joint') {
      onJointClick?.(creation.joint);
      return;
    }
    onAddPoint?.(position);
  }, [addMode, currentFrame, getJointsAtFrame, height, onAddPoint, onJointClick, width]);

  const handleOverlayMove = React.useCallback((event) => {
    if (!overlayRef.current || dragRef.current) return;
    if (event.target.closest?.('[data-name="fixed-point"]')) {
      setHoveredJointName(null);
      return;
    }
    const position = normalizedPosition(event, overlayRef.current);
    const joints = getJointsAtFrame(currentFrame);
    const nearest = findNearestJoint(
      joints,
      position.x * width,
      position.y * height,
    );
    setHoveredJointName(nearest?.name ?? null);
  }, [currentFrame, getJointsAtFrame, height, width]);

  const handlePointDown = React.useCallback((event, pointId) => {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { pointId, position: null };
    onSelectPoint?.(pointId);
  }, [onSelectPoint]);

  const handlePointMove = React.useCallback((event) => {
    if (!dragRef.current || !overlayRef.current) return;
    const position = normalizedPosition(event, overlayRef.current);
    const point = editorStateRef.current?.points.find(
      (candidate) => candidate.id === dragRef.current.pointId,
    );
    let jointPosition = null;
    if (point?.source.type === 'joint') {
      const joint = getJointsAtFrame(currentFrame)?.[point.source.joint];
      if (!joint || (joint.x === 0 && joint.y === 0)) return;
      jointPosition = { x: joint.x / width, y: joint.y / height };
    }
    dragRef.current.position = position;
    onMovePoint?.(dragRef.current.pointId, position, jointPosition);
  }, [currentFrame, getJointsAtFrame, height, onMovePoint, width]);

  const handlePointUp = React.useCallback((event) => {
    if (!dragRef.current) return;
    event.stopPropagation();
    const { pointId, position } = dragRef.current;
    dragRef.current = null;
    if (position) onCommitPoint?.(pointId);
  }, [onCommitPoint]);

  if (!visible) return null;

  const hoveredPosition = hoveredJointName
    ? getJointsAtFrame(currentFrame)?.[hoveredJointName]
    : null;
  const hoveredJoint = hoveredPosition && !(hoveredPosition.x === 0 && hoveredPosition.y === 0)
    ? { name: hoveredJointName, x: hoveredPosition.x, y: hoveredPosition.y }
    : null;

  return (
    <div
      ref={overlayRef}
      data-name="point-overlay"
      className="absolute inset-0"
      style={{
        zIndex: 30,
        pointerEvents: 'auto',
        cursor: hoveredJoint ? 'pointer' : (addMode ? 'crosshair' : 'default'),
        touchAction: 'none',
      }}
      onPointerDown={handleCreate}
      onPointerMove={handleOverlayMove}
      onPointerLeave={() => setHoveredJointName(null)}
    >
      <JointHoverLabel joint={hoveredJoint} width={width} height={height} />
      {displayedPoints.map(({ point, x, y }) => {
        const isJointPoint = point.source.type === 'joint';
        const pointKind = isJointPoint ? 'Joint' : 'Fixed';
        const jointLabel = isJointPoint ? formatJointName(point.source.joint) : null;
        return (
        <React.Fragment key={point.id}>
          <button
            type="button"
            data-name="fixed-point"
            data-point-kind={point.source.type}
            aria-label={jointLabel ? `Move ${point.alias}, ${jointLabel}` : `Move ${point.alias}`}
            title={`${point.alias} · ${pointKind} — drag to move`}
            className="group absolute -translate-x-1/2 -translate-y-1/2"
            style={{
              left: `${x * 100}%`,
              top: `${y * 100}%`,
              width: 32,
              height: 32,
              pointerEvents: 'auto',
              cursor: 'grab',
              color: '#FFFFFF',
              backgroundColor: 'transparent',
              border: 0,
            }}
            onPointerDown={(event) => handlePointDown(event, point.id)}
            onPointerMove={handlePointMove}
            onPointerUp={handlePointUp}
            onPointerCancel={handlePointUp}
          >
            <span
              data-name="point-marker"
              className="absolute"
              style={{
                left: 7,
                top: 7,
                width: 18,
                height: 18,
                backgroundColor: isJointPoint ? '#7a94b3' : '#b69a76',
                borderRadius: isJointPoint ? 9999 : 4,
                border: '2px solid rgba(255,255,255,0.9)',
                boxShadow: point.id === selectedPointId
                  ? '0 0 0 5px rgba(255,255,255,0.35)'
                  : (isJointPoint
                      ? '0 0 0 3px rgba(122,148,179,0.15)'
                      : '0 0 0 3px rgba(182,154,118,0.15)'),
              }}
            />
            <span
              className="absolute text-[10px] font-mono whitespace-nowrap"
              style={{ left: 30, top: 7, textShadow: '0 1px 3px #000' }}
            >
              {point.alias}
            </span>
            {jointLabel ? (
              <span
                role="tooltip"
                className="pointer-events-none invisible absolute bottom-full left-4 mb-1 whitespace-nowrap rounded-md border px-2 py-1 text-xs font-medium opacity-0 shadow-lg transition-opacity group-hover:visible group-hover:opacity-100 group-focus-visible:visible group-focus-visible:opacity-100"
                style={{
                  color: '#F4F4F5',
                  backgroundColor: 'rgba(24,24,30,0.96)',
                  borderColor: 'rgba(255,255,255,0.12)',
                }}
              >
                {jointLabel}
              </span>
            ) : null}
          </button>
          {point.id === selectedPointId ? (
            <button
              type="button"
              data-name="delete-point"
              aria-label={`Delete ${point.alias}`}
              title={`Delete ${point.alias}`}
              className="absolute flex items-center justify-center rounded-full text-xs font-medium"
              style={{
                left: `${x * 100}%`,
                top: `${y * 100}%`,
                width: 20,
                height: 20,
                transform: 'translate(10px, -28px)',
                pointerEvents: 'auto',
                cursor: 'pointer',
                color: '#FFFFFF',
                backgroundColor: 'rgba(20,20,24,0.95)',
                border: '1px solid rgba(255,255,255,0.25)',
              }}
              onPointerDown={(event) => {
                event.preventDefault();
                event.stopPropagation();
              }}
              onClick={(event) => {
                event.stopPropagation();
                onDeletePoint?.(point.id);
              }}
            >
              ×
            </button>
          ) : null}
        </React.Fragment>
        );
      })}
    </div>
  );
}
