import assert from 'node:assert/strict';
import test from 'node:test';

import { parseEffectFromCode } from './effectParser.js';

const V2_CODE = `class Effect {
  static CONTRACT_VERSION = 2;
  static CONFIG = {};
  display() {}
}`;

test('只接受 CONTRACT_VERSION 为 2 的 Effect', () => {
  const effect = parseEffectFromCode(V2_CODE);
  assert.equal(typeof effect.display, 'function');

  assert.throws(
    () => parseEffectFromCode('class Effect { static CONFIG = {}; display() {} }'),
    /CONTRACT_VERSION = 2/,
  );
  assert.throws(
    () => parseEffectFromCode('class Effect { static CONTRACT_VERSION = 1; display() {} }'),
    /CONTRACT_VERSION = 2/,
  );
});
