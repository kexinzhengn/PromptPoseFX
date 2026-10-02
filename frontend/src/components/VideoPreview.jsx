import React from 'react';
import PointOverlay from './PointOverlay.jsx';
import PathOverlay from './PathOverlay.jsx';
import useP5Sketch from '../hooks/useP5Sketch.js';
import usePoseData from '../hooks/usePoseData.js';
import { BODY_CONNECTIONS, FACE_CONNECTIONS } from '../constants/joints.js';
import { createEffectFrameTracker } from '../utils/effectFrameTracker.js';
import { createEffectClipTracker } from '../utils/effectClipRuntime.js';
import { APP_LAYERS } from '../utils/layoutLayers.js';
import { createFrameControls } from '../../../shared/controlRuntime.mjs';

function drawSkeleton(p, joints, pinnedJoints) {
  if (!joints || Object.keys(joints).length === 0) return;

  // Build reverse map: jointName → pinId
  const pinByJoint = {};
  if (pinnedJoints) {
    for (const [pinId, jointName] of Object.entries(pinnedJoints)) {
      pinByJoint[jointName] = pinId;
    }
  }

  // 1. Body skeleton lines
  p.stroke(122, 148, 179, 160);
  p.strokeWeight(1.5);
  for (const [a, b] of BODY_CONNECTIONS) {
    const ja = joints[a];
    const jb = joints[b];
    if (!ja || !jb) continue;
    if ((ja.x === 0 && ja.y === 0) || (jb.x === 0 && jb.y === 0)) continue;
    p.line(ja.x, ja.y, jb.x, jb.y);
  }

  // 2. Face lines (thinner, more transparent)
  p.stroke(122, 148, 179, 80);
  p.strokeWeight(0.8);
  for (const [a, b] of FACE_CONNECTIONS) {
    const ja = joints[a];
    const jb = joints[b];
    if (!ja || !jb) continue;
    if ((ja.x === 0 && ja.y === 0) || (jb.x === 0 && jb.y === 0)) continue;
    p.line(ja.x, ja.y, jb.x, jb.y);
  }

  // 3. Joint dots (+ pin highlights)
  p.noStroke();
  for (const [name, pos] of Object.entries(joints)) {
    if (pos.x === 0 && pos.y === 0) continue;
    const isPinned = name in pinByJoint;
    p.fill(isPinned ? '#b69a76' : '#7a94b3');
    p.circle(pos.x, pos.y, isPinned ? 12 : 8);
  }

  // 4. Pin labels
  p.textSize(11);
  p.textFont('monospace');
  for (const [name, pos] of Object.entries(joints)) {
    if (pos.x === 0 && pos.y === 0) continue;
    const pinId = pinByJoint[name];
    if (!pinId) continue;

    const tx = pos.x + 10;
    const ty = pos.y - 4;
    const tw = p.textWidth(pinId) + 8;
    const th = 16;

    // Background badge
    p.noStroke();
    p.fill(0, 0, 0, 180);
    p.rect(tx - 2, ty - th / 2 + 1, tw, th, 4);

    // Label text
    p.fill(255);
    p.textAlign(p.LEFT, p.CENTER);
    p.text(pinId, tx, ty);
  }
}

