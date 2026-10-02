import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import { selectPointReference, selectPathReference } from './referenceSelection.js';

test('canvas and chat Point controls share the exclusive selection handler', () => {
  const appSource = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8');
  const handlers = [...appSource.matchAll(/onSelectPoint=\{([^}]+)\}/g)]
    .map((match) => match[1]);
  assert.deepEqual(handlers, ['handleSelectPoint', 'handleSelectPoint']);
});

test('selecting a Point clears a previously selected Path', () => {
  assert.deepEqual(selectPointReference('point-1'), {
    selectedPointId: 'point-1',
    selectedPathId: null,
  });
});

test('selecting a Path clears a previously selected Point', () => {
  assert.deepEqual(selectPathReference('path-1'), {
    selectedPointId: null,
    selectedPathId: 'path-1',
  });
});
