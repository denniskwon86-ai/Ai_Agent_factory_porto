/**
 * ★★★ [E0-1A] Preview 샌드박스용 벤더 자산을 **로컬 node_modules 에서** 만든다.
 *
 * 결과물: `public/preview-vendor/`
 *   · runtime.js  — React 19 · ReactDOM · lucide-react 를 전역으로 (IIFE)
 *   · babel.js    — @babel/standalone (JSX 컴파일, `new Function` 을 쓰므로 unsafe-eval 필요)
 *   · tailwind.js — @tailwindcss/browser (브라우저 JIT)
 *
 * ⚠️ **`npm run dev` · `npm run build` 앞에 자동으로 돈다**(package.json 의 predev·prebuild).
 *   손으로 돌리는 단계로 두면 «어제는 됐는데 오늘 미리보기가 하얗다» 가 되고, 원인을 찾는 데
 *   시간이 든다. 자산은 `.gitignore` 로 커밋하지 않는다 — 3MB 짜리 남의 코드를 저장소에 넣지
 *   않고, 대신 **언제든 재생성되게** 만든다.
 *
 * ⚠️ 이 스크립트가 실패하면 **조용히 넘어가지 않는다.** 벤더가 없으면 미리보기는 그냥 안 뜨고,
 *   그 상태가 「격리 때문에 막힌 것」과 구별되지 않는다.
 */
import { copyFileSync, existsSync, mkdirSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { build } from 'vite';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const outDir = resolve(root, 'public/preview-vendor');

mkdirSync(outDir, { recursive: true });

//: ① React·ReactDOM·lucide-react 를 하나의 IIFE 로 묶는다.
await build({
  configFile: false,
  root,
  logLevel: 'warn',
  //: ⚠️ **끄지 않으면 `public/` 전체가 결과 폴더로 복사된다.** outDir 이 publicDir 안에 있어서
  //   vite 가 「정적 자산을 결과물에 넣는」 기본 동작을 그대로 하고, 실제로 favicon.svg ·
  //   icons.svg 가 `public/preview-vendor/` 안에 복제됐다. 빌드마다 늘어난다.
  publicDir: false,
  //: ⚠️ 개발 빌드(`NODE_ENV=development`)로 두면 React 가 3배 커지고 경고를 쏟는다.
  define: { 'process.env.NODE_ENV': '"production"' },
  build: {
    outDir,
    emptyOutDir: false,
    minify: true,
    //: `lib` 모드여야 IIFE 단일 파일이 나온다. 코드 분할이 생기면 srcDoc 에 넣을 수 없다.
    lib: {
      entry: resolve(here, 'preview-vendor-entry.js'),
      name: 'AFSPreviewVendor',
      formats: ['iife'],
      fileName: () => 'runtime.js',
    },
  },
});

//: ② 그대로 복사하면 되는 것들. 재가공하면 원본과 달라질 뿐 얻는 게 없다.
const copies = [
  ['@babel/standalone/babel.min.js', 'babel.js'],
  ['@tailwindcss/browser/dist/index.global.js', 'tailwind.js'],
];
for (const [from, to] of copies) {
  const src = resolve(root, 'node_modules', from);
  if (!existsSync(src)) {
    throw new Error(
      `[preview-vendor] ${from} 이 없습니다. 'npm install' 을 먼저 하십시오. ` +
      `이것이 없으면 미리보기가 뜨지 않고, 그 증상이 격리 실패와 구별되지 않습니다.`);
  }
  copyFileSync(src, resolve(outDir, to));
}

const kb = (p) => Math.round(statSync(resolve(outDir, p)).size / 1024);
console.log(
  `[preview-vendor] 생성 완료 — runtime.js ${kb('runtime.js')}KB · ` +
  `babel.js ${kb('babel.js')}KB · tailwind.js ${kb('tailwind.js')}KB`);
