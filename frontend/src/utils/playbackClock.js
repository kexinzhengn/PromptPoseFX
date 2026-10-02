function normalizeFrame(frame, totalFrames) {
  if (totalFrames <= 1) return 0;
  return Math.max(0, Math.min(totalFrames - 1, Math.round(frame)));
}


/** Create a frame clock driven by requestAnimationFrame timestamps. */
export function createPlaybackClock({
  fps = 30,
  totalFrames = 1,
  onFrame,
  requestFrame = globalThis.requestAnimationFrame?.bind(globalThis),
  cancelFrame = globalThis.cancelAnimationFrame?.bind(globalThis),
}) {
  let frameCount = Math.max(1, Math.floor(totalFrames));
  let currentFrame = 0;
  let isPlaying = false;
  let animationFrameId = null;
  let anchorTimestamp = null;
  let anchorFrame = 0;
  let lastElapsedFrames = 0;
  let sequence = 0;
  let continuityId = 0;
  let continuityReason = 'none';
  let disposed = false;

  if (!requestFrame || !cancelFrame) {
    throw new Error('Playback clock requires requestAnimationFrame and cancelAnimationFrame');
  }

  const schedule = () => {
    animationFrameId = requestFrame(tick);
  };

  const emitFrame = (nextFrame, deltaFrames, discontinuity) => {
    currentFrame = nextFrame;
    if (discontinuity !== 'none') {
      continuityId += 1;
      continuityReason = discontinuity;
    }
    sequence += 1;
    onFrame?.({
      currentFrame,
      deltaFrames,
      discontinuity,
      sequence,
      continuityId,
      continuityReason,
    });
  };

  const tick = (timestamp) => {
    animationFrameId = null;
    if (!isPlaying || disposed) return;

    if (anchorTimestamp === null) {
      anchorTimestamp = timestamp;
      anchorFrame = currentFrame;
      lastElapsedFrames = 0;
    } else {
      const elapsedFrames = Math.floor(((timestamp - anchorTimestamp) * fps) / 1000 + 1e-9);
      const targetFrame = (anchorFrame + elapsedFrames) % frameCount;
      const previousAbsoluteFrame = anchorFrame + lastElapsedFrames;
      const nextAbsoluteFrame = anchorFrame + elapsedFrames;
      const looped = Math.floor(nextAbsoluteFrame / frameCount) > Math.floor(previousAbsoluteFrame / frameCount);
      if (targetFrame !== currentFrame || looped) {
        emitFrame(targetFrame, looped ? 0 : targetFrame - currentFrame, looped ? 'loop' : 'none');
      }
      lastElapsedFrames = elapsedFrames;
    }

    schedule();
  };

  const resetAnchor = () => {
    anchorTimestamp = null;
    anchorFrame = currentFrame;
    lastElapsedFrames = 0;
  };

  return {
    play() {
      if (disposed || isPlaying) return;
      isPlaying = true;
      resetAnchor();
      schedule();
    },
    pause() {
      if (!isPlaying) return;
      isPlaying = false;
      resetAnchor();
      if (animationFrameId !== null) cancelFrame(animationFrameId);
      animationFrameId = null;
    },
    seek(frame) {
      const nextFrame = normalizeFrame(frame, frameCount);
      resetAnchor();
      emitFrame(nextFrame, 0, 'seek');
    },
    setTotalFrames(nextTotalFrames) {
      frameCount = Math.max(1, Math.floor(nextTotalFrames || 1));
      const nextFrame = normalizeFrame(currentFrame, frameCount);
      if (nextFrame !== currentFrame) {
        emitFrame(nextFrame, 0, 'seek');
      }
      resetAnchor();
    },
    getSnapshot() {
      return {
        currentFrame,
        isPlaying,
        totalFrames: frameCount,
        sequence,
        continuityId,
        continuityReason,
      };
    },
    dispose() {
      this.pause();
      disposed = true;
    },
  };
}
