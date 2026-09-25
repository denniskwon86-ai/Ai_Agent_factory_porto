// 실제 TS 컨트롤러·어댑터와 React SSR을 검사한다. API·인증은 메모리 대역이며 서버 검증이 아니다.
// 병렬 작성 중에는 실행하지 않는다. 메인이 소스 동결 뒤 이 스크립트를 실행한다.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createHash, randomUUID } from 'node:crypto';

const evidenceFiles = ['../src/lib/processInstallationApi.ts', '../src/lib/processInstallationFlow.ts',
  '../src/lib/processConfigurationEdit.ts', '../src/lib/processStructureEdit.ts', '../src/components/ProcessConfigurationEditor.tsx',
  '../src/components/ProcessStructureEditor.tsx',
  '../src/lib/companyApi.ts', '../src/components/ProcessInstallationPanel.tsx',
  '../src/components/process-installation.css', '../src/components/CompanySetupPanel.tsx',
  '../src/components/EnterprisePage.tsx', '../src/components/KitOperationsPanel.tsx',
  '../tests/process-installation.fixture.tsx', '../tests/process-installation.fixture.html',
  './check-process-installation.mjs', './build-process-installation-fixture.mjs'];
const sourceHashes = () => Object.fromEntries(evidenceFiles.map((file) => [file,
  createHash('sha256').update(fs.readFileSync(new URL(file, import.meta.url))).digest('hex')]));
const beforeHashes = sourceHashes();
const startedAt = new Date().toISOString();
const startedMs = performance.now();

const copy = (value) => structuredClone(value);
function loadTs(relative, dependencies = {}) {
  const file = new URL(relative, import.meta.url);
  const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  } }).outputText;
  const module = { exports: {} };
  const nativeRequire = createRequire(file);
  const require = (name) => {
    if (Object.hasOwn(dependencies, name)) return dependencies[name];
    if (name === '../lib/processConfigurationEdit') return editModule;
    if (name === './ProcessConfigurationEditor') return editorComponentModule;
    if (['react', 'react/jsx-runtime', 'lucide-react'].includes(name)) return nativeRequire(name);
    throw new Error(`격리 시험: 허용하지 않은 모듈 ${name}`);
  };
  new Function('module', 'exports', 'require', compiled)(module, module.exports, require);
  return module.exports;
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

const identityBase = { tenantId: 'SYNTHETIC-TENANT', scopeNodeId: 'SYNTHETIC-SCOPE',
  entityMode: 'REAL', user: 'synthetic-user', token: 'synthetic-memory-only-token' };
let identity = copy(identityBase);
let transport = async () => { throw new Error('격리 시험: API 대역을 먼저 지정해야 합니다.'); };
const apiModule = loadTs('../src/lib/processInstallationApi.ts', { './api': {
  getEnterpriseContext: () => ({ tenantId: identity.tenantId,
    scopeNodeId: identity.scopeNodeId, entityMode: identity.entityMode }),
  getActingUser: () => identity.user, getSessionToken: () => identity.token,
  apiFetch: (...args) => transport(...args),
} });
const { ProcessApiError, createProcessInstallationApi, unwrapProcessResponse } = apiModule;
const flowModule = loadTs('../src/lib/processInstallationFlow.ts', {
  './processInstallationApi': apiModule,
});
const { createInstallationFlow } = flowModule;
const structureModule = loadTs('../src/lib/processStructureEdit.ts', { './processInstallationApi': apiModule });
const { applyProcessStep, replayProcessSteps } = structureModule;
const editModule = loadTs('../src/lib/processConfigurationEdit.ts', {
  './processInstallationApi': apiModule, './processStructureEdit': structureModule,
});
const structureComponentModule = loadTs('../src/components/ProcessStructureEditor.tsx', {
  '../lib/processConfigurationEdit': editModule,
});
const editorComponentModule = loadTs('../src/components/ProcessConfigurationEditor.tsx', {
  '../lib/processConfigurationEdit': editModule,
  './ProcessStructureEditor': structureComponentModule,
});
const { createProcessEditFlow, orderedPlacements, buildProcessEditCommands } = editModule;
const boundary = { tenant_id: 'SYNTHETIC-TENANT', context_root_id: 'SYNTHETIC-ROOT',
  scope_node_id: 'SYNTHETIC-SCOPE', entity_mode: 'REAL', configuration_kind: 'business_process' };
const document = { nodes: [
  { process_id: 'synthetic-l1', level: 'L1', parent_process_id: '', label: '원료 구매', note: '', enabled: true },
  { process_id: 'synthetic-l2', level: 'L2', parent_process_id: 'synthetic-l1', label: '구매 계획', note: '', enabled: true },
], placements: [
  { placement_id: 'placement-l1', process_id: 'synthetic-l1', parent_process_id: '', position: 0, hidden: false, kind: 'CANONICAL' },
  { placement_id: 'placement-l2', process_id: 'synthetic-l2', parent_process_id: 'synthetic-l1', position: 0, hidden: false, kind: 'CANONICAL' },
], template_sources: [{ artifact_digest: 'a'.repeat(64), kit_instance_ref: 'synthetic-instance' }] };
const pack = { kit_id: 'KIT-MFG-NONFERROUS-PROCUREMENT', version: '1.1.0', artifact_digest: 'a'.repeat(64),
  name: '합성 표준 업무', state: 'DOMAIN_REVIEW_REQUIRED', data_class: 'NO_DATA',
  setup_only: true, business_kit_ids: ['BK-01', 'BK-02'],
  business_kits: [{ business_kit_id: 'BK-01', label: '원료 구매' }, { business_kit_id: 'BK-02', label: '원료 입고' }] };
const resolved = { boundary, configuration_id: 'synthetic-configuration', head_version: 7,
  profile_id: 'synthetic-profile', digest: 'b'.repeat(64), state: 'APPROVED',
  payload: document, legacy_review_required: false };
const plan = { plan_digest: 'c'.repeat(64), preview: document, state: 'READY',
  warnings: ['DOMAIN_REVIEW_REQUIRED'], data_ready: false, apps_ready: false };
const operation = { operation_id: 'synthetic-operation', configuration_id: 'synthetic-configuration',
  plan_digest: plan.plan_digest, stage: 'AWAITING_APPROVAL', error_code: '',
  kit_instance_ref: 'synthetic-instance', change_id: 'synthetic-change', actor: 'synthetic-user',
  installer: 'synthetic-installer', revision: 1, applied_profile_id: '', data_ready: false, apps_ready: false };
const input = { context_root_id: boundary.context_root_id, scope_node_id: boundary.scope_node_id,
  artifact_digest: pack.artifact_digest, business_kit_ids: ['BK-01'], expected_head_version: 7,
  base_profile_id: resolved.profile_id, base_fingerprint: resolved.digest, legacy_decisions: [],
  template_mapping: {}, instance_id: 'synthetic-instance', reason: '합성 설치 이유' };

function harness(overrides = {}) {
  const calls = [];
  const defaults = {
    access: () => ({ boundary, context_root_label: '합성 회사', target_label: '합성 구매팀', permitted_actions: ['propose', 'edit'] }),
    resolved: () => resolved, catalog: () => [pack], legacy: () => ({ sources: [] }),
    register: () => ({ artifact_digest: pack.artifact_digest }), plan: () => plan,
    start: () => operation, list: () => ({ items: [operation], next_offset: null }), get: () => operation,
    changes: () => ({ items: [], next_offset: null }),
    change: () => { throw new Error('합성 변경안 대역을 지정하세요.'); },
    resume: () => { throw new Error('합성 재개 대역을 지정하세요.'); },
    approve: () => { throw new Error('합성 승인 대역을 지정하세요.'); },
    propose: () => { throw new Error('합성 편집 제안 대역을 지정하세요.'); },
  };
  const api = Object.fromEntries(Object.entries(defaults).map(([name, implementation]) => [name, async (...args) => {
    calls.push({ name, args: copy(args) });
    const value = copy(await (overrides[name] || implementation)(...args));
    return name === 'access' ? { principal_user_id: 'synthetic-user', ...value } : value;
  }]));
  let ids = 0;
  const flow = createInstallationFlow(api, true, () => `synthetic-request-${++ids}`);
  return { api, flow, calls, ids: () => ids };
}
async function prepare(h) {
  await h.flow.load();
  assert.equal(h.flow.getSnapshot().error, null);
  h.flow.selectPack(pack);
  h.flow.selectKit('BK-02', false);
  h.flow.setReason('  합성 설치 이유  ');
  await h.flow.prepare();
  assert.equal(h.flow.getSnapshot().error, null);
  assert.deepEqual(h.flow.getSnapshot().prepared.input, input);
}
const cases = [];
const test = (name, work) => cases.push({ name, work });
const response = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
});
const succeeds = (data) => response({ status: 'success', data });
const isError = (status, reasonCode) => (error) => error instanceof ProcessApiError
  && error.status === status && (reasonCode === undefined || error.reasonCode === reasonCode);

test('컨트롤러: 조회·계획의 묵시 등록 없음 / 명시 등록 1회', async () => {
  const h = harness();
  await prepare(h);
  assert.equal(h.calls.filter((call) => ['register', 'start'].includes(call.name)).length, 0);
  await h.flow.register();
  assert.equal(h.calls.filter((call) => call.name === 'register').length, 1);
  assert.equal(h.flow.getSnapshot().registeredDigest, pack.artifact_digest);
});

test('컨트롤러: 원래 계획 입력·지문·키 전송 / 중복 클릭 차단 / 후속 GET', async () => {
  const pending = deferred();
  const h = harness({ start: () => pending.promise });
  await prepare(h);
  const saved = copy(h.flow.getSnapshot().prepared);
  const first = h.flow.start();
  await h.flow.start();
  assert.equal(h.calls.filter((call) => call.name === 'start').length, 1);
  assert.deepEqual(h.calls.find((call) => call.name === 'start').args,
    [input, saved.plan.plan_digest, saved.requestId]);
  assert.ok(!Object.hasOwn(saved.input, 'preview'));
  h.flow.setReason('중복 클릭 중 변경 시도');
  assert.equal(h.flow.getSnapshot().reason, '  합성 설치 이유  ');
  pending.resolve(operation);
  await first;
  assert.deepEqual(h.calls.slice(-2).map((call) => call.name), ['start', 'get']);
  assert.equal(h.flow.getSnapshot().operation.operation_id, operation.operation_id);
  assert.equal(h.ids(), 1);
});

test('컨트롤러: 응답 유실 뒤 명시 재시도도 같은 원본·지문·요청 키', async () => {
  let attempts = 0;
  const h = harness({ start: () => {
    if (++attempts === 1) throw new ProcessApiError(503, '합성 응답 유실', 'SYNTHETIC_UNAVAILABLE');
    return operation;
  } });
  await prepare(h);
  const prepared = copy(h.flow.getSnapshot().prepared);
  await h.flow.start();
  assert.equal(h.flow.getSnapshot().error.status, 503);
  assert.deepEqual(h.flow.getSnapshot().prepared, prepared);
  assert.equal(attempts, 1);
  await h.flow.start();
  const starts = h.calls.filter((call) => call.name === 'start');
  assert.equal(starts.length, 2);
  assert.deepEqual(starts[0].args, starts[1].args);
  assert.equal(h.ids(), 1);
});

test('컨트롤러: 409 후 이유·업무·기존 구성 선택·계획 보존', async () => {
  const legacy = { profile_id: 'synthetic-legacy', source_digest: 'd'.repeat(64), status: 'APPROVED',
    payload: { nodes: [{ key: 'old-process', label: '기존 업무' }] } };
  const h = harness({ legacy: () => ({ sources: [legacy] }),
    start: () => { throw new ProcessApiError(409, '합성 충돌', 'STALE_PLAN', '입력을 확인하세요.'); } });
  await h.flow.load(); h.flow.selectPack(pack); h.flow.setReason('보존할 합성 이유');
  h.flow.setLegacyChoice(legacy.profile_id, 'KEEP_LEGACY');
  await h.flow.prepare();
  const before = copy(h.flow.getSnapshot());
  await h.flow.start();
  const after = h.flow.getSnapshot();
  for (const key of ['reason', 'selectedDigest', 'selectedKits', 'legacyChoices', 'prepared']) {
    assert.deepEqual(after[key], before[key]);
  }
  assert.equal(after.error.status, 409);
  assert.equal(after.error.reasonCode, 'STALE_PLAN');
  assert.equal(h.calls.filter((call) => call.name === 'start').length, 1);
  assert.equal(h.calls.filter((call) => call.name === 'get').length, 0);
});

test('컨트롤러: 기존 설치 목록 복구·상세 새로고침은 GET 역할 메서드만', async () => {
  const h = harness();
  await h.flow.load(); await h.flow.refresh(operation.operation_id); await h.flow.refresh();
  assert.ok(h.calls.every((call) => ['access', 'resolved', 'catalog', 'legacy', 'list', 'get'].includes(call.name)));
  assert.equal(h.calls.filter((call) => call.name === 'get').length, 2);
  assert.equal(h.flow.getSnapshot().prepared, null);
  assert.equal(h.ids(), 0);
});

test('컨트롤러: 문맥 전환·unmount 뒤 늦은 조회 결과 폐기', async () => {
  const pending = deferred();
  const entered = deferred();
  const h = harness({ catalog: () => { entered.resolve(); return pending.promise; } });
  let notices = 0;
  const unsubscribe = h.flow.subscribe(() => { notices++; });
  const loading = h.flow.load();
  await entered.promise;
  assert.ok(h.calls.some((call) => call.name === 'catalog'));
  unsubscribe(); h.flow.invalidate();
  const frozen = h.flow.getSnapshot();
  const noticeCount = notices;
  pending.resolve([pack]); await loading;
  assert.equal(h.flow.getSnapshot(), frozen);
  assert.equal(h.flow.getSnapshot().loaded, false);
  assert.equal(notices, noticeCount);
});

test('컨트롤러: 폐기된 화면의 start 응답은 상태 갱신·후속 GET 없음', async () => {
  const pending = deferred();
  const h = harness({ start: () => pending.promise });
  await prepare(h);
  const starting = h.flow.start();
  h.flow.invalidate();
  const frozen = h.flow.getSnapshot();
  pending.resolve(operation); await starting;
  assert.equal(h.flow.getSnapshot(), frozen);
  assert.equal(h.calls.filter((call) => call.name === 'get').length, 0);
});

test('컨트롤러: 첫 503을 정상 빈 구성으로 바꾸지 않음', async () => {
  const h = harness({ resolved: () => { throw new ProcessApiError(503, '합성 조회 장애'); } });
  await h.flow.load();
  const state = h.flow.getSnapshot();
  assert.equal(state.loaded, false); assert.equal(state.resolved, null);
  assert.equal(state.error.status, 503); assert.equal(state.busy, '');
});

test('컨트롤러: 새로고침 503도 마지막 정상 구성·설치 상태 보존', async () => {
  let unavailable = false;
  const h = harness({ resolved: () => {
    if (unavailable) throw new ProcessApiError(503, '합성 조회 장애');
    return resolved;
  } });
  await h.flow.load(); await h.flow.refresh(operation.operation_id);
  const before = copy(h.flow.getSnapshot()); unavailable = true;
  await h.flow.refresh();
  const after = h.flow.getSnapshot();
  assert.equal(after.error.status, 503); assert.equal(after.loaded, true);
  for (const key of ['resolved', 'operations', 'operation']) assert.deepEqual(after[key], before[key]);
});

