import React from 'react';
import { PlayIcon } from './icons/Icons.jsx';
import { getTimelineFrame } from '../utils/timelineCoordinates.js';

function framePercent(frame, totalFrames) {
  return totalFrames <= 1 ? 0 : (frame / (totalFrames - 1)) * 100;
}

export function TimelineTrackRow({ effectId, onSelectEffect, children, ...props }) {
  return (
    <div
      {...props}
      data-name="timeline-track"
      data-effect-id={effectId}
      data-selects-effect="true"
      onPointerDownCapture={() => onSelectEffect?.(effectId)}
    >
      {children}
    </div>
  );
}

export function EffectDeleteButton({ effectId, name, pending = false, running, onDeleteEffect }) {
  return (
    <button
      data-name={pending ? 'timeline-delete-pending-effect' : 'timeline-delete-effect'}
      data-effect-id={effectId}
      type="button"
      className="editor-effect-delete flex-shrink-0 text-sm leading-none"
      disabled={running}
      style={{
        color: running ? 'var(--editor-line)' : 'var(--editor-quiet)',
        cursor: running ? 'default' : 'pointer',
      }}
      aria-label={`Delete ${name || 'Effect'}`}
      title={running ? 'Cannot delete while generating' : 'Delete effect'}
      onClick={(event) => {
        event.stopPropagation();
        onDeleteEffect?.(effectId);
      }}
    >
      ×
    </button>
  );
}

