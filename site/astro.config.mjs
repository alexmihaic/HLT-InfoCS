import { fileURLToPath } from 'node:url';
import { defineConfig } from 'astro/config';

export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  output: 'static',
  outDir: './dist',
});
