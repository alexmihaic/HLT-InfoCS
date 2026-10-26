// UTILITY-02: BDNS call-type presentation and filter. Behaviour tests on the pure helpers and on the
// generated HTML (the latter need `npm run build` first, as in CI).
//   node --test scripts/
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  NO_CALL_TYPE,
  callTypeOptions,
  callTypeValue,
  matchesRecordFilters,
  sanitizeFilterValue,
} from '../src/lib/presentation/recordFilters.ts';

const bdns = (callType) => ({ sourceId: 'bdns', ...(callType === undefined ? {} : { bdns: { callType } }) });
const boe = () => ({ sourceId: 'boe' });

test('options are built only from official values present, with live counters', () => {
  const options = callTypeOptions([bdns('Concesión directa - instrumental'), bdns('Concurrencia competitiva - canónica'), bdns('Concesión directa - instrumental'), boe()]);
  assert.deepEqual(options, [
    { value: 'Concesión directa - instrumental', label: 'Concesión directa - instrumental', count: 2 },
    { value: 'Concurrencia competitiva - canónica', label: 'Concurrencia competitiva - canónica', count: 1 },
  ]);
});

test('no option is invented: empty input, BOE only and unknown official values', () => {
  assert.deepEqual(callTypeOptions([]), []);
  assert.deepEqual(callTypeOptions([boe(), boe()]), []);
  const options = callTypeOptions([bdns('Valor oficial futuro')]);
  assert.deepEqual(options.map((option) => option.value), ['Valor oficial futuro']);
});

test('BDNS records without a call type get a neutral marker, never an official category', () => {
  assert.equal(callTypeValue(bdns(undefined)), NO_CALL_TYPE);
  assert.equal(callTypeValue(bdns('   ')), NO_CALL_TYPE);
  const options = callTypeOptions([bdns(undefined), bdns('Concesión directa - instrumental')]);
  assert.deepEqual(options.map((option) => option.value), ['Concesión directa - instrumental', NO_CALL_TYPE]);
  assert.equal(options.at(-1).label, 'Sin tipo indicado por BDNS');
});

test('BOE records are never classified under a BDNS call type', () => {
  assert.equal(callTypeValue(boe()), undefined);
  assert.equal(matchesRecordFilters({ category: 'employment', callType: callTypeValue(boe()) }, { category: '', municipality: '', callType: 'Concesión directa - instrumental' }), false);
  assert.equal(matchesRecordFilters({ category: 'employment' }, { category: '', municipality: '', callType: NO_CALL_TYPE }), false);
});

test('filters combine with AND and an empty selection restricts nothing', () => {
  const grant = { category: 'grants.call', callType: 'Concesión directa - instrumental' };
  const job = { category: 'employment', municipality: '12031' };
  const none = { category: '', municipality: '', callType: '' };
  assert.ok(matchesRecordFilters(grant, none) && matchesRecordFilters(job, none));
  assert.ok(matchesRecordFilters(grant, { ...none, callType: 'Concesión directa - instrumental' }));
  assert.ok(!matchesRecordFilters(grant, { ...none, callType: 'Concurrencia competitiva - canónica' }));
  assert.ok(matchesRecordFilters(grant, { category: 'grants.call', municipality: '', callType: 'Concesión directa - instrumental' }));
  assert.ok(!matchesRecordFilters(grant, { category: 'employment', municipality: '', callType: 'Concesión directa - instrumental' }));
  assert.ok(!matchesRecordFilters(grant, { ...none, municipality: '12031', callType: 'Concesión directa - instrumental' }));
  assert.ok(matchesRecordFilters(job, { ...none, municipality: '12031' }));
});

test('URL values are restored only when valid; unknown, empty and malformed values are ignored', () => {
  const allowed = ['', 'Concesión directa - instrumental', NO_CALL_TYPE];
  assert.equal(sanitizeFilterValue('Concesión directa - instrumental', allowed), 'Concesión directa - instrumental');
  assert.equal(sanitizeFilterValue('<script>alert(1)</script>', allowed), '');
  assert.equal(sanitizeFilterValue('concesión directa - instrumental', allowed), '');
  assert.equal(sanitizeFilterValue(null, allowed), '');
  assert.equal(sanitizeFilterValue('', allowed), '');
});

// --- generated HTML -----------------------------------------------------------------------------
const DIST = new URL('../dist/', import.meta.url);
const DATA = new URL('../../data/records/', import.meta.url);
const built = existsSync(new URL('registros/index.html', DIST));
const decode = (text) => text.replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
  .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
  .replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

async function publicRecords(source) {
  const dir = new URL(`${source}/`, DATA);
  const names = (await readdir(dir)).filter((name) => name.endsWith('.json'));
  return Promise.all(names.map(async (name) => JSON.parse(await readFile(join(fileURLToPath(dir), name), 'utf8'))));
}

