import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { adaptEvent, parseCanonicalJson } from './canonical';
import { jsonFiles } from './records';
import { PUBLIC_SOURCE_IDS } from './sources';
import type { FrontendEvent, FrontendRecord } from './types';

const EVENTS_ROOT = fileURLToPath(new URL('../../../../data/events/', import.meta.url));

export async function loadEvents(records: readonly FrontendRecord[]): Promise<FrontendEvent[]> {
  const recordById = new Map(records.map((record) => [record.id, record]));
  const sourceDirectories = await readdir(EVENTS_ROOT, { withFileTypes: true });
  const paths = (
    await Promise.all(
      sourceDirectories
        .filter((entry) => entry.isDirectory() && PUBLIC_SOURCE_IDS.has(entry.name))
        .map((entry) => jsonFiles(join(EVENTS_ROOT, entry.name))),
    )
  ).flat();
  const events = await Promise.all(
    paths.map(async (path) => {
      const text = await readFile(path, 'utf8');
      return adaptEvent(parseCanonicalJson(text, path), path);
    }),
  );

  for (const event of events) {
    const record = recordById.get(event.recordId);
    if (!record) {
      throw new Error(`Frontend data contract: Event ${event.eventId} referencia un Record inexistente.`);
    }
    if (record.sourceId !== event.sourceId) {
      throw new Error(`Frontend data contract: source_id del Event ${event.eventId} no coincide con su Record.`);
    }
  }

  return events.sort((left, right) => {
    const byDate = Date.parse(right.observedAt) - Date.parse(left.observedAt);
    return byDate || (left.eventId < right.eventId ? -1 : left.eventId > right.eventId ? 1 : 0);
  });
}
