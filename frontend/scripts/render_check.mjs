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

function makeRequire(fromPath) {
  return (mod) => {
    if (mod === 'react') return React;
    if (mod === 'react-dom' || mod === 'react-dom/client')
      return { createRoot: () => ({ render() {}, unmount() {} }), render() {}, hydrateRoot: () => ({}) };
    if (mod.startsWith('.')) {
      const target = normalizePath(dirOf(fromPath) + '/' + mod);
      for (const k of Object.keys(registry)) if (normalizePath(k) === target) return registry[k];
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

for (const f of sorted) {
  const fp = f.file_path || 'unknown';
  if (!/\.(tsx|ts|jsx|js)$/i.test(fp)) continue;
  try {
    const compiled = transpile(f.code, fp);
    const exportsObj = {};
    const moduleObj = { exports: exportsObj };
    const fn = new Function('exports', 'module', 'require', 'React', compiled);
    fn(exportsObj, moduleObj, makeRequire(fp), React);
    registry[fp] = moduleObj.exports;
  } catch (e) {
    result.errors.push('[' + fp + '] 로드/컴파일 실패: ' + (e && e.message ? e.message : e));
  }
}

// 루트 App 탐색
let App = null;
for (const k of Object.keys(registry)) {
  if (/app\.(tsx|jsx|ts|js)$/i.test(k)) {
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
