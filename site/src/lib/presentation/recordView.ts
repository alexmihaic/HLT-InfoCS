import type { FrontendRecord } from '../data/types';
import type { FrontendEvent } from '../data/types';
import { eventDescription } from './labels';
import { formatPortalDate } from './dates';

export interface PrimaryDateView {
  readonly value: string;
  readonly label: 'Publicado' | 'Detectado por InfoCs';
  readonly display: string;
}

export function primaryDate(record: FrontendRecord): PrimaryDateView {
  const value = record.publishedAt ?? record.detectedAt;
  return {
    value,
    label: record.publishedAt ? 'Publicado' : 'Detectado por InfoCs',
    display: formatPortalDate(value),
  };
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
