// 기존 Vite 격리 fixture 패턴. 산출물 폴더만 갱신하며 서버·DB를 호출하지 않는다.
import { build } from 'vite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const frontend = fileURLToPath(new URL('..', import.meta.url));
await build({ root: frontend, publicDir: false, base: './', build: {
  outDir: path.resolve(frontend, '../output/process-installation-browser'), emptyOutDir: false,
  rollupOptions: { input: path.join(frontend, 'tests/studio-transition.fixture.html') },
} });
