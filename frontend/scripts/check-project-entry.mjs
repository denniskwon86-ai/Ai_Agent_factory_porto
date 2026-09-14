// B6 모의 HTTP + 실제 flow/SSR. 브라우저·실제 서버 권한 검사는 별도다.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const files = ['../src/factory/studioProjectEntry.ts', '../src/factory/StudioProjectEntryGate.tsx', './check-project-entry.mjs'];
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
const module = load(files[0], { '../lib/api': api, './studioInputMemory': { studioIdentityKey: () => JSON.stringify(identity) } });
const ui = load(files[1], { './studioProjectEntry': module });
const metadata = () => ({ project_id: 'P1', project_name: '구매 계획', runtime_document_version: '1.0',
  ownership: { tenant_id: 'tenant-a', enterprise_scope_id: 'child-scope', entity_mode: 'REAL' },
  viewing_context: { tenant_id: 'tenant-a', scope_node_id: 'scope-a', entity_mode: 'REAL' } });
const response = (data = metadata(), status = 200) => new Response(JSON.stringify({ status: 'success', data }), { status });
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const results = [], flows = [];
function flow() { const f = module.createProjectEntryFlow('P1'); flows.push(f); f.activate(); return f; }
async function test(name, run) {
  identity = { ...initial }; calls = []; responder = async () => response();
  try { await run(); results.push({ name, result: 'PASS' }); }
  catch (error) { results.push({ name, result: 'FAIL', error: String(error.stack || error) }); }
  finally { for (const f of flows.splice(0)) f.dispose(); }
}
await test('API 단건 GET·no-store·허용 필드만 반환', async () => {
  responder = async () => response({ ...metadata(), state: { secret: 'omit' }, can_release: true });
  assert.deepEqual(await module.readProjectEntry('P1'), metadata());
  assert.equal(calls.length, 1); assert.equal(calls[0].url, '/api/v1/factory/P1/entry-metadata');
  assert.equal(calls[0].init.method, 'GET'); assert.equal(calls[0].init.cache, 'no-store'); assert.equal(calls[0].init.body, undefined);
});
await test('API 2.0·서버 기본 문맥 허용·하위범위 판정은 서버 담당', async () => {
  identity = { ...initial, tenantId: '', scopeNodeId: '', entityMode: '' };
  responder = async () => response({ ...metadata(), runtime_document_version: '2.0' });
  assert.equal((await module.readProjectEntry('P1')).runtime_document_version, '2.0');
});
await test('API 잘못된 프로젝트 ID는 통신 전 차단', async () => {
  for (const id of ['', '../P1', 'P1/P2', 'P1?x=1', 'x'.repeat(161)]) {
    await assert.rejects(module.readProjectEntry(id), e => e.reasonCode === 'ENTRY_INVALID_TARGET');
  }
  assert.equal(calls.length, 0);
});
for (const status of [401, 403, 404, 409, 500, 503]) await test('API HTTP ' + status + '·민감 상세 미노출', async () => {
  responder = async () => new Response(JSON.stringify({ detail: 'SECRET_SERVER_BODY' }), { status });
  await assert.rejects(module.readProjectEntry('P1'), e => e.status === status && !e.message.includes('SECRET'));
});
await test('API 대상/이름/버전/소유문맥 손상 거절', async () => {
  for (const data of [{ ...metadata(), project_id: 'P2' }, { ...metadata(), project_name: '' },
    { ...metadata(), runtime_document_version: ['1.0'] }, { ...metadata(), runtime_document_version: '3.0' },
    { ...metadata(), ownership: {} }, { ...metadata(), ownership: { ...metadata().ownership, tenant_id: 'other' } },
    { ...metadata(), viewing_context: { ...metadata().viewing_context, entity_mode: 'VIRTUAL' } }]) {
    responder = async () => response(data);
    await assert.rejects(module.readProjectEntry('P1'), e => e.reasonCode === 'ENTRY_RESPONSE_INVALID');
  }
});
for (const key of ['tenantId', 'scopeNodeId', 'entityMode']) await test('API 선택 문맥 불일치 ' + key, async () => {
  identity[key] = 'different'; await assert.rejects(module.readProjectEntry('P1'), e => e.reasonCode === 'ENTRY_CONTEXT_CHANGED');
});
await test('API JSON 해석 중 로그인 교체 응답 폐기', async () => {
  responder = async () => ({ ok: true, status: 200, json: async () => {
    identity.token = 'changed'; return { status: 'success', data: metadata() };
  } });
  await assert.rejects(module.readProjectEntry('P1'), e => e.reasonCode === 'ENTRY_CONTEXT_CHANGED');
});
await test('API 파싱/네트워크 실패는 503·본문 미노출', async () => {
  responder = async () => new Response('not json', { status: 200 });
  await assert.rejects(module.readProjectEntry('P1'), { status: 503 });
  responder = async () => { throw new Error('SECRET'); };
  await assert.rejects(module.readProjectEntry('P1'), e => e.status === 503 && !e.message.includes('SECRET'));
});
await test('FLOW 로딩→확인, 재조회 중 기존 데이터 숨김', async () => {
  const f = flow(); await f.load(); assert.equal(f.getSnapshot().phase, 'AVAILABLE');
  const wait = deferred(); responder = () => wait.promise;
  const pending = f.load(); assert.deepEqual(f.getSnapshot(), { phase: 'LOADING', data: null, error: null });
  wait.resolve(response()); await pending; assert.equal(f.getSnapshot().data.project_id, 'P1');
});
for (const event of ['factory:session-changed', 'factory:acting-user-changed', 'factory:enterprise-context-changed']) {
  await test('FLOW 전환시 즉시 제거·자동 조회 없음 ' + event, async () => {
    const f = flow(); await f.load(); window.dispatchEvent(new Event(event));
    assert.equal(f.getSnapshot().phase, 'BLOCKED'); assert.equal(f.getSnapshot().data, null); assert.equal(calls.length, 1);
    await f.load(); assert.equal(f.getSnapshot().phase, 'AVAILABLE'); assert.equal(calls.length, 2);
  });
}
await test('FLOW A→B→A 뒤 늦은 A 응답도 폐기', async () => {
  const wait = deferred(); responder = () => wait.promise; const f = flow(); const pending = f.load();
  identity.scopeNodeId = 'B'; window.dispatchEvent(new Event('factory:enterprise-context-changed'));
  identity.scopeNodeId = 'scope-a'; window.dispatchEvent(new Event('factory:enterprise-context-changed'));
  wait.resolve(response()); await pending;
  assert.equal(f.getSnapshot().phase, 'BLOCKED'); assert.equal(f.getSnapshot().data, null);
  assert.equal(calls[0].init.signal.aborted, true); assert.equal(calls.length, 1);
});
await test('FLOW 최신 요청 우선·역순 응답 덮어쓰기 금지', async () => {
  const wait = deferred(); responder = () => wait.promise; const f = flow(); const first = f.load();
  responder = async () => response({ ...metadata(), project_name: '최신' }); await f.load();
  wait.resolve(response()); await first; assert.equal(f.getSnapshot().data.project_name, '최신');
});
await test('FLOW 해제 후 늦은 응답·재조회·이벤트 반영 없음', async () => {
  const wait = deferred(); responder = () => wait.promise; const f = flow(); const pending = f.load();
  f.dispose(); wait.resolve(response()); await pending; await f.load(); window.dispatchEvent(new Event('factory:session-changed'));
  assert.equal(f.getSnapshot().phase, 'IDLE'); assert.equal(f.getSnapshot().data, null); assert.equal(calls.length, 1);
});
await test('FLOW 권한 거절 후 이전 프로젝트 표시 없음', async () => {
  const f = flow(); await f.load(); responder = async () => response(null, 404); await f.load();
  assert.equal(f.getSnapshot().phase, 'BLOCKED'); assert.equal(f.getSnapshot().data, null);
});
await test('SSR 확인 전 자식 Studio 미생성·GET은 effect 전 0', () => {
  let children = 0;
  const html = renderToStaticMarkup(React.createElement(ui.StudioProjectEntryGate, { projectId: 'P1',
    children: () => { children++; return 'SECRET_CHILD'; } }));
  assert.ok(html.includes('확인하고 있습니다')); assert.ok(!html.includes('SECRET_CHILD'));
  assert.equal(children, 0); assert.equal(calls.length, 0);
});
await test('SSR 조회확인과 실행허용 구분·오류/재시도 표시', () => {
  const ready = renderToStaticMarkup(React.createElement(ui.ProjectEntryStatus, { onRetry() {},
    state: { phase: 'AVAILABLE', data: metadata(), error: null } }));
  assert.ok(ready.includes('구매 계획')); assert.ok(ready.includes('각각의 단계에서 다시 확인'));
  const blocked = renderToStaticMarkup(React.createElement(ui.ProjectEntryStatus, { onRetry() {},
    state: { phase: 'BLOCKED', data: null, error: new module.ProjectEntryError('확인 실패') } }));
  assert.ok(blocked.includes('role="alert"')); assert.ok(blocked.includes('현재 회사에서 다시 확인'));
});
await test('소스·검사 해시 보존', () => assert.deepEqual(hashes(), before));
const failed = results.filter(row => row.result === 'FAIL');
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length,
  browser: 'NOT_RUN', network: 'MOCK_ONLY', source_hashes: before, results }, null, 2));
if (failed.length) process.exitCode = 1;
