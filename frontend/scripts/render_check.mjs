// 생성된 프론트엔드 코드를 서버사이드에서 실제로 렌더해 동작을 검증한다.
// 브라우저 프리뷰 샌드박스(PreviewPanel)의 트랜스파일+require 로직을 미러링하되,
// 미해결 외부 import는 결함으로 throw하고 renderToString으로 초기 렌더 크래시를 검출한다.
// 사용: node render_check.mjs <input.json>   (input = [{file_path, code}, ...])
// 출력(stdout): {"ok":bool, "errors":[...], "rendered":int}
import fs from 'node:fs';
import * as Babel from '@babel/standalone';
import React from 'react';
import { renderToString } from 'react-dom/server';

const result = { ok: false, errors: [], rendered: 0 };

function fail(msg) {
  result.errors.push(msg);
  process.stdout.write(JSON.stringify(result));
  process.exit(0);
}

let files;
try {
  files = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));
  if (!Array.isArray(files)) fail('입력이 파일 배열이 아닙니다.');
} catch (e) {
  fail('입력 파싱 실패: ' + e.message);
}

function transpile(code, filename) {
  // import.meta(.env)는 CJS 컨텍스트에서 못 쓰므로 안전한 빈 객체로 치환
  const src = String(code || '')
    .replace(/import\s*\.\s*meta\s*\.\s*env/g, '({})')
    .replace(/import\s*\.\s*meta/g, '({})');
  return Babel.transform(src, {
    presets: [['env', { modules: 'commonjs' }], ['react', { runtime: 'classic' }], 'typescript'],
    filename: filename || 'file.tsx',
  }).code;
}

function normalizePath(p) {
  const parts = [];
  String(p).split('/').forEach((s) => {
    if (s === '..') parts.pop();
    else if (s !== '.' && s !== '') parts.push(s);
  });
  return parts.join('/').replace(/\.(tsx|ts|jsx|js)$/i, '');
}
function dirOf(p) {
  const i = String(p).lastIndexOf('/');
  return i < 0 ? '' : String(p).slice(0, i);
}

// ── 브라우저 전역 스텁 ────────────────────────────────────────────────
// [2026-07-26 결함 #20] 이 하네스는 맨 Node 에서 도는데 브라우저 전역이 하나도 없었다.
//   그래서 PRD 가 요구한 '이력 저장'을 localStorage 로 올바르게 구현한 코드가
//   `localStorage is not defined` 로 렌더 실패 처리됐다 — **요구한 대로 만든 것을 감점**하는
//   거짓 실패다. 실제 프리뷰(PreviewPanel)는 브라우저이므로 거기서는 정상 동작한다.
//   → 브라우저와 같은 의미(semantics)의 최소 스텁을 주입해 하네스를 실제 실행 환경에 맞춘다.
//   ⚠️ 과하게 스텁하지 말 것: 진짜 깨진 코드가 통과하면 검증의 의미가 없다.
//      여기 있는 것은 모두 '브라우저라면 반드시 있는' 것들로 제한한다.
function makeStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(String(k)) ? m.get(String(k)) : null),
    setItem: (k, v) => { m.set(String(k), String(v)); },
    removeItem: (k) => { m.delete(String(k)); },
    clear: () => m.clear(),
    key: (i) => Array.from(m.keys())[i] ?? null,
    get length() { return m.size; },
  };
}
if (typeof globalThis.localStorage === 'undefined') globalThis.localStorage = makeStorage();
if (typeof globalThis.sessionStorage === 'undefined') globalThis.sessionStorage = makeStorage();
if (typeof globalThis.matchMedia === 'undefined') {
  globalThis.matchMedia = () => ({
    matches: false, media: '', onchange: null,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
    dispatchEvent: () => false,
  });
}
if (typeof globalThis.window === 'undefined') {
  globalThis.window = globalThis;   // window.localStorage 등 접근 경로도 열어준다
  globalThis.window.location = { href: 'http://localhost/', origin: 'http://localhost', pathname: '/', search: '', hash: '' };
  globalThis.window.addEventListener = () => {};
  globalThis.window.removeEventListener = () => {};
}
if (typeof globalThis.navigator === 'undefined') {
  globalThis.navigator = { userAgent: 'render-check', language: 'ko-KR', clipboard: { writeText: async () => {} } };
}
// document: renderToString 은 DOM 을 쓰지 않지만 document.title 등을 만지는 코드가 있다.
// getElementById 는 null 을 돌려준다 — 브라우저 초기 렌더와 동일하며, null 미확인 접근은 여기서 잡혀야 한다.
if (typeof globalThis.document === 'undefined') {
  globalThis.document = {
    title: '', getElementById: () => null, querySelector: () => null,
    querySelectorAll: () => [], addEventListener: () => {}, removeEventListener: () => {},
    body: { classList: { add() {}, remove() {}, toggle() {} }, appendChild() {}, style: {} },
    documentElement: { classList: { add() {}, remove() {}, toggle() {} }, style: {}, setAttribute() {} },
    createElement: () => ({ style: {}, setAttribute() {}, appendChild() {}, classList: { add() {}, remove() {} } }),
  };
}

const registry = {}; // file_path -> module.exports

