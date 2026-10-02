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

const { default: JointHoverLabel } = await vite.ssrLoadModule('/src/components/JointHoverLabel.jsx');
const {
  findNearestJoint,
  resolvePointCreation,
} = await vite.ssrLoadModule('/src/utils/jointPicker.js');

test('overlapping joint hit areas select the joint nearest to the pointer', () => {
  const nearest = findNearestJoint({
    left_wrist: { x: 100, y: 100 },
    left_index: { x: 112, y: 100 },
    missing_joint: { x: 0, y: 0 },
  }, 109, 100, 18);

  assert.equal(nearest?.name, 'left_index');
  assert.equal(findNearestJoint({ nose: { x: 50, y: 50 } }, 80, 80, 18), null);
});

test('point creation prefers a nearby Pose joint over a Fixed Point', () => {
  const joints = { left_wrist: { x: 100, y: 100 } };

  assert.deepEqual(resolvePointCreation({
    joints,
    x: 104,
    y: 100,
    addMode: true,
  }), { type: 'joint', joint: 'left_wrist' });
  assert.deepEqual(resolvePointCreation({
    joints,
    x: 104,
    y: 100,
    addMode: false,
  }), { type: 'joint', joint: 'left_wrist' });
});

test('empty canvas creates a Fixed Point only while the Point tool is active', () => {
  const joints = { left_wrist: { x: 100, y: 100 } };

  assert.deepEqual(resolvePointCreation({
    joints,
    x: 220,
    y: 180,
    addMode: true,
  }), { type: 'fixed' });
  assert.equal(resolvePointCreation({
    joints,
    x: 220,
    y: 180,
    addMode: false,
  }), null);
});

test('hover feedback presents a readable Pose joint name', () => {
  const html = renderToStaticMarkup(React.createElement(JointHoverLabel, {
    joint: { name: 'left_wrist', x: 100, y: 60 },
    width: 640,
    height: 360,
  }));

  assert.match(html, /Left Wrist/);
  assert.match(html, /role="tooltip"/);
});
