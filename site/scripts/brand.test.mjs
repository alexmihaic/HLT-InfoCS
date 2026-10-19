import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const assets = ['favicon.svg', 'favicon.ico', 'apple-touch-icon.png', 'icon-192.png', 'icon-512.png', 'site.webmanifest'];

test('brand exports reach the build byte-for-byte', async () => {
  for (const name of assets) {
    assert.deepEqual(await readFile(new URL(`public/${name}`, root)), await readFile(new URL(`dist/${name}`, root)), name);
  }
});

test('every generated page has one set of icon metadata', async () => {
  let pages = 0;
  async function walk(dir) {
    for (const item of await readdir(dir, { withFileTypes: true })) {
      const path = new URL(item.name + (item.isDirectory() ? '/' : ''), dir);
      if (item.isDirectory()) await walk(path);
      else if (item.name.endsWith('.html')) {
        const html = await readFile(path, 'utf8');
        const head = html.match(/<head\b[^>]*>([\s\S]*?)<\/head>/i)?.[1];
        assert.ok(head);
        for (const name of ['favicon.svg', 'favicon.ico', 'apple-touch-icon.png', 'site.webmanifest']) {
          assert.equal((head.match(new RegExp(`href="/${name.replace('.', '\\.')}"`, 'g')) ?? []).length, 1, name);
        }
        assert.equal((head.match(/name="theme-color"/g) ?? []).length, 1);
        assert.match(head, /name="theme-color" content="#07111d"/);
        pages++;
      }
    }
  }
  await walk(new URL('dist/', root));
  assert.ok(pages > 0);
});

test('SVG master is vector-only and uses the existing brand palette', async () => {
  const svg = await readFile(new URL('public/favicon.svg', root), 'utf8');
  assert.match(svg, /viewBox="0 0 64 64"/);
  assert.doesNotMatch(svg, /<(text|image|foreignObject|filter|linearGradient|radialGradient)\b/);
  assert.deepEqual([...new Set([...svg.matchAll(/fill="(#[0-9a-f]+)"/g)].map((x) => x[1]))].sort(), ['#07111d', '#2f8cff', '#f4f8fc']);
});
