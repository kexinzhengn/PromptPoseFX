import assert from 'node:assert/strict';
import test from 'node:test';

import { createEffectPatchScheduler } from './effectPatchScheduler.js';


test('debounces and merges Effect parameter patches per Effect', async () => {
  const callbacks = [];
  const cleared = [];
  const saved = [];
  const scheduler = createEffectPatchScheduler({
    delay: 300,
    save: async (effectId, patch) => {
      saved.push({ effectId, patch });
      return { effect_update: { effect_id: effectId, params: patch.parameter_updates } };
    },
    setTimer: (callback, delay) => {
      callbacks.push({ callback, delay });
      return callbacks.length;
    },
    clearTimer: (timerId) => cleared.push(timerId),
  });

  scheduler.schedule('effect-1', { parameter_updates: { size: 20 } });
  scheduler.schedule('effect-1', { parameter_updates: { size: 40, enabled: false } });

  assert.deepEqual(saved, []);
  assert.deepEqual(scheduler.getLocalPatch('effect-1'), {
    parameter_updates: { size: 40, enabled: false },
  });
  assert.deepEqual(cleared, [1]);
  assert.equal(callbacks[1].delay, 300);

  await callbacks[1].callback();

  assert.deepEqual(saved, [{
    effectId: 'effect-1',
    patch: { parameter_updates: { size: 40, enabled: false } },
  }]);
});


test('ignores an older save result after a newer local change', async () => {
  const callbacks = [];
  const resolvers = [];
  const applied = [];
  const scheduler = createEffectPatchScheduler({
    save: (effectId, patch) => new Promise((resolve) => {
      resolvers.push(() => resolve({ effectId, patch }));
    }),
    onSaved: (result) => applied.push(result),
    setTimer: (callback) => {
      callbacks.push(callback);
      return callbacks.length;
    },
    clearTimer: () => {},
  });

  scheduler.schedule('effect-1', { parameter_updates: { size: 20 } });
  const firstSave = callbacks[0]();
  scheduler.schedule('effect-1', { parameter_updates: { size: 40 } });
  resolvers[0]();
  await firstSave;

  assert.deepEqual(applied, []);
});


test('resends all unconfirmed local changes after an overlapping request', async () => {
  const callbacks = [];
  const saved = [];
  const scheduler = createEffectPatchScheduler({
    save: async (effectId, patch) => saved.push({ effectId, patch }),
    setTimer: (callback) => {
      callbacks.push(callback);
      return callbacks.length;
    },
    clearTimer: () => {},
  });

  scheduler.schedule('effect-1', { parameter_updates: { size: 20 } });
  const firstSave = callbacks[0]();
  scheduler.schedule('effect-1', { parameter_updates: { enabled: false } });
  await firstSave;
  await callbacks[1]();

  assert.deepEqual(saved[1].patch, {
    parameter_updates: { size: 20, enabled: false },
  });
});


test('merges slider ranges and values into one Effect patch', async () => {
  const callbacks = [];
  const saved = [];
  const scheduler = createEffectPatchScheduler({
    save: async (effectId, patch) => saved.push({ effectId, patch }),
    setTimer: (callback) => {
      callbacks.push(callback);
      return callbacks.length;
    },
    clearTimer: () => {},
  });

  scheduler.schedule('effect-1', {
    parameter_updates: { size: 30 },
    parameter_range_updates: { size: { min: 30, max: 45 } },
  });
  scheduler.schedule('effect-1', {
    parameter_range_updates: { strength: { min: 2, max: 8 } },
  });

  assert.deepEqual(scheduler.getLocalPatch('effect-1'), {
    parameter_updates: { size: 30 },
    parameter_range_updates: {
      size: { min: 30, max: 45 },
      strength: { min: 2, max: 8 },
    },
  });

  await callbacks[1]();

  assert.deepEqual(saved[0].patch, {
    parameter_updates: { size: 30 },
    parameter_range_updates: {
      size: { min: 30, max: 45 },
      strength: { min: 2, max: 8 },
    },
  });
});


test('starts an explicit range save before a refresh can cancel the debounce', async () => {
  const saved = [];
  const scheduler = createEffectPatchScheduler({
    save: async (effectId, patch) => saved.push({ effectId, patch }),
    setTimer: () => 1,
    clearTimer: () => {},
  });

  const saving = scheduler.schedule('effect-1', {
    parameter_updates: { size: 30 },
    parameter_range_updates: { size: { min: 30, max: 45 } },
  }, { immediate: true });
  scheduler.cancelAll();
  await saving;

  assert.deepEqual(saved, [{
    effectId: 'effect-1',
    patch: {
      parameter_updates: { size: 30 },
      parameter_range_updates: { size: { min: 30, max: 45 } },
    },
  }]);
});