for (const reasonCode of ['PROCESS_PLAN_CONFLICT', 'PROCESS_HEAD_CONFLICT', 'PROCESS_DIGEST_CONFLICT', 'PROCESS_LEGACY_CONFLICT']) {
  test(`컨트롤러: 확정 409 ${reasonCode}만 명시 재계획 허용`, async () => {
    const h = harness({ start: () => { throw new ProcessApiError(409, '합성 확정 충돌', reasonCode); } });
    await prepare(h); await h.flow.start();
    const before = copy(h.flow.getSnapshot());
    assert.equal(before.startRejected, true);
    const callCount = h.calls.length;
    await h.flow.replan();
    const after = h.flow.getSnapshot();
    assert.deepEqual(h.calls.slice(callCount).map((call) => call.name), ['access', 'resolved', 'legacy']);
    for (const key of ['reason', 'selectedKits', 'selectedDigest']) assert.deepEqual(after[key], before[key]);
    assert.equal(after.prepared, null); assert.equal(after.startAttempted, false); assert.equal(after.startRejected, false);
    assert.equal(h.ids(), 1);
  });
}

test('컨트롤러: 재계획은 최신 base·원장 조회 후 기존 선택 재확인 / 검토 전 새 키 없음', async () => {
  let newest = false;
  let conflict = true;
  let plans = 0;
  const source = { profile_id: 'synthetic-legacy', source_digest: 'd'.repeat(64), status: 'APPROVED',
    payload: { nodes: [{ key: 'old-process', label: '기존 업무' }] } };
  const h = harness({
    resolved: () => newest ? { ...resolved, head_version: 8, profile_id: 'synthetic-new-profile', digest: 'e'.repeat(64) } : resolved,
    legacy: () => ({ sources: [{ ...source, source_digest: newest ? 'f'.repeat(64) : source.source_digest }] }),
    plan: () => ({ ...plan, plan_digest: (++plans).toString(16).padStart(64, '0') }),
    start: (_body, digest) => {
      if (conflict) throw new ProcessApiError(409, '합성 확정 충돌', 'PROCESS_HEAD_CONFLICT');
      return { ...operation, plan_digest: digest };
    },
  });
  await h.flow.load(); h.flow.selectPack(pack); h.flow.setReason('다시 검토할 이유');
  h.flow.setLegacyChoice(source.profile_id, 'KEEP_LEGACY'); await h.flow.prepare();
  const first = copy(h.flow.getSnapshot().prepared);
  await h.flow.start(); newest = true; await h.flow.replan();
  assert.deepEqual(h.flow.getSnapshot().legacyChoices, {});
  assert.equal(h.flow.getSnapshot().prepared, null); assert.equal(h.ids(), 1);
  await h.flow.prepare();
  assert.equal(h.flow.getSnapshot().error.status, 422); assert.equal(plans, 1);
  h.flow.setLegacyChoice(source.profile_id, 'KEEP_LEGACY'); await h.flow.prepare();
  const next = h.flow.getSnapshot().prepared;
  assert.notEqual(next.requestId, first.requestId); assert.notEqual(next.plan.plan_digest, first.plan.plan_digest);
  assert.equal(next.input.expected_head_version, 8); assert.equal(next.input.base_profile_id, 'synthetic-new-profile');
  assert.equal(next.input.base_fingerprint, 'e'.repeat(64));
  assert.equal(next.input.legacy_decisions[0].source_digest, 'f'.repeat(64));
  assert.equal(next.input.reason, first.input.reason); assert.deepEqual(next.input.business_kit_ids, first.input.business_kit_ids);
  conflict = false; await h.flow.start();
  assert.equal(h.flow.getSnapshot().error, null);
  assert.deepEqual(h.calls.filter((call) => call.name === 'start').at(-1).args,
    [next.input, next.plan.plan_digest, next.requestId]);
});

for (const [name, error] of [
  ['알 수 없는 409', new ProcessApiError(409, '합성 미확정', 'UNKNOWN_CONFLICT')],
  ['503과 알려진 코드 조합', new ProcessApiError(503, '합성 미확정', 'PROCESS_PLAN_CONFLICT')],
  ['연결 유실', new Error('합성 연결 유실')],
]) {
  test(`컨트롤러: ${name}는 재계획 금지 / 기존 요청 키 유지`, async () => {
    const h = harness({ start: () => { throw error; } });
    await prepare(h); const prepared = copy(h.flow.getSnapshot().prepared);
    await h.flow.start(); assert.equal(h.flow.getSnapshot().startRejected, false);
    const callCount = h.calls.length; await h.flow.replan();
    assert.equal(h.calls.length, callCount); assert.deepEqual(h.flow.getSnapshot().prepared, prepared);
    assert.equal(h.flow.getSnapshot().startAttempted, true);
    await h.flow.start();
    const starts = h.calls.filter((call) => call.name === 'start');
    assert.equal(starts.length, 2); assert.deepEqual(starts[0].args, starts[1].args); assert.equal(h.ids(), 1);
  });
}

for (const status of [401, 403, 404]) {
  test(`컨트롤러: ${status}이면 이전 결과 숨김 / 권한 복구 뒤 입력·키 보존`, async () => {
    let denied = false;
    const h = harness({ access: () => {
      if (denied) throw new ProcessApiError(status, '합성 접근 차단');
      return { boundary, permitted_actions: ['propose', 'edit'] };
    } });
    await prepare(h); await h.flow.start(); const before = copy(h.flow.getSnapshot());
    denied = true; await h.flow.refresh(); const hidden = h.flow.getSnapshot();
    assert.equal(hidden.error.status, status); assert.equal(hidden.loaded, false);
    for (const key of ['access', 'resolved', 'operation']) assert.equal(hidden[key], null);
    for (const key of ['packs', 'operations']) assert.deepEqual(hidden[key], []);
    for (const key of ['prepared', 'reason', 'selectedKits', 'selectedDigest']) assert.deepEqual(hidden[key], before[key]);
    denied = false; await h.flow.load();
    assert.equal(h.flow.getSnapshot().loaded, true); assert.deepEqual(h.flow.getSnapshot().prepared, before.prepared);
    assert.equal(h.calls.filter((call) => call.name === 'start').length, 1);
    await h.flow.start();
    const starts = h.calls.filter((call) => call.name === 'start');
    assert.deepEqual(starts[0].args, starts[1].args); assert.equal(h.ids(), 1);
  });
}

test('컨트롤러: 서버 boundary 변경은 차단하고 명시 확인 뒤 새 범위 조회', async () => {
  let updated = false;
  const latest = { ...boundary, context_root_id: 'SYNTHETIC-NEW-ROOT' };
  const h = harness({ access: () => ({ boundary: updated ? latest : boundary, permitted_actions: ['propose', 'edit'] }),
    resolved: () => ({ ...resolved, boundary: updated ? latest : boundary }) });
  await h.flow.load(); updated = true;
  const callCount = h.calls.length; await h.flow.refresh();
  assert.equal(h.calls[callCount].name, 'access');
  assert.deepEqual(h.calls.slice(callCount).map((item) => item.name), ['access']);
  assert.equal(h.flow.getSnapshot().boundaryChanged, true);
  assert.equal(h.flow.getSnapshot().loaded, false);
  const blockedCount = h.calls.length;
  await h.flow.start(); await h.flow.prepare(); await h.flow.register(); await h.flow.refresh();
  assert.equal(h.calls.length, blockedCount);
  await h.flow.confirmBoundary();
  assert.equal(h.flow.getSnapshot().boundaryChanged, false);
  for (const call of h.calls.slice(blockedCount).filter((item) => ['list', 'resolved'].includes(item.name))) {
    assert.deepEqual(call.args[0], latest);
  }
});

test('컨트롤러: 권한 회수로 access가 지워져도 최초 boundary·미확정 키 보존', async () => {
  let mode = 'old';
  const latest = { ...boundary, context_root_id: 'SYNTHETIC-NEW-ROOT' };
  const h = harness({ access: () => {
    if (mode === 'denied') throw new ProcessApiError(403, '합성 회수');
    return { boundary: mode === 'new' ? latest : boundary, permitted_actions: ['propose', 'edit'] };
  }, start: () => { throw new ProcessApiError(503, '합성 응답 유실'); } });
  await prepare(h); await h.flow.start(); const pending = copy(h.flow.getSnapshot().prepared);
  mode = 'denied'; await h.flow.refresh(); assert.equal(h.flow.getSnapshot().access, null);
  mode = 'new'; await h.flow.load();
  assert.equal(h.flow.getSnapshot().boundaryChanged, true);
  assert.deepEqual(h.flow.getSnapshot().prepared, pending);
  await h.flow.confirmBoundary();
  assert.deepEqual(h.flow.getSnapshot().preservedAttempts, [pending]);
  assert.equal(h.flow.getSnapshot().prepared, null);
  assert.equal(h.calls.filter((c) => c.name === 'start').length, 1);
  assert.equal(h.ids(), 1);
});

test('컨트롤러: 과거 요청 상세 조회는 이번 제출·미확정 재시도를 막지 않음', async () => {
  let lost = true;
  const historical = { ...operation, operation_id: 'synthetic-older-operation' };
  const h = harness({ get: (id) => id === historical.operation_id ? historical : operation,
    start: () => { if (lost) throw new ProcessApiError(503, '합성 유실'); return operation; } });
  await prepare(h); await h.flow.refresh(historical.operation_id);
  assert.equal(h.flow.getSnapshot().submittedOperationId, '');
  await h.flow.start(); const pending = copy(h.flow.getSnapshot().prepared);
  assert.equal(h.flow.getSnapshot().operation.operation_id, historical.operation_id);
  lost = false; await h.flow.start();
  assert.equal(h.flow.getSnapshot().submittedOperationId, operation.operation_id);
  await h.flow.refresh(historical.operation_id);
  assert.equal(h.flow.getSnapshot().submittedOperationId, operation.operation_id);
  assert.deepEqual(h.flow.getSnapshot().prepared, pending);
  assert.deepEqual(h.calls.filter((c) => c.name === 'start')[0].args, h.calls.filter((c) => c.name === 'start')[1].args);
});

test('컨트롤러: 외부 운영 경계 A→B→A는 원요청 복원·새 키 계획 차단', async () => {
  let current = boundary;
  const other = { ...boundary, context_root_id: 'SYNTHETIC-ROOT-B' };
  const h = harness({ access: () => ({ boundary: current, permitted_actions: ['propose', 'edit'] }),
    start: () => { throw new ProcessApiError(503, '합성 접수 후 응답 유실'); } });
  await prepare(h); await h.flow.start(); const original = copy(h.flow.getSnapshot().prepared);
  current = other; await h.flow.refresh(); await h.flow.confirmBoundary();
  assert.equal(h.flow.getSnapshot().prepared, null);
  current = boundary; await h.flow.refresh(); await h.flow.confirmBoundary();
  const restored = h.flow.getSnapshot();
  assert.deepEqual(restored.prepared, original); assert.equal(restored.startAttempted, true);
  await h.flow.prepare(); assert.equal(h.ids(), 1);
  await h.flow.start();
  const starts = h.calls.filter((c) => c.name === 'start');
  assert.deepEqual(starts[0].args, starts[1].args);
});

test('컨트롤러: 적용 범위 왕복의 모델 재연결은 미확정 입력·키 유지', async () => {
  const h = harness({ start: () => { throw new ProcessApiError(503, '합성 유실'); } });
  await prepare(h); await h.flow.start(); const pending = copy(h.flow.getSnapshot().prepared);
  h.flow.invalidate(); await h.flow.load(); await h.flow.start();
  assert.deepEqual(h.flow.getSnapshot().prepared, pending);
  assert.equal(h.ids(), 1);
  assert.deepEqual(h.calls.filter((c) => c.name === 'start')[0].args, h.calls.filter((c) => c.name === 'start')[1].args);
});

test('어댑터: 구조화 오류의 status·reason_code·next_action 보존', async () => {
  await assert.rejects(unwrapProcessResponse(response({ detail: {
    message: '합성 충돌', reason_code: 'STALE_PLAN', next_action: '입력과 현재 구성을 확인하세요.',
  } }, 409)), (error) => isError(409, 'STALE_PLAN')(error)
    && error.message === '합성 충돌' && error.nextAction === '입력과 현재 구성을 확인하세요.');
  await assert.rejects(unwrapProcessResponse(response({ detail: '문자열 오류' }, 403)),
    (error) => isError(403)(error) && error.message === '문자열 오류');
});

test('어댑터: 503·잘못된 성공 봉투는 빈 배열로 정상화하지 않음', async () => {
  for (const body of [{}, { status: 'success' }, { status: 'success', data: null }, { status: 'error', data: [] }]) {
    await assert.rejects(unwrapProcessResponse(response(body)), isError(503));
  }
  await assert.rejects(unwrapProcessResponse(response({ detail: { message: '점검 중' } }, 503)), isError(503));
  await assert.rejects(unwrapProcessResponse(new Response('not-json', { status: 503 })), isError(503));
  assert.deepEqual(await unwrapProcessResponse(succeeds([])), []);
});

for (const field of ['tenantId', 'scopeNodeId', 'entityMode', 'user', 'token']) {
  test(`어댑터: ${field} 변경 시 전송 전 identity 차단`, async () => {
    identity = copy(identityBase);
    let sent = 0;
    transport = async () => { sent++; return succeeds([pack]); };
    const api = createProcessInstallationApi();
    identity[field] = `changed-${field}`;
    await assert.rejects(api.catalog(boundary), isError(409, 'CLIENT_CONTEXT_CHANGED'));
    assert.equal(sent, 0);
  });
}

test('어댑터: fetch 대기 중 바뀐 identity의 응답 폐기', async () => {
  identity = copy(identityBase);
  const pending = deferred(); transport = () => pending.promise;
  const api = createProcessInstallationApi(); const result = api.catalog(boundary);
  const rejected = assert.rejects(result, isError(409, 'CLIENT_CONTEXT_CHANGED'));
  identity.scopeNodeId = 'other-synthetic-scope'; pending.resolve(succeeds([pack]));
  await rejected;
});

test('어댑터: JSON 읽기 중 바뀐 identity도 응답 폐기', async () => {
  identity = copy(identityBase);
  const pending = deferred(); const entered = deferred();
  transport = async () => ({ ok: true, status: 200, json: () => { entered.resolve(); return pending.promise; } });
  const result = createProcessInstallationApi().catalog(boundary);
  const rejected = assert.rejects(result, isError(409, 'CLIENT_CONTEXT_CHANGED'));
  await entered.promise; identity.user = 'other-synthetic-user';
  pending.resolve({ status: 'success', data: [pack] }); await rejected;
});

test('어댑터: 시작 직렬화는 원본 입력과 digest/key만 / 조회는 GET', async () => {
  identity = copy(identityBase);
  const calls = [];
  transport = async (url, init) => { calls.push({ url, init }); return succeeds(operation); };
  const api = createProcessInstallationApi(); const original = copy(input);
  await api.start(input, plan.plan_digest, 'synthetic-stable-request');
  const start = calls[0];
  assert.equal(start.init.method, 'POST');
  assert.deepEqual(JSON.parse(start.init.body), { ...input, plan_digest: plan.plan_digest,
    client_request_id: 'synthetic-stable-request' });
  assert.deepEqual(input, original);
  await api.access(true); await api.resolved(boundary); await api.catalog(boundary);
  await api.legacy(boundary); await api.list(boundary); await api.get('synthetic/id?#');
  assert.ok(calls.slice(1).every((call) => !call.init || (call.init.method || 'GET') === 'GET'));
  assert.ok(calls.at(-1).url.endsWith('/synthetic%2Fid%3F%23'));
  assert.ok(calls.every((call) => !call.url.includes(identity.token) && !call.url.includes(identity.user)));
});

test('제품 패널: 실제 React SSR 기본 안내 / 렌더 중 API 호출 없음', () => {
  const { ProcessInstallationPanel } = loadTs('../src/components/ProcessInstallationPanel.tsx', {
    '../lib/processInstallationApi': apiModule, '../lib/processInstallationFlow': flowModule,
    './process-installation.css': {},
  });
  const h = harness();
  const html = renderToStaticMarkup(React.createElement(ProcessInstallationPanel, {
    companyName: '합성 회사', scopeLabel: '합성 구매팀', apiFactory: () => h.api,
  }));
  assert.ok(html.includes('합성 구매팀'));
  assert.ok(html.includes('우리 업무 구성'));
  assert.ok(html.includes('회사·조직과 업무 구성을 확인합니다.'));
  assert.ok(!html.includes('현재 조회 가능한 표준 업무가 없습니다.'));
  assert.equal(h.calls.length, 0);
});

