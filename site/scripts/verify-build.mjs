// Verifies the built static portal in site/dist against the canonical public
// data in ../data. No dependencies, no network. Run after `npm run build`:
//   node scripts/verify-build.mjs
// Diagnostics are public in CI: they name rules and use opaque labels
// (source + ordinal) instead of official IDs, slugs or paths that encode them.
import { existsSync } from 'node:fs';
import { readdir, readFile } from 'node:fs/promises';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(SITE, 'dist');
const DATA = resolve(SITE, '..', 'data');
const HOME_LIMIT = 10;
const FRESHNESS_CLAIMS = [/tiempo real/i, /actualizad[oa] hoy/i, /siempre actualizad/i, /al minuto/i];
const STATE_CLAIMS = [/abierta ahora/i, /plazo abierto/i, /plazo cerrado/i, /convocatoria cerrada/i];

const failures = [];
const fail = (rule, where) => failures.push(`${rule}${where ? ` — ${where}` : ''}`);

async function files(directory, suffix) {
  if (!existsSync(directory)) return [];
  const result = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) result.push(...await files(path, suffix));
    else if (entry.isFile() && entry.name.endsWith(suffix)) result.push(path);
  }
  return result.sort();
}

async function json(path) {
  try { return JSON.parse(await readFile(path, 'utf8')); } catch { return undefined; }
}

const page = (...parts) => join(DIST, ...parts, 'index.html');
const readPage = async (path) => (existsSync(path) ? readFile(path, 'utf8') : undefined);
const encodeRecordId = (id) => `r-${Buffer.from(id, 'utf8').toString('hex')}`;
const show = (path) => relative(DIST, path).split(sep).join('/');
// Opaque labels, filled once records and organism slugs are known.
const recordLabels = new Map(); // record slug -> records/<source>#<ordinal>
const organismLabels = new Map(); // organism slug -> organismos#<ordinal>
const pageLabel = (path) => {
  const parts = show(path).split('/');
  if (parts[0] === 'registro' && parts.length > 1) return recordLabels.get(parts[1]) ?? 'registro/(sin Record)';
  if (parts[0] === 'organismos' && parts.length > 2) return organismLabels.get(parts[1]) ?? 'organismos/(desconocido)';
  return parts.join('/');
};
const count = (text, pattern) => (text.match(pattern) ?? []).length;
const decode = (text) => text.replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
  .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
  .replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const authoritySlugOf = (record) => {
  const name = record.source_data?.bdns?.authority_hierarchy?.nivel2;
  if (typeof name !== 'string') return null;
  return name.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '').slice(0, 80).replace(/-+$/g, '') || null;
};
const visibleText = (html) => decode(html.replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ').replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ');

if (!existsSync(DIST)) {
  console.error('verify-build: site/dist no existe; ejecuta antes `npm run build`.');
  process.exit(1);
}

// --- Canonical data -----------------------------------------------------------
const records = [];
for (const path of await files(join(DATA, 'records'), '.json')) {
  const payload = await json(path);
  if (payload && typeof payload.id === 'string') records.push(payload);
}

// --- 1. Record pages reference real Records; publishing is all-or-nothing per source
{
  const perSource = new Map();
  for (const record of records) {
    const source = /^[a-z0-9_-]{1,64}$/.test(record.source?.id ?? '') ? record.source.id : '?';
    perSource.set(source, (perSource.get(source) ?? 0) + 1);
    recordLabels.set(encodeRecordId(record.id), `records/${source}#${perSource.get(source)}`);
  }
}
const recordPages = (await files(join(DIST, 'registro'), 'index.html'));
const pageSlugs = new Set(recordPages.map((path) => relative(join(DIST, 'registro'), dirname(path)).split(sep).join('/')));
const slugToRecord = new Map(records.map((record) => [encodeRecordId(record.id), record]));
for (const slug of pageSlugs) if (!slugToRecord.has(slug)) fail('ficha sin Record canónico');
const publishedSources = new Set([...pageSlugs].map((slug) => slugToRecord.get(slug)?.source?.id).filter(Boolean));
for (const record of records) {
  if (publishedSources.has(record.source.id) && !pageSlugs.has(encodeRecordId(record.id))) {
    fail('Record de fuente publicada sin ficha', record.source.id);
  }
}
if (publishedSources.has('bop_castellon')) fail('BOP Castellón tiene fichas públicas pese al hold de reutilización');
const publishedRecords = records.filter((record) => publishedSources.has(record.source.id));

