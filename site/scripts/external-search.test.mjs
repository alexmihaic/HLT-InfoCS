// UTILITY-03B-1: external search link and official BDNS extract metadata.
//   node --test scripts/
// Built-HTML checks need `npm run build` first, as in CI.
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

import { buildBDNSExtractsView } from '../src/lib/presentation/bdnsExtracts.ts';
import { buildExternalSearchHref, googleSearchHref, searchOrganism } from '../src/lib/presentation/externalLinks.ts';

const viewFactory = {
  officialGroup: (label, canonicalPath) => ({ origin: 'official', label, canonicalPath }),
  textView: (label, value, canonicalPath) => ({ origin: 'official', label, canonicalPath, value }),
  dateView: (label, value, canonicalPath) => ({ origin: 'official', label, canonicalPath, value, display: `Fecha: ${value}` }),
};

const HASH = 'a'.repeat(64);
const authority = (name) => ({ id: 'authority-1', name, administrationLevel: null });

function record({
  title = 'Convocatoria de prueba',
  sourceId = 'bdns',
  authority: issuer = null,
  bdns = {},
  category = sourceId === 'bdns' ? 'grants.call' : 'employment',
  extra = {},
} = {}) {
  return {
    id: `infocs:${sourceId}:1-abc`,
    sourceId,
    officialId: '1',
    category,
    title,
    authority: issuer,
    administrationLevel: null,
    detectedAt: '2026-10-27T00:00:00.000Z',
    lastCheckedAt: '2026-10-27T00:00:00.000Z',
    sourceUrl: 'https://www.infosubvenciones.es/bdnstrans/api/convocatorias?numConv=1',
    tags: [],
    contentHash: HASH,
    ...extra,
    ...(sourceId === 'bdns' ? {
      bdns: {
        extensionVersion: '1.0',
        instruments: [],
        eligibleBeneficiaryTypes: [],
        sectors: [],
        impactRegions: [],
        documents: [],
        extracts: [],
        ...bdns,
      },
    } : {}),
  };
}

const queryOf = (href) => new URL(href).searchParams.get('q');

// --- 1. Encoding -------------------------------------------------------------------------------
test('Google URL encodes accents, quotes, ampersands, parentheses and long titles', () => {
  const query = 'Ayudas & subvenciones "X" (2026) — Niño/Jesús';
  const href = googleSearchHref(query);
  assert.ok(href.startsWith('https://www.google.com/search?'));
  const url = new URL(href);
  assert.equal(url.origin, 'https://www.google.com');
  assert.equal(url.pathname, '/search');
  assert.deepEqual([...url.searchParams.keys()], ['q']);
  assert.equal(url.searchParams.get('q'), query);
  assert.match(href, /%26/, '& codificado');
  assert.match(href, /%22/, 'comillas codificadas');
  assert.match(href, /%C3%A1|%C3%AD|%C3%BA/, 'acentos codificados en UTF-8');

  const long = `${'A'.repeat(400)} ó & "q"`;
  assert.equal(queryOf(googleSearchHref(long)), long);

  assert.equal(googleSearchHref('   '), null);
  assert.equal(googleSearchHref(''), null);
});

// --- 2/3. Query composition --------------------------------------------------------------------
test('BDNS query uses the official title and the most specific organism', () => {
  const burriana = record({
    title: 'Subvenciones a entidades deportivas Burriana',
    authority: authority('LOCAL / BORRIANA/BURRIANA / AYUNTAMIENTO DE BORRIANA/BURRIANA'),
    bdns: { authorityHierarchy: { nivel1: 'LOCAL', nivel2: 'BORRIANA/BURRIANA', nivel3: 'AYUNTAMIENTO DE BORRIANA/BURRIANA' } },
  });
  assert.equal(searchOrganism(burriana), 'AYUNTAMIENTO DE BORRIANA/BURRIANA');
  assert.equal(queryOf(buildExternalSearchHref(burriana)),
    'Subvenciones a entidades deportivas Burriana AYUNTAMIENTO DE BORRIANA/BURRIANA');

  const chamber = record({ bdns: { authorityHierarchy: { nivel1: 'OTROS', nivel2: 'CÁMARA DE COMERCIO DE CASTELLÓN' } } });
  assert.equal(searchOrganism(chamber), 'CÁMARA DE COMERCIO DE CASTELLÓN');

  const fallback = record({ authority: authority('AYUNTAMIENTO DE NULES'), bdns: {} });
  assert.equal(searchOrganism(fallback), 'AYUNTAMIENTO DE NULES');

  const generic = record({ bdns: { authorityHierarchy: { nivel1: 'LOCAL' } } });
  assert.equal(searchOrganism(generic), undefined);
  assert.equal(queryOf(buildExternalSearchHref(generic)), 'Convocatoria de prueba');
});

