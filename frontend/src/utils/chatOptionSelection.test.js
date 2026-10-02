import assert from 'node:assert/strict';
import test from 'node:test';

import { formatSelectedOptionMessage } from './chatOptionSelection.js';

test('selected options show both their title and detailed description', () => {
  assert.equal(
    formatSelectedOptionMessage({
      label: 'Orbiting light',
      description: 'A soft light circles both wrists and accelerates with movement.',
    }),
    'Orbiting light\nA soft light circles both wrists and accelerates with movement.',
  );
});

test('selected options do not duplicate identical detail text', () => {
  assert.equal(
    formatSelectedOptionMessage({ label: 'Pulse', description: 'Pulse' }),
    'Pulse',
  );
});
