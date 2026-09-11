import { build } from 'vite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const frontend = fileURLToPath(new URL('..', import.meta.url));
await build({ root: frontend, publicDir: false, base: './', build: {
  outDir: path.resolve(frontend, '../output/decision-create-browser'),
  emptyOutDir: false,
  rollupOptions: { input: path.join(frontend, 'tests/decision-create.fixture.html') },
} });