export default function Timeline({ effects, selectedEffectId, onSelectEffect, onAddEffect, onDeleteEffect, onToggleEffect, onAddTimeMarker, onMoveTimeMarker, onCommitTimeMarker, onDeleteTimeMarker, onTrimEffectClip, onCommitEffectClip, runningEffectIds = [], pendingEffects = [], editorWorkspaces = {}, totalFrames, currentFrame, onFrameChange, isPlaying, onTogglePlayback, onPausePlayback }) {
  const LAYER_H = 53;
  const controlsHeight = 50;
  const MAX_VISIBLE_LAYERS = 4;
  const maxTracksHeight = MAX_VISIBLE_LAYERS * LAYER_H + 28;

  const tracksRef = React.useRef(null);
  const scrubberRef = React.useRef(null);
  const markerDragRef = React.useRef(null);
  const clipDragRef = React.useRef(null);
  const [isDragging, setIsDragging] = React.useState(false);
  const trackEntries = [...effects, ...pendingEffects];

  const getFrameFromX = React.useCallback((clientX, ref) => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    return getTimelineFrame(clientX, rect, totalFrames);
  }, [totalFrames]);

  const handlePointerDown = React.useCallback((e) => {
    onPausePlayback?.();
    const frame = getFrameFromX(e.clientX, tracksRef);
    if (frame !== undefined) { onFrameChange(frame); setIsDragging(true); }
  }, [getFrameFromX, onFrameChange, onPausePlayback]);

  const handlePointerMove = React.useCallback((e) => {
    if (!isDragging) return;
    const frame = getFrameFromX(e.clientX, tracksRef);
    if (frame !== undefined) onFrameChange(frame);
  }, [isDragging, getFrameFromX, onFrameChange]);

  const handlePointerUp = React.useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleScrubberDown = React.useCallback((e) => {
    e.stopPropagation();
    onPausePlayback?.();
    e.currentTarget.setPointerCapture(e.pointerId);
    const frame = getFrameFromX(e.clientX, scrubberRef);
    if (frame !== undefined) { onFrameChange(frame); setIsDragging(true); }
  }, [getFrameFromX, onFrameChange, onPausePlayback]);

  const handleScrubberMove = React.useCallback((e) => {
    if (!isDragging) return;
    const frame = getFrameFromX(e.clientX, scrubberRef);
    if (frame !== undefined) onFrameChange(frame);
  }, [isDragging, getFrameFromX, onFrameChange]);

  const handleScrubberKeyDown = React.useCallback((event) => {
    let nextFrame = currentFrame;
    if (event.key === 'ArrowLeft') nextFrame -= 1;
    else if (event.key === 'ArrowRight') nextFrame += 1;
    else if (event.key === 'Home') nextFrame = 0;
    else if (event.key === 'End') nextFrame = Math.max(0, totalFrames - 1);
    else return;
    event.preventDefault();
    onPausePlayback?.();
    onFrameChange?.(Math.max(0, Math.min(Math.max(0, totalFrames - 1), nextFrame)));
  }, [currentFrame, onFrameChange, onPausePlayback, totalFrames]);

  const handleTrackDoubleClick = React.useCallback((event, effectId) => {
    if (effectId !== selectedEffectId) return;
    const frame = getFrameFromX(event.clientX, tracksRef);
    if (frame !== undefined) onAddTimeMarker?.(effectId, frame);
  }, [getFrameFromX, onAddTimeMarker, selectedEffectId]);

  const handleMarkerPointerDown = React.useCallback((event, effectId, markerId) => {
    event.preventDefault();
    event.stopPropagation();
    if (effectId !== selectedEffectId) return;
    onPausePlayback?.();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    markerDragRef.current = { effectId, markerId };
  }, [onPausePlayback, selectedEffectId]);

  const handleMarkerPointerMove = React.useCallback((event) => {
    const drag = markerDragRef.current;
    if (!drag) return;
    event.preventDefault();
    event.stopPropagation();
    const frame = getFrameFromX(event.clientX, tracksRef);
    if (frame !== undefined) {
      onMoveTimeMarker?.(drag.effectId, drag.markerId, frame);
    }
  }, [getFrameFromX, onMoveTimeMarker]);

  const handleMarkerPointerUp = React.useCallback((event) => {
    const drag = markerDragRef.current;
    if (!drag) return;
    event.preventDefault();
    event.stopPropagation();
    markerDragRef.current = null;
    onCommitTimeMarker?.(drag.effectId);
  }, [onCommitTimeMarker]);

  const handleMarkerDoubleClick = React.useCallback((event, effectId, markerId) => {
    event.preventDefault();
    event.stopPropagation();
    markerDragRef.current = null;
    if (effectId === selectedEffectId) {
      onDeleteTimeMarker?.(effectId, markerId);
    }
  }, [onDeleteTimeMarker, selectedEffectId]);

  const handleClipPointerDown = React.useCallback((event, effectId, edge) => {
    event.preventDefault();
    event.stopPropagation();
    onPausePlayback?.();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    clipDragRef.current = { effectId, edge };
  }, [onPausePlayback]);

  const handleClipPointerMove = React.useCallback((event) => {
    const drag = clipDragRef.current;
    if (!drag) return;
    event.preventDefault();
    event.stopPropagation();
    const frame = getFrameFromX(event.clientX, tracksRef);
    if (frame !== undefined) {
      onTrimEffectClip?.(drag.effectId, drag.edge, frame);
    }
  }, [getFrameFromX, onTrimEffectClip]);

  const handleClipPointerUp = React.useCallback((event) => {
    const drag = clipDragRef.current;
    if (!drag) return;
    event.preventDefault();
    event.stopPropagation();
    clipDragRef.current = null;
    onCommitEffectClip?.(drag.effectId);
  }, [onCommitEffectClip]);

  React.useEffect(() => {
    if (!isDragging) return;
    const handleUp = () => setIsDragging(false);
    window.addEventListener('pointerup', handleUp);
    return () => window.removeEventListener('pointerup', handleUp);
  }, [isDragging]);

  return (
    <div data-name="timeline" className="editor-timeline w-full" style={{ height: maxTracksHeight + controlsHeight }}>
      <div data-name="timeline-controls" className="editor-timeline-controls" style={{ height: controlsHeight }}>
        <div className="editor-playback">
          <button type="button" aria-label="Previous frame" title="Previous frame" onClick={() => { onPausePlayback?.(); onFrameChange?.(Math.max(0, currentFrame - 1)); }}>‹</button>
          <button
            data-name="playback-play"
            type="button"
            aria-label={isPlaying ? 'Pause playback' : 'Play playback'}
            title={isPlaying ? 'Pause' : 'Play'}
            onClick={onTogglePlayback}
          >
            {isPlaying ? <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg> : <PlayIcon />}
          </button>
          <button type="button" aria-label="Next frame" title="Next frame" onClick={() => { onPausePlayback?.(); onFrameChange?.(Math.min(Math.max(0, totalFrames - 1), currentFrame + 1)); }}>›</button>
        </div>
        <div className="editor-transport">
          <span data-name="timeline-frame-label" className="editor-frame-label" style={{ whiteSpace: 'nowrap' }}>
            {String(currentFrame).padStart(4, '0')} / {String(totalFrames).padStart(4, '0')}
          </span>
          <div
            ref={scrubberRef}
            data-name="timeline-scrubber"
            className="editor-scrubber"
            role="slider"
            tabIndex={0}
            aria-label="Playback position"
            aria-valuemin={0}
            aria-valuemax={Math.max(0, totalFrames - 1)}
            aria-valuenow={currentFrame}
            onPointerDown={handleScrubberDown}
            onPointerMove={handleScrubberMove}
            onPointerUp={handlePointerUp}
            onKeyDown={handleScrubberKeyDown}
          >
            <div className="editor-scrubber-track"><div className="editor-scrubber-progress" style={{ width: `${framePercent(currentFrame, totalFrames)}%` }} /></div>
            <div className="editor-scrubber-thumb" style={{ left: `${framePercent(currentFrame, totalFrames)}%` }} />
          </div>
        </div>
        <div className="editor-timeline-actions">
          <button type="button" disabled={!selectedEffectId} onClick={() => onAddTimeMarker?.(selectedEffectId, currentFrame)}>+ Marker</button>
          <button type="button" onClick={() => onAddEffect?.()}>+ Effect layer</button>
        </div>
      </div>
      <div className="editor-timeline-ruler-row">
        <div />
        <div className="editor-timeline-ruler">
          {Array.from({ length: 6 }, (_, index) => {
            const frame = Math.round((Math.max(1, totalFrames - 1) * index) / 5);
            return <span key={index} style={{ left: `${index * 20}%` }}>{String(frame).padStart(4, '0')}</span>;
          })}
        </div>
      </div>
      <div
        data-name="timeline-track-viewport"
        className="editor-track-viewport flex overflow-y-auto overflow-x-hidden items-start"
        style={{ flex: 1, minHeight: 0, minWidth: 0 }}
      >
        {/* Layer names */}
        <div data-name="timeline-layers" className="editor-timeline-layers flex-shrink-0">
          {effects.map(fx => {
            const sel = fx.id === selectedEffectId;
            return (
              <div
                key={fx.id}
                data-name="timeline-layer"
                className={`editor-layer flex items-center gap-2.5 px-3 ${sel ? 'selected' : ''}`}
                style={{
                  height: LAYER_H,
                }}
              >
                <button
                  type="button"
                  className="editor-layer-select"
                  aria-label={`Select ${fx.name}`}
                  aria-pressed={sel}
                  onClick={() => onSelectEffect?.(fx.id)}
                >
                  <span className="editor-layer-indicator" style={{ opacity: fx.visible === false ? 0.35 : 1 }} />
                  <span className="text-xs truncate">{fx.name}</span>
                </button>
                <button
                  data-name="timeline-toggle-effect"
                  type="button"
                  aria-label={fx.visible === false ? `Enable ${fx.name}` : `Disable ${fx.name}`}
                  title={fx.visible === false ? 'Show effect' : 'Hide effect'}
                  className="editor-layer-toggle flex-shrink-0 text-[10px] px-1.5 py-0.5"
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleEffect?.(fx.id);
                  }}
                >
                  {fx.visible === false ? 'Off' : 'On'}
                </button>
                {fx.status === 'draft' && (
                  <span
                    className="editor-layer-status flex-shrink-0 text-[10px] px-1.5 py-0.5"
                  >
                    Draft
                  </span>
                )}
                <EffectDeleteButton
                  effectId={fx.id}
                  name={fx.name}
                  running={runningEffectIds.includes(fx.id)}
                  onDeleteEffect={onDeleteEffect}
                />
              </div>
            );
          })}
          {pendingEffects.map((entry, idx) => {
            const sel = entry.id === selectedEffectId;
            return (
              <div
                key={entry.id}
                data-name="timeline-pending-layer"
                className={`editor-layer editor-layer-pending flex items-center gap-2.5 px-3 ${sel ? 'selected' : ''}`}
                style={{
                  height: LAYER_H,
                }}
              >
                <button
                  type="button"
                  className="editor-layer-select"
                  aria-label={`Select ${entry.name || 'Pending Effect'}`}
                  aria-pressed={sel}
                  onClick={() => onSelectEffect?.(entry.id)}
                >
                  <span className="editor-layer-indicator" />
                  <span className="text-xs truncate">{entry.name || 'Pending'}</span>
                </button>
                <span className="editor-layer-status flex-shrink-0 text-[10px] px-1.5 py-0.5">
                  {idx + 1}
                </span>
                <EffectDeleteButton
                  effectId={entry.id}
                  name={entry.name || 'Pending Effect'}
                  pending
                  running={runningEffectIds.includes(entry.id)}
                  onDeleteEffect={onDeleteEffect}
                />
              </div>
            );
          })}
        </div>

        {/* Tracks */}
        <div
          ref={tracksRef}
          data-name="timeline-tracks"
          className="flex-1 relative"
          style={{ cursor: 'pointer', minWidth: 0 }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
        >
          <div className="absolute inset-0" style={{ pointerEvents: 'none' }}>
            {Array.from({ length: Math.ceil(totalFrames / 10) + 1 }).map((_, i) => (
              <div key={i} className="absolute top-0 h-full"
                style={{
                  left: `${(i * 10 / totalFrames) * 100}%`, width: 1,
                  backgroundColor: i % 3 === 0 ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.04)',
                }} />
            ))}
          </div>

          {trackEntries.map((entry) => {
            const editorState = editorWorkspaces[entry.id]?.editorState;
            const markers = editorState?.markers || [];
            const interval = editorState?.active_interval || {
              start_frame: 0,
              end_frame: Math.max(0, totalFrames - 1),
            };
            const clipLeft = framePercent(interval.start_frame, totalFrames);
            const clipRight = framePercent(interval.end_frame, totalFrames);
            const selected = entry.id === selectedEffectId;
            return (
              <TimelineTrackRow
                key={entry.id}
                effectId={entry.id}
                onSelectEffect={onSelectEffect}
                className="relative"
                onDoubleClick={(event) => handleTrackDoubleClick(event, entry.id)}
                style={{
                  height: LAYER_H,
                  borderBottom: '1px solid var(--editor-raised)',
                }}
              >
                <div
                  data-name="timeline-effect-clip"
                  data-start-frame={interval.start_frame}
                  data-end-frame={interval.end_frame}
                  className={`editor-effect-clip absolute ${selected ? 'selected' : ''}`}
                  style={{
                    left: `${clipLeft}%`,
                    width: `${Math.max(0, clipRight - clipLeft)}%`,
                    top: 17,
                    height: 28,
                  }}
                />
                {selected ? ['start', 'end'].map((edge) => (
                  <button
                    key={edge}
                    data-name="timeline-clip-handle"
                    data-effect-id={entry.id}
                    data-edge={edge}
                    type="button"
                    aria-label={`Trim Effect Clip ${edge}`}
                    title={`Drag to trim the Effect Clip ${edge}`}
                    onPointerDown={(event) => handleClipPointerDown(event, entry.id, edge)}
                    onPointerMove={handleClipPointerMove}
                    onPointerUp={handleClipPointerUp}
                    onPointerCancel={handleClipPointerUp}
                    onDoubleClick={(event) => event.stopPropagation()}
                    className="editor-clip-handle absolute"
                    style={{
                      left: `${edge === 'start' ? clipLeft : clipRight}%`,
                      top: 17,
                      width: 8,
                      height: 28,
                      cursor: 'ew-resize',
                      zIndex: 4,
                      touchAction: 'none',
                      transform: edge === 'start' ? 'translateX(0)' : 'translateX(-100%)',
                    }}
                  />
                )) : null}
                {markers.map((marker) => {
                  const outsideClip = marker.frame < interval.start_frame
                    || marker.frame > interval.end_frame;
                  return (
                  <React.Fragment key={marker.id}>
                    {selected ? (
                      <span
                        data-name="timeline-marker-label"
                        className="editor-marker-label absolute -translate-x-1/2 px-1 font-mono text-[9px] leading-[13px] pointer-events-none"
                        style={{
                          left: `${framePercent(marker.frame, totalFrames)}%`,
                          top: 1,
                          opacity: outsideClip ? 0.45 : 1,
                          zIndex: 5,
                        }}
                      >
                        {marker.alias}
                      </span>
                    ) : null}
                    <button
                    data-name="timeline-marker"
                    data-marker-id={marker.id}
                    data-editable={selected ? 'true' : 'false'}
                    aria-label={`${marker.alias} at frame ${marker.frame}`}
                    title={`${marker.alias} — drag to move, double-click to delete`}
                    type="button"
                    disabled={!selected}
                    onPointerDown={(event) => handleMarkerPointerDown(event, entry.id, marker.id)}
                    onPointerMove={handleMarkerPointerMove}
                    onPointerUp={handleMarkerPointerUp}
                    onPointerCancel={handleMarkerPointerUp}
                    onDoubleClick={(event) => handleMarkerDoubleClick(event, entry.id, marker.id)}
                    className="editor-marker absolute -translate-x-1/2 flex items-center justify-center"
                    style={{
                      left: `${framePercent(marker.frame, totalFrames)}%`,
                      top: 13,
                      width: 14,
                      height: 29,
                      color: selected ? '#c08a70' : 'var(--editor-quiet)',
                      opacity: outsideClip ? 0.45 : 1,
                      cursor: selected ? 'ew-resize' : 'default',
                      pointerEvents: selected ? 'auto' : 'none',
                      touchAction: 'none',
                      zIndex: 4,
                    }}
                    >
                      <span
                        className="absolute left-1/2 -translate-x-1/2"
                        style={{
                          top: 0,
                          bottom: 4,
                          width: 1,
                          backgroundColor: 'currentColor',
                          opacity: 0.65,
                        }}
                      />
                      <span
                        className="relative block w-2.5 h-2.5"
                        style={{
                          backgroundColor: 'currentColor',
                          clipPath: 'polygon(50% 0%,100% 50%,50% 100%,0% 50%)',
                        }}
                      />
                    </button>
                  </React.Fragment>
                  );
                })}
              </TimelineTrackRow>
            );
          })}
          <div data-name="timeline-playhead" className="editor-playhead absolute top-0 h-full pointer-events-none"
            style={{
              left: `${framePercent(currentFrame, totalFrames)}%`,
            }} />
        </div>
      </div>

    </div>
  );
}