test('제품 패널: 실제 컨트롤러의 준비된 상태를 SSR에 연결해 단계·안전 문구 확인', async () => {
  const h = harness(); await prepare(h); await h.flow.register();
  // SSR은 effect를 실행하지 않는다. 조회·준비를 마친 실제 컨트롤러를 생성 경계에 주입한다.
  const { ProcessInstallationPanel, ProcessTree } = loadTs('../src/components/ProcessInstallationPanel.tsx', {
    '../lib/processInstallationApi': apiModule,
    '../lib/processInstallationFlow': { ...flowModule, createInstallationFlow: () => h.flow },
    './process-installation.css': {},
  });
  const before = h.calls.length;
  const html = renderToStaticMarkup(React.createElement(ProcessInstallationPanel, {
    companyName: '합성 회사', scopeLabel: '합성 구매팀', apiFactory: () => h.api,
  }));
  for (const label of ['합성 회사', '1. 필요한 표준 업무 선택', '2. 설치 계획 확인',
    '3. 설치 요청 및 진행 확인', '이 판본을 설치 후보로 등록', '등록 확인됨',
    '설치할 업무 미리보기', '검토한 계획으로 설치 요청', '설치 상태 새로고침',
    'DOMAIN_REVIEW_REQUIRED', 'NO_DATA', '데이터 미연결', '앱 사용 준비 미완료']) {
    assert.ok(html.includes(label), label);
  }
  assert.ok(!html.includes('BK-01'));
  assert.ok(!html.includes('BK-02'));
  assert.ok(html.includes('표준 업무키트 추가 설치 · 설치 요청 관리'));
  assert.ok(!/<details\b[^>]*class="process-install-more"[^>]*\bopen(?:=|\s|>)/.test(html));
  const tree = renderToStaticMarkup(React.createElement(ProcessTree, { document, title: '합성 L1/L2 미리보기' }));
  for (const label of ['합성 L1/L2 미리보기', '원료 구매', '구매 계획', '상위 업무 선택']) assert.ok(tree.includes(label));
  assert.equal(h.calls.length, before);
});

// 후속 쓰기 경계는 실제 컨트롤러로 검사한다. 아래 저장 상태와 API 응답만 메모리 대역이다.
function followup(overrides = {}) {
  const live = {
    principal: 'synthetic-reviewer',
    operation: { ...copy(operation), stage: 'AWAITING_INSTALLER', installer: 'synthetic-reviewer',
      change_id: '', revision: 4, permitted_actions: ['resume'] },
    review: { change_id: 'synthetic-review-change', configuration_id: resolved.configuration_id,
      base_head_version: 7, draft_profile_id: 'synthetic-review-profile', draft_digest: 'f'.repeat(64),
      actor: 'synthetic-author', reason: '합성 변경 목적', status: 'DRAFT', boundary: copy(boundary),
      current_head_version: 7, principal_user_id: 'synthetic-reviewer', permitted_actions: ['read', 'approve'],
      review_blockers: [], operation_id: operation.operation_id, payload: copy(document), base_payload: null },
    resolved: copy(resolved),
  };
  const completeResume = () => {
    Object.assign(live.operation, { stage: 'AWAITING_APPROVAL', revision: live.operation.revision + 1,
      change_id: live.review.change_id, permitted_actions: [] });
    return copy(live.operation);
  };
  const completeApproval = (_boundary, changeId, body) => {
    assert.equal(changeId, live.review.change_id);
    assert.equal(body.expected_head_version, live.review.base_head_version);
    assert.equal(body.draft_digest, live.review.draft_digest);
    live.review.status = 'APPLIED'; live.review.permitted_actions = ['read'];
    live.review.current_head_version = body.expected_head_version + 1;
    Object.assign(live.operation, { stage: 'APPLIED', change_id: changeId,
      applied_profile_id: live.review.draft_profile_id, permitted_actions: [] });
    Object.assign(live.resolved, { head_version: body.expected_head_version + 1,
      profile_id: live.review.draft_profile_id, digest: body.draft_digest, payload: copy(live.review.payload) });
    return { change_id: changeId, configuration_id: live.review.configuration_id, status: 'APPLIED',
      profile_id: live.review.draft_profile_id, head_version: live.resolved.head_version,
      digest: body.draft_digest, event_id: 'synthetic-approval-event', audit_delivery: 'PENDING' };
  };
  const h = harness({ access: () => ({ boundary: copy(boundary), principal_user_id: live.principal,
    permitted_actions: ['propose', 'edit', 'approve'], context_root_label: '합성 회사' }),
    list: () => ({ items: [live.operation], next_offset: null }), get: () => live.operation,
    resolved: () => live.resolved,
    changes: () => ({ items: live.review.status === 'DRAFT' ? [live.review] : [], next_offset: null }),
    change: (_boundary, id) => ({ ...live.review, change_id: id }),
    resume: completeResume, approve: completeApproval, ...overrides });
  return { ...h, live, completeResume, completeApproval };
}
async function openedOperation(h) {
  await h.flow.load(); await h.flow.refresh(h.live.operation.operation_id);
  assert.equal(h.flow.getSnapshot().error, null);
}
async function openedReview(h) {
  Object.assign(h.live.operation, { stage: 'AWAITING_APPROVAL', change_id: h.live.review.change_id, permitted_actions: [] });
  await h.flow.load(); await h.flow.reviewChange(h.live.review.change_id);
  h.flow.setApprovalReason('  합성 별도 승인 이유  ');
  assert.equal(h.flow.getSnapshot().error, null);
}
const writeCalls = (h) => h.calls.filter((call) => ['resume', 'approve'].includes(call.name));
function renderReview(h) {
  const { ProcessReviewPanel } = loadTs('../src/components/ProcessInstallationPanel.tsx', {
    '../lib/processInstallationApi': apiModule, '../lib/processInstallationFlow': flowModule,
    './process-installation.css': {},
  });
  return renderToStaticMarkup(React.createElement(ProcessReviewPanel, {
    flow: h.flow, state: h.flow.getSnapshot(), review: h.flow.getSnapshot().review,
  }));
}

test('후속: 재개 직전 access GET / 검토 revision 고정 / 중복 클릭 차단', async () => {
  const pending = deferred(); const entered = deferred();
  const h = followup({ resume: () => { entered.resolve(); return pending.promise; } });
  await openedOperation(h); const count = h.calls.length;
  const running = h.flow.resume(false); await entered.promise; await h.flow.resume(false);
  assert.deepEqual(h.calls.slice(count).map((call) => call.name), ['access', 'resume']);
  assert.deepEqual(writeCalls(h)[0].args, [operation.operation_id, 4, false]);
  assert.equal(writeCalls(h).length, 1);
  pending.resolve(h.completeResume()); await running;
  assert.equal(h.flow.getSnapshot().operation.stage, 'AWAITING_APPROVAL');
  assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, false);
});

test('후속: 인수 action은 adopt=true만 명시 전송 / 기본 재개는 차단', async () => {
  const h = followup(); h.live.operation.installer = 'synthetic-other-installer';
  h.live.operation.permitted_actions = ['adopt']; await openedOperation(h);
  await h.flow.resume(false); assert.equal(writeCalls(h).length, 0);
  assert.equal(h.flow.getSnapshot().error.status, 403);
  await h.flow.load(); await h.flow.refresh(operation.operation_id); await h.flow.resume(true);
  assert.deepEqual(writeCalls(h)[0].args, [operation.operation_id, 4, true]);
});

test('후속: 변경 목록·더 보기·상세는 GET만 / 페이지 중복 제거', async () => {
  const h = followup({ changes: (_boundary, offset = 0) => ({ items: offset
    ? [{ ...h.live.review }, { ...h.live.review, change_id: 'synthetic-second-change' }]
    : [h.live.review], next_offset: offset ? null : 20 }) });
  await h.flow.load(); await h.flow.loadChanges(); await h.flow.moreChanges();
  await h.flow.reviewChange(h.live.review.change_id);
  assert.equal(h.flow.getSnapshot().changesLoaded, true);
  assert.deepEqual(h.flow.getSnapshot().changes.map((change) => change.change_id), [h.live.review.change_id, 'synthetic-second-change']);
  assert.equal(h.flow.getSnapshot().nextChangeOffset, null); assert.equal(writeCalls(h).length, 0);
  assert.ok(h.calls.some((call) => call.name === 'changes' && call.args[1] === 20));
});

test('후속: 자기가 작성한 변경안은 approve 권한 표시가 있어도 POST 차단', async () => {
  const h = followup(); h.live.review.actor = h.live.principal;
  await openedReview(h);
  const html = renderReview(h);
  assert.ok(html.includes('내가 작성한 변경안입니다.'));
  assert.ok(!html.includes('>검토한 변경안 승인</button>'));
  await h.flow.approveChange(); assert.equal(writeCalls(h).length, 0);
  assert.equal(h.flow.getSnapshot().error.status, 403);
});

test('후속: 승인 이유 필수 / 검토 digest·base와 명시 reason만 POST', async () => {
  const h = followup(); await openedReview(h); h.flow.setApprovalReason('  ');
  await h.flow.approveChange(); assert.equal(writeCalls(h).length, 0);
  assert.equal(h.flow.getSnapshot().error.status, 422);
  h.flow.setApprovalReason('  합성 별도 승인 이유  ');
  const before = copy(h.flow.getSnapshot().review); const count = h.calls.length;
  await h.flow.approveChange();
  assert.deepEqual(h.calls.slice(count, count + 2).map((call) => call.name), ['access', 'approve']);
  assert.deepEqual(writeCalls(h)[0].args, [boundary, before.change_id, {
    expected_head_version: before.base_head_version, draft_digest: before.draft_digest, reason: '합성 별도 승인 이유',
  }]);
  assert.equal(h.flow.getSnapshot().applicationVerified, true);
  assert.equal(h.flow.getSnapshot().operation.data_ready, false);
  assert.equal(h.flow.getSnapshot().operation.apps_ready, false);
});

test('후속: 승인 직전 최신 access와 검토자 불일치면 POST 없음', async () => {
  const h = followup(); await openedReview(h); h.live.principal = 'synthetic-different-reviewer';
  await h.flow.approveChange(); assert.equal(writeCalls(h).length, 0);
  assert.equal(h.flow.getSnapshot().error.status, 409);
});

test('후속: 변경안 A/B 왕복은 각 승인 이유를 따로 보존 / 자동 POST 없음', async () => {
  const h = followup(); await openedReview(h); const first = h.live.review.change_id;
  await h.flow.reviewChange('synthetic-second-change');
  assert.equal(h.flow.getSnapshot().approvalReason, '');
  h.flow.setApprovalReason('두 번째 변경안의 합성 이유');
  await h.flow.reviewChange(first);
  assert.equal(h.flow.getSnapshot().approvalReason, '  합성 별도 승인 이유  ');
  await h.flow.reviewChange('synthetic-second-change');
  assert.equal(h.flow.getSnapshot().approvalReason, '두 번째 변경안의 합성 이유');
  assert.equal(writeCalls(h).length, 0);
});

test('후속: 잘못된 범위의 상세 응답은 검토 대상으로 노출하지 않음', async () => {
  const h = followup({ change: () => ({ ...h.live.review,
    boundary: { ...boundary, context_root_id: 'SYNTHETIC-WRONG-ROOT' } }) });
  await h.flow.load(); await h.flow.reviewChange(h.live.review.change_id);
  assert.equal(h.flow.getSnapshot().error.status, 503);
  assert.equal(h.flow.getSnapshot().review, null); assert.equal(writeCalls(h).length, 0);
});

test('후속: 새 상세 조회 대기·실패 중 이전 승인 대상 숨김 / 이유는 복귀 시 복원', async () => {
  const pending = deferred(); const entered = deferred();
  const h = followup({ change: (_boundary, id) => {
    if (id === 'synthetic-unavailable-change') { entered.resolve(); return pending.promise; }
    return { ...h.live.review, change_id: id };
  } });
  await openedReview(h);
  const reading = h.flow.reviewChange('synthetic-unavailable-change');
  await entered.promise; assert.equal(h.flow.getSnapshot().review, null);
  await h.flow.approveChange(); assert.equal(writeCalls(h).length, 0);
  pending.reject(new ProcessApiError(503, '합성 상세 조회 장애')); await reading;
  assert.equal(h.flow.getSnapshot().error.status, 503); assert.equal(h.flow.getSnapshot().review, null);
  await h.flow.approveChange(); assert.equal(writeCalls(h).length, 0);
  await h.flow.reviewChange(h.live.review.change_id);
  assert.equal(h.flow.getSnapshot().approvalReason, '  합성 별도 승인 이유  ');
});

test('후속: 승인 영수증의 profile 불일치도 재POST 없이 GET으로 확인', async () => {
  const h = followup({ approve: (...args) => ({ ...h.completeApproval(...args), profile_id: 'synthetic-wrong-receipt' }) });
  await openedReview(h); await h.flow.approveChange();
  assert.equal(h.flow.getSnapshot().error.status, 503);
  assert.equal(h.flow.getSnapshot().approvalReceipt, null);
  assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, true);
  await h.flow.approveChange(); assert.equal(writeCalls(h).length, 1);
  await h.flow.refreshReview();
  assert.equal(h.flow.getSnapshot().applicationVerified, true); assert.equal(writeCalls(h).length, 1);
});

test('후속: 서버 초안이 바뀌어도 검토한 digest/base를 몰래 갱신하지 않음', async () => {
  const h = followup({ approve: () => { throw new ProcessApiError(409, '합성 초안 변경', 'PROCESS_DIGEST_CONFLICT'); } });
  await openedReview(h); const reviewed = copy(h.flow.getSnapshot().review);
  h.live.review.draft_digest = '9'.repeat(64); h.live.review.base_head_version = 9;
  await h.flow.approveChange();
  assert.equal(writeCalls(h)[0].args[2].draft_digest, reviewed.draft_digest);
  assert.equal(writeCalls(h)[0].args[2].expected_head_version, reviewed.base_head_version);
  assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, true);
});

for (const action of ['resume', 'approve']) {
  test(`후속: ${action} POST 성공 뒤 GET 실패는 재POST 차단 / GET 복구`, async () => {
    let committed = false; let readFails = true;
    const h = followup({
      resume: (...args) => { committed = true; return h.completeResume(...args); },
      approve: (...args) => { committed = true; return h.completeApproval(...args); },
      get: () => { if (committed && readFails) throw new ProcessApiError(503, '합성 후속 조회 장애'); return h.live.operation; },
    });
    if (action === 'resume') await openedOperation(h); else await openedReview(h);
    const submit = () => action === 'resume' ? h.flow.resume(false) : h.flow.approveChange();
    await submit(); assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, true);
    assert.equal(h.flow.getSnapshot().applicationVerified, false);
    if (action === 'approve') assert.equal(h.flow.getSnapshot().approvalReceipt.status, 'APPLIED');
    await submit(); assert.equal(writeCalls(h).length, 1);
    const count = h.calls.length; await h.flow.refreshReview();
    assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, true);
    readFails = false; await h.flow.refreshReview();
    assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, false);
    assert.equal(writeCalls(h).length, 1);
    assert.ok(h.calls.slice(count).every((call) => !['resume', 'approve'].includes(call.name)));
    if (action === 'approve') assert.equal(h.flow.getSnapshot().applicationVerified, true);
  });
}

