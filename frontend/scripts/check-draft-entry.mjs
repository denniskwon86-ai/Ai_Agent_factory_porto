// [DRAFT-ENTRY-01] 모의 HTTP + 실제 flow/SSR. 브라우저·실제 서버 권한 검사는 별도다.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const files = ['../src/factory/studioDraftEntry.ts', '../src/factory/StudioDraftEntryGate.tsx',
  '../src/factory/studioEntryFlow.ts', './check-draft-entry.mjs'];
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
const flow_ = load('../src/factory/studioEntryFlow.ts', { './studioInputMemory': memory });
const module = load(files[0], { '../lib/api': api, './studioInputMemory': memory, './studioEntryFlow': flow_ });
const ui = load(files[1], { './studioDraftEntry': module });
const DRAFT = 'adv_1ea9be5dfff4468e9508ac85c61f9b28';
const metadata = () => ({ draft_id: DRAFT, draft_kind: 'blueprint', revision: 2,
  ownership: { tenant_id: 'tenant-a', context_root_id: 'root-a', entity_mode: 'REAL', scope_node_id: 'scope-a' },
  viewing_context: { tenant_id: 'tenant-a', scope_node_id: 'scope-a', entity_mode: 'REAL' } });
const response = (data = metadata(), status = 200) => new Response(JSON.stringify({ status: 'success', data }), { status });
const refusal = (reason_code, status = 422) => new Response(
  JSON.stringify({ detail: { reason_code, message: '서버 원문 — 화면에 옮기면 안 된다', next_action: '...' } }), { status });
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const results = [], flows = [];
function flow(revision = 2) { const f = module.createDraftEntryFlow(DRAFT, 'blueprint', revision); flows.push(f); f.activate(); return f; }
async function test(name, run) {
  identity = { ...initial }; calls = []; responder = async () => response();
  try { await run(); results.push({ name, result: 'PASS' }); }
  catch (error) { results.push({ name, result: 'FAIL', error: String(error.stack || error) }); }
  finally { for (const f of flows.splice(0)) f.dispose(); }
}

// ── ★★★ 경계를 싣지 않는다 ──────────────────────────────────────────────
await test('API 질의에 회사·조직 경계를 «싣지 않는다»', async () => {
  const entry = await module.readDraftEntry(DRAFT, 'blueprint', 2);
  assert.deepEqual(entry, metadata());
  assert.equal(calls.length, 1);
  const url = calls[0].url;
  assert.equal(url, `/api/v1/advisor/drafts/${DRAFT}/entry-metadata?kind=blueprint&revision=2`);
  // ⚠️ 이것이 이 모듈의 존재 이유다 — 프런트가 경계를 지어내지 않는다.
  for (const forbidden of ['context_root_id', 'scope_node_id', 'tenant', 'entity_mode']) {
    assert.ok(!url.includes(forbidden), `질의에 ${forbidden} 가 실렸다: ${url}`);
  }
  assert.equal(calls[0].init.method, 'GET'); assert.equal(calls[0].init.cache, 'no-store');
  assert.equal(calls[0].init.body, undefined);
});
await test('API 허용 필드만 남기고 확장 필드는 복사하지 않는다', async () => {
  responder = async () => response({ ...metadata(), digest: 'a'.repeat(64), status: 'DRAFT',
    blueprint: { secret: 'omit' }, head_revision: 9 });
  const entry = await module.readDraftEntry(DRAFT, 'blueprint', 2);
  assert.deepEqual(entry, metadata());
  assert.equal(JSON.stringify(entry).includes('omit'), false);
});

