// PRODUCT-03A: node --test scripts/changes.test.mjs (after npm run build).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile, readdir } from 'node:fs/promises';
import { eventDescription } from '../src/lib/presentation/labels.ts';

const update = (...changedFields) => ({ type: 'update', sourceId: 'bdns', changedFields });
const path = (field) => `source_data.bdns.${field}`;
const describe = (...fields) => eventDescription(update(...fields.map(path)));

test('application dates, literal periods and source flag describe only the area changed', () => {
  for (const field of ['application', 'application.start_date', 'application.end_date', 'application.start_text', 'application.end_text', 'application.abierto']) {
    assert.equal(describe(field), 'InfoCs detectó cambios en el plazo de solicitud');
  }
});
test('budget and currency are grouped without implying an increase or award', () => {
  assert.equal(describe('budget_total.value', 'budget_total.currency'), 'InfoCs detectó cambios en el presupuesto de la convocatoria');
});
test('eligible types are not presented as actual awarded beneficiaries', () => {
  assert.equal(describe('eligible_beneficiary_types'), 'InfoCs detectó cambios en los tipos de destinatarios');
});
test('same category and duplicate fields produce one label', () => {
  assert.equal(describe('application.start_date', 'application.end_date', 'application.end_date'), describe('application'));
  assert.equal(eventDescription(update('documents', path('documents'))), 'InfoCs detectó cambios en la documentación');
});
test('different categories have deterministic order and natural separators', () => {
  const expected = 'InfoCs detectó cambios en el plazo de solicitud, el presupuesto de la convocatoria y los tipos de destinatarios';
  assert.equal(describe('eligible_beneficiary_types', 'budget_total.value', 'application.end_date'), expected);
  assert.equal(describe('application.end_date', 'eligible_beneficiary_types', 'budget_total.value'), expected);
});
test('unknown and unknown descendants stay neutral and never expose raw paths', () => {
  for (const field of ['unknown', 'application.future_field', 'documents.fake', '__proto__']) {
    assert.equal(describe(field), 'InfoCs detectó cambios en información de la ficha');
  }
  assert.equal(describe('application.end_date', 'unknown'), 'InfoCs detectó cambios en el plazo de solicitud y otros datos de la ficha');
});
test('CREATE and historical UPDATE without changed_fields retain neutral descriptions', () => {
  assert.equal(eventDescription({ type: 'create', changedFields: [path('application')] }), 'InfoCs incorporó esta publicación');
  assert.equal(eventDescription({ type: 'update', sourceId: 'boe' }), 'InfoCs detectó cambios en la ficha');
});
test('BOE keeps its own semantics and does not interpret BDNS extension paths', () => {
  assert.equal(eventDescription({ ...update('authority.name', 'title'), sourceId: 'boe' }), 'InfoCs detectó cambios en el título y la sección del BOE');
  assert.equal(eventDescription({ ...update(path('application.end_date')), sourceId: 'boe' }), 'InfoCs detectó cambios en información de la ficha');
});
test('dates root does not invent a deadline; documentation, bases and authority are distinct', () => {
  assert.equal(eventDescription(update('dates')), 'InfoCs detectó cambios en las fechas de la publicación');
  assert.equal(describe('authority_hierarchy.nivel2'), 'InfoCs detectó cambios en el organismo convocante');
  assert.equal(describe('regulatory_bases.description'), 'InfoCs detectó cambios en las bases reguladoras');
  assert.equal(describe('extracts'), 'InfoCs detectó cambios en los extractos en diarios oficiales');
});

async function jsonFiles(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const url = new URL(`${encodeURIComponent(entry.name)}${entry.isDirectory() ? '/' : ''}`, directory);
    if (entry.isDirectory()) files.push(...await jsonFiles(url));
    else if (entry.name.endsWith('.json')) files.push(url);
  }
  return files;
}

test('all real historical UPDATE descriptions appear identically in changes and record build', async () => {
  const changes = await readFile(new URL('../dist/cambios/index.html', import.meta.url), 'utf8');
  let updates = 0;
  for (const file of await jsonFiles(new URL('../../data/events/', import.meta.url))) {
    const event = JSON.parse(await readFile(file, 'utf8'));
    if (event.type !== 'update') continue;
    updates++;
    const description = eventDescription({ type: event.type, sourceId: event.source_id, changedFields: event.changed_fields });
    const slug = `r-${Buffer.from(event.record_id, 'utf8').toString('hex')}`;
    const record = await readFile(new URL(`../dist/registro/${slug}/index.html`, import.meta.url), 'utf8');
    assert.ok(changes.includes(description));
    assert.ok(record.includes(description));
  }
  assert.ok(updates > 0, 'snapshot contains real UPDATE coverage');
});
