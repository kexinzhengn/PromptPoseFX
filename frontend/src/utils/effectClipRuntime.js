export function createEffectClipTracker() {
  const activity = new Map();

  function consume(effectId, frame, interval) {
    const active = !interval || (
      frame >= interval.start_frame && frame <= interval.end_frame
    );
    const wasActive = activity.get(effectId);
    activity.set(effectId, active);
    return {
      active,
      reentered: active && wasActive === false,
    };
  }

  function reset() {
    activity.clear();
  }

  return { consume, reset };
}
