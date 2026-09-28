import { fileURLToPath } from 'node:url';
import { defineConfig } from 'astro/config';

export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  site: 'https://infocs.hazlotuyo.pro',
  base: '/',
  output: 'static',
  outDir: './dist',
});
