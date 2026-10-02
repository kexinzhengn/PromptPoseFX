/** Track which playback event each Effect instance has already processed. */
export function createEffectFrameTracker() {
  let effectFrames = new WeakMap();

  return {
    consume(effect, frameEvent) {
      const previous = effectFrames.get(effect);
      if (previous?.sequence === frameEvent.sequence) {
        return {
          isNewFrame: false,
          deltaFrames: 0,
          discontinuity: 'none',
        };
      }

      let deltaFrames = 0;
      let discontinuity = frameEvent.discontinuity;
      if (previous) {
        if (previous.continuityId !== frameEvent.continuityId) {
          discontinuity = frameEvent.continuityReason;
        } else {
          deltaFrames = Math.max(0, frameEvent.currentFrame - previous.currentFrame);
        }
      }

      effectFrames.set(effect, {
        currentFrame: frameEvent.currentFrame,
        sequence: frameEvent.sequence,
        continuityId: frameEvent.continuityId,
      });

      return {
        isNewFrame: true,
        deltaFrames,
        discontinuity,
      };
    },

    reset() {
      effectFrames = new WeakMap();
    },
  };
}
