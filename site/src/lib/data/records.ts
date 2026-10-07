import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { adaptRecord, assertProductiveRecord, parseCanonicalJson } from './canonical';
import { PUBLIC_SOURCE_IDS } from './sources';
import type { FrontendRecord } from './types';

const RECORDS_ROOT = fileURLToPath(new URL('../../../../data/records/', import.meta.url));

export async function loadRecords(): Promise<FrontendRecord[]> {
  const sourceDirectories = await readdir(RECORDS_ROOT, { withFileTypes: true });
  const paths = (
    await Promise.all(
      sourceDirectories
        .filter((entry) => entry.isDirectory() && PUBLIC_SOURCE_IDS.has(entry.name))
        .map((entry) => jsonFiles(join(RECORDS_ROOT, entry.name))),
    )
  ).flat();
  const records = await Promise.all(
    paths.map(async (path) => {
      const text = await readFile(path, 'utf8');
      const record = adaptRecord(parseCanonicalJson(text, path), path);
      assertProductiveRecord(record, path);
      return record;
    }),
  );

  const identities = new Set<string>();
  for (const record of records) {
    if (identities.has(record.id)) {
      throw new Error(`Frontend data contract: identidad Record duplicada (${record.sourceId}).`);
    }
    identities.add(record.id);
  }

  return records.sort((left, right) => {
    const leftDate = Date.parse(left.publishedAt ?? left.detectedAt);
    const rightDate = Date.parse(right.publishedAt ?? right.detectedAt);
    return rightDate - leftDate || left.id.localeCompare(right.id);
  });
}

export async function jsonFiles(root: string): Promise<string[]> {
  const result: string[] = [];
  async function visit(directory: string): Promise<void> {
    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(path);
      } else if (entry.isFile() && entry.name.endsWith('.json')) {
        result.push(path);
      }
    }
  }
  await visit(root);
  return result.sort((left, right) => left.localeCompare(right));
}
