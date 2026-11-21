import assert from 'node:assert/strict';
import { test } from 'node:test';
import { authorityFilterValue, authorityOptions, matchesRecordFilters, sanitizeFilterDate } from '../src/lib/presentation/recordFilters.ts';
import { readFile } from 'node:fs/promises';
const bdns = name => ({ sourceId: 'bdns', bdns: { authorityHierarchy: { nivel2: name } } });
const none = { category: '', municipality: '', callType: '' };
test('literal authorities group repeated names without merging spelling or slug collisions', () => {
  const options = authorityOptions([bdns('ÁREA'), bdns('ÁREA'), bdns('AREA'), bdns('sin-organismo'), bdns('  '), { sourceId: 'boe' }]);
  assert.equal(options.length, 4);
  assert.equal(options.find(o => o.value === 'nombre:ÁREA').count, 2);
  assert.equal(options.find(o => o.value === 'nombre:AREA').count, 1);
  assert.equal(authorityFilterValue(bdns(undefined)), 'sin-organismo');
  assert.equal(authorityFilterValue(bdns('sin-organismo')), 'nombre:sin-organismo');
  assert.equal(authorityFilterValue({ sourceId: 'boe', bdns: bdns('AREA').bdns }), undefined);
});
test('dates are real calendar dates, with leap years and strict URL validation', () => {
  for (const value of [null, '', '2026-02-29', '2026-04-31', '0000-01-01', '2026-1-01', '<script>', '2026-10-29T00:00:00Z']) assert.equal(sanitizeFilterDate(value), '');
  assert.equal(sanitizeFilterDate('2024-02-29'), '2024-02-29');
});
test('all filters intersect, dates include endpoints and reversed ranges match nothing', () => {
  const item = { category: 'grants.call', source: 'bdns', authority: 'nombre:ALMASSORA', callType: 'Directa', date: '2026-10-20' };
  const selection = { ...none, category: 'grants.call', source: 'bdns', authority: item.authority, callType: 'Directa', from: item.date, to: item.date };
  assert.equal(matchesRecordFilters(item, selection), true);
  for (const change of [{ source: 'boe' }, { municipality: '12009' }, { authority: 'sin-organismo' }, { from: '2026-10-21' }, { to: '2026-10-19' }]) assert.equal(matchesRecordFilters(item, { ...selection, ...change }), false);
  assert.equal(matchesRecordFilters({ source: 'boe' }, { ...none, authority: 'sin-organismo' }), false);
  assert.equal(matchesRecordFilters({}, { ...none, from: '2026-01-01' }), false);
});
test('generated authority counts and date attributes agree with the rendered records', async () => {
  const html = await readFile(new URL('../dist/registros/index.html', import.meta.url), 'utf8');
  const records = [...html.matchAll(/<li data-source="([^"]+)"([^>]+)>/g)];
  assert.ok(records.length > 0);
  const counts = new Map();
  for (const [, source, attrs] of records) {
    assert.match(attrs, /data-date="\d{4}-\d{2}-\d{2}"/);
    const authority = attrs.match(/data-authority="([^"]+)"/)?.[1];
    if (source === 'boe') assert.equal(authority, undefined);
    else counts.set(authority, (counts.get(authority) ?? 0) + 1);
  }
  const select = html.match(/<select id="filter-organismo"[\s\S]*?<\/select>/)[0];
  const options = [...select.matchAll(/<option value="([^"]+)">[^<]+ \((\d+)\)<\/option>/g)];
  assert.equal(options.length, counts.size);
  for (const [, value, count] of options) assert.equal(Number(count), counts.get(value));
});

 test('filter explains the official BDNS hierarchy and its legal identity limitation', async () => {
  const html = await readFile(new URL('../dist/registros/index.html', import.meta.url), 'utf8');
  assert.match(html, /nivel 2 de la jerarquía oficial BDNS/);
  assert.match(html, /no necesariamente identifican jurídicamente al organismo convocante exacto/);
});
