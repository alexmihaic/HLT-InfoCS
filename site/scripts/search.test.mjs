// PRODUCT-02A: node --test scripts/search.test.mjs (after npm run build).
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { buildSearchDocument, searchExcerpt } from '../src/lib/presentation/searchContent.ts';

test('record index uses an explicit search corpus, not the entire detail UI', async () => {
  const [slug] = await readdir(new URL('../dist/registro/', import.meta.url));
  const html = await readFile(new URL(`../dist/registro/${slug}/index.html`, import.meta.url), 'utf8');
  assert.ok(/class="record-search-content"[^>]*data-pagefind-body/.test(html), 'dedicated corpus required');
  assert.ok(!/<article[^>]*data-pagefind-body/.test(html), 'detail UI must not be the corpus');
  assert.ok(/data-pagefind-meta="search_context"/.test(html), 'safe context metadata required');
});

const fixture = () => ({
  record: { sourceId: 'boe', title: 'Convocatoria de empleo sintética', officialId: 'TEST-001' },
  bdnsView: null, source: 'BOE', category: 'Empleo público',
  authority: { label: 'Sección del BOE', value: 'Administración Local' },
  date: { label: 'Publicado', display: '20 de octubre de 2099', value: '2099-10-20' },
  geographies: ['Provincia: Castellón'], municipality: null,
});

test('index retains metadata matches with explicit separators, without page boilerplate', () => {
  const result = buildSearchDocument(fixture());
  assert.ok(result.texts.includes('Sección del BOE: Administración Local'));
  assert.ok(result.texts.includes('Publicado: 20 de octubre de 2099'));
  assert.ok(result.texts.includes('Identificador BOE: TEST-001'));
  assert.ok(!result.excerpts.some((text) => text.includes('Administración Local')));
  assert.ok(!result.texts.some((text) => text.includes('asesoramiento jurídico')));
});

test('optional fields stay absent; no undefined, invented authority or deadline', () => {
  const input = fixture();
  input.authority = null;
  delete input.record.officialId;
  input.geographies = [];
  const result = buildSearchDocument(input);
  assert.equal(result.excerpts.length, 0);
  assert.equal(searchExcerpt(JSON.stringify(result.excerpts), 'empleo'), null);
  assert.ok(!result.texts.join(' ').includes('undefined'));
});

test('BDNS preserves searchable official details, excludes locators/codes already excluded by UI', () => {
  const input = fixture();
  input.record.sourceId = 'bdns';
  input.record.grant = { callId: 'TEST-002' };
  input.bdnsView = {
    purpose: { label: 'Finalidad declarada', value: 'Promoción del comercio de prueba' },
    budget: { label: 'Presupuesto de la convocatoria', displayValue: '20.000', currencyNotice: 'Moneda no indicada en los datos' },
    instruments: { label: 'Instrumentos de ayuda', items: ['Subvención'] },
    beneficiaryTypes: { label: 'Destinatarios', items: [{ label: 'Asociaciones', code: 'CODE_NOT_INDEXED' }] },
    sectors: { items: [] }, impactRegions: { label: 'Ámbito declarado', items: ['Territorio de prueba'] },
    application: { end: { label: 'Fin de solicitud', text: { value: 'Veinte días hábiles desde la publicación' } } },
    regulatoryBases: { description: { label: 'Bases reguladoras', value: 'Bases reguladoras del comercio de prueba' }, sourceLocator: { value: 'LOCATOR_NOT_INDEXED' } },
    electronicOffice: { value: 'URL_NOT_INDEXED' },
    documents: { items: [{ description: { label: 'Descripción', value: 'Anexo de bases' }, filename: { value: 'FILE_NOT_INDEXED' } }] },
  };
  const result = buildSearchDocument(input);
  assert.ok(result.texts.includes('Presupuesto de la convocatoria: 20.000 · Moneda no indicada en los datos'));
  assert.ok(result.excerpts.includes('Fin de solicitud: Veinte días hábiles desde la publicación'));
  assert.ok(result.excerpts.includes('Descripción: Anexo de bases'));
  assert.ok(result.excerpts.includes('Bases reguladoras del comercio de prueba'));
  assert.ok(!result.excerpts.some((text) => text.includes('20.000')));
  assert.ok(!result.texts.join(' ').includes('NOT_INDEXED'));
});

