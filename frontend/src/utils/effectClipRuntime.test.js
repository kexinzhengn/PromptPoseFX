import assert from 'node:assert/strict';
import test from 'node:test';

import { createEffectClipTracker } from './effectClipRuntime.js';


test('Effect Clip renders inclusively and requests one reset on each re-entry', () => {
  const tracker = createEffectClipTracker();
  const interval = { start_frame: 10, end_frame: 20 };

  assert.deepEqual(tracker.consume('effect-1', 5, interval), {
    active: false,
    reentered: false,
  });
  assert.deepEqual(tracker.consume('effect-1', 10, interval), {
    active: true,
    reentered: true,
  });
  assert.deepEqual(tracker.consume('effect-1', 11, interval), {
    active: true,
    reentered: false,
  });
  assert.deepEqual(tracker.consume('effect-1', 21, interval), {
    active: false,
    reentered: false,
  });
  assert.deepEqual(tracker.consume('effect-1', 20, interval), {
    active: true,
    reentered: true,
  });
});


test('Effect Clip changes and different Effects keep independent activity', () => {
  const tracker = createEffectClipTracker();

  assert.deepEqual(
    tracker.consume('effect-1', 15, { start_frame: 10, end_frame: 20 }),
    { active: true, reentered: false },
  );
  assert.deepEqual(
    tracker.consume('effect-2', 15, { start_frame: 20, end_frame: 30 }),
    { active: false, reentered: false },
  );
  assert.deepEqual(
    tracker.consume('effect-1', 15, { start_frame: 20, end_frame: 30 }),
    { active: false, reentered: false },
  );
  assert.deepEqual(
    tracker.consume('effect-1', 15, { start_frame: 10, end_frame: 30 }),
    { active: true, reentered: true },
  );
  assert.deepEqual(
    tracker.consume('effect-2', 20, { start_frame: 20, end_frame: 30 }),
    { active: true, reentered: true },
  );
});


test('reset forgets Clip activity when the video changes', () => {
  const tracker = createEffectClipTracker();
  const interval = { start_frame: 10, end_frame: 20 };

  tracker.consume('effect-1', 5, interval);
  tracker.reset();

  assert.deepEqual(tracker.consume('effect-1', 10, interval), {
    active: true,
    reentered: false,
  });
});
