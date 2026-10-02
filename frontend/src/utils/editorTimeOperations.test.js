import assert from 'node:assert/strict';
import test from 'node:test';

import {
  addTimeMarker,
  moveTimeMarker,
  removeTimeMarker,
  trimEffectClip,
} from './editorTimeOperations.js';


function createEditorState() {
  return {
    schema_version: 2,
    video_id: 'video-1',
    active_interval: { start_frame: 0, end_frame: 229 },
    points: [],
    markers: [],
    next_alias: { point: 1, marker: 1 },
  };
}


test('adding a Time Marker assigns the next alias without mutating EditorState', () => {
  const editorState = createEditorState();

  const updated = addTimeMarker(editorState, {
    id: 'marker-1',
    frame: 90,
  });

  assert.deepEqual(updated.markers, [
    { id: 'marker-1', alias: 't1', frame: 90 },
  ]);
  assert.equal(updated.next_alias.marker, 2);
  assert.deepEqual(editorState.markers, []);
  assert.equal(editorState.next_alias.marker, 1);
});


test('adding a Time Marker rejects a frame already used by this Effect', () => {
  const editorState = createEditorState();
  editorState.markers = [
    { id: 'marker-1', alias: 't1', frame: 90 },
  ];
  editorState.next_alias.marker = 2;

  assert.throws(
    () => addTimeMarker(editorState, { id: 'marker-2', frame: 90 }),
    /A Time Marker already exists at frame 90/,
  );
});


test('moving a Time Marker changes only its frame', () => {
  const editorState = createEditorState();
  editorState.markers = [
    { id: 'marker-1', alias: 't1', frame: 90 },
    { id: 'marker-2', alias: 't2', frame: 120 },
  ];
  editorState.next_alias.marker = 3;

  const updated = moveTimeMarker(editorState, 'marker-1', 105);

  assert.deepEqual(updated.markers, [
    { id: 'marker-1', alias: 't1', frame: 105 },
    { id: 'marker-2', alias: 't2', frame: 120 },
  ]);
  assert.equal(editorState.markers[0].frame, 90);
});


test('moving onto another Time Marker keeps the last legal EditorState', () => {
  const editorState = createEditorState();
  editorState.markers = [
    { id: 'marker-1', alias: 't1', frame: 90 },
    { id: 'marker-2', alias: 't2', frame: 120 },
  ];

  const updated = moveTimeMarker(editorState, 'marker-1', 120);

  assert.strictEqual(updated, editorState);
  assert.equal(updated.markers[0].frame, 90);
});


test('deleting a Time Marker preserves the monotonic alias counter', () => {
  const editorState = createEditorState();
  editorState.markers = [
    { id: 'marker-1', alias: 't1', frame: 60 },
    { id: 'marker-2', alias: 't2', frame: 90 },
    { id: 'marker-3', alias: 't3', frame: 120 },
  ];
  editorState.next_alias.marker = 4;

  const updated = removeTimeMarker(editorState, 'marker-2');

  assert.deepEqual(updated.markers, [
    { id: 'marker-1', alias: 't1', frame: 60 },
    { id: 'marker-3', alias: 't3', frame: 120 },
  ]);
  assert.equal(updated.next_alias.marker, 4);
  assert.equal(editorState.markers.length, 3);
});


test('trimming the Effect Clip start preserves Markers outside the new interval', () => {
  const editorState = createEditorState();
  editorState.markers = [
    { id: 'marker-1', alias: 't1', frame: 20 },
  ];

  const updated = trimEffectClip(editorState, 'start', 50);

  assert.deepEqual(updated.active_interval, {
    start_frame: 50,
    end_frame: 229,
  });
  assert.deepEqual(updated.markers, editorState.markers);
  assert.equal(editorState.active_interval.start_frame, 0);
});


test('trimming the Effect Clip end changes only the inclusive end frame', () => {
  const editorState = createEditorState();

  const updated = trimEffectClip(editorState, 'end', 180);

  assert.deepEqual(updated.active_interval, {
    start_frame: 0,
    end_frame: 180,
  });
  assert.deepEqual(editorState.active_interval, {
    start_frame: 0,
    end_frame: 229,
  });
});