// ── 통신 전 차단 ──────────────────────────────────────────────────────────
await test('API 잘못된 초안 ID·종류·판본은 통신 전 차단', async () => {
  const bad = [[''], ['../x'], ['a/b'], ['x'.repeat(161)]];
  for (const [id] of bad) {
    await assert.rejects(module.readDraftEntry(id, 'blueprint', 1), e => e.reasonCode === 'ENTRY_INVALID_TARGET');
  }
  for (const kind of ['', 'BLUEPRINT', 'project', 'blueprint2']) {
    await assert.rejects(module.readDraftEntry(DRAFT, kind, 1), e => e.reasonCode === 'ENTRY_INVALID_TARGET');
  }
  for (const revision of [0, -1, 1.5, NaN, Infinity, '2']) {
    await assert.rejects(module.readDraftEntry(DRAFT, 'blueprint', revision), e => e.reasonCode === 'ENTRY_INVALID_TARGET');
  }
  assert.equal(calls.length, 0);
});

// ── 물어본 것이 돌아왔는가 ────────────────────────────────────────────────
await test('API 다른 초안·종류·판본이 오면 계약 위반', async () => {
  const wrong = [{ draft_id: 'adv_other' }, { draft_kind: 'consultation' }, { revision: 3 }];
  for (const change of wrong) {
    responder = async () => response({ ...metadata(), ...change });
    await assert.rejects(module.readDraftEntry(DRAFT, 'blueprint', 2), e => e.reasonCode === 'ENTRY_RESPONSE_INVALID');
  }
});
await test('API 선택 문맥과 다르면 문맥 변경으로 접는다', async () => {
  for (const bad of [{ tenant_id: 'tenant-b' }, { scope_node_id: 'scope-b' }, { entity_mode: 'VIRTUAL' }]) {
    responder = async () => response({ ...metadata(),
      viewing_context: { ...metadata().viewing_context, ...bad } });
    await assert.rejects(module.readDraftEntry(DRAFT, 'blueprint', 2),
      e => e.reasonCode === 'ENTRY_CONTEXT_CHANGED' || e.reasonCode === 'ENTRY_RESPONSE_INVALID');
  }
});

// ── ★ 「지원 전」은 「없다」와 다르게 말한다 ──────────────────────────────
await test('API 지원 전 종류는 «없다» 와 다른 문구로 답한다', async () => {
  responder = async () => refusal('STUDIO_DRAFT_KIND_UNSUPPORTED');
  const unsupported = await module.readDraftEntry(DRAFT, 'consultation', 1).catch(e => e);
  responder = async () => new Response('{}', { status: 404 });
  const missing = await module.readDraftEntry(DRAFT, 'blueprint', 1).catch(e => e);
  assert.equal(unsupported.reasonCode, 'ENTRY_KIND_UNSUPPORTED');
  assert.notEqual(unsupported.message, missing.message);
  assert.match(missing.message, /찾을 수 없습니다/);
  // ⚠️ 서버 원문은 화면 오류로 옮기지 않는다.
  assert.equal(unsupported.message.includes('서버 원문'), false);
  assert.equal(missing.message.includes('서버 원문'), false);
});
await test('API 회사·조직 미선택은 «링크 문제와 다르게» 말한다', async () => {
  //: ⚠️⚠️ [2026-09-16] 실화면에서 잡았다. 종전에는 422 를 몽땅 「초안 링크를 확인하세요」로
  //:   접어서, 링크는 멀쩡한데 링크를 의심하게 만들었다.
  responder = async () => refusal('PROCESS_CONTEXT_REQUIRED');
  const notSelected = await module.readDraftEntry(DRAFT, 'blueprint', 2).catch(e => e);
  assert.equal(notSelected.reasonCode, 'ENTRY_CONTEXT_NOT_SELECTED');
  assert.match(notSelected.message, /회사·조직/);
  assert.equal(notSelected.message.includes('링크를 확인'), false);
  // 링크 형식이 정말 틀린 경우와 «다른» 문구여야 한다.
  const badLink = await module.readDraftEntry('../x', 'blueprint', 2).catch(e => e);
  assert.equal(badLink.reasonCode, 'ENTRY_INVALID_TARGET');
  assert.notEqual(badLink.message, notSelected.message);
  assert.equal(notSelected.message.includes('서버 원문'), false);
});
await test('API 알 수 없는 사유 코드는 일반 문구로 접는다', async () => {
  responder = async () => refusal('SOMETHING_NEW_WE_DO_NOT_KNOW');
  const error = await module.readDraftEntry(DRAFT, 'blueprint', 1).catch(e => e);
  assert.equal(error.reasonCode, 'ENTRY_HTTP_422');
  assert.equal(error.message.includes('서버 원문'), false);
});