// --- 2. Home: purpose, coverage, dates, queue count, limit ------------------------
const home = await readPage(page());
if (!home) fail('falta la portada');
else {
  const text = visibleText(home);
  for (const required of ['Qué puedes consultar', 'Qué fuentes tienen contenido público', 'Qué no cubre todavía InfoCs', 'Portal generado el']) {
    if (!text.includes(required)) fail(`la portada no contiene «${required}»`);
  }
  if (!text.includes(`${publishedRecords.length} registros publicados`)) fail('la portada no muestra el total de registros publicados');
  for (const sourceId of publishedSources) {
    const health = await json(join(DATA, 'health', `${sourceId}.json`));
    if (health?.last_success_at) {
      if (!home.includes(`datetime="${health.last_success_at}"`)) fail('la portada no muestra la última ejecución satisfactoria registrada', sourceId);
    }
  }
  const queue = await json(join(DATA, 'review', 'boe', 'pending.json'));
  if (Array.isArray(queue?.records) && publishedSources.has('boe')) {
    if (!/Detectadas y pendientes de revisión \(no publicadas\)\s*<\/dt>\s*<dd[^>]*>\s*(\d+)\s*</.test(home)
      || Number(home.match(/Detectadas y pendientes de revisión \(no publicadas\)\s*<\/dt>\s*<dd[^>]*>\s*(\d+)\s*</)[1]) !== queue.records.length) {
      fail('la portada no muestra el número agregado de la cola BOE');
    }
    for (const entry of queue.records) {
      if (typeof entry.official_id === 'string' && home.includes(entry.official_id)) fail('la portada expone un elemento pendiente de revisión');
    }
  }
  const listMatch = home.match(/<ol class="record-list"[^>]*>([\s\S]*?)<\/ol>/);
  const homeCards = listMatch ? count(listMatch[1], /data-record-item/g) : 0;
  if (homeCards !== Math.min(HOME_LIMIT, publishedRecords.length)) fail(`la portada debe listar ${Math.min(HOME_LIMIT, publishedRecords.length)} registros recientes`, `${homeCards}`);
  if (!home.includes('href="/registros/"')) fail('la portada no enlaza a todos los registros');
  for (const pattern of FRESHNESS_CLAIMS) if (pattern.test(text)) fail('afirmación de frescura no acreditada en portada', String(pattern));
}

// --- 3. All records page ------------------------------------------------------------
const allPage = await readPage(page('registros'));
if (!allPage) fail('falta /registros/');
else if (count(allPage, /data-record-item/g) !== publishedRecords.length) fail('/registros/ no lista todos los registros publicados');

// --- 4. Organisms --------------------------------------------------------------------
const organismIndex = await readPage(page('organismos'));
if (!organismIndex) fail('falta /organismos/');
else {
  if (!visibleText(organismIndex).includes('Administración convocante (según BDNS)')) fail('/organismos/ no etiqueta el campo como dato BDNS');
  const slugs = [...organismIndex.matchAll(/href="\/organismos\/([^"/]+)\/"/g)].map((match) => match[1]);
  slugs.forEach((slug, index) => { if (!organismLabels.has(slug)) organismLabels.set(slug, `organismos#${index + 1}`); });
  if (new Set(slugs).size !== slugs.length) fail('slugs de organismo duplicados');
  const expected = new Map();
  for (const record of publishedRecords) {
    const name = record.source.id === 'bdns' ? record.source_data?.bdns?.authority_hierarchy?.nivel2 : undefined;
    if (typeof name === 'string' && name.trim()) expected.set(name, (expected.get(name) ?? 0) + 1);
  }
  if (slugs.length !== expected.size) fail('número de organismos distinto de los valores nivel2 publicados', `${slugs.length}/${expected.size}`);
  let grouped = 0;
  for (const slug of slugs) {
    const html = await readPage(page('organismos', slug));
    if (!html) { fail('página de organismo inexistente', organismLabels.get(slug)); continue; }
    const links = [...html.matchAll(/<h3[^>]*><a href="\/registro\/([^"/]+)\/">/g)].map((match) => match[1]);
    if (links.length === 0) fail('organismo sin registros', organismLabels.get(slug));
    for (const recordSlug of links) {
      const record = slugToRecord.get(recordSlug);
      if (!record || !pageSlugs.has(recordSlug)) fail('organismo enlaza un registro inexistente', organismLabels.get(slug));
      else if (record.source.id !== 'bdns') fail('organismo agrupa un registro no BDNS', organismLabels.get(slug));
      else if (authoritySlugOf(record) !== slug) fail('registro agrupado bajo un organismo distinto de su nivel2', organismLabels.get(slug));
    }
    grouped += links.length;
  }
  const expectedTotal = [...expected.values()].reduce((sum, value) => sum + value, 0);
  if (grouped !== expectedTotal) fail('los organismos no cubren exactamente los registros BDNS con nivel2', `${grouped}/${expectedTotal}`);
}

