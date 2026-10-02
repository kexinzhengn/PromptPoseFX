import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveWorkspaceId } from './workspaceIdentity.js';

test('resolveWorkspaceId reuses the current thread identity', () => {
  let calls = 0;
  const result = resolveWorkspaceId('thread-1', 'effect-1', () => {
    calls += 1;
    return 'new-id';
  });

  assert.equal(result, 'thread-1');
  assert.equal(calls, 0);
});

test('resolveWorkspaceId reuses a selected pending effect identity', () => {
  const result = resolveWorkspaceId('', 'pending-1', () => 'new-id');
  assert.equal(result, 'pending-1');
});

test('resolveWorkspaceId creates an identity before the first request', () => {
  const result = resolveWorkspaceId('', null, () => 'workspace-1');
  assert.equal(result, 'workspace-1');
});
