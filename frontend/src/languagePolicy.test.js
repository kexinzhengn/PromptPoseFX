import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const SOURCE_ROOT = path.dirname(fileURLToPath(import.meta.url));
const CJK_PATTERN = /[\u3400-\u4dbf\u4e00-\u9fff]/u;

async function collectRuntimeSourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nestedFiles = await Promise.all(entries.map(async (entry) => {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return collectRuntimeSourceFiles(entryPath);
    if (!/\.(js|jsx)$/u.test(entry.name) || entry.name.endsWith('.test.js')) return [];
    return [entryPath];
  }));
  return nestedFiles.flat();
}

test('runtime UI source and code comments use English', async () => {
  const files = await collectRuntimeSourceFiles(SOURCE_ROOT);
  const violations = [];

  for (const file of files) {
    const lines = (await readFile(file, 'utf8')).split('\n');
    lines.forEach((line, index) => {
      if (CJK_PATTERN.test(line)) {
        violations.push(`${path.relative(SOURCE_ROOT, file)}:${index + 1}`);
      }
    });
  }

  assert.deepEqual(violations, []);
});
