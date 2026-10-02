import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyMentionSelection,
  findMentionQuery,
  getMentionCandidates,
  reconcileMentions,
} from './effectMentions.js';

const effects = [
  { id: 'current', name: 'Current Glow', status: 'active' },
  { id: 'active-1', name: 'Ribbon Flow', status: 'active' },
  { id: 'active-2', name: 'Wrist Sparks', status: 'active' },
  { id: 'draft-1', name: 'Draft Trail', status: 'draft' },
];

test('mention candidates contain only other active Effects', () => {
  const candidates = getMentionCandidates(effects, 'current', [], 'ribbon');

  assert.deepEqual(candidates.map((effect) => effect.id), ['active-1']);
  assert.equal(candidates.some((effect) => effect.id === 'current'), false);
  assert.equal(candidates.some((effect) => effect.status === 'draft'), false);
});

test('selecting multiple mentions preserves stable IDs and visible names', () => {
  const firstQuery = findMentionQuery('Use @ri');
  const first = applyMentionSelection('Use @ri', firstQuery.start, effects[1]);
  const secondText = `${first.text}and @wri`;
  const secondQuery = findMentionQuery(secondText);
  const second = applyMentionSelection(secondText, secondQuery.start, effects[2]);

  assert.equal(second.text, 'Use @Ribbon Flow and @Wrist Sparks ');
  assert.deepEqual(
    [first.mention, second.mention],
    [
      { effect_id: 'active-1', display_name: 'Ribbon Flow' },
      { effect_id: 'active-2', display_name: 'Wrist Sparks' },
    ],
  );
});

test('removed visible tags are removed from structured mentions', () => {
  const mentions = [
    { effect_id: 'active-1', display_name: 'Ribbon Flow' },
    { effect_id: 'active-2', display_name: 'Wrist Sparks' },
  ];

  assert.deepEqual(
    reconcileMentions('Keep @Wrist Sparks only', mentions),
    [{ effect_id: 'active-2', display_name: 'Wrist Sparks' }],
  );
});

test('mention search also opens directly after Chinese text', () => {
  assert.deepEqual(findMentionQuery('参考@Ribbon'), {
    start: 2,
    query: 'ribbon',
  });
});