test('BOE query uses the title only: the BOE summary section is not an issuing organism', () => {
  const boe = record({
    sourceId: 'boe',
    title: 'Resolución de 1 de octubre de 2026, del Ayuntamiento de Nules',
    authority: authority('I. Disposiciones generales'),
  });
  assert.equal(searchOrganism(boe), undefined);
  assert.equal(queryOf(buildExternalSearchHref(boe)), boe.title);
  assert.doesNotMatch(queryOf(buildExternalSearchHref(boe)), /Disposiciones generales/);
});

test('no internal identifier, hash or derived municipality is sent to Google', () => {
  const withTerritory = record({
    title: 'Convocatoria de prueba',
    bdns: { authorityHierarchy: { nivel3: 'AYUNTAMIENTO DE BORRIANA/BURRIANA' } },
    extra: {
      geography: { municipality: 'Borriana/Burriana', province: 'Castellón/Castelló' },
      territorialMatches: [{ reason: 'official_code_match', entityCode: '12031', entityName: 'Borriana/Burriana', field: 'title', matchedText: 'Burriana', method: 'official_variant' }],
    },
  });
  const query = queryOf(buildExternalSearchHref(withTerritory));
  for (const forbidden of ['infocs:bdns', HASH, '12031', 'Castellón/Castelló']) {
    assert.ok(!query.includes(forbidden), `no debe incluir ${forbidden}`);
  }
});

// --- 4/5/6. Component contract -----------------------------------------------------------------
const componentUrl = new URL('../src/components/ExternalSearchLink.astro', import.meta.url);

test('the component opens a new tab with safe link attributes', async () => {
  const component = await readFile(componentUrl, 'utf8');
  assert.match(component, /href=\{href\}/);
  assert.match(component, /target="_blank"/);
  assert.match(component, /rel="noopener noreferrer"/);
  assert.match(component, /referrerpolicy="no-referrer"/);
  assert.match(component, /data-external-search/);
  assert.match(component, />Buscar en Google</);
});

test('the component states external, unverified results and the new-tab warning accessibly', async () => {
  const component = await readFile(componentUrl, 'utf8');
  assert.match(component, /no verificados por InfoCs/);
  assert.match(component, /class="visually-hidden"> \(se abre en una pestaña nueva\)/);
});