for (const action of ['resume', 'approve']) {
  test(`후속: ${action} 409 뒤 GET 재확인 전 차단 / 명시 재시도만 허용`, async () => {
    let conflict = true;
    const h = followup({
      resume: (...args) => { if (conflict) throw new ProcessApiError(409, '합성 경합'); return h.completeResume(...args); },
      approve: (...args) => { if (conflict) throw new ProcessApiError(409, '합성 경합'); return h.completeApproval(...args); },
    });
    if (action === 'resume') await openedOperation(h); else await openedReview(h);
    const submit = () => action === 'resume' ? h.flow.resume(false) : h.flow.approveChange();
    await submit(); const reason = h.flow.getSnapshot().approvalReason;
    assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, true);
    await submit(); assert.equal(writeCalls(h).length, 1);
    await h.flow.refreshReview();
    assert.equal(writeCalls(h).length, 1); assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, false);
    assert.equal(h.flow.getSnapshot().approvalReason, reason);
    conflict = false; await submit(); assert.equal(writeCalls(h).length, 2);
  });
}

test('후속: 응답 유실·다른 상세·일반 새로고침은 미확정 승인 잠금을 지우지 않음', async () => {
  const h = followup({ approve: (...args) => {
    h.completeApproval(...args); throw new ProcessApiError(503, '합성 승인 응답 유실');
  } });
  await openedReview(h); await h.flow.approveChange();
  assert.equal(h.flow.getSnapshot().approvalReceipt, null);
  await h.flow.reviewChange('synthetic-other-change'); await h.flow.loadChanges(); await h.flow.refresh();
  assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, true);
  await h.flow.approveChange(); assert.equal(writeCalls(h).length, 1);
  await h.flow.refreshReview();
  assert.equal(h.flow.getSnapshot().review.change_id, h.live.review.change_id);
  assert.equal(h.flow.getSnapshot().applicationVerified, true); assert.equal(writeCalls(h).length, 1);
});

for (const action of ['resume', 'approve']) {
  test(`후속: ${action} 대기 중 unmount·늦은 응답은 화면 갱신·후속 GET 폐기`, async () => {
    const pending = deferred(); const entered = deferred();
    const h = followup({ [action]: () => { entered.resolve(); return pending.promise; } });
    if (action === 'resume') await openedOperation(h); else await openedReview(h);
    const running = action === 'resume' ? h.flow.resume(false) : h.flow.approveChange();
    await entered.promise; h.flow.invalidate(); const frozen = h.flow.getSnapshot(); const count = h.calls.length;
    pending.resolve(action === 'resume' ? h.completeResume() : h.completeApproval(boundary, h.live.review.change_id,
      { expected_head_version: 7, draft_digest: h.live.review.draft_digest, reason: '합성 별도 승인 이유' }));
    await running; assert.equal(h.flow.getSnapshot(), frozen); assert.equal(h.calls.length, count);
    await h.flow.load(); assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, true);
    await h.flow.refreshReview(); assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, false);
    assert.equal(writeCalls(h).length, 1);
  });
}

test('후속: 미확정 재개는 경계 A→B→A에서 잠금 복원 / GET 전 POST 금지', async () => {
  let current = boundary;
  const h = followup({ access: () => ({ boundary: current, principal_user_id: 'synthetic-reviewer', permitted_actions: ['edit', 'approve'] }),
    resume: () => { throw new ProcessApiError(503, '합성 재개 응답 유실'); } });
  await openedOperation(h); await h.flow.resume(false);
  current = { ...boundary, context_root_id: 'SYNTHETIC-OTHER-ROOT' };
  await h.flow.refreshReview(); await h.flow.confirmBoundary();
  assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, false);
  current = boundary; await h.flow.refreshReview(); await h.flow.confirmBoundary();
  assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, true);
  await h.flow.refresh(operation.operation_id); await h.flow.resume(false);
  assert.equal(writeCalls(h).length, 1);
  await h.flow.refreshReview(); assert.equal(h.flow.getSnapshot().mutationNeedsRefresh, false);
});

test('후속: 적용 GET의 지문·설치 연결 불일치는 완료로 표시하지 않음', async () => {
  const h = followup(); await openedReview(h); await h.flow.approveChange();
  h.live.resolved.digest = '0'.repeat(64); await h.flow.refreshReview();
  assert.equal(h.flow.getSnapshot().applicationVerified, false);
  h.live.resolved.digest = h.live.review.draft_digest; h.live.operation.applied_profile_id = 'synthetic-wrong-profile';
  await h.flow.refreshReview(); assert.equal(h.flow.getSnapshot().applicationVerified, false);
  h.live.operation.applied_profile_id = h.live.review.draft_profile_id;
  h.live.resolved.configuration_id = 'synthetic-wrong-configuration';
  await h.flow.refreshReview(); assert.equal(h.flow.getSnapshot().applicationVerified, false);
  h.live.resolved.configuration_id = h.live.review.configuration_id; h.live.resolved.head_version = h.live.review.base_head_version;
  await h.flow.refreshReview(); assert.equal(h.flow.getSnapshot().applicationVerified, false);
  h.live.resolved.head_version = h.live.review.base_head_version + 1;
  h.live.operation.change_id = 'synthetic-wrong-change';
  await h.flow.refreshReview(); assert.equal(h.flow.getSnapshot().applicationVerified, false);
  h.live.operation.change_id = h.live.review.change_id;
  await h.flow.refreshReview(); assert.equal(h.flow.getSnapshot().applicationVerified, true);
});

test('후속: 후속 승인판이 있어도 과거 적용 기록은 별도 문구로 확인', async () => {
  const h = followup(); await openedReview(h); await h.flow.approveChange();
  Object.assign(h.live.resolved, { head_version: 10, profile_id: 'synthetic-newer-profile', digest: '1'.repeat(64) });
  await h.flow.refreshReview(); assert.equal(h.flow.getSnapshot().applicationVerified, true);
  const html = renderReview(h);
  assert.ok(html.includes('이 변경 이후 다른 승인판이 적용되었습니다.'));
  assert.ok(html.includes('데이터 연결·인증과 앱 사용 준비는 별도입니다.'));
});

test('후속 SSR: 인수·승인 확인 체크 전 버튼 잠금 / 원문·기준판 표시', async () => {
  const h = followup(); h.live.operation.permitted_actions = ['adopt']; await openedOperation(h);
  const { ProcessInstallationPanel } = loadTs('../src/components/ProcessInstallationPanel.tsx', {
    '../lib/processInstallationApi': apiModule,
    '../lib/processInstallationFlow': { ...flowModule, createInstallationFlow: () => h.flow },
    './process-installation.css': {},
  });
  const panel = renderToStaticMarkup(React.createElement(ProcessInstallationPanel, { companyName: '합성 회사', scopeLabel: '합성 범위', apiFactory: () => h.api }));
  assert.ok(panel.includes('이 요청의 설치 담당자로 인수하겠습니다.'));
  assert.match(panel.match(/<button\b[^>]*>담당자로 인수하고 진행<\/button>/)?.[0] || '', /disabled/);
  await openedReview(h); const html = renderReview(h);
  for (const label of ['검토할 변경안', '검토 기준판', '변경 후 · 검토 대상', '위 변경 전후와 적용 범위를 확인했습니다.', h.live.review.draft_digest]) assert.ok(html.includes(label));
  assert.match(html.match(/<button\b[^>]*>검토한 변경안 승인<\/button>/)?.[0] || '', /disabled/);
  assert.equal(writeCalls(h).length, 0);
});

test('후속 어댑터: 재개·승인 정확 본문 / 검토 GET 경계와 ID 인코딩', async () => {
  identity = copy(identityBase); const calls = [];
  transport = async (url, init) => { calls.push({ url, init }); return succeeds(operation); };
  const api = createProcessInstallationApi(); const body = { expected_head_version: 7, draft_digest: 'f'.repeat(64), reason: '합성 승인 이유' };
  await api.resume('synthetic/op?', 4, true); await api.approve(boundary, 'synthetic/change?', body);
  assert.deepEqual(JSON.parse(calls[0].init.body), { expected_revision: 4, adopt: true });
  assert.ok(calls[0].url.endsWith('/synthetic%2Fop%3F/resume'));
  assert.deepEqual(JSON.parse(calls[1].init.body), body);
  assert.ok(calls[1].url.endsWith('/synthetic%2Fchange%3F/approve'));
  assert.ok(!calls[1].url.includes('context_root_id'));
  await api.changes(boundary, 20); await api.change(boundary, 'synthetic/change?');
  for (const call of calls.slice(2)) {
    assert.equal(call.init, undefined); assert.ok(call.url.includes('context_root_id=SYNTHETIC-ROOT'));
  }
  assert.ok(calls[2].url.includes('status=DRAFT')); assert.ok(calls[2].url.includes('offset=20'));
});

function editBase() {
  const base = copy(resolved);
  base.payload.nodes.push(
    { process_id: 'edit-root-2', level: 'L1', parent_process_id: '', label: '두 번째 상위 업무', note: '', enabled: true },
    { process_id: 'edit-hidden', level: 'L2', parent_process_id: 'synthetic-l1', label: '숨긴 미사용 업무', note: '', enabled: false },
    { process_id: 'edit-other-child', level: 'L2', parent_process_id: 'edit-root-2', label: '다른 상위의 업무', note: '서버 설명', enabled: true },
  );
  base.payload.placements.push(
    { placement_id: 'edit-root-placement', process_id: 'edit-root-2', parent_process_id: '', position: 1, hidden: false, kind: 'CANONICAL' },
    { placement_id: 'edit-hidden-placement', process_id: 'edit-hidden', parent_process_id: 'synthetic-l1', position: 1, hidden: true, kind: 'CANONICAL' },
    { placement_id: 'edit-other-placement', process_id: 'edit-other-child', parent_process_id: 'edit-root-2', position: 0, hidden: false, kind: 'CANONICAL' },
    { placement_id: 'edit-shortcut', process_id: 'edit-other-child', parent_process_id: 'synthetic-l1', position: 2, hidden: false, kind: 'SHORTCUT' },
  );
  return base;
}
function editHarness(overrides = {}) {
  const live = { base: editBase(), access: { boundary: copy(boundary), principal_user_id: 'synthetic-editor',
    permitted_actions: ['read', 'propose'], context_root_label: '합성 회사' } };
  let keys = 0;
  const completePropose = (_boundary, body) => ({ change_id: 'synthetic-edit-change',
    configuration_id: live.base.configuration_id, base_head_version: body.expected_head_version,
    draft_profile_id: 'synthetic-edit-draft', draft_digest: '7'.repeat(64), actor: live.access.principal_user_id,
    reason: body.reason, status: 'DRAFT' });
  const h = harness({ access: () => live.access, resolved: () => live.base, propose: completePropose, ...overrides });
  const edit = createProcessEditFlow(h.api, false, () => `synthetic-edit-request-${++keys}`);
  edit.begin(live.base, live.access);
  return { ...h, edit, live, completePropose, keys: () => keys };
}
function editChanges(h) {
  h.edit.select('synthetic-l1'); h.edit.setLabel('원료 구매 관리'); h.edit.setNote('  합성 현업 설명  ');
  h.edit.move('edit-hidden-placement', -1); h.edit.setReason('  합성 편집 이유  ');
}
const proposals = (h) => h.calls.filter((call) => call.name === 'propose');

test('편집: 실제 명령 생성·미리보기는 원본·업무 ID·고정 참조를 변경하지 않음', () => {
  const h = editHarness(); const original = copy(h.live.base); editChanges(h);
  const preview = h.edit.getSnapshot().document;
  assert.deepEqual(h.live.base, original); assert.deepEqual(h.edit.getSnapshot().base, original);
  assert.deepEqual(preview.nodes.map((node) => node.process_id), original.payload.nodes.map((node) => node.process_id));
  assert.deepEqual(preview.template_sources, original.payload.template_sources);
  assert.deepEqual(buildProcessEditCommands(original.payload, preview), [
    { op: 'RENAME', process_id: 'synthetic-l1', label: '원료 구매 관리' },
    { op: 'SET_NOTE', process_id: 'synthetic-l1', note: '  합성 현업 설명  ' },
    { op: 'REORDER_PLACEMENTS', parent_process_id: 'synthetic-l1',
      placement_ids: ['edit-hidden-placement', 'placement-l2', 'edit-shortcut'] },
  ]);
  assert.deepEqual(buildProcessEditCommands(original.payload, original.payload), []);
  assert.equal(h.calls.length, 0);
});

test('편집: 형제순서는 숨김·미사용·바로가기 포함 / 경계 이동은 다른 부모에 영향 없음', () => {
  const h = editHarness(); const before = copy(h.edit.getSnapshot().document);
  h.edit.move('placement-l2', -1); h.edit.move('edit-shortcut', 1);
  assert.deepEqual(h.edit.getSnapshot().document, before);
  h.edit.move('edit-shortcut', -1);
  const after = h.edit.getSnapshot().document;
  assert.deepEqual(orderedPlacements(after, 'synthetic-l1').map((placement) => placement.placement_id),
    ['placement-l2', 'edit-shortcut', 'edit-hidden-placement']);
  const withoutPosition = (items) => items.map(({ position: _position, ...rest }) => rest);
  assert.deepEqual(withoutPosition(after.placements), withoutPosition(before.placements));
  assert.deepEqual(orderedPlacements(after, ''), orderedPlacements(before, ''));
  assert.deepEqual(orderedPlacements(after, 'edit-root-2'), orderedPlacements(before, 'edit-root-2'));
});

test('편집: begin 반복은 편집 중 원본을 대체하지 않음 / 별도 모델과 상태 공유 없음', () => {
  const h = editHarness(); editChanges(h); const before = copy(h.edit.getSnapshot().document);
  const latest = copy(h.live.base); latest.head_version++; latest.payload.nodes[0].label = '다른 서버 이름';
  h.edit.begin(latest, h.live.access);
  assert.equal(h.edit.getSnapshot().base.head_version, 7); assert.deepEqual(h.edit.getSnapshot().document, before);
  const other = createProcessEditFlow(h.api, true, () => 'other-synthetic-key');
  const otherBoundary = { ...boundary, scope_node_id: '' };
  other.begin({ ...latest, boundary: otherBoundary }, { ...h.live.access, boundary: otherBoundary });
  other.setLabel('다른 범위 편집');
  assert.deepEqual(h.edit.getSnapshot().document, before);
});

test('편집: pristine만 새 승인판·범위 이동 / 이유·명령·미확정·접수 입력은 보존', async () => {
  const h = editHarness();
  const latest = copy(h.live.base); latest.head_version++; latest.profile_id = 'synthetic-new-profile';
  latest.digest = '9'.repeat(64); latest.payload.nodes[0].label = '새 승인판 업무';
  h.edit.begin(latest, h.live.access);
  assert.deepEqual(h.edit.getSnapshot().base, latest);
  assert.deepEqual(h.edit.getSnapshot().document, latest.payload);
  const moved = { ...latest, boundary: { ...boundary, scope_node_id: 'synthetic-new-scope' } };
  h.edit.begin(moved, { ...h.live.access, boundary: moved.boundary });
  assert.deepEqual(h.edit.getSnapshot().base, moved);
  for (const dirty of ['reason', 'commands', 'attempt', 'receipt']) {
    const item = editHarness(dirty === 'attempt' ? { propose: () => { throw new ProcessApiError(503, '합성 유실'); } } : {});
    if (dirty === 'reason') item.edit.setReason('보존할 이유');
    else if (dirty === 'commands') item.edit.setLabel('보존할 이름');
    else { editChanges(item); await item.edit.submit(); }
    const before = copy(item.edit.getSnapshot());
    item.edit.begin(latest, item.live.access);
    item.edit.begin(moved, { ...item.live.access, boundary: moved.boundary });
    for (const key of ['base', 'document', 'reason', 'attempt', 'receipt']) {
      assert.deepEqual(item.edit.getSnapshot()[key], before[key], `${dirty}:${key}`);
    }
  }
});

