// Verifies the built static portal in site/dist against the canonical public
// data in ../data. No dependencies, no network. Run after `npm run build`:
//   node scripts/verify-build.mjs
// Diagnostics name pages and rules only; they never print record payloads.
import { existsSync } from 'node:fs';
import { readdir, readFile } from 'node:fs/promises';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(SITE, 'dist');
const DATA = resolve(SITE, '..', 'data');
const HOME_LIMIT = 20;
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
const recordPages = (await files(join(DIST, 'registro'), 'index.html'));
const pageSlugs = new Set(recordPages.map((path) => relative(join(DIST, 'registro'), dirname(path)).split(sep).join('/')));
const slugToRecord = new Map(records.map((record) => [encodeRecordId(record.id), record]));
for (const slug of pageSlugs) if (!slugToRecord.has(slug)) fail('ficha sin Record canónico', `registro/${slug}/`);
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
  const homeCards = listMatch ? count(listMatch[1], /<article class="record-card"/g) : 0;
  if (homeCards !== Math.min(HOME_LIMIT, publishedRecords.length)) fail(`la portada debe listar ${Math.min(HOME_LIMIT, publishedRecords.length)} registros recientes`, `${homeCards}`);
  if (!home.includes('href="/registros/"')) fail('la portada no enlaza a todos los registros');
  for (const pattern of FRESHNESS_CLAIMS) if (pattern.test(text)) fail('afirmación de frescura no acreditada en portada', String(pattern));
}

// --- 3. All records page ------------------------------------------------------------
const allPage = await readPage(page('registros'));
if (!allPage) fail('falta /registros/');
else if (count(allPage, /<article class="record-card"/g) !== publishedRecords.length) fail('/registros/ no lista todos los registros publicados');

// --- 4. Organisms --------------------------------------------------------------------
const organismIndex = await readPage(page('organismos'));
if (!organismIndex) fail('falta /organismos/');
else {
  if (!visibleText(organismIndex).includes('Administración convocante (según BDNS)')) fail('/organismos/ no etiqueta el campo como dato BDNS');
  const slugs = [...organismIndex.matchAll(/href="\/organismos\/([^"/]+)\/"/g)].map((match) => match[1]);
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
    if (!html) { fail('página de organismo inexistente', slug); continue; }
    const links = [...html.matchAll(/<h3><a href="\/registro\/([^"/]+)\/">/g)].map((match) => match[1]);
    if (links.length === 0) fail('organismo sin registros', slug);
    for (const recordSlug of links) {
      const record = slugToRecord.get(recordSlug);
      if (!record || !pageSlugs.has(recordSlug)) fail('organismo enlaza un registro inexistente', slug);
      else if (record.source.id !== 'bdns') fail('organismo agrupa un registro no BDNS', slug);
      else if (authoritySlugOf(record) !== slug) fail('registro agrupado bajo un organismo distinto de su nivel2', slug);
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
  const where = `${record.source.id}:${record.source.official_id ?? '?'}`;
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
  const received = bdns.filter((record) => record.source_data?.bdns?.received_date).length;
  if (count(text, /Recibida en BDNS:/g) !== received) fail('tarjetas BDNS sin «Recibida en BDNS» o con etiqueta indebida', `${count(text, /Recibida en BDNS:/g)}/${received}`);
  const withDeadline = bdns.filter((record) => {
    const application = record.source_data?.bdns?.application;
    return application?.end_date || application?.end_text?.trim();
  }).length;
  if (count(text, /Plazo \(dato oficial\)/g) !== withDeadline) fail('tarjetas BDNS sin «Plazo (dato oficial)»', `${count(text, /Plazo \(dato oficial\)/g)}/${withDeadline}`);
  for (const pattern of STATE_CLAIMS) if (pattern.test(text)) fail('estado administrativo inferido en tarjetas', String(pattern));
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
      if (!SAFE_EXTERNAL.test(value)) fail(`protocolo no permitido en ${match[1]}`, `${show(path)}: ${value.split(':')[0]}:`);
      continue;
    }
    if (value.startsWith('//')) { fail('URL relativa al protocolo', show(path)); continue; }
    const clean = value.split(/[?#]/)[0];
    const target = clean.startsWith('/') ? join(DIST, clean) : resolve(dirname(path), clean);
    if (!target.startsWith(DIST)) { fail('enlace interno fuera del sitio', show(path)); continue; }
    const candidates = clean.endsWith('/') ? [join(target, 'index.html')] : [target, `${target}.html`, join(target, 'index.html')];
    if (!candidates.some((candidate) => existsSync(candidate))) fail('enlace interno roto', `${show(path)} → ${clean}`);
  }
}

if (failures.length > 0) {
  console.error(`verify-build: ${failures.length} comprobación(es) fallida(s):`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`verify-build: OK — ${recordPages.length} fichas, ${publishedRecords.length} registros publicados, fuentes: ${[...publishedSources].sort().join(', ')}.`);
