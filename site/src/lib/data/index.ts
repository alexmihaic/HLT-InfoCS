import { loadEvents } from './events';
import { loadRecords } from './records';
import { buildSources } from './sources';
import type { FrontendEvent, FrontendRecord, PortalData } from './types';

export async function loadPortalData(): Promise<PortalData> {
  const records = await loadRecords();
  const events = await loadEvents(records);
  const eventsByRecordId = new Map<string, FrontendEvent[]>();
  for (const event of events) {
    const recordEvents = eventsByRecordId.get(event.recordId) ?? [];
    recordEvents.push(event);
    eventsByRecordId.set(event.recordId, recordEvents);
  }

  return {
    records,
    events,
    sources: buildSources(records),
    eventsByRecordId: new Map(
      [...eventsByRecordId.entries()].map(([recordId, recordEvents]) => [recordId, recordEvents]),
    ),
  };
}

export function encodeRecordId(id: string): string {
  const bytes = new TextEncoder().encode(id);
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, '0')).join('');
  return `r-${hex}`;
}

export function decodeRecordId(slug: string): string {
  if (!/^r-(?:[0-9a-f]{2})+$/.test(slug)) throw new Error('Slug de Record no válido.');
  const hex = slug.slice(2);
  const bytes = new Uint8Array(hex.match(/.{2}/g)!.map((pair) => Number.parseInt(pair, 16)));
  return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
}

export function eventsForRecord(data: PortalData, record: FrontendRecord): readonly FrontendEvent[] {
  return data.eventsByRecordId.get(record.id) ?? [];
}