test('편집 권한 401/403/404: 부모 suspendAccess는 표시·늦은 조회 폐기 / 원입력 보존', async () => {
  for (const status of [401, 403, 404]) {
    let denied = false, paused = false;
    const entered = deferred(), pending = deferred();
    const h = editHarness({ access: () => {
      if (denied) throw new ProcessApiError(status, '합성 편집 접근 회수');
      return h.live.access;
    }, resolved: () => {
      if (paused) { entered.resolve(); return pending.promise; }
      return h.live.base;
    } });
    await prepare(h); await h.flow.start(); editChanges(h);
    const before = copy(h.flow.getSnapshot()), edited = copy(h.edit.getSnapshot());
    paused = true; const oldRead = h.flow.load(); await entered.promise;
    denied = true; await h.edit.submit();
    assert.equal(h.edit.getSnapshot().error.status, status); assert.equal(proposals(h).length, 0);
    // React effect 자체는 실행하지 않는다. 실제 편집 오류를 부모가 호출하는 동일 컨트롤러 경계에 전달한다.
    h.flow.suspendAccess(h.edit.getSnapshot().error);
    const hidden = h.flow.getSnapshot();
    assert.equal(hidden.loaded, false); assert.equal(hidden.busy, ''); assert.equal(hidden.error.status, status);
    for (const key of ['access', 'resolved', 'operation', 'review', 'approvalReceipt']) assert.equal(hidden[key], null);
    for (const key of ['packs', 'legacy', 'operations', 'changes']) assert.deepEqual(hidden[key], []);
    assert.equal(hidden.changesLoaded, false); assert.equal(hidden.applicationVerified, false);
    for (const key of ['prepared', 'reason', 'selectedKits', 'selectedDigest']) assert.deepEqual(hidden[key], before[key]);
    for (const key of ['base', 'document', 'reason', 'attempt']) assert.deepEqual(h.edit.getSnapshot()[key], edited[key]);
    pending.resolve(h.live.base); await oldRead;
    assert.equal(h.flow.getSnapshot(), hidden);
    denied = false; paused = false; await h.flow.load(); h.edit.begin(h.live.base, h.live.access);
    assert.equal(h.flow.getSnapshot().loaded, true); assert.deepEqual(h.flow.getSnapshot().prepared, before.prepared);
    assert.deepEqual(h.edit.getSnapshot().document, edited.document);
    assert.equal(h.calls.filter((call) => call.name === 'start').length, 1); assert.equal(proposals(h).length, 0);
  }
});

test('편집: 승인 기준판 없음·범위 불일치는 시작 차단', () => {
  const h = editHarness();
  const empty = createProcessEditFlow(h.api, false);
  empty.begin({ ...h.live.base, payload: null, profile_id: '', head_version: 0 }, h.live.access);
  assert.equal(empty.getSnapshot().document, null); assert.equal(empty.getSnapshot().error.status, 409);
  const other = createProcessEditFlow(h.api, false);
  other.begin(h.live.base, { ...h.live.access, boundary: { ...boundary, scope_node_id: 'other-scope' } });
  assert.equal(other.getSnapshot().document, null);
});

test('편집: 변경 없음·이유 누락·빈 이름·이름 길이 초과는 POST 없음', async () => {
  for (const invalid of ['unchanged', 'reason', 'blank-label', 'long-label']) {
    const h = editHarness(); editChanges(h);
    if (invalid === 'unchanged') { h.edit.reset(); h.edit.begin(h.live.base, h.live.access); h.edit.setReason('합성 이유'); }
    if (invalid === 'reason') h.edit.setReason('  ');
    if (invalid === 'blank-label') h.edit.setLabel('  ');
    if (invalid === 'long-label') h.edit.setLabel('가'.repeat(201));
    assert.equal(await h.edit.submit(), null); assert.equal(proposals(h).length, 0);
    assert.equal(h.edit.getSnapshot().error.status, 422); assert.equal(h.keys(), 0);
  }
});

test('편집: 설명 비우기는 SET_NOTE 빈 문자열 / 불필요 RENAME 없음', () => {
  const h = editHarness(); h.edit.select('edit-other-child'); h.edit.setNote('');
  assert.deepEqual(buildProcessEditCommands(h.live.base.payload, h.edit.getSnapshot().document),
    [{ op: 'SET_NOTE', process_id: 'edit-other-child', note: '' }]);
});

test('편집: 제출 직전 access GET / 고정 base·명령·이유·키 / 중복 POST 차단', async () => {
  const pending = deferred(); const entered = deferred();
  const h = editHarness({ propose: () => { entered.resolve(); return pending.promise; } }); editChanges(h);
  const expectedCommands = buildProcessEditCommands(h.live.base.payload, h.edit.getSnapshot().document);
  const running = h.edit.submit(); await entered.promise; assert.equal(await h.edit.submit(), null);
  assert.deepEqual(h.calls.map((call) => call.name), ['access', 'propose']);
  const body = h.edit.getSnapshot().attempt.body;
  assert.deepEqual(body, { context_root_id: boundary.context_root_id, scope_node_id: boundary.scope_node_id,
    commands: expectedCommands, expected_head_version: 7, base_profile_id: resolved.profile_id,
    base_fingerprint: resolved.digest, client_request_id: 'synthetic-edit-request-1', reason: '합성 편집 이유' });
  pending.resolve(h.completePropose(boundary, body)); const receipt = await running;
  assert.equal(receipt.change_id, 'synthetic-edit-change'); assert.equal(receipt.status, 'DRAFT');
  assert.deepEqual(await h.edit.submit(), receipt); assert.equal(proposals(h).length, 1);
});

for (const status of [503, 409]) {
  test(`편집: 미확정 ${status}는 frozen 본문·키 보존 / reset·reload 차단 / 명시 동일 키 재시도`, async () => {
    let lost = true;
    const h = editHarness({ propose: (...args) => {
      if (lost) throw new ProcessApiError(status, '합성 응답 미확정', 'SYNTHETIC_UNKNOWN');
      return h.completePropose(...args);
    } }); editChanges(h); await h.edit.submit();
    const before = copy(h.edit.getSnapshot()); assert.equal(before.conflict, false);
    h.edit.setLabel('덮어쓰기 시도'); h.edit.setNote('다른 설명'); h.edit.move('edit-shortcut', -1); h.edit.setReason('다른 이유');
    h.edit.reset(); await h.edit.reloadBase();
    assert.deepEqual(h.edit.getSnapshot().attempt, before.attempt);
    assert.deepEqual(h.edit.getSnapshot().document, before.document);
    assert.equal(h.calls.filter((call) => call.name === 'resolved').length, 0);
    lost = false; await h.edit.submit();
    assert.deepEqual(proposals(h)[0].args, proposals(h)[1].args); assert.equal(h.keys(), 1);
  });
}

for (const reasonCode of ['PROCESS_HEAD_CONFLICT', 'PROCESS_DIGEST_CONFLICT']) {
  test(`편집: 확정 ${reasonCode} 후 명시 최신판 재조회는 편집 보존 / 새 검토·새 키`, async () => {
    let rejected = true;
    const h = editHarness({ propose: (...args) => {
      if (rejected) throw new ProcessApiError(409, '합성 기준판 경합', reasonCode);
      return h.completePropose(...args);
    } }); editChanges(h); await h.edit.submit();
    const attempt = copy(h.edit.getSnapshot().attempt);
    const changed = copy(h.live.base); changed.head_version = 8; changed.profile_id = 'synthetic-new-base'; changed.digest = '8'.repeat(64);
    changed.payload.nodes.find((node) => node.process_id === 'edit-other-child').label = '새 서버의 다른 업무';
    h.live.base = changed;
    await h.edit.submit(); assert.equal(proposals(h).length, 1);
    await h.edit.reloadBase(); const state = h.edit.getSnapshot();
    assert.equal(state.conflict, false); assert.equal(state.attempt, null); assert.equal(h.keys(), 1);
    assert.equal(state.document.nodes[0].label, '원료 구매 관리'); assert.equal(state.document.nodes[0].note, '  합성 현업 설명  ');
    assert.equal(state.document.nodes.find((node) => node.process_id === 'edit-other-child').label, '새 서버의 다른 업무');
    assert.deepEqual(orderedPlacements(state.document, 'synthetic-l1').map((placement) => placement.placement_id),
      ['edit-hidden-placement', 'placement-l2', 'edit-shortcut']);
    assert.equal(proposals(h).length, 1);
    rejected = false; await h.edit.submit(); const next = proposals(h)[1].args[1];
    assert.equal(next.expected_head_version, 8); assert.equal(next.base_profile_id, 'synthetic-new-base');
    assert.equal(next.base_fingerprint, changed.digest); assert.notEqual(next.client_request_id, attempt.body.client_request_id);
    assert.equal(next.reason, attempt.body.reason);
  });
}

test('편집: 새 기준판의 형제 ID가 달라지면 부분 덮어쓰기 없이 기존 입력 보존', async () => {
  const h = editHarness({ propose: () => { throw new ProcessApiError(409, '합성 경합', 'PROCESS_HEAD_CONFLICT'); } });
  editChanges(h); await h.edit.submit(); const before = copy(h.edit.getSnapshot());
  const changed = copy(h.live.base); changed.head_version++;
  changed.payload.placements = changed.payload.placements.filter((placement) => placement.placement_id !== 'edit-hidden-placement');
  h.live.base = changed; await h.edit.reloadBase();
  assert.equal(h.edit.getSnapshot().error.status, 409);
  for (const key of ['base', 'document', 'attempt', 'reason']) assert.deepEqual(h.edit.getSnapshot()[key], before[key]);
});

test('편집: 실제 제출 직전 문맥·사용자·권한 변경은 POST 차단', async () => {
  for (const kind of ['boundary', 'principal', 'permission']) {
    const h = editHarness(); editChanges(h);
    if (kind === 'boundary') h.live.access.boundary = { ...boundary, scope_node_id: 'synthetic-other-scope' };
    if (kind === 'principal') h.live.access.principal_user_id = 'synthetic-other-editor';
    if (kind === 'permission') h.live.access.permitted_actions = ['read'];
    assert.equal(await h.edit.submit(), null); assert.equal(proposals(h).length, 0);
    assert.equal(h.edit.getSnapshot().error.status, kind === 'permission' ? 403 : 409);
  }
});

test('편집: 화면 폐기 뒤 늦은 제안 접수는 노출 없음 / 원요청으로 재접속 확인', async () => {
  const pending = deferred(); const entered = deferred(); let paused = true;
  const h = editHarness({ propose: (...args) => {
    if (paused) { entered.resolve(); return pending.promise; } return h.completePropose(...args);
  } }); editChanges(h); const submitting = h.edit.submit(); await entered.promise;
  h.edit.invalidate(); const frozen = h.edit.getSnapshot();
  pending.resolve(h.completePropose(boundary, frozen.attempt.body));
  assert.equal(await submitting, null); assert.equal(h.edit.getSnapshot(), frozen);
  h.edit.begin(h.live.base, h.live.access); paused = false; await h.edit.submit();
  assert.deepEqual(proposals(h)[0].args, proposals(h)[1].args); assert.equal(h.keys(), 1);
});

test('편집: 접수 응답의 actor/base 불일치는 미확정 유지 / 동일 키 확인', async () => {
  let corrupt = true;
  const h = editHarness({ propose: (...args) => ({ ...h.completePropose(...args),
    ...(corrupt ? { actor: 'synthetic-wrong-actor', base_head_version: 99 } : {}) }) });
  editChanges(h); assert.equal(await h.edit.submit(), null);
  assert.equal(h.edit.getSnapshot().error.status, 503); assert.equal(h.edit.getSnapshot().receipt, null);
  corrupt = false; assert.ok(await h.edit.submit());
  assert.deepEqual(proposals(h)[0].args, proposals(h)[1].args); assert.equal(h.keys(), 1);
});

test('편집 SSR: 실제 선택·설명·순서·미리보기 / 확인 전 제출 잠금', () => {
  const h = editHarness(); editChanges(h); let reviewed = 0;
  const html = renderToStaticMarkup(React.createElement(editorComponentModule.ProcessConfigurationEditor,
    { flow: h.edit, busy: false, onReview: () => { reviewed++; } }));
  for (const label of ['우리 업무에 맞게 수정하기', '업무 이름', '업무 설명', '변경 이유', '제안할 변경 내용',
    '바로가기', '숨김', '미사용', '위 변경 내용과 적용 범위를 확인했습니다.', '원료 구매 관리']) assert.ok(html.includes(label), label);
  assert.match(html.match(/<button\b[^>]*>\s*변경안 제안하기\s*<\/button>/)?.[0] || '', /disabled/);
  assert.equal(reviewed, 0); assert.equal(proposals(h).length, 0);
});

test('편집: 제안 receipt를 기존 review/approve에 연결 / operation 없는 적용 GET', async () => {
  const h = editHarness(); editChanges(h); const receipt = await h.edit.submit();
  const review = followup({ get: () => { throw new Error('일반 편집은 설치 operation을 조회하지 않습니다.'); },
    approve: (...args) => { const old = copy(review.live.operation); const result = review.completeApproval(...args);
      review.live.operation = old; return result; } });
  Object.assign(review.live.review, receipt, { operation_id: null,
    payload: copy(h.edit.getSnapshot().document), base_payload: copy(h.live.base.payload) });
  await review.flow.load(); await review.flow.reviewChange(receipt.change_id);
  assert.equal(review.flow.getSnapshot().review.operation_id, null);
  review.flow.setApprovalReason('합성 편집 결과 확인'); await review.flow.approveChange();
  assert.equal(review.flow.getSnapshot().applicationVerified, true);
  assert.equal(review.flow.getSnapshot().operation, null);
  assert.equal(review.calls.filter((call) => call.name === 'get').length, 0);
  assert.deepEqual(review.flow.getSnapshot().resolved.payload, h.edit.getSnapshot().document);
});

test('편집 어댑터: 기존 changes POST 경로 / command·base·키·이유 본문 그대로', async () => {
  const h = editHarness(); editChanges(h); await h.edit.submit();
  const body = copy(h.edit.getSnapshot().attempt.body); identity = copy(identityBase);
  const calls = [];
  transport = async (url, init) => { calls.push({ url, init }); return succeeds(h.edit.getSnapshot().receipt); };
  await createProcessInstallationApi().propose(boundary, body);
  assert.equal(calls.length, 1); assert.equal(calls[0].url, '/api/v1/enterprise-context/process-configurations/changes');
  assert.equal(calls[0].init.method, 'POST'); assert.deepEqual(JSON.parse(calls[0].init.body), body);
  assert.ok(!Object.hasOwn(body, 'payload')); assert.ok(!Object.hasOwn(body, 'draft_digest'));
});

// 구조 편집도 실제 helper/controller를 사용한다. 서버·권한·승인은 여전히 메모리 API 대역이다.
test('구조 helper: 순차 replay와 apply는 원본·명령·고정 참조를 수정하지 않음', () => {
  const base = editBase().payload, original = copy(base);
  const steps = [
    { command: { op: 'ADD_NODE', node: { process_id: 'custom-root', level: 'L1', parent_process_id: '', label: '새 상위', note: '' } }, placementId: 'local-placement-root' },
    { command: { op: 'ADD_NODE', node: { process_id: 'custom-child', level: 'L2', parent_process_id: 'custom-root', label: '새 하위', note: '설명' } }, placementId: 'local-placement-child' },
    { command: { op: 'SET_USAGE', process_id: 'custom-child', enabled: false } },
    { command: { op: 'MOVE_NODE', process_id: 'custom-child', parent_process_id: 'edit-root-2' } },
    { command: { op: 'ADD_SHORTCUT', process_id: 'custom-child', parent_process_id: 'custom-root' }, placementId: 'local-placement-link' },
    { command: { op: 'REMOVE_SHORTCUT', placement_id: 'local-placement-link' } },
  ];
  const saved = copy(steps), result = replayProcessSteps(base, steps);
  assert.deepEqual(steps, saved); assert.deepEqual(base, original);
  assert.deepEqual(result, steps.reduce((doc, step) => applyProcessStep(doc, step), base));
  assert.equal(result.nodes.find((node) => node.process_id === 'custom-child').enabled, false);
  assert.equal(result.placements.find((p) => p.process_id === 'custom-child').parent_process_id, 'edit-root-2');
  assert.equal(result.placements.some((p) => p.placement_id === 'local-placement-link'), false);
  assert.deepEqual(result.template_sources, original.template_sources);
});

