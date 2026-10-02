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

const { default: Toolbar } = await vite.ssrLoadModule('/src/components/Toolbar.jsx');

test('the active Pen is presented as a toggle that can be exited', () => {
  const html = renderToStaticMarkup(React.createElement(Toolbar, {
    skeletonVisible: true,
    onToggleSkeleton: () => {},
    pointToolActive: true,
    onTogglePointTool: () => {},
    pointToolDisabled: false,
    pathToolActive: false,
    onTogglePathTool: () => {},
  }));

  assert.match(html, /aria-label="Exit point tool"/);
  assert.match(html, /aria-pressed="true"/);
});

test('Draw Path is a separate toggle from the Point tool', () => {
  const html = renderToStaticMarkup(React.createElement(Toolbar, {
    skeletonVisible: true,
    onToggleSkeleton: () => {},
    pointToolActive: false,
    onTogglePointTool: () => {},
    pointToolDisabled: false,
    pathToolActive: true,
    onTogglePathTool: () => {},
  }));

  assert.match(html, /aria-label="Add fixed point"[^>]+aria-pressed="false"/);
  assert.match(html, /aria-label="Exit Path tool"[^>]+aria-pressed="true"/);
});

test('each tool exposes a concise visible tooltip', () => {
  const html = renderToStaticMarkup(React.createElement(Toolbar, {
    skeletonVisible: true,
    onToggleSkeleton: () => {},
    pointToolActive: false,
    onTogglePointTool: () => {},
    pointToolDisabled: false,
    pathToolActive: false,
    onTogglePathTool: () => {},
  }));

  assert.match(html, /data-tooltip="Show or hide pose guides"/);
  assert.match(html, /data-tooltip="Place a reference point"/);
  assert.match(html, /data-tooltip="Draw a reference path"/);
});
