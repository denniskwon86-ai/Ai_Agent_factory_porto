// B5 영향 범위만 검사한다. 네트워크는 메모리 대역, SSR은 실제 브라우저가 아니다.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { createHash, randomUUID, webcrypto } from 'node:crypto';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const files = ['../src/factory/studioNextAction.ts', '../src/factory/studioInputMemory.ts',
  '../src/factory/sprintActions.ts', '../src/store/useFactoryStore.ts', '../src/factory/RunControls.tsx',
  '../src/factory/ProjectHeader.tsx', '../src/factory/AdaptiveProductionStudio.tsx',
  '../src/factory/factoryViewModel.ts', '../tests/studio-transition.fixture.tsx',
  '../src/factory/WbsSpine.tsx', '../src/factory/studio.css', '../src/factory/StudioInputDraftControls.tsx',
  '../src/lib/studioInputDraftApi.ts', '../src/lib/contractReviewApi.ts',
  '../src/factory/studioDecisionApi.ts', '../src/factory/studioDecisionFlow.ts',
  '../src/factory/StudioDecisionPanel.tsx', '../src/factory/DecisionJarvisDock.tsx',
  '../src/lib/studioRequirementDraft.ts', '../src/lib/processInstallationApi.ts',
  '../src/factory/RevisionRequestEditor.tsx',
  '../src/lib/kitContractReviewApi.ts', '../src/lib/kitContractReviewFlow.ts',
  '../src/lib/studioRevisionApi.ts', '../src/lib/studioRevisionFlow.ts',
  '../src/lib/studioExecutionApi.ts',
  '../src/factory/StudioExecutionRequests.tsx',
  '../src/components/KitContractReview.tsx',
  '../src/components/KitAppPanel.tsx', '../src/components/KitOperationsPanel.tsx',
  './check-studio-contracts.mjs'];
const hashes = () => Object.fromEntries(files.map(f => [f, createHash('sha256').update(fs.readFileSync(new URL(f, import.meta.url))).digest('hex')]));
const before = hashes();
const start = performance.now();
const results = [];
function load(file, deps = {}) {
  const url = new URL(file, import.meta.url);
  const js = ts.transpileModule(fs.readFileSync(url, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  } }).outputText;
  const mod = { exports: {} };
  const native = createRequire(url);
  new Function('module', 'exports', 'require', js)(mod, mod.exports, name => {
    if (Object.hasOwn(deps, name)) return deps[name];
    if (['react', 'react/jsx-runtime', 'zustand'].includes(name)) return native(name);
    throw new Error(`검사 허용 목록 밖 import: ${name}`);
  });
  return mod.exports;
}
async function test(name, fn) {
  try { await fn(); results.push({ name, result: 'PASS' }); }
  catch (error) { results.push({ name, result: 'FAIL', error: String(error?.stack || error) }); }
}
let identity = { token: 'SYNTHETIC_TOKEN', user: 'SYNTHETIC_USER', tenantId: 'SYNTHETIC_TENANT', scopeNodeId: 'SYNTHETIC_SCOPE_A', entityMode: 'REAL' };
const api = { API_BASE_URL: 'https://synthetic.invalid', getActingUser: () => identity.user,
  getSessionToken: () => identity.token, getEnterpriseContext: () => identity };
let calls = [];
let reply = async () => { throw new Error('대역 응답 미지정'); };
globalThis.fetch = async (url, options = {}) => { calls.push({ url, options }); return reply(url, options); };
api.apiFetch = (...args) => globalThis.fetch(...args);
const next = load('../src/factory/studioNextAction.ts');
const memory = load('../src/factory/studioInputMemory.ts', { '../lib/api': api });
const syntheticIdentity = { token: 'SYNTHETIC_TOKEN', user: 'SYNTHETIC_USER', tenantId: 'SYNTHETIC_TENANT',
  scopeNodeId: 'SYNTHETIC_SCOPE_A', entityMode: 'REAL' };
function resetMemory() { identity = { ...syntheticIdentity }; memory.studioInputMemory.clearAll(); memory.studioIdentityKey(); }
// 실행 영수증도 실제 SHA-256·메모리를 쓴다. HTTP 대역 외에 지속 잠금을 우회하는 대역은 두지 않는다.
if (!globalThis.crypto?.subtle) Object.defineProperty(globalThis, 'crypto', { value: webcrypto, configurable: true });
const executionApi = load('../src/lib/studioExecutionApi.ts', { './api': api, '../factory/studioInputMemory': memory });
const actions = load('../src/factory/sprintActions.ts', { '../lib/api': api, '../lib/studioExecutionApi': executionApi });
const factory = load('../src/store/useFactoryStore.ts', { '../lib/api': api, '../factory/sprintActions': actions,
  '../lib/studioExecutionApi': executionApi });
const draftApi = load('../src/lib/studioInputDraftApi.ts', { './api': api, '../factory/studioInputMemory': memory });
const revisionApi = load('../src/lib/studioRevisionApi.ts', {
  './api': api, '../factory/studioInputMemory': memory, './studioInputDraftApi': draftApi });
const revisionFlow = load('../src/lib/studioRevisionFlow.ts', {
  '../factory/studioInputMemory': memory, './studioInputDraftApi': draftApi, './studioRevisionApi': revisionApi });
const draftControls = load('../src/factory/StudioInputDraftControls.tsx', { '../lib/studioInputDraftApi': draftApi, './studioInputMemory': memory });
const revisionEditor = load('../src/factory/RevisionRequestEditor.tsx', {
  '../lib/studioInputDraftApi': draftApi, './StudioInputDraftControls': draftControls, './studioInputMemory': memory,
  '../lib/studioRevisionApi': revisionApi, '../lib/studioRevisionFlow': revisionFlow });
const executionUi = load('../src/factory/StudioExecutionRequests.tsx', {
  '../lib/studioExecutionApi': executionApi, './studioInputMemory': memory });
const run = load('../src/factory/RunControls.tsx', { '../store/useFactoryStore': factory,
  './sprintActions': actions, './studioNextAction': next, './studioInputMemory': memory,
  './StudioInputDraftControls': draftControls, './RevisionRequestEditor': revisionEditor,
  '../lib/studioExecutionApi': executionApi, './StudioExecutionRequests': executionUi });
const header = load('../src/factory/ProjectHeader.tsx', { '../store/useFactoryStore': factory,
  './studioInputMemory': memory, '../lib/studioExecutionApi': executionApi, './StudioExecutionRequests': executionUi });
const reviewApi = load('../src/lib/contractReviewApi.ts', { './api': api });
const decisionApi = load('../src/factory/studioDecisionApi.ts', {
  '../lib/api': api, '../lib/contractReviewApi': reviewApi, './studioInputMemory': memory });
const decisionFlow = load('../src/factory/studioDecisionFlow.ts', {
  './studioDecisionApi': decisionApi, './studioInputMemory': memory });
const clarify = load('../src/factory/clarifyAnswers.ts', {});
const processApi = load('../src/lib/processInstallationApi.ts', { './api': api });
const kitReviewApi = load('../src/lib/kitContractReviewApi.ts', {
  './api': api, '../factory/studioInputMemory': memory });
const kitReviewFlow = load('../src/lib/kitContractReviewFlow.ts', {
  './kitContractReviewApi': kitReviewApi, '../factory/studioInputMemory': memory });
const kitReviewUi = load('../src/components/KitContractReview.tsx', {
  '../lib/kitContractReviewApi': kitReviewApi, '../lib/kitContractReviewFlow': kitReviewFlow,
  '../factory/studioInputMemory': memory });
// 요구초안은 실제 helper/오류/unwrap을 쓴다. access/resolved만 합성 읽기 대역이다.
let requirementReadWorld = null;
const requirements = load('../src/lib/studioRequirementDraft.ts', {
  './api': api,
  './processInstallationApi': { ...processApi, createProcessInstallationApi: capturedIdentity => ({
    access: async companyWide => {
      assert.equal(companyWide, false); assert.equal(capturedIdentity, processApi.processContextIdentity());
      requirementReadWorld.reads.push('access'); return structuredClone(requirementReadWorld.access);
    },
    resolved: async boundary => {
      assert.equal(capturedIdentity, processApi.processContextIdentity());
      assert.deepEqual(boundary, requirementReadWorld.access.boundary);
      requirementReadWorld.reads.push('resolved'); return structuredClone(requirementReadWorld.resolved);
    },
  }) },
});
const base = { project: { id: 'synthetic_project', name: '원료 구매 앱', mode: 'PLANNING', cost: null },
  stages: [], selectedStageId: '', currentStageId: '', wbs: [], decisions: [], artifacts: [], events: [],
  connection: 'connected', loadState: 'ready', loadReason: '', stageSourceKnown: true,
  clarify: { awaiting: false, questions: [], summary: '', initialIdea: '' }, generated: { rawCode: '', runnable: false, building: false },
  inspect: { nextStage: null, blocked: [], failure: null, healingRetries: 0, suspendedTaskId: '' }, docs: {}, releases: [],
  run: { active: false, sprintId: '', wbsDone: 0, wbsTotal: 0, label: '대기' } };
const withVm = patch => ({ ...structuredClone(base), ...patch });
const response = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

// 합성 서버 영수증만 만든다. 제품 검증 함수를 오라클로 재사용하지 않는다.
function executionCanonical(value) {
  if (Array.isArray(value)) return '[' + value.map(executionCanonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([key, item]) => JSON.stringify(key) + ':' + executionCanonical(item)).join(',') + '}';
  return JSON.stringify(value);
}
function executionHash(value) { return createHash('sha256').update(executionCanonical(value)).digest('hex'); }
function sealExecutionReceipt(receipt) {
  const { receipt_digest: _ignored, ...unsigned } = structuredClone(receipt);
  return { ...unsigned, receipt_digest: executionHash(unsigned) };
}
function executionReceipt(projectId, command, patch = {}) {
  const statuses = { START: 'started', RESUME: 'resumed', RESUME_QUOTA: 'resumed', PAUSE: 'paused', STOP: 'stopped',
    HEAL: 'healing_started', RELEASE: 'success', REPLAN: 'started' };
  const resultTaskId = command.operation === 'HEAL'
    ? 'TASK_REV_HEAL_' + command.client_request_id.replaceAll('-', '') : command.task_id;
  // [B5] 프로젝트 단위 명령은 요청 task_id('PROJECT')와 다른 결과를 준다.
  const response = command.operation === 'RELEASE'
    ? { status: 'success', release_id: 'rel-synthetic-1', note: '릴리스 저장 응답' }
    : command.operation === 'REPLAN' ? { status: 'started', task_id: 'TASK_REPLANNED_1' }
    : { status: statuses[command.operation], task_id: resultTaskId };
  return sealExecutionReceipt({ request_id: command.client_request_id, project_id: projectId, actor_id: identity.user,
    operation: command.operation, task_id: command.task_id, input: structuredClone(command.input), command_digest: executionHash(command),
    status: 'ACCEPTED', result: { http_status: 200, response },
    created_at: '2026-09-13T13:00:00.000Z', updated_at: '2026-09-13T13:00:00.000Z', ...patch });
}
function executionWorld(projectId = 'SYNTHETIC_EXECUTION') {
  resetMemory();
  // 모듈의 읽기 캐시도 실제 문맥 전환 계약으로 비운다. 지속 잠금 대역은 쓰지 않는다.
  identity.scopeNodeId = 'SYNTHETIC_EXECUTION_RESET'; executionApi.getExecutionRecords(projectId);
  identity.scopeNodeId = syntheticIdentity.scopeNodeId; executionApi.getExecutionRecords(projectId);
  calls = [];
  const world = { projectId, receipts: new Map(), post: null, read: null, list: null };
  world.commit = (command, patch = {}) => {
    const receipt = executionReceipt(projectId, command, patch);
    world.receipts.set(command.client_request_id, receipt); return receipt;
  };
  const basePath = '/api/v1/factory/' + encodeURIComponent(projectId) + '/execution-commands';
  reply = async (url, options) => {
    const path = new URL(url, api.API_BASE_URL).pathname, method = options.method || 'GET';
    if (method === 'POST' && path === basePath) {
      const command = JSON.parse(options.body);
      return world.post ? world.post(command) : response({ request: world.commit(command) });
    }
    if (method === 'GET' && path === basePath) return world.list ? world.list()
      : response({ requests: [...world.receipts.values()] });
    if (method === 'GET' && path.startsWith(basePath + '/')) {
      const id = decodeURIComponent(path.slice(basePath.length + 1));
      return world.read ? world.read(id) : world.receipts.has(id)
        ? response({ request: world.receipts.get(id) }) : response({ detail: '합성 기록 없음' }, 404);
    }
    throw new Error('합성 실행 검사 허용 밖 HTTP: ' + method + ' ' + path);
  };
  return world;
}

for (const [name, patch, expected] of [
  ['요구 입력', {}, 'planning'], ['비가시', { loadState: 'forbidden' }, 'blocked'],
  ['읽기 실패', { loadState: 'error' }, 'refresh'], ['연결 불명', { connection: 'offline' }, 'refresh'],
  ['결정 우선', { decisions: [{ id: 'task' }], run: { ...base.run, active: true } }, 'decision'],
  ['한도 재개', { inspect: { ...base.inspect, suspendedTaskId: 'task' } }, 'quota'],
  ['제작 중', { run: { ...base.run, active: true } }, 'running'],
  ['복구 안내', { inspect: { ...base.inspect, failure: { taskId: 'task', error: '실패' } } }, 'heal'],
  ['작업 시작', { wbs: [{ id: 'task', title: '입고 입력', kind: 'waiting' }] }, 'task'],
  ['결과 확인', { docs: { PLANNING: { text: '기획 결과' } } }, 'result'],
  ['선행 조건', { wbs: [{ id: 'task', kind: 'blocked' }] }, 'blocked'],
]) await test(`CTA ${name}`, () => assert.equal(next.studioNextAction(withVm(patch)).kind, expected));
await test('과거 화면 선택은 실행 대상을 바꾸지 않음', () => {
  const vm = withVm({ selectedStageId: 'OLD', wbs: [{ id: 'current-task', kind: 'waiting' }] });
  assert.equal(next.studioNextAction(vm).taskId, 'current-task');
});
await test('입력 동일 문맥 왕복 보존 및 복제', () => {
  const k = memory.studioInputKey('p', 'comment', 'round1');
  memory.studioInputMemory.set(k, { text: '의견' });
  const value = memory.studioInputMemory.get(k, {}); value.text = '변조';
  assert.equal(memory.studioInputMemory.get(k, {}).text, '의견');
  identity.scopeNodeId = 'SYNTHETIC_SCOPE_B';
  assert.deepEqual(memory.studioInputMemory.get(memory.studioInputKey('p', 'comment', 'round1'), {}), {});
  identity.scopeNodeId = 'SYNTHETIC_SCOPE_A';
  assert.equal(memory.studioInputMemory.get(k, {}).text, '의견');
});
await test('새 결정 차수에 이전 입력 없음', () => assert.deepEqual(memory.studioInputMemory.get(memory.studioInputKey('p', 'comment', 'round2'), {}), {}));
await test('사용자 변경 시 이전 입력 폐기', () => {
  const k = memory.studioInputKey('p', 'comment', 'round1'); identity.token = 'SYNTHETIC_OTHER';
  assert.deepEqual(memory.studioInputMemory.get(k, {}), {}); identity.token = 'SYNTHETIC_TOKEN';
  assert.deepEqual(memory.studioInputMemory.get(k, {}), {});
});
await test('기존 작업 payload 보호 필드 미전송', () => {
  const payload = actions.buildExistingTaskPayload('p', 'TASK_1', { schema_version: 9, process_context: { forged: true }, initial_idea: '요구' });
  assert.equal(payload.factory_mode, 'EXECUTION'); assert.equal(payload.schema_version, undefined); assert.equal(payload.process_context, undefined);
  assert.equal(actions.buildExistingTaskPayload('p', 'TASK_REV_1').factory_mode, 'REVISION');
});
await test('기획 접수·모드 및 대상', async () => {
  executionWorld('p');
  const r = await actions.startPlanning('p', '요구', '', 'PLANNING_123');
  assert.equal(r.outcome, 'CONFIRMED'); assert.equal(r.ok, true);
  assert.deepEqual(calls.map(call => call.options.method || 'GET'), ['POST', 'GET']);
  const body = JSON.parse(calls[0].options.body);
  assert.deepEqual(body, { client_request_id: r.requestId, operation: 'START', task_id: 'PLANNING_123', input: { initial_idea: '요구', master_data: '' } });
  assert.ok(calls[1].url.endsWith('/execution-commands/' + r.requestId));
  assert.equal(actions.buildPlanningPayload('p', '요구', '').factory_mode, 'PLANNING');
});
await test('HTTP 403은 명시 거절', async () => { resetMemory(); calls = []; reply = async () => response({ detail: { message: '권한 없음', reason_code: 'DENIED' } }, 403); assert.equal((await actions.startExistingTask('p', 'TASK_1')).outcome, 'REJECTED'); });
await test('응답 유실은 UNKNOWN·단일 요청', async () => { resetMemory(); calls = []; reply = async () => { throw new Error('응답 유실'); }; assert.equal((await actions.startExistingTask('p', 'TASK_1')).outcome, 'UNKNOWN'); assert.equal(calls.length, 1); });
await test('성공처럼 보이는 손상 응답은 UNKNOWN', async () => { resetMemory(); calls = []; reply = async () => response({}); assert.equal((await actions.startExistingTask('p', 'TASK_1')).outcome, 'UNKNOWN'); });
await test('한도 재개는 일반 재개와 다른 명령·원 키 영수증 조회', async () => {
  executionWorld('p');
  const result = await actions.resumeAfterQuota('p', 'TASK_1');
  assert.equal(result.outcome, 'CONFIRMED'); assert.match(calls[0].url, /execution-commands$/);
  assert.deepEqual(JSON.parse(calls[0].options.body), { client_request_id: result.requestId, operation: 'RESUME_QUOTA', task_id: 'TASK_1', input: {} });
  assert.deepEqual(calls.map(call => call.options.method || 'GET'), ['POST', 'GET']);
});
await test('중단 거절 후 원 task·HOTL 보존', async () => {
  resetMemory(); calls = [];
  factory.useFactoryStore.setState({ currentProjectId: 'p', activeSprintId: 'TASK_1', hotlTaskId: 'TASK_1', isConnected: true });
  reply = async () => response({ detail: '거절' }, 403);
  const r = await factory.useFactoryStore.getState().stopSprint('p', 'TASK_1');
  assert.equal(r.outcome, 'REJECTED'); assert.equal(factory.useFactoryStore.getState().activeSprintId, 'TASK_1'); assert.equal(factory.useFactoryStore.getState().hotlTaskId, 'TASK_1');
});
await test('중단 늦은 응답이 새 프로젝트를 변경하지 않음', async () => {
  const world = executionWorld('p');
  factory.useFactoryStore.setState({ currentProjectId: 'p', activeSprintId: 'TASK_1', hotlTaskId: 'TASK_1', isConnected: true });
  const entered = deferred(), finish = deferred();
  world.post = async command => {
    const receipt = world.commit(command);
    entered.resolve(); await finish.promise; return response({ request: receipt });
  };
  const promise = factory.useFactoryStore.getState().stopSprint('p', 'TASK_1');
  try {
    await bounded(entered.promise);
    assert.equal(calls.filter(call => call.options.method === 'POST').length, 1);
    factory.useFactoryStore.setState({ currentProjectId: 'q', activeSprintId: 'TASK_2', hotlTaskId: null });
  } finally { finish.resolve(); await bounded(promise); }
  assert.equal(factory.useFactoryStore.getState().activeSprintId, 'TASK_2');
});
await test('실제 RunControls SSR 대표 행동·추가 작업 구분', () => {
  factory.useFactoryStore.setState({ currentProjectId: base.project.id });
  const html = renderToStaticMarkup(React.createElement(run.RunControls, { vm: base }));
  assert.match(html, /어떤 일을 쉽게 만들고 싶으세요/); assert.match(html, /<details/); assert.match(html, /검토용 버전 저장/);
  assert.doesNotMatch(html, />기획 가동</);
});
await test('실제 Header SSR 일시정지·중단 분리', () => {
  const html = renderToStaticMarkup(React.createElement(header.ProjectHeader, { vm: base, onReviewResult() {} }));
  assert.match(html, /일시정지/); assert.match(html, /제작 중단/); assert.match(html, /작업 준비/);
});

