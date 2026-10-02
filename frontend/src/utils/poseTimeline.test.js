import assert from 'node:assert/strict';
import test from 'node:test';

import { PoseTimeline } from './poseTimeline.js';

const LEFT_WRIST_INDEX = 15;

function makeLandmarks(x, y) {
  const landmarks = Array.from({ length: 33 }, () => [0, 0]);
  landmarks[LEFT_WRIST_INDEX] = [x, y];
  return landmarks;
}

test('返回从视频开头截断的关节历史，并计算每帧速度', () => {
  const timeline = new PoseTimeline({
    frame_number: 3,
    0: makeLandmarks(10, 20),
    1: makeLandmarks(13, 24),
    2: makeLandmarks(19, 32),
  });

  assert.deepEqual(timeline.getJointsAtFrame(1).left_wrist, { x: 13, y: 24 });
  assert.deepEqual(timeline.getJointHistory('left_wrist', 1, 10), [
    {
      frame: 0, x: 10, y: 20,
      vx: 0, vy: 0, speed: 0,
      valid: true, connected: false,
    },
    {
      frame: 1, x: 13, y: 24,
      vx: 3, vy: 4, speed: 5,
      valid: true, connected: true,
    },
  ]);
});

test('姿态缺失时断开轨迹，未知关节返回空历史', () => {
  const timeline = new PoseTimeline({
    frame_number: 3,
    0: makeLandmarks(10, 20),
    1: makeLandmarks(0, 0),
    2: makeLandmarks(30, 40),
  });

  const history = timeline.getJointHistory('left_wrist', 2, 3);

  assert.deepEqual(history[1], {
    frame: 1, x: null, y: null,
    vx: 0, vy: 0, speed: 0,
    valid: false, connected: false,
  });
  assert.deepEqual(history[2], {
    frame: 2, x: 30, y: 40,
    vx: 0, vy: 0, speed: 0,
    valid: true, connected: false,
  });
  assert.deepEqual(timeline.getJointHistory('unknown_joint', 2, 3), []);
});

test('关节历史最多返回 120 帧', () => {
  const raw = { frame_number: 131 };
  for (let frame = 0; frame <= 130; frame += 1) {
    raw[frame] = makeLandmarks(10 + frame, 20 + frame);
  }
  const timeline = new PoseTimeline(raw);

  const history = timeline.getJointHistory('left_wrist', 130, 999);

  assert.equal(history.length, 120);
  assert.equal(history[0].frame, 11);
  assert.equal(history.at(-1).frame, 130);
});
