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

const {
  default: ParamsPanel,
  ParamSelect,
} = await vite.ssrLoadModule('/src/components/ParamsPanel.jsx');

const EFFECT_CODE = `class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {
    enabled: {
      default: true,
      type: 'boolean',
      label: 'Enabled',
      description: 'Shows the effect',
    },
    mode: {
      default: 2,
      type: 'select',
      label: 'Mode',
      description: 'Chooses the rendering mode',
      options: [
        { label: 'Soft', value: 1 },
        { label: 'Bold', value: 2 },
      ],
    },
  };
  constructor() {}
  display() {}
}`;

const RANGE_EFFECT_CODE = `class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {
    intensity: {
      default: 1.236,
      type: 'range',
      label: 'Intensity',
      description: 'Controls the visual intensity',
      min: 0,
      max: 2,
      step: 0.001,
    },
  };
  constructor() {}
  display() {}
}`;

test('renders boolean and select CONFIG controls', () => {
  const html = renderToStaticMarkup(React.createElement(ParamsPanel, {
    effectCodes: { effect_1: EFFECT_CODE },
    selectedEffectId: 'effect_1',
    paramsState: { effect_1: { enabled: true, mode: 2 } },
    onUpdateParam: () => {},
    effects: [{ id: 'effect_1', name: 'Test effect' }],
    onRenameEffect: () => {},
  }));

  assert.match(html, /type="checkbox"/);
  assert.match(html, /<select/);
  assert.match(html, />Soft<\/option>/);
  assert.match(html, />Bold<\/option>/);
});

test('renders CONFIG descriptions as accessible parameter tooltips', () => {
  const html = renderToStaticMarkup(React.createElement(ParamsPanel, {
    effectCodes: { effect_1: EFFECT_CODE },
    selectedEffectId: 'effect_1',
    paramsState: { effect_1: { enabled: true, mode: 2 } },
    onUpdateParam: () => {},
    effects: [{ id: 'effect_1', name: 'Test effect' }],
    onRenameEffect: () => {},
  }));

  assert.match(html, /aria-label="About Enabled"/);
  assert.match(html, /aria-describedby="[^"]+"/);
  assert.match(html, /role="tooltip"/);
  assert.match(html, />Shows the effect<\/span>/);
  assert.match(html, />Chooses the rendering mode<\/span>/);
});

test('range controls show two-decimal values and expose slider range settings', () => {
  const html = renderToStaticMarkup(React.createElement(ParamsPanel, {
    effectCodes: { effect_1: RANGE_EFFECT_CODE },
    selectedEffectId: 'effect_1',
    paramsState: { effect_1: { intensity: 1.236 } },
    parameterRanges: {},
    onUpdateParam: () => {},
    onUpdateRange: () => {},
    effects: [{ id: 'effect_1', name: 'Test effect' }],
    onRenameEffect: () => {},
  }));

  assert.match(html, />1\.24<\/span>/);
  assert.doesNotMatch(html, />1\.236<\/span>/);
  assert.match(html, /aria-label="Edit Intensity slider range"/);
});

test('select returns the original typed option value', () => {
  let receivedValue = null;
  const tree = ParamSelect({
    label: 'Mode',
    value: 1,
    options: [
      { label: 'Soft', value: 1 },
      { label: 'Bold', value: 2 },
      { label: 'Disabled', value: false },
    ],
    onChange: (value) => { receivedValue = value; },
  });
  const select = tree.props.children[1];

  select.props.onChange({ target: { value: '1' } });
  assert.equal(receivedValue, 2);
  assert.equal(typeof receivedValue, 'number');

  select.props.onChange({ target: { value: '2' } });
  assert.equal(receivedValue, false);
  assert.equal(typeof receivedValue, 'boolean');
});
