import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import type { FrontendRecord } from './types';

export interface BDNSLinks { readonly bases: string | null; readonly office: string | null }
let previousInput: string | undefined;
let previousOutput: readonly BDNSLinks[] | undefined;

/** One local Python process per route generation, never per record or network request. */
export function projectBDNSLinks(records: readonly FrontendRecord[]): readonly BDNSLinks[] {
  const input = records.map((record) => ({
    bases: record.sourceId === 'bdns' ? record.bdns?.regulatoryBases?.sourceLocator ?? null : null,
    office: record.sourceId === 'bdns' ? record.bdns?.electronicOfficeUrl ?? null : null,
  }));
  const serialized = JSON.stringify(input);
  if (serialized === previousInput && previousOutput !== undefined) return previousOutput;
  const script = fileURLToPath(new URL('../../../scripts/bdns_link_projection.py', import.meta.url));
  const process = spawnSync('python', ['-B', script], {
    input: serialized, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024,
    env: { ...globalThis.process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONIOENCODING: 'utf-8' },
  });
  if (process.error || process.status !== 0) throw new Error('BDNS link projection requires Python with the InfoCs runtime installed.');
  let output: unknown;
  try { output = JSON.parse(process.stdout); } catch { throw new Error('BDNS link projection returned invalid output.'); }
  if (!Array.isArray(output) || output.length !== input.length) throw new Error('BDNS link projection returned invalid output.');
  const projected = output.map((row: unknown, index): BDNSLinks => {
    if (!row || typeof row !== 'object' || Array.isArray(row)) throw new Error('BDNS link projection returned invalid output.');
    const item = row as Record<string, unknown>;
    if (Object.keys(item).sort().join(',') !== 'bases,office'
      || (item.bases !== null && item.bases !== input[index].bases)
      || (item.office !== null && item.office !== input[index].office)) {
      throw new Error('BDNS link projection returned invalid output.');
    }
    return { bases: item.bases as string | null, office: item.office as string | null };
  });
  previousInput = serialized;
  previousOutput = projected;
  return projected;
}
