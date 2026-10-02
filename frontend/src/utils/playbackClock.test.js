import test from 'node:test';
import assert from 'node:assert/strict';

import { createPlaybackClock } from './playbackClock.js';


function createFakeAnimationFrames() {
  let nextId = 1;
  const callbacks = new Map();

  return {
    request(callback) {
      const id = nextId++;
      callbacks.set(id, callback);
      return id;
    },
    cancel(id) {
      callbacks.delete(id);
    },
    fire(timestamp) {
      const pending = [...callbacks.values()];
      callbacks.clear();
      for (const callback of pending) callback(timestamp);
    },
  };
}


test('playback jumps directly to the frame implied by elapsed time', () => {
  const animationFrames = createFakeAnimationFrames();
  const frameEvents = [];
  const clock = createPlaybackClock({
    fps: 30,
    totalFrames: 100,
    onFrame: (event) => frameEvents.push(event),
    requestFrame: animationFrames.request,
    cancelFrame: animationFrames.cancel,
  });

  clock.seek(10);
  clock.play();
  animationFrames.fire(1_000);
  animationFrames.fire(1_100);

  assert.deepEqual(frameEvents.map(({ currentFrame, deltaFrames, discontinuity }) => ({
    currentFrame,
    deltaFrames,
    discontinuity,
  })), [
    { currentFrame: 10, deltaFrames: 0, discontinuity: 'seek' },
    { currentFrame: 13, deltaFrames: 3, discontinuity: 'none' },
  ]);
  assert.equal(clock.getSnapshot().currentFrame, 13);
});


test('playback loops from the final frame using the same elapsed-time calculation', () => {
  const animationFrames = createFakeAnimationFrames();
  const frameEvents = [];
  const clock = createPlaybackClock({
    fps: 30,
    totalFrames: 100,
    onFrame: (event) => frameEvents.push(event),
    requestFrame: animationFrames.request,
    cancelFrame: animationFrames.cancel,
  });

  clock.seek(98);
  clock.play();
  animationFrames.fire(2_000);
  animationFrames.fire(2_100);

  assert.deepEqual(frameEvents.map(({ currentFrame, deltaFrames, discontinuity }) => ({
    currentFrame,
    deltaFrames,
    discontinuity,
  })), [
    { currentFrame: 98, deltaFrames: 0, discontinuity: 'seek' },
    { currentFrame: 1, deltaFrames: 0, discontinuity: 'loop' },
  ]);
});


test('pause freezes playback and resume starts from the paused frame', () => {
  const animationFrames = createFakeAnimationFrames();
  const renderedFrames = [];
  const clock = createPlaybackClock({
    fps: 30,
    totalFrames: 100,
    onFrame: ({ currentFrame }) => renderedFrames.push(currentFrame),
    requestFrame: animationFrames.request,
    cancelFrame: animationFrames.cancel,
  });

  clock.play();
  animationFrames.fire(3_000);
  animationFrames.fire(3_100);
  clock.pause();
  animationFrames.fire(3_500);
  clock.play();
  animationFrames.fire(4_000);
  animationFrames.fire(4_100);

  assert.deepEqual(renderedFrames, [3, 6]);
  assert.equal(clock.getSnapshot().isPlaying, true);
});
