import type { FrontendRecord } from '../data/types';
import type { BDNSRecordView } from './bdnsRecordView';
import type { PrimaryDateView } from './recordView';

interface SearchDocumentInput {
  readonly record: FrontendRecord;
  readonly bdnsView: BDNSRecordView | null;
  readonly source: string;
  readonly category: string;
  readonly authority: { readonly label: string; readonly value: string } | null;
  readonly date: PrimaryDateView;
  readonly eventDate?: string;
  readonly geographies: readonly string[];
  readonly municipality: { readonly label: string; readonly name: string; readonly code?: string } | null;
  readonly administrationLabel?: string;
}

/** Only values already exposed on the public detail page. No canonical mutation,
 * new source fields, ranking, deadline inference or fallback to private payloads.
 * Paragraph boundaries are explicit; UI labels/sidebars are not the index.
 */
export function buildSearchDocument(input: SearchDocumentInput): { texts: string[]; excerpts: string[] } {
  const { record, bdnsView: view, authority, date } = input;
  const texts: string[] = [];
  const excerpts: string[] = [];
  const seen = new Set<string>();
  const add = (value: string | undefined, label?: string, excerpt = true) => {
    if (!value?.trim()) return;
    const key = value.replace(/\s+/gu, ' ').trim();
    if (seen.has(key)) return;
    seen.add(key);
    const alreadyLabelled = label && (key.toLocaleLowerCase('es') === label.toLocaleLowerCase('es')
      || key.toLocaleLowerCase('es').startsWith(`${label.toLocaleLowerCase('es')} `));
    const text = label && !alreadyLabelled ? `${label}: ${value}` : value;
    texts.push(text);
    if (excerpt) excerpts.push(text);
  };

  // Searchable, but already displayed in the result's title/metadata.
  add(record.title, undefined, false);
  add(input.source, 'Fuente', false);
  add(input.category, 'Tipo', false);
  add(authority?.value, authority?.label, false);
  add(date.display, date.label, false);
  add(view?.callType?.value, view?.callType?.label, false);
  if (view?.budget) add(
    [view.budget.displayValue, view.budget.currency, view.budget.currencyNotice].filter(Boolean).join(' · '),
    view.budget.label, false,
  );

  add(view?.purpose?.value, view?.purpose?.label);
  add(view?.officialTitleCoofficial?.value, view?.officialTitleCoofficial?.label);
  add(input.eventDate, 'Fecha del acto');
  add(record.sourceId === 'boe' ? record.officialId : record.grant?.callId,
    record.sourceId === 'boe' ? 'Identificador BOE' : 'Código BDNS');
  for (const text of input.geographies) add(text);
  add(input.municipality?.name, input.municipality?.label);
  add(input.municipality?.code, 'Código INE del municipio identificado', false);
  add(input.administrationLabel, 'Nivel administrativo');
  if (view) {
    // Preserve all searchable official fields from BDNSHumanReadableDetail.
    // Dates remain literal/formatted source values, never open/closed states.
    for (const boundary of [view.application?.start, view.application?.end]) {
      if (boundary) add([boundary.date?.display, boundary.text?.value].filter(Boolean).join(' · '), boundary.label);
    }
    add(view.receivedDate?.display, view.receivedDate?.label);
    for (const item of view.instruments.items) add(item, view.instruments.label);
    for (const group of [view.beneficiaryTypes, view.sectors]) {
      for (const item of group.items) add(item.label, group.label);
    }
    for (const item of view.impactRegions.items) add(item, view.impactRegions.label);
    for (const level of view.authorityHierarchy?.items ?? []) add(level.value, level.label, false);
    add(view.regulatoryBases?.description?.value, view.regulatoryBases?.description?.label);
    for (const extract of view.extracts.items) {
      add(extract.title?.value, extract.title?.label);
      add(extract.titleCoofficial?.value, extract.titleCoofficial?.label);
      add(extract.diary?.value, extract.diary?.label);
      add(extract.publicationDate?.display, extract.publicationDate?.label);
      add(extract.cve?.value, extract.cve?.label, false);
    }
    for (const document of view.documents.items) {
      add(document.description?.value, document.description?.label);
      add(document.publishedDate?.display, document.publishedDate?.label);
    }
  }
  return { texts, excerpts };
}

const normalizeForMatch = (text: string) => text.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase('es');

/** Select context, not result ranking. Values are plain text metadata produced
 * from the same public projection as the index. Render ONLY via textContent.
 * No HTML decoding: JSON metadata is already decoded once by Pagefind.
 */
export function searchExcerpt(value: unknown, query: string, limit = 240): string | null {
  if (typeof value !== 'string') return null;
  let parsed: unknown;
  try { parsed = JSON.parse(value); } catch { return null; }
  if (!Array.isArray(parsed) || !parsed.every((item) => typeof item === 'string')) return null;
  const contexts = parsed.map((text: string) => text.replace(/\s+/gu, ' ').trim()).filter(Boolean);
  const terms = normalizeForMatch(query).match(/[\p{L}\p{N}]+/gu) ?? [];
  const context = contexts.find((text) => terms.some((term) => normalizeForMatch(text).includes(term)));
  // A metadata-only match needs no redundant excerpt. Missing context stays empty.
  if (!context) return null;
  if (context.length <= limit) return context;
  // Centre a bounded literal excerpt on the matching term, not always the start.
  const matchAt = terms.map((term) => normalizeForMatch(context).indexOf(term)).find((index) => index >= 0) ?? 0;
  let start = Math.max(0, matchAt - Math.floor(limit / 3));
  if (start > 0) {
    const boundary = context.indexOf(' ', start);
    start = boundary >= 0 && boundary < matchAt ? boundary + 1 : 0;
  }
  let end = Math.min(context.length, start + limit);
  if (end < context.length) {
    const boundary = context.lastIndexOf(' ', end);
    if (boundary > start) end = boundary;
  }
  return `${start > 0 ? '…' : ''}${context.slice(start, end)}${end < context.length ? '…' : ''}`;
}