// ── FLOW 수명 ─────────────────────────────────────────────────────────────
await test('FLOW 로딩→확인, 재조회 중 기존 데이터 숨김', async () => {
  const f = flow(); const first = f.load();
  assert.equal(f.getSnapshot().phase, 'LOADING'); assert.equal(f.getSnapshot().data, null);
  await first; assert.equal(f.getSnapshot().phase, 'AVAILABLE');
  const wait = deferred(); responder = () => wait.promise;
  const again = f.load(); assert.equal(f.getSnapshot().data, null);
  wait.resolve(response()); await again; assert.equal(f.getSnapshot().phase, 'AVAILABLE');
});
await test('FLOW 해제 후 늦은 응답·재조회 반영 없음', async () => {
  const wait = deferred(); responder = () => wait.promise; const f = flow(); const pending = f.load();
  f.dispose(); wait.resolve(response()); await pending; await f.load();
  window.dispatchEvent(new Event('factory:session-changed'));
  assert.equal(f.getSnapshot().phase, 'IDLE'); assert.equal(f.getSnapshot().data, null); assert.equal(calls.length, 1);
});
for (const event of ['factory:session-changed', 'factory:acting-user-changed', 'factory:enterprise-context-changed']) {
  await test('FLOW 전환시 즉시 제거 ' + event, async () => {
    const f = flow(); await f.load(); assert.equal(f.getSnapshot().phase, 'AVAILABLE');
    window.dispatchEvent(new Event(event));
    assert.equal(f.getSnapshot().phase, 'BLOCKED'); assert.equal(f.getSnapshot().data, null);
    assert.equal(f.getSnapshot().error.reasonCode, 'ENTRY_CONTEXT_CHANGED');
  });
}
await test('FLOW 판본마다 다른 질문을 한다', async () => {
  responder = async () => response({ ...metadata(), revision: 5 });
  const f = flow(5); await f.load();
  assert.equal(f.getSnapshot().phase, 'AVAILABLE');
  assert.ok(calls[0].url.endsWith('revision=5'));
});

// ── SSR ───────────────────────────────────────────────────────────────────
await test('SSR 확인 전 자식 미생성·GET은 effect 전 0', () => {
  let children = 0;
  const html = renderToStaticMarkup(React.createElement(ui.StudioDraftEntryGate,
    { draftId: DRAFT, draftKind: 'blueprint', revision: 2,
      children: () => { children++; return 'SECRET_CHILD'; } }));
  assert.ok(html.includes('확인하고 있습니다')); assert.ok(!html.includes('SECRET_CHILD'));
  assert.equal(children, 0); assert.equal(calls.length, 0);
});
await test('SSR 조회확인과 편집·승인 허용을 구분해 말한다', () => {
  const ready = renderToStaticMarkup(React.createElement(ui.DraftEntryStatus, { onRetry() {},
    state: { phase: 'AVAILABLE', data: metadata(), error: null } }));
  assert.ok(ready.includes('2판')); assert.ok(ready.includes('각각의 단계에서 다시 확인'));
  // 초안 원문·지문을 화면에 그리지 않는다.
  assert.equal(ready.includes('root-a'), false);
  const blocked = renderToStaticMarkup(React.createElement(ui.DraftEntryStatus, { onRetry() {},
    state: { phase: 'BLOCKED', data: null, error: new module.DraftEntryError('확인 실패') } }));
  assert.ok(blocked.includes('role="alert"')); assert.ok(blocked.includes('현재 회사에서 다시 확인'));
});

await test('소스·검사 해시 보존', () => assert.deepEqual(hashes(), before));
const failed = results.filter(row => row.result === 'FAIL');
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length,
  browser: 'NOT_RUN', network: 'MOCK_ONLY', source_hashes: before, results }, null, 2));
if (failed.length) process.exitCode = 1;