// ── 지연(on-demand) 모듈 해석 ───────────────────────────────────────
// ⚠️ [2026-07-27 결함] 기존 구현은 파일을 **배열 순서대로** 미리 로드하고 `App.*` 만 마지막으로
//   미뤘다. 그래서 다중 디렉터리 구조(`src/components/X.tsx` 가 `../utils/Y` 를 import)에서
//   `components/*` 가 `utils/*` 보다 먼저 로드되면, 실제로 존재하는 파일인데도
//   `미해결 상대 모듈 import` 로 **거짓 실패**했다.
//   실측(test_a1_v7): 모델이 컴포넌트를 잘 분리해 만들수록 이 실패가 더 잘 났다 —
//   좋은 구조를 만들수록 반려되는 역설. 렌더 검증 9회 연속 실패 → 재작업 상한 → FAILED_REVIEW.
//   (결함 #20 렌더 하네스 거짓 실패와 같은 종류 — 하네스가 앱을 부당하게 반려한다.)
// → import 시점에 대상 모듈을 **필요하면 그 자리에서 컴파일**한다. 로드 순서에 의존하지 않는다.
const sourceByPath = new Map();   // normalized path -> {fp, code}
const loading = new Set();        // 순환 import 무한재귀 방지

function loadModule(normTarget) {
  if (registry[normTarget] !== undefined) return registry[normTarget];
  const entry = sourceByPath.get(normTarget);
  if (!entry) return undefined;
  if (loading.has(normTarget)) return {};   // 순환 참조: 부분 모듈 반환(Node CJS 와 동일 동작)
  loading.add(normTarget);
  try {
    const compiled = transpile(entry.code, entry.fp);
    const exportsObj = {};
    const moduleObj = { exports: exportsObj };
    const fn = new Function('exports', 'module', 'require', 'React', compiled);
    fn(exportsObj, moduleObj, makeRequire(entry.fp), React);
    registry[normTarget] = moduleObj.exports;
    return moduleObj.exports;
  } finally {
    loading.delete(normTarget);
  }
}

function makeRequire(fromPath) {
  return (mod) => {
    if (mod === 'react') return React;
    if (mod === 'react-dom' || mod === 'react-dom/client')
      return { createRoot: () => ({ render() {}, unmount() {} }), render() {}, hydrateRoot: () => ({}) };
    if (mod.startsWith('.')) {
      const target = normalizePath(dirOf(fromPath) + '/' + mod);
      const got = loadModule(target);
      if (got !== undefined) return got;
      // CSS 등 비-JS 자산은 렌더에 영향이 없다. 파일이 실제로 있으면 빈 객체로 통과시킨다.
      if (/\.(css|scss|sass|less)$/i.test(mod) && sourceByPath.has(target)) return {};
      throw new Error('미해결 상대 모듈 import: "' + mod + '" (from ' + fromPath + ')');
    }
    throw new Error('허용되지 않은 외부 라이브러리 import: "' + mod + '" — 프리뷰 샌드박스는 react와 상대경로 파일만 지원합니다(axios 등 금지).');
  };
}

// 의존성이 먼저 로드되도록 App.* 를 마지막으로 정렬
const sorted = [...files].sort((a, b) => {
  const aa = /app\.(tsx|jsx|ts|js)$/i.test(a.file_path || '') ? 1 : 0;
  const bb = /app\.(tsx|jsx|ts|js)$/i.test(b.file_path || '') ? 1 : 0;
  return aa - bb;
});

// 소스 인덱스를 먼저 채운다 — 지연 해석(loadModule)이 순서와 무관하게 찾을 수 있도록.
for (const f of files) {
  const fp = f.file_path || 'unknown';
  sourceByPath.set(normalizePath(fp), { fp, code: f.code });
}

for (const f of sorted) {
  const fp = f.file_path || 'unknown';
  if (!/\.(tsx|ts|jsx|js)$/i.test(fp)) continue;
  const norm = normalizePath(fp);
  if (registry[norm] !== undefined) continue;   // 다른 모듈의 import 로 이미 로드됨
  try {
    loadModule(norm);
  } catch (e) {
    result.errors.push('[' + fp + '] 로드/컴파일 실패: ' + (e && e.message ? e.message : e));
  }
}

// 루트 App 탐색
// ⚠️ 레지스트리 키는 **정규화 경로**(확장자 제거)다 — `src/App.tsx` → `src/App`.
//   예전 정규식(`app\.(tsx|jsx)$`)은 확장자를 요구해 절대 매치되지 않는다.
let App = null;
for (const k of Object.keys(registry)) {
  if (/(^|\/)app$/i.test(k)) {
    const e = registry[k];
    App = (e && e.default) || e;
    break;
  }
}
if (typeof App !== 'function') {
  for (const k of Object.keys(registry)) {
    const e = registry[k];
    const c = (e && e.default) || e;
    if (typeof c === 'function') { App = c; break; }
  }
}

if (typeof App === 'function') {
  try {
    const html = renderToString(React.createElement(App));
    result.rendered = (html || '').length;
    result.ok = result.errors.length === 0 && result.rendered > 0;
  } catch (e) {
    result.errors.push('초기 렌더 런타임 에러: ' + (e && e.message ? e.message : e));
  }
} else if (result.errors.length === 0) {
  result.errors.push('렌더할 App 루트 컴포넌트를 찾지 못했습니다(App.tsx의 default export 필요).');
}

process.stdout.write(JSON.stringify(result));
