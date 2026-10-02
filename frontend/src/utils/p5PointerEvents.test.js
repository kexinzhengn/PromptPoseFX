import assert from 'node:assert/strict';
import test from 'node:test';

import { dispatchCanvasMousePressed } from './p5PointerEvents.js';

test('a pointer press outside the p5 canvas keeps its browser default behavior', () => {
  const canvas = {};
  const input = {};
  const p = { canvas };
  let callCount = 0;

  const result = dispatchCanvasMousePressed(p, { target: input }, () => {
    callCount += 1;
    return false;
  });

  assert.equal(result, undefined);
  assert.equal(callCount, 0);
});

test('a pointer press on the p5 canvas reaches the canvas handler', () => {
  const canvas = {};
  const p = { canvas };

  const result = dispatchCanvasMousePressed(p, { target: canvas }, () => false);

  assert.equal(result, false);
});
