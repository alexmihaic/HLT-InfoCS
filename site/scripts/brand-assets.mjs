// Deterministic exports from the hand-drawn vector master. No fonts or network.
// Uses sharp already installed and pinned through Astro's lockfile.
// node scripts/brand-assets.mjs [--check]
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const publicDir = new URL('../public/', import.meta.url);
const master = await readFile(new URL('favicon.svg', publicDir));
assert(!/<(?:text|image|foreignObject)\b|(?:href|filter)=/i.test(master.toString()));
const png = (size) => sharp(master, { density: 576 }).resize(size, size).png().toBuffer();
const exports = [
  ['apple-touch-icon.png', 180], ['icon-192.png', 192], ['icon-512.png', 512],
];
// PNG-compressed ICO frames, each with its own explicit size/directory entry.
const frames = await Promise.all([16, 32].map(png));
const header = Buffer.alloc(6 + 16 * frames.length);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(frames.length, 4);
let offset = header.length;
for (let i = 0; i < frames.length; i++) {
  const entry = 6 + i * 16;
  header[entry] = header[entry + 1] = [16, 32][i];
  header.writeUInt16LE(1, entry + 4);
  header.writeUInt16LE(32, entry + 6);
  header.writeUInt32LE(frames[i].length, entry + 8);
  header.writeUInt32LE(offset, entry + 12);
  offset += frames[i].length;
}
const ico = Buffer.concat([header, ...frames]);
const checkOnly = process.argv.includes('--check');
for (const [name, size] of exports) {
  const expected = await png(size);
  const path = new URL(name, publicDir);
  if (!checkOnly) await writeFile(path, expected);
  assert.deepEqual(await readFile(path), expected, `${name}: regenerate from master`);
  const meta = await sharp(await readFile(path)).metadata();
  assert.equal(meta.width, size); assert.equal(meta.height, size);
}
const icoPath = new URL('favicon.ico', publicDir);
if (!checkOnly) await writeFile(icoPath, ico);
assert.deepEqual(await readFile(icoPath), ico);
for (let i = 0; i < 2; i++) {
  const start = ico.readUInt32LE(6 + i * 16 + 12);
  const length = ico.readUInt32LE(6 + i * 16 + 8);
  const meta = await sharp(ico.subarray(start, start + length)).metadata();
  assert.equal(meta.width, [16, 32][i]); assert.equal(meta.height, [16, 32][i]);
}
const manifest = JSON.parse(await readFile(new URL('site.webmanifest', publicDir), 'utf8'));
assert.equal(manifest.theme_color, '#07111d');
assert.equal(manifest.background_color, '#07111d');
assert.deepEqual(manifest.icons.map((icon) => icon.sizes), ['192x192', '512x512']);
for (const icon of manifest.icons) {
  assert.equal(icon.purpose, 'any'); // Not maskable: no unsupported safe-zone claim.
  await readFile(new URL(icon.src.slice(1), publicDir));
}
console.log(`brand-assets: PASS — master, 3 PNGs, ICO 16/32 and manifest (${fileURLToPath(publicDir)})`);