export default function VideoPreview({ videoInfo, currentFrame, frameEvent, isVideoLoading, videoError, effectsRef, paramsMapRef, effectVisibilityRef, effectVisibility, visualVersion, isProcessing, pinnedJoints, onJointClick, skeletonVisible, editorWorkspaces, selectedEditorState, pointToolActive, pathToolActive, redrawPathId, onAddFixedPoint, onAddPath, onRedrawPath, onCancelRedraw, onMovePoint, onCommitPoint, selectedPointId, onSelectPoint, onDeletePoint, selectedPathId, onSelectPath, onDeletePath, onStartRedraw }) {
  const [imgError, setImgError] = React.useState(false);
  const [displayWidth, setDisplayWidth] = React.useState(0);
  const frameShellRef = React.useRef(null);
  const p5ContainerRef = React.useRef(null);
  const effectFrameTrackerRef = React.useRef(createEffectFrameTracker());
  const effectClipTrackerRef = React.useRef(createEffectClipTracker());
  const trackedVideoIdRef = React.useRef(videoInfo?.id);
  const hasVideo = Boolean(videoInfo);

  React.useLayoutEffect(() => {
    const shell = frameShellRef.current;
    if (!shell) return;
    setDisplayWidth(shell.getBoundingClientRect().width);
    const observer = new ResizeObserver(([entry]) => {
      setDisplayWidth(entry.contentRect.width);
    });
    observer.observe(shell);
    return () => observer.disconnect();
  }, [hasVideo]);

  // Only request pose data after processing completes
  const poseReady = !isProcessing && !!videoInfo;
  const { getJointsAtFrame, getJointHistory } = usePoseData(videoInfo?.id, poseReady);

  // Sync refs
  // Reset error state when frame changes
  React.useEffect(() => {
    setImgError(false);
  }, [currentFrame, videoInfo?.id]);

  // Render all active effects + skeleton overlay on the p5 canvas
  const renderFrame = React.useCallback((p) => {
    const frame = currentFrame;
    const joints = getJointsAtFrame(frame);
    if (trackedVideoIdRef.current !== videoInfo?.id) {
      effectFrameTrackerRef.current.reset();
      effectClipTrackerRef.current.reset();
      trackedVideoIdRef.current = videoInfo?.id;
    }
    const activeFrameEvent = frameEvent || {
      currentFrame: frame,
      discontinuity: 'none',
      sequence: 0,
      continuityId: 0,
      continuityReason: 'none',
    };
    const baseFrameData = {
      joints,
      currentFrame: frame,
      width: videoInfo?.width,
      height: videoInfo?.height,
      getJointHistory: (jointName, lookbackFrames) => (
        getJointHistory(jointName, frame, lookbackFrames)
      ),
    };

    // Effects (if any)
    const effectsMap = effectsRef?.current;
    const paramsMap = paramsMapRef?.current;
    if (effectsMap && effectsMap.size > 0) {
      for (const [id, registeredInstance] of effectsMap) {
        const editorState = editorWorkspaces?.[id]?.editorState;
        const clipState = effectClipTrackerRef.current.consume(
          id,
          frame,
          editorState?.active_interval,
        );
        if (!clipState.active) continue;
        let instance = registeredInstance;
        if (clipState.reentered) {
          try {
            instance = new registeredInstance.constructor();
            effectsMap.set(id, instance);
          } catch (error) {
            console.error(`[VideoPreview] reset error for effect ${id}:`, error);
            continue;
          }
        }
        if (effectVisibilityRef?.current[id] === false) continue;
        if (!instance.display) continue;
        p.push();
        try {
          const sequentialFrame = effectFrameTrackerRef.current.consume(instance, activeFrameEvent);
          const controls = createFrameControls({
            bindings: instance.constructor.CONTROL_BINDINGS || {},
            editorState: editorState || { points: [] },
            width: videoInfo.width,
            height: videoInfo.height,
            currentFrame: frame,
            getJointsAtFrame,
          });
          const frameData = { ...baseFrameData, ...sequentialFrame, controls };
          instance.display(p, frameData, paramsMap[id] || {});
        } catch (e) {
          console.error(`[VideoPreview] display error for effect ${id}:`, e);
        }
        p.pop();
      }
    }

    // Skeleton overlay (always drawn on top of effects)
    if (skeletonVisible) {
      drawSkeleton(p, joints, pinnedJoints);
    }
  }, [effectsRef, paramsMapRef, effectVisibilityRef, videoInfo, currentFrame, frameEvent, getJointsAtFrame, getJointHistory, pinnedJoints, skeletonVisible, editorWorkspaces]);

  const redrawToken = React.useMemo(
    () => ({ effectVisibility, visualVersion }),
    [effectVisibility, visualVersion],
  );

  useP5Sketch({
    containerRef: p5ContainerRef,
    width: videoInfo?.width,
    height: videoInfo?.height,
    renderFrame,
    redrawToken,
  });

  if (!videoInfo) {
    return (
      <div data-name="video-container-empty" className="editor-preview-empty">
        <span>{isVideoLoading ? 'Preparing video…' : 'Import a video to begin'}</span>
        {videoError && (
          <span className="editor-preview-error">{videoError}</span>
        )}
      </div>
    );
  }

  const frameUrl = videoInfo.id === 'local'
    ? videoInfo.url
    : `/api/video/${videoInfo.id}/img/${String(currentFrame).padStart(4, '0')}.jpg`;

  return (
    <div
      ref={frameShellRef}
      data-name="video-container-shell"
      className="editor-preview-shell"
      style={{ '--frame-ratio': videoInfo.width / videoInfo.height }}
    >
    <div data-name="video-container"
      className="editor-preview-content"
      style={{
        width: videoInfo.width,
        height: videoInfo.height,
        transform: `scale(${displayWidth ? displayWidth / videoInfo.width : 1})`,
      }}
      onPointerDownCapture={(event) => {
        if (!event.target.closest?.('[data-name="saved-path"], [data-name="path-actions"]')) {
          onSelectPath?.(null);
        }
      }}
    >
      {!imgError && frameUrl ? (
        <img
          data-name="video-frame"
          src={frameUrl}
          alt="video frame"
          className="absolute inset-0 w-full h-full object-cover"
          onError={() => setImgError(true)}
        />
      ) : (
        <div
          data-name="video-frame-empty"
          className="absolute inset-0 flex items-center justify-center text-sm"
          style={{ color: 'var(--editor-quiet)', backgroundColor: '#101010' }}
        >
          Video frame unavailable. Upload the video again.
        </div>
      )}
      {/* p5 canvas overlay — effects + skeleton + pins */}
      <div
        ref={p5ContainerRef}
        data-name="p5-canvas"
        className="absolute inset-0"
        style={{ zIndex: APP_LAYERS.videoCanvas }}
      />
      <PointOverlay
        editorState={selectedEditorState}
        width={videoInfo.width}
        height={videoInfo.height}
        currentFrame={currentFrame}
        getJointsAtFrame={getJointsAtFrame}
        addMode={pointToolActive}
        onAddPoint={onAddFixedPoint}
        onJointClick={onJointClick}
        onMovePoint={onMovePoint}
        onCommitPoint={onCommitPoint}
        selectedPointId={selectedPointId}
        onSelectPoint={onSelectPoint}
        onDeletePoint={onDeletePoint}
        visible={skeletonVisible}
      />
      <PathOverlay
        active={pathToolActive || !!redrawPathId}
        redrawPathId={redrawPathId}
        paths={selectedEditorState?.paths || []}
        width={videoInfo.width}
        height={videoInfo.height}
        onAddPath={onAddPath}
        onRedrawPath={onRedrawPath}
        onCancelRedraw={onCancelRedraw}
        selectedPathId={selectedPathId}
        onSelectPath={onSelectPath}
        onDeletePath={onDeletePath}
        onStartRedraw={onStartRedraw}
        selectionEnabled={!pointToolActive}
        visible={skeletonVisible}
      />
    </div>
    </div>
  );
}
