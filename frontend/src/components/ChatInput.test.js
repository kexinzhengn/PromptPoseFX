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

const { default: ChatInput } = await vite.ssrLoadModule('/src/components/ChatInput.jsx');

function renderChatInput(points = [], paths = []) {
  return renderToStaticMarkup(React.createElement(ChatInput, {
    onSend: async () => true,
    isLoading: false,
    hasVideo: true,
    points,
    paths,
  }));
}

test('Chat Input keeps the same fixed size with or without Point references', () => {
  const withoutPoints = renderChatInput();
  const withPoints = renderChatInput([
    { id: 'point-1', alias: 'p1', source: { type: 'fixed', x: 0.2, y: 0.3 } },
    { id: 'point-2', alias: 'p2', source: { type: 'fixed', x: 0.7, y: 0.6 } },
  ]);

  const fixedSize = /data-name="chat-input"[^>]+height:96px/;
  assert.match(withoutPoints, fixedSize);
  assert.match(withPoints, fixedSize);
});

test('Point references render inside the fixed context row', () => {
  const html = renderChatInput([
    { id: 'point-1', alias: 'p1', source: { type: 'fixed', x: 0.2, y: 0.3 } },
  ]);

  assert.match(
    html,
    /data-name="chat-input-context"[^>]+height:40px[^>]*>.*data-name="editor-reference-strip"/,
  );
});

test('Path references render inside the same fixed context row', () => {
  const html = renderChatInput([], [{
    id: 'path-1',
    alias: 'path1',
    points: [{ x: 0.1, y: 0.2 }, { x: 0.8, y: 0.7 }],
  }]);

  assert.match(html, /data-reference-type="path"[^>]+aria-label="Select path1"/);
  assert.match(html, />path1<\/button>/);
});
