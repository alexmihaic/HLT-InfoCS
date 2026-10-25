// Unit tests for the VISUAL-02A accessibility and consistency fixes. Run with:
//   node --test scripts/
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

import { describeSystemTimestamp } from '../src/lib/presentation/dates.ts';
import { recordCountLabel } from '../src/lib/presentation/recordFilters.ts';

test('record count label: initial state, filtered state and zero matches', () => {
  assert.equal(recordCountLabel(77, 77), '77 registros publicados');
  assert.equal(recordCountLabel(1, 1), '1 registro publicado');
  assert.equal(recordCountLabel(5, 77), '5 de 77 registros publicados');
  assert.equal(recordCountLabel(0, 77), '0 de 77 registros publicados');
});

test('technical timestamps use the common Madrid-time formatter without altering the stored value', () => {
  const view = describeSystemTimestamp('2026-10-24T08:30:00Z');
  assert.equal(view.dateTime, '2026-10-24T08:30:00Z');
  assert.match(view.text, /24 de octubre de 2026/);
  assert.match(view.text, /10:30/);
  assert.doesNotMatch(view.text, /T08:30/);
});

test('technical timestamps keep explicit states for missing and invalid values', () => {
  for (const missing of [undefined, null, '', '   ']) {
    assert.deepEqual(describeSystemTimestamp(missing), { text: 'No disponible' });
  }
  assert.deepEqual(describeSystemTimestamp('no-es-una-fecha'), { text: 'no-es-una-fecha' });
});

test('timestamps with an explicit offset respect that instant', () => {
  const plus = describeSystemTimestamp('2026-10-24T10:30:00+02:00');
  assert.equal(plus.dateTime, '2026-10-24T10:30:00+02:00');
  assert.match(plus.text, /24 de octubre de 2026 a las 10:30/);
  const minus = describeSystemTimestamp('2026-10-24T05:30:00-05:00');
  assert.equal(minus.dateTime, '2026-10-24T05:30:00-05:00');
  assert.match(minus.text, /24 de octubre de 2026 a las 12:30/); // 10:30Z → Madrid CEST
  const winter = describeSystemTimestamp('2026-01-15T23:30:00-0500');
  assert.match(winter.text, /16 de enero de 2026 a las 05:30/); // 04:30Z → Madrid CET
});

test('values without a declared zone are kept literally, never converted or given a time', () => {
  for (const value of ['2026-10-24', '2026-10-24T08:30:00', '2026-10-24T08:30', '2026-10-24T08:30:00.123456', '2026']) {
    assert.deepEqual(describeSystemTimestamp(value), { text: value }, value);
  }
  // Hyphens in the date are not an offset.
  assert.deepEqual(describeSystemTimestamp('2026-10-24 08:30:00'), { text: '2026-10-24 08:30:00' });
  // Zone-shaped but impossible dates are invalid, not converted.
  assert.deepEqual(describeSystemTimestamp('2026-13-45T00:00:00Z'), { text: '2026-13-45T00:00:00Z' });
});

test('timestamp presentation does not depend on the machine time zone', () => {
  const probe = `
    import { describeSystemTimestamp as d } from ${JSON.stringify(new URL('../src/lib/presentation/dates.ts', import.meta.url).href)};
    console.log(JSON.stringify(['2026-10-24', '2026-10-24T08:30:00', '2026-10-24T08:30:00Z', '2026-10-24T08:30:00+02:00'].map(d)));`;
  const outputs = ['UTC', 'America/Los_Angeles', 'Asia/Tokyo'].map((tz) => {
    const result = spawnSync(process.execPath, ['--input-type=module', '-e', probe], { env: { ...process.env, TZ: tz }, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    return result.stdout.trim();
  });
  assert.equal(new Set(outputs).size, 1, outputs.join('\n'));
  assert.match(outputs[0], /a las 10:30 CEST/);
});

test('shared sources keep the accessible-status, heading and focus contracts', async () => {
  const read = (path) => readFile(new URL(path, import.meta.url), 'utf8');
  assert.match(await read('../src/components/RecordList.astro'), /data-record-count role="status"/);
  const css = await read('../src/styles/global.css');
  assert.match(css, /\.search-input:focus-visible\s*\{[^}]*outline:[^}]*var\(--color-focus\)/);
  const entry = await read('../src/components/ChangeRecordEntry.astro');
  assert.equal((entry.match(/href=\{item\.recordHref\}/g) ?? []).length, 1);
  for (const page of ['../src/pages/registros/index.astro', '../src/pages/organismos/[slug].astro']) {
    assert.match(await read(page), /<RecordList [^>]*headingLevel=\{2\}/, page);
  }
});