test('the component never triggers a search on load', async () => {
  const component = await readFile(componentUrl, 'utf8');
  assert.doesNotMatch(component, /<script|<form|fetch\(|XMLHttpRequest|window\.|onload|autofocus/i);
});

test('secondary CTA has decorative icons and a separate associated warning', async () => {
  const component = await readFile(componentUrl, 'utf8');
  assert.match(component, /class="external-search-link"/);
  assert.doesNotMatch(component, /class="text-link/);
  assert.equal((component.match(/<svg aria-hidden="true" focusable="false"/g) ?? []).length, 2);
  assert.match(component, /aria-describedby="external-search-note"/);
  assert.match(component, /<\/a>\s*<p class="fact-note" id="external-search-note">Búsqueda externa:/);
  const css = await readFile(new URL('../src/styles/global.css', import.meta.url), 'utf8');
  const button = css.match(/\.external-search-link \{([^}]+)\}/)?.[1] ?? '';
  assert.match(button, /min-height: var\(--control-md\)/);
  assert.match(button, /min-width: var\(--control-md\)/);
  assert.match(button, /border: var\(--border-1\) solid var\(--color-accent\)/);
  assert.match(css, /\.external-search-link:focus-visible\s*\{[^}]*outline:/);
});

// --- 7/8/9. Extracts ---------------------------------------------------------------------------
test('official extract metadata is projected literally, with its own date role', () => {
  const view = buildBDNSExtractsView([{
    diary: 'B.O.P. DE CASTELLÓN',
    publicationDate: '2026-10-22',
    title: 'XLVIII Concurso de tarjetas de Navidad',
    titleCoofficial: 'XLVIII Concurs de targetes de Nadal',
    cve: 'BOP-2026-1',
    sourceUrl: 'https://example.test/not-used',
  }], 'Convocatoria de prueba', viewFactory);
  assert.equal(view.items.length, 1);
  const [item] = view.items;
  assert.equal(item.diary.value, 'B.O.P. DE CASTELLÓN');
  assert.equal(item.publicationDate.value, '2026-10-22');
  assert.equal(item.publicationDate.label, 'Fecha del extracto');
  assert.equal(item.title.value, 'XLVIII Concurso de tarjetas de Navidad');
  assert.equal(item.titleCoofficial.value, 'XLVIII Concurs de targetes de Nadal');
  assert.equal(item.cve.value, 'BOP-2026-1');
  assert.equal('sourceUrl' in item, false, 'el localizador no se proyecta en 03B-1');
});

test('empty extracts produce no section; the publication flag is never an input', () => {
  // The builder receives only the extracts list. `extract_published_in_official_diary`
  // cannot manufacture an item; the real flag-true/empty case is checked on the build.
  assert.equal(buildBDNSExtractsView([], 'Convocatoria de prueba', viewFactory).items.length, 0);
  const locatorOnly = buildBDNSExtractsView([{ sourceUrl: 'https://example.test' }], 'Convocatoria de prueba', viewFactory);
  assert.equal(locatorOnly.items.length, 0, 'sin metadatos legibles no se inventa un extracto');
});

test('an extract title equal to the page title is not duplicated', () => {
  const view = buildBDNSExtractsView(
    [{ title: '  Convocatoria   de prueba ', diary: 'B.O.P. DE CASTELLÓN' }],
    'Convocatoria de prueba',
    viewFactory,
  );
  assert.equal(view.items[0].title, undefined);
  assert.equal(view.items[0].diary.value, 'B.O.P. DE CASTELLÓN');
});

// --- 10. Built pages ----------------------------------------------------------------------------
const DIST = new URL('../dist/', import.meta.url);
const DATA = new URL('../../data/records/', import.meta.url);
const built = existsSync(new URL('registros/index.html', DIST));
const decode = (text) => text.replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
  .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
  .replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const slugOf = (id) => `r-${Buffer.from(id, 'utf8').toString('hex')}`;

async function publicRecords(source) {
  const dir = new URL(`${source}/`, DATA);
  const names = (await readdir(dir)).filter((name) => name.endsWith('.json'));
  return Promise.all(names.map(async (name) => JSON.parse(await readFile(join(fileURLToPath(dir), name), 'utf8'))));
}

const pageOf = async (record) => readFile(new URL(`registro/${slugOf(record.id)}/index.html`, DIST), 'utf8');
const visibleExtracts = (record) => (record.source_data?.bdns?.extracts ?? []).filter((extract) =>
  ['diary', 'publication_date', 'title', 'title_coofficial', 'cve'].some((key) => typeof extract[key] === 'string' && extract[key].trim()));

test('built BDNS and BOE fiches keep the official link and add the Google link below it', { skip: !built }, async () => {
  for (const source of ['bdns', 'boe']) {
    for (const item of await publicRecords(source)) {
      const html = await pageOf(item);
      const official = html.indexOf('source-link-primary');
      const actions = html.indexOf('class="key-facts-actions"');
      const google = html.indexOf('data-external-search');
      assert.ok(actions >= 0 && official > actions, `enlace oficial fuera de .key-facts-actions: ${item.id}`);
      assert.ok(google > official, `Google debe ir después del enlace oficial: ${item.id}`);
      assert.ok(html.includes('no verificados por InfoCs'), `aviso visible ausente: ${item.id}`);
      assert.ok(html.includes('(se abre en una pestaña nueva)'), `aviso accesible ausente: ${item.id}`);
      // Locate the whole opening tag: no fixed character window around the attribute.
      const tagEnd = html.indexOf('>', google);
      const tagStart = html.lastIndexOf('<a ', google);
      assert.ok(tagStart >= 0 && tagEnd > google, `ancla de Google mal formada: ${item.id}`);
      const anchor = html.slice(tagStart, tagEnd + 1);
      assert.match(anchor, /target="_blank"/);
      assert.match(anchor, /rel="noopener noreferrer"/);
      assert.match(anchor, /referrerpolicy="no-referrer"/);
      assert.match(anchor, /aria-describedby="external-search-note"/);
      assert.equal((html.match(/id="external-search-note"/g) ?? []).length, 1);
      assert.match(anchor, /^<a\s[^>]*href="https:\/\/www\.google\.com\/search\?q=[^"]+"[^>]*>$/);
      const href = decode(anchor.match(/\shref="([^"]*)"/)[1]);
      const url = new URL(href);
      assert.equal(url.origin, 'https://www.google.com');
      assert.equal(url.pathname, '/search');
      assert.deepEqual([...url.searchParams.keys()], ['q']);
      const query = url.searchParams.get('q');
      assert.ok(query.includes(item.title.replace(/\s+/gu, ' ').trim()), `título ausente en la consulta: ${item.id}`);
      if (source === 'boe' && item.authority?.name) {
        assert.ok(!query.includes(item.authority.name), `sección del BOE usada como organismo: ${item.id}`);
      }
      if (source === 'bdns') {
        const hierarchy = item.source_data?.bdns?.authority_hierarchy;
        const specific = hierarchy?.nivel3 ?? hierarchy?.nivel2;
        if (specific) assert.ok(query.includes(specific), `organismo específico ausente: ${item.id}`);
      }
      assert.ok(decode(html).includes('href="' + item.source_url + '"'), `enlace oficial original ausente: ${item.id}`);
    }
  }
});

test('built pages: Google is a voluntary link, never an automatic request, and only on fiches', { skip: !built }, async () => {
  const fiche = await pageOf((await publicRecords('bdns'))[0]);
  for (const match of fiche.matchAll(/\s(href|src|action)="([^"]*google\.com[^"]*)"/gi)) {
    assert.equal(match[1], 'href', 'Google sólo puede aparecer como href');
  }
  assert.doesNotMatch(fiche, /<link[^>]+google\.com|preconnect|dns-prefetch/i);
  for (const path of ['index.html', 'registros/index.html', 'cambios/index.html', 'buscar/index.html']) {
    const html = await readFile(new URL(path, DIST), 'utf8');
    assert.doesNotMatch(html, /data-external-search|google\.com\/search/, `enlace fuera de la ficha: ${path}`);
  }
});

test('built fiches: extract sections match the metadata, the flag alone adds nothing', { skip: !built }, async () => {
  const bdns = await publicRecords('bdns');
  let expected = 0;
  for (const item of bdns) {
    const html = await pageOf(item);
    const sections = (html.match(/id="bdns-extracts-title"/g) ?? []).length;
    const extracts = visibleExtracts(item);
    if (extracts.length === 0) {
      assert.equal(sections, 0, `sección de extractos sin metadatos: ${item.id}`);
      continue;
    }
    expected += 1;
    assert.equal(sections, 1, `sección de extractos ausente: ${item.id}`);
    for (const extract of extracts) {
      if (extract.diary) assert.ok(decode(html).includes(extract.diary), `diario literal ausente: ${item.id}`);
      if (extract.publication_date) assert.ok(html.includes(`datetime="${extract.publication_date}"`), `fecha literal ausente: ${item.id}`);
      if (extract.cve) assert.ok(decode(html).includes(extract.cve), `CVE literal ausente: ${item.id}`);
    }
  }
  const all = await Promise.all(bdns.map((item) => pageOf(item)));
  assert.equal(all.reduce((total, html) => total + (html.match(/id="bdns-extracts-title"/g) ?? []).length, 0), expected);
});

test('built search corpus excludes technical URLs, hashes and internal identifiers', { skip: !built }, async () => {
  for (const item of await publicRecords('bdns')) {
    const html = await pageOf(item);
    const corpus = html.match(/<div class="record-search-content"[^>]*>([\s\S]*?)<\/div>/)?.[1] ?? '';
    assert.ok(corpus.length > 0, `corpus Pagefind ausente: ${item.id}`);
    assert.doesNotMatch(corpus, /https?:\/\//i, `URL técnica en el corpus: ${item.id}`);
    assert.doesNotMatch(corpus, /infocs:/i, `ID interno en el corpus: ${item.id}`);
    assert.ok(!corpus.includes(item.technical.content_hash), `hash en el corpus: ${item.id}`);
  }
});

test('built fiches: no SNPSAP ficha link and no automatic clickability for locators', { skip: !built }, async () => {
  for (const item of await publicRecords('bdns')) {
    const html = decode(await pageOf(item));
    assert.doesNotMatch(html, /bdnstrans\/GE\/es\/convocatorias\//, `ficha SNPSAP prematura: ${item.id}`);
    const locator = item.source_data.bdns.regulatory_bases?.source_locator;
    if (typeof locator === 'string' && locator.trim()) {
      assert.ok(!html.includes(`href="${locator}"`), `localizador convertido en enlace: ${item.id}`);
    }
    if (item.source_data.bdns.electronic_office_url) {
      assert.ok(!html.includes(`href="${item.source_data.bdns.electronic_office_url}"`), `sede convertida en enlace: ${item.id}`);
    }
  }
});
