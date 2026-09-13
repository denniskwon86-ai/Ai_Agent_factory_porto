// 실제 제품 패널과 메모리 API 대역만 빌드한다. 실행·서버·DB 접근은 하지 않는다.
// 이 파일 실행은 메인이 소스 동결 후 수행한다. 기존 산출물을 지우지 않는다.
import { build } from 'vite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = fileURLToPath(new URL('..', import.meta.url));
await build({ root: frontend, publicDir: false, base: './', build: {
  outDir: path.resolve(frontend, '../output/process-installation-browser'),
  emptyOutDir: false,
  rollupOptions: { input: path.join(frontend, 'tests/process-installation.fixture.html') },
} });
