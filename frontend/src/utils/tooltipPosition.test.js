import assert from 'node:assert/strict';
import test from 'node:test';

import { calculateTooltipPosition } from './tooltipPosition.js';

const viewport = { width: 1000, height: 700 };
const tooltip = { width: 224, height: 72 };

test('a tooltip near the tab boundary opens below its trigger', () => {
  const position = calculateTooltipPosition(
    { left: 760, right: 774, top: 32, bottom: 46 },
    tooltip,
    viewport,
  );

  assert.equal(position.placement, 'below');
  assert.ok(position.top >= 54);
});

test('a tooltip near the panel bottom opens above and stays inside the viewport', () => {
  const position = calculateTooltipPosition(
    { left: 970, right: 984, top: 650, bottom: 664 },
    tooltip,
    viewport,
  );

  assert.equal(position.placement, 'above');
  assert.ok(position.left + tooltip.width <= viewport.width - 8);
  assert.ok(position.top >= 8);
});
