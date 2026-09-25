// 실제 앱 운영 패널과 페이지 안 합성 응답만 빌드한다. 실행·서버·DB 접근은 하지 않는다.
// 기존 산출물을 지우지 않는다. 설치 fixture 와 같은 출력 폴더를 쓴다(같은 정적 서버로 연다).
import { build } from 'vite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = fileURLToPath(new URL('..', import.meta.url));
await build({ root: frontend, publicDir: false, base: './', build: {
  outDir: path.resolve(frontend, '../output/process-installation-browser'),
  emptyOutDir: false,
  rollupOptions: { input: path.join(frontend, 'tests/kit-operations-upgrade.fixture.html') },
} });
