import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { parseEffectFromCode, getDefaultParams } from './effectParser.js';
import { createEffectFrameTracker } from './effectFrameTracker.js';

const FIXTURE_URL = new URL(
  './fixtures/sequentialEffect.txt',
  import.meta.url,
);

function loadEffect() {
  const code = readFileSync(FIXTURE_URL, 'utf8');
  return {
    effect: parseEffectFromCode(code),
    params: getDefaultParams(code),
  };
}

function frameEvent(currentFrame, sequence, overrides = {}) {
  return {
    currentFrame,
    discontinuity: 'none',
    sequence,
    continuityId: 0,
    continuityReason: 'none',
    ...overrides,
  };
}

function render(effect, params, tracker, event) {
  const commands = [];
  const sketch = {
    push() {},
    pop() {},
    noStroke() {},
    fill() {},
    ellipse: (...args) => commands.push(['ellipse', ...args]),
  };
  effect.display(sketch, {
    joints: {},
    currentFrame: event.currentFrame,
    width: 320,
    height: 240,
    getJointHistory: () => [],
    ...tracker.consume(effect, event),
  }, params);
  return commands;
}

test('顺序帧推进状态，被动重绘保持相同结果', () => {
  const tracker = createEffectFrameTracker();
  const { effect, params } = loadEffect();
  const firstFrame = frameEvent(0, 1);

  const initial = render(effect, params, tracker, firstFrame);
  const passive = render(effect, params, tracker, firstFrame);
  const skipped = render(effect, params, tracker, frameEvent(3, 2));

  assert.deepEqual(initial, [['ellipse', 160, 120, 11, 1]]);
  assert.deepEqual(passive, initial);
  assert.deepEqual(skipped, [['ellipse', 160, 120, 14, 2]]);
});

test('隐藏期间漏过的帧由 deltaFrames 补偿，seek 后状态重置', () => {
  const tracker = createEffectFrameTracker();
  const { effect, params } = loadEffect();

  render(effect, params, tracker, frameEvent(1, 1));
  const reopened = render(effect, params, tracker, frameEvent(4, 4));
  const afterSeek = render(effect, params, tracker, frameEvent(0, 5, {
    discontinuity: 'seek',
    continuityId: 1,
    continuityReason: 'seek',
  }));

  assert.deepEqual(reopened, [['ellipse', 160, 120, 14, 2]]);
  assert.deepEqual(afterSeek, [['ellipse', 160, 120, 11, 1]]);
});
