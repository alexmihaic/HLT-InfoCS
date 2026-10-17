// Lightweight unit tests for build-time presentation logic. Run with:
//   node --test scripts/
// Uses only node:test and Node's built-in TypeScript type stripping (Node >= 23.6).
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { authorityGroups, authoritySlug } from '../src/lib/presentation/authorities.ts';
import { loadPortalStatus } from '../src/lib/data/status.ts';

function bdnsRecord(id, nivel2) {
  return {
    id,
    sourceId: 'bdns',
    title: id,
    detectedAt: '2026-10-01T00:00:00Z',
    bdns: nivel2 === undefined ? { extensionVersion: '1.0' } : { extensionVersion: '1.0', authorityHierarchy: { nivel1: 'LOCAL', nivel2 } },
  };
}

test('authoritySlug is deterministic ASCII and drops diacritics', () => {
  assert.equal(authoritySlug("VALL D'UIXÓ, LA"), 'vall-d-uixo-la');
  assert.equal(authoritySlug('CASTELLÓN DE LA PLANA/CASTELLÓ DE LA PLANA'), 'castellon-de-la-plana-castello-de-la-plana');
  assert.equal(authoritySlug('DIPUTACIÓN PROV. DE CASTELLÓN'), authoritySlug('DIPUTACIÓN PROV. DE CASTELLÓN'));
  assert.equal(authoritySlug('—'), null);
  assert.ok(authoritySlug('A'.repeat(200)).length <= 80);
});

test('authorityGroups never merges by similarity: same slug from different literals is an error', () => {
  assert.throws(
    () => authorityGroups([bdnsRecord('a', 'ALMASSORA'), bdnsRecord('b', 'Almassora')]),
    /colisión de slug/,
  );
});

test('authorityGroups excludes non-BDNS records and records without nivel2', () => {
  const groups = authorityGroups([
    bdnsRecord('a', 'ALMASSORA'),
    bdnsRecord('b', 'ALMASSORA'),
    bdnsRecord('c', 'ONDA'),
    bdnsRecord('d', undefined),
    bdnsRecord('e', '   '),
    { ...bdnsRecord('f', 'NULES'), sourceId: 'boe' },
  ]);
  assert.deepEqual(groups.map((group) => [group.slug, group.records.map((record) => record.id)]), [
    ['almassora', ['a', 'b']],
    ['onda', ['c']],
  ]);
});

test('loadPortalStatus is neutral when health, manifests and queue are missing', async () => {
  const root = await mkdtemp(join(tmpdir(), 'infocs-status-'));
  try {
    const now = new Date('2026-10-17T10:00:00Z');
    const status = await loadPortalStatus(['boe', 'bdns'], now, root);
    assert.equal(status.builtAt, '2026-10-17T10:00:00.000Z');
    assert.equal(status.boePendingReview, undefined);
    for (const sourceId of ['boe', 'bdns']) {
      const source = status.sources.get(sourceId);
      assert.equal(source.health, undefined);
      assert.equal(source.lastRun, undefined);
      assert.equal(source.manifestCount, 0);
    }
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('loadPortalStatus reads health, latest manifest and queue size without contents', async () => {
  const root = await mkdtemp(join(tmpdir(), 'infocs-status-'));
  try {
    await mkdir(join(root, 'health'), { recursive: true });
    await mkdir(join(root, 'manifests', 'bdns', '2026', '10'), { recursive: true });
    await mkdir(join(root, 'review', 'boe'), { recursive: true });
    await writeFile(join(root, 'health', 'bdns.json'), JSON.stringify({
      source_id: 'bdns', status: 'degraded', consecutive_failures: 2,
      last_success_at: '2026-10-07T13:32:57.274645Z', last_attempt_at: '2026-10-09T13:24:20.064187Z',
    }));
    await writeFile(join(root, 'health', 'boe.json'), '{not json');
    await writeFile(join(root, 'manifests', 'bdns', '2026', '10', 'a.json'), JSON.stringify({ source_id: 'bdns', status: 'success', finished_at: '2026-10-07T13:33:00Z' }));
    await writeFile(join(root, 'manifests', 'bdns', '2026', '10', 'b.json'), JSON.stringify({ source_id: 'bdns', status: 'failed', finished_at: '2026-10-09T13:24:22Z' }));
    await writeFile(join(root, 'review', 'boe', 'pending.json'), JSON.stringify({ schema_version: '1', source_id: 'boe', records: [{ official_id: 'X' }, { official_id: 'Y' }] }));

    const status = await loadPortalStatus(['boe', 'bdns'], new Date('2026-10-17T00:00:00Z'), root);
    const bdns = status.sources.get('bdns');
    assert.equal(bdns.health.status, 'degraded');
    assert.equal(bdns.health.consecutiveFailures, 2);
    assert.equal(bdns.health.lastSuccessAt, '2026-10-07T13:32:57.274645Z');
    assert.deepEqual(bdns.lastRun, { status: 'failed', finishedAt: '2026-10-09T13:24:22Z' });
    assert.equal(bdns.manifestCount, 2);
    assert.equal(status.sources.get('boe').health, undefined, 'malformed health is neutral, not invented');
    assert.equal(status.boePendingReview, 2);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
