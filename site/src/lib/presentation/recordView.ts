import type { FrontendRecord } from '../data/types';
import type { FrontendEvent } from '../data/types';
import { eventDescription } from './labels';
import { formatPortalDate } from './dates';

export interface PrimaryDateView {
  readonly value: string;
  readonly label: 'Publicado' | 'Recibida en BDNS' | 'Detectado por InfoCs';
  readonly display: string;
}

/**
 * Official date first: publication date, then the official BDNS reception date
 * (which is not a publication date), and only then InfoCs' own observation.
 */
export function primaryDate(record: FrontendRecord): PrimaryDateView {
  if (record.publishedAt) {
    return { value: record.publishedAt, label: 'Publicado', display: formatPortalDate(record.publishedAt) };
  }
  const received = record.sourceId === 'bdns' ? record.bdns?.receivedDate : undefined;
  if (received) {
    return { value: received, label: 'Recibida en BDNS', display: formatPortalDate(received) };
  }
  return { value: record.detectedAt, label: 'Detectado por InfoCs', display: formatPortalDate(record.detectedAt) };
}

/** Most recent first by the displayed primary date, then by InfoCs detection. */
export function byPrimaryDateDesc(left: FrontendRecord, right: FrontendRecord): number {
  return primaryDate(right).value.localeCompare(primaryDate(left).value)
    || right.detectedAt.localeCompare(left.detectedAt)
    || left.id.localeCompare(right.id);
}

export interface OfficialDeadlineView {
  readonly label: 'Plazo (dato oficial)';
  readonly date?: { readonly value: string; readonly display: string };
  readonly text?: string;
}

/**
 * Literal BDNS application end as supplied by the source. It never derives an
 * open/closed state and never compares against the current date.
 */
export function officialDeadline(record: FrontendRecord): OfficialDeadlineView | null {
  if (record.sourceId !== 'bdns') return null;
  const application = record.bdns?.application;
  const endDate = application?.endDate;
  const endText = application?.endText?.trim() ? application.endText : undefined;
  if (endDate === undefined && endText === undefined) return null;
  return {
    label: 'Plazo (dato oficial)',
    ...(endDate !== undefined ? { date: { value: endDate, display: formatPortalDate(endDate) } } : {}),
    ...(endText !== undefined ? { text: endText } : {}),
  };
}

/**
 * BOE `authority` holds the department heading of the BOE summary, not the
 * issuing body of the act; it is presented as such.
 */
export function authorityPresentation(record: FrontendRecord): { readonly label: string; readonly value: string } | null {
  if (!record.authority) return null;
  if (record.sourceId === 'boe') return { label: 'Sección del BOE', value: record.authority.name };
  return { label: 'Organismo', value: record.authority.name };
}

/** BOE administration level reflects the publisher, not the act's real scope. */
export function showsAdministrationLevel(record: FrontendRecord): boolean {
  return record.sourceId !== 'boe' && record.administrationLevel !== null;
}

export function geographyLabels(record: FrontendRecord): readonly string[] {
  if (!record.geography) return [];
  return [
    ...(record.geography.municipality ? [`Municipio: ${record.geography.municipality}`] : []),
    ...(record.geography.province ? [`Provincia: ${record.geography.province}`] : []),
  ];
}

export interface TimelineItem {
  readonly eventId: string;
  readonly description: string;
  readonly value: string;
  readonly display: string;
}

export function timelineItems(events: readonly FrontendEvent[]): readonly TimelineItem[] {
  return events.map((event) => ({
    eventId: event.eventId,
    description: eventDescription(event),
    value: event.observedAt,
    display: formatPortalDate(event.observedAt),
  }));
}
