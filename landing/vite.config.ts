import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

/** Multi-page build: the landing plus the two generated legal documents. */
const entry = (name: string) => fileURLToPath(new URL(name, import.meta.url));

export default defineConfig({
  server: {
    port: 5173,
    host: true,
  },
  build: {
    target: 'esnext',
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      input: {
        main: entry('index.html'),
        privacy: entry('privacy.html'),
        terms: entry('terms.html'),
      },
    },
  },
});

