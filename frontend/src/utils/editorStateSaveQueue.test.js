import assert from 'node:assert/strict';
import test from 'node:test';

import { createEditorStateSaveQueue } from './editorStateSaveQueue.js';


test('serializes saves and never applies an older Point position over a newer move', async () => {
  const requests = [];
  const resolvers = [];
  const applied = [];
  const queue = createEditorStateSaveQueue({
    save: (effectId, expectedRevision, editorState) => new Promise((resolve) => {
      requests.push({ effectId, expectedRevision, editorState });
      resolvers.push(resolve);
    }),
    onSaved: (result) => applied.push(result),
  });
  const firstState = { points: [{ id: 'point-1', x: 0.2, y: 0.8 }] };
  const latestState = { points: [{ id: 'point-1', x: 0.9, y: 0.1 }] };

  queue.enqueue('effect-1', 0, firstState);
  queue.enqueue('effect-1', 0, latestState);

  assert.equal(requests.length, 1);
  assert.deepEqual(requests[0], {
    effectId: 'effect-1',
    expectedRevision: 0,
    editorState: firstState,
  });

  resolvers[0]({
    effect_id: 'effect-1',
    editor_revision: 1,
    editor_state: firstState,
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(applied, []);
  assert.equal(requests.length, 2);
  assert.deepEqual(requests[1], {
    effectId: 'effect-1',
    expectedRevision: 1,
    editorState: latestState,
  });

  resolvers[1]({
    effect_id: 'effect-1',
    editor_revision: 2,
    editor_state: latestState,
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(applied, [{
    effect_id: 'effect-1',
    editor_revision: 2,
    editor_state: latestState,
  }]);
});


test('cancelAll ignores a save response from the previous video', async () => {
  let resolveSave;
  const applied = [];
  const queue = createEditorStateSaveQueue({
    save: () => new Promise((resolve) => { resolveSave = resolve; }),
    onSaved: (result) => applied.push(result),
  });

  queue.enqueue('effect-1', 0, { points: [] });
  queue.cancelAll();
  resolveSave({
    effect_id: 'effect-1',
    editor_revision: 1,
    editor_state: { points: [] },
  });
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(applied, []);
});


test('waitForIdle resolves only after the latest queued editor state is saved', async () => {
  const resolvers = [];
  const queue = createEditorStateSaveQueue({
    save: () => new Promise((resolve) => { resolvers.push(resolve); }),
  });
  let settledRevision = null;

  queue.enqueue('effect-1', 3, { points: [{ id: 'point-1', x: 0.2 }] });
  queue.enqueue('effect-1', 3, { points: [{ id: 'point-1', x: 0.8 }] });
  const waiting = queue.waitForIdle('effect-1').then((revision) => {
    settledRevision = revision;
  });

  resolvers[0]({ editor_revision: 4, editor_state: {} });
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(settledRevision, null);

  resolvers[1]({ editor_revision: 5, editor_state: {} });
  await waiting;

  assert.equal(settledRevision, 5);
});


test('waitForIdle rejects when the pending editor state cannot be saved', async () => {
  const saveError = new Error('save failed');
  const queue = createEditorStateSaveQueue({
    save: () => Promise.reject(saveError),
  });

  queue.enqueue('effect-1', 0, { points: [] });

  await assert.rejects(queue.waitForIdle('effect-1'), saveError);
});

test('cancel ignores an in-flight save result for a deleted Effect', async () => {
  let finishSave;
  const saved = [];
  const queue = createEditorStateSaveQueue({
    save: () => new Promise((resolve) => { finishSave = resolve; }),
    onSaved: (result) => saved.push(result),
  });

  queue.enqueue('effect-1', 1, { revision: 1 });
  queue.cancel('effect-1');
  finishSave({ effect_id: 'effect-1', editor_revision: 2 });
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(saved, []);
});