test('deduplicates values already shown as title/metadata', () => {
  const input = fixture();
  input.geographies = [input.record.title, input.record.title];
  const result = buildSearchDocument(input);
  assert.equal(result.texts.filter((text) => text === input.record.title).length, 1);
  assert.equal(searchExcerpt(JSON.stringify(result.excerpts), 'convocatoria'), null);
});

test('avoids redundant field prefix while preserving the literal and searchable INE evidence', () => {
  const input = fixture();
  input.geographies = ['Provincia: Castellón'];
  input.municipality = { name: 'Municipio de prueba', label: 'Municipio convocante', code: '12000' };
  const result = buildSearchDocument(input);
  assert.ok(result.texts.includes('Provincia: Castellón'));
  assert.ok(result.texts.includes('Código INE del municipio identificado: 12000'));
});

test('excerpt finds relevant literal context including accent-insensitive terms', () => {
  const data = JSON.stringify(['Fin de solicitud: Veinte días hábiles', 'Finalidad declarada: Formación de jóvenes']);
  assert.equal(searchExcerpt(data, 'formacion'), 'Finalidad declarada: Formación de jóvenes');
  assert.equal(searchExcerpt(data, 'jóvenes'), 'Finalidad declarada: Formación de jóvenes');
  assert.equal(searchExcerpt(data, 'háBiles'), 'Fin de solicitud: Veinte días hábiles');
  assert.equal(searchExcerpt(data, 'desconocido'), null);
});

test('excerpt is bounded, keeps matching context and collapses presentation whitespace only', () => {
  const text = `${'Inicio de ejemplo '.repeat(30)}comercio local ${'resto del texto '.repeat(30)}`;
  const excerpt = searchExcerpt(JSON.stringify([text]), 'comercio');
  assert.ok(excerpt.length <= 242);
  assert.ok(excerpt.includes('comercio'));
  assert.ok(excerpt.startsWith('…'));
  assert.equal(searchExcerpt(JSON.stringify(['Finalidad:\n ayuda\tlocal']), 'ayuda'), 'Finalidad: ayuda local');
});

test('missing/malformed excerpt metadata is omitted safely', () => {
  for (const value of [undefined, null, {}, 'not-json', '{}', '[12]', '[null]', '[]']) {
    assert.equal(searchExcerpt(value, 'dato'), null);
  }
});

test('special characters remain literal; renderer never inserts HTML or double-decodes entities', async () => {
  const text = 'Finalidad: Ayuda & formación <img src=x onerror=alert(1)> &lt;literal&gt;';
  assert.equal(searchExcerpt(JSON.stringify([text]), 'formación'), text);
  const renderer = await readFile(new URL('../src/scripts/search.ts', import.meta.url), 'utf8');
  assert.ok(!/innerHTML|outerHTML|insertAdjacentHTML/.test(renderer));
  assert.ok(renderer.includes('element.textContent = text'));
  assert.ok(renderer.includes("document.createTextNode(' · ')"));
});

