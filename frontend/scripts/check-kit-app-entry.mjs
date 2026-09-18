// B6 업무 앱 진입 확인: 모의 HTTP + 실제 flow/SSR. 브라우저·실제 서버 권한 검사는 별도다.
//
// ★★★ **목록 수준** 판정이다(사용자 결정 2026-09-15). project 경로와 한 가지가 다르다 —
//   소유와 조회 문맥이 **달라도 정상**이다. 전사 조회 권한에서 그렇게 된다.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const files = ['../src/factory/studioKitAppEntry.ts', '../src/factory/StudioKitAppEntryGate.tsx',
  '../src/factory/studioEntryFlow.ts', './check-kit-app-entry.mjs'];
const hashes = () => Object.fromEntries(files.map(f => [f, createHash('sha256').update(fs.readFileSync(new URL(f, import.meta.url))).digest('hex')]));
const before = hashes();
function load(file, deps = {}) {
  const url = new URL(file, import.meta.url), native = createRequire(url), mod = { exports: {} };
  const js = ts.transpileModule(fs.readFileSync(url, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  new Function('module', 'exports', 'require', js)(mod, mod.exports, name => {
    if (Object.hasOwn(deps, name)) return deps[name];
    if (['react', 'react/jsx-runtime'].includes(name)) return native(name);
    throw new Error('예상하지 않은 의존성: ' + name);
  });
  return mod.exports;
}
globalThis.window = new EventTarget();
const initial = { user: 'test-user', token: 'synthetic', tenantId: 'tenant-a', scopeNodeId: 'scope-a', entityMode: 'REAL' };
let identity, calls, responder;
const api = { getEnterpriseContext: () => identity, apiFetch: async (url, init) => {
  calls.push({ url, init }); return responder(url, init);
} };
const memory = { studioIdentityKey: () => JSON.stringify(identity) };
// [DRAFT-ENTRY-01] flow 공통부는 «실제 모듈»을 싣는다 — 대역이면 수명 검사가 의미를 잃는다.
const flow_ = load('../src/factory/studioEntryFlow.ts', { './studioInputMemory': memory });
const module = load(files[0], { '../lib/api': api, './studioInputMemory': memory, './studioEntryFlow': flow_ });
const ui = load(files[1], { './studioKitAppEntry': module });
const INSTANCE = 'ki_6b06ffb50a994a', APP = 'APP-03';
const metadata = () => ({ instance_id: INSTANCE, app_id: APP, app_label: '재고·생산 영향 분석',
  ownership: { tenant_id: 'tenant-a', enterprise_scope_id: 'plant-smelting', entity_mode: 'REAL' },
  viewing_context: { tenant_id: 'tenant-a', scope_node_id: 'scope-a', entity_mode: 'REAL' } });
const response = (data = metadata(), status = 200) => new Response(JSON.stringify({ status: 'success', data }), { status });
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const results = [], flows = [];
function flow(instance = INSTANCE, app = APP) {
  const f = module.createKitAppEntryFlow(instance, app); flows.push(f); f.activate(); return f;
}
async function test(name, run) {
  identity = { ...initial }; calls = []; responder = async () => response();
  try { await run(); results.push({ name, result: 'PASS' }); }
  catch (error) { results.push({ name, result: 'FAIL', error: String(error.stack || error) }); }
  finally { for (const f of flows.splice(0)) f.dispose(); }
}

await test('API 단건 GET·no-store·허용 필드만 반환', async () => {
  const value = await module.readKitAppEntry(INSTANCE, APP);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `/api/v1/data-preparation/instances/${INSTANCE}/apps/${APP}/entry-metadata`);
  assert.equal(calls[0].init.method, 'GET');
  assert.equal(calls[0].init.cache, 'no-store');
  assert.deepEqual(Object.keys(value).sort(), ['app_id', 'app_label', 'instance_id', 'ownership', 'viewing_context']);
});

await test('API 소유와 조회 문맥이 달라도 정상 — 목록 수준 판정', async () => {
  // ★ project 경로는 둘이 다르면 잘못된 응답으로 본다. 여기서는 전사 조회 권한에서
  //   정상적으로 갈릴 수 있다. 범위 판정은 서버가 한다.
  const value = await module.readKitAppEntry(INSTANCE, APP);
  assert.notEqual(value.ownership.enterprise_scope_id, value.viewing_context.scope_node_id);
  assert.equal(value.app_label, '재고·생산 영향 분석');
});

await test('API 잘못된 ID는 통신 전 차단', async () => {
  for (const [instance, app] of [[INSTANCE, 'has space'], [INSTANCE, '앱'], [INSTANCE, 'x'.repeat(161)],
                                 ['', APP], ['a/b', APP], [INSTANCE, '']]) {
    await assert.rejects(() => module.readKitAppEntry(instance, app),
      error => error.reasonCode === 'KIT_APP_ENTRY_INVALID_TARGET' && error.status === 422);
  }
  assert.equal(calls.length, 0, '형식 위반인데 서버로 나갔다');
});

await test('API 대상 불일치·필드 손상은 거절', async () => {
  for (const patch of [{ instance_id: 'other' }, { app_id: 'APP-99' }, { app_label: '' },
                       { app_label: 42 }, { ownership: null }, { viewing_context: [] },
                       { ownership: { tenant_id: '', enterprise_scope_id: 'x', entity_mode: 'REAL' } }]) {
    responder = async () => response({ ...metadata(), ...patch });
    await assert.rejects(() => module.readKitAppEntry(INSTANCE, APP),
      error => error.reasonCode === 'KIT_APP_ENTRY_RESPONSE_INVALID');
  }
});

await test('API 실패 상태는 본문을 옮기지 않는다', async () => {
  for (const [status, expected] of [[401, '로그인이 필요합니다.'], [403, '현재 회사·권한에서 업무 앱을 찾을 수 없습니다.'],
                                    [404, '현재 회사·권한에서 업무 앱을 찾을 수 없습니다.'], [400, '현재 회사·권한에서 업무 앱을 찾을 수 없습니다.']]) {
    responder = async () => new Response(JSON.stringify({ detail: '서버 내부 원문 — 노출 금지' }), { status });
    await assert.rejects(() => module.readKitAppEntry(INSTANCE, APP), error => {
      assert.equal(error.message, expected);
      assert.ok(!error.message.includes('원문'), '서버 원문이 화면 문구로 샜다');
      return true;
    });
  }
});

await test('API 문맥이 바뀌면 응답을 버린다', async () => {
  responder = async () => { identity = { ...initial, tenantId: 'tenant-b' }; return response(); };
  await assert.rejects(() => module.readKitAppEntry(INSTANCE, APP),
    error => error.reasonCode === 'KIT_APP_ENTRY_CONTEXT_CHANGED' && error.status === 409);
});

await test('API 선택 문맥과 다른 조회 문맥은 거절', async () => {
  responder = async () => response({ ...metadata(), viewing_context: { tenant_id: 'tenant-a', scope_node_id: 'other-scope', entity_mode: 'REAL' } });
  await assert.rejects(() => module.readKitAppEntry(INSTANCE, APP),
    error => error.reasonCode === 'KIT_APP_ENTRY_CONTEXT_CHANGED');
});

await test('FLOW 로딩→확인, 재조회 중 기존 데이터 숨김', async () => {
  const f = flow();
  const gate = deferred();
  responder = async () => { await gate.promise; return response(); };
  const first = f.load();
  assert.equal(f.getSnapshot().phase, 'LOADING');
  assert.equal(f.getSnapshot().data, null);
  gate.resolve(); await first;
  assert.equal(f.getSnapshot().phase, 'AVAILABLE');
  assert.equal(f.getSnapshot().data.app_id, APP);
  const second = deferred();
  responder = async () => { await second.promise; return response(); };
  const again = f.load();
  assert.equal(f.getSnapshot().phase, 'LOADING');
  assert.equal(f.getSnapshot().data, null, '재조회 중 이전 데이터가 남았다');
  second.resolve(); await again;
});

await test('FLOW 회사 전환 이벤트는 즉시 무효화한다', async () => {
  const f = flow();
  await f.load();
  assert.equal(f.getSnapshot().phase, 'AVAILABLE');
  window.dispatchEvent(new Event('factory:enterprise-context-changed'));
  assert.equal(f.getSnapshot().phase, 'BLOCKED');
  assert.equal(f.getSnapshot().data, null);
});

await test('FLOW 늦은 응답이 최신 상태를 덮지 않는다', async () => {
  const f = flow();
  const slow = deferred();
  responder = async () => { await slow.promise; return response(); };
  const first = f.load();
  responder = async () => response({ ...metadata(), app_label: '나중 응답' });
  await f.load();
  slow.resolve(); await first;
  assert.equal(f.getSnapshot().data?.app_label, '나중 응답', '늦은 응답이 최신을 덮었다');
});

await test('FLOW 해제 뒤에는 조회도 이벤트 반영도 없다', async () => {
  const f = module.createKitAppEntryFlow(INSTANCE, APP);
  f.activate(); await f.load(); f.dispose();
  const seen = calls.length;
  await f.load();
  window.dispatchEvent(new Event('factory:acting-user-changed'));
  assert.equal(calls.length, seen, '해제 뒤에도 서버를 불렀다');
  assert.equal(f.getSnapshot().phase, 'IDLE');
});

await test('SSR 확인 전에는 자식을 만들지 않고 GET 도 없다', () => {
  const html = renderToStaticMarkup(React.createElement(ui.StudioKitAppEntryGate, {
    instanceId: INSTANCE, appId: APP, children: () => React.createElement('div', null, '자식 STUDIO'),
  }));
  assert.ok(!html.includes('자식 STUDIO'), '확인 전에 자식이 그려졌다');
  assert.ok(html.includes('확인하고 있습니다'));
  assert.equal(calls.length, 0, 'effect 전에 서버를 불렀다');
});

await test('SSR 조회 확인과 실행 허용을 구분해 말한다', () => {
  const state = { phase: 'AVAILABLE', data: metadata(), error: null };
  const html = renderToStaticMarkup(React.createElement(ui.KitAppEntryStatus, { state, onRetry: () => {} }));
  assert.ok(html.includes('조회 가능한 업무 앱'));
  assert.ok(html.includes('다시 확인합니다'), '조회 가능을 실행 승인으로 말하고 있다');
  const blocked = renderToStaticMarkup(React.createElement(ui.KitAppEntryStatus, {
    state: { phase: 'BLOCKED', data: null, error: { message: '현재 회사·권한에서 업무 앱을 찾을 수 없습니다.' } },
    onRetry: () => {},
  }));
  assert.ok(blocked.includes('role="alert"') && blocked.includes('다시 확인'));
});

await test('소스·검사 해시 보존', () => assert.deepEqual(hashes(), before));

const failed = results.filter(row => row.result === 'FAIL');
for (const row of failed) process.stderr.write(`${row.name}: ${row.error}\n`);
process.stdout.write(JSON.stringify({ passed: results.length - failed.length, failed: failed.length,
  browser: 'NOT_RUN', network: 'MOCK_ONLY', source_hashes: before, results }, null, 2) + '\n');
if (failed.length) process.exitCode = 1;
