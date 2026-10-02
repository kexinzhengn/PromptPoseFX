import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('p5 is loaded on demand instead of entering the initial UI bundle', async () => {
  const source = await readFile(new URL('./useP5Sketch.js', import.meta.url), 'utf8');

  assert.doesNotMatch(source, /^import p5 from ['"]p5['"];?$/m);
  assert.match(source, /import\(['"]p5['"]\)/);
});
