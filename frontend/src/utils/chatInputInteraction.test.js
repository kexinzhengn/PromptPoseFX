import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldFocusInputFromRow } from './chatInputInteraction.js';

test('the input row does not override native caret placement inside the input', () => {
  const row = {};
  const input = {};

  assert.equal(shouldFocusInputFromRow(input, row), false);
  assert.equal(shouldFocusInputFromRow(row, row), true);
});