// Execute the actual search controller with only its external Pagefind/DOM
// boundary replaced. TypeScript is already a project dependency. No browser
// download, no server and no network; no copied renderer implementation.
class Element {
  constructor(tagName = '') { this.tagName = tagName; this.children = []; this.text = ''; this.hidden = false; }
  set textContent(value) { this.text = value; this.children = []; }
  get textContent() { return this.text + this.children.map((child) => child.textContent).join(''); }
  get childElementCount() { return this.children.length; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.text = ''; this.children = children; }
}
const controller = ts.transpileModule(await readFile(new URL('../src/scripts/search.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

async function renderSearch({ query = 'ayuda', data = [], failure = false } = {}) {
  const calls = [];
  const controls = Object.fromEntries(['form[role="search"]', '#search-query', '#search-status', '#search-empty', '#search-results']
    .map((selector) => [selector, new Element(selector)]));
  const root = { querySelector: (selector) => controls[selector] };
  runInNewContext(controller, {
    exports: {}, URL, URLSearchParams,
    document: {
      querySelector: () => root,
      createElement: (tag) => new Element(tag),
      createTextNode: (text) => Object.assign(new Element('#text'), { text }),
    },
    window: { location: { origin: 'https://example.test', search: `?q=${encodeURIComponent(query)}` }, addEventListener() {} },
    require: (path) => {
      if (path.includes('searchContent')) return { searchExcerpt };
      if (failure) throw new Error('synthetic index unavailable');
      return {
        options: async (options) => { calls.push(['options', options]); },
        search: async () => {
          calls.push(['search']);
          return { results: data.map((item) => ({ data: async () => item })) };
        },
      };
    },
  });
  const loading = controls['#search-status'].textContent;
  await new Promise(setImmediate);
  return { controls, calls, loading, result: controls['#search-results'], status: controls['#search-status'].textContent };
}

test('controller neutralizes only search_context before searching, preserving default title/other weights', async () => {
  const view = await renderSearch();
  assert.equal(JSON.stringify(view.calls), JSON.stringify([
    ['options', { ranking: { metaWeights: { search_context: 0 } } }], ['search'],
  ]));
});

test('actual controller preserves loading, empty query, no-results and index-error states', async () => {
  const none = await renderSearch();
  assert.equal(none.loading, 'Buscando en las publicaciones…');
  assert.ok(none.status.startsWith('No se encontraron resultados'));
  assert.equal(none.controls['#search-empty'].hidden, false);
  assert.ok((await renderSearch({ query: '' })).status.startsWith('Introduce un término'));
  assert.equal((await renderSearch({ failure: true })).status, 'No se pudo cargar el índice de búsqueda.');
});

test('actual controller handles absent metadata and rejects external/non-record links', async () => {
  const meta = { kind: 'record', title: 'Ayuda de prueba', public_url: '/registro/test/' };
  const view = await renderSearch({ data: [
    {}, { meta: { ...meta, kind: 'page' } },
    { meta: { ...meta, public_url: 'https://other.test/registro/test/' } },
    { meta: { ...meta, public_url: 'javascript:alert(1)' } }, { meta },
  ] });
  assert.equal(view.result.children.length, 1);
  assert.equal(view.status, '1 resultado para «ayuda».');
  assert.equal(view.result.textContent, 'Ayuda de prueba');
});

test('actual renderer treats hostile HTML/entities as text and keeps links/date/labels', async () => {
  const literal = 'Ayuda & formación <img src=x onerror=alert(1)> &lt;literal&gt;';
  const view = await renderSearch({ data: [{ meta: {
    kind: 'record', title: 'Convocatoria sintética', public_url: '/registro/test/', source: 'BDNS',
    authority: 'Organismo con un nombre largo de prueba', authority_label: 'Organismo',
    primary_date_label: 'Publicado', primary_date_value: '20 de octubre de 2099', primary_date_iso: '2099-10-20',
    bdns_budget_display: '20.000', bdns_budget_currency_notice: 'Moneda no indicada en los datos',
    search_context: JSON.stringify([literal]),
  } }] });
  const all = (node) => [node, ...node.children.flatMap(all)];
  const nodes = all(view.result);
  assert.equal(nodes.find((node) => node.tagName === 'a').href, '/registro/test/');
  assert.equal(nodes.find((node) => node.tagName === 'time').dateTime, '2099-10-20');
  assert.equal(nodes.some((node) => node.tagName === 'img'), false);
  assert.ok(view.result.textContent.includes(literal));
  assert.ok(view.result.textContent.includes('20.000 · Moneda no indicada'));
  assert.ok(view.result.textContent.includes('Publicado: 20 de octubre de 2099'));
});
