import assert from 'node:assert/strict';
import test from 'node:test';

import {
  appendDraftPathPoint,
  addDrawnPath,
  getPathDeletionError,
  removePath,
  replacePathPoints,
} from './editorPathOperations.js';


test('draft Path sampling drops pointer noise while preserving meaningful movement', () => {
  let points = [];
  points = appendDraftPathPoint(points, { x: 0.1, y: 0.2 }, 200, 100);
  const firstSample = points;
  const unchanged = appendDraftPathPoint(points, { x: 0.11, y: 0.2 }, 200, 100);
  points = appendDraftPathPoint(unchanged, { x: 0.15, y: 0.2 }, 200, 100);

  assert.strictEqual(unchanged, firstSample);
  assert.deepEqual(points, [
    { x: 0.1, y: 0.2 },
    { x: 0.15, y: 0.2 },
  ]);
});


test('adding a drawn Path assigns the next alias without mutating EditorState', () => {
  const editorState = {
    paths: [],
    next_alias: { point: 1, marker: 1, path: 3 },
  };

  const result = addDrawnPath(editorState, {
    id: 'path-stable-id',
    points: [{ x: 0.1, y: 0.2 }, { x: 0.8, y: 0.7 }],
  });

  assert.deepEqual(result.paths, [{
    id: 'path-stable-id',
    alias: 'path3',
    points: [{ x: 0.1, y: 0.2 }, { x: 0.8, y: 0.7 }],
  }]);
  assert.equal(result.next_alias.path, 4);
  assert.deepEqual(editorState.paths, []);
  assert.equal(editorState.next_alias.path, 3);
});


test('deleting a Path preserves other Paths and never reuses its alias', () => {
  const editorState = {
    paths: [
      { id: 'path-1', alias: 'path1', points: [{ x: 0, y: 0 }, { x: 1, y: 1 }] },
      { id: 'path-2', alias: 'path2', points: [{ x: 0, y: 1 }, { x: 1, y: 0 }] },
    ],
    next_alias: { point: 1, marker: 1, path: 3 },
  };

  const result = removePath(editorState, 'path-1');

  assert.deepEqual(result.paths.map((path) => path.id), ['path-2']);
  assert.equal(result.next_alias.path, 3);
  assert.equal(editorState.paths.length, 2);
});


test('a Path used by the current Effect is blocked before optimistic deletion', () => {
  assert.equal(getPathDeletionError('path-1', []), null);
  assert.equal(
    getPathDeletionError('path-1', ['path-1']),
    'This Path cannot be deleted because the current Effect uses it.',
  );
});


test('redrawing replaces only points while preserving Path identity', () => {
  const editorState = {
    paths: [{
      id: 'path-1',
      alias: 'path1',
      points: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
    }],
  };

  const result = replacePathPoints(editorState, 'path-1', [
    { x: 0.2, y: 0.8 },
    { x: 0.7, y: 0.3 },
  ]);

  assert.deepEqual(result.paths[0], {
    id: 'path-1',
    alias: 'path1',
    points: [{ x: 0.2, y: 0.8 }, { x: 0.7, y: 0.3 }],
  });
  assert.deepEqual(editorState.paths[0].points, [{ x: 0, y: 0 }, { x: 1, y: 1 }]);
});
