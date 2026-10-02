import assert from 'node:assert/strict';
import { after, test } from 'node:test';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const vite = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
});

after(async () => {
  await vite.close();
});

const {
  default: Timeline,
  EffectDeleteButton,
  TimelineTrackRow,
} = await vite.ssrLoadModule('/src/components/Timeline.jsx');
const { getTimelineFrame } = await vite.ssrLoadModule('/src/utils/timelineCoordinates.js');


function renderTimeline(overrides = {}) {
  return renderToStaticMarkup(React.createElement(Timeline, {
    effects: [{ id: 'effect-1', name: 'Timed Glow', visible: true }],
    pendingEffects: [],
    editorWorkspaces: {
      'effect-1': {
        editorState: {
          active_interval: { start_frame: 20, end_frame: 180 },
          markers: [{ id: 'marker-1', alias: 't1', frame: 90 }],
        },
      },
    },
    selectedEffectId: 'effect-1',
    runningEffectIds: [],
    totalFrames: 230,
    currentFrame: 90,
    isPlaying: false,
    ...overrides,
  }));
}


test('Timeline renders the persisted Effect Clip and Time Markers', () => {
  const html = renderTimeline();

  assert.match(
    html,
    /data-name="timeline-effect-clip"[^>]+data-start-frame="20"[^>]+data-end-frame="180"/,
  );
  assert.match(
    html,
    /data-name="timeline-marker"[^>]+data-marker-id="marker-1"[^>]+aria-label="t1 at frame 90"/,
  );
  assert.match(
    html,
    /data-name="timeline-marker-label"[^>]+>t1<\/span>/,
  );
  assert.doesNotMatch(html, /data-name="timeline-marker-label"[^>]+>[^<]*Frame/);
  assert.doesNotMatch(html, /timeline-keyframe/);
});


test('Timeline maps its full track width to the first and final video frames', () => {
  const rect = { left: 100, width: 500 };

  assert.equal(getTimelineFrame(100, rect, 230), 0);
  assert.equal(getTimelineFrame(600, rect, 230), 229);
  assert.equal(getTimelineFrame(350, rect, 230), 115);
  assert.equal(getTimelineFrame(50, rect, 230), 0);
  assert.equal(getTimelineFrame(650, rect, 230), 229);
});


test('Timeline only exposes Marker editing on the selected Effect track', () => {
  const html = renderTimeline({
    effects: [
      { id: 'effect-1', name: 'Timed Glow', visible: true },
      { id: 'effect-2', name: 'Foot Trail', visible: true },
    ],
    editorWorkspaces: {
      'effect-1': {
        editorState: {
          active_interval: { start_frame: 20, end_frame: 180 },
          markers: [{ id: 'marker-1', alias: 't1', frame: 90 }],
        },
      },
      'effect-2': {
        editorState: {
          active_interval: { start_frame: 0, end_frame: 229 },
          markers: [{ id: 'marker-2', alias: 't1', frame: 120 }],
        },
      },
    },
  });

  assert.match(
    html,
    /data-marker-id="marker-1"[^>]+data-editable="true"/,
  );
  assert.match(
    html,
    /data-marker-id="marker-2"[^>]+data-editable="false"[^>]+disabled=""[^>]+pointer-events:none/,
  );
  assert.equal(
    (html.match(/data-name="timeline-marker-label"/g) || []).length,
    1,
  );
});


test('Timeline exposes both Clip trim handles only on the selected track', () => {
  const html = renderTimeline({
    effects: [
      { id: 'effect-1', name: 'Timed Glow', visible: true },
      { id: 'effect-2', name: 'Foot Trail', visible: true },
    ],
    editorWorkspaces: {
      'effect-1': {
        editorState: {
          active_interval: { start_frame: 20, end_frame: 180 },
          markers: [],
        },
      },
      'effect-2': {
        editorState: {
          active_interval: { start_frame: 40, end_frame: 160 },
          markers: [],
        },
      },
    },
  });

  assert.match(
    html,
    /data-name="timeline-clip-handle"[^>]+data-effect-id="effect-1"[^>]+data-edge="start"/,
  );
  assert.match(
    html,
    /data-name="timeline-clip-handle"[^>]+data-effect-id="effect-1"[^>]+data-edge="end"/,
  );
  assert.doesNotMatch(
    html,
    /data-name="timeline-clip-handle"[^>]+data-effect-id="effect-2"/,
  );
});


