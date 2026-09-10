// Build only the component fixture, never the product entry or production data.
import { build } from 'vite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const frontend = fileURLToPath(new URL('..', import.meta.url));
await build({ root: frontend, publicDir: false, base: './', build: {
  outDir: path.resolve(frontend, '../tmp/home-responsive-layout'),
  emptyOutDir: false,
  rollupOptions: { input: path.join(frontend, 'tests/enterprise-layout.fixture.html') },
} });
