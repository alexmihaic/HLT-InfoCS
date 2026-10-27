import type { FrontendRecord } from '../data/types';

/**
 * External search is a presentation aid, not an official source. Queries are built
 * only from values already shown on the public detail page: the official title and,
 * for BDNS, the most specific official authority name. Never internal IDs, hashes,
 * technical metadata or InfoCs-derived territory.
 */
const GOOGLE_SEARCH = 'https://www.google.com/search';

/** Administrative-level words that do not identify an organism by themselves. */
const GENERIC_AUTHORITY_LABELS = new Set([
  'ADMINISTRACIÓN GENERAL DEL ESTADO',
  'ADMINISTRACION GENERAL DEL ESTADO',
  'AUTONOMICA',
  'AUTONÓMICA',
  'ESTADO',
  'ESTATAL',
  'LOCAL',
  'OTROS',
]);

/** Fixed Google destination. Encoding only; no API, request or tracking parameter. */
export function googleSearchHref(query: string): string | null {
  // Collapse repeated whitespace for the query only; the stored title is untouched.
  const normalized = query.replace(/\s+/gu, ' ').trim();
  if (!normalized) return null;
  return `${GOOGLE_SEARCH}?${new URLSearchParams({ q: normalized })}`;
}

/**
 * Most specific official BDNS authority name. BOE `authority` is the BOE summary
 * section, not the issuing body, so it is never used as an organism.
 */
export function searchOrganism(record: FrontendRecord): string | undefined {
  if (record.sourceId !== 'bdns') return undefined;
  const hierarchy = record.bdns?.authorityHierarchy;
  const candidates = [hierarchy?.nivel3, hierarchy?.nivel2, record.authority?.name];
  for (const candidate of candidates) {
    const value = typeof candidate === 'string' ? candidate.replace(/\s+/gu, ' ').trim() : '';
    if (value && !GENERIC_AUTHORITY_LABELS.has(value.toLocaleUpperCase('es'))) return value;
  }
  return undefined;
}

export function buildExternalSearchHref(record: FrontendRecord): string | null {
  const title = record.title.replace(/\s+/gu, ' ').trim();
  if (!title) return null;
  const organism = searchOrganism(record);
  return googleSearchHref(organism ? `${title} ${organism}` : title);
}
