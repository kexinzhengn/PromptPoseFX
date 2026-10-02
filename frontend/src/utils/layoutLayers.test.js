import assert from 'node:assert/strict';
import test from 'node:test';

import { APP_LAYERS } from './layoutLayers.js';

test('interactive chat UI stays above video overlays', () => {
  assert.ok(APP_LAYERS.chatInput > APP_LAYERS.videoProgress);
  assert.ok(APP_LAYERS.videoProgress > APP_LAYERS.videoCanvas);
});