test('구조 helper: 잘못된 부모·중복 ID·canonical 삭제·중복 바로가기는 원본 보존', () => {
  const base = editBase().payload, original = copy(base);
  const add = (node, placementId = 'local-placement-test') => ({ command: { op: 'ADD_NODE', node }, placementId });
  const fresh = { process_id: 'custom-test', level: 'L2', parent_process_id: 'synthetic-l1', label: '합성', note: '' };
  const invalid = [add({ ...fresh, process_id: 'synthetic-l2' }), add({ ...fresh, parent_process_id: 'synthetic-l2' }),
    add({ ...fresh, level: 'L1' }), add({ ...fresh, label: ' ' }), add(fresh, 'placement-l1'),
    { command: { op: 'MOVE_NODE', process_id: 'synthetic-l1', parent_process_id: 'edit-root-2' } },
    { command: { op: 'ADD_SHORTCUT', process_id: 'edit-other-child', parent_process_id: 'synthetic-l1' }, placementId: 'local-placement-test' },
    { command: { op: 'REMOVE_SHORTCUT', placement_id: 'placement-l2' } },
  ];
  for (const step of invalid) {
    assert.throws(() => applyProcessStep(base, step), isError(422, 'CLIENT_STRUCTURE_INVALID'));
    assert.deepEqual(base, original);
  }
});

test('구조: 상위·하위 추가는 안정 업무 ID와 미리보기 배치를 분리 / 원본 보존', () => {
  const h = editHarness(), before = copy(h.live.base);
  const root = h.edit.addNode('L1', '', '새 상위', '상위 설명');
  const child = h.edit.addNode('L2', root, '새 하위');
  assert.ok(root && child && root !== child);
  assert.deepEqual(h.edit.getCommands(), [
    { op: 'ADD_NODE', node: { process_id: root, level: 'L1', parent_process_id: '', label: '새 상위', note: '상위 설명' } },
    { op: 'ADD_NODE', node: { process_id: child, level: 'L2', parent_process_id: root, label: '새 하위', note: '' } },
  ]);
  const state = h.edit.getSnapshot();
  assert.equal(state.selectedId, child); assert.deepEqual(state.workingBase, state.document);
  assert.ok(state.steps.every((step) => step.placementId.startsWith('local-placement-')));
  assert.ok(state.document.nodes.filter((node) => [root, child].includes(node.process_id)).every((node) => node.enabled));
  assert.deepEqual(state.base, before); assert.deepEqual(h.live.base, before); assert.equal(h.calls.length, 0);
});

test('구조: 표시 변경은 구조 action 앞에 고정 / 마지막 표시 차이만 뒤에 추가', () => {
  const h = editHarness(); editChanges(h);
  const prefix = buildProcessEditCommands(h.live.base.payload, h.edit.getSnapshot().document);
  h.edit.setUsage(false); h.edit.setLabel('두 번째 이름');
  h.edit.select('synthetic-l2'); h.edit.moveNode('edit-root-2'); h.edit.setNote('이동 뒤 설명');
  assert.deepEqual(h.edit.getCommands(), [...prefix,
    { op: 'SET_USAGE', process_id: 'synthetic-l1', enabled: false },
    { op: 'RENAME', process_id: 'synthetic-l1', label: '두 번째 이름' },
    { op: 'MOVE_NODE', process_id: 'synthetic-l2', parent_process_id: 'edit-root-2' },
    { op: 'SET_NOTE', process_id: 'synthetic-l2', note: '이동 뒤 설명' },
  ]);
  assert.deepEqual(buildProcessEditCommands(h.edit.getSnapshot().workingBase, h.edit.getSnapshot().document),
    [{ op: 'SET_NOTE', process_id: 'synthetic-l2', note: '이동 뒤 설명' }]);
});

test('구조: 사용 여부는 원본 노드만 변경 / canonical·shortcut ID 유지 / 같은 값 무명령', () => {
  const h = editHarness(), placements = copy(h.edit.getSnapshot().document.placements);
  h.edit.select('edit-other-child'); h.edit.setUsage(true); assert.deepEqual(h.edit.getCommands(), []);
  h.edit.setUsage(false); h.edit.setUsage(false);
  assert.deepEqual(h.edit.getCommands(), [{ op: 'SET_USAGE', process_id: 'edit-other-child', enabled: false }]);
  assert.equal(h.edit.getSnapshot().document.nodes.find((node) => node.process_id === 'edit-other-child').enabled, false);
  assert.deepEqual(h.edit.getSnapshot().document.placements, placements);
  assert.deepEqual(h.edit.getSnapshot().document.template_sources, h.live.base.payload.template_sources);
});

test('구조: 하위 이동은 canonical 소속만 변경 / L1·잘못된 부모·바로가기 충돌 차단', () => {
  const h = editHarness(); h.edit.select('synthetic-l2'); h.edit.moveNode('edit-root-2');
  const state = h.edit.getSnapshot();
  assert.equal(state.document.nodes.find((node) => node.process_id === 'synthetic-l2').parent_process_id, 'edit-root-2');
  assert.equal(state.document.placements.find((p) => p.placement_id === 'placement-l2').parent_process_id, 'edit-root-2');
  assert.deepEqual(state.document.placements.find((p) => p.placement_id === 'edit-shortcut'),
    h.live.base.payload.placements.find((p) => p.placement_id === 'edit-shortcut'));
  h.edit.moveNode('edit-root-2'); assert.equal(h.edit.getCommands().length, 1);
  for (const [id, parent] of [['synthetic-l1', 'edit-root-2'], ['synthetic-l2', 'missing'], ['edit-other-child', 'synthetic-l1']]) {
    h.edit.select(id); const before = copy(h.edit.getSnapshot().document), commands = h.edit.getCommands();
    h.edit.moveNode(parent); assert.equal(h.edit.getSnapshot().error.status, 422);
    assert.deepEqual(h.edit.getSnapshot().document, before); assert.deepEqual(h.edit.getCommands(), commands);
  }
});

test('구조: 바로가기는 하위 원본을 복제하지 않음 / 원래 부모·중복·L1 차단', () => {
  const h = editHarness(), nodes = copy(h.edit.getSnapshot().document.nodes);
  h.edit.addShortcut('synthetic-l2', 'edit-root-2');
  const state = h.edit.getSnapshot();
  assert.deepEqual(state.document.nodes, nodes);
  assert.equal(state.document.placements.length, h.live.base.payload.placements.length + 1);
  assert.deepEqual(h.edit.getCommands(), [{ op: 'ADD_SHORTCUT', process_id: 'synthetic-l2', parent_process_id: 'edit-root-2' }]);
  for (const [id, parent] of [['synthetic-l2', 'edit-root-2'], ['synthetic-l2', 'synthetic-l1'], ['synthetic-l1', 'edit-root-2']]) {
    h.edit.addShortcut(id, parent); assert.equal(h.edit.getSnapshot().error.status, 422);
    assert.deepEqual(h.edit.getSnapshot().document, state.document); assert.equal(h.edit.getCommands().length, 1);
  }
});

test('구조: 기존 shortcut 제거와 미제출 shortcut 취소 구별 / 임시 삭제 명령 전송 없음', () => {
  const h = editHarness(); h.edit.removeShortcut('edit-shortcut');
  assert.deepEqual(h.edit.getCommands(), [{ op: 'REMOVE_SHORTCUT', placement_id: 'edit-shortcut' }]);
  assert.ok(h.edit.getSnapshot().document.nodes.some((node) => node.process_id === 'edit-other-child'));
  const before = copy(h.edit.getSnapshot().document);
  h.edit.addShortcut('synthetic-l2', 'edit-root-2');
  const localId = h.edit.getSnapshot().steps.at(-1).placementId;
  h.edit.select('synthetic-l2'); h.edit.setNote('취소 뒤에도 보존할 설명'); h.edit.removeShortcut(localId);
  assert.deepEqual(h.edit.getCommands(), [{ op: 'REMOVE_SHORTCUT', placement_id: 'edit-shortcut' },
    { op: 'SET_NOTE', process_id: 'synthetic-l2', note: '취소 뒤에도 보존할 설명' }]);
  assert.deepEqual(h.edit.getSnapshot().document.placements, before.placements);
  assert.ok(!JSON.stringify(h.edit.getCommands()).includes('local-placement-'));
});

test('구조: 임시 배치 포함 형제 순서만 차단 / 승인 GET의 서버 배치 ID로 재정렬 재개', async () => {
  for (const kind of ['node', 'shortcut']) {
    const h = editHarness();
    if (kind === 'node') h.edit.addNode('L2', 'edit-root-2', '새 업무');
    else h.edit.addShortcut('synthetic-l2', 'edit-root-2');
    assert.equal(h.edit.canReorder('edit-root-2'), false); assert.equal(h.edit.canReorder('synthetic-l1'), true);
    const before = copy(h.edit.getSnapshot().document);
    h.edit.move('edit-other-placement', 1); assert.equal(h.edit.getSnapshot().error.status, 422);
    assert.deepEqual(h.edit.getSnapshot().document, before); assert.equal(h.edit.getSnapshot().rejected, false);
    h.edit.setReason('합성 구조 변경'); const receipt = await h.edit.submit(); assert.ok(receipt);
    const approved = copy(h.edit.getSnapshot().document);
    approved.placements.forEach((p) => { if (p.placement_id.startsWith('local-placement-')) p.placement_id = p.placement_id.replace('local-placement-', 'synthetic-server-placement-'); });
    h.live.base = { ...h.live.base, head_version: 8, profile_id: receipt.draft_profile_id, digest: receipt.draft_digest, payload: approved };
    await h.edit.reloadBase(); assert.equal(h.edit.canReorder('edit-root-2'), true);
    h.edit.move('edit-other-placement', 1);
    assert.equal(h.edit.getCommands()[0].op, 'REORDER_PLACEMENTS');
    assert.equal(h.edit.getSnapshot().steps.length, 0);
  }
});

test('구조: 외부 명령 배열 변경·invalid action은 원본 steps와 미리보기 불변', () => {
  const h = editHarness(); const id = h.edit.addNode('L2', 'synthetic-l1', '보존할 업무'); h.edit.setNote('보존할 설명');
  const commands = h.edit.getCommands(); commands[0].node.label = '외부 덮어쓰기'; commands.pop();
  assert.equal(h.edit.getCommands()[0].node.label, '보존할 업무'); assert.equal(h.edit.getCommands().length, 2);
  const before = copy(h.edit.getSnapshot());
  assert.equal(h.edit.addNode('L2', id, '잘못된 하위'), null);
  for (const key of ['base', 'workingBase', 'document', 'steps']) assert.deepEqual(h.edit.getSnapshot()[key], before[key]);
  const moved = { ...h.live.base, boundary: { ...boundary, scope_node_id: 'other' } };
  h.edit.begin(moved, { ...h.live.access, boundary: moved.boundary });
  assert.deepEqual(h.edit.getSnapshot().base, before.base); assert.deepEqual(h.edit.getSnapshot().document, before.document);
});

test('구조 제출·어댑터: 전체 명령 순서와 base/key 고정 / local placement 메타데이터 없음', async () => {
  const h = editHarness(); h.edit.setLabel('수정 상위');
  const root = h.edit.addNode('L1', '', '새 상위'); const child = h.edit.addNode('L2', root, '새 하위');
  h.edit.setUsage(false); h.edit.moveNode('edit-root-2'); h.edit.addShortcut(child, root);
  h.edit.removeShortcut('edit-shortcut'); h.edit.setReason('  합성 구조 제출  ');
  const commands = h.edit.getCommands(); await h.edit.submit();
  const body = h.edit.getSnapshot().attempt.body;
  assert.deepEqual(body.commands, commands); assert.equal(body.expected_head_version, 7);
  assert.equal(body.base_profile_id, resolved.profile_id); assert.equal(body.base_fingerprint, resolved.digest);
  assert.equal(body.reason, '합성 구조 제출'); assert.ok(!JSON.stringify(body).includes('local-placement-'));
  assert.ok(body.commands.every((command) => !Object.hasOwn(command, 'placementId')));
  assert.ok(!Object.hasOwn(body, 'steps')); assert.ok(!Object.hasOwn(body, 'workingBase'));
  identity = copy(identityBase); const calls = [];
  transport = async (url, init) => { calls.push({ url, init }); return succeeds(h.edit.getSnapshot().receipt); };
  await createProcessInstallationApi().propose(boundary, body);
  assert.equal(calls[0].url, '/api/v1/enterprise-context/process-configurations/changes');
  assert.equal(calls[0].init.method, 'POST'); assert.deepEqual(JSON.parse(calls[0].init.body), body);
  assert.equal(calls.length, 1); assert.equal(proposals(h).length, 1);
});

test('구조: 503·unknown409는 revise/추가/삭제로 미확정 해제 불가 / 동일 키 재시도', async () => {
  for (const status of [503, 409]) {
    let failed = true;
    const h = editHarness({ propose: (...args) => {
      if (failed) throw new ProcessApiError(status, '합성 미확정', 'SYNTHETIC_UNKNOWN');
      return h.completePropose(...args);
    } });
    h.edit.addNode('L2', 'synthetic-l1', '새 업무'); h.edit.setReason('미확정 구조'); await h.edit.submit();
    const before = copy(h.edit.getSnapshot()), keys = h.keys();
    h.edit.revise(); h.edit.setUsage(false); h.edit.moveNode('edit-root-2');
    assert.equal(h.edit.addNode('L1', '', '추가 금지'), null);
    h.edit.addShortcut('synthetic-l2', 'edit-root-2'); h.edit.removeShortcut('edit-shortcut'); h.edit.reset();
    for (const key of ['attempt', 'steps', 'document', 'workingBase']) assert.deepEqual(h.edit.getSnapshot()[key], before[key]);
    assert.equal(h.edit.getSnapshot().rejected, false); assert.equal(h.keys(), keys);
    failed = false; await h.edit.submit(); assert.deepEqual(proposals(h)[0].args, proposals(h)[1].args);
  }
});

test('구조: propose 확정 422만 rejected / 명시 revise 뒤 입력 보존·새 키 제출', async () => {
  let rejected = true;
  const h = editHarness({ propose: (...args) => {
    if (rejected) throw new ProcessApiError(422, '합성 구조 거절', 'PROCESS_COMMAND_INVALID');
    return h.completePropose(...args);
  } });
  const id = h.edit.addNode('L2', 'synthetic-l1', '수정 전'); h.edit.setReason('합성 이유'); await h.edit.submit();
  const before = copy(h.edit.getSnapshot()); assert.equal(before.rejected, true);
  h.edit.setLabel('잠금 중 변경'); assert.equal(h.edit.getSnapshot().document.nodes.find((n) => n.process_id === id).label, '수정 전');
  h.edit.revise(); assert.equal(h.edit.getSnapshot().attempt, null); assert.equal(h.edit.getSnapshot().rejected, false);
  for (const key of ['base', 'document', 'steps', 'workingBase', 'reason']) assert.deepEqual(h.edit.getSnapshot()[key], before[key]);
  h.edit.setLabel('수정 후'); rejected = false; await h.edit.submit();
  const next = proposals(h)[1].args[1]; assert.notEqual(next.client_request_id, before.attempt.body.client_request_id);
  assert.deepEqual(next.commands.at(-1), { op: 'RENAME', process_id: id, label: '수정 후' });
  assert.equal(next.base_fingerprint, before.attempt.body.base_fingerprint);
});

