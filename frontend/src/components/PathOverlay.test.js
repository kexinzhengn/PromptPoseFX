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

const { default: PathOverlay } = await vite.ssrLoadModule('/src/components/PathOverlay.jsx');

test('saved Paths stay visible while drawing interaction is inactive', () => {
  const html = renderToStaticMarkup(React.createElement(PathOverlay, {
    active: false,
    visible: true,
    width: 200,
    height: 100,
    paths: [{
      id: 'path-1',
      alias: 'path1',
      points: [{ x: 0.1, y: 0.2 }, { x: 0.8, y: 0.7 }],
    }],
  }));

  assert.match(html, /data-name="saved-path"[^>]+data-path-id="path-1"/);
  assert.match(html, /points="20,20 160,70"/);
  assert.match(html, /data-name="path-contrast-outline"[^>]+stroke="rgba\(0,0,0,0.82\)"/);
  assert.match(html, /data-name="path-visible-stroke"[^>]+stroke="#89b4df"/);
  assert.match(html, />path1<\/text>/);
  assert.match(html, /data-active="false"/);
  assert.match(html, /pointer-events:none/);
});

test('Path controls follow the shared skeleton visibility toggle', () => {
  const html = renderToStaticMarkup(React.createElement(PathOverlay, {
    active: true,
    visible: false,
    width: 200,
    height: 100,
  }));

  assert.equal(html, '');
});

test('a selected Path exposes compact redraw and delete actions', () => {
  const html = renderToStaticMarkup(React.createElement(PathOverlay, {
    active: false,
    visible: true,
    width: 200,
    height: 100,
    selectedPathId: 'path-1',
    paths: [{
      id: 'path-1',
      alias: 'path1',
      points: [{ x: 0.1, y: 0.2 }, { x: 0.8, y: 0.7 }],
    }],
  }));

  assert.match(html, /data-selected="true"/);
  assert.match(html, /data-name="path-hit-area"/);
  assert.match(html, /aria-label="Redraw path1"/);
  assert.match(html, /aria-label="Delete path1"/);
});
