import test from 'node:test';
import assert from 'node:assert/strict';

import { createEffectFrameTracker } from './effectFrameTracker.js';


function frameEvent(overrides = {}) {
  return {
    currentFrame: 10,
    discontinuity: 'none',
    sequence: 1,
    continuityId: 0,
    continuityReason: 'none',
    ...overrides,
  };
}


test('each Effect consumes a playback frame once while repeated redraws stay passive', () => {
  const tracker = createEffectFrameTracker();
  const event = frameEvent();
  const spark = {};
  const ribbon = {};

  assert.deepEqual(tracker.consume(spark, event), {
    isNewFrame: true,
    deltaFrames: 0,
    discontinuity: 'none',
  });
  assert.deepEqual(tracker.consume(spark, event), {
    isNewFrame: false,
    deltaFrames: 0,
    discontinuity: 'none',
  });
  assert.deepEqual(tracker.consume(ribbon, event), {
    isNewFrame: true,
    deltaFrames: 0,
    discontinuity: 'none',
  });
});


test('an Effect receives its own forward delta and any discontinuity it missed', () => {
  const tracker = createEffectFrameTracker();
  const spark = {};
  tracker.consume(spark, frameEvent());

  assert.deepEqual(tracker.consume(spark, frameEvent({
    currentFrame: 13,
    sequence: 2,
  })), {
    isNewFrame: true,
    deltaFrames: 3,
    discontinuity: 'none',
  });

  assert.deepEqual(tracker.consume(spark, frameEvent({
    currentFrame: 6,
    sequence: 4,
    continuityId: 1,
    continuityReason: 'seek',
  })), {
    isNewFrame: true,
    deltaFrames: 0,
    discontinuity: 'seek',
  });
});
