import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { projectBDNSLinks } from '../src/lib/data/bdnsLinks.ts';

const script = fileURLToPath(new URL('./bdns_link_projection.py', import.meta.url));

test('Python projection preserves only eligible literal HTTPS locators', () => {
  const values = ['https://example.org/path?q=1', 'http://example.org', 'example.org', 'https://example.org/a b', 'https://example.org/\n', 'javascript:alert(1)', 'data:text/plain,x', 'file:///x', 'mailto:a@example.org', 'https://127.0.0.1/x', null];
  const input = values.map(value => ({ bases: value, office: value }));
  const result = spawnSync('python', ['-B', script], { input: JSON.stringify(input), encoding: 'utf8' });
  assert.equal(result.status, 0);
  assert.deepEqual(JSON.parse(result.stdout), values.map((value, i) => ({ bases: i === 0 ? value : null, office: i === 0 ? value : null })));
});

test('batch is deterministic and retains distinct actions even when their destination is identical', async () => {
  const value = 'https://example.org/sede/bases?q=%C3%B3';
  const records = [{ sourceId: 'bdns', bdns: { regulatoryBases: { sourceLocator: value }, electronicOfficeUrl: value } },
    { sourceId: 'boe', bdns: { regulatoryBases: { sourceLocator: value }, electronicOfficeUrl: value } },
    { sourceId: 'bdns', bdns: {} }];
  const projected = projectBDNSLinks(records);
  assert.deepEqual(projected, [{ bases: value, office: value }, { bases: null, office: null }, { bases: null, office: null }]);
  assert.strictEqual(projectBDNSLinks(records), projected, 'identical batch reuses the single projection');
  const component = await readFile(new URL('../src/components/BDNSHumanReadableDetail.astro', import.meta.url), 'utf8');
  assert.equal((component.match(/label="Abrir localizador de bases reguladoras"/g) ?? []).length, 1);
  assert.equal((component.match(/label="Abrir sede electrónica indicada por BDNS"/g) ?? []).length, 1);
  assert.match(component, /href=\{links\.bases\}/);
  assert.match(component, /href=\{links\.office\}/);
});

test('projection runs with network disabled', () => {
  const program = "import runpy,socket,sys; deny=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network')); socket.socket.connect=deny; socket.socket.connect_ex=deny; socket.create_connection=deny; socket.getaddrinfo=deny; runpy.run_path(sys.argv[1],run_name='__main__')";
  const input = [{ bases: 'https://example.org/bases', office: 'https://example.org/sede' }];
  const result = spawnSync('python', ['-B', '-c', program, script], { input: JSON.stringify(input), encoding: 'utf8' });
  assert.equal(result.status, 0);
  assert.deepEqual(JSON.parse(result.stdout), input);
});

test('unavailable Python fails closed with no unvalidated links', () => {
  const oldPath = process.env.PATH;
  try {
    process.env.PATH = '';
    assert.throws(() => projectBDNSLinks([{ sourceId: 'bdns', bdns: { electronicOfficeUrl: 'https://example.org/new' } }]), /requires Python/);
  } finally {
    process.env.PATH = oldPath;
  }
});