test('구조 우선경계: 선행 access GET 422는 최초·미확정 모두 rejected 해제 권한 없음', async () => {
  let deny = true;
  const h = editHarness({ access: () => {
    if (deny) throw new ProcessApiError(422, '합성 access 오류'); return h.live.access;
  }, propose: () => { throw new ProcessApiError(503, '합성 접수 미확정'); } });
  h.edit.addNode('L2', 'synthetic-l1', 'GET 실패 보존'); h.edit.setReason('합성 이유');
  await h.edit.submit(); assert.equal(h.edit.getSnapshot().rejected, false);
  assert.equal(h.edit.getSnapshot().attempt, null); assert.equal(proposals(h).length, 0);
  deny = false; await h.edit.submit(); const before = copy(h.edit.getSnapshot()), keys = h.keys();
  deny = true; await h.edit.submit(); assert.equal(h.edit.getSnapshot().error.status, 422);
  h.edit.revise(); h.edit.reset();
  assert.equal(h.edit.getSnapshot().rejected, false); assert.equal(proposals(h).length, 1); assert.equal(h.keys(), keys);
  for (const key of ['base', 'attempt', 'document', 'steps', 'workingBase', 'reason']) assert.deepEqual(h.edit.getSnapshot()[key], before[key]);
});

test('구조: resolved GET 422·replay 실패는 원 steps/attempt 보존 / CLIENT_REBASE_CONFLICT', async () => {
  let getFails = true;
  const h = editHarness({ propose: () => { throw new ProcessApiError(409, '합성 경합', 'PROCESS_HEAD_CONFLICT'); },
    resolved: () => { if (getFails) throw new ProcessApiError(422, '합성 조회 오류'); return h.live.base; } });
  h.edit.addNode('L2', 'edit-root-2', '부모 보존 필요'); h.edit.setReason('합성 이유'); await h.edit.submit();
  const before = copy(h.edit.getSnapshot()); await h.edit.reloadBase();
  assert.equal(h.edit.getSnapshot().error.status, 422); assert.equal(h.edit.getSnapshot().rejected, false);
  h.edit.revise();
  for (const key of ['base', 'attempt', 'document', 'steps', 'workingBase', 'reason']) assert.deepEqual(h.edit.getSnapshot()[key], before[key]);
  getFails = false; h.live.base = copy(h.live.base); h.live.base.head_version++;
  const removed = ['edit-root-2', 'edit-other-child'];
  h.live.base.payload.nodes = h.live.base.payload.nodes.filter((node) => !removed.includes(node.process_id));
  h.live.base.payload.placements = h.live.base.payload.placements.filter((placement) =>
    !removed.includes(placement.process_id) && !removed.includes(placement.parent_process_id));
  await h.edit.reloadBase();
  assert.equal(h.edit.getSnapshot().error.reasonCode, 'CLIENT_REBASE_CONFLICT');
  assert.equal(h.edit.getSnapshot().error.status, 409); assert.equal(h.edit.getSnapshot().rejected, false);
  for (const key of ['base', 'attempt', 'document', 'steps', 'workingBase', 'reason']) assert.deepEqual(h.edit.getSnapshot()[key], before[key]);
});

test('구조: 최신 기준판에 표시 prefix·구조·최종 표시 전체 replay / 새 키는 명시 제출 때만', async () => {
  let conflict = true;
  const h = editHarness({ propose: (...args) => {
    if (conflict) throw new ProcessApiError(409, '합성 경합', 'PROCESS_HEAD_CONFLICT'); return h.completePropose(...args);
  } });
  h.edit.setLabel('보존 상위'); h.edit.addNode('L2', 'synthetic-l1', '추가 하위');
  h.edit.setUsage(false); h.edit.setNote('마지막 설명'); h.edit.setReason('합성 전체 replay');
  const commands = h.edit.getCommands(); await h.edit.submit(); const before = copy(h.edit.getSnapshot()), keys = h.keys();
  h.live.base = copy(h.live.base); h.live.base.head_version++; h.live.base.profile_id = 'synthetic-latest'; h.live.base.digest = '8'.repeat(64);
  h.live.base.payload.nodes.find((node) => node.process_id === 'edit-other-child').note = '다른 사용자의 최신 설명';
  await h.edit.reloadBase(); const state = h.edit.getSnapshot();
  assert.equal(state.error, null); assert.equal(state.attempt, null); assert.equal(state.conflict, false);
  assert.deepEqual(h.edit.getCommands(), commands); assert.deepEqual(state.workingBase, state.document);
  assert.deepEqual(state.document, replayProcessSteps(h.live.base.payload, state.steps));
  assert.equal(state.document.nodes.find((node) => node.process_id === 'edit-other-child').note, '다른 사용자의 최신 설명');
  assert.equal(h.keys(), keys); assert.equal(proposals(h).length, 1);
  conflict = false; await h.edit.submit(); const next = proposals(h)[1].args[1];
  assert.notEqual(next.client_request_id, before.attempt.body.client_request_id); assert.deepEqual(next.commands, commands);
  assert.equal(next.expected_head_version, 8); assert.equal(next.base_profile_id, 'synthetic-latest');
});

test('구조: unmount 뒤 propose 422는 rejected로 바꾸지 않음 / frozen 원요청 보존', async () => {
  const pending = deferred(), entered = deferred();
  const h = editHarness({ propose: () => { entered.resolve(); return pending.promise; } });
  h.edit.addNode('L2', 'synthetic-l1', '늦은 오류 시험'); h.edit.setReason('합성 이유');
  const running = h.edit.submit(); await entered.promise; h.edit.invalidate(); const frozen = h.edit.getSnapshot();
  pending.reject(new ProcessApiError(422, '뒤늦게 도착한 거절')); assert.equal(await running, null);
  assert.equal(h.edit.getSnapshot(), frozen); assert.equal(frozen.rejected, false);
  h.edit.revise(); assert.equal(h.edit.getSnapshot().attempt, frozen.attempt); assert.equal(proposals(h).length, 1);
});

test('구조: 읽기 전용·제출 대기 동안 구조 변경과 중복 제출 차단', async () => {
  const h = editHarness(); h.edit.begin(h.live.base, { ...h.live.access, permitted_actions: ['read'] });
  const readOnly = copy(h.edit.getSnapshot().document);
  assert.equal(h.edit.addNode('L1', '', '금지'), null); h.edit.setUsage(false); h.edit.moveNode('edit-root-2');
  h.edit.addShortcut('synthetic-l2', 'edit-root-2'); h.edit.removeShortcut('edit-shortcut');
  assert.deepEqual(h.edit.getSnapshot().document, readOnly); assert.deepEqual(h.edit.getCommands(), []); assert.equal(h.keys(), 0);
  const pending = deferred(), entered = deferred();
  const active = editHarness({ propose: () => { entered.resolve(); return pending.promise; } });
  active.edit.addNode('L2', 'synthetic-l1', '제출 업무'); active.edit.setReason('합성 이유');
  const running = active.edit.submit(); await entered.promise; const before = copy(active.edit.getSnapshot());
  assert.equal(await active.edit.submit(), null); assert.equal(active.edit.addNode('L1', '', '금지'), null);
  active.edit.setUsage(false); active.edit.removeShortcut('edit-shortcut'); active.edit.revise();
  assert.deepEqual(active.edit.getSnapshot().document, before.document); assert.deepEqual(active.edit.getSnapshot().steps, before.steps);
  pending.resolve(active.completePropose(boundary, before.attempt.body)); assert.ok(await running); assert.equal(proposals(active).length, 1);
});

test('구조 SSR: 실제 추가 설정·모든 구조 미리보기·임시 순서 잠금·명시 422 수정 안내', async () => {
  const h = editHarness({ propose: () => { throw new ProcessApiError(422, '합성 서버 거절'); } });
  const root = h.edit.addNode('L1', '', 'SSR 새 상위'); const child = h.edit.addNode('L2', root, 'SSR 새 하위');
  h.edit.setLabel('SSR 수정 하위'); h.edit.setNote('SSR 설명'); h.edit.setUsage(false);
  h.edit.moveNode('edit-root-2'); h.edit.addShortcut(child, root); h.edit.removeShortcut('edit-shortcut');
  h.edit.setReason('SSR 합성 구조 검토');
  const render = () => renderToStaticMarkup(React.createElement(editorComponentModule.ProcessConfigurationEditor,
    { flow: h.edit, busy: false, onReview: () => { throw new Error('SSR은 제안·검토를 실행하지 않습니다.'); } }));
  const html = render();
  for (const label of ['추가 설정', '새 업무 추가', '이 업무 사용', '소속 상위 업무 변경', '바로가기만 제거',
    '상위 업무 추가', '하위 업무 추가', '미사용', '바로가기 추가', '바로가기 제거', 'SSR 수정 하위', 'SSR 설명']) {
    assert.ok(html.includes(label), label);
  }
  const arrows = [...html.matchAll(/<button\b[^>]*aria-label="SSR 수정 하위 (?:위로|아래로)"[^>]*>/g)];
  assert.equal(arrows.length, 2); assert.ok(arrows.every(([tag]) => tag.includes('disabled')));
  assert.match(html.match(/<button\b[^>]*>\s*편집 초안에 업무 추가\s*<\/button>/)?.[0] || '', /disabled/);
  assert.equal(h.calls.length, 0); await h.edit.submit();
  const rejected = render(); assert.ok(rejected.includes('입력을 보존하고 수정 이어하기'));
  assert.match(rejected.match(/<button\b[^>]*>\s*같은 요청으로 접수 확인·재시도\s*<\/button>/)?.[0] || '', /disabled/);
  assert.equal(proposals(h).length, 1);
});

test('구조 양식: 미추가 raw 입력은 범위 왕복·재연결·새 승인판에도 보존 / 명시 reset만 초기화', async () => {
  const choice = { selectedId: 'synthetic-l1', parentId: 'edit-root-2' };
  for (const patch of [{ label: '  작성 중 이름  ' }, { note: '작성 중 설명' }, { level: 'L1' },
    { addParent: choice }, { moveParent: choice }, { shortcutParent: choice }]) {
    const h = editHarness(), empty = copy(h.edit.getSnapshot().structureInput), original = copy(h.live.base);
    h.edit.setStructureInput(patch); h.edit.setStructureInput({ message: '입력 보존 안내', failed: true });
    const input = copy(h.edit.getSnapshot().structureInput);
    assert.deepEqual(JSON.parse(JSON.stringify(input)), input);
    assert.deepEqual(input, { ...empty, ...patch, message: '입력 보존 안내', failed: true });
    assert.deepEqual(h.edit.getCommands(), []); assert.equal(h.edit.getSnapshot().reason, '');
    const latest = { ...copy(h.live.base), head_version: 8, profile_id: 'synthetic-form-latest', digest: '8'.repeat(64) };
    h.edit.begin(latest, h.live.access);
    const otherBoundary = { ...boundary, scope_node_id: 'synthetic-other-form-scope' };
    h.edit.begin({ ...latest, boundary: otherBoundary }, { ...h.live.access, boundary: otherBoundary });
    const other = editHarness();
    other.edit.begin({ ...latest, boundary: otherBoundary }, { ...other.live.access, boundary: otherBoundary });
    other.edit.setStructureInput({ label: '다른 범위의 입력' });
    h.edit.invalidate(); h.edit.begin(h.live.base, h.live.access);
    assert.deepEqual(h.edit.getSnapshot().structureInput, input); assert.deepEqual(h.edit.getSnapshot().base, original);
    const html = renderToStaticMarkup(React.createElement(structureComponentModule.ProcessStructureEditor, { flow: h.edit, locked: false }));
    assert.ok(html.includes('입력 보존 안내'));
    if (input.label) assert.ok(html.includes(`value="${input.label}"`));
    if (input.note) assert.ok(html.includes(input.note));
    assert.equal(h.calls.length, 0);
    // 명시 최신판 조회도 추가하지 않은 양식 자체는 지우지 않는다.
    h.live.base = latest; await h.edit.reloadBase();
    assert.deepEqual(h.edit.getSnapshot().structureInput, input); assert.equal(h.edit.getSnapshot().base.head_version, 8);
    h.edit.reset(); assert.deepEqual(h.edit.getSnapshot().structureInput, empty); assert.equal(h.edit.getSnapshot().base, null);
    assert.equal(other.edit.getSnapshot().structureInput.label, '다른 범위의 입력');
  }
});

test('구조 양식: 미추가 이름·설명·공백은 로컬 422/POST0 / 추가·비우기 후 제출 및 미확정 잠금', async () => {
  for (const patch of [{ label: '추가할 업무' }, { note: '설명만 작성 중' }, { label: '  ', note: ' ' }]) {
    const pending = deferred(), entered = deferred(); let wait = true;
    const h = editHarness({ propose: (...args) => {
      if (wait) { entered.resolve(); return pending.promise; } return h.completePropose(...args);
    } });
    h.edit.setUsage(false); h.edit.setReason('합성 제안 이유'); h.edit.setStructureInput(patch);
    const input = copy(h.edit.getSnapshot().structureInput), commands = h.edit.getCommands();
    assert.equal(await h.edit.submit(), null); assert.equal(h.edit.getSnapshot().error.status, 422);
    assert.equal(h.edit.getSnapshot().rejected, false); assert.equal(h.edit.getSnapshot().attempt, null);
    assert.equal(proposals(h).length, 0); assert.equal(h.keys(), 0);
    assert.deepEqual(h.calls.map((call) => call.name), ['access']);
    assert.deepEqual(h.edit.getSnapshot().structureInput, input); assert.deepEqual(h.edit.getCommands(), commands);
    // UI의 명시 추가·비우기가 호출하는 동일 flow 경계이다. 클릭 동작 검증은 아니다.
    if (input.label.trim()) assert.ok(h.edit.addNode('L2', 'synthetic-l1', input.label, input.note));
    h.edit.setStructureInput({ label: '', note: '', addParent: null, message: '', failed: false });
    const cleared = copy(h.edit.getSnapshot().structureInput);
    const running = h.edit.submit(); await entered.promise;
    h.edit.setStructureInput({ label: '전송 중 변경 금지', moveParent: { selectedId: 'synthetic-l2', parentId: 'edit-root-2' } });
    assert.deepEqual(h.edit.getSnapshot().structureInput, cleared);
    pending.reject(new ProcessApiError(503, '합성 응답 미확정')); assert.equal(await running, null);
    const frozen = copy(h.edit.getSnapshot().attempt), keys = h.keys();
    h.edit.setStructureInput({ label: '미확정 중 변경 금지', note: '잠금' }); h.edit.revise(); h.edit.reset();
    assert.deepEqual(h.edit.getSnapshot().structureInput, cleared); assert.deepEqual(h.edit.getSnapshot().attempt, frozen);
    assert.ok(!Object.hasOwn(frozen.body, 'structureInput')); assert.equal(h.keys(), keys);
    wait = false; assert.ok(await h.edit.submit());
    assert.deepEqual(proposals(h)[0].args, proposals(h)[1].args); assert.equal(h.keys(), keys);
  }
});

for (const [kind, label] of [['빈 이름', ''], ['200자 초과 이름', '가'.repeat(201)]]) {
  test(`구조 prefix: ${kind}는 append 원자적 실패 / steps·workingBase·입력 보존 / 교정 후 성공`, () => {
    const h = editHarness(); editChanges(h); h.edit.setLabel(label);
    const before = copy(h.edit.getSnapshot()), commands = h.edit.getCommands();
    h.edit.setUsage(false);
    assert.equal(h.edit.getSnapshot().error.status, 422);
    for (const key of ['base', 'document', 'workingBase', 'steps', 'reason', 'structureInput', 'attempt', 'receipt']) {
      assert.deepEqual(h.edit.getSnapshot()[key], before[key], `${kind}:${key}`);
    }
    assert.deepEqual(h.edit.getCommands(), commands);
    assert.equal(h.edit.getSnapshot().conflict, false); assert.equal(h.edit.getSnapshot().rejected, false);
    h.edit.setLabel('교정된 업무 이름'); h.edit.setUsage(false);
    const state = h.edit.getSnapshot(); assert.equal(state.error, null);
    assert.equal(state.document.nodes.find((node) => node.process_id === 'synthetic-l1').enabled, false);
    assert.deepEqual(state.workingBase, state.document);
    assert.deepEqual(state.document, replayProcessSteps(h.live.base.payload, state.steps));
    assert.equal(state.document.nodes[0].label, '교정된 업무 이름');
    assert.equal(state.document.nodes[0].note, before.document.nodes[0].note);
    assert.deepEqual(state.document.placements, before.document.placements);
    assert.ok(h.edit.getCommands().filter((command) => command.op === 'RENAME').every((command) => command.label === '교정된 업무 이름'));
    assert.deepEqual(h.edit.getCommands().at(-1), { op: 'SET_USAGE', process_id: 'synthetic-l1', enabled: false });
    assert.equal(h.calls.length, 0);
  });
}

