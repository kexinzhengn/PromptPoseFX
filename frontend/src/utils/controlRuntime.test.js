import assert from 'node:assert/strict';
import test from 'node:test';

import { createFrameControls } from '../../../shared/controlRuntime.mjs';


test('Fixed Point resolves from normalized video coordinates to pixels', () => {
  const controls = createFrameControls({
    bindings: {
      anchor: { type: 'point', id: 'point-1' },
    },
    editorState: {
      points: [
        {
          id: 'point-1',
          alias: 'p1',
          source: { type: 'fixed', x: 0.75, y: 0.25 },
        },
      ],
    },
    width: 640,
    height: 360,
    currentFrame: 10,
  });

  assert.deepEqual(controls.getPoint('anchor'), {
    x: 480,
    y: 90,
    vx: 0,
    vy: 0,
    speed: 0,
    valid: true,
    connected: true,
  });
});


test('Joint Point applies normalized offset while preserving Pose velocity', () => {
  const poseFrames = {
    4: { left_wrist: { x: 100, y: 200 } },
    5: { left_wrist: { x: 106, y: 208 } },
  };
  const controls = createFrameControls({
    bindings: {
      anchor: { type: 'point', id: 'point-1' },
    },
    editorState: {
      points: [
        {
          id: 'point-1',
          alias: 'p1',
          source: {
            type: 'joint',
            joint: 'left_wrist',
            offset_x: 0.1,
            offset_y: -0.2,
          },
        },
      ],
    },
    width: 800,
    height: 600,
    currentFrame: 5,
    getJointsAtFrame: (frame) => poseFrames[frame] || {},
  });

  assert.deepEqual(controls.getPoint('anchor'), {
    x: 186,
    y: 88,
    vx: 6,
    vy: 8,
    speed: 10,
    valid: true,
    connected: true,
  });
});


test('Joint Point reports missing Pose without reusing an older position', () => {
  const controls = createFrameControls({
    bindings: { anchor: { type: 'point', id: 'point-1' } },
    editorState: {
      points: [{
        id: 'point-1',
        alias: 'p1',
        source: {
          type: 'joint',
          joint: 'left_wrist',
          offset_x: 0.1,
          offset_y: -0.2,
        },
      }],
    },
    width: 800,
    height: 600,
    currentFrame: 5,
    getJointsAtFrame: (frame) => (
      frame === 4 ? { left_wrist: { x: 100, y: 200 } } : {}
    ),
  });

  assert.deepEqual(controls.getPoint('anchor'), {
    x: null,
    y: null,
    vx: 0,
    vy: 0,
    speed: 0,
    valid: false,
    connected: false,
  });
});


test('Joint Point can resolve its position at an explicit birth frame', () => {
  const poseFrames = {
    3: { left_wrist: { x: 90, y: 190 } },
    4: { left_wrist: { x: 100, y: 200 } },
    10: { left_wrist: { x: 300, y: 300 } },
  };
  const controls = createFrameControls({
    bindings: { anchor: { type: 'point', id: 'point-1' } },
    editorState: {
      points: [{
        id: 'point-1',
        alias: 'p1',
        source: {
          type: 'joint',
          joint: 'left_wrist',
          offset_x: 0.1,
          offset_y: -0.2,
        },
      }],
    },
    width: 800,
    height: 600,
    currentFrame: 10,
    getJointsAtFrame: (frame) => poseFrames[frame] || {},
  });

  assert.deepEqual(controls.getPoint('anchor', 4), {
    x: 180,
    y: 80,
    vx: 10,
    vy: 10,
    speed: Math.sqrt(200),
    valid: true,
    connected: true,
  });
});


test('Time Marker bindings always resolve their current persisted frames', () => {
  const editorState = {
    markers: [
      { id: 'marker-late', alias: 't1', frame: 120 },
      { id: 'marker-early', alias: 't2', frame: 60 },
    ],
  };
  const bindings = {
    start: { type: 'time_marker', id: 'marker-early' },
    end: { type: 'time_marker', id: 'marker-late' },
  };

  const controls = createFrameControls({
    bindings,
    editorState,
    width: 640,
    height: 360,
    currentFrame: 90,
  });
  const movedControls = createFrameControls({
    bindings,
    editorState: {
      markers: [
        { id: 'marker-late', alias: 't1', frame: 150 },
        { id: 'marker-early', alias: 't2', frame: 30 },
      ],
    },
    width: 640,
    height: 360,
    currentFrame: 90,
  });

  assert.deepEqual(controls.getTimeMarker('start'), { frame: 60 });
  assert.deepEqual(controls.getTimeMarker('end'), { frame: 120 });
  assert.deepEqual(movedControls.getTimeMarker('start'), { frame: 30 });
  assert.deepEqual(movedControls.getTimeMarker('end'), { frame: 150 });
});


test('Path exposes pixel points and samples position and tangent by arc length', () => {
  const controls = createFrameControls({
    bindings: {
      guide: { type: 'path', id: 'path-1' },
    },
    editorState: {
      paths: [{
        id: 'path-1',
        alias: 'path1',
        points: [
          { x: 0, y: 0 },
          { x: 0.5, y: 0 },
          { x: 0.5, y: 1 },
        ],
      }],
    },
    width: 200,
    height: 100,
    currentFrame: 10,
  });

  const path = controls.getPath('guide');

  assert.deepEqual(path.points, [
    { x: 0, y: 0 },
    { x: 100, y: 0 },
    { x: 100, y: 100 },
  ]);
  assert.equal(path.length, 200);
  assert.deepEqual(path.sample(0), {
    x: 0,
    y: 0,
    tangentX: 1,
    tangentY: 0,
    valid: true,
  });
  assert.deepEqual(path.sample(0.25), {
    x: 50,
    y: 0,
    tangentX: 1,
    tangentY: 0,
    valid: true,
  });
  assert.deepEqual(path.sample(0.75), {
    x: 100,
    y: 50,
    tangentX: 0,
    tangentY: 1,
    valid: true,
  });
  assert.deepEqual(path.sample(1), {
    x: 100,
    y: 100,
    tangentX: 0,
    tangentY: 1,
    valid: true,
  });
});


test('Path binding rejects a missing persisted control', () => {
  assert.throws(
    () => createFrameControls({
      bindings: { guide: { type: 'path', id: 'missing-path' } },
      editorState: { paths: [] },
      width: 200,
      height: 100,
      currentFrame: 0,
    }),
    /Path binding references a missing control: guide/,
  );
});
