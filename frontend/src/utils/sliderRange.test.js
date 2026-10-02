import assert from 'node:assert/strict';
import test from 'node:test';

import { calculateSliderStep, formatSliderValue, prepareSliderRange } from './sliderRange.js';

test('slider values display at most two decimal places without changing integers', () => {
  assert.equal(formatSliderValue(2), '2');
  assert.equal(formatSliderValue(2.5), '2.5');
  assert.equal(formatSliderValue(2.345), '2.35');
  assert.equal(formatSliderValue(-0.004), '0');
});

test('a valid custom slider range clamps the current value into that range', () => {
  assert.deepEqual(prepareSliderRange({
    minimum: '10',
    maximum: '50',
    currentValue: 80,
  }), {
    ok: true,
    minimum: 10,
    maximum: 50,
    step: 0.5,
    value: 50,
  });
});

test('a custom slider range may extend beyond the generated CONFIG range', () => {
  assert.deepEqual(prepareSliderRange({
    minimum: '-50',
    maximum: '150',
    currentValue: 20,
  }), {
    ok: true,
    minimum: -50,
    maximum: 150,
    step: 2,
    value: 20,
  });
});

test('a custom slider range still requires ordered finite bounds', () => {
  assert.deepEqual(prepareSliderRange({
    minimum: '40',
    maximum: '40',
    currentValue: 20,
  }), {
    ok: false,
    error: 'Minimum must be less than maximum.',
  });

  assert.deepEqual(prepareSliderRange({
    minimum: 'not-a-number',
    maximum: '40',
    currentValue: 20,
  }), {
    ok: false,
    error: 'Enter valid minimum and maximum values.',
  });
});

test('slider step is recalculated from the current range span', () => {
  assert.equal(calculateSliderStep(0, 100), 1);
  assert.equal(calculateSliderStep(10, 50), 0.5);
  assert.equal(calculateSliderStep(0, 1), 0.01);
  assert.equal(calculateSliderStep(0, 0.1), 0.001);
});