test('Timeline keeps horizontal overflow out of the playback boundary', () => {
  const html = renderTimeline();

  assert.match(
    html,
    /data-name="timeline-track-viewport"[^>]+class="[^"]*overflow-x-hidden[^"]*"/,
  );
  assert.match(
    html,
    /data-name="timeline-tracks"[^>]+min-width:0/,
  );
});


test('Timeline renders a compact single-line frame position', () => {
  const html = renderTimeline({ currentFrame: 9, totalFrames: 230 });

  assert.match(
    html,
    /data-name="timeline-frame-label"[^>]+white-space:nowrap[^>]*>0009 \/ 0230<\/span>/,
  );
  assert.doesNotMatch(html, />Frame 0009 \/ 230<\/span>/);
});

test('Timeline puts full-width transport and creation controls above the tracks', () => {
  const html = renderTimeline();

  assert.ok(html.indexOf('data-name="timeline-controls"') < html.indexOf('data-name="timeline-track-viewport"'));
  assert.match(html, /aria-label="Previous frame"/);
  assert.match(html, /aria-label="Next frame"/);
  assert.match(html, /data-name="timeline-scrubber"/);
  assert.match(
    html,
    /data-name="timeline-scrubber"[^>]+role="slider"[^>]+aria-valuemin="0"[^>]+aria-valuemax="229"[^>]+aria-valuenow="90"/,
  );
  assert.match(html, />\+ Marker<\/button>/);
  assert.match(html, />\+ Effect layer<\/button>/);
  assert.doesNotMatch(html, /data-name="timeline-add-layer"/);
});

test('Timeline exposes keyboard-focusable Effect selection controls', () => {
  const html = renderTimeline();

  assert.match(
    html,
    /class="editor-layer-select"[^>]+aria-label="Select Timed Glow"[^>]+aria-pressed="true"/,
  );
});


test('Timeline track rows expose Effect selection at the clicked timeline position', () => {
  const html = renderTimeline({
    effects: [
      { id: 'effect-1', name: 'Timed Glow', visible: true },
      { id: 'effect-2', name: 'Foot Trail', visible: true },
    ],
  });

  assert.match(
    html,
    /data-name="timeline-track"[^>]+data-effect-id="effect-2"[^>]+data-selects-effect="true"/,
  );

  let selectedEffectId = null;
  const row = TimelineTrackRow({
    effectId: 'effect-2',
    onSelectEffect: (effectId) => { selectedEffectId = effectId; },
    children: null,
  });
  row.props.onPointerDownCapture();

  assert.equal(selectedEffectId, 'effect-2');
});


test('Pending Effect rows expose deletion unless generation is running', () => {
  const html = renderTimeline({
    pendingEffects: [
      { id: 'pending-1', name: 'Pending' },
      { id: 'pending-2', name: 'Pending' },
    ],
    runningEffectIds: ['pending-2'],
  });

  assert.match(
    html,
    /data-name="timeline-delete-pending-effect"[^>]+data-effect-id="pending-1"(?![^>]+disabled)/,
  );
  assert.match(
    html,
    /data-name="timeline-delete-pending-effect"[^>]+data-effect-id="pending-2"[^>]+disabled=""/,
  );

  let deletedEffectId = null;
  let propagationStopped = false;
  const button = EffectDeleteButton({
    effectId: 'pending-1',
    name: 'Pending',
    pending: true,
    running: false,
    onDeleteEffect: (effectId) => { deletedEffectId = effectId; },
  });
  button.props.onClick({ stopPropagation: () => { propagationStopped = true; } });

  assert.equal(deletedEffectId, 'pending-1');
  assert.equal(propagationStopped, true);
});