const items = (html) => html.split('<li').slice(1).filter((chunk) => chunk.includes('data-record-item'));

test('built /registros/: filter options and counters equal the official values in the data', { skip: !built }, async () => {
  const html = await readFile(new URL('registros/index.html', DIST), 'utf8');
  const expected = new Map();
  for (const record of await publicRecords('bdns')) {
    const value = record.source_data?.bdns?.call_type;
    const key = typeof value === 'string' && value.trim() ? value : NO_CALL_TYPE;
    expected.set(key, (expected.get(key) ?? 0) + 1);
  }
  const select = html.match(/<select id="filter-convocatoria"[\s\S]*?<\/select>/)?.[0] ?? '';
  const options = [...select.matchAll(/<option value="([^"]*)">([^<]*)<\/option>/g)].map((match) => [decode(match[1]), decode(match[2])]).filter(([value]) => value !== '');
  assert.equal(options.length, expected.size);
  for (const [value, label] of options) {
    assert.ok(expected.has(value), `valor inventado: ${value}`);
    assert.ok(label.endsWith(`(${expected.get(value)})`), `contador de ${value}: ${label}`);
  }
  assert.match(html, /<label for="filter-convocatoria">Tipo de convocatoria BDNS<\/label>/);
  assert.match(html, /<label for="filter-tipo">Tipo<\/label>/);
});

test('built /registros/: each BDNS row carries its literal official call type once; BOE rows carry none', { skip: !built }, async () => {
  const html = await readFile(new URL('registros/index.html', DIST), 'utf8');
  const rows = items(html);
  const bdnsRecords = await publicRecords('bdns');
  const boeRecords = await publicRecords('boe');
  assert.equal(rows.length, bdnsRecords.length + boeRecords.length);
  const withType = rows.filter((row) => / data-calltype="/.test(row.split('>')[0]));
  assert.equal(withType.length, bdnsRecords.length);
  const official = new Map();
  for (const record of bdnsRecords) {
    const value = record.source_data.bdns.call_type;
    official.set(value, (official.get(value) ?? 0) + 1);
  }
  const shown = new Map();
  for (const row of withType) {
    const attr = decode(row.match(/ data-calltype="([^"]*)"/)[1]);
    const text = decode(row.match(/<span class="calltype-value">([^<]*)<\/span>/)?.[1] ?? '');
    assert.equal(text, attr, 'el valor visible debe ser el literal del atributo');
    assert.equal((row.match(/calltype-value/g) ?? []).length, 1, 'tipo mostrado una sola vez');
    assert.doesNotMatch(row, /<dt>Tipo de convocatoria<\/dt>/, 'sin duplicar en la lista de datos');
    shown.set(attr, (shown.get(attr) ?? 0) + 1);
  }
  assert.deepEqual([...shown].sort(), [...official].sort());
  for (const row of rows.filter((candidate) => !withType.includes(candidate))) {
    assert.match(row, /data-category="employment"/);
    assert.doesNotMatch(row, /data-calltype|calltype-value/);
  }
});

test('built pages: source, organism and home keep one call-type presentation each', { skip: !built }, async () => {
  const source = await readFile(new URL('fuentes/bdns/index.html', DIST), 'utf8');
  assert.equal((source.match(/calltype-value/g) ?? []).length, items(source).length);
  assert.match(source, /href="\/registros\/\?tipo=grants\.call"/);
  const boeSource = await readFile(new URL('fuentes/boe/index.html', DIST), 'utf8');
  assert.doesNotMatch(boeSource, /calltype-value|\/registros\/\?tipo=/);
  const home = await readFile(new URL('index.html', DIST), 'utf8');
  assert.doesNotMatch(home, /calltype-value/, 'la portada conserva su presentación');
  const organisms = (await readdir(new URL('organismos/', DIST), { withFileTypes: true })).filter((entry) => entry.isDirectory());
  assert.ok(organisms.length > 0);
  const organism = await readFile(new URL(`organismos/${organisms[0].name}/index.html`, DIST), 'utf8');
  assert.equal((organism.match(/calltype-value/g) ?? []).length, items(organism).length);
});

test('built /registros/: titles, budgets and original data are untouched by the call-type work', { skip: !built }, async () => {
  const html = await readFile(new URL('registros/index.html', DIST), 'utf8');
  const text = decode(html);
  for (const record of await publicRecords('bdns')) {
    assert.ok(text.includes(record.title.replace(/\s+/g, ' ').trim()) || text.includes(record.title), `título ausente: ${record.source.official_id}`);
  }
  assert.equal((html.match(/<dt>Presupuesto<\/dt>/g) ?? []).length, (await publicRecords('bdns')).filter((r) => r.source_data.bdns.budget_total?.value !== undefined).length);
});