test('구조 prefix: 빈 이름 교정 뒤 미제출 바로가기 취소·전체 rebase·제출이 잠기지 않음', async () => {
  const h = editHarness(); h.edit.addShortcut('synthetic-l2', 'edit-root-2');
  const localId = h.edit.getSnapshot().steps[0].placementId;
  h.edit.select('synthetic-l1'); h.edit.setLabel(''); h.edit.setNote('취소·최신판에도 보존');
  const before = copy(h.edit.getSnapshot()); h.edit.setUsage(false);
  assert.equal(h.edit.getSnapshot().error.status, 422); assert.deepEqual(h.edit.getSnapshot().steps, before.steps);
  h.edit.setLabel('교정한 상위 업무'); h.edit.removeShortcut(localId);
  assert.equal(h.edit.getSnapshot().error, null);
  assert.deepEqual(h.edit.getCommands(), [
    { op: 'RENAME', process_id: 'synthetic-l1', label: '교정한 상위 업무' },
    { op: 'SET_NOTE', process_id: 'synthetic-l1', note: '취소·최신판에도 보존' },
  ]);
  assert.equal(h.edit.getSnapshot().document.placements.some((p) => p.placement_id === localId), false);
  assert.equal(h.edit.getSnapshot().document.nodes[0].enabled, true);
  h.edit.setReason('교정한 변경 재검토'); const commands = h.edit.getCommands();
  h.live.base = copy(h.live.base); h.live.base.head_version = 8;
  h.live.base.profile_id = 'synthetic-corrected-prefix-base'; h.live.base.digest = '8'.repeat(64);
  h.live.base.payload.nodes.find((node) => node.process_id === 'edit-other-child').note = '다른 최신 변경';
  await h.edit.reloadBase();
  assert.equal(h.edit.getSnapshot().error, null); assert.equal(h.edit.getSnapshot().conflict, false);
  assert.equal(h.edit.getSnapshot().base.head_version, 8); assert.deepEqual(h.edit.getCommands(), commands);
  assert.equal(h.edit.getSnapshot().document.nodes.find((node) => node.process_id === 'edit-other-child').note, '다른 최신 변경');
  assert.equal(proposals(h).length, 0); assert.ok(await h.edit.submit());
  assert.equal(proposals(h).length, 1); assert.equal(proposals(h)[0].args[1].expected_head_version, 8);
  assert.deepEqual(proposals(h)[0].args[1].commands, commands);
  assert.ok(!JSON.stringify(proposals(h)[0].args).includes('local-placement-'));
});

test('STATIC: 두 진입 버튼의 단일 패널·닫기 재조회 배선 / DOM·focus·실제 조회 미검증', () => {
  // 소스 형태만 검사한다. 컴포넌트를 import하거나 클릭·포커스·effect 동작을 실행하지 않는다.
  const source = (name) => fs.readFileSync(new URL(`../src/components/${name}.tsx`, import.meta.url), 'utf8');
  const setup = source('CompanySetupPanel');
  assert.match(setup, /initialTab\s*=\s*'company'/);
  assert.match(setup, /initialTab\?\s*:\s*Tab/);
  assert.match(setup, /useState<Tab>\(initialTab\)/);
  for (const name of ['EnterprisePage', 'KitOperationsPanel']) {
    const text = source(name);
    assert.match(text, /import\s*\{\s*CompanySetupPanel\s*\}\s*from\s*'\.\/CompanySetupPanel'/, name);
    assert.equal((text.match(/<CompanySetupPanel\b/g) || []).length, 1, `${name}: 단일 공유 패널`);
    const entry = text.match(/if\s*\(showProcessConfiguration\)\s*return\s*<CompanySetupPanel\s+initialTab="thread"[\s\S]*?\/>;/)?.[0] || '';
    assert.ok(entry, `${name}: 단일 early-return`);
    assert.match(entry, /onClose=\{\(\)\s*=>\s*\{[\s\S]*setShowProcessConfiguration\(false\)/, name);
    if (name === 'EnterprisePage') {
      assert.match(entry, /setThreadRevision\(\(\s*(\w+)\s*\)\s*=>\s*\1\s*\+\s*1\)/);
      assert.match(entry, /setThread\(null\)/); assert.match(entry, /setThreadState\('loading'\)/);
      assert.match(text, /\[threadRevision,\s*setThreadRevision\]\s*=\s*useState\(0\)/);
      // 소스 텍스트의 조회 hook 의존성만 대조한다. 네트워크 재조회나 효과 실행의 증거는 아니다.
      const threadDeps = text.match(/listProfiles\(scope,[\s\S]*?\},\s*\[([^\]]*)\]\)/)?.[1] || '';
      const canvasDeps = text.match(/fetchCanvas\(\)[\s\S]*?\},\s*\[([^\]]*)\]\)/)?.[1] || '';
      const calcDeps = text.match(/setCalcWhy\(null\)[\s\S]*?\},\s*\[([^\]]*)\]\)/)?.[1] || '';
      const readinessDeps = text.match(/setReadiness\(null\)[\s\S]*?\},\s*\[([^\]]*)\]\)/)?.[1] || '';
      for (const deps of [threadDeps, canvasDeps, calcDeps, readinessDeps]) assert.match(deps, /\bthreadRevision\b/);
      assert.match(text, /setCanvas\(null\)/);
      assert.match(text, /if\s*\(alive\)\s*setCalcWhy\(w\)/);
      assert.match(text, /if\s*\(alive\)\s*setReadiness\(out\)/);
      assert.match(text, /if\s*\(alive\)\s*\{\s*setCanvas\(c\)/);
    } else {
      assert.match(entry, /setRevision\(\(\s*(\w+)\s*\)\s*=>\s*\1\s*\+\s*1\)/);
      assert.match(entry, /setInstances\(null\)/);
      // 위 EnterprisePage 와 같은 방식으로 **의존성 목록에 들어 있는지**만 본다.
      // ⚠️ 종전에는 `[revision]` 정확 일치를 요구해, 같은 커밋(58713ed1d)이 문맥 전환
      //   재조회를 위해 `identity` 를 더하자 정상 배선이 실패로 닫혔다. 의존성 추가는
      //   이 검사가 막으려는 것(재조회 미배선)이 아니다.
      const instanceDeps = text.match(/listInstances\(\)[\s\S]*?\},\s*\[([^\]]*)\]\)/)?.[1] || '';
      assert.match(instanceDeps, /\brevision\b/);
      assert.match(text, /setSelected\(\(previous\)\s*=>\s*rows\.some\([\s\S]*?===\s*previous\)\s*\?\s*previous\s*:\s*rows\.length\s*===\s*1\s*\?\s*String\(rows\[0\]\.instance_id\s*\|\|\s*''\)\s*:\s*''\)/);
    }
    assert.match(text, /<button\s+ref=\{processButton\}[\s\S]*?onClick=\{\(\)\s*=>\s*setShowProcessConfiguration\(true\)\}>업무 구성 · L1\/L2 수정<\/button>/, name);
    assert.equal((text.match(/업무 구성 · L1\/L2 수정<\/button>/g) || []).length, 1, `${name}: 진입 버튼`);
    assert.match(text, /if\s*\(!showProcessConfiguration\s*&&\s*processWasOpen\.current\)\s*processButton\.current\?\.focus\(\)/, name);
  }
});

const originalFetch = globalThis.fetch;
// [2026-09-26 Codex §20] 판본 업그레이드 — 활성화 대기의 복구는 같은 승인자의 같은 승인 재요청뿐이다.
const upgradeRetry = { change_id: 'synthetic-upgrade-change', expected_head_version: 7,
  draft_digest: 'e'.repeat(64), reason: '합성 원래 승인 이유' };
const pendingUpgrade = { instance_id: 'synthetic-instance', from_artifact_digest: 'a'.repeat(64),
  to_artifact_digest: 'b'.repeat(64), from_version: '1.1.0', to_version: '1.2.0',
  activation: 'ACTIVATION_PENDING', activation_error: 'PROCESS_STORAGE_UNAVAILABLE', retry: upgradeRetry };
function renderUpgrade(h, upgrade) {
  const { UpgradeActivation } = loadTs('../src/components/ProcessInstallationPanel.tsx', {
    '../lib/processInstallationApi': apiModule, '../lib/processInstallationFlow': flowModule,
    './process-installation.css': {},
  });
  return renderToStaticMarkup(React.createElement(UpgradeActivation, { flow: h.flow, state: h.flow.getSnapshot(), upgrade }));
}

test('업그레이드: 활성화 재시도는 서버가 준 같은 승인 값만 POST / 아직 대기면 503 을 보이고 다시 읽음 / 복구 뒤에는 POST 없음', async () => {
  let attempts = 0;
  const h = followup({ approve: (_boundary, changeId, body) => {
    attempts += 1;
    if (attempts === 1) throw new ProcessApiError(503, '합성 활성화 대기', 'PROCESS_UPGRADE_ACTIVATION_PENDING');
    const { retry: _retry, activation_error: _error, ...rest } = h.live.operation.upgrade;
    h.live.operation.upgrade = { ...rest, activation: 'ACTIVE' };
    return { change_id: changeId, configuration_id: resolved.configuration_id, status: 'APPLIED',
      profile_id: 'synthetic-upgrade-profile', head_version: body.expected_head_version + 1,
      digest: body.draft_digest, event_id: 'synthetic-approval-event', audit_delivery: 'PENDING' };
  } });
  Object.assign(h.live.operation, { stage: 'APPLIED', change_id: upgradeRetry.change_id, permitted_actions: [],
    upgrade: copy(pendingUpgrade) });
  await openedOperation(h);
  await h.flow.retryActivation();
  assert.deepEqual(writeCalls(h).map((call) => call.args), [[boundary, upgradeRetry.change_id, {
    expected_head_version: 7, draft_digest: 'e'.repeat(64), reason: '합성 원래 승인 이유' }]]);
  assert.equal(h.flow.getSnapshot().error.reasonCode, 'PROCESS_UPGRADE_ACTIVATION_PENDING');
  assert.equal(h.flow.getSnapshot().operation.upgrade.activation, 'ACTIVATION_PENDING');
  await h.flow.retryActivation();
  assert.equal(writeCalls(h).length, 2);
  assert.equal(h.flow.getSnapshot().error, null);
  assert.equal(h.flow.getSnapshot().operation.upgrade.activation, 'ACTIVE');
  await h.flow.retryActivation();
  assert.equal(writeCalls(h).length, 2, '활성화된 뒤에는 다시 보내지 않는다');
  assert.equal(h.flow.getSnapshot().error.status, 409);
});

test('업그레이드: 다른 오류는 삼키지 않는다 / retry 값이 없으면(승인자가 아님) POST 없음', async () => {
  const h = followup({ approve: () => { throw new ProcessApiError(409, '합성 기준판 충돌', 'PROCESS_HEAD_CONFLICT'); } });
  Object.assign(h.live.operation, { stage: 'APPLIED', change_id: upgradeRetry.change_id, permitted_actions: [],
    upgrade: copy(pendingUpgrade) });
  await openedOperation(h);
  await h.flow.retryActivation();
  assert.equal(h.flow.getSnapshot().error.reasonCode, 'PROCESS_HEAD_CONFLICT');
  const other = followup();
  const { retry: _retry, ...withoutRetry } = pendingUpgrade;
  Object.assign(other.live.operation, { stage: 'APPLIED', change_id: upgradeRetry.change_id, permitted_actions: [],
    upgrade: copy(withoutRetry) });
  await openedOperation(other);
  await other.flow.retryActivation();
  assert.equal(writeCalls(other).length, 0);
  assert.equal(other.flow.getSnapshot().error.status, 409);
});

test('업그레이드 SSR: 활성화 대기는 사유와 (승인자에게만) 재시도 버튼 / 승인 대기는 현재 판본 유지 안내', async () => {
  const h = followup(); await h.flow.load();
  const pendingHtml = renderUpgrade(h, pendingUpgrade);
  assert.ok(pendingHtml.includes('판본 업그레이드 1.1.0 → 1.2.0'));
  assert.ok(pendingHtml.includes('마지막 활성화 실패 사유: PROCESS_STORAGE_UNAVAILABLE'));
  assert.ok(pendingHtml.includes('>같은 승인으로 활성화 다시 시도</button>'));
  const { retry: _retry, ...withoutRetry } = pendingUpgrade;
  const othersHtml = renderUpgrade(h, withoutRetry);
  assert.ok(!othersHtml.includes('</button>'));
  assert.ok(othersHtml.includes('이 승인을 한 승인자만'));
  const waitingHtml = renderUpgrade(h, { ...withoutRetry, activation: 'AWAITING_APPROVAL', activation_error: undefined });
  assert.ok(waitingHtml.includes('승인 전까지 현재 판본이 그대로 활성입니다'));
  assert.ok(!waitingHtml.includes('</button>') && !waitingHtml.includes('실패 사유'));
});

const passedCases = [];
let failed = false;
globalThis.fetch = async () => { throw new Error('격리 시험: 실제 네트워크 요청 금지'); };
try {
  for (const { name, work } of cases) {
    await work();
    passedCases.push(name);
    process.stdout.write(`PASS ${name}\n`);
  }
  process.stdout.write(`ProcessInstallation: ${cases.length} cases passed; SYNTHETIC / 모의 API, 실제 서버·브라우저 검증 아님\n`);
  process.stdout.write(`STATIC 소스 계약 ${cases.filter((item) => item.name.startsWith('STATIC:')).length}건은 별도 포함; 실제 DOM·focus 검증 아님\n`);
} catch (error) {
  failed = true;
  throw error;
} finally {
  globalThis.fetch = originalFetch;
  const afterHashes = sourceHashes();
  const sourcesUnchanged = JSON.stringify(beforeHashes) === JSON.stringify(afterHashes);
  fs.mkdirSync(new URL('../../output/', import.meta.url), { recursive: true });
  const reportDir = new URL(`../../output/process-installation-check-${randomUUID()}/`, import.meta.url);
  fs.mkdirSync(reportDir, { recursive: false });
  fs.writeFileSync(new URL('report.json', reportDir), JSON.stringify({
    status: !failed && sourcesUnchanged && passedCases.length === cases.length ? 'PASS' : 'FAIL',
    started_at: startedAt, elapsed_ms: performance.now() - startedMs,
    selected: cases.length, passed: passedCases.length, passed_cases: passedCases,
    source_hashes_before: beforeHashes, source_hashes_after: afterHashes,
    sources_unchanged: sourcesUnchanged, scope: 'SYNTHETIC_API_UNIT_AND_REACT_SSR',
    validation_counts: { synthetic_unit_or_ssr: cases.filter((item) => !item.name.startsWith('STATIC:')).length,
      static_source_contract: cases.filter((item) => item.name.startsWith('STATIC:')).length },
    static_source_contract: { passed: passedCases.filter((name) => name.startsWith('STATIC:')).length,
      scope: 'SOURCE_TEXT_ONLY', dom_and_focus_behavior: 'NOT_RUN' },
    real_browser: 'NOT_RUN',
  }, null, 2), { flag: 'wx' });
  process.stdout.write(`증거: ${reportDir.pathname}report.json\n`);
  if (!sourcesUnchanged) throw new Error('시험 도중 프런트 소스가 변경되었습니다.');
}