// --- 5. Record detail presentation rules ---------------------------------------------
for (const record of publishedRecords) {
  const html = await readPage(page('registro', encodeRecordId(record.id)));
  if (!html) continue;
  const where = recordLabels.get(encodeRecordId(record.id));
  if (record.source.id === 'boe') {
    if (html.includes('<dt>Nivel administrativo</dt>')) fail('ficha BOE muestra «Nivel administrativo»', where);
    if (html.includes('<dt>Organismo</dt>')) fail('ficha BOE presenta la sección del sumario como «Organismo»', where);
    if (record.authority && !html.includes('<dt>Sección del BOE</dt>')) fail('ficha BOE no etiqueta «Sección del BOE»', where);
  }
  const text = visibleText(html);
  for (const pattern of STATE_CLAIMS) if (pattern.test(text)) fail('estado administrativo inferido en ficha', where);
}

// --- 6. BDNS card dates and deadlines --------------------------------------------------
if (allPage) {
  const text = visibleText(allPage);
  const bdns = publishedRecords.filter((record) => record.source.id === 'bdns');
  // An official publication date takes precedence over the BDNS reception date.
  const received = bdns.filter((record) => record.source_data?.bdns?.received_date && !record.dates?.published_at).length;
  const published = bdns.filter((record) => record.dates?.published_at).length;
  if (count(allPage, /data-date-kind="published"/g) < published) fail('tarjetas BDNS con fecha oficial de publicación sin «Publicado»');
  const receivedCount = count(allPage, /data-date-kind="received"[^>]*>\s*<span class="date-stamp-label">Recibida en BDNS<\/span>/g);
  if (receivedCount !== received) fail('tarjetas BDNS sin «Recibida en BDNS» o con etiqueta indebida', `${receivedCount}/${received}`);
  const withDeadline = bdns.filter((record) => {
    const application = record.source_data?.bdns?.application;
    return application?.end_date || application?.end_text?.trim();
  }).length;
  if (count(text, /Plazo \(dato oficial\)/g) !== withDeadline) fail('tarjetas BDNS sin «Plazo (dato oficial)»', `${count(text, /Plazo \(dato oficial\)/g)}/${withDeadline}`);
  for (const pattern of STATE_CLAIMS) if (pattern.test(text)) fail('estado administrativo inferido en tarjetas', String(pattern));
}

// --- 6b. Shared UI controls and record detail order ---------------------------------
for (const path of [page(), page('registros')]) {
  const html = await readPage(path);
  if (html && !html.includes('data-view-toggle')) fail('listado sin control Lista/Tarjetas', show(path));
}
if (home && (!home.includes('data-theme-select') || !home.includes('value="auto"'))) fail('falta el selector de tema Automático/Claro/Oscuro');
for (const record of publishedRecords) {
  const html = await readPage(page('registro', encodeRecordId(record.id)));
  if (!html) continue;
  const where = recordLabels.get(encodeRecordId(record.id));
  const titleAt = html.indexOf('<h1');
  const linkAt = html.indexOf('source-link-primary');
  const layoutAt = html.indexOf('class="detail-layout"');
  if (linkAt < 0 || !(titleAt < linkAt && linkAt < layoutAt)) fail('el enlace oficial no aparece justo después del título', where);
  if (record.source.id === 'bdns' && linkAt >= 0 && !/source-link-primary[^>]*>[^<]*JSON/.test(html.slice(linkAt - 200, linkAt + 400))) {
    fail('el enlace BDNS no indica que abre JSON de la API', where);
  }
}

