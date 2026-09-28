import type { FrontendEvent, FrontendRecord, PortalData } from '../data/types';
import { encodeRecordId } from '../data';
import { categoryLabel, eventDescription, sourceLabel } from './labels';
import { formatPortalDate } from './dates';

export interface ChangeItemView {
  readonly typeLabel: 'Incorporación' | 'Actualización';
  readonly description: string;
  readonly observedAt: string;
  readonly observedDate: string;
  readonly recordTitle: string;
  readonly recordHref: string;
  readonly source: string;
  readonly sourceId: string;
  readonly category: string;
}

function eventOrder(left: FrontendEvent, right: FrontendEvent): number {
  const difference = Date.parse(right.observedAt) - Date.parse(left.observedAt);
  return difference || left.eventId.localeCompare(right.eventId);
}

export function changeItems(data: PortalData): readonly ChangeItemView[] {
  const records = new Map<string, FrontendRecord>(data.records.map((record) => [record.id, record]));
  return [...data.events].sort(eventOrder).map((event) => {
    const record = records.get(event.recordId);
    if (!record) throw new Error('Frontend data contract: un cambio público no resuelve su publicación.');
    if (record.sourceId !== event.sourceId) throw new Error('Frontend data contract: la fuente del cambio no coincide con su publicación.');
    return {
      typeLabel: event.type === 'create' ? 'Incorporación' : 'Actualización',
      description: eventDescription(event),
      observedAt: event.observedAt,
      observedDate: formatPortalDate(event.observedAt),
      recordTitle: record.title,
      recordHref: `/registro/${encodeRecordId(record.id)}/`,
      source: sourceLabel(record.sourceId, data.sources),
      sourceId: record.sourceId,
      category: categoryLabel(record.category),
    };
  });
}
