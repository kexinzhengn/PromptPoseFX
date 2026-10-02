import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import PointReferenceStrip from './PointReferenceStrip.js';


test('没有 Point 或 Path 时不占用输入区域空间', () => {
  const html = renderToStaticMarkup(React.createElement(PointReferenceStrip, {
    points: [],
  }));

  assert.equal(html, '');
});

test('只显示可点选的 Point 名称和当前选择', () => {
  const html = renderToStaticMarkup(React.createElement(PointReferenceStrip, {
    points: [
      {
        id: 'joint-1',
        alias: 'p1',
        source: { type: 'joint', joint: 'left_wrist', offset_x: 0, offset_y: 0 },
      },
      {
        id: 'fixed-1',
        alias: 'p2',
        source: { type: 'fixed', x: 0.25, y: 0.5 },
      },
    ],
    selectedPointId: 'fixed-1',
  }));

  assert.match(html, />p1<\/button>/);
  assert.match(html, />p2<\/button>/);
  assert.match(html, /aria-label="Select p2" aria-pressed="true"/);
  assert.doesNotMatch(html, /Left wrist|Fixed/);
});

test('点击名称使用 Stable ID 选择对应 Point', () => {
  let selected = null;
  const tree = PointReferenceStrip({
    points: [{
      id: 'point-stable-id',
      alias: 'p1',
      source: { type: 'fixed', x: 0.25, y: 0.5 },
    }],
    onSelectPoint: (pointId) => { selected = pointId; },
  });

  tree.props.children[0].props.onClick();

  assert.equal(selected, 'point-stable-id');
});

test('Path 名称显示并使用 Stable ID 选择对应 Path', () => {
  let selected = null;
  const tree = PointReferenceStrip({
    paths: [{
      id: 'path-stable-id',
      alias: 'path1',
      points: [{ x: 0.1, y: 0.2 }, { x: 0.7, y: 0.8 }],
    }],
    selectedPathId: 'path-stable-id',
    onSelectPath: (pathId) => { selected = pathId; },
  });

  assert.equal(tree.props.children[0].props['data-reference-type'], 'path');
  assert.equal(tree.props.children[0].props['aria-pressed'], true);
  tree.props.children[0].props.onClick();

  assert.equal(selected, 'path-stable-id');
});
