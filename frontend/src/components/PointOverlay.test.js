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

const { default: PointOverlay } = await vite.ssrLoadModule('/src/components/PointOverlay.jsx');


const editorState = {
  points: [{
    id: 'fixed-1',
    alias: 'p1',
    source: { type: 'fixed', x: 0.25, y: 0.5 },
  }],
};

function renderOverlay(props = {}) {
  return renderToStaticMarkup(React.createElement(PointOverlay, {
    editorState,
    width: 640,
    height: 360,
    currentFrame: 0,
    getJointsAtFrame: () => ({}),
    visible: true,
    ...props,
  }));
}

test('hiding skeleton controls also hides Point controls without changing their data', () => {
  const html = renderOverlay({ visible: false });

  assert.equal(html, '');
  assert.equal(editorState.points.length, 1);
});

test('a selected Point exposes an explicit delete control', () => {
  const selectedHtml = renderOverlay({ selectedPointId: 'fixed-1' });
  const unselectedHtml = renderOverlay({ selectedPointId: null });

  assert.match(selectedHtml, /aria-label="Delete p1"/);
  assert.doesNotMatch(unselectedHtml, /aria-label="Delete p1"/);
});

test('Fixed and Joint Points use distinct color and shape encodings', () => {
  const html = renderOverlay({
    editorState: {
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
    },
    getJointsAtFrame: () => ({
      left_wrist: { x: 320, y: 180, vx: 0, vy: 0, speed: 0 },
    }),
  });

  assert.match(html, /data-point-kind="fixed"[\s\S]+?data-name="point-marker"[^>]+background-color:#b69a76[^>]+border-radius:4px/);
  assert.match(html, /data-point-kind="joint"[\s\S]+?data-name="point-marker"[^>]+background-color:#7a94b3[^>]+border-radius:9999px/);
  assert.match(html, /title="p1 · Fixed — drag to move"/);
  assert.match(html, /title="p2 · Joint — drag to move"/);
});

test('a created Joint Point has a large hit target and names its bound joint on hover', () => {
  const html = renderOverlay({
    editorState: {
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
    },
    getJointsAtFrame: () => ({
      left_wrist: { x: 320, y: 180, vx: 0, vy: 0, speed: 0 },
    }),
  });

  assert.match(html, /data-point-kind="joint"[^>]+width:32px[^>]+height:32px/);
  assert.match(html, /role="tooltip"/);
  assert.match(html, />Left Wrist<\/span>/);
});
