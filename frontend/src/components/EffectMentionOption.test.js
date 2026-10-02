import assert from 'node:assert/strict';
import test from 'node:test';

import EffectMentionOption from './EffectMentionOption.js';

test('clicking an Effect mention option selects that Effect', () => {
  const effect = { id: 'effect-1', name: 'Strange Head Flower' };
  let selectedEffect = null;
  const option = EffectMentionOption({
    effect,
    onSelect: (selected) => { selectedEffect = selected; },
  });

  option.props.onClick();

  assert.equal(selectedEffect, effect);
});
