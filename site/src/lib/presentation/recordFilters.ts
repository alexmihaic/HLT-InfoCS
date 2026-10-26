/** Visible-count text for the record list; also the content of its status region. */
export function recordCountLabel(visible: number, total: number): string {
  return visible === total
    ? `${total} ${total === 1 ? 'registro publicado' : 'registros publicados'}`
    : `${visible} de ${total} registros publicados`;
}

/** URL value of the "BDNS record without an official call type" option. Never an official literal. */
export const NO_CALL_TYPE = 'sin-tipo-indicado';

interface CallTypeSource {
  readonly sourceId: string;
  readonly bdns?: { readonly callType?: string };
}

export interface CallTypeOption {
  readonly value: string;
  readonly label: string;
  readonly count: number;
}

/**
 * Value used by the BDNS call-type filter for a record: the literal official
 * `call_type`, the neutral "none" marker for a BDNS record that lacks it, or
 * `undefined` for any non-BDNS record (which can never match this filter).
 */
export function callTypeValue(record: CallTypeSource): string | undefined {
  if (record.sourceId !== 'bdns') return undefined;
  const value = record.bdns?.callType;
  return value !== undefined && value.trim() !== '' && value !== NO_CALL_TYPE ? value : NO_CALL_TYPE;
}

/** Options derived only from the official values present in the given records, in Spanish alphabetical order. */
export function callTypeOptions(records: readonly CallTypeSource[]): CallTypeOption[] {
  const counts = new Map<string, number>();
  for (const record of records) {
    const value = callTypeValue(record);
    if (value !== undefined) counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count, label: value === NO_CALL_TYPE ? 'Sin tipo indicado por BDNS' : value }))
    .sort((left, right) => {
      if (left.value === NO_CALL_TYPE) return 1;
      if (right.value === NO_CALL_TYPE) return -1;
      return left.label.localeCompare(right.label, 'es');
    });
}

export interface RecordFilterSelection {
  readonly category: string;
  readonly municipality: string;
  readonly callType: string;
}

export interface RecordFilterAttributes {
  readonly category?: string;
  readonly municipality?: string;
  readonly callType?: string;
}

/** An empty selection value means "no restriction"; the three filters combine with AND. */
export function matchesRecordFilters(item: RecordFilterAttributes, selection: RecordFilterSelection): boolean {
  return (!selection.category || item.category === selection.category)
    && (!selection.municipality || item.municipality === selection.municipality)
    && (!selection.callType || item.callType === selection.callType);
}

/** Keeps only a value present among the allowed options; unknown or malformed values are ignored. */
export function sanitizeFilterValue(value: string | null, allowed: readonly string[]): string {
  return value !== null && allowed.includes(value) ? value : '';
}