// 기존 25개 기능 검사와 마지막 소스 불변 검사(총 26개)는 그대로 유지한다.
const originalFunctionalChecks = results.length;
const roundId = 'a'.repeat(64);
const secondRoundId = 'b'.repeat(64);
const contractFingerprint = 'c'.repeat(64);
const emptyQuestionsDigest = createHash('sha256').update('[]').digest('hex');
const writes = suffix => calls.filter(call => call.options.method === 'POST' && (!suffix || call.url.endsWith(suffix)));
const bodyOf = call => JSON.parse(call.options.body);
function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; }
async function bounded(promise) {
  let timer;
  try { return await Promise.race([promise, new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('합성 비동기 경계가 2.5초 안에 도착하지 않음')), 2500);
  })]); } finally { clearTimeout(timer); }
}
function recordOf(flow, kind) {
  const row = Object.values(flow.getSnapshot().records).find(value => value.kind === kind);
  assert.ok(row, kind + ' 처리/입력 기록 필요'); return row;
}
function pendingHost() {
  return { pending: true, actionable: true, verdict: 'REVIEW_REQUIRED', reason: '합성 검토',
    request_event_id: 'request-1', compiled_fingerprint: contractFingerprint };
}
function capabilityRow() {
  return { decision_kind: 'CAPABILITY', decision_request_id: 'cdr_' + roundId, expected_digest: roundId,
    round_status: 'PENDING', task_id: 'TASK_1', capability: 'synthetic.capability',
    choices: ['REDUCE', 'WAIT'], reason: '합성 지원 제약' };
}
function pendingCapabilities(row) {
  return { pending: true, capability_decisions: row.decision_kind === 'DATASET' ? [] : [row],
    dataset_conflicts: row.decision_kind === 'DATASET' ? [row] : [], other_errors: [], round_metadata_status: 'READY' };
}
async function decisionWorld(patch = {}) {
  resetMemory(); calls = [];
  const world = {
    hotl: { status: 'success', hotl_task_id: 'TASK_1', hotl_context: {
      status: 'PENDING', pending: true, available: true, decision_kind: 'GENERAL_HOTL',
      request_id: roundId, questions_digest: emptyQuestionsDigest, reason_code: 'HOTL_PENDING' } },
    host: { pending: false, verdict: 'NOT_REQUIRED', reason: '' },
    capabilities: { pending: false, capability_decisions: [], dataset_conflicts: [], other_errors: [], round_metadata_status: 'READY' },
    hostApplied: true, handlers: {}, ...patch,
  };
  reply = async (url, options) => {
    const parsed = new URL(url, api.API_BASE_URL);
    const route = parsed.pathname.replace('/api/v1/factory/p', '');
    const method = options.method || 'GET';
    const body = options.body ? JSON.parse(options.body) : null;
    if (world.handlers[method + ' ' + route]) return world.handlers[method + ' ' + route](body, parsed);
    if (method === 'GET' && route === '/hotl/check') return response(world.hotl);
    if (method === 'GET' && route === '/contract-review/pending') {
      assert.equal(parsed.searchParams.get('task_id'), 'TASK_1');
      return response({ status: 'success', data: world.host });
    }
    if (method === 'GET' && route === '/contract-decisions/pending') return response({ status: 'success', data: world.capabilities });
    if (method === 'POST' && route === '/hotl/resume') return response({ status: 'resumed', task_id: body.task_id });
    if (method === 'POST' && route === '/contract-review/decision') return response({ status: 'success', data: {
      decision: body.decision, event_id: 'event-1', request_event_id: body.request_event_id,
      contract_fingerprint: world.host.compiled_fingerprint, state_applied: world.hostApplied } });
    if (method === 'POST' && route === '/contract-review/reconcile') return response({ status: 'success', data: {
      event_id: body.event_id, request_event_id: body.request_event_id, contract_fingerprint: body.compiled_fingerprint,
      state_applied: true, execution_started: false, reason_code: 'APPLIED' } });
    if (method === 'POST' && route === '/contract-decisions/resolve') return response({ status: 'success', data: {
      decision_request_id: body.decision_request_id, expected_digest: body.expected_digest,
      event_id: 'cap-event-1', draft_applied: true } });
    throw new Error('미지정 합성 결정 요청: ' + method + ' ' + route);
  };
  const client = decisionApi.createStudioDecisionApi('p');
  const flow = decisionFlow.createStudioDecisionFlow('p', client, 'TASK_1');
  flow.activate(); await flow.load();
  return { world, client, flow };
}

