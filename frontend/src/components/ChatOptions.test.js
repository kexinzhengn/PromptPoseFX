import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import ChatOptions from './ChatOptions.js';

test('显示追问标题、选项名称和说明', () => {
  const html = renderToStaticMarkup(React.createElement(ChatOptions, {
    header: '你更喜欢哪种风格？',
    options: [
      { label: '火焰', description: '手腕产生火焰拖尾' },
      { label: '闪电', description: '双手之间出现闪电' },
    ],
  }));

  assert.match(html, /你更喜欢哪种风格/);
  assert.match(html, /火焰/);
  assert.match(html, /手腕产生火焰拖尾/);
  assert.match(html, /闪电/);
  assert.match(html, /双手之间出现闪电/);
  assert.equal((html.match(/<button/g) ?? []).length, 2);
});

test('没有选项时不渲染选项区域', () => {
  const html = renderToStaticMarkup(React.createElement(ChatOptions, {
    header: '请选择',
    options: [],
  }));

  assert.equal(html, '');
});

test('有选择回调时按钮可用', () => {
  const html = renderToStaticMarkup(React.createElement(ChatOptions, {
    options: [{ label: '火焰', description: '手腕产生火焰拖尾' }],
    onSelect: () => {},
  }));

  assert.doesNotMatch(html, / disabled=""/);
});

test('请求进行中时按钮禁用', () => {
  const html = renderToStaticMarkup(React.createElement(ChatOptions, {
    disabled: true,
    options: [{ label: '火焰', description: '手腕产生火焰拖尾' }],
    onSelect: () => {},
  }));

  assert.match(html, / disabled=""/);
});

test('点击按钮时返回对应选项', () => {
  const option = { id: 'option-123', label: 'Fire', description: 'A wrist-bound flame trail.' };
  let selected = null;
  const tree = ChatOptions({
    options: [option],
    onSelect: (value) => { selected = value; },
  });
  const button = tree.props.children[1];

  button.props.onClick();

  assert.equal(selected, option);
  assert.equal(selected.id, 'option-123');
});
