// Regression tests for UTILITY-01 (municipality filter wording, header tag). The source-page
// order is enforced on the real build by scripts/verify-build.mjs (section 3b).
//   node --test scripts/
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';


test('municipality filter states its BOE-title scope, points to Organismos and offers a reset', async () => {
  const filters = await readFile(new URL('../src/components/RecordFilters.astro', import.meta.url), 'utf8');
  assert.match(filters, /Municipio mencionado en el título \(BOE\)/);
  assert.match(filters, /El municipio solo se busca en títulos BOE/);
  assert.match(filters, /href="\/organismos\/"/);
  assert.match(filters, /data-filter-reset/);
  assert.match(filters, /Quitar filtros/);
  const list = await readFile(new URL('../src/components/RecordList.astro', import.meta.url), 'utf8');
  assert.match(list, /Municipio del título BOE y administración BDNS corresponden a fuentes distintas/);
});

test('header tag appears only from 1100px, where it no longer collides with the navigation', async () => {
  const css = await readFile(new URL('../src/styles/global.css', import.meta.url), 'utf8');
  assert.match(css, /@media \(min-width: 1100px\) \{\s*\.brand-tag \{ display: inline; \}\s*\}/);
  const block = css.match(/@media \(min-width: 1024px\) \{[\s\S]*?\n\}/)[0];
  assert.doesNotMatch(block, /\.brand-tag/);
});