await test('결정 실제 API 조회는 세 종류 GET뿐이며 POST 없음', async () => {
  const { flow } = await decisionWorld();
  assert.equal(flow.getSnapshot().loaded, true); assert.equal(calls.length, 3); assert.equal(writes().length, 0);
  assert.ok(calls.some(call => call.url.includes('/contract-review/pending?task_id=TASK_1')));
  assert.ok(calls.some(call => call.url.endsWith('/contract-decisions/pending')));
});
await test('HOTL 실제 Flow 원 차수·지문 제출 및 접수 후 재결정 차단', async () => {
  const { flow } = await decisionWorld();
  await flow.resume('검토 의견'); await flow.resume('두 번째 의견');
  assert.equal(writes().length, 1);
  assert.deepEqual(bodyOf(writes()[0]), { task_id: 'TASK_1', feedback: '검토 의견',
    expected_request_id: roundId, expected_questions_digest: emptyQuestionsDigest });
  assert.equal(recordOf(flow, 'HOTL').outcome, 'CONFIRMED');
});
await test('B5 STATIC 원키 재조회가 화면에 실제로 배선돼 있다', () => {
  // ⚠️ flow 에 메서드만 만들고 화면에 붙이지 않으면 UNIT 은 초록인데 사용자는 쓸 수 없다.
  //    이 저장소가 반복해 겪은 「생산자→소비자 배선 누락」이라 소스로 잠근다(실제 클릭 아님).
  const panel = fs.readFileSync(new URL('../src/factory/StudioDecisionPanel.tsx', import.meta.url), 'utf8');
  assert.match(panel, /flow\.recheckSubmission\(/);
  // 접수를 확인한 뒤에만 채워지는 eventId 로는 응답 유실 상황을 못 연다. 보존된 원키를 쓴다.
  assert.match(panel, /record\.body\?\.client_request_id/);
  assert.doesNotMatch(panel, /recheckSubmission\([^)]*record\.eventId/);
  // 누를 수 없는 이유를 읽어 줄 설명이 붙어 있어야 한다.
  assert.match(panel, /aria-describedby=\{`\$\{record\.key\}-recheck-why`\}/);
});

// ── [B5] 명확화 답변 본문 형식 잠금 ──────────────────────────────────────────
// ⚠️ 조합 규칙이 화면과 서버(`core/clarify_answers.py`) 두 곳에 있다. 아래 예제는 서버
//    시험(`tests/test_b5_clarify_answers.py`)의 GOLDEN 과 **같은 값**이어야 한다.
//    형식을 바꾸면 양쪽 예제를 함께 고쳐야 한다 — 한쪽만 고치면 이 잠금은 잡지 못한다.
await test('B5 명확화 본문 형식은 서버 재현과 같은 고정 예제를 지킨다', async () => {
  const questions = [
    { id: 'q1', question: '원료 도입 주기를 어떻게 잡습니까?',
      options: [{ label: '월 1회', description: '재고 부담이 크다' }, { label: '주 1회' }] },
    { id: 'q2', question: '품질 기준을 누가 정합니까?', multi: true,
      options: [{ label: '품질팀' }, { label: '생산팀' }] },
  ];
  const golden = ['[요구 확인 인터뷰 답변]', '1. 원료 도입 주기를 어떻게 잡습니까?',
    '→ 선택: 월 1회 (재고 부담이 크다)', '2. 품질 기준을 누가 정합니까?',
    '→ 선택 없음 (전문가 추천안대로 진행)', '', '[추가 의견]', '추가로 확인할 것이 있습니다.'].join('\n');
  assert.equal(clarify.serializeClarifyAnswers(questions, { q1: ['월 1회'] }, '  추가로 확인할 것이 있습니다.  '), golden);
  // 고른 항목의 출력 순서는 선택 순서가 아니라 선택지 순서다. 서버 재현도 같은 규칙이다.
  assert.equal(clarify.serializeClarifyAnswers(
    [{ id: 'q', question: '누가?', multi: true, options: [{ label: '가' }, { label: '나' }, { label: '다' }] }],
    { q: ['다', '가'] }, ''), '[요구 확인 인터뷰 답변]\n1. 누가?\n→ 선택: 가\n→ 선택: 다');
});

// ── [B5] 일반 HOTL 저장 초안 결속 ────────────────────────────────────────────
const hotlDraftRef = { draft_id: 'sid_b5hotl', revision: 2, digest: 'd'.repeat(64) };
const hotlReceipt = (patch = {}) => ({ request_id: '', task_id: 'TASK_1', status: 'ACCEPTED',
  input_draft: { ...hotlDraftRef }, created_at: '2026-09-14T00:00:00+00:00',
  updated_at: '2026-09-14T00:00:00+00:00', receipt_digest: 'e'.repeat(64), ...patch });
function boundResume(world, patch = {}) {
  world.handlers['POST /hotl/resume'] = async body => response({ status: 'resumed', task_id: body.task_id,
    submission: hotlReceipt({ request_id: body.client_request_id, ...patch }) });
}
await test('B5 결속 제출은 원키·저장 초안 판을 함께 싣고 접수 확인만 소비 근거로 남긴다', async () => {
  const { flow, world } = await decisionWorld();
  boundResume(world);
  await flow.resume('결속 의견', undefined, { ...hotlDraftRef });
  assert.equal(writes().length, 1);
  const sent = bodyOf(writes()[0]);
  assert.deepEqual(sent.input_draft, hotlDraftRef);
  assert.match(sent.client_request_id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  const record = recordOf(flow, 'HOTL');
  assert.equal(record.outcome, 'CONFIRMED');
  // 접수 확인된 제출만 초안을 닫을 근거가 된다. 접수는 가동·완료가 아니다.
  assert.equal(record.eventId, sent.client_request_id);
});
await test('B5 초안 참조 없는 제출은 결속하지 않고 소비 근거도 남기지 않는다', async () => {
  const { flow, world } = await decisionWorld();
  boundResume(world);
  await flow.resume('결속 없는 의견');
  const sent = bodyOf(writes()[0]);
  assert.equal('client_request_id' in sent, false); assert.equal('input_draft' in sent, false);
  assert.equal(recordOf(flow, 'HOTL').eventId, undefined);
});
await test('B5 명확화도 초안 참조를 실어 보낸다 — 본문 대조는 서버가 접수 시점에 한다', async () => {
  const { flow, world } = await decisionWorld({ hotl: { status: 'success', hotl_task_id: 'TASK_1', hotl_context: {
    status: 'PENDING', pending: true, available: true, decision_kind: 'CLARIFICATION',
    request_id: roundId, questions_digest: emptyQuestionsDigest, reason_code: 'HOTL_PENDING' } } });
  boundResume(world);
  await flow.resume('답변', { rawQuestions: [], displayedQuestions: [] }, { ...hotlDraftRef });
  assert.equal(writes().length, 1);
  const sent = bodyOf(writes()[0]);
  assert.deepEqual(sent.input_draft, hotlDraftRef);
  assert.equal(recordOf(flow, 'HOTL').eventId, sent.client_request_id);
});
await test('B5 접수 기록이 없거나 요청과 다르면 소비 근거로 쓰지 않는다', async () => {
  for (const [label, patch] of [['없음', null], ['다른 초안', { input_draft: { ...hotlDraftRef, revision: 9 } }]]) {
    const { flow, world } = await decisionWorld();
    world.handlers['POST /hotl/resume'] = async body => response(patch === null
      ? { status: 'resumed', task_id: body.task_id }
      : { status: 'resumed', task_id: body.task_id, submission: hotlReceipt({ request_id: body.client_request_id, ...patch }) });
    await flow.resume('결속 의견', undefined, { ...hotlDraftRef });
    assert.equal(flow.getSnapshot().error.reasonCode, 'DECISION_RESPONSE_INVALID', label);
    // 결과를 확정하지 못했으므로 원 본문을 보존하고 닫지 않는다.
    assert.equal(recordOf(flow, 'HOTL').outcome, 'UNKNOWN', label);
  }
});
await test('B5 응답 유실 뒤 원키 조회는 재전송 없이 서버 상태만 읽는다', async () => {
  const { flow, world } = await decisionWorld();
  world.handlers['POST /hotl/resume'] = async () => { throw new Error('합성 응답 유실'); };
  await flow.resume('보존할 결속 의견', undefined, { ...hotlDraftRef });
  const sent = bodyOf(writes()[0]);
  assert.equal(recordOf(flow, 'HOTL').outcome, 'UNKNOWN');
  const subject = decisionFlow.hotlSubject(flow.getSnapshot().hotl);
  world.handlers[`GET /hotl/submissions/${sent.client_request_id}`] = async () =>
    response({ submission: hotlReceipt({ request_id: sent.client_request_id }) });
  const receipt = await flow.recheckSubmission(subject, sent.client_request_id);
  assert.equal(receipt.status, 'ACCEPTED');
  assert.equal(writes().length, 1);  // 재전송 0
  assert.equal(recordOf(flow, 'HOTL').eventId, sent.client_request_id);
});
await test('B5 원키 조회가 미접수 상태면 그 사실을 그대로 표시한다', async () => {
  const { flow, world } = await decisionWorld();
  world.handlers['POST /hotl/resume'] = async () => { throw new Error('합성 응답 유실'); };
  await flow.resume('보존할 결속 의견', undefined, { ...hotlDraftRef });
  const sent = bodyOf(writes()[0]);
  const subject = decisionFlow.hotlSubject(flow.getSnapshot().hotl);
  world.handlers[`GET /hotl/submissions/${sent.client_request_id}`] = async () =>
    response({ submission: hotlReceipt({ request_id: sent.client_request_id, status: 'UNKNOWN' }) });
  const receipt = await flow.recheckSubmission(subject, sent.client_request_id);
  assert.equal(receipt.status, 'UNKNOWN');
  assert.match(recordOf(flow, 'HOTL').message, /UNKNOWN/);
  assert.equal(writes().length, 1);
});

await test('새 HOTL 차수는 구판 입력으로 제출하지 않고 원 입력 보존', async () => {
  const { flow, world } = await decisionWorld();
  const subject = decisionFlow.hotlSubject(flow.getSnapshot().hotl);
  flow.edit('HOTL', subject, 'note', '원 차수 의견');
  world.hotl.hotl_context.request_id = secondRoundId;
  await flow.resume('원 차수 의견');
  assert.equal(writes().length, 0); assert.equal(flow.getSnapshot().error.reasonCode, 'DECISION_ROUND_STALE');
  assert.equal(recordOf(flow, 'HOTL').note, '원 차수 의견');
  await flow.load();
  const newKey = flow.keyFor('HOTL', decisionFlow.hotlSubject(flow.getSnapshot().hotl));
  assert.equal(flow.getSnapshot().records[newKey], undefined);
});
await test('UNKNOWN 재개는 조회·재마운트 후에도 원 본문 보존·재전송 0', async () => {
  const { flow, world, client } = await decisionWorld();
  world.handlers['POST /hotl/resume'] = async () => { throw new Error('합성 응답 유실'); };
  await flow.resume('보존할 답변');
  const original = structuredClone(recordOf(flow, 'HOTL'));
  assert.equal(original.outcome, 'UNKNOWN'); await flow.load(); await flow.resume('변경 시도');
  flow.invalidate();
  const reopened = decisionFlow.createStudioDecisionFlow('p', client, 'TASK_1');
  reopened.activate(); await reopened.load(); await reopened.resume('재마운트 재전송 시도');
  assert.equal(writes().length, 1); assert.deepEqual(recordOf(reopened, 'HOTL').body, original.body);
});
await test('실제 async POST 대기 중 동일 결정 중복·새 조회 차단', async () => {
  const { flow, world } = await decisionWorld();
  const entered = deferred(), release = deferred();
  world.handlers['POST /hotl/resume'] = async body => { entered.resolve(); await release.promise; return response({ status: 'resumed', task_id: body.task_id }); };
  const pending = flow.resume('한 번');
  try {
    await bounded(entered.promise);
    await flow.resume('중복'); await flow.load();
    assert.equal(flow.getSnapshot().busy, true); assert.equal(writes().length, 1);
  } finally { release.resolve(); await bounded(pending); }
  assert.equal(flow.getSnapshot().busy, false);
});
await test('늦은 결정 GET은 언마운트 후 표시·메모리 변경 없음', async () => {
  const { flow, world } = await decisionWorld();
  const entered = deferred(), release = deferred();
  world.handlers['GET /hotl/check'] = async () => { entered.resolve(); await release.promise; return response(world.hotl); };
  const pending = flow.load();
  try { await bounded(entered.promise); flow.invalidate(); } finally { release.resolve(); await bounded(pending); }
  assert.equal(flow.getSnapshot().loaded, false); assert.equal(flow.getSnapshot().hotl, null);
  assert.deepEqual(flow.getSnapshot().records, {}); assert.equal(writes().length, 0);
});
await test('늦은 결정 POST는 다른 문맥에 반영하지 않고 원 문맥 UNKNOWN 유지', async () => {
  const { flow, world, client } = await decisionWorld();
  const entered = deferred(), release = deferred();
  world.handlers['POST /hotl/resume'] = async body => { entered.resolve(); await release.promise; return response({ status: 'resumed', task_id: body.task_id }); };
  const pending = flow.resume('원 문맥 답변');
  try { await bounded(entered.promise); identity.scopeNodeId = 'SYNTHETIC_SCOPE_B'; flow.invalidate(); }
  finally { release.resolve(); await bounded(pending); }
  assert.deepEqual(flow.getSnapshot().records, {});
  identity.scopeNodeId = 'SYNTHETIC_SCOPE_A';
  const reopened = decisionFlow.createStudioDecisionFlow('p', client, 'TASK_1');
  reopened.activate(); await reopened.load();
  assert.equal(recordOf(reopened, 'HOTL').outcome, 'UNKNOWN'); assert.equal(writes().length, 1);
});
await test('결정 API JSON 읽는 중 사용자 변경도 결과 폐기', async () => {
  const { client, world } = await decisionWorld();
  reply = async () => ({ ok: true, status: 200, json: async () => {
    identity.token = 'SYNTHETIC_CHANGED'; return world.hotl;
  } });
  await assert.rejects(client.hotl(), error => error.status === 409 && error.reasonCode === 'DECISION_CONTEXT_CHANGED');
});
await test('Host 검토 지문 변경은 승인 POST 0·이유 보존', async () => {
  const { flow, world } = await decisionWorld({ host: pendingHost() });
  flow.edit('HOST', decisionFlow.hostSubject('TASK_1', flow.getSnapshot().host), 'note', '확인한 이유');
  world.host.compiled_fingerprint = 'd'.repeat(64);
  await flow.decide('APPROVE');
  assert.equal(writes().length, 0); assert.equal(recordOf(flow, 'HOST').note, '확인한 이유');
  assert.equal(flow.getSnapshot().error.reasonCode, 'DECISION_ROUND_STALE');
});
await test('Host 미반영은 재승인 금지·false/503 이후 동일 사건 명시 멱등 복구', async () => {
  const { flow, world } = await decisionWorld({ host: pendingHost(), hostApplied: false });
  await flow.decide('APPROVE');
  const original = recordOf(flow, 'HOST');
  assert.equal(original.outcome, 'RECORDED'); assert.equal(original.eventId, 'event-1');
  assert.equal(flow.canResume(), false); await flow.decide('APPROVE');
  world.host.request_event_id = 'request-2'; await flow.load(); await flow.decide('APPROVE');
  assert.equal(writes('/contract-review/decision').length, 1);
  let attempt = 0;
  const entered = deferred(), release = deferred();
  world.handlers['POST /contract-review/reconcile'] = async body => {
    attempt += 1;
    if (attempt === 1) { entered.resolve(); await release.promise;
      return response({ status: 'success', data: { event_id: body.event_id, request_event_id: body.request_event_id,
        contract_fingerprint: body.compiled_fingerprint, state_applied: false, execution_started: false, reason_code: 'RETRY_REQUIRED' } }); }
    if (attempt === 2) return response({ detail: { reason_code: 'STATE_UNAVAILABLE', message: '합성 장애' } }, 503);
    return response({ status: 'success', data: { event_id: body.event_id, request_event_id: body.request_event_id,
      contract_fingerprint: body.compiled_fingerprint, state_applied: true, execution_started: false, reason_code: 'APPLIED' } });
  };
  const pending = flow.reconcile(original.key);
  try { await bounded(entered.promise); await flow.reconcile(original.key); assert.equal(attempt, 1); }
  finally { release.resolve(); await bounded(pending); }
  assert.equal(attempt, 1); await flow.reconcile(original.key); assert.equal(attempt, 2);
  await flow.reconcile(original.key); assert.equal(attempt, 3); await flow.reconcile(original.key);
  assert.equal(attempt, 3); assert.equal(recordOf(flow, 'HOST').outcome, 'CONFIRMED');
  for (const call of writes('/contract-review/reconcile')) assert.deepEqual(bodyOf(call), {
    task_id: 'TASK_1', event_id: 'event-1', request_event_id: 'request-1', compiled_fingerprint: contractFingerprint });
  assert.equal(writes('/hotl/resume').length, 0); assert.equal(writes('/contract-review/decision').length, 1);
});
await test('Host UNKNOWN 결정은 현재 조회 후에도 명시 재결정 금지', async () => {
  const { flow, world } = await decisionWorld({ host: pendingHost() });
  world.handlers['POST /contract-review/decision'] = async () => { throw new Error('원장 응답 유실'); };
  await flow.decide('APPROVE'); const original = structuredClone(recordOf(flow, 'HOST'));
  assert.equal(original.outcome, 'UNKNOWN'); assert.equal(original.hostReceipt, undefined);
  await flow.load(); await flow.decide('APPROVE'); await flow.reconcile(original.key);
  assert.equal(writes().length, 1); assert.deepEqual(recordOf(flow, 'HOST').body, original.body);
});
await test('지원 능력 허용 선택·고정 토큰·부분 원장 사건 보존 및 재결정 금지', async () => {
  const row = capabilityRow();
  const { flow, world } = await decisionWorld({ capabilities: pendingCapabilities(row) });
  const subject = decisionFlow.capabilitySubject(row);
  flow.edit('CAPABILITY', subject, 'choice', 'REQUEST_HOST_FEATURE'); await flow.resolve(row);
  assert.equal(writes().length, 0);
  flow.edit('CAPABILITY', subject, 'choice', 'REDUCE'); flow.edit('CAPABILITY', subject, 'note', '축소 이유');
  world.handlers['POST /contract-decisions/resolve'] = async () => response({ detail: {
    reason_code: 'DECISION_ROUND_PARTIAL', message: '합성 부분 반영', event_id: 'partial-event',
    decision_request_id: row.decision_request_id, draft_applied: false } }, 503);
  await flow.resolve(row); await flow.load(); await flow.resolve(row);
  assert.equal(writes().length, 1); assert.deepEqual(bodyOf(writes()[0]), { decision_request_id: row.decision_request_id,
    expected_digest: row.expected_digest, rationale: '축소 이유', task_id: 'TASK_1', capability: row.capability, decision: 'REDUCE' });
  assert.equal(recordOf(flow, 'CAPABILITY').eventId, 'partial-event');
  assert.equal(recordOf(flow, 'CAPABILITY').outcome, 'UNKNOWN');
});
await test('데이터 충돌은 실제 winner만 전송하고 능력 결정 필드 혼입 없음', async () => {
  const row = { decision_kind: 'DATASET', decision_request_id: 'cdr_' + roundId, expected_digest: roundId,
    round_status: 'PENDING', dataset_key: 'raw_material', choices: ['TASK_1', 'TASK_2'], differences: ['columns'] };
  const { flow } = await decisionWorld({ capabilities: pendingCapabilities(row) });
  flow.edit('CAPABILITY', decisionFlow.capabilitySubject(row), 'choice', 'TASK_2'); await flow.resolve(row);
  assert.deepEqual(bodyOf(writes()[0]), { decision_request_id: row.decision_request_id, expected_digest: roundId,
    rationale: '', dataset_key: 'raw_material', winner_task_id: 'TASK_2' });
});
await test('결정 성공 응답의 task/사건/복구 지문 불일치를 거절', async () => {
  const { client, world } = await decisionWorld();
  world.handlers['POST /hotl/resume'] = async () => response({ status: 'resumed', task_id: 'OTHER' });
  await assert.rejects(client.resume({ task_id: 'TASK_1', feedback: '', expected_request_id: roundId,
    expected_questions_digest: emptyQuestionsDigest }), error => error.status === 503);
  world.handlers['POST /contract-review/decision'] = async () => response({ status: 'success', data: {
    decision: 'APPROVE', event_id: 'e', request_event_id: 'OTHER', contract_fingerprint: contractFingerprint, state_applied: true } });
  await assert.rejects(client.decide({ task_id: 'TASK_1', request_event_id: 'request-1', decision: 'APPROVE', rationale: '' }), error => error.status === 503);
  world.handlers['POST /contract-review/reconcile'] = async () => response({ status: 'success', data: {
    event_id: 'e', request_event_id: 'request-1', contract_fingerprint: roundId, state_applied: true, execution_started: false } });
  await assert.rejects(client.reconcile({ task_id: 'TASK_1', request_event_id: 'request-1', event_id: 'e',
    compiled_fingerprint: contractFingerprint }), error => error.status === 503);
});
await test('권한 조회 실패는 과거 표시 숨김·입력 메모리 보존·권한 회복 GET만', async () => {
  const { flow, world } = await decisionWorld({ host: pendingHost() });
  flow.edit('HOST', decisionFlow.hostSubject('TASK_1', flow.getSnapshot().host), 'note', '보존할 검토');
  world.handlers['GET /contract-review/pending'] = async () => response({ detail: { message: '권한 없음', reason_code: 'DENIED' } }, 403);
  await flow.load();
  assert.equal(flow.getSnapshot().loaded, false); assert.equal(flow.getSnapshot().host, null);
  assert.deepEqual(flow.getSnapshot().records, {}); assert.equal(flow.getSnapshot().error.status, 403);
  delete world.handlers['GET /contract-review/pending']; await flow.load();
  assert.equal(recordOf(flow, 'HOST').note, '보존할 검토'); assert.equal(writes().length, 0);
});

// 오라클은 제품 canonical 함수로 만들지 않는다. 한국어와 화면에 없는 원본 필드를 함께 고정한다.
const questionCanonical = '[{"id":"q1","multi":false,"options":[{"description":"원료","label":"입고","recommended":true}],"question":"어떤 업무?","server_meta":{"revision":2}}]';
const questionRaw = JSON.parse(questionCanonical);
const displayedQuestions = [{ id: 'q1', question: '어떤 업무?', multi: false,
  options: [{ label: '입고', description: '원료', recommended: true }] }];
const questionDigest = createHash('sha256').update(questionCanonical, 'utf8').digest('hex');
const questionProof = () => ({ rawQuestions: structuredClone(questionRaw), displayedQuestions: structuredClone(displayedQuestions) });
await test('실제 SHA256 원본 전체와 표시 질문 동시 검증·숨은 필드 구판 거절', async () => {
  assert.equal(decisionApi.canonicalQuestionJson(questionRaw), questionCanonical);
  assert.equal(await decisionApi.verifyHotlQuestions(questionProof(), questionDigest), true);
  const stale = questionProof(); stale.rawQuestions[0].server_meta.revision = 1;
  assert.equal(await decisionApi.verifyHotlQuestions(stale, questionDigest), false);
  const mismatch = questionProof(); mismatch.displayedQuestions[0].question = '다른 화면 질문';
  assert.equal(await decisionApi.verifyHotlQuestions(mismatch, questionDigest), false);
});
await test('명확화 구판/미확인 질문 POST0·검증된 같은 질문만 고정 차수 POST', async () => {
  const { flow, world } = await decisionWorld();
  Object.assign(world.hotl.hotl_context, { decision_kind: 'CLARIFICATION', questions_digest: questionDigest }); await flow.load();
  await flow.resume('증명 없는 답'); assert.equal(writes().length, 0);
  const stale = questionProof(); stale.rawQuestions[0].server_meta.revision = 1;
  await flow.resume('구판 답', stale);
  assert.equal(writes().length, 0); assert.equal(flow.getSnapshot().error.reasonCode, 'HOTL_QUESTIONS_UNVERIFIED');
  await flow.resume('현재 답', questionProof());
  assert.equal(writes().length, 1); assert.equal(bodyOf(writes()[0]).expected_questions_digest, questionDigest);
});
await test('계약 메타데이터 미준비는 검증 명확화만 허용·일반 HOTL은 차단', async () => {
  const { flow, world } = await decisionWorld();
  world.handlers['GET /contract-decisions/pending'] = async () => response({ detail: {
    reason_code: 'DECISION_ROUND_METADATA_MISSING', message: '아직 계약 초안 없음' } }, 503);
  Object.assign(world.hotl.hotl_context, { decision_kind: 'CLARIFICATION', questions_digest: questionDigest }); await flow.load();
  assert.equal(flow.getSnapshot().loaded, true); assert.equal(flow.getSnapshot().capabilities, null);
  assert.equal(flow.getSnapshot().capabilityError.status, 503);
  await flow.resume('최초 답변', questionProof()); assert.equal(writes().length, 1);
  Object.assign(world.hotl.hotl_context, { decision_kind: 'GENERAL_HOTL', request_id: secondRoundId }); await flow.load();
  assert.equal(flow.getSnapshot().loaded, false); await flow.resume('우회 시도'); assert.equal(writes().length, 1);
});

const draftTarget = { kind: 'DECISION_COMMENT', task_id: 'TASK_1', decision_kind: 'HOST_CONTRACT',
  request_id: 'request-1', target_digest: contractFingerprint, subject_id: '' };
const draftSelector = { kind: draftTarget.kind, task_id: draftTarget.task_id, decision_kind: draftTarget.decision_kind,
  request_id: draftTarget.request_id, subject_id: '' };
const savedDraft = () => ({ draft_id: 'draft-1', project_id: 'p', target: structuredClone(draftTarget),
  content: { text: '저장한 의견', decision: 'APPROVE', selections: {} }, revision: 1,
  digest: roundId, status: 'DRAFT', restorable: true });
await test('초안 실제 API target GET 고정 selector 및 서버 입력 원문 반환', async () => {
  resetMemory(); calls = [];
  reply = async () => response({ status: 'success', data: { target: draftTarget, draft: savedDraft(), consume_supported: true } });
  const result = await draftApi.createInputDraftApi('p').target(draftSelector);
  assert.deepEqual(result.target, draftTarget); assert.equal(result.draft.content.text, '저장한 의견');
  assert.equal(calls.length, 1); assert.equal(writes().length, 0);
  const query = new URL(calls[0].url, api.API_BASE_URL).searchParams;
  for (const [key, value] of Object.entries(draftSelector)) assert.equal(query.get(key), value);
});
await test('초안 target의 요청·종류·subject 변경 및 내장 초안 target 불일치 거절', async () => {
  resetMemory();
  const client = draftApi.createInputDraftApi('p');
  for (const patch of [{ request_id: 'OTHER' }, { decision_kind: 'GENERAL_HOTL' }, { subject_id: 'OTHER' },
    { task_id: 'OTHER' }, { kind: 'CLARIFICATION' }]) {
    reply = async () => response({ status: 'success', data: { target: { ...draftTarget, ...patch }, draft: null, consume_supported: true } });
    await assert.rejects(client.target(draftSelector), error => [409, 503].includes(error.status));
  }
  reply = async () => response({ status: 'success', data: { target: draftTarget,
    draft: { ...savedDraft(), target: { ...draftTarget, target_digest: secondRoundId } }, consume_supported: true } });
  await assert.rejects(client.target(draftSelector), error => [409, 503].includes(error.status));
});
await test('초안 응답 프로젝트·판본·지문·상태 손상은 불러오기 불가', async () => {
  resetMemory(); const client = draftApi.createInputDraftApi('p');
  for (const patch of [{ project_id: 'OTHER' }, { revision: 0 }, { digest: 'bad' },
    { status: 'CONSUMED', restorable: true }]) {
    reply = async () => response({ status: 'success', data: { target: draftTarget,
      draft: { ...savedDraft(), ...patch }, consume_supported: true } });
    await assert.rejects(client.target(draftSelector), error => error.status === 503);
  }
});
await test('초안 API 구조 오류 구분 및 JSON 중 문맥 변경·구 API 재사용 차단', async () => {
  resetMemory(); calls = []; const client = draftApi.createInputDraftApi('p');
  reply = async () => response({ detail: { reason_code: 'INPUT_DRAFT_UNAVAILABLE', message: '합성 장애' } }, 503);
  await assert.rejects(client.target(draftSelector), error => error.status === 503 && error.reasonCode === 'INPUT_DRAFT_UNAVAILABLE');
  reply = async () => ({ ok: true, status: 200, json: async () => {
    identity.scopeNodeId = 'SYNTHETIC_SCOPE_B';
    return { status: 'success', data: { target: draftTarget, draft: null, consume_supported: true } };
  } });
  await assert.rejects(client.target(draftSelector), error => error.status === 409);
  const count = calls.length;
  await assert.rejects(client.target(draftSelector), error => error.status === 409);
  assert.equal(calls.length, count); assert.equal(writes().length, 0);
});
await test('메모리 다른 회사 old-key 읽기·쓰기·삭제 거절 후 원 입력 보존', () => {
  resetMemory();
  const old = memory.studioInputKey('p', 'decision-HOST', 'round1');
  memory.studioInputMemory.set(old, { text: 'A 원본' }); identity.scopeNodeId = 'SYNTHETIC_SCOPE_B';
  const current = memory.studioInputKey('p', 'decision-HOST', 'round1');
  memory.studioInputMemory.set(current, { text: 'B 원본' });
  assert.deepEqual(memory.studioInputMemory.get(old, {}), {});
  // 거절 표현은 예외 또는 무동작 모두 허용하되, 다른 문맥의 데이터는 반드시 불변이다.
  try { memory.studioInputMemory.set(old, { text: '늦은 A 응답' }); } catch { /* 명시 거절 */ }
  try { memory.studioInputMemory.clear(old); } catch { /* 명시 거절 */ }
  assert.equal(memory.studioInputMemory.get(current, {}).text, 'B 원본');
  identity.scopeNodeId = 'SYNTHETIC_SCOPE_A';
  assert.equal(memory.studioInputMemory.get(old, {}).text, 'A 원본');
});
await test('메모리 인증 변경 후 old-key로 재삽입해도 새 사용자 입력과 격리', () => {
  resetMemory();
  const old = memory.studioInputKey('p', 'decision-HOST', 'round1');
  memory.studioInputMemory.set(old, { text: '이전 사용자' }); identity.token = 'SYNTHETIC_OTHER_TOKEN';
  const current = memory.studioInputKey('p', 'decision-HOST', 'round1');
  memory.studioInputMemory.set(current, { text: '새 사용자' });
  try { memory.studioInputMemory.set(old, { text: '늦은 이전 사용자' }); } catch { /* 명시 거절 */ }
  assert.deepEqual(memory.studioInputMemory.get(old, {}), {});
  assert.equal(memory.studioInputMemory.get(current, {}).text, '새 사용자');
});

// BuildStart 요구초안 단위: 실제 서버 저장·PDP·실제 DOM을 검증했다는 주장이 아니다.
const preRequirementChecks = results.length;
const requirementSeed = { initialIdea: '  원료 입고 확인을 쉽게 하고 싶습니다.  ', projectName: '  원료 입고  ',
  templateId: 'SYNTHETIC_TEMPLATE', packIds: ['SYNTHETIC_PACK'], masterDomains: 'raw_material, inventory',
  processSelection: null, kitInstanceId: '', kitStartInstanceId: '' };
function requirementWorld() {
  resetMemory(); calls = [];
  const boundary = { tenant_id: identity.tenantId, context_root_id: 'SYNTHETIC_ROOT',
    entity_mode: identity.entityMode, scope_node_id: identity.scopeNodeId, configuration_kind: 'business_process' };
  const world = {
    reads: [], access: { boundary, principal_user_id: identity.user, permitted_actions: ['propose'] },
    resolved: { boundary, configuration_id: '', head_version: 0, profile_id: '', digest: '',
      state: 'NONE', payload: null, legacy_review_required: false },
    latest: null, post: null, ids: 0,
  };
  requirementReadWorld = world;
  world.revisionFor = body => ({
    draft_id: body.draft_id || 'requirement-draft-1', revision_id: 'requirement-revision-' + (body.expected_revision + 1),
    revision: body.expected_revision + 1,
    digest: createHash('sha256').update(JSON.stringify(body)).digest('hex'),
    status: 'DRAFT', author_actor: world.access.principal_user_id,
    context_key: { tenant_id: boundary.tenant_id, context_root_id: boundary.context_root_id,
      entity_mode: boundary.entity_mode, scope_node_id: boundary.scope_node_id },
    blueprint: Object.fromEntries(body.patch.map(item => [item.path[0], structuredClone(item.value)])),
    process_ref: null,
  });
  reply = async (url, options) => {
    const parsed = new URL(url, api.API_BASE_URL);
    if (options.method === 'POST' && parsed.pathname === '/api/v1/advisor/drafts') {
      const body = JSON.parse(options.body);
      if (world.post) return world.post(body, options.body);
      world.latest = world.revisionFor(body);
      return response({ status: 'success', data: world.latest });
    }
    if ((!options.method || options.method === 'GET')
        && parsed.pathname === '/api/v1/advisor/drafts/requirement-draft-1') {
      assert.equal(parsed.searchParams.get('context_root_id'), boundary.context_root_id);
      assert.equal(parsed.searchParams.get('scope_node_id'), boundary.scope_node_id);
      assert.ok(world.latest); return response({ status: 'success', data: world.latest });
    }
    throw new Error('요구초안 단위 범위 밖 요청: ' + (options.method || 'GET') + ' ' + parsed.pathname);
  };
  const flow = requirements.createStudioRequirementDraft('software_app', processApi.processContextIdentity(),
    () => 'requirement-request-' + (++world.ids));
  flow.initialize(requirementSeed);
  return { flow, world, boundary };
}
await test('요구초안 UNIT 무L2·무데이터 저장의 실제 POST 본문과 미실행 상태', async () => {
  const { flow, world, boundary } = requirementWorld();
  await flow.refresh();
  assert.equal(flow.getSnapshot().resolved.payload, null);
  const saved = await flow.save();
  assert.equal(saved.status, 'DRAFT'); assert.equal(saved.process_ref, null);
  assert.deepEqual(bodyOf(writes()[0]), {
    context_root_id: boundary.context_root_id, scope_node_id: boundary.scope_node_id,
    draft_id: '', expected_revision: 0, expected_digest: '', client_request_id: 'requirement-request-1',
    process_selection: null,
    patch: [
      { op: 'SET', path: ['title'], value: '원료 입고' },
      { op: 'SET', path: ['business'], value: { objective: requirementSeed.initialIdea } },
      { op: 'SET', path: ['system'], value: { template_id: 'SYNTHETIC_TEMPLATE' } },
      { op: 'SET', path: ['request_options'], value: { deliverable_type: 'software_app', is_mega: false,
        knowledge_pack_ids: ['SYNTHETIC_PACK'], master_domains: ['raw_material', 'inventory'],
        mcp_live_grounding: false, kit_instance_id: '', kit_start_instance_id: '' } },
    ],
  });
  assert.equal(flow.getSnapshot().creationState, 'IDLE');
  assert.deepEqual(await flow.save(), saved); assert.equal(writes().length, 1);
  assert.ok(world.reads.includes('resolved'));
  assert.ok(calls.every(call => call.url === '/api/v1/advisor/drafts'));
});
await test('요구초안 UNIT 409 CAS는 입력 잠금·최신 GET·명시 적용 후 새 판본 저장', async () => {
  const { flow, world } = requirementWorld();
  const first = await flow.save();
  flow.update({ initialIdea: '수정한 요구를 보존합니다.' });
  const preserved = structuredClone(flow.getSnapshot().form);
  world.post = async () => response({ detail: { reason_code: 'REVISION_CONFLICT', message: '다른 판본 존재' } }, 409);
  assert.equal(await flow.save(), null);
  const rejectedBody = bodyOf(writes()[1]);
  assert.equal(rejectedBody.expected_revision, first.revision);
  assert.equal(rejectedBody.expected_digest, first.digest);
  assert.equal(flow.getSnapshot().conflict, true);
  flow.update({ initialIdea: '차단 중 덮어쓰기' }); assert.deepEqual(flow.getSnapshot().form, preserved);
  await flow.save(); assert.equal(writes().length, 2);
  world.latest = { ...structuredClone(first), revision: 2, revision_id: 'requirement-revision-2', digest: 'd'.repeat(64) };
  await flow.readLatest();
  assert.equal(writes().length, 2); assert.equal(flow.getSnapshot().receipt.revision, 1);
  assert.deepEqual(flow.getSnapshot().form, preserved);
  flow.useLatest(); assert.equal(flow.getSnapshot().receipt.revision, 2);
  world.post = null; const saved = await flow.save();
  assert.equal(saved.revision, 3);
  const retried = bodyOf(writes()[2]);
  assert.equal(retried.expected_revision, 2); assert.equal(retried.expected_digest, 'd'.repeat(64));
  assert.notEqual(retried.client_request_id, rejectedBody.client_request_id);
  assert.equal(retried.patch.find(item => item.path[0] === 'business').value.objective, preserved.initialIdea);
});
await test('요구초안 UNIT 응답 유실은 원 키·직렬화 본문 보존 후 명시 동일 요청 재확인', async () => {
  const { flow, world } = requirementWorld();
  let original = '', committed = null;
  world.post = async (body, serialized) => {
    if (!original) { original = serialized; committed = world.revisionFor(body); throw new Error('합성 저장 응답 유실'); }
    assert.equal(serialized, original); return response({ status: 'success', data: committed });
  };
  assert.equal(await flow.save(), null);
  const frozen = structuredClone(flow.getSnapshot().attempt);
  assert.equal(frozen.serialized, original); assert.equal(world.ids, 1);
  flow.update({ initialIdea: '미확정 요청 덮어쓰기' });
  assert.deepEqual(flow.getSnapshot().form, frozen.form);
  await flow.refresh(); assert.equal(writes().length, 1);
  const saved = await flow.save();
  assert.equal(saved.revision_id, committed.revision_id);
  assert.equal(world.ids, 1); assert.equal(writes().length, 2);
  assert.equal(writes()[0].options.body, writes()[1].options.body);
  assert.equal(flow.getSnapshot().attempt, null);
});
await test('요구초안 UNIT 회사·산출물 메모리 분리 및 같은 문맥 왕복 seed 덮어쓰기 금지', async () => {
  resetMemory(); calls = [];
  identity.scopeNodeId = 'SYNTHETIC_REQUIREMENT_A';
  const first = requirements.getStudioRequirementDraft('software_app');
  first.initialize({ initialIdea: 'A 회사 요구', projectName: 'A 앱' });
  const again = requirements.getStudioRequirementDraft('software_app');
  assert.equal(again, first); again.initialize({ initialIdea: '뒤늦은 초기 props' });
  assert.equal(first.getSnapshot().form.initialIdea, 'A 회사 요구');
  identity.scopeNodeId = 'SYNTHETIC_REQUIREMENT_B';
  const second = requirements.getStudioRequirementDraft('software_app');
  assert.notEqual(second, first); assert.equal(second.getSnapshot().form.initialIdea, '');
  second.initialize({ initialIdea: 'B 회사 요구' });
  assert.throws(() => first.update({ initialIdea: '다른 문맥 수정' }), error => error.reasonCode === 'CLIENT_CONTEXT_CHANGED');
  assert.equal(await first.save(), null); assert.equal(writes().length, 0);
  identity.scopeNodeId = 'SYNTHETIC_REQUIREMENT_A';
  assert.equal(requirements.getStudioRequirementDraft('software_app'), first);
  assert.equal(first.getSnapshot().form.initialIdea, 'A 회사 요구');
  const reportDraft = requirements.getStudioRequirementDraft('document_report');
  assert.notEqual(reportDraft, first); assert.equal(reportDraft.getSnapshot().form.initialIdea, '');
  assert.equal(second.getSnapshot().form.initialIdea, 'B 회사 요구');
});
await test('요구초안 UNIT 다른 조직 저장 응답은 성공으로 수용하지 않고 원 요청 유지', async () => {
  const { flow, world } = requirementWorld();
  world.post = async body => {
    const row = world.revisionFor(body);
    row.context_key.scope_node_id = 'SYNTHETIC_OTHER_SCOPE';
    return response({ status: 'success', data: row });
  };
  assert.equal(await flow.save(), null);
  assert.equal(flow.getSnapshot().receipt, null);
  assert.equal(flow.getSnapshot().error.reasonCode, 'STUDIO_RESPONSE_INVALID');
  assert.ok(flow.getSnapshot().attempt);
  assert.equal(flow.getSnapshot().attempt.serialized, writes()[0].options.body);
  assert.equal(flow.getSnapshot().creationState, 'IDLE');
});
const requirementChecks = results.length - preRequirementChecks;
await test('초안 consume API 원 사건·CAS·요청 키 전송과 503 후 명시 동일 본문 재확인', async () => {
  resetMemory(); calls = [];
  const client = draftApi.createInputDraftApi('p');
  const body = Object.freeze({ expected_revision: 1, expected_digest: roundId,
    client_request_id: 'synthetic-consume-request-1', submission_id: 'synthetic-ledger-event-1' });
  let requestCount = 0;
  reply = async () => {
    requestCount += 1;
    if (requestCount === 1) return response({ detail: { message: '합성 반영 확인 장애', reason_code: 'CONSUME_UNAVAILABLE' } }, 503);
    return response({ status: 'success', data: { ...savedDraft(), status: 'CONSUMED', restorable: false, content: null } });
  };
  await assert.rejects(client.consume('draft-1', body), error => error.status === 503 && error.reasonCode === 'CONSUME_UNAVAILABLE');
  assert.equal(requestCount, 1);
  const result = await client.consume('draft-1', body);
  assert.equal(result.status, 'CONSUMED'); assert.equal(result.content, null); assert.equal(result.restorable, false);
  assert.equal(requestCount, 2);
  assert.ok(calls.every(call => call.url === '/api/v1/factory/p/input-drafts/draft-1/consume'));
  assert.equal(writes()[0].options.body, writes()[1].options.body);
  assert.deepEqual(bodyOf(writes()[0]), body);
});
await test('STATIC 초안 consume 미확정 원키 재사용·실패 중 자동 재전송 없음', () => {
  // 소스 계약 확인만 한다. 실제 이벤트/DOM/원장 멱등 동작을 검증한 것이 아니다.
  const source = fs.readFileSync(new URL('../src/factory/StudioInputDraftControls.tsx', import.meta.url), 'utf8');
  const start = source.indexOf('const consume = async');
  const end = source.indexOf('return <section', start);
  assert.ok(start >= 0 && end > start);
  const consume = source.slice(start, end);
  assert.match(consume, /const attempt = local\.consumeAttempt \|\|/);
  assert.match(consume, /client_request_id: crypto\.randomUUID\(\), submission_id: submissionId/);
  assert.match(consume, /update\(\{ \.\.\.local, consumeAttempt: attempt \}\)/);
  assert.match(consume, /api\.consume\(draftId, body\)/);
  const failure = consume.slice(consume.indexOf('} catch'));
  assert.doesNotMatch(failure, /api\.consume|crypto\.randomUUID|consumeAttempt:\s*null/);
  assert.match(source, /local\.attempt \|\| local\.consumeAttempt \? local\.draft : result\.draft/);
});
const preKitReviewChecks = results.length;
// 실제 adapter·flow·화면을 사용한다. 아래 계약/원장 응답은 모두 합성이며 서버 권한 검증이 아니다.
function kitReviewWorld(instanceId = 'SYNTHETIC_KIT_INSTANCE', appId = 'SYNTHETIC_KIT_APP') {
  resetMemory(); calls = [];
  const basePath = '/api/v1/data-preparation/instances/' + encodeURIComponent(instanceId)
    + '/apps/' + encodeURIComponent(appId) + '/contract';
  const draft = {
    instance_id: instanceId, app_id: appId, revision: 1, latest_revision: 1, status: 'DRAFT',
    semantic_fingerprint: contractFingerprint, drafted_by: 'SYNTHETIC_AUTHOR', approved_by: '',
    principal_user_id: identity.user, permitted_actions: ['approve', 'reject'],
    review_blockers: [], decision_event: null,
    contract: { schema_version: '2.0', project_id: instanceId, task_id: appId, revision: 1,
      semantic_fingerprint: contractFingerprint, status: 'DRAFT',
      description: 'SYNTHETIC_FULL_CONTRACT <script>notExecutable()</script>',
      process_context: { synthetic_only: true } },
  };
  const world = { instanceId, appId, basePath, latest: 1, rows: new Map([[1, draft]]),
    read: null, post: null };
  world.newDraft = (revision, fingerprint = secondRoundId) => {
    const row = structuredClone(draft);
    row.revision = revision; row.latest_revision = revision; row.semantic_fingerprint = fingerprint;
    row.contract.revision = revision; row.contract.semantic_fingerprint = fingerprint;
    world.rows.set(revision, row); world.latest = revision;
    for (const value of world.rows.values()) value.latest_revision = revision;
    return row;
  };
  world.commit = (decision, body, options = {}) => {
    const row = structuredClone(world.rows.get(body.revision));
    assert.ok(row, '합성 서버에도 지정 판본이 있어야 한다');
    const eventId = options.eventId || 'SYNTHETIC_KIT_EVENT_1';
    const actorId = options.actorId || identity.user;
    row.status = decision === 'APPROVE' ? 'APPROVED' : 'REJECTED';
    row.permitted_actions = [];
    row.contract.status = decision === 'APPROVE' ? 'APPROVED' : 'DRAFT';
    row.decision_event = { event_id: eventId, actor_id: actorId, decision: row.status, rationale: body.rationale };
    if (decision === 'APPROVE') {
      row.approved_by = actorId;
      row.contract.approval = { decision_ledger_id: eventId };
      row.ledger_event_id = eventId;
    } else row.rejection = { decision_ledger_id: eventId, rejected_by: actorId, rationale: body.rationale };
    world.rows.set(body.revision, row);
    return structuredClone(row);
  };
  reply = async (url, options) => {
    const parsed = new URL(url, 'https://synthetic.invalid');
    assert.equal(parsed.origin, 'https://synthetic.invalid');
    const method = options.method || 'GET';
    if (method === 'GET' && parsed.pathname === basePath + '/v2') {
      const revision = parsed.searchParams.has('revision') ? Number(parsed.searchParams.get('revision')) : world.latest;
      const row = structuredClone(world.rows.get(revision));
      assert.ok(row, '허용한 합성 판본만 조회한다');
      return world.read ? world.read(row, revision, parsed) : response({ status: 'success', data: row });
    }
    if (method === 'POST' && [basePath + '/v2/approve', basePath + '/reject'].includes(parsed.pathname)) {
      const decision = parsed.pathname.endsWith('/v2/approve') ? 'APPROVE' : 'REJECT';
      const body = JSON.parse(options.body);
      return world.post ? world.post(decision, body) : response({ status: 'success', data: world.commit(decision, body) });
    }
    throw new Error('키트 검토 외 합성 요청 금지: ' + method + ' ' + url);
  };
  world.makeFlow = () => {
    const client = kitReviewApi.createKitContractReviewApi(instanceId, appId);
    const flow = kitReviewFlow.createKitContractReviewFlow(instanceId, appId, client);
    flow.activate();
    return { client, flow };
  };
  return { world, ...world.makeFlow() };
}
function selectKitDecision(flow, decision = 'APPROVE', rationale = '  합성 계약 원문을 검토한 이유  ') {
  flow.editDecision(decision); flow.editRationale(rationale); flow.confirm(true);
}
function kitReviewHtml(flow) {
  // 실제 화면이 사용하는 View에 실제 flow 상태를 넘긴다. 이벤트/DOM/브라우저 동작은 실행하지 않는다.
  return renderToStaticMarkup(React.createElement(kitReviewUi.KitContractReviewView, {
    state: flow.getSnapshot(), canSubmit: flow.canSubmit(), onLoad: () => flow.load(),
    onSubmit: () => flow.submit(), onRecheck: key => flow.recheck(key),
    onRationale: flow.editRationale, onDecision: flow.editDecision, onConfirm: flow.confirm,
  }));
}
await test('Kit 검토 API 적용본·앱 경로 인코딩·지정 판본 GET과 원문 복제', async () => {
  const { world, client } = kitReviewWorld('SYNTHETIC/INSTANCE', 'APP ?#');
  const first = await client.read(); first.contract.description = '지역 변경';
  const second = await client.read(1);
  assert.match(second.contract.description, /SYNTHETIC_FULL_CONTRACT/);
  assert.deepEqual(calls.map(call => call.url), [world.basePath + '/v2', world.basePath + '/v2?revision=1']);
  assert.equal(writes().length, 0);
  await assert.rejects(client.read(0), error => error.status === 422);
  assert.equal(calls.length, 2);
});
await test('Kit 검토 UNIT 구판 preflight는 POST 0·원 판본 의견 보존', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  const original = structuredClone(flow.getSnapshot().current);
  world.newDraft(2);
  assert.equal(await flow.submit(), false);
  assert.equal(writes().length, 0);
  assert.equal(flow.getSnapshot().error.reasonCode, 'KIT_REVIEW_CHANGED');
  assert.equal(flow.getSnapshot().current.rationale, original.rationale);
  assert.equal(flow.getSnapshot().current.fingerprint, original.fingerprint);
  assert.equal(flow.getSnapshot().confirmed, false);
  await flow.load();
  assert.equal(flow.getSnapshot().current.revision, 2);
  assert.equal(flow.getSnapshot().current.rationale, '');
  assert.equal(flow.getSnapshot().current.decision, '');
});
await test('Kit 검토 UNIT 허용 행동 없음·제출 직전 권한 철회는 POST 0', async () => {
  const { world, flow } = kitReviewWorld();
  world.rows.get(1).permitted_actions = [];
  await flow.load(); selectKitDecision(flow);
  assert.equal(flow.canSubmit(), false); assert.equal(await flow.submit(), false);
  world.rows.get(1).permitted_actions = ['approve'];
  await flow.load(); selectKitDecision(flow);
  assert.equal(flow.canSubmit(), true);
  world.rows.get(1).permitted_actions = [];
  assert.equal(await flow.submit(), false);
  assert.equal(flow.getSnapshot().error.reasonCode, 'KIT_REVIEW_CHANGED');
  assert.equal(writes().length, 0);
});
await test('Kit 검토 UNIT 자기 승인·반려 차단 및 SSR 다른 적격 검토자 안내', async () => {
  const { world, flow } = kitReviewWorld();
  world.rows.get(1).drafted_by = '  ' + identity.user.toLowerCase() + '  ';
  world.rows.get(1).permitted_actions = [];
  await flow.load();
  for (const decision of ['APPROVE', 'REJECT']) {
    selectKitDecision(flow, decision); assert.equal(flow.canSubmit(), false);
    assert.equal(await flow.submit(), false);
  }
  const html = kitReviewHtml(flow);
  assert.match(html, /다른 적격 검토자가 승인·반려해야 합니다/);
  assert.match(html, /class="primary-button" disabled=""/);
  assert.equal(writes().length, 0);
});
await test('Kit 검토 UNIT 확인 후 사유·선택 수정은 확인 무효·재확인 전 POST 0', async () => {
  const { flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow); assert.equal(flow.canSubmit(), true);
  flow.editRationale('바뀐 검토 이유');
  assert.equal(flow.getSnapshot().confirmed, false); assert.equal(await flow.submit(), false);
  flow.confirm(true); assert.equal(flow.canSubmit(), true);
  flow.editDecision('REJECT');
  assert.equal(flow.getSnapshot().confirmed, false); assert.equal(await flow.submit(), false);
  flow.confirm(true); assert.equal(flow.canSubmit(), true);
  assert.equal(writes().length, 0);
});
await test('Kit 검토 API 승인 exact payload·같은 판본 GET 확인·재승인 없음', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  assert.equal(await flow.submit(), true);
  assert.deepEqual(bodyOf(writes()[0]), { revision: 1, expected_fingerprint: contractFingerprint, rationale: '합성 계약 원문을 검토한 이유' });
  assert.equal(writes()[0].url, world.basePath + '/v2/approve');
  assert.equal(calls.at(-1).url, world.basePath + '/v2?revision=1');
  assert.equal(flow.getSnapshot().current.outcome, 'CONFIRMED');
  assert.equal(flow.getSnapshot().current.eventId, 'SYNTHETIC_KIT_EVENT_1');
  assert.equal(await flow.submit(), false); assert.equal(writes().length, 1);
});
await test('Kit 검토 API 반려 exact digest payload·원문 DRAFT 유지·읽기 전용 SSR', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow, 'REJECT', '수정 근거가 부족합니다.');
  assert.equal(await flow.submit(), true);
  assert.deepEqual(bodyOf(writes()[0]), { revision: 1, expected_digest: contractFingerprint, rationale: '수정 근거가 부족합니다.' });
  assert.equal(writes()[0].url, world.basePath + '/reject');
  assert.equal(flow.getSnapshot().view.status, 'REJECTED');
  assert.equal(flow.getSnapshot().view.contract.status, 'DRAFT');
  const html = kitReviewHtml(flow);
  assert.match(html, /반려됨/); assert.match(html, /반려 사건 확인/);
  assert.match(html, /<textarea[^>]*disabled=""/);
  assert.match(html, /class="primary-button" disabled=""/);
  assert.equal(await flow.submit(), false); assert.equal(writes().length, 1);
});
await test('Kit 검토 UNIT UNKNOWN 유실은 재POST 0·재진입 후 원 사건 GET만 확인', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  let sent;
  world.post = async (_decision, body) => { sent = structuredClone(body); throw new Error('합성 결정 응답 유실'); };
  assert.equal(await flow.submit(), false);
  const frozen = structuredClone(flow.getSnapshot().current);
  assert.equal(frozen.outcome, 'UNKNOWN');
  assert.match(kitReviewHtml(flow), /제출 결과 미확정/);
  assert.match(kitReviewHtml(flow), /이 요청의 처리 결과 확인/);
  assert.equal(await flow.submit(), false);
  flow.invalidate();
  const reopened = world.makeFlow().flow;
  await reopened.load(); reopened.editRationale('미확정 요청 덮어쓰기'); reopened.confirm(true);
  assert.deepEqual(reopened.getSnapshot().current.command, frozen.command);
  assert.equal(reopened.canSubmit(), false); assert.equal(await reopened.submit(), false);
  await reopened.recheck(frozen.key);
  assert.equal(reopened.getSnapshot().current.outcome, 'UNKNOWN');
  world.commit('APPROVE', sent);
  const beforeRecheck = calls.length;
  await reopened.recheck(frozen.key);
  assert.equal(reopened.getSnapshot().current.outcome, 'CONFIRMED');
  assert.equal(reopened.getSnapshot().current.eventId, 'SYNTHETIC_KIT_EVENT_1');
  assert.deepEqual(calls.slice(beforeRecheck).map(call => [call.options.method || 'GET', call.url]),
    [['GET', world.basePath + '/v2?revision=1']]);
  assert.equal(writes().length, 1);
});
await test('Kit 검토 UNIT UNKNOWN 503 뒤 다른 결정은 RESOLVED_OTHER·내 성공 아님', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  world.post = async () => response({ detail: { reason_code: 'OUTCOME_UNKNOWN', message: '합성 원장 확인 장애' } }, 503);
  assert.equal(await flow.submit(), false);
  const record = structuredClone(flow.getSnapshot().current);
  world.commit('REJECT', { revision: 1, rationale: '다른 검토자의 반려 이유' }, { actorId: 'OTHER_REVIEWER', eventId: 'OTHER_EVENT' });
  await flow.recheck(record.key);
  assert.equal(flow.getSnapshot().current.outcome, 'RESOLVED_OTHER');
  assert.deepEqual(flow.getSnapshot().current.command, record.command);
  assert.equal(flow.getSnapshot().current.eventId, 'OTHER_EVENT');
  assert.match(kitReviewHtml(flow), /내 제출 성공이 아님/);
  assert.equal(await flow.submit(), false); assert.equal(writes().length, 1);
});
await test('Kit 검토 UNIT 기록 응답 뒤 GET 장애는 사건 보존·같은 사건 조회로 확인', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  world.read = async (row, _revision, parsed) => parsed.searchParams.has('revision')
    ? response({ detail: { message: '합성 조회 장애' } }, 503) : response({ status: 'success', data: row });
  assert.equal(await flow.submit(), false);
  const record = structuredClone(flow.getSnapshot().current);
  assert.equal(record.outcome, 'RECORDED'); assert.equal(record.eventId, 'SYNTHETIC_KIT_EVENT_1');
  assert.equal(flow.getSnapshot().loaded, false);
  assert.match(kitReviewHtml(flow), /사건 기록됨 · 반영 확인 필요/);
  assert.equal(await flow.submit(), false);
  world.read = null;
  await flow.recheck(record.key);
  assert.equal(flow.getSnapshot().current.outcome, 'CONFIRMED');
  assert.equal(flow.getSnapshot().current.eventId, record.eventId);
  assert.deepEqual(flow.getSnapshot().current.command, record.command);
  assert.equal(writes().length, 1);
});
await test('Kit 검토 UNIT 이미 받은 사건 ID와 다른 GET 사건은 같은 내용이어도 성공 아님', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  world.post = async (decision, body) => {
    const receipt = world.commit(decision, body, { eventId: 'RECEIPT_EVENT_A' });
    world.commit(decision, body, { eventId: 'READ_EVENT_B' });
    return response({ status: 'success', data: receipt });
  };
  assert.equal(await flow.submit(), false);
  assert.notEqual(flow.getSnapshot().current.outcome, 'CONFIRMED');
  assert.equal(flow.canSubmit(), false);
  assert.equal(await flow.submit(), false); assert.equal(writes().length, 1);
});
await test('Kit 검토 UNIT 진행 중 중복 제출·조회는 추가 POST 없이 차단', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  const entered = deferred(), finish = deferred();
  world.post = async (decision, body) => {
    entered.resolve(); await finish.promise;
    return response({ status: 'success', data: world.commit(decision, body) });
  };
  const pending = flow.submit();
  try {
    await bounded(entered.promise);
    assert.equal(flow.getSnapshot().busy, true);
    const key = flow.getSnapshot().current.key, count = calls.length;
    assert.equal(await flow.submit(), false);
    await flow.load(); await flow.recheck(key);
    assert.equal(calls.length, count); assert.equal(writes().length, 1);
  } finally { finish.resolve(); await bounded(pending); }
  assert.equal(flow.getSnapshot().busy, false);
  assert.equal(flow.getSnapshot().current.outcome, 'CONFIRMED');
});
await test('Kit 검토 UNIT preflight 중 문맥 전환은 늦은 원문 폐기·POST 0·SSR 숨김', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  const entered = deferred(), finish = deferred();
  world.read = async row => { entered.resolve(); await finish.promise; return response({ status: 'success', data: row }); };
  const pending = flow.submit();
  try {
    await bounded(entered.promise);
    identity.scopeNodeId = 'SYNTHETIC_OTHER_SCOPE'; flow.invalidate();
  } finally { finish.resolve(); await bounded(pending); }
  assert.equal(flow.getSnapshot().view, null); assert.equal(flow.getSnapshot().current, null);
  assert.deepEqual(flow.getSnapshot().history, []);
  assert.equal(flow.getSnapshot().loaded, false); assert.equal(writes().length, 0);
  assert.doesNotMatch(kitReviewHtml(flow), /SYNTHETIC_FULL_CONTRACT|합성 계약 원문을 검토한 이유/);
});
await test('Kit 검토 UNIT POST 중 문맥 전환은 늦은 영수증 숨김·왕복 시 GET 복구만', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  const entered = deferred(), finish = deferred();
  world.post = async (decision, body) => {
    const receipt = world.commit(decision, body);
    entered.resolve(); await finish.promise; return response({ status: 'success', data: receipt });
  };
  const pending = flow.submit();
  try {
    await bounded(entered.promise);
    identity.scopeNodeId = 'SYNTHETIC_OTHER_SCOPE'; flow.invalidate();
    assert.equal(flow.canSubmit(), false);
  } finally { finish.resolve(); await bounded(pending); }
  assert.equal(flow.getSnapshot().current, null); assert.deepEqual(flow.getSnapshot().history, []);
  assert.doesNotMatch(kitReviewHtml(flow), /SYNTHETIC_FULL_CONTRACT|SYNTHETIC_KIT_EVENT_1/);
  identity.scopeNodeId = syntheticIdentity.scopeNodeId;
  const reopened = world.makeFlow().flow;
  await reopened.load();
  assert.equal(reopened.getSnapshot().current.outcome, 'CONFIRMED');
  assert.equal(await reopened.submit(), false); assert.equal(writes().length, 1);
});
await test('Kit 검토 UNIT 구판 미확정 요청이 있으면 새 판도 재결정 차단', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  world.post = async () => { throw new Error('합성 응답 유실'); };
  await flow.submit();
  const old = structuredClone(flow.getSnapshot().current);
  world.newDraft(2);
  await flow.load(); selectKitDecision(flow, 'APPROVE', '새 판의 독립 의견');
  assert.equal(flow.getSnapshot().current.revision, 2);
  assert.equal(flow.canSubmit(), false); assert.equal(await flow.submit(), false);
  world.commit('REJECT', { revision: 1, rationale: '다른 결정' }, { actorId: 'OTHER_REVIEWER' });
  await flow.recheck(old.key);
  assert.equal(flow.getSnapshot().current.revision, 2);
  assert.equal(flow.getSnapshot().current.rationale, '새 판의 독립 의견');
  assert.equal(flow.getSnapshot().history.find(row => row.key === old.key).outcome, 'RESOLVED_OTHER');
  flow.confirm(true); assert.equal(flow.canSubmit(), true); assert.equal(writes().length, 1);
});
await test('Kit 검토 UNIT 대체된 승인판은 원문 조회 전용·새 판에 의견 자동 복사 없음', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  assert.equal(await flow.submit(), true);
  world.newDraft(2);
  world.rows.get(1).status = 'SUPERSEDED';
  await flow.load(1);
  assert.equal(flow.getSnapshot().view.contract.status, 'APPROVED');
  assert.equal(flow.canSubmit(), false);
  const html = kitReviewHtml(flow);
  assert.match(html, /이전 판 · 대체됨/); assert.match(html, /최신 판이 아닙니다/);
  assert.match(html, /<textarea[^>]*disabled=""/);
  await flow.load();
  assert.equal(flow.getSnapshot().current.rationale, '');
  assert.equal(flow.getSnapshot().current.decision, '');
  assert.equal(writes().length, 1);
});
await test('Kit 검토 UNIT 서버가 구판 후속 결정 불가를 확인하면 원기록 보존·최신판만 잠금 해제', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  world.post = async () => { throw new Error('합성 응답 유실'); };
  await flow.submit();
  const old = structuredClone(flow.getSnapshot().current);
  world.newDraft(2);
  const prior = world.rows.get(1);
  prior.permitted_actions = [];
  prior.review_blockers = [{ reason_code: 'PROCESS_CONTRACT_CONFLICT', message: '최신 개정이 아닙니다.' }];
  await flow.load(); selectKitDecision(flow, 'APPROVE', '새 판의 독립 의견');
  assert.equal(flow.canSubmit(), false);
  await flow.recheck(old.key);
  const history = flow.getSnapshot().history.find(row => row.key === old.key);
  assert.equal(history.outcome, 'RESOLVED_OTHER');
  assert.deepEqual(history.command, old.command);
  assert.equal(history.eventId, undefined);
  assert.equal(flow.getSnapshot().current.rationale, '새 판의 독립 의견');
  flow.confirm(true); assert.equal(flow.canSubmit(), true);
  assert.equal(writes().length, 1);
});
await test('Kit 검토 UNIT 기록 영수증은 구판 후속 결정 불가만으로 해제하지 않음', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  world.read = async (row, _revision, parsed) => parsed.searchParams.has('revision')
    ? response({ detail: { message: '합성 조회 장애' } }, 503) : response({ status: 'success', data: row });
  await flow.submit();
  const record = structuredClone(flow.getSnapshot().current);
  assert.equal(record.outcome, 'RECORDED');
  world.newDraft(2); world.read = null;
  const prior = world.rows.get(1);
  prior.status = 'DRAFT'; prior.contract.status = 'DRAFT'; prior.decision_event = null;
  prior.permitted_actions = [];
  prior.review_blockers = [{ reason_code: 'PROCESS_CONTRACT_CONFLICT', message: '최신 개정이 아닙니다.' }];
  await flow.load(); await flow.recheck(record.key);
  assert.equal(flow.getSnapshot().history.find(row => row.key === record.key).outcome, 'RECORDED');
  selectKitDecision(flow); assert.equal(flow.canSubmit(), false); assert.equal(writes().length, 1);
});
await test('Kit 검토 STATIC 가시성 상실 신호가 카드·앱 목록·적용본 캐시 숨김으로 전달됨', () => {
  const read = file => fs.readFileSync(new URL(file, import.meta.url), 'utf8');
  const review = read('../src/components/KitContractReview.tsx');
  const panel = read('../src/components/KitAppPanel.tsx');
  const operations = read('../src/components/KitOperationsPanel.tsx');
  assert.match(review, /\[401, 403, 404\]\.includes\(state\.error\.status\)/);
  assert.match(review, /onVisibilityLost\?\.\(\)/);
  assert.match(panel, /onVisibilityLost=\{onVisibilityLost\}/);
  assert.match(panel, /row\.contract_status !== null \? <KitContractReview/);
  assert.match(panel, /setRows\(null\); setNotices\(\{\}\); setSelectedAppId\(''\)/);
  assert.match(panel, /onVisibilityLost=\{hideUnavailable\}/);
  assert.match(operations, /setInstances\(null\); setSelected\(''\)/);
  assert.match(operations, /onVisibilityLost=\{hideUnavailable\}/);
});
await test('Kit 검토 API 악성 원문 대상·판본·지문·상태·허용 행동 응답 거절', async () => {
  const { world, client } = kitReviewWorld();
  const valid = structuredClone(world.rows.get(1));
  const corruptions = [
    row => { row.instance_id = 'OTHER_INSTANCE'; }, row => { row.app_id = 'OTHER_APP'; },
    row => { row.latest_revision = 0; }, row => { row.semantic_fingerprint = 'not-a-digest'; },
    row => { row.contract.project_id = 'OTHER_PROJECT'; }, row => { row.contract.task_id = 'OTHER_TASK'; },
    row => { row.contract.revision = 2; }, row => { row.contract.semantic_fingerprint = secondRoundId; },
    row => { row.contract.schema_version = '1.0'; }, row => { row.contract.status = 'APPROVED'; },
    row => { row.permitted_actions = ['execute']; }, row => { row.review_blockers = [{ reason_code: 'BLOCKED' }]; },
    row => { row.drafted_by = row.principal_user_id; },
    row => { row.status = 'APPROVED'; row.contract.status = 'APPROVED'; row.permitted_actions = []; },
    row => { row.decision_event = { event_id: 'INVENTED', actor_id: identity.user, rationale: '', decision: 'APPROVED' }; },
  ];
  for (const corrupt of corruptions) {
    const row = structuredClone(valid); corrupt(row);
    world.read = async () => response({ status: 'success', data: row });
    await assert.rejects(client.read(), error => error.status === 503 && error.reasonCode === 'KIT_REVIEW_RESPONSE_INVALID');
  }
  world.newDraft(2);
  world.read = async () => response({ status: 'success', data: valid });
  await assert.rejects(client.read(2), error => error.status === 503);
  assert.equal(writes().length, 0);
});
await test('Kit 검토 API 오류 envelope·실제 사용자 변경은 정상 계약으로 수용 안 함', async () => {
  const { world, client } = kitReviewWorld();
  await client.read();
  world.read = async () => response({ status: 'success', data: [] });
  await assert.rejects(client.read(), error => error.reasonCode === 'KIT_REVIEW_RESPONSE_INVALID');
  world.read = async () => response({ detail: { reason_code: 'REVIEW_FORBIDDEN', message: '합성 접근 거절' } }, 403);
  await assert.rejects(client.read(), error => error.status === 403 && error.reasonCode === 'REVIEW_FORBIDDEN');
  world.read = async row => response({ status: 'success', data: { ...row, principal_user_id: 'DIFFERENT_PRINCIPAL' } });
  await assert.rejects(client.read(), error => error.status === 409 && error.reasonCode === 'CONTEXT_CHANGED');
  assert.equal(writes().length, 0);
});
await test('Kit 검토 API 악성 승인·반려 영수증은 UNKNOWN·자동 재POST 없음', async () => {
  for (const [decision, corrupt] of [
    ['APPROVE', row => { row.approved_by = 'OTHER_REVIEWER'; }],
    ['APPROVE', row => { row.contract.approval.decision_ledger_id = 'OTHER_EVENT'; }],
    ['REJECT', row => { row.rejection.rationale = '다른 반려 이유'; }],
    ['REJECT', row => { row.contract.semantic_fingerprint = secondRoundId; }],
  ]) {
    const { world, flow } = kitReviewWorld();
    await flow.load(); selectKitDecision(flow, decision);
    world.post = async (choice, body) => {
      const row = world.commit(choice, body); corrupt(row);
      return response({ status: 'success', data: row });
    };
    assert.equal(await flow.submit(), false);
    assert.equal(flow.getSnapshot().error.reasonCode, 'KIT_REVIEW_RESPONSE_INVALID');
    assert.equal(flow.getSnapshot().current.outcome, 'UNKNOWN');
    assert.equal(flow.getSnapshot().current.command.decision, decision);
    assert.equal(await flow.submit(), false); assert.equal(writes().length, 1);
  }
});
await test('Kit 검토 UNIT 403 조회 실패는 이전 원문·입력 숨김·복구 GET 후 같은 문맥 입력 보존', async () => {
  const { world, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow, 'APPROVE', 'PRIVATE_REVIEW_INPUT');
  world.read = async () => response({ detail: { message: '권한 확인 필요', reason_code: 'FORBIDDEN' } }, 403);
  await flow.load();
  assert.equal(flow.getSnapshot().view, null); assert.equal(flow.getSnapshot().current, null);
  assert.deepEqual(flow.getSnapshot().history, []);
  const html = kitReviewHtml(flow);
  assert.match(html, /권한 확인 필요/);
  assert.doesNotMatch(html, /PRIVATE_REVIEW_INPUT|SYNTHETIC_FULL_CONTRACT/);
  world.read = null; await flow.load();
  assert.equal(flow.getSnapshot().current.rationale, 'PRIVATE_REVIEW_INPUT');
  assert.equal(flow.getSnapshot().confirmed, false); assert.equal(writes().length, 0);
});
await test('Kit 검토 SSR 실제 원문 escaping·확인 버튼·메모리/서버/실행 경계', async () => {
  const { world, client, flow } = kitReviewWorld();
  await flow.load(); selectKitDecision(flow);
  const count = calls.length, html = kitReviewHtml(flow);
  assert.match(html, /계약 원문 전체 보기/); assert.match(html, /SYNTHETIC_FULL_CONTRACT/);
  assert.match(html, /&lt;script&gt;notExecutable\(\)&lt;\/script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /class="primary-button">확인한 계약 승인/);
  assert.match(html, /서버 초안 저장은 아니며/);
  assert.match(html, /앱 실행 권한이 생기지 않습니다/);
  const initial = renderToStaticMarkup(React.createElement(kitReviewUi.KitContractReview, {
    instanceId: world.instanceId, appId: world.appId, apiFactory: () => client,
  }));
  assert.match(initial, /현재 문맥의 계약 원문을 확인한 뒤/);
  assert.doesNotMatch(initial, /SYNTHETIC_FULL_CONTRACT/);
  assert.equal(calls.length, count); assert.equal(writes().length, 0);
});
const kitReviewChecks = results.length - preKitReviewChecks;
const preRevisionChecks = results.length;
// 실제 수정 API·flow와 초안 reader를 재사용한다. HTTP 응답만 합성이며 작업/DB/서버 권한은 실행하지 않는다.
function revisionRequestWorld(projectId = 'SYNTHETIC_REVISION_PROJECT', taskId = 'SYNTHETIC_SOURCE_TASK') {
  resetMemory(); calls = [];
  const key = (project, subject) => JSON.stringify([project, subject]);
  const world = { bindings: new Map(), receipts: new Map(), feedback: '  합성 산출물의 입고 검증을 보완해 주세요.  ',
    targetRead: null, post: null, read: null, count: 0 };
  world.commit = (project, command) => {
    const receipt = { request_id: command.client_request_id, submission_id: 'SYNTHETIC_SUBMISSION_' + (++world.count),
      project_id: project, actor_id: identity.user, target: structuredClone(command.target), feedback: command.feedback,
      input_draft: structuredClone(command.input_draft), task_id: 'TASK_REV_SYNTHETIC_' + world.count,
      status: 'ACCEPTED', execution_started: false, created_at: '2026-09-13T12:00:00.000Z' };
    world.receipts.set(key(project, command.client_request_id), structuredClone(receipt));
    return receipt;
  };
  world.open = (project = projectId, task = taskId) => {
    if (!world.bindings.has(key(project, task))) {
      const target = { kind: 'REVISION_REQUEST', task_id: task, decision_kind: '', subject_id: '',
        target_digest: contractFingerprint, request_id: 'artifact_' + contractFingerprint };
      const draft = { draft_id: 'SYNTHETIC_SAVED_' + task, project_id: project, target: structuredClone(target),
        revision: 1, digest: roundId, status: 'DRAFT', restorable: true,
        content: { text: world.feedback, decision: '', selections: {} } };
      world.bindings.set(key(project, task), { projectId: project, taskId: task, target, draft });
    }
    const binding = world.bindings.get(key(project, task));
    const client = revisionApi.createStudioRevisionApi(project);
    const inputApi = draftApi.createInputDraftApi(project);
    const flow = revisionFlow.createStudioRevisionFlow(project, task, client, inputApi);
    flow.activate();
    const authorize = async () => {
      const current = await inputApi.target({ kind: 'REVISION_REQUEST', task_id: task });
      flow.authorize(current.target);
      return current;
    };
    return { binding, client, inputApi, flow, authorize };
  };
  reply = async (url, options) => {
    const parsed = new URL(url, 'https://synthetic.invalid');
    assert.equal(parsed.origin, 'https://synthetic.invalid');
    const route = parsed.pathname.match(/^\/api\/v1\/factory\/([^/]+)\/(.*)$/);
    assert.ok(route, '허용한 수정/초안 합성 경로만 호출한다');
    const project = decodeURIComponent(route[1]), tail = route[2], method = options.method || 'GET';
    if (method === 'GET' && tail === 'input-drafts/target') {
      assert.equal(parsed.searchParams.get('kind'), 'REVISION_REQUEST');
      assert.deepEqual([...parsed.searchParams.keys()].sort(), ['kind', 'task_id']);
      const binding = world.bindings.get(key(project, parsed.searchParams.get('task_id')));
      assert.ok(binding, '등록한 합성 프로젝트/작업만 조회한다');
      const data = { target: structuredClone(binding.target), draft: structuredClone(binding.draft), consume_supported: true };
      return world.targetRead ? world.targetRead(data, binding) : response({ status: 'success', data });
    }
    if (method === 'POST' && tail === 'sprint/revision-requests') {
      const command = JSON.parse(options.body);
      return world.post ? world.post(command, project) : response({ status: 'success', data: world.commit(project, command) });
    }
    const read = tail.match(/^sprint\/revision-requests\/([^/]+)$/);
    if (method === 'GET' && read) {
      const requestId = decodeURIComponent(read[1]);
      const receipt = structuredClone(world.receipts.get(key(project, requestId)) || null);
      return world.read ? world.read(receipt, requestId, project) : receipt
        ? response({ status: 'success', data: receipt })
        : response({ detail: { reason_code: 'REVISION_REQUEST_NOT_FOUND', message: '합성 접수 확인 대기' } }, 404);
    }
    throw new Error('수정 접수 외 실행/초안 변경 경로는 허용하지 않는다: ' + method + ' ' + url);
  };
  return { world, ...world.open() };
}
function revisionCommand(binding, feedback, requestId = 'SYNTHETIC_REVISION_REQUEST') {
  return { client_request_id: requestId, target: structuredClone(binding.target), feedback: feedback.trim(),
    input_draft: { draft_id: binding.draft.draft_id, revision: binding.draft.revision, digest: binding.draft.digest } };
}
const submitRevision = fixture => fixture.flow.submit(fixture.binding.target, fixture.world.feedback, fixture.binding.draft);
await test('수정 접수 UNIT 현재 대상 조회 전 비노출·strict target·저장 본문/길이 경계', async () => {
  const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
  assert.equal(flow.getSnapshot().authorized, false); assert.deepEqual(flow.getSnapshot().records, []);
  assert.equal(await submitRevision(fixture), null); assert.equal(calls.length, 0);
  for (const patch of [{ request_id: 'old_round' }, { subject_id: 'not-empty' }, { decision_kind: 'GENERAL_HOTL' },
    { kind: 'DECISION_COMMENT' }, { target_digest: 'bad' }, { task_id: 'OTHER_TASK' }]) {
    flow.authorize({ ...binding.target, ...patch });
    assert.equal(flow.getSnapshot().authorized, false);
  }
  await authorize();
  assert.equal(flow.canSubmit(binding.target, world.feedback, binding.draft), true);
  for (const selections of [undefined, {}]) {
    const saved = { ...binding.draft, content: { text: world.feedback.trim(), decision: '', selections } };
    assert.equal(revisionApi.matchesRevisionDraft(binding.projectId, binding.target, world.feedback, saved), true);
    assert.equal(flow.canSubmit(binding.target, world.feedback, saved), true);
  }
  for (const draft of [null, { ...binding.draft, status: 'CONSUMED', restorable: false },
    { ...binding.draft, content: { text: '저장한 내용과 다름', decision: '' } },
    { ...binding.draft, content: { text: world.feedback, decision: 'APPROVE' } },
    { ...binding.draft, content: { text: world.feedback, decision: '', selections: { q: ['answer'] } } }]) {
    assert.equal(flow.canSubmit(binding.target, world.feedback, draft), false);
  }
  for (const feedback of ['', '  ', 'x'.repeat(32001)]) {
    const draft = { ...binding.draft, content: { text: feedback, decision: '' } };
    assert.equal(flow.canSubmit(binding.target, feedback, draft), false);
  }
  const maximum = 'x'.repeat(32000);
  assert.equal(flow.canSubmit(binding.target, maximum, { ...binding.draft, content: { text: maximum, decision: '' } }), true);
  assert.equal(writes().length, 0);
});
await test('수정 접수 API 잘못된 요청 키·전체 대상·저장 참조는 HTTP 전 차단', async () => {
  const { world, client, binding } = revisionRequestWorld();
  const good = revisionCommand(binding, world.feedback);
  for (const corrupt of [
    command => { command.client_request_id = ''; }, command => { command.client_request_id = 'x'.repeat(161); },
    command => { command.target.request_id = 'artifact_' + secondRoundId; },
    command => { command.target.task_id = '../task'; }, command => { command.target.subject_id = 'OTHER'; },
    command => { command.feedback = ' not-trimmed '; }, command => { command.feedback = 'x'.repeat(32001); },
    command => { command.input_draft.revision = 0; }, command => { command.input_draft.digest = 'bad'; },
    command => { command.input_draft.draft_id = ''; },
  ]) {
    const command = structuredClone(good); corrupt(command);
    await assert.rejects(client.submit(command), error => error.status === 422 && error.reasonCode === 'REVISION_INPUT_INVALID');
  }
  assert.equal(calls.length, 0);
});
await test('수정 접수 API exact POST·원 요청 키 GET·원문 참조 복제·실행 없음', async () => {
  const { world, client, binding } = revisionRequestWorld('SYNTHETIC/PROJECT');
  const command = revisionCommand(binding, world.feedback, 'SYNTHETIC request/?#');
  const receipt = await client.submit(command), frozen = structuredClone(receipt);
  assert.deepEqual(bodyOf(writes()[0]), command);
  assert.equal(writes()[0].url, '/api/v1/factory/SYNTHETIC%2FPROJECT/sprint/revision-requests');
  assert.equal(receipt.execution_started, false); assert.equal(receipt.status, 'ACCEPTED');
  receipt.target.task_id = 'LOCAL_MUTATION';
  const read = await client.read(command, frozen);
  assert.deepEqual(read, frozen);
  assert.equal(calls.at(-1).url, '/api/v1/factory/SYNTHETIC%2FPROJECT/sprint/revision-requests/' + encodeURIComponent(command.client_request_id));
  assert.equal(writes().length, 1);
});
await test('수정 접수 API 악성 접수증의 대상6키·초안3키·작업·날짜·실행 상태 거절', async () => {
  const { world, client, binding } = revisionRequestWorld();
  const command = revisionCommand(binding, world.feedback), valid = world.commit(binding.projectId, command);
  const corruptions = [
    row => { row.request_id = 'OTHER_REQUEST'; }, row => { row.project_id = 'OTHER_PROJECT'; },
    row => { row.submission_id = ''; }, row => { row.actor_id = ''; },
    row => { row.task_id = 'NOT_REVISION_TASK'; }, row => { row.task_id = command.target.task_id; },
    row => { row.status = 'RUNNING'; }, row => { row.execution_started = true; },
    row => { row.created_at = 'not-a-date'; }, row => { row.feedback += '다른 내용'; },
    ...['kind', 'task_id', 'decision_kind', 'request_id', 'target_digest', 'subject_id'].map(field =>
      row => { row.target[field] = 'OTHER'; }),
    ...['draft_id', 'revision', 'digest'].map(field => row => { row.input_draft[field] = field === 'revision' ? 2 : 'OTHER'; }),
  ];
  for (const corrupt of corruptions) {
    const row = structuredClone(valid); corrupt(row);
    world.read = async () => response({ status: 'success', data: row });
    await assert.rejects(client.read(command), error => error.status === 503 && error.reasonCode === 'REVISION_RESPONSE_INVALID');
  }
  world.read = async () => response({ status: 'success', data: [] });
  await assert.rejects(client.read(command), error => error.reasonCode === 'REVISION_RESPONSE_INVALID');
  assert.equal(writes().length, 0);
});
await test('수정 접수 API POST 후 GET은 원 접수증 actor/task/submission/created_at까지 일치', async () => {
  const { world, client, binding } = revisionRequestWorld();
  const command = revisionCommand(binding, world.feedback), expected = await client.submit(command);
  for (const patch of [{ actor_id: 'OTHER_ACTOR' }, { task_id: 'TASK_REV_OTHER' },
    { submission_id: 'OTHER_SUBMISSION' }, { created_at: '2026-09-13T12:00:01.000Z' }]) {
    world.read = async () => response({ status: 'success', data: { ...expected, ...patch } });
    await assert.rejects(client.read(command, expected), error => error.status === 503 && error.reasonCode === 'REVISION_RESPONSE_INVALID');
  }
  world.read = null;
  assert.deepEqual(await client.read(command, expected), expected);
  assert.equal(writes().length, 1);
});
await test('수정 접수 UNIT preflight 산출물 교체는 POST 0·원 의견/저장 참조 불변', async () => {
  const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
  await authorize();
  const target = structuredClone(binding.target), draft = structuredClone(binding.draft), original = structuredClone(draft);
  binding.target = { ...binding.target, target_digest: secondRoundId, request_id: 'artifact_' + secondRoundId };
  binding.draft.target = structuredClone(binding.target);
  assert.equal(await flow.submit(target, world.feedback, draft), null);
  assert.equal(flow.getSnapshot().error.reasonCode, 'REVISION_BASIS_CHANGED');
  assert.deepEqual(draft, original); assert.deepEqual(flow.getSnapshot().records, []);
  assert.equal(writes().length, 0);
});
await test('수정 접수 UNIT preflight 저장 초안 ID/revision/digest/본문/상태 변경은 POST 0', async () => {
  for (const mutate of [
    draft => { draft.draft_id = 'OTHER_SAVED_DRAFT'; }, draft => { draft.revision = 2; },
    draft => { draft.digest = secondRoundId; }, draft => { draft.content.text = '나중에 저장한 의견'; },
    draft => { draft.status = 'CONSUMED'; draft.restorable = false; }, draft => { draft.content = null; },
  ]) {
    const { world, flow, binding, authorize } = revisionRequestWorld();
    await authorize(); const original = structuredClone(binding.draft);
    mutate(binding.draft);
    assert.equal(await flow.submit(binding.target, world.feedback, original), null);
    assert.equal(flow.getSnapshot().error.reasonCode, 'REVISION_BASIS_CHANGED');
    assert.deepEqual(flow.getSnapshot().records, []); assert.equal(writes().length, 0);
  }
});
await test('수정 접수 UNIT UNKNOWN 선저장→RECORDED→동일 GET CONFIRMED 순서·자동 실행/consume 없음', async () => {
  const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
  await authorize();
  const outcomes = [];
  const unsubscribe = flow.subscribe(() => {
    const record = flow.getSnapshot().records[0]; if (record) outcomes.push(record.outcome);
  });
  world.post = async (command, project) => {
    const record = flow.getSnapshot().records[0];
    assert.equal(record.outcome, 'UNKNOWN'); assert.equal(record.receipt, null);
    assert.deepEqual(record.command, command);
    return response({ status: 'success', data: world.commit(project, command) });
  };
  let receipt;
  try { receipt = await submitRevision(fixture); } finally { unsubscribe(); }
  assert.deepEqual([...new Set(outcomes)], ['UNKNOWN', 'RECORDED', 'CONFIRMED']);
  assert.equal(receipt.execution_started, false); assert.equal(flow.getSnapshot().busy, false);
  const command = flow.getSnapshot().records[0].command;
  assert.match(command.client_request_id, /^[0-9a-f-]{36}$/);
  assert.deepEqual(command, revisionCommand(binding, world.feedback, command.client_request_id));
  assert.deepEqual(calls.map(call => call.options.method || 'GET'), ['GET', 'GET', 'POST', 'GET']);
  assert.ok(calls.every(call => !/\/consume|\/start|\/execute|\/backlog/.test(call.url)));
  assert.equal(writes().length, 1);
});
await test('수정 접수 UNIT UNKNOWN 조회404는 원키 보존·재진입 재인가 후 GET만 복구', async () => {
  const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
  await authorize();
  world.post = async () => { throw new Error('합성 접수 응답 유실'); };
  assert.equal(await submitRevision(fixture), null);
  const original = structuredClone(flow.getSnapshot().records[0]);
  assert.equal(original.outcome, 'UNKNOWN'); assert.equal(await submitRevision(fixture), null);
  assert.equal(await flow.recheck(original.command.client_request_id), null);
  assert.equal(flow.getSnapshot().error.status, 404); assert.equal(flow.getSnapshot().authorized, false);
  assert.deepEqual(flow.getSnapshot().records, []);
  assert.deepEqual(memory.studioInputMemory.projectValues(binding.projectId, 'revision-request')[0], original);
  flow.invalidate();
  const reopened = world.open();
  assert.deepEqual(reopened.flow.getSnapshot().records, []);
  const count = calls.length;
  assert.equal(await reopened.flow.recheck(original.command.client_request_id), null);
  assert.equal(calls.length, count);
  await reopened.authorize();
  assert.deepEqual(reopened.flow.getSnapshot().records[0].command, original.command);
  world.commit(binding.projectId, original.command);
  const verified = await reopened.flow.recheck(original.command.client_request_id);
  assert.equal(verified.request_id, original.command.client_request_id);
  assert.equal(reopened.flow.getSnapshot().records[0].outcome, 'CONFIRMED');
  assert.equal(writes().length, 1);
});
await test('수정 접수 UNIT RECORDED GET503·다른 사건 응답은 원 접수증 보존 후 같은 GET 복구', async () => {
  const fixture = revisionRequestWorld(), { world, flow, authorize } = fixture;
  await authorize();
  world.read = async () => response({ detail: { message: '합성 접수 조회 장애' } }, 503);
  assert.equal(await submitRevision(fixture), null);
  const original = structuredClone(flow.getSnapshot().records[0]);
  assert.equal(original.outcome, 'RECORDED'); assert.ok(original.receipt.submission_id);
  world.read = async receipt => response({ status: 'success', data: { ...receipt, submission_id: 'OTHER_SUBMISSION' } });
  assert.equal(await flow.recheck(original.command.client_request_id), null);
  assert.equal(flow.getSnapshot().error.reasonCode, 'REVISION_RESPONSE_INVALID');
  assert.deepEqual(flow.getSnapshot().records[0], original);
  assert.equal(await submitRevision(fixture), null);
  world.read = null;
  assert.deepEqual(await flow.recheck(original.command.client_request_id), original.receipt);
  assert.equal(flow.getSnapshot().records[0].outcome, 'CONFIRMED'); assert.equal(writes().length, 1);
});
await test('수정 접수 UNIT 최초 POST 명시4xx는 REJECTED·자동 재전송 없음', async () => {
  for (const status of [400, 401, 403, 404, 409, 422]) {
    const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
    await authorize();
    world.post = async () => response({ detail: { reason_code: 'EXPLICIT_REJECTION', message: '합성 명시 거절' } }, status);
    assert.equal(await submitRevision(fixture), null);
    const record = memory.studioInputMemory.projectValues(binding.projectId, 'revision-request')[0];
    assert.equal(record.outcome, 'REJECTED'); assert.equal(record.receipt, null);
    assert.equal(flow.getSnapshot().error.status, status); assert.equal(flow.getSnapshot().busy, false);
    const count = calls.length; await flow.recheck(record.command.client_request_id);
    assert.equal(calls.length, count); assert.equal(writes().length, 1);
  }
});
await test('수정 접수 UNIT 확인된 동일 저장 참조 중복 차단·새 초안 revision은 새 요청 키', async () => {
  const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
  await authorize(); const first = await submitRevision(fixture);
  const count = calls.length;
  assert.equal(flow.canSubmit(binding.target, world.feedback.trim(), binding.draft), false);
  assert.equal(await submitRevision(fixture), null); assert.equal(calls.length, count);
  binding.draft = { ...binding.draft, revision: 2, digest: secondRoundId };
  assert.equal(flow.canSubmit(binding.target, world.feedback, binding.draft), true);
  const second = await submitRevision(fixture);
  assert.notEqual(second.request_id, first.request_id); assert.notEqual(second.task_id, first.task_id);
  assert.equal(second.input_draft.revision, 2); assert.equal(writes().length, 2);
  assert.deepEqual(flow.getSnapshot().records.map(record => record.outcome), ['CONFIRMED', 'CONFIRMED']);
});
await test('수정 접수 UNIT 미확정 요청은 같은 프로젝트 타작업도 차단·다른 프로젝트 허용', async () => {
  const fixture = revisionRequestWorld(), { world, binding, authorize } = fixture;
  await authorize(); world.post = async () => { throw new Error('합성 응답 유실'); };
  await submitRevision(fixture);
  const same = world.open(binding.projectId, 'SYNTHETIC_OTHER_TASK');
  await same.authorize();
  assert.equal(same.flow.canSubmit(same.binding.target, world.feedback, same.binding.draft), false);
  const count = calls.length;
  assert.equal(await same.flow.submit(same.binding.target, world.feedback, same.binding.draft), null);
  assert.equal(calls.length, count);
  const other = world.open('SYNTHETIC_OTHER_PROJECT', 'SYNTHETIC_OTHER_TASK');
  await other.authorize();
  assert.deepEqual(other.flow.getSnapshot().records, []);
  assert.equal(other.flow.canSubmit(other.binding.target, world.feedback, other.binding.draft), true);
  world.post = null;
  assert.equal((await other.flow.submit(other.binding.target, world.feedback, other.binding.draft)).status, 'ACCEPTED');
  assert.equal(writes().length, 2);
});
await test('수정 접수 UNIT 두 패널 preflight 경합·중복 클릭은 예약 재검증으로 POST 하나', async () => {
  const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
  const other = world.open(binding.projectId, 'SYNTHETIC_OTHER_TASK');
  await authorize(); await other.authorize();
  const entered = deferred(), finish = deferred();
  world.targetRead = async (data, current) => {
    if (current.taskId === binding.taskId) { entered.resolve(); await finish.promise; }
    return response({ status: 'success', data });
  };
  world.post = async () => { throw new Error('첫 접수 미확정'); };
  const pending = submitRevision(fixture);
  try {
    await bounded(entered.promise);
    const count = calls.length;
    assert.equal(await submitRevision(fixture), null); assert.equal(calls.length, count);
    await other.flow.submit(other.binding.target, world.feedback, other.binding.draft);
    assert.equal(writes().length, 1);
  } finally { finish.resolve(); await bounded(pending); }
  assert.equal(flow.getSnapshot().error.reasonCode, 'REVISION_ALREADY_PENDING');
  assert.equal(flow.getSnapshot().busy, false); assert.equal(writes().length, 1);
});
await test('수정 접수 UNIT preflight 중 문맥 변경은 POST 0·늦은 응답 비노출', async () => {
  const fixture = revisionRequestWorld(), { world, flow, authorize } = fixture;
  await authorize(); const entered = deferred(), finish = deferred();
  world.targetRead = async data => { entered.resolve(); await finish.promise; return response({ status: 'success', data }); };
  const pending = submitRevision(fixture);
  try {
    await bounded(entered.promise); identity.scopeNodeId = 'SYNTHETIC_OTHER_SCOPE'; flow.invalidate();
  } finally { finish.resolve(); await bounded(pending); }
  assert.equal(flow.getSnapshot().authorized, false); assert.deepEqual(flow.getSnapshot().records, []);
  assert.equal(flow.getSnapshot().busy, false); assert.equal(writes().length, 0);
});
await test('수정 접수 UNIT POST 중 문맥 변경은 영수증 숨김·왕복 시 같은 원키 조회만', async () => {
  const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
  await authorize(); const entered = deferred(), finish = deferred();
  world.post = async (command, project) => {
    const receipt = world.commit(project, command);
    entered.resolve(); await finish.promise; return response({ status: 'success', data: receipt });
  };
  const pending = submitRevision(fixture);
  let requestId;
  try {
    await bounded(entered.promise); requestId = flow.getSnapshot().records[0].command.client_request_id;
    identity.scopeNodeId = 'SYNTHETIC_OTHER_SCOPE'; flow.invalidate();
  } finally { finish.resolve(); await bounded(pending); }
  assert.deepEqual(flow.getSnapshot().records, []);
  const otherScope = world.open();
  await otherScope.authorize(); assert.deepEqual(otherScope.flow.getSnapshot().records, []);
  otherScope.flow.invalidate(); identity.scopeNodeId = syntheticIdentity.scopeNodeId;
  const reopened = world.open(); await reopened.authorize();
  assert.equal(reopened.flow.getSnapshot().records[0].outcome, 'UNKNOWN');
  const receipt = await reopened.flow.recheck(requestId);
  assert.equal(receipt.project_id, binding.projectId); assert.equal(receipt.request_id, requestId);
  assert.equal(reopened.flow.getSnapshot().records[0].outcome, 'CONFIRMED');
  assert.equal(writes().length, 1);
});
await test('수정 접수 UNIT 악성 POST 응답/503는 UNKNOWN·원본문 유지·자동 재POST 없음', async () => {
  for (const failure of ['malformed', '503']) {
    const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
    await authorize();
    world.post = async (command, project) => {
      if (failure === '503') return response({ detail: { message: '합성 접수 장애', reason_code: 'OUTCOME_UNKNOWN' } }, 503);
      const receipt = world.commit(project, command); receipt.input_draft.digest = secondRoundId;
      return response({ status: 'success', data: receipt });
    };
    assert.equal(await submitRevision(fixture), null);
    const record = structuredClone(flow.getSnapshot().records[0]);
    assert.equal(record.outcome, 'UNKNOWN'); assert.equal(record.receipt, null);
    assert.deepEqual(record.command, revisionCommand(binding, world.feedback, record.command.client_request_id));
    assert.equal(await submitRevision(fixture), null); assert.equal(writes().length, 1);
  }
});
await test('수정 접수 UNIT 권한 상실은 기록 숨김·현재 대상 GET 재인가 전 복구 불가', async () => {
  const fixture = revisionRequestWorld(), { world, flow, authorize } = fixture;
  await authorize();
  world.read = async () => response({ detail: { message: '합성 조회 장애' } }, 503);
  await submitRevision(fixture);
  const original = structuredClone(flow.getSnapshot().records[0]);
  world.read = async () => response({ detail: { reason_code: 'FORBIDDEN', message: '합성 권한 회수' } }, 403);
  await flow.recheck(original.command.client_request_id);
  assert.equal(flow.getSnapshot().authorized, false); assert.deepEqual(flow.getSnapshot().records, []);
  const count = calls.length;
  await flow.recheck(original.command.client_request_id); assert.equal(calls.length, count);
  world.read = null; await authorize();
  assert.deepEqual(flow.getSnapshot().records[0], original);
  assert.equal((await flow.recheck(original.command.client_request_id)).submission_id, original.receipt.submission_id);
  assert.equal(writes().length, 1);
});
await test('수정 접수 UNIT 대상 GET409/503에도 recover는 원키 GET 한행만 공개·새 제출 권한 없음', async () => {
  for (const status of [409, 503]) {
    const fixture = revisionRequestWorld(), { world, flow, binding, inputApi, authorize } = fixture;
    await authorize(); const previous = await submitRevision(fixture);
    binding.draft = { ...binding.draft, revision: 2, digest: secondRoundId };
    world.post = async (command, project) => { world.commit(project, command); throw new Error('합성 접수 응답 유실'); };
    await submitRevision(fixture);
    const original = structuredClone(flow.getSnapshot().records.find(record => record.outcome === 'UNKNOWN'));
    flow.invalidate(); assert.equal(flow.hasRecovery(), false);
    flow.activate(); assert.equal(flow.hasRecovery(), true);
    assert.deepEqual(flow.getSnapshot().records, []);
    world.targetRead = async () => response({ detail: { message: '합성 현재 산출물 조회 실패' } }, status);
    await assert.rejects(inputApi.target({ kind: 'REVISION_REQUEST', task_id: binding.taskId }), error => error.status === status);
    const count = calls.length, postCount = writes().length;
    const receipt = await flow.recover();
    assert.equal(receipt.request_id, original.command.client_request_id);
    assert.notEqual(receipt.request_id, previous.request_id);
    assert.equal(flow.getSnapshot().authorized, false);
    assert.equal(flow.getSnapshot().records.length, 1);
    assert.equal(flow.getSnapshot().records[0].outcome, 'CONFIRMED');
    assert.deepEqual(flow.getSnapshot().records[0].command, original.command);
    assert.deepEqual(calls.slice(count).map(call => [call.options.method || 'GET', call.url]),
      [['GET', '/api/v1/factory/' + binding.projectId + '/sprint/revision-requests/' + original.command.client_request_id]]);
    assert.equal(flow.canSubmit(binding.target, world.feedback, binding.draft), false);
    assert.equal(await submitRevision(fixture), null); assert.equal(writes().length, postCount);
  }
});
await test('수정 접수 UNIT 비인가 recover 권한거절은 본문 비노출·원키 보존·POST 0', async () => {
  for (const status of [401, 403]) {
    const fixture = revisionRequestWorld(), { world, flow, binding, inputApi, authorize } = fixture;
    await authorize(); world.post = async () => { throw new Error('합성 접수 응답 유실'); };
    await submitRevision(fixture);
    const original = structuredClone(flow.getSnapshot().records[0]);
    flow.invalidate(); flow.activate();
    world.targetRead = async () => response({ detail: { message: '합성 현재 대상 조회 불가' } }, 503);
    await assert.rejects(inputApi.target({ kind: 'REVISION_REQUEST', task_id: binding.taskId }), error => error.status === 503);
    world.read = async () => response({ detail: { message: '합성 원접수 조회 권한 거절', reason_code: 'FORBIDDEN' } }, status);
    const count = calls.length, postCount = writes().length;
    assert.equal(flow.hasRecovery(), true); assert.equal(await flow.recover(), null);
    assert.equal(flow.getSnapshot().authorized, false); assert.equal(flow.getSnapshot().busy, false);
    assert.deepEqual(flow.getSnapshot().records, []); assert.equal(flow.getSnapshot().error.status, status);
    assert.deepEqual(memory.studioInputMemory.projectValues(binding.projectId, 'revision-request')[0], original);
    assert.deepEqual(calls.slice(count).map(call => call.options.method || 'GET'), ['GET']);
    assert.equal(await submitRevision(fixture), null); assert.equal(writes().length, postCount);
  }
});
await test('수정 접수 UNIT 다건 recover A→B→A 순환·invalidate 초기화·매 GET 검증 한행만 공개', async () => {
  const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
  await authorize(); const first = await submitRevision(fixture);
  binding.draft = { ...binding.draft, revision: 2, digest: secondRoundId };
  const second = await submitRevision(fixture);
  assert.notEqual(first.request_id, second.request_id);
  flow.invalidate(); flow.activate();
  world.targetRead = async () => { throw new Error('과거 접수 복구는 현재 대상 GET을 요구하지 않는다'); };
  world.read = async receipt => {
    // 응답 검증 전에는 직전 조회 건을 포함해 과거 본문이 보이지 않아야 한다.
    assert.equal(flow.getSnapshot().busy, true);
    assert.equal(flow.getSnapshot().authorized, false);
    assert.deepEqual(flow.getSnapshot().records, []);
    return response({ status: 'success', data: receipt });
  };
  const count = calls.length, postCount = writes().length;
  for (const expected of [first, second, first]) {
    assert.equal(flow.hasRecovery(), true);
    assert.deepEqual(await flow.recover(), expected);
    assert.equal(flow.getSnapshot().records.length, 1);
    assert.deepEqual(flow.getSnapshot().records[0].receipt, expected);
    assert.equal(flow.getSnapshot().records[0].command.client_request_id, expected.request_id);
    assert.equal(flow.getSnapshot().authorized, false);
    assert.equal(flow.getSnapshot().busy, false);
  }
  // A 다음 차례는 B지만 invalidate 이후에는 성공 조회 집합이 초기화되어 다시 A부터 확인한다.
  flow.invalidate(); assert.equal(flow.hasRecovery(), false); assert.deepEqual(flow.getSnapshot().records, []);
  flow.activate();
  assert.deepEqual(await flow.recover(), first);
  assert.equal(flow.getSnapshot().records.length, 1);
  assert.deepEqual(flow.getSnapshot().records[0].receipt, first);
  assert.deepEqual(calls.slice(count).map(call => [call.options.method || 'GET', call.url]),
    [first, second, first, first].map(receipt =>
      ['GET', '/api/v1/factory/' + binding.projectId + '/sprint/revision-requests/' + receipt.request_id]));
  assert.equal(flow.getSnapshot().authorized, false);
  assert.equal(flow.canSubmit(binding.target, world.feedback, binding.draft), false);
  assert.equal(await submitRevision(fixture), null); assert.equal(writes().length, postCount);
});
await test('수정 접수 UNIT 실패한 UNKNOWN A를 보존하며 B 복구 가능·재POST 없음', async () => {
  for (const status of [404, 503]) {
    const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
    await authorize(); const first = await submitRevision(fixture);
    binding.draft = { ...binding.draft, revision: 2, digest: secondRoundId };
    const second = await submitRevision(fixture);
    const key = memory.studioInputKey(binding.projectId, 'revision-request', first.request_id);
    const original = { ...memory.studioInputMemory.get(key, null), outcome: 'UNKNOWN', receipt: null };
    memory.studioInputMemory.set(key, original);
    flow.invalidate(); flow.activate();
    world.read = async receipt => receipt.request_id === first.request_id
      ? response({ detail: { message: '첫 요청 조회 실패' } }, status)
      : response({ status: 'success', data: receipt });
    const count = calls.length, postCount = writes().length;
    assert.equal(await flow.recover(), null);
    assert.deepEqual(flow.getSnapshot().records, []);
    assert.deepEqual(await flow.recover(), second);
    assert.deepEqual(flow.getSnapshot().records.map(record => record.receipt.request_id), [second.request_id]);
    assert.deepEqual(memory.studioInputMemory.get(key, null), original);
    assert.equal(flow.getSnapshot().authorized, false);
    assert.equal(await flow.recover(), null);
    assert.deepEqual(calls.slice(count).map(call => call.url.split('/').at(-1)), [first.request_id, second.request_id, first.request_id]);
    assert.equal(writes().length, postCount);
  }
});
function revisionRequestHtml(fixture) {
  // 준비한 실제 flow를 컴포넌트 생성 경계에 주입한다. React 효과/이벤트는 실행하지 않는 SSR 검사다.
  const ui = load('../src/factory/RevisionRequestEditor.tsx', {
    '../lib/studioInputDraftApi': draftApi, './StudioInputDraftControls': draftControls, './studioInputMemory': memory,
    '../lib/studioRevisionApi': revisionApi,
    '../lib/studioRevisionFlow': { ...revisionFlow, createStudioRevisionFlow: (project, task) => {
      assert.equal(project, fixture.binding.projectId); assert.equal(task, fixture.binding.taskId);
      return fixture.flow;
    } },
  });
  const count = calls.length;
  const html = renderToStaticMarkup(React.createElement(ui.RevisionRequestEditor, {
    projectId: fixture.binding.projectId, taskId: fixture.binding.taskId,
    onSubmitted: () => { throw new Error('SSR에서 접수 후처리를 실행하면 안 된다'); },
  }));
  assert.equal(calls.length, count);
  return html;
}
await test('수정 접수 SSR 실제 화면의 미확인/UNKNOWN/확인된 접수·권한 상실 표시 구별', async () => {
  const fixture = revisionRequestWorld(), { world, flow, binding, authorize } = fixture;
  let html = revisionRequestHtml(fixture);
  assert.match(html, /수정 요청 작성/);
  assert.match(html, /class="primary-button" disabled=""/);
  assert.match(html, /접수는 실행이나 수정 완료가 아니며/);
  assert.doesNotMatch(html, /수정 요청 처리 기록/);
  await authorize();
  world.post = async () => { throw new Error('합성 응답 유실'); };
  await submitRevision(fixture);
  const record = structuredClone(flow.getSnapshot().records[0]);
  html = revisionRequestHtml(fixture);
  assert.match(html, /접수 결과 미확정/); assert.match(html, /GET 조회만/);
  assert.ok(html.includes(record.command.client_request_id));
  assert.doesNotMatch(html, /서버 접수 확인 · 실행 전/);
  world.commit(binding.projectId, record.command);
  await flow.recheck(record.command.client_request_id);
  html = revisionRequestHtml(fixture);
  assert.match(html, /서버 접수 확인 · 실행 전/); assert.match(html, /접수증:/);
  assert.ok(html.includes(flow.getSnapshot().records[0].receipt.submission_id));
  assert.match(html, /서버 접수 확인, 실행은 시작하지 않음/);
  assert.doesNotMatch(html, /이 요청의 접수 상태 확인 · GET 조회만/);
  flow.invalidate(); html = revisionRequestHtml(fixture);
  assert.doesNotMatch(html, /수정 요청 처리 기록/);
  assert.ok(!html.includes(record.command.client_request_id));
  assert.ok(!html.includes(record.command.feedback)); assert.equal(writes().length, 1);
});
await test('수정 접수 STATIC 정규화 본문 매칭·저장 증거 무효화·원초안 consume/새 의견 배선', () => {
  // 코드 연결만 확인한다. 브라우저 클릭이나 서버 consume/원장 검증의 통과가 아니다.
  const editor = fs.readFileSync(new URL('../src/factory/RevisionRequestEditor.tsx', import.meta.url), 'utf8');
  const controls = fs.readFileSync(new URL('../src/factory/StudioInputDraftControls.tsx', import.meta.url), 'utf8');
  assert.match(editor, /onDraftChange=\{setSavedDraft\}/);
  // 서버의 selections:{}와 같은 본문을 작성·영수증 양쪽에서 전달해야 실제 저장 확인이 성립한다.
  assert.match(editor, /content=\{\{ text: visible\.text\.trim\(\), decision: '', selections: \{\} \}\}/);
  assert.match(editor, /content=\{\{ text: record\.command\.feedback, decision: '', selections: \{\} \}\}/);
  const update = editor.slice(editor.indexOf('const updateText ='), editor.indexOf('const notifyReceipt ='));
  assert.match(update, /setSavedDraft\(null\)/);
  assert.match(editor, /flow\.canSubmit\(input\.target, input\.text, savedDraft\)/);
  assert.match(editor, /await flow\.submit\(input\.target, input\.text, savedDraft\)/);
  const refreshStart = editor.indexOf('const refresh =');
  const refreshEnd = editor.indexOf('useEffect(() => {', refreshStart);
  assert.ok(refreshStart >= 0 && refreshEnd > refreshStart);
  const refresh = editor.slice(refreshStart, refreshEnd);
  assert.ok(refresh.indexOf('await api.target(') >= 0);
  assert.ok(refresh.indexOf('flow.authorize(target)') > refresh.indexOf('await api.target('));
  assert.match(editor, /record\.outcome === 'CONFIRMED' && record\.receipt/);
  assert.match(editor, /expectedTarget=\{record\.command\.target\}/);
  assert.match(editor, /expectedDraft=\{record\.receipt\.input_draft\}/);
  assert.match(editor, /receiptOnly submissionId=\{record\.receipt\.submission_id\}/);
  assert.match(editor, /onConsumed=\{recordConsumed\}/);
  assert.match(editor, /acceptedRecords\.every\(record => record\.receipt && consumedIds\.includes\(record\.receipt\.submission_id\)\)/);
  assert.match(editor, /onClick=\{startOpinion\}>같은 기준에 새 의견 작성/);
  assert.match(editor, /await flow\.recover\(\)/);
  assert.match(controls, /!local\.attempt && !local\.consumeAttempt/);
  assert.match(controls, /local\.savedContent === canonical\(content\)/);
  assert.match(controls, /canonical\(local\.draft\.content\) === canonical\(content\)/);
  assert.match(controls, /savedContent: canonical\(body\.content\)/);
  assert.match(controls, /savedContent: result\.draft\?\.restorable && result\.draft\.content \? canonical\(result\.draft\.content\)/);
  assert.match(controls, /onDraftChange\(active\.current && identity === studioIdentityKey\(\) && verifiedDraft/);
  assert.match(controls, /onDraftChange\?\.\(null\)/);
  assert.match(controls, /expectedDraft\.draft_id === id && expectedDraft\.revision === revision && expectedDraft\.digest === digest/);
  assert.match(controls, /if \(!submissionId \|\| consumed \|\| !originalDraft/);
});
const revisionChecks = results.length - preRevisionChecks;
const preExecutionChecks = results.length;
await test('실행 접수 API 독립 canonical SHA256·한글 입력·원키 POST/GET 일치', async () => {
  const world = executionWorld('SYNTHETIC_EXECUTION_CANONICAL');
  const input = { master_data: '합성 참조', initial_idea: '입고를 쉽게' };
  assert.equal(executionCanonical({ z: [true, { 나: 2, a: 1 }], a: null }), '{"a":null,"z":[true,{"a":1,"나":2}]}');
  world.post = command => {
    const receipt = world.commit(command);
    // 객체 삽입 순서는 서명 의미가 아니며 문자열·배열 순서는 의미를 유지한다.
    return response({ request: Object.fromEntries(Object.entries(receipt).reverse()) });
  };
  const attempt = await executionApi.executeStudioCommand(world.projectId, 'START', 'TASK_1', input);
  assert.equal(attempt.outcome, 'CONFIRMED');
  assert.deepEqual(calls.map(call => call.options.method || 'GET'), ['POST', 'GET']);
  const sent = bodyOf(writes()[0]);
  assert.deepEqual(sent, { client_request_id: attempt.request.client_request_id, operation: 'START', task_id: 'TASK_1', input });
  assert.match(sent.client_request_id, /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/);
  assert.equal(attempt.receipt.command_digest, executionHash(sent));
  assert.equal(attempt.receipt.receipt_digest, sealExecutionReceipt(attempt.receipt).receipt_digest);
  assert.ok(calls[1].url.endsWith('/execution-commands/' + sent.client_request_id));
  input.initial_idea = '호출자 뒤늦은 수정';
  assert.equal(executionApi.getExecutionRecords(world.projectId)[0].request.input.initial_idea, '입고를 쉽게');
  assert.match(attempt.message, /접수.*실제 실행 상태는 별도로/);
  assert.equal(executionApi.hasExecutionPending(world.projectId), false);
});
// ── [B5] 프로젝트 단위 명령(릴리스 저장·작업 재분할) ──────────────────────────
await test('B5 릴리스 저장은 원키 접수 기록을 남기고 고정 task_id 로 보낸다', async () => {
  const world = executionWorld();
  const result = await actions.saveProjectRelease(world.projectId);
  assert.equal(result.ok, true); assert.equal(result.outcome, 'CONFIRMED');
  assert.equal(result.releaseId, 'rel-synthetic-1');
  const sent = bodyOf(writes()[0]);
  assert.equal(sent.operation, 'RELEASE'); assert.equal(sent.task_id, 'PROJECT');
  assert.deepEqual(sent.input, {});
  assert.match(sent.client_request_id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  // 접수 확인은 원키 GET 뒤에만 이뤄진다.
  assert.ok(calls.some(call => call.options.method !== 'POST' && call.url.endsWith('/' + sent.client_request_id)));
});
await test('B5 작업 재분할은 원키 접수 기록을 남기고 서버가 정한 새 task 를 받는다', async () => {
  const world = executionWorld();
  const result = await actions.replanWbs(world.projectId);
  assert.equal(result.ok, true); assert.equal(result.outcome, 'CONFIRMED');
  assert.equal(result.taskId, 'TASK_REPLANNED_1');
  const sent = bodyOf(writes()[0]);
  assert.equal(sent.operation, 'REPLAN'); assert.equal(sent.task_id, 'PROJECT');
});
await test('B5 재분할 응답 유실은 UNKNOWN 으로 남고 다시 눌러도 WBS 를 또 지우지 않는다', async () => {
  const world = executionWorld();
  world.post = () => { throw new Error('합성 응답 유실'); };
  const first = await actions.replanWbs(world.projectId);
  assert.equal(first.outcome, 'UNKNOWN');
  assert.equal(writes().length, 1);
  // 되돌릴 수 없는 명령이므로 결과 확인 전 재실행을 막는다.
  assert.equal((await actions.replanWbs(world.projectId)).outcome, 'REJECTED');
  assert.equal((await actions.saveProjectRelease(world.projectId)).outcome, 'REJECTED');
  assert.equal((await actions.startExistingTask(world.projectId, 'TASK_2')).outcome, 'REJECTED');
  assert.equal(writes().length, 1);
  assert.equal(executionApi.hasExecutionPending(world.projectId), true);
});
await test('B5 프로젝트 단위 명령의 잘못된 응답 모양은 CONFIRMED 로 세지 않는다', async () => {
  const world = executionWorld();
  // release_id 없는 성공 응답은 저장 증거가 아니다.
  world.commit = (command, patch = {}) => {
    const receipt = executionReceipt(world.projectId, command,
      { result: { http_status: 200, response: { status: 'success' } }, ...patch });
    world.receipts.set(command.client_request_id, receipt); return receipt;
  };
  const result = await actions.saveProjectRelease(world.projectId);
  assert.notEqual(result.outcome, 'CONFIRMED');
  assert.equal(result.releaseId, null);
});

await test('실행 접수 UNIT POST 접수만으로 잠금 해제 없음·같은 키 GET 후에만 CONFIRMED', async () => {
  const world = executionWorld();
  const entered = deferred(), finish = deferred();
  world.read = async id => { entered.resolve(id); await finish.promise; return response({ request: world.receipts.get(id) }); };
  const pending = executionApi.executeStudioCommand(world.projectId, 'START', 'TASK_1');
  try {
    const id = await bounded(entered.promise);
    const row = executionApi.getExecutionRecords(world.projectId)[0];
    assert.equal(row.request.client_request_id, id); assert.equal(row.receipt.status, 'ACCEPTED');
    assert.equal(row.outcome, 'UNKNOWN'); assert.equal(actions.isProjectCommandPending(world.projectId), true);
    assert.equal((await actions.startExistingTask(world.projectId, 'TASK_2')).outcome, 'REJECTED');
    assert.equal(writes().length, 1);
  } finally { finish.resolve(); await bounded(pending); }
  assert.equal(executionApi.getExecutionRecords(world.projectId)[0].outcome, 'CONFIRMED');
  assert.equal(actions.isProjectCommandPending(world.projectId), false);
});
await test('실행 접수 UNIT 응답 유실·GET404는 원키 UNKNOWN 보존·새 START/RESUME/HEAL POST0', async () => {
  const world = executionWorld();
  world.post = () => { throw new Error('합성 응답 유실'); };
  const first = await executionApi.executeStudioCommand(world.projectId, 'START', 'TASK_1', { feedback: '원 의견' });
  const frozen = structuredClone(first.request), id = frozen.client_request_id;
  assert.equal(first.outcome, 'UNKNOWN');
  for (const operation of ['START', 'RESUME', 'RESUME_QUOTA', 'HEAL']) {
    assert.equal((await executionApi.executeStudioCommand(world.projectId, operation, 'TASK_2')).outcome, 'REJECTED');
  }
  assert.equal(await executionApi.recoverExecutionRequest(world.projectId, id), null);
  assert.equal(executionApi.hasExecutionPending(world.projectId), true);
  assert.deepEqual(executionApi.getExecutionRecords(world.projectId), []);
  assert.equal(writes().length, 1);
  world.commit(frozen);
  assert.equal((await executionApi.recoverExecutionRequest(world.projectId, id)).request_id, id);
  assert.deepEqual(executionApi.getExecutionRecords(world.projectId)[0].request, frozen);
  assert.equal(executionApi.getExecutionRecords(world.projectId)[0].outcome, 'CONFIRMED');
  assert.equal(writes().length, 1);
  assert.ok(calls.filter(call => call.options.method !== 'POST').every(call => call.url.endsWith('/' + id)));
});
await test('실행 접수 API PROCESSING 고정 명령은 같은 actor·생성시각으로 ACCEPTED 전이 가능', async () => {
  const world = executionWorld();
  world.post = command => response({ request: world.commit(command, { status: 'PROCESSING', result: null }) });
  const first = await executionApi.executeStudioCommand(world.projectId, 'RESUME', 'PLANNING_123');
  assert.equal(first.outcome, 'UNKNOWN'); assert.equal(first.receipt.result, null);
  world.commit(first.request, { updated_at: '2026-09-13T13:01:00.000Z' });
  const receipt = await executionApi.recoverExecutionRequest(world.projectId, first.request.client_request_id);
  assert.equal(receipt.status, 'ACCEPTED'); assert.equal(executionApi.hasExecutionPending(world.projectId), false);
  assert.equal(writes().length, 1);
});
await test('실행 접수 API GET 다른 actor·본문·생성시각·확정 지문은 재해시돼도 거절', async () => {
  for (const change of [
    row => { row.actor_id = 'SYNTHETIC_OTHER_ACTOR'; },
    row => { row.input.feedback = '위조 의견'; row.command_digest = executionHash({
      client_request_id: row.request_id, operation: row.operation, task_id: row.task_id, input: row.input }); },
    row => { row.created_at = '2026-09-13T12:59:00.000Z'; },
    row => { row.updated_at = '2026-09-13T13:01:00.000Z'; },
    row => { row.result.response.task_id = 'OTHER_TASK'; },
  ]) {
    const world = executionWorld();
    world.read = id => { const row = structuredClone(world.receipts.get(id)); change(row); return response({ request: sealExecutionReceipt(row) }); };
    const attempt = await executionApi.executeStudioCommand(world.projectId, 'START', 'TASK_1', { feedback: '원 의견' });
    assert.equal(attempt.outcome, 'UNKNOWN'); assert.equal(executionApi.hasExecutionPending(world.projectId), true);
    assert.equal(attempt.request.input.feedback, '원 의견'); assert.equal(writes().length, 1);
    assert.equal(calls.length, 2);
  }
});
await test('실행 접수 API 악성 envelope·해시·필드·시각·result 형식은 GET승격 없이 UNKNOWN', async () => {
  const attacks = [
    row => ({ request: { ...row, receipt_digest: '0'.repeat(64) } }),
    row => ({ request: sealExecutionReceipt({ ...row, command_digest: '0'.repeat(64) }) }),
    row => ({ request: sealExecutionReceipt({ ...row, project_id: 'OTHER_PROJECT' }) }),
    row => ({ request: sealExecutionReceipt({ ...row, extra: true }) }),
    row => ({ request: sealExecutionReceipt({ ...row, created_at: 'invalid' }) }),
    row => ({ request: sealExecutionReceipt({ ...row, updated_at: '2026-09-13T12:59:00.000Z' }) }),
    row => ({ request: sealExecutionReceipt({ ...row, input: { ...row.input, runtime_document_version: '1.0' } }) }),
    row => ({ request: sealExecutionReceipt({ ...row, result: { http_status: 200, response: [] } }) }),
    row => ({ request: sealExecutionReceipt({ ...row, status: 'PROCESSING' }) }),
    row => ({ request: sealExecutionReceipt({ ...row, status: 'COMPLETE' }) }),
    row => ({ requests: [row] }),
  ];
  for (const attack of attacks) {
    const world = executionWorld();
    world.post = command => response(attack(world.commit(command)));
    const attempt = await executionApi.executeStudioCommand(world.projectId, 'START', 'TASK_1');
    assert.equal(attempt.outcome, 'UNKNOWN'); assert.equal(attempt.receipt, null);
    assert.equal(executionApi.hasExecutionPending(world.projectId), true);
    assert.equal(writes().length, 1); assert.equal(calls.length, 1);
  }
});
await test('실행 접수 UNIT 잘못된 작업 응답·reply status는 bridge UNKNOWN과 지속 잠금 일치', async () => {
  for (const [badResponse, httpStatus] of [
    [{ status: 'completed', task_id: 'TASK_1' }, 200], [{ status: 'started', task_id: 'OTHER_TASK' }, 200],
    [{}, 200], [{ status: 'started', task_id: 'TASK_1' }, 503],
  ]) {
    const world = executionWorld();
    world.post = command => response({ request: world.commit(command, { result: { http_status: httpStatus, response: badResponse } }) });
    const attempt = await actions.startExistingTask(world.projectId, 'TASK_1');
    assert.equal(attempt.outcome, 'UNKNOWN'); assert.equal(attempt.ok, false);
    assert.equal(executionApi.hasExecutionPending(world.projectId), true);
    assert.equal((await actions.startExistingTask(world.projectId, 'TASK_2')).outcome, 'REJECTED');
    assert.equal(writes().length, 1);
  }
});
await test('실행 접수 UNIT 명시 거절 영수증은 GET 확인 후 REJECTED·실제 작업 상태 미변경', async () => {
  const world = executionWorld();
  world.post = command => response({ request: world.commit(command, { status: 'REJECTED',
    result: { http_status: 409, response: { detail: { message: '합성 경합', reason_code: 'COMMAND_CONFLICT' } } } }) });
  const result = await actions.pauseSprint(world.projectId, 'TASK_1');
  assert.equal(result.outcome, 'REJECTED'); assert.equal(result.ok, false);
  assert.equal(result.reasonCode, 'COMMAND_CONFLICT'); assert.equal(result.status, 409);
  assert.match(result.message, /합성 경합/); assert.equal(executionApi.hasExecutionPending(world.projectId), false);
  assert.deepEqual(calls.map(call => call.options.method || 'GET'), ['POST', 'GET']);
});
await test('실행 접수 API 목록은 GET만·중복키/혼합actor/손상행 전체 거절·부분노출 없음', async () => {
  for (const mutate of [
    rows => [rows[0], rows[0]],
    rows => [rows[0], sealExecutionReceipt({ ...rows[1], actor_id: 'SYNTHETIC_OTHER_ACTOR' })],
    rows => [rows[0], { ...rows[1], receipt_digest: '0'.repeat(64) }],
  ]) {
    const world = executionWorld();
    const rows = ['TASK_1', 'TASK_2'].map(task_id => world.commit({ client_request_id: randomUUID(), operation: 'START', task_id, input: {} }));
    world.list = () => response({ requests: mutate(rows) });
    await assert.rejects(executionApi.refreshExecutionRecords(world.projectId));
    assert.deepEqual(executionApi.getExecutionRecords(world.projectId), []); assert.equal(writes().length, 0);
    assert.equal(executionApi.hasExecutionPending(world.projectId), false);
    world.list = null; await executionApi.refreshExecutionRecords(world.projectId);
    assert.equal(executionApi.getExecutionRecords(world.projectId).length, 2); assert.equal(writes().length, 0);
    // 이후 목록은 방금 서버가 공개한 행만 노출한다. 제외된 원키는 복구용으로만 유지한다.
    world.list = () => response({ requests: [rows[1]] });
    await executionApi.refreshExecutionRecords(world.projectId);
    assert.deepEqual(executionApi.getExecutionRecords(world.projectId).map(row => row.request.client_request_id), [rows[1].request_id]);
    assert.deepEqual(executionApi.getExecutionRecoveryIds(world.projectId).sort(), rows.map(row => row.request_id).sort());
    assert.equal(writes().length, 0);
  }
});
await test('실행 접수 UNIT 목록 권한거절은 본문 숨김·원키 GET 복구·빈 목록은 UNKNOWN 해제 아님', async () => {
  const world = executionWorld();
  world.post = () => { throw new Error('합성 유실'); };
  const pending = await executionApi.executeStudioCommand(world.projectId, 'START', 'TASK_1', { feedback: '비공개 원문' });
  for (const status of [401, 403, 404, 503]) {
    world.list = () => response({ detail: '합성 조회 실패' }, status);
    await assert.rejects(executionApi.refreshExecutionRecords(world.projectId));
    assert.deepEqual(executionApi.getExecutionRecords(world.projectId), []);
    assert.equal(executionApi.hasExecutionPending(world.projectId), true);
    assert.deepEqual(executionApi.getExecutionRecoveryIds(world.projectId), [pending.request.client_request_id]);
  }
  world.list = () => response({ requests: [] });
  await executionApi.refreshExecutionRecords(world.projectId);
  assert.deepEqual(executionApi.getExecutionRecords(world.projectId), []);
  assert.deepEqual(executionApi.getExecutionRecoveryIds(world.projectId), [pending.request.client_request_id]);
  assert.equal(executionApi.hasExecutionPending(world.projectId), true);
  world.commit(pending.request);
  assert.ok(await executionApi.recoverExecutionRequest(world.projectId, pending.request.client_request_id));
  assert.equal(writes().length, 1);
});
await test('실행 접수 UNIT 미보유 원키 GET 없음·동일 프로젝트 UNKNOWN에도 명시 PAUSE/STOP 별도 허용', async () => {
  const world = executionWorld();
  assert.equal(await executionApi.recoverExecutionRequest(world.projectId, randomUUID()), null);
  assert.equal(calls.length, 0);
  world.post = () => { throw new Error('합성 유실'); };
  const original = await executionApi.executeStudioCommand(world.projectId, 'START', 'TASK_1');
  world.post = null;
  const recoveryIds = [original.request.client_request_id];
  for (const op of ['PAUSE', 'STOP']) {
    const confirmed = await executionApi.executeStudioCommand(world.projectId, op, 'TASK_1');
    assert.equal(confirmed.outcome, 'CONFIRMED');
    recoveryIds.push(confirmed.request.client_request_id);
    assert.deepEqual(executionApi.getExecutionRecords(world.projectId).map(row => row.request.client_request_id), [confirmed.request.client_request_id]);
    assert.deepEqual(executionApi.getExecutionRecoveryIds(world.projectId).sort(), [...recoveryIds].sort());
    assert.equal(executionApi.hasExecutionPending(world.projectId), true);
  }
  assert.equal(writes().length, 3);
  world.commit(original.request, { status: 'PROCESSING', result: null });
  assert.ok(await executionApi.recoverExecutionRequest(world.projectId, original.request.client_request_id));
  const visible = executionApi.getExecutionRecords(world.projectId);
  assert.equal(visible.length, 1); assert.equal(visible[0].outcome, 'UNKNOWN');
  assert.deepEqual(visible[0].request, original.request);
  assert.deepEqual(executionApi.getExecutionRecoveryIds(world.projectId).sort(), recoveryIds.sort());
  assert.equal(writes().length, 3);
});
await test('실행 접수 UNIT POST 중 문맥 변경은 늦은 영수증 비노출·왕복 원키만 복구', async () => {
  const world = executionWorld();
  const entered = deferred(), finish = deferred();
  world.post = async command => { const receipt = world.commit(command); entered.resolve(command); await finish.promise; return response({ request: receipt }); };
  const promise = executionApi.executeStudioCommand(world.projectId, 'START', 'TASK_1', { feedback: 'A 문맥' });
  let original;
  try {
    original = await bounded(entered.promise); identity.scopeNodeId = 'SYNTHETIC_SCOPE_B';
    assert.deepEqual(executionApi.getExecutionRecords(world.projectId), []);
    assert.deepEqual(executionApi.getExecutionRecoveryIds(world.projectId), []);
    assert.equal(executionApi.hasExecutionPending(world.projectId), false);
  } finally { finish.resolve(); await bounded(promise); }
  assert.deepEqual(executionApi.getExecutionRecords(world.projectId), []);
  assert.equal(calls.length, 1);
  identity.scopeNodeId = 'SYNTHETIC_SCOPE_A';
  assert.deepEqual(executionApi.getExecutionRecords(world.projectId), []);
  assert.deepEqual(executionApi.getExecutionRecoveryIds(world.projectId), [original.client_request_id]);
  assert.equal(executionApi.hasExecutionPending(world.projectId), true);
  assert.ok(await executionApi.recoverExecutionRequest(world.projectId, original.client_request_id));
  assert.deepEqual(executionApi.getExecutionRecords(world.projectId)[0].request, original);
  assert.equal(writes().length, 1);
});
await test('실행 접수 UNIT 목록 JSON 해석 중 인증 변경은 늦은 기록 저장/노출 없음', async () => {
  const world = executionWorld();
  world.commit({ client_request_id: randomUUID(), operation: 'START', task_id: 'TASK_1', input: {} });
  const entered = deferred(), finish = deferred();
  world.list = () => ({ ok: true, status: 200, json: async () => {
    entered.resolve(); await finish.promise; return { requests: [...world.receipts.values()] };
  } });
  const promise = executionApi.refreshExecutionRecords(world.projectId).catch(error => error);
  try {
    await bounded(entered.promise); identity.token = 'SYNTHETIC_OTHER_TOKEN';
    assert.deepEqual(executionApi.getExecutionRecords(world.projectId), []);
  } finally { finish.resolve(); assert.ok(await bounded(promise) instanceof Error); }
  assert.deepEqual(executionApi.getExecutionRecords(world.projectId), []);
  identity.token = syntheticIdentity.token;
  assert.deepEqual(executionApi.getExecutionRecords(world.projectId), []);
  assert.equal(writes().length, 0);
});
await test('실행 접수 UNIT 기존 기획은 RESUME 빈 입력·원 작업 ID·의견 덮어쓰기 거절', async () => {
  const world = executionWorld();
  const resumed = await actions.startExistingTask(world.projectId, 'PLANNING_123', { initial_idea: '교체 금지', master_data: '교체 금지' });
  assert.equal(resumed.outcome, 'CONFIRMED');
  assert.deepEqual(bodyOf(writes()[0]), { client_request_id: resumed.requestId, operation: 'RESUME', task_id: 'PLANNING_123', input: {} });
  assert.equal((await actions.restartExistingTask(world.projectId, 'PLANNING_123', {}, '새 의견')).outcome, 'REJECTED');
  assert.equal(writes().length, 1);
});
await test('실행 접수 UNIT 기존 작업 START 입력 허용목록·상태/문맥 위조 미전송', async () => {
  const world = executionWorld();
  const result = await actions.startExistingTask(world.projectId, 'TASK_REV_1', {
    initial_idea: '원 요구', master_data: '원 자료', process_context: { forged: true }, schema_version: '1.0', factory_mode: 'PLANNING',
  }, '  수정 의견  ');
  assert.equal(result.outcome, 'CONFIRMED');
  assert.deepEqual(bodyOf(writes()[0]), { client_request_id: result.requestId, operation: 'START', task_id: 'TASK_REV_1',
    input: { initial_idea: '원 요구', master_data: '원 자료', feedback: '수정 의견' } });
});
await test('실행 접수 UNIT HEAL 원키 기반 작업·현재 다른 작업 HOTL 구분 및 잘못된 작업/원키 거절', async () => {
  for (const [replyBody, expected, field, expectedValue] of [
    [command => ({ status: 'healing_started', task_id: 'TASK_REV_HEAL_' + command.client_request_id.replaceAll('-', '') }),
      'HEAL_STARTED', 'taskId', requestId => 'TASK_REV_HEAL_' + requestId.replaceAll('-', '')],
    [() => ({ status: 'success', hotl_task_id: 'TASK_FAILED' }), 'HOTL_PENDING', 'hotlTaskId', () => 'TASK_FAILED'],
    [() => ({ status: 'success', hotl_task_id: 'sprint_init' }), 'HOTL_PENDING', 'hotlTaskId', () => 'sprint_init'],
    [() => ({ status: 'success', hotl_task_id: 'OTHER_CURRENT_TASK' }), 'HOTL_PENDING', 'hotlTaskId', () => 'OTHER_CURRENT_TASK'],
  ]) {
    const world = executionWorld();
    world.post = command => response({ request: world.commit(command, { result: { http_status: 200, response: replyBody(command) } }) });
    const result = await actions.requestSelfHealing(world.projectId, '합성 원 오류', 'TASK_FAILED');
    assert.equal(result.outcome, expected); assert.equal(result[field], expectedValue(result.requestId));
    assert.deepEqual(bodyOf(writes()[0]), { client_request_id: result.requestId, operation: 'HEAL', task_id: 'TASK_FAILED', input: { error_log: '합성 원 오류' } });
    assert.equal(writes().length, 1);
  }
  for (const badResponse of [
    { status: 'healing_started', task_id: 'TASK_HEAL_1' },
    { status: 'healing_started', task_id: 'TASK_REV_HEAL_' + '0'.repeat(32) },
    { status: 'success', hotl_task_id: '../OTHER_TASK' },
    { status: 'success', hotl_task_id: 'TASK_FAILED', task_id: 'TASK_FAILED' },
  ]) {
    const world = executionWorld();
    world.post = command => response({ request: world.commit(command, { result: { http_status: 200, response: badResponse } }) });
    const result = await actions.requestSelfHealing(world.projectId, '합성 원 오류', 'TASK_FAILED');
    assert.equal(result.outcome, 'UNKNOWN'); assert.equal(result.ok, false);
    assert.equal(executionApi.hasExecutionPending(world.projectId), true);
    assert.equal(calls.length, 1); assert.equal(writes().length, 1);
  }
});
await test('실행 접수 UNIT store 지속 UNKNOWN은 self-heal DB/HTTP 진입 전 차단·실패 근거 보존', async () => {
  const world = executionWorld();
  world.post = () => { throw new Error('합성 유실'); };
  await executionApi.executeStudioCommand(world.projectId, 'START', 'TASK_1');
  const saved = factory.useFactoryStore.getState();
  const failure = { taskId: 'TASK_FAILED', error: '합성 원 실패' };
  try {
    factory.useFactoryStore.setState({ currentProjectId: world.projectId, isConnected: true, healingRetryCount: 0, lastSprintFailure: failure });
    const blocked = await factory.useFactoryStore.getState().triggerSelfHealing('합성 복구');
    assert.equal(blocked.outcome, 'LOCAL_BLOCKED'); assert.equal(blocked.reasonCode, 'COMMAND_PENDING');
    assert.equal(factory.useFactoryStore.getState().healingRetryCount, 0);
    assert.deepEqual(factory.useFactoryStore.getState().lastSprintFailure, failure); assert.equal(writes().length, 1);
  } finally { factory.useFactoryStore.setState(saved); }
});
await test('실행 접수 UNIT store CONFIRMED 후 읽기만 재조회·active/HOTL/실패 자동 초기화 없음', async () => {
  const world = executionWorld();
  const saved = factory.useFactoryStore.getState(), reads = [];
  const failure = { taskId: 'TASK_FAILED', error: '합성 원 실패' };
  try {
    // 상태 조회 호출만 대역화한다. store 명령·bridge·영수증 검증은 실제 구현이다.
    factory.useFactoryStore.setState({ currentProjectId: world.projectId, isConnected: true,
      activeSprintId: 'TASK_1', hotlTaskId: 'TASK_HOTL_1', lastSprintFailure: failure,
      fetchLatestState: async () => { reads.push('state'); },
      fetchWBS: async force => { assert.equal(force, true); reads.push('wbs'); },
      checkHotl: async () => { reads.push('hotl'); } });
    const result = await factory.useFactoryStore.getState().stopSprint(world.projectId, 'TASK_1');
    assert.equal(result.outcome, 'CONFIRMED'); assert.equal(result.ok, true);
    assert.deepEqual(reads.sort(), ['hotl', 'state', 'wbs']);
    assert.equal(factory.useFactoryStore.getState().activeSprintId, 'TASK_1');
    assert.equal(factory.useFactoryStore.getState().hotlTaskId, 'TASK_HOTL_1');
    assert.deepEqual(factory.useFactoryStore.getState().lastSprintFailure, failure);
    assert.equal(writes().length, 1);
  } finally { factory.useFactoryStore.setState(saved); }
});
await test('실행 접수 SSR 내역 초기 권한확인·접수와 실행완료 분리·개인 기록 사전 비노출', async () => {
  const world = executionWorld();
  const attempt = await executionApi.executeStudioCommand(world.projectId, 'START', 'TASK_1', { feedback: 'SSR_PRIVATE_INPUT' });
  const count = calls.length;
  const html = renderToStaticMarkup(React.createElement(executionUi.StudioExecutionRequests, {
    projectId: world.projectId, onConfirmed() { throw new Error('SSR에서 상태 갱신 불가'); },
  }));
  assert.match(html, /실행 요청 기록과 복구/); assert.match(html, /실행 요청 목록 조회/);
  assert.match(html, /조회 권한을 확인/); assert.match(html, /명령 접수 확인은 가동 중·중지 완료·제작 완료를 뜻하지 않습니다/);
  assert.ok(!html.includes(attempt.request.client_request_id)); assert.ok(!html.includes('SSR_PRIVATE_INPUT'));
  assert.equal(calls.length, count);
});
await test('실행 접수 STATIC Header/store·RunControls 원키 해제·내역 GET 전용 및 문맥 해제 배선', () => {
  // 소스 계약 검사다. 실제 DOM 클릭·서버 권한·엔진 실행의 증거가 아니다.
  const controls = fs.readFileSync(new URL('../src/factory/RunControls.tsx', import.meta.url), 'utf8');
  const headerSource = fs.readFileSync(new URL('../src/factory/ProjectHeader.tsx', import.meta.url), 'utf8');
  const requests = fs.readFileSync(new URL('../src/factory/StudioExecutionRequests.tsx', import.meta.url), 'utf8');
  assert.match(headerSource, /\(stop \? stopSprint : pauseSprint\)\(vm\.project\.id, taskId\)/);
  assert.doesNotMatch(headerSource, /\bfetch\s*\(/);
  assert.match(controls, /<StudioExecutionRequests projectId=\{pid\} onConfirmed=\{executionConfirmed\}/);
  assert.match(controls, /record\.request\.client_request_id === previous\.requestId/);
  assert.match(controls, /record\.outcome === 'CONFIRMED' \|\| record\.outcome === 'REJECTED'/);
  assert.match(controls, /hasExecutionPending\(pid\)/);
  const callback = controls.slice(controls.indexOf('const executionConfirmed ='), controls.indexOf('const doPlanning ='));
  assert.match(callback, /fetchLatestState\(\)/); assert.match(callback, /fetchWBS\(true\)/); assert.match(callback, /checkHotl\(\)/);
  assert.doesNotMatch(callback, /executeStudioCommand|startExistingTask|startPlanning|resumeAfterQuota/);
  assert.match(requests, /await refreshExecutionRecords\(projectId\)/);
  assert.match(requests, /await recoverExecutionRequest\(projectId, requestId\)/);
  assert.doesNotMatch(requests, /executeStudioCommand|\bfetch\s*\(/);
  assert.match(requests, /active\.current = false; generation\.current\+\+/);
  assert.match(requests, /identity === studioIdentityKey\(\)/);
  assert.match(requests, /key=\{JSON\.stringify\(\[identity, props\.projectId\]\)\}/);
});
for (const resumable of [true, false]) await test(
  resumable ? '실행 접수 SSR 일시정지 일반 작업은 멈춘 작업 이어하기 CTA 활성'
    : '실행 접수 SSR resumable=false는 재개 CTA 비활성·서버 사유 표시',
  () => {
    resetMemory(); calls = [];
    const taskId = 'TASK_PAUSED_1';
    const reasonCode = resumable ? 'RESUMABLE' : 'CHECKPOINT_UNAVAILABLE';
    const vm = withVm({ project: { ...base.project, mode: 'EXECUTION' },
      wbs: [{ id: taskId, title: '입고 입력', kind: 'waiting' }],
      run: { ...base.run, label: '일시정지' } });
    const snapshot = { ...factory.useFactoryStore.getState(), currentProjectId: vm.project.id,
      state: { current_sprint_task_id: taskId, studio_execution_state: {
        task_id: taskId, running: false, pause: { status: 'PAUSED', resumable, reason_code: reasonCode },
      } } };
    // SSR 선택자에 합성 조회 상태만 주입한다. 실제 컴포넌트·CTA·명령 모듈을 사용하며 클릭은 실행하지 않는다.
    const ssrStore = Object.assign(selector => selector(snapshot), { getState: () => snapshot });
    const pausedRun = load('../src/factory/RunControls.tsx', {
      '../store/useFactoryStore': { ...factory, useFactoryStore: ssrStore },
      './sprintActions': actions, './studioNextAction': next, './studioInputMemory': memory,
      './StudioInputDraftControls': draftControls, './RevisionRequestEditor': revisionEditor,
      '../lib/studioExecutionApi': executionApi, './StudioExecutionRequests': executionUi,
    });
    const html = renderToStaticMarkup(React.createElement(pausedRun.RunControls, { vm }));
    assert.match(html, /멈춘 작업을 이어갈 수 있는지 확인하세요/);
    assert.match(html, /현재 작업의 저장된 지점에서 재개합니다. 새 작업 시작과는 다릅니다/);
    const primary = html.match(/<button\b[^>]*class="primary"[^>]*>멈춘 작업 이어하기<\/button>/)?.[0];
    assert.ok(primary, '일반 작업의 재개가 대표 CTA여야 함');
    if (resumable) {
      assert.doesNotMatch(primary, /\sdisabled(?:=|\s|>)/);
      assert.doesNotMatch(html, /재개 불가 사유:/);
    } else {
      assert.match(primary, /\sdisabled=""/);
      assert.match(html, /재개 불가 사유: CHECKPOINT_UNAVAILABLE/);
      const buttons = [...html.matchAll(/<button\b[^>]*>(?:<span>)?멈춘 작업 이어하기/g)];
      assert.equal(buttons.length, 2);
      for (const [button] of buttons) assert.match(button, /\sdisabled=""/);
    }
    assert.equal(calls.length, 0, 'SSR는 조회·명령을 보내지 않음');
  },
);
const executionChecks = results.length - preExecutionChecks;
const addedChecks = results.length - originalFunctionalChecks;
const after = hashes();
await test('검사 중 제품 소스 불변', () => assert.deepEqual(after, before));
const report = { passed: results.filter(x => x.result === 'PASS').length, failed: results.filter(x => x.result === 'FAIL').length,
  elapsed_ms: performance.now() - start, real_browser: 'NOT_RUN', network: 'MOCK_ONLY',
  original_checks: originalFunctionalChecks + 1, added_checks: addedChecks, cryptography: 'ACTUAL_SHA256',
  requirement_unit_checks: requirementChecks, requirement_server_validation: 'NOT_RUN',
  pre_kit_review_checks: preKitReviewChecks + 1,
  kit_review_checks: kitReviewChecks,
  kit_review_unit_api_ssr_checks: results.slice(preKitReviewChecks).filter(result => result.name.startsWith('Kit 검토') && !result.name.includes('STATIC')).length,
  kit_review_server_validation: 'NOT_RUN',
  pre_revision_checks: preRevisionChecks + 1, revision_checks: revisionChecks,
  revision_unit_api_ssr_checks: results.slice(preRevisionChecks).filter(result => result.name.startsWith('수정 접수') && !result.name.includes('STATIC')).length,
  revision_server_validation: 'NOT_RUN',
  pre_execution_checks: preExecutionChecks + 1, execution_checks: executionChecks,
  execution_unit_api_ssr_checks: results.slice(preExecutionChecks).filter(result => result.name.startsWith('실행 접수') && !result.name.includes('STATIC')).length,
  execution_server_validation: 'NOT_RUN',
  static_checks: results.filter(result => result.name.includes('STATIC ')).length,
  source_hashes_before: before, source_hashes_after: after, results };
const output = new URL(`../../output/studio-contracts-${randomUUID()}/`, import.meta.url);
fs.mkdirSync(output, { recursive: true }); fs.writeFileSync(new URL('report.json', output), JSON.stringify(report, null, 2));
for (const result of results) if (result.result === 'FAIL') process.stderr.write(`${result.name}: ${result.error}\n`);
process.stdout.write(`B5 Studio: ${report.passed} PASS / ${report.failed} FAIL; ${new URL('report.json', output).pathname}\n`);
if (report.failed) process.exitCode = 1;
