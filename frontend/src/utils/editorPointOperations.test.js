import assert from 'node:assert/strict';
import test from 'node:test';

import {
  addJointPoint,
  getPointDeletionError,
  movePointToPosition,
  removePoint,
} from './editorPointOperations.js';


test('clicking a Pose joint appends a zero-offset Joint Point with the next alias', () => {
  const editorState = {
    schema_version: 2,
    video_id: 'video-1',
    active_interval: { start_frame: 0, end_frame: 99 },
    points: [{
      id: 'fixed-1',
      alias: 'p1',
      source: { type: 'fixed', x: 0.25, y: 0.5 },
    }],
    markers: [],
    next_alias: { point: 2, marker: 1 },
  };

  const updated = addJointPoint(editorState, {
    id: 'joint-1',
    joint: 'left_wrist',
  });

  assert.deepEqual(updated.points[1], {
    id: 'joint-1',
    alias: 'p2',
    source: {
      type: 'joint',
      joint: 'left_wrist',
      offset_x: 0,
      offset_y: 0,
    },
  });
  assert.equal(updated.next_alias.point, 3);
  assert.equal(editorState.points.length, 1);
});


test('dragging a Joint Point updates offset without changing its joint identity', () => {
  const editorState = {
    points: [{
      id: 'joint-1',
      alias: 'p1',
      source: {
        type: 'joint',
        joint: 'left_wrist',
        offset_x: 0,
        offset_y: 0,
      },
    }],
  };

  const updated = movePointToPosition(editorState, {
    pointId: 'joint-1',
    position: { x: 0.75, y: 0.25 },
    jointPosition: { x: 0.5, y: 0.5 },
  });

  assert.deepEqual(updated.points[0], {
    id: 'joint-1',
    alias: 'p1',
    source: {
      type: 'joint',
      joint: 'left_wrist',
      offset_x: 0.25,
      offset_y: -0.25,
    },
  });
  assert.equal(editorState.points[0].source.offset_x, 0);
});


test('dragging a Fixed Point updates its normalized video position', () => {
  const editorState = {
    points: [{
      id: 'fixed-1',
      alias: 'p1',
      source: { type: 'fixed', x: 0.25, y: 0.5 },
    }],
  };

  const updated = movePointToPosition(editorState, {
    pointId: 'fixed-1',
    position: { x: 0.75, y: 0.25 },
  });

  assert.deepEqual(updated.points[0].source, {
    type: 'fixed',
    x: 0.75,
    y: 0.25,
  });
});


test('deleting a selected Point preserves other Points and does not reuse its alias', () => {
  const editorState = {
    points: [
      {
        id: 'fixed-1',
        alias: 'p1',
        source: { type: 'fixed', x: 0.25, y: 0.5 },
      },
      {
        id: 'joint-1',
        alias: 'p2',
        source: {
          type: 'joint',
          joint: 'left_wrist',
          offset_x: 0,
          offset_y: 0,
        },
      },
    ],
    next_alias: { point: 3, marker: 1 },
  };

  const updated = removePoint(editorState, 'fixed-1');

  assert.deepEqual(updated.points, [editorState.points[1]]);
  assert.equal(updated.next_alias.point, 3);
  assert.equal(editorState.points.length, 2);
});


test('a Point used by the current Effect is blocked before optimistic deletion', () => {
  assert.equal(
    getPointDeletionError('point-1', ['point-1']),
    'This Point cannot be deleted because the current Effect uses it.',
  );
  assert.equal(getPointDeletionError('point-2', ['point-1']), null);
});