// --- 6c. Derived municipality (EMPLEO-01) -------------------------------------------
// Mirrors territory.ts: one distinct exact INE municipality match in the BOE title.
const expectedMunicipality = (record) => {
  if (record.source.id !== 'boe') return null;
  const matches = (record.provenance?.territorial_matches ?? []).map((match) => {
    try { return JSON.parse(match.detail); } catch { return null; }
  }).filter((d) => d && d.boe_reason === 'municipality_exact' && d.field === 'title'
    && String(d.method).startsWith('official_variant') && /^12\d{3}$/.test(d.entity_code)
    && String(d.entity_name).split('/').map((v) => v.trim()).includes(d.matched_text));
  const codes = new Set(matches.map((d) => d.entity_code));
  if (codes.size !== 1) return null;
  const issuer = /^(?:Resolución de \d{1,2} de [a-záéíóú]+ de \d{4}, del|Anuncio del|Edicto del) Ayuntamiento de /u.exec(record.title);
  const rest = issuer ? record.title.slice(issuer[0].length) : '';
  const convocante = matches.some((d) => issuer && rest.startsWith(d.matched_text) && !/^[\p{L}\p{N}]/u.test(rest.slice(d.matched_text.length)));
  return { code: matches[0].entity_code, label: convocante ? 'Municipio convocante' : 'Municipio relacionado' };
};
if (allPage) {
  const filters = allPage.includes('data-record-filters');
  if (!filters) fail('/registros/ sin filtros de tipo y municipio');
  for (const record of publishedRecords) {
    const expected = expectedMunicipality(record);
    const slug = encodeRecordId(record.id);
    const where = recordLabels.get(slug);
    const li = allPage.match(new RegExp(`<li[^>]*>(?:(?!<li[ >]).)*?href="/registro/${slug}/"`, 's'));
    const attr = li ? (li[0].match(/^<li[^>]*data-municipality="([^"]*)"/) ?? [])[1] : undefined;
    if ((expected?.code) !== attr) fail('municipio derivado distinto del esperado en el listado', where);
    const html = await readPage(page('registro', slug));
    if (!html) continue;
    if (expected && !html.includes(`<dt>${expected.label}</dt>`)) fail('ficha sin municipio derivado esperado', where);
    if (!expected && /<dt>Municipio (convocante|relacionado)<\/dt>/.test(html)) fail('ficha con municipio sin evidencia suficiente', where);
  }
}

// --- 7. Links: allowed protocols and internal targets ------------------------------
const SAFE_EXTERNAL = /^https:\/\//i;
const HAS_SCHEME = /^[a-z][a-z0-9+.-]*:/i;
for (const path of await files(DIST, '.html')) {
  const html = await readFile(path, 'utf8');
  for (const match of html.matchAll(/\s(href|src|action)\s*=\s*"([^"]*)"/gi)) {
    const value = decode(match[2]).trim();
    if (value === '' || value.startsWith('#')) continue;
    if (HAS_SCHEME.test(value)) {
      if (!SAFE_EXTERNAL.test(value)) fail(`protocolo no permitido en ${match[1]}`, `${pageLabel(path)}: ${/^[a-z][a-z0-9+.-]{0,15}$/i.test(value.split(':')[0]) ? value.split(':')[0] : '?'}:`);
      continue;
    }
    if (value.startsWith('//')) { fail('URL relativa al protocolo', pageLabel(path)); continue; }
    const clean = value.split(/[?#]/)[0];
    const target = clean.startsWith('/') ? join(DIST, clean) : resolve(dirname(path), clean);
    if (!target.startsWith(DIST)) { fail('enlace interno fuera del sitio', pageLabel(path)); continue; }
    const candidates = clean.endsWith('/') ? [join(target, 'index.html')] : [target, `${target}.html`, join(target, 'index.html')];
    if (!candidates.some((candidate) => existsSync(candidate))) fail('enlace interno roto', `${pageLabel(path)} → ${pageLabel(target)}`);
  }
}

if (failures.length > 0) {
  console.error(`verify-build: ${failures.length} comprobación(es) fallida(s):`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`verify-build: OK — ${recordPages.length} fichas, ${publishedRecords.length} registros publicados, fuentes: ${[...publishedSources].sort().join(', ')}.`);
