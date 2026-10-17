import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Build-time operational status read from public, local canonical artifacts.
 * It never touches the network. Missing or unreadable optional artifacts yield
 * `undefined` (neutral state) instead of invented values or a failed build;
 * contract validity is enforced separately by CI (scripts/validate_canonical_data.py).
 */

const DATA_ROOT = fileURLToPath(new URL('../../../../data/', import.meta.url));

export type HealthStatus = 'healthy' | 'degraded' | 'failing' | 'unknown';
export type RunStatus = 'success' | 'partial' | 'failed' | 'no_publication';

export interface SourceRunStatus {
  readonly sourceId: string;
  /** From data/health/<source>.json, if present and well-formed. */
  readonly health?: {
    readonly status: HealthStatus;
    readonly lastSuccessAt?: string;
    readonly lastAttemptAt?: string;
    readonly consecutiveFailures: number;
  };
  /** Most recent Run Manifest by finished_at, if any. */
  readonly lastRun?: { readonly status: RunStatus; readonly finishedAt: string };
  readonly manifestCount: number;
}

export interface PortalStatus {
  readonly sources: ReadonlyMap<string, SourceRunStatus>;
  /** Aggregate count of BOE review queue entries; contents are never exposed. */
  readonly boePendingReview?: number;
  /** Moment this static build was generated (not a data freshness claim). */
  readonly builtAt: string;
}

const HEALTH_STATUSES = new Set<HealthStatus>(['healthy', 'degraded', 'failing', 'unknown']);
const RUN_STATUSES = new Set<RunStatus>(['success', 'partial', 'failed', 'no_publication']);
const SOURCE_ID = /^[a-z0-9][a-z0-9._-]{0,63}$/;
const TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

export async function loadPortalStatus(
  sourceIds: readonly string[],
  now: Date = new Date(),
  dataRoot: string = DATA_ROOT,
): Promise<PortalStatus> {
  const sources = new Map<string, SourceRunStatus>();
  for (const sourceId of sourceIds) {
    if (!SOURCE_ID.test(sourceId)) continue;
    const [health, runs] = await Promise.all([readHealth(dataRoot, sourceId), readRuns(dataRoot, sourceId)]);
    const lastRun = runs.sort((left, right) => right.finishedAt.localeCompare(left.finishedAt))[0];
    sources.set(sourceId, {
      sourceId,
      ...(health !== undefined ? { health } : {}),
      ...(lastRun !== undefined ? { lastRun } : {}),
      manifestCount: runs.length,
    });
  }
  const boePendingReview = await readReviewQueueCount(join(dataRoot, 'review', 'boe', 'pending.json'));
  return {
    sources,
    ...(boePendingReview !== undefined ? { boePendingReview } : {}),
    builtAt: now.toISOString(),
  };
}

async function readJson(path: string): Promise<unknown> {
  try {
    return JSON.parse(await readFile(path, 'utf8')) as unknown;
  } catch {
    return undefined;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function timestamp(value: unknown): string | undefined {
  return typeof value === 'string' && TIMESTAMP.test(value) && !Number.isNaN(Date.parse(value)) ? value : undefined;
}

async function readHealth(dataRoot: string, sourceId: string): Promise<SourceRunStatus['health']> {
  const payload = await readJson(join(dataRoot, 'health', `${sourceId}.json`));
  if (!isObject(payload) || payload.source_id !== sourceId) return undefined;
  const status = payload.status;
  const failures = payload.consecutive_failures;
  if (typeof status !== 'string' || !HEALTH_STATUSES.has(status as HealthStatus)) return undefined;
  if (typeof failures !== 'number' || !Number.isInteger(failures) || failures < 0) return undefined;
  const lastSuccessAt = timestamp(payload.last_success_at);
  const lastAttemptAt = timestamp(payload.last_attempt_at);
  return {
    status: status as HealthStatus,
    consecutiveFailures: failures,
    ...(lastSuccessAt !== undefined ? { lastSuccessAt } : {}),
    ...(lastAttemptAt !== undefined ? { lastAttemptAt } : {}),
  };
}

async function readRuns(dataRoot: string, sourceId: string): Promise<{ status: RunStatus; finishedAt: string }[]> {
  const root = join(dataRoot, 'manifests', sourceId);
  const files: string[] = [];
  async function visit(directory: string): Promise<void> {
    let entries;
    try {
      entries = await readdir(directory, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) await visit(path);
      else if (entry.isFile() && entry.name.endsWith('.json')) files.push(path);
    }
  }
  await visit(root);
  const runs: { status: RunStatus; finishedAt: string }[] = [];
  for (const path of files) {
    const payload = await readJson(path);
    if (!isObject(payload) || payload.source_id !== sourceId) continue;
    const finishedAt = timestamp(payload.finished_at);
    const status = payload.status;
    if (finishedAt === undefined || typeof status !== 'string' || !RUN_STATUSES.has(status as RunStatus)) continue;
    runs.push({ status: status as RunStatus, finishedAt });
  }
  return runs;
}

async function readReviewQueueCount(path: string): Promise<number | undefined> {
  const payload = await readJson(path);
  if (!isObject(payload) || payload.source_id !== 'boe' || !Array.isArray(payload.records)) return undefined;
  return payload.records.length;
}
