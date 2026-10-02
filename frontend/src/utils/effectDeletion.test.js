import assert from 'node:assert/strict';
import test from 'node:test';

import {
  deleteAfterWorkspaceCreation,
  planEffectRemoval,
} from './effectDeletion.js';

test('removing one pending Effect preserves the other workspaces', () => {
  const result = planEffectRemoval({
    effectId: 'pending-1',
    effects: [{ id: 'active-1', name: 'Glow' }],
    pendingEffects: [
      { id: 'pending-1', name: 'Pending' },
      { id: 'pending-2', name: 'Pending' },
    ],
    selectedEffectId: 'pending-1',
  });

  assert.deepEqual(result.effects.map((effect) => effect.id), ['active-1']);
  assert.deepEqual(result.pendingEffects.map((effect) => effect.id), ['pending-2']);
  assert.equal(result.nextSelectedEffectId, 'active-1');
  assert.equal(result.removedPendingEffect.id, 'pending-1');
});

test('deletion waits for pending Workspace creation before calling the backend', async () => {
  const calls = [];
  let finishCreation;
  const creation = new Promise((resolve) => { finishCreation = resolve; });
  const deletion = deleteAfterWorkspaceCreation({
    creation,
    remove: async () => { calls.push('delete'); },
  });

  await Promise.resolve();
  assert.deepEqual(calls, []);
  calls.push('create');
  finishCreation();
  await deletion;

  assert.deepEqual(calls, ['create', 'delete']);
});

test('failed Workspace creation needs no backend deletion', async () => {
  let deleted = false;

  const result = await deleteAfterWorkspaceCreation({
    creation: Promise.reject(new Error('creation failed')),
    remove: async () => { deleted = true; },
  });

  assert.equal(result, 'not-created');
  assert.equal(deleted, false);
});
