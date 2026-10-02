import assert from 'node:assert/strict';
import test from 'node:test';

import { createEffectWorkspace, createRun, patchEffect, replaceEditorState } from './api.js';

test('createRun sends a stable selected option ID', async () => {
  const originalFetch = globalThis.fetch;
  let requestBody = null;
  globalThis.fetch = async (_url, options) => {
    requestBody = JSON.parse(options.body);
    return {
      ok: true,
      json: async () => ({ run_id: 'run-1', thread_id: 'workspace-1' }),
    };
  };

  try {
    await createRun({
      video_id: 'video-1',
      user_input: 'Orbiting rings',
      thread_id: 'workspace-1',
      selected_option_id: 'option-123',
      effect_mentions: [{ effect_id: 'effect-2', display_name: 'Ribbon Flow' }],
      editor_revision: 7,
      editor_selection: {
        current_frame: 42,
        selected_point_id: 'point-1',
      },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestBody.selected_option_id, 'option-123');
  assert.deepEqual(requestBody.effect_mentions, [
    { effect_id: 'effect-2', display_name: 'Ribbon Flow' },
  ]);
  assert.equal(requestBody.editor_revision, 7);
  assert.deepEqual(requestBody.editor_selection, {
    current_frame: 42,
    selected_point_id: 'point-1',
  });
  assert.equal('editor_state' in requestBody, false);
  assert.doesNotMatch(requestBody.user_input, /^Selected:/);
});


test('workspace control APIs send stable IDs and editor revisions', async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({}) };
  };
  const editorState = { points: [] };

  try {
    await createEffectWorkspace('effect-1', 'video-1');
    await replaceEditorState('effect-1', 4, editorState);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requests[0].url, '/api/effects');
  assert.equal(requests[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(requests[0].options.body), {
    effect_id: 'effect-1',
    video_id: 'video-1',
  });
  assert.equal(requests[1].url, '/api/effect/effect-1/editor-state');
  assert.equal(requests[1].options.method, 'PUT');
  assert.deepEqual(JSON.parse(requests[1].options.body), {
    expected_revision: 4,
    editor_state: editorState,
  });
});


test('Effect PATCH sends slider range and value updates together', async () => {
  const originalFetch = globalThis.fetch;
  let request = null;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => ({}) };
  };

  try {
    await patchEffect('effect-1', {
      parameter_updates: { size: 30 },
      parameter_range_updates: { size: { min: 30, max: 45 } },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(request.url, '/api/effect/effect-1');
  assert.equal(request.options.method, 'PATCH');
  assert.equal(request.options.keepalive, true);
  assert.deepEqual(JSON.parse(request.options.body), {
    parameter_updates: { size: 30 },
    parameter_range_updates: { size: { min: 30, max: 45 } },
  });
});
