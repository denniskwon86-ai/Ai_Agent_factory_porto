// B6 모의 HTTP + 실제 flow/SSR. 브라우저·실제 서버 권한 검사는 별도다.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const files = ['../src/factory/studioProjectEntry.ts', '../src/factory/StudioProjectEntryGate.tsx',
  '../src/factory/studioEntryFlow.ts', '../src/factory/studioLeaveGuard.ts', '../src/App.tsx', './check-project-entry.mjs'];
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
// [DRAFT-ENTRY-01] flow 공통부는 «실제 모듈»을 싣는다 — 대역으로 만들면 수명 검사가 의미를 잃는다.
const flow_ = load('../src/factory/studioEntryFlow.ts', { './studioInputMemory': memory });
const module = load(files[0], { '../lib/api': api, './studioInputMemory': memory, './studioEntryFlow': flow_ });
const ui = load(files[1], { './studioProjectEntry': module });
const location = load('../src/factory/studioLocation.ts');
// [MEGA-ENTRY-01] 서버 계약에 소속 두 칸이 늘었다(설계안 §10.3). 모의 응답도 따른다.
const metadata = () => ({ project_id: 'P1', project_name: '구매 계획', runtime_document_version: '1.0',
  is_mega_project: false, child: null,
  ownership: { tenant_id: 'tenant-a', enterprise_scope_id: 'child-scope', entity_mode: 'REAL' },
  viewing_context: { tenant_id: 'tenant-a', scope_node_id: 'scope-a', entity_mode: 'REAL' } });
const childRow = (id = 'C1') => ({ project_id: id, project_name: '[구매] 통합', runtime_document_version: '1.0',
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
// ── [MEGA-ENTRY-01] 메가 — 관계는 서버가 판정한다 ────────────────────────
await test('MEGA 부모+자식을 한 번의 GET 으로 묻는다', async () => {
  responder = async () => response({ ...metadata(), is_mega_project: true, child: childRow() });
  const entry = await module.readProjectEntry('P1', undefined, 'C1');
  assert.equal(entry.is_mega_project, true);
  assert.equal(entry.child.project_id, 'C1');
  // ★ 두 번 묻지 않는다 — 두 응답을 맞춰 보는 쪽이 관계를 추론하게 된다.
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/v1/factory/P1/entry-metadata?child=C1');
});
await test('MEGA 안 물었는데 자식이 오면 계약 위반', async () => {
  responder = async () => response({ ...metadata(), child: childRow() });
  await assert.rejects(module.readProjectEntry('P1'), e => e.reasonCode === 'ENTRY_RESPONSE_INVALID');
});
await test('MEGA 물었는데 자식이 없으면 계약 위반', async () => {
  responder = async () => response({ ...metadata(), is_mega_project: true, child: null });
  await assert.rejects(module.readProjectEntry('P1', undefined, 'C1'), e => e.reasonCode === 'ENTRY_RESPONSE_INVALID');
});
await test('MEGA 다른 자식이 오면 계약 위반 — 여기서 메우지 않는다', async () => {
  responder = async () => response({ ...metadata(), is_mega_project: true, child: childRow('OTHER') });
  await assert.rejects(module.readProjectEntry('P1', undefined, 'C1'), e => e.reasonCode === 'ENTRY_RESPONSE_INVALID');
});
await test('MEGA is_mega_project 가 참·거짓이 아니면 계약 위반', async () => {
  for (const flag of ['true', 1, null, undefined]) {
    responder = async () => response({ ...metadata(), is_mega_project: flag });
    await assert.rejects(module.readProjectEntry('P1'), e => e.reasonCode === 'ENTRY_RESPONSE_INVALID');
  }
});
await test('MEGA 자식도 부모와 같은 문맥 규칙을 지난다', async () => {
  for (const bad of [{ tenant_id: 'tenant-b' }, { scope_node_id: 'scope-b' }, { entity_mode: 'SIMULATION' }]) {
    responder = async () => response({ ...metadata(), is_mega_project: true,
      child: { ...childRow(), viewing_context: { ...childRow().viewing_context, ...bad } } });
    await assert.rejects(module.readProjectEntry('P1', undefined, 'C1'),
      e => e.reasonCode === 'ENTRY_CONTEXT_CHANGED' || e.reasonCode === 'ENTRY_RESPONSE_INVALID');
  }
});
await test('MEGA 자식의 상태·형제 목록은 복사하지 않는다', async () => {
  responder = async () => response({ ...metadata(), is_mega_project: true,
    child: { ...childRow(), sub_projects_map: { d0: 'SIBLING' }, state: { secret: 'omit' } } });
  const entry = await module.readProjectEntry('P1', undefined, 'C1');
  assert.deepEqual(entry.child, childRow());
  assert.equal(JSON.stringify(entry).includes('SIBLING'), false);
});
await test('MEGA 잘못된 자식 ID 는 통신 전 차단', async () => {
  for (const id of ['../C1', 'C1/C2', 'C1?x=1', 'x'.repeat(161)]) {
    await assert.rejects(module.readProjectEntry('P1', undefined, id),
      e => e.reasonCode === 'ENTRY_INVALID_TARGET');
  }
  assert.equal(calls.length, 0);
});
await test('MEGA FLOW 는 자식마다 다른 질문을 한다', async () => {
  responder = async () => response({ ...metadata(), is_mega_project: true, child: childRow('C2') });
  const f = module.createProjectEntryFlow('P1', 'C2'); flows.push(f); f.activate(); await f.load();
  assert.equal(f.getSnapshot().phase, 'AVAILABLE');
  assert.equal(f.getSnapshot().data.child.project_id, 'C2');
  assert.equal(calls[0].url, '/api/v1/factory/P1/entry-metadata?child=C2');
});
await test('MEGA FLOW 해제 후 늦은 응답은 반영하지 않는다', async () => {
  const wait = deferred(); responder = () => wait.promise;
  const f = module.createProjectEntryFlow('P1', 'C1'); flows.push(f); f.activate();
  const pending = f.load(); f.dispose();
  wait.resolve(response({ ...metadata(), is_mega_project: true, child: childRow() }));
  await pending;
  assert.equal(f.getSnapshot().phase, 'IDLE'); assert.equal(f.getSnapshot().data, null);
});
// ── [FIX1 · 보완1] 메가 요청은 «명시 true» 일 때만 진행한다 ──────────────
await test('FIX1 메가 링크 + 일반 프로젝트 응답은 거절', async () => {
  // ★ 서버는 정확히 답했다. 그대로 열면 메가 링크가 일반 프로젝트를 여는 통로가 된다.
  responder = async () => response(metadata());                       // is_mega_project: false
  await assert.rejects(module.readProjectEntry('P1', undefined, '', true),
    e => e.reasonCode === 'ENTRY_NOT_MEGA');
});
await test('FIX1 메가 링크 + 명시 true 응답만 통과', async () => {
  responder = async () => response({ ...metadata(), is_mega_project: true });
  const entry = await module.readProjectEntry('P1', undefined, '', true);
  assert.equal(entry.is_mega_project, true); assert.equal(entry.child, null);
});
await test('FIX1 일반 project 요청은 false 도 정상', async () => {
  const entry = await module.readProjectEntry('P1');
  assert.equal(entry.is_mega_project, false);
});
await test('FIX1 child 를 물었는데 false 로 오면 거절', async () => {
  responder = async () => response({ ...metadata(), is_mega_project: false, child: childRow() });
  await assert.rejects(module.readProjectEntry('P1', undefined, 'C1'),
    e => e.reasonCode === 'ENTRY_RESPONSE_INVALID');
  await assert.rejects(module.readProjectEntry('P1', undefined, 'C1', true),
    e => e.reasonCode === 'ENTRY_NOT_MEGA' || e.reasonCode === 'ENTRY_RESPONSE_INVALID');
});
await test('FIX1 Gate 는 확인 전에 자식 Studio 를 만들지 않는다(메가 요청)', () => {
  let children = 0;
  const html = renderToStaticMarkup(React.createElement(ui.StudioProjectEntryGate,
    { projectId: 'P1', childId: 'C1', requireMega: true,
      children: () => { children++; return 'SECRET_CHILD'; } }));
  assert.ok(!html.includes('SECRET_CHILD')); assert.equal(children, 0); assert.equal(calls.length, 0);
});

// ── [FIX1 · 보완1] App 의 «실제» 배선을 뽑아 실행한다 ────────────────────
//   ⚠️ 소스 문자열 검사가 아니다. App.tsx 의 조건/JSX 를 AST 로 추출해 컴파일하고
//     대역 Gate 로 **실제 전달되는 props** 를 받아 본다.
function compileApp(expression) {
  const js = ts.transpileModule('export const value = ' + expression, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  const mod = { exports: {} };
  new Function('module', 'exports', js)(mod, mod.exports);
  return mod.exports.value;
}
function appAst() {
  const source = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  return ts.createSourceFile('App.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
}
await test('FIX1 App readStudioEntry 는 mega 대상을 «종류째» 보존한다', () => {
  const ast = appAst(); let fn = null;
  (function walk(node) {
    if (ts.isFunctionDeclaration(node) && node.name && node.name.getText(ast) === 'readStudioEntry') fn = node;
    ts.forEachChild(node, walk);
  })(ast);
  assert.ok(fn, 'readStudioEntry 를 찾지 못했다');
  const js = ts.transpileModule('export ' + fn.getText(ast), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  const mod = { exports: {} };
  new Function('module', 'exports', 'parseStudioLocation', js)(mod, mod.exports, location.parseStudioLocation);
  window.location = { search: '?space=build&target=mega&mega=M1&child=C1' };
  const withChild = mod.exports.readStudioEntry();
  assert.deepEqual(withChild.mega, { megaProjectId: 'M1', childProjectId: 'C1' });
  assert.equal(withChild.project, null);
  window.location = { search: '?space=build&target=mega&mega=M1' };
  assert.deepEqual(mod.exports.readStudioEntry().mega, { megaProjectId: 'M1', childProjectId: '' });
  window.location = { search: '?space=build&target=project&project=P1' };
  const plain = mod.exports.readStudioEntry();
  assert.equal(plain.mega, null); assert.equal(plain.project, 'P1');
});
await test('FIX1 App 은 Gate 에 requireMega 를 실제로 넘긴다', () => {
  const ast = appAst(); const branches = [];
  (function walk(node) {
    if (ts.isIfStatement(node) && node.expression.getText(ast).includes('entryGateId || draftGate')) branches.push(node);
    ts.forEachChild(node, walk);
  })(ast);
  assert.equal(branches.length, 1, '진입 게이트 분기를 정확히 하나 찾아야 한다');
  const js = ts.transpileModule('export function render(props) { const { entryGateId, currentProjectId,'
    + ' overlays, ErrorBoundary, closeEntryGate, setSpace, megaRequest, StudioProjectEntryGate,'
    + ' StudioEntryCommit, setCurrentProject, draftGate, StudioDraftEntryGate,'
    + ' OperatingContextChip, shellCompanyName, shellCtx, openContextSwitcher } = props; '
    + branches[0].getText(ast) + ' return null; }',
    { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const mod = { exports: {} };
  new Function('module', 'exports', 'require', js)(mod, mod.exports, name => {
    if (['react', 'react/jsx-runtime'].includes(name)) return createRequire(import.meta.url)(name);
    throw new Error('예상하지 않은 의존성: ' + name);
  });
  const seen = [];
  const drafts = [];
  //: 거절(Gate) 머리에 붙은 문맥 칩도 함께 그린다 — 있는지 아래에서 단언한다.
  const chipProps = [];
  const base = { entryGateId: 'M1', currentProjectId: null, overlays: null, draftGate: null,
    OperatingContextChip: (props) => { chipProps.push(props); return null; },
    shellCompanyName: 'LS MnM', shellCtx: { scopeLabel: '제련공장', entityMode: 'REAL' },
    openContextSwitcher: () => {},
    ErrorBoundary: ({ children }) => children, closeEntryGate: () => {}, setSpace: () => {},
    StudioEntryCommit: () => null, setCurrentProject: () => {},
    StudioDraftEntryGate: props => { drafts.push(props); return null; },
    StudioProjectEntryGate: props => { seen.push(props); return null; } };
  renderToStaticMarkup(mod.exports.render({ ...base, megaRequest: { childProjectId: 'C1' } }));
  assert.equal(seen.length, 1);
  assert.equal(seen[0].requireMega, true); assert.equal(seen[0].childId, 'C1');
  renderToStaticMarkup(mod.exports.render({ ...base, megaRequest: { childProjectId: '' } }));
  assert.equal(seen[1].requireMega, true); assert.equal(seen[1].childId, '');
  renderToStaticMarkup(mod.exports.render({ ...base, megaRequest: null }));
  assert.equal(seen[2].requireMega, false); assert.equal(seen[2].childId, '');
  // ★ [DRAFT-ENTRY-01] 초안 대상은 **프로젝트 게이트를 타지 않는다** — 다른 질문이다.
  renderToStaticMarkup(mod.exports.render({ ...base, megaRequest: null, entryGateId: null,
    draftGate: { draftId: 'adv_1', draftKind: 'blueprint', revision: 3 } }));
  assert.equal(seen.length, 3, '초안 진입이 프로젝트 게이트를 불렀다');
  assert.equal(drafts.length, 1);
  assert.equal(drafts[0].draftId, 'adv_1');
  assert.equal(drafts[0].draftKind, 'blueprint');
  assert.equal(drafts[0].revision, 3);
  // ★ [DRAFT-OPEN-01] 확인된 초안을 «실제로 여는» 연결이 붙어 있어야 한다.
  assert.equal(typeof drafts[0].children, 'function', 'Gate 에 여는 연결이 없다');
  assert.deepEqual(Object.keys(drafts[0]).sort(), ['children', 'draftId', 'draftKind', 'revision']);
  //: ★ [검토 §3] 거절/확인 화면에도 **공용 문맥 칩**이 그려져야 한다 — 그것이 되돌아올 길이다.
  //:   ⚠️ 없으면 권한 있는 범위로 가려고 홈까지 나갔다 다시 들어와야 한다(실측으로 그랬다).
  assert.ok(chipProps.length >= 1, '거절(Gate) 화면에 문맥 칩이 없다');
  assert.equal(typeof chipProps[0].onContext, 'function', '칩이 전환 문에 연결되지 않았다');
  assert.equal(chipProps[0].company, 'LS MnM', '칩이 셸과 다른 상태 출처를 쓴다');
});
await test('FIX2 확인이 끝나기 전에는 URL 대상을 «지우지 않는다»', () => {
  //: ★★★ [2026-09-16] 실화면에서 드러났다. 초기값이 project·mega 만 봐서 kit_app·draft 는
  //:   게이트가 도는 중에 URL 대상이 지워졌고, 그 상태로 새로고침하면 진입 대상이 사라진다.
  //: ⚠️ 소스 문자열 검사가 아니다 — App.tsx 의 «그 초기식»을 뽑아 실제로 실행한다.
  const ast = appAst(); const inits = [];
  (function walk(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(ast).includes('routeRestored')
        && node.initializer && ts.isCallExpression(node.initializer)
        && node.initializer.expression.getText(ast) === 'useState') {
      inits.push(node.initializer.arguments[0]);
    }
    ts.forEachChild(node, walk);
  })(ast);
  assert.equal(inits.length, 1, 'routeRestored 초기식을 정확히 하나 찾아야 한다');
  const restored = compileApp('(initialProject, initialEntry) => (' + inits[0].getText(ast) + ')');
  const entry = (patch = {}) => ({ current: { project: null, isNew: false, release: null,
    kitApp: null, mega: null, draft: null, ...patch } });
  const none = { current: null };
  // 진입 대상이 없으면 즉시 URL 을 정리해도 된다.
  assert.equal(restored(none, entry()), true);
  // ⚠️ 대상이 있으면 «확인 전» 이므로 지우면 안 된다 — 넷 다.
  assert.equal(restored({ current: 'P1' }, entry({ project: 'P1' })), false, 'project');
  assert.equal(restored({ current: 'M1' }, entry({ mega: { megaProjectId: 'M1', childProjectId: '' } })), false, 'mega');
  assert.equal(restored(none, entry({ kitApp: { instanceId: 'ki_1', appId: 'app_1' } })), false, 'kit_app');
  assert.equal(restored(none, entry({ draft: { draftId: 'adv_1', draftKind: 'blueprint', revision: 1 } })), false, 'draft');
});
await test('FIX2 공통 적용 경로: URL 목적지와 화면이 «일치»한다', () => {
  //: ⚠️⚠️ 종전 이 시험은 「대상 없으면 currentProject 를 건드리지 않는다」를 단언해
  //:   **잘못된 동작을 고정하고 있었다**(검토 지적). 이제 URL↔화면 일치를 단언한다.
  const ast = appAst(); const decls = [];
  (function walk(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'applyStudioEntry'
        && node.initializer && ts.isCallExpression(node.initializer)) decls.push(node.initializer.arguments[0]);
    ts.forEachChild(node, walk);
  })(ast);
  assert.equal(decls.length, 1, 'applyStudioEntry 를 정확히 하나 찾아야 한다');
  const make = compileApp('(setBuildStart, setCurrentProject, setEntryGateId, setMegaRequest,'
    + ' setKitAppGate, setDraftGate, setRouteRestored, leaveRelease, setSpace, openRelease,'
    + ' setBuildStartType, readSpaceFromUrl, setOpenedMega, setOpenedKitApp, setOpenedDraft,'
    + ' setShowPathCalc) => (' + decls[0].getText(ast) + ')');
  const run = (entry, spaceInUrl = 'operate') => {
    const seen = {};
    const rec = (k) => (v) => { seen[k] = v; };
    make(rec('buildStart'), rec('currentProject'), rec('entryGate'), rec('megaRequest'),
      rec('kitApp'), rec('draftGate'), rec('routeRestored'), () => { seen.releaseClosed = true; },
      rec('space'), (id) => { seen.viewedRelease = id; }, rec('buildStartType'),
      () => spaceInUrl, rec('openedMega'), rec('openedKitApp'), rec('openedDraft'),
      rec('pathCalc'))(entry);
    return seen;
  };
  const none = { project: null, isNew: false, release: null, kitApp: null, mega: null, draft: null };

  // ① 대상이 있으면 확인 게이트로 — 편집기·선택을 내리고 URL 대상은 유지한다.
  const draft = run({ ...none, draft: { draftId: 'adv_1', draftKind: 'blueprint', revision: 2 } });
  assert.deepEqual(draft.draftGate, { draftId: 'adv_1', draftKind: 'blueprint', revision: 2 });
  assert.equal(draft.buildStart, false);
  assert.equal(draft.currentProject, null);
  assert.equal(draft.routeRestored, false);
  //: ★★★ [FIX2 · 지시 3] **대상은 배타적이다.** 종전에는 보던 릴리스·업무앱을 그대로 두어
  //:   `openTarget` 이 옛 릴리스를 먼저 골랐고, **새 주소를 옛 대상이 덮었다.**
  assert.equal(draft.releaseClosed, true, '릴리스→초안인데 보던 릴리스를 놓지 않았다');
  assert.equal(draft.pathCalc, false, '업무앱 화면이 초안 위에 남는다');
  assert.equal(draft.openedKitApp, null, '업무앱 대상 기록이 남아 주소를 덮는다');
  assert.equal(draft.openedDraft, null);
  assert.equal(draft.openedMega, null);

  // ② ★ 대상 없는 «목록/홈» 주소 → 그 화면으로 «전환» 하고 열린 것을 정리한다.
  const list = run(none, 'operate');
  assert.equal(list.currentProject, null, '열린 프로젝트가 남았다 — URL 과 화면이 어긋난다');
  assert.equal(list.space, 'operate', 'URL 의 목적지로 전환하지 않았다');
  assert.equal(list.buildStart, false);
  assert.equal(list.releaseClosed, true, '보던 릴리스를 정리하지 않았다');
  assert.equal(list.entryGate, null);
  //: ★ 열린 대상 기록도 함께 비운다 — 안 비우면 목록 주소인데 URL 에 옛 대상이 남는다.
  assert.equal(list.openedMega, null);
  assert.equal(list.openedKitApp, null);
  assert.equal(list.openedDraft, null);
  assert.equal(list.pathCalc, false, '목록으로 왔는데 업무앱 화면이 남았다');
  assert.equal(list.routeRestored, true);

  // ③ ★ release 복원 — 검토가 지적한 누락분.
  const rel = run({ ...none, release: 'rel_9' });
  assert.equal(rel.viewedRelease, 'rel_9', '릴리스 주소인데 그 릴리스를 열지 않았다');
  assert.equal(rel.space, 'build');
  assert.equal(rel.currentProject, null);
  assert.equal(rel.pathCalc, false, '릴리스로 왔는데 업무앱 화면이 남았다');

  // ④ ★ new 복원 — 역시 누락분.
  const fresh = run({ ...none, isNew: true });
  assert.equal(fresh.buildStart, true, '새로 만들기 주소인데 그 화면을 열지 않았다');
  assert.equal(fresh.buildStartType, 'software_app');
  assert.equal(fresh.space, 'build');
});

// ── [FIX2 · 지시 1] 뒤로/앞으로 — «방향과 칸 수»를 실제 히스토리 스택으로 잰다 ──
//   ⚠️ `history.length` 가 같다고 성공이 아니다. **현재 항목 위치·주소·적용 여부**를
//     함께 본다. 그래서 여기서는 로그가 아니라 **스택을 움직이는 대역**을 쓴다.
//   ★ 실제 브라우저처럼 `go()` 는 popstate 를 **나중에** 던진다(동기 호출 중이 아니다).
//     그 순서가 「복원 전에 들어온 승인 클릭」 처리의 전제다.
function historyStub(searches, at, { indexed = true, marks = null, epoch = 'E0' } = {}) {
  const stack = searches.map((search, i) => ({
    search,
    //: 번호만으로는 «구간» 을 알 수 없다 — 우리 칸에는 구간도 함께 찍힌다.
    state: marks ? { __studioEpoch: epoch, ...marks[i] }
                 : (indexed ? { __studioIndex: i, __studioEpoch: epoch } : {}),
  }));
  const queue = [], log = [];
  const history = {
    get state() { return stack[history.index].state; },
    //: 제품이 「칸 수가 이 문서의 히스토리보다 클 수 없다」를 여기서 읽는다.
    get length() { return stack.length; },
    index: at,
    go(n) {
      log.push('go:' + n);
      //: ⚠️⚠️ [검토 §4] **`history.go(0)` 은 «아무 일도 안 함» 이 아니라 «문서를 다시 읽음» 이다.**
      //:   종전 대역은 위치가 같으면 조용히 넘겨서 이 경계를 **증명할 수 없었다**(검토 지적).
      //:   여기서 그대로 기록해 두면, 되돌리려다 입력을 통째로 잃는 회귀가 빨강으로 보인다.
      if (n === 0) { log.push('RELOAD'); return; }
      const to = Math.max(0, Math.min(stack.length - 1, history.index + n));
      //: 이동이 없으면 브라우저도 popstate 를 던지지 않는다 — 그 점이 옛 결함의 씨앗이었다.
      if (to === history.index) { log.push('nowhere'); return; }
      history.index = to;
      queue.push({ state: stack[to].state });
    },
    back() { history.go(-1); },
    pushState(state, _t, url) { log.push('push'); stack.splice(history.index + 1);
      stack.push({ search: url, state }); history.index = stack.length - 1; },
    replaceState(state, _t, url) { log.push('replace'); stack[history.index] = { search: url, state }; },
  };
  return { history, stack, queue, log, epoch: { current: 'E0' },
    /** 사용자가 브라우저 버튼을 눌렀다 — 위치를 옮기고 popstate 를 예약한다. */
    press(n) { const to = history.index + n;
      if (to < 0 || to >= stack.length) return false;          // 끝에서는 아무 일도 없다
      history.index = to; queue.push({ state: stack[to].state }); return true; } };
}

await test('FIX2 뒤로/앞으로: 취소는 «온 방향으로 정확히» 되돌리고 승인은 목적지로 간다', () => {
  const ast = appAst(); const effects = [];
  (function walk(node) {
    if (ts.isCallExpression(node) && node.expression.getText(ast) === 'useEffect'
        && node.getText(ast).includes("'popstate'")) effects.push(node.arguments[0]);
    ts.forEachChild(node, walk);
  })(ast);
  assert.equal(effects.length, 1);
  const make = compileApp('(window, skipNextPop, leavingAnyway, canLeaveNow, confirmLeave,'
    + ' applyStudioEntry, readStudioEntry, restoringFromPop, historyIndex, pendingApproval,'
    + ' setStrandedEntry, historyEpoch, newEpoch, setContextBlocked) => (' + effects[0].getText(ast) + ')');

  /** 한 문서 안의 왕복을 처음부터 끝까지 돌린다. `approve` 는 확인창에서 「떠난다」를 누르는 시점. */
  const session = ({ searches, at, safe, indexed = true, fast = false, marks = null, here }) => {
    const env = historyStub(searches, at, { indexed, marks });
    const applied = [];
    let handler = null, asked = 0, decide = null;
    const win = { history: env.history,
      addEventListener: (e, f) => { if (e === 'popstate') handler = f; },
      removeEventListener: () => {} };
    const skip = { current: false }, leaving = { current: false }, restoring = { current: false };
    const index = { current: here !== undefined ? here : (indexed ? at : null) };
    const approval = { current: null };
    const stranded = [];
    const cleanup = make(win, skip, leaving, () => safe,
      //: `fast` 는 **확인창이 뜨자마자 누르는** 사용자다 — 복원 popstate 보다 «먼저» 온다.
      (proceed) => { asked += 1; decide = proceed; if (fast) proceed(); },
      () => applied.push(env.history.index),
      () => ({ project: null, isNew: false, release: null, kitApp: null, mega: null, draft: null }),
      //: `null` 로 «지우는» 호출은 배너를 띄운 것이 아니다 — 띄운 것만 센다.
      //: 구간(epoch) — 대역에서는 «같은 구간» 을 기본으로 둔다. 구간이 다른 경우는 FIX4 시험이 본다.
      restoring, index, approval, (v) => { if (v) stranded.push(v); },
      env.epoch, () => { env.epoch.current = 'E' + (Math.random() * 1e6 | 0); return env.epoch.current; },
      () => {})();
    //: 예약된 popstate 를 «브라우저처럼» 순서대로 흘려보낸다.
    const flush = () => { let guard = 0;
      while (env.queue.length) { if (++guard > 20) throw new Error('popstate 가 멎지 않는다');
        env.log.push('pop'); handler(env.queue.shift()); } };
    return { env, applied, flush, skip, leaving, restoring, index, approval, cleanup, stranded,
      press: (n) => { env.press(n); flush(); },
      asked: () => asked, approve: () => { decide(); flush(); } };
  };

  // ① 안전하면 묻지 않고 그대로 적용한다.
  const ok = session({ searches: ['?a', '?b'], at: 1, safe: true });
  ok.press(-1);
  assert.equal(ok.asked(), 0, '안전한데 물었다');
  assert.deepEqual(ok.applied, [0], '적용하지 않았다');
  assert.equal(ok.index.current, 0, '현재 항목 번호를 갱신하지 않았다');
  assert.equal(ok.restoring.current, true, 'popstate 복원인데 새 칸을 만들 태세다');

  // ②★★★ 뒤로 취소 — 앞으로 한 칸 되돌아와 «원위치» 여야 한다.
  const backCancel = session({ searches: ['?a', '?b', '?c'], at: 2, safe: false });
  backCancel.press(-1);
  assert.equal(backCancel.asked(), 1, '확인을 띄우지 않았다');
  assert.deepEqual(backCancel.applied, [], '묻지 않고 이동해 버렸다');
  assert.equal(backCancel.env.history.index, 2, '취소했는데 원위치가 아니다');
  assert.equal(backCancel.index.current, 2, '취소인데 우리 위치 기록이 움직였다');
  assert.equal(backCancel.env.log.includes('push'), false, '취소하며 히스토리를 늘렸다');
  assert.equal(backCancel.skip.current, false, '복원 popstate 를 삼키는 표시가 남았다');
  assert.equal(backCancel.restoring.current, false, '취소인데 복원 표시가 남았다');

  // ③★★★ **앞으로 취소** — 옛 결함의 정면. `go(1)` 이면 더 앞으로 간다.
  const fwdCancel = session({ searches: ['?a', '?b', '?c'], at: 0, safe: false });
  fwdCancel.press(+1);
  assert.equal(fwdCancel.env.history.index, 0, '앞으로가기를 취소했는데 원위치가 아니다');
  assert.ok(fwdCancel.env.log.includes('go:-1'), '앞으로 이동을 뒤로 되돌리지 않았다');
  assert.equal(fwdCancel.env.log.includes('go:1'), false, '취소인데 «더 앞으로» 갔다');
  assert.deepEqual(fwdCancel.applied, []);

  // ④★★★ **마지막 항목으로 앞으로 → 취소 → 다시 뒤로.** 옛 코드는 여기서 표시가 남아
  //   다음 진짜 이동을 통째로 삼켰다.
  const tail = session({ searches: ['?a', '?b'], at: 0, safe: false });
  tail.press(+1);
  assert.equal(tail.env.history.index, 0, '마지막 항목 앞으로 취소가 원위치로 못 왔다');
  assert.equal(tail.skip.current, false, '표시가 남아 다음 이동을 삼킬 참이다');
  tail.press(+1);
  assert.equal(tail.asked(), 2, '다음 이동을 삼켜 묻지 않았다');

  // ⑤ 두 칸 이동도 원위치로 돌아온다.
  const two = session({ searches: ['?a', '?b', '?c', '?d'], at: 3, safe: false });
  two.press(-2);
  assert.ok(two.env.log.includes('go:2'), '두 칸을 한 칸으로 되돌리려 했다');
  assert.equal(two.env.history.index, 3, '두 칸 이동 취소가 원위치로 못 왔다');

  // ⑥★★★ 승인 — 복원 popstate «전» 에 눌러도 목적지로 간다(빠른 클릭 순서 제어).
  const approved = session({ searches: ['?a', '?b', '?c'], at: 2, safe: false });
  approved.press(-1);
  assert.equal(approved.env.history.index, 2, '확인 중인데 위치가 목적지에 있다');
  approved.approve();
  assert.equal(approved.env.history.index, 1, '떠나기를 골랐는데 목적지가 아니다');
  assert.deepEqual(approved.applied, [1], '목적지 진입을 다시 실행하지 않았다');
  assert.equal(approved.index.current, 1);
  assert.equal(approved.leaving.current, false, '다시 묻게 되어 무한히 막힌다');

  // ⑦ 앞으로 승인도 방향이 맞아야 한다.
  const fwdOk = session({ searches: ['?a', '?b', '?c'], at: 0, safe: false });
  fwdOk.press(+1);
  fwdOk.approve();
  assert.equal(fwdOk.env.history.index, 1, '앞으로 승인이 목적지로 가지 않았다');
  assert.deepEqual(fwdOk.applied, [1]);

  // ⑧★★★ **빠른 클릭** — 확인창이 뜨자마자 「떠난다」를 눌러도 순서가 어긋나지 않는다.
  //   ⚠️ 복원 이동이 «끝나기 전» 에 두 번째 이동을 걸면 두 왕복이 겹친다. 승인은 복원
  //     popstate 를 받은 «뒤» 에 나가야 한다.
  const racing = session({ searches: ['?a', '?b', '?c'], at: 2, safe: false, fast: true });
  racing.press(-1);
  assert.deepEqual(racing.env.log, ['pop', 'go:1', 'pop', 'go:-1', 'pop'],
    '복원이 끝나기 전에 두 번째 이동을 걸었다 — 왕복이 겹친다');
  assert.equal(racing.env.history.index, 1, '빠른 승인이 목적지로 가지 않았다');
  assert.deepEqual(racing.applied, [1]);

  // ⑨★★★ [검토 §4] **번호 없는 항목에서도 입력은 지킨다.**
  //   ⚠️⚠️ 종전 시험은 여기서 `applied [0]` 을 **단언하고 있었다** — 즉 「묻지 않고 편집기를
  //     내리는」 동작을 초록으로 고정하고 있었다. 번호가 없다는 것은 「앱 밖」이라는 증거가
  //     아니다. 같은 문서에서 다른 코드가 만든 항목일 수 있고, 그때 `beforeunload` 는 뜨지
  //     않는다. 잃는 것은 되돌릴 수 없으므로 **막는 쪽**으로 답한다.
  //   ★ 그러나 방향·칸 수를 **지어내지 않는다** — `go()` 를 한 번도 부르지 않아야 한다.
  const foreign = session({ searches: ['?a', '?b'], at: 1, safe: false, indexed: false });
  foreign.press(-1);
  assert.deepEqual(foreign.applied, [], '번호를 모르는데 화면을 내려 버렸다 — 입력이 사라진다');
  assert.equal(foreign.env.log.some((x) => x.startsWith('go:')), false,
    '위치를 모르면서 이동을 «지어냈다»');
  assert.equal(foreign.stranded.length, 1, '어긋난 주소를 사용자에게 보이지 않았다');
  assert.equal(foreign.restoring.current, false, '적용하지도 않고 복원 표시만 켰다');

  // ⑩ 같은 자리에서 **안전하면** 종전처럼 그대로 따라간다 — 정상 이동을 막지 않는다.
  const foreignSafe = session({ searches: ['?a', '?b'], at: 1, safe: true, indexed: false });
  foreignSafe.press(-1);
  assert.deepEqual(foreignSafe.applied, [0], '잃을 것이 없는데 화면을 안 맞췄다');
  assert.equal(foreignSafe.stranded.length, 0, '물을 것도 없는데 배너를 띄웠다');
  assert.equal(foreignSafe.index.current, null, '없는 번호를 지어냈다');

  // ⑪★★★ **번호가 같다(delta = 0)** — `history.go(0)` 은 «문서를 다시 읽는다».
  //   되돌리려다 입력을 통째로 잃는 자리다. 번호가 겹쳤다는 것 자체가 「모른다」는 뜻이다.
  const dup = session({ searches: ['?a', '?b'], at: 1, safe: false,
    marks: [{ __studioIndex: 4 }, { __studioIndex: 4 }], here: 4 });
  dup.press(-1);
  assert.equal(dup.env.log.includes('RELOAD'), false,
    'go(0) 을 불렀다 — 문서가 다시 읽히며 미저장 입력이 사라진다');
  assert.equal(dup.env.log.some((x) => x.startsWith('go:')), false, '겹친 번호로 이동을 계산했다');
  assert.deepEqual(dup.applied, [], '확인 전에 화면을 바꿨다');
  assert.equal(dup.stranded.length, 1, '어긋난 주소를 보이지 않았다');

  // ⑫ **말이 안 되는 번호**(소수·문자·NaN)는 「번호 없음」과 같게 다룬다.
  for (const bad of [1.5, '2', NaN, null]) {
    const junk = session({ searches: ['?a', '?b'], at: 1, safe: false,
      marks: [{ __studioIndex: bad }, { __studioIndex: bad }], here: 0 });
    junk.press(-1);
    assert.equal(junk.env.log.some((x) => x.startsWith('go:')), false,
      '엉터리 번호(' + String(bad) + ')로 이동을 계산했다');
    assert.deepEqual(junk.applied, [], '엉터리 번호인데 화면을 바꿨다');
    assert.equal(junk.stranded.length, 1, '엉터리 번호에서 어긋난 주소를 보이지 않았다');
  }

  // ⑬ 칸 수가 **이 문서의 히스토리보다 클 수 없다** — 넘으면 믿지 않는다.
  const wild = session({ searches: ['?a', '?b'], at: 1, safe: false,
    marks: [{ __studioIndex: 0 }, { __studioIndex: 900 }], here: 900 });
  wild.press(-1);
  assert.equal(wild.env.log.some((x) => x.startsWith('go:')), false,
    '히스토리보다 먼 칸 수를 그대로 믿고 이동했다');
  assert.equal(wild.stranded.length, 1);
});

await test('FIX2 열린 대상이 «주소에 남는다» — 새로고침으로 재현 가능', () => {
  //: ⚠️ 정적 검사가 아니다. App 의 URL 동기화 효과를 뽑아 가짜 window 로 «실행» 하고,
  //:   기록된 pushState/replaceState 의 주소를 **파서로 되읽어** 왕복을 확인한다.
  const ast = appAst(); const effects = [];
  (function walk(node) {
    if (ts.isCallExpression(node) && node.expression.getText(ast) === 'useEffect'
        && node.getText(ast).includes('serializeStudioLocation')) effects.push(node.arguments[0]);
    ts.forEachChild(node, walk);
  })(ast);
  assert.equal(effects.length, 1, 'URL 동기화 효과를 정확히 하나 찾아야 한다');
  const make = compileApp('(routeRestored, window, openTarget, serializeStudioLocation, space,'
    + ' restoringFromPop, historyIndex, historyEpoch, newEpoch) => ('
    + effects[0].getText(ast) + ')');

  const run = (openTarget, { href = 'http://x/app?tab=cost#frag', pop = false, space = 'build' } = {}) => {
    const calls = [];
    const win = { location: new URL(href), history: { state: { k: 1 },
      pushState: (st, _t, url) => calls.push(['push', url]),
      replaceState: (st, _t, url) => calls.push(['replace', url]) } };
    win.location.search = new URL(href).search; win.location.hash = new URL(href).hash;
    make(true, win, openTarget, location.serializeStudioLocation, space, { current: pop },
      { current: 0 }, { current: 'E0' }, () => 'E0')();
    return calls;
  };

  // ① 초안: 종류·판본까지 남는다.
  const draft = run({ kind: 'draft', draftKind: 'blueprint', draftId: 'adv_1', revision: 3 });
  assert.equal(draft.length, 1); assert.equal(draft[0][0], 'push');
  const back = location.parseStudioLocation(new URL(draft[0][1], 'http://x').search);
  assert.equal(back.kind, 'MATCH');
  assert.deepEqual(back.location.target,
    { kind: 'draft', draftKind: 'blueprint', draftId: 'adv_1', revision: 3 });
  //: ★ 관련 없는 쿼리와 hash 를 «무단 제거하지 않는다»(결정서 §3).
  assert.ok(draft[0][1].includes('tab=cost'), '남의 쿼리를 지웠다');
  assert.ok(draft[0][1].includes('#frag'), 'hash 를 지웠다');

  // ② 메가: 부모/자식을 잃지 않는다.
  const mega = run({ kind: 'mega', megaProjectId: 'M1', childProjectId: 'C1' });
  const megaBack = location.parseStudioLocation(new URL(mega[0][1], 'http://x').search);
  assert.deepEqual(megaBack.location.target, { kind: 'mega', megaProjectId: 'M1', childProjectId: 'C1' });

  // ③ 릴리스·업무앱도 같은 규칙.
  for (const [target, expect] of [
      [{ kind: 'release', releaseId: 'rel_9' }, { kind: 'release', releaseId: 'rel_9' }],
      [{ kind: 'kit_app', instanceId: 'ki_1', appId: 'app_1' },
       { kind: 'kit_app', instanceId: 'ki_1', appId: 'app_1' }]]) {
    const w = run(target);
    assert.deepEqual(location.parseStudioLocation(new URL(w[0][1], 'http://x').search).location.target, expect);
  }

  // ④ ★ popstate 복원은 **새 칸을 만들지 않는다** — 교체다.
  const restored = run({ kind: 'project', projectId: 'P1' }, { pop: true });
  assert.equal(restored[0][0], 'replace', 'popstate 복원인데 히스토리를 늘렸다');

  // ⑤ ★ 같은 주소면 «아무것도 기록하지 않는다» — 중복 이동을 쌓지 않는다.
  const same = run({ kind: 'project', projectId: 'P1' },
    { href: 'http://x/app?space=build&target=project&project=P1' });
  assert.deepEqual(same, [], '같은 대상인데 히스토리 칸을 더했다');
});

// ── [FIX2 · 지시 2] 복원 표시가 «다음 클릭까지» 남지 않는다 — 전이 연속 검사 ──────
//   ⚠️⚠️ 효과 하나만 따로 부르는 검사로는 이 결함이 안 잡힌다. 결함의 조건이 「복원 때
//     URL 이 **이미 같아서** 일찍 return 하는 것」이라서, 그 다음 «클릭» 까지 이어 봐야
//     기록을 잃는 장면이 나온다. 그래서 여기서는 URL 효과와 popstate 처리를 **같은
//     히스토리 스택 위에서** 번갈아 돌린다.
await test('FIX2 목록→초안→목록→뒤로→다른 대상: 마지막 클릭이 «한 칸 늘어난다»', () => {
  const ast = appAst(); const urlEffects = [], popEffects = [];
  (function walk(node) {
    if (ts.isCallExpression(node) && node.expression.getText(ast) === 'useEffect') {
      const text = node.getText(ast);
      if (text.includes('serializeStudioLocation')) urlEffects.push(node.arguments[0]);
      else if (text.includes("'popstate'")) popEffects.push(node.arguments[0]);
    }
    ts.forEachChild(node, walk);
  })(ast);
  assert.equal(urlEffects.length, 1); assert.equal(popEffects.length, 1);
  const makeUrl = compileApp('(routeRestored, window, openTarget, serializeStudioLocation, space,'
    + ' restoringFromPop, historyIndex, historyEpoch, newEpoch) => ('
    + urlEffects[0].getText(ast) + ')');
  const makePop = compileApp('(window, skipNextPop, leavingAnyway, canLeaveNow, confirmLeave,'
    + ' applyStudioEntry, readStudioEntry, restoringFromPop, historyIndex, pendingApproval,'
    + ' setStrandedEntry, historyEpoch, newEpoch, setContextBlocked) => (' + popEffects[0].getText(ast) + ')');

  //: 한 문서의 히스토리 스택. push/replace/go 가 **주소까지** 함께 움직인다.
  const epoch = { current: 'E0' };
  const newEpoch = () => { epoch.current = 'E' + (Math.random() * 1e6 | 0); return epoch.current; };
  const stack = [{ url: '/app?space=build', state: { __studioIndex: 0, __studioEpoch: 'E0' } }];
  let at = 0;
  const queue = [], win = { location: null };
  const sync = () => { const u = new URL(stack[at].url, 'http://x');
    win.location = { href: u.href, pathname: u.pathname, search: u.search, hash: u.hash }; };
  win.history = {
    get state() { return stack[at].state; },
    get length() { return stack.length; },
    go(n) { const to = Math.max(0, Math.min(stack.length - 1, at + n));
      if (to === at) return; at = to; sync(); queue.push({ state: stack[at].state }); },
    back() { win.history.go(-1); },
    pushState(state, _t, url) { stack.splice(at + 1); stack.push({ url, state });
      at = stack.length - 1; sync(); },
    replaceState(state, _t, url) { stack[at] = { url, state }; sync(); },
  };
  let popHandler = null;
  win.addEventListener = (e, f) => { if (e === 'popstate') popHandler = f; };
  win.removeEventListener = () => {};
  sync();

  const restoring = { current: false }, index = { current: 0 };
  let target = null, space = 'build';
  //: 화면 상태 → URL. 실제 앱에서 렌더 뒤에 도는 그 효과다.
  const render = () => { makeUrl(true, win, target, location.serializeStudioLocation, space,
    restoring, index, epoch, newEpoch)(); };
  //: 사용자가 대상을 «클릭» 했다.
  const click = (next, nextSpace = 'build') => { target = next; space = nextSpace; render(); };
  //: 브라우저 뒤로/앞으로. popstate → applyStudioEntry 가 URL 의 대상으로 화면을 맞춘다.
  makePop(win, { current: false }, { current: false }, () => true, (go) => go(),
    () => { const parsed = location.parseStudioLocation(win.location.search);
      target = parsed.kind === 'MATCH' ? parsed.location.target : null;
      space = 'build'; },
    () => ({}), restoring, index, { current: null }, () => {}, epoch, newEpoch, () => {})();
  const press = (n) => { at = Math.max(0, Math.min(stack.length - 1, at + n)); sync();
    popHandler({ state: stack[at].state }); render(); };

  const draft = { kind: 'draft', draftKind: 'blueprint', draftId: 'adv_1', revision: 2 };

  render();                                     // 목록에서 시작 — 주소가 같으니 기록 없음
  assert.equal(stack.length, 1, '같은 주소인데 칸을 더했다');

  click(draft);                                 // 목록 → 초안
  assert.equal(stack.length, 2); assert.equal(at, 1);
  click(null);                                  // 초안 → 목록
  assert.equal(stack.length, 3); assert.equal(at, 2);

  press(-1);                                    // 뒤로 → 초안
  assert.equal(at, 1, '뒤로가 초안 칸으로 오지 않았다');
  assert.deepEqual(location.parseStudioLocation(win.location.search).location.target, draft);
  assert.equal(stack.length, 3, '복원이 히스토리를 늘렸다');
  //: ★★★ 여기서 표시가 «꺼져 있어야» 한다. 종전에는 URL 이 이미 같아 일찍 return 하는
  //:   바람에 켜진 채 남았고, 그 값이 다음 클릭을 교체로 만들었다.
  assert.equal(restoring.current, false, '복원 표시가 다음 클릭까지 남았다');

  click({ kind: 'project', projectId: 'P9' }); // ★ 다른 대상 클릭 — **한 칸 늘어야 한다**
  assert.equal(at, 2, '클릭이 새 칸으로 가지 않았다');
  assert.equal(stack.length, 3, '뒤로 뒤의 클릭은 앞쪽 칸을 «대체» 한다(브라우저 규칙)');
  assert.equal(stack[2].state.__studioIndex, 2, '새 칸에 번호를 붙이지 않았다');
  assert.ok(stack[2].url.includes('project=P9'), '클릭한 대상이 주소에 없다');

  press(-1);                                    // ★ 그 뒤 뒤로가기는 «초안» 으로 돌아온다
  assert.equal(at, 1);
  assert.deepEqual(location.parseStudioLocation(win.location.search).location.target, draft,
    '클릭이 기록을 잃어 초안으로 못 돌아왔다');
});

// ── [FIX2 · 지시 3] 「지금 열린 대상」 계산 — 조회 중·만들기도 주소를 잃지 않는다 ──
await test('FIX2 openTarget: 릴리스 조회 중에도, «새로 만들기» 도 주소가 있다', () => {
  const ast = appAst(); const memos = [];
  (function walk(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'openTarget'
        && node.initializer && ts.isCallExpression(node.initializer)) memos.push(node.initializer.arguments[0]);
    ts.forEachChild(node, walk);
  })(ast);
  assert.equal(memos.length, 1, 'openTarget 을 정확히 하나 찾아야 한다');
  const make = compileApp('(viewingRelease, pendingRelease, openedDraft, openedKitApp, openedMega,'
    + ' currentProjectId, buildStart) => (' + memos[0].getText(ast) + ')');
  const run = (o = {}) => make(o.viewingRelease ?? null, o.pendingRelease ?? null,
    o.openedDraft ?? null, o.openedKitApp ?? null, o.openedMega ?? null,
    o.currentProjectId ?? null, o.buildStart ?? false)();

  //: ★★★ 조회가 **끝나기 전** — 종전에는 `viewingRelease` 가 비어 목적지를 잃었다.
  assert.deepEqual(run({ pendingRelease: 'rel_9' }), { kind: 'release', releaseId: 'rel_9' },
    '릴리스 조회 중에 주소가 목적지를 잃는다');
  //: 실패로 끝나도 주소는 그 릴리스를 가리킨다 — 사용자가 새로고침으로 다시 시도할 수 있다.
  assert.deepEqual(run({ pendingRelease: 'rel_9', viewingRelease: null }),
    { kind: 'release', releaseId: 'rel_9' });
  //: 성공하면 서버가 답한 식별자를 쓴다.
  assert.deepEqual(run({ pendingRelease: 'rel_9', viewingRelease: { release_id: 'rel_10' } }),
    { kind: 'release', releaseId: 'rel_10' });

  //: ★★★ `new` — 만들기 화면이 열렸는데 주소가 목록이면 새로고침이 입력을 버린다.
  assert.deepEqual(run({ buildStart: true }), { kind: 'new' }, '«새로 만들기» 가 주소에 없다');

  //: 다른 대상이 열려 있으면 그것이 먼저다(만들기는 그 위의 대화상자다).
  assert.deepEqual(run({ buildStart: true, currentProjectId: 'P1' }),
    { kind: 'project', projectId: 'P1' });
  assert.equal(run(), null, '아무것도 안 열렸는데 대상을 지어냈다');
});

// ── [FIX2 · 지시 3] 닫으면 «주소도» 그 대상을 놓는다 ────────────────────────
//   ⚠️ 실화면에서 잡힌 결함이다 — 화면은 닫혔는데 URL 이 「열려 있다」고 말하면,
//     새로고침이 방금 닫은 것을 다시 연다. 주소가 거짓말을 한다.
await test('FIX2 편집기·업무앱을 닫으면 그 대상이 주소에서도 사라진다', () => {
  const ast = appAst(); const handlers = {};
  (function walk(node) {
    if (ts.isJsxAttribute(node) && node.name.getText(ast) === 'onClose'
        && node.initializer && ts.isJsxExpression(node.initializer)) {
      const open = node.parent;                       // JsxAttributes → 여는 태그
      const element = open.parent;
      const tag = element && element.tagName ? element.tagName.getText(ast) : '';
      //: ⚠️ 같은 컴포넌트가 «모달» 과 «전체 화면(page)» 두 벌로 쓰인다. 둘은 다른 자리다 —
      //:   전체 화면 쪽은 애초에 대상을 기록하지 않으므로 지울 것도 없다. 섞으면 엉뚱한
      //:   핸들러를 단언하게 된다.
      const page = open.properties.some((a) => ts.isJsxAttribute(a) && a.name.getText(ast) === 'page');
      const key = tag + (page ? '[page]' : '');
      if (tag) (handlers[key] = handlers[key] || []).push(node.initializer.expression.getText(ast));
    }
    ts.forEachChild(node, walk);
  })(ast);
  for (const tag of ['BuildStartDialog', 'PathCalcPanel']) {
    assert.equal((handlers[tag] || []).length, 1, tag + ' 의 onClose 를 정확히 하나 찾아야 한다');
  }
  const cleared = (tag, names) => {
    const seen = {};
    const make = compileApp('(' + names.join(', ') + ') => (' + handlers[tag][0] + ')');
    make(...names.map((n) => (v) => { seen[n] = v; }))();
    return seen;
  };
  const editor = cleared('BuildStartDialog', ['setBuildStart', 'setOpenedDraft']);
  assert.equal(editor.setBuildStart, false);
  assert.equal(editor.setOpenedDraft, null, '편집기를 닫았는데 주소에 초안이 남는다');
  const kit = cleared('PathCalcPanel', ['setShowPathCalc', 'setOpenedKitApp']);
  assert.equal(kit.setShowPathCalc, false);
  assert.equal(kit.setOpenedKitApp, null, '업무앱을 닫았는데 주소에 업무앱이 남는다');
  //: 전체 화면 쪽은 `?space=path` 로 주소가 서고 대상을 기록하지 않는다 — 존재만 확인한다.
  assert.equal((handlers['PathCalcPanel[page]'] || []).length, 1);
});

// ── [FIX2 · 지시 4] 보호가 «실패» 하면 떠나지 않는다 ────────────────────────
//   ⚠️⚠️ 종전에는 `confirm` 이 예외를 던지면 catch 에서 `proceed()` 를 불렀다.
//     **보호 실패가 「이동 승인」으로 바뀌는** fail-open 이었고, 그 순간 미저장 입력이
//     사라진다. 잃는 것은 되돌릴 수 없으므로 막는 쪽으로 답한다.
await test('FIX2 미저장 보호: 확인을 못 띄우면 «떠나지 않는다»', () => {
  const guard = load('../src/factory/studioLeaveGuard.ts');

  // ① 보호가 없으면 묻지 않고 간다 — 물을 사람이 없는데 멈추면 앱이 잠긴다.
  guard.clearLeaveGuard();
  let went = 0;
  assert.equal(guard.confirmLeave(() => { went += 1; }), 'no-guard');
  assert.equal(went, 1);
  assert.equal(guard.canLeaveNow(), true);

  // ②★★★ 보호가 «있는데 실패» 하면 이동하지 않는다. 화면이 남으므로 다시 시도할 수 있다.
  const seen = [];
  guard.registerLeaveGuard({ safe: () => false,
    confirm: () => { throw new Error('확인창을 띄우지 못했다'); },
    onConfirmError: (error) => seen.push(String(error.message || error)) });
  went = 0;
  assert.equal(guard.confirmLeave(() => { went += 1; }), 'failed', '보호 실패를 「보호 없음」과 같게 답했다');
  assert.equal(went, 0, '보호가 실패했는데 떠나 버렸다 — 미저장 입력이 사라진다');
  assert.equal(seen.length, 1, '사용자에게 재시도할 수 있다고 알리지 않았다');

  // ③ 알림 «자체» 가 실패해도 이동이 생기지 않는다.
  guard.registerLeaveGuard({ safe: () => false,
    confirm: () => { throw new Error('x'); },
    onConfirmError: () => { throw new Error('알림도 실패'); } });
  went = 0;
  assert.equal(guard.confirmLeave(() => { went += 1; }), 'failed');
  assert.equal(went, 0, '알림 실패가 이동을 만들었다');

  // ④ 판단 자체가 실패하면 «막는 쪽» 으로 답한다.
  guard.registerLeaveGuard({ safe: () => { throw new Error('판단 실패'); }, confirm: () => {} });
  assert.equal(guard.canLeaveNow(), false, '판단이 실패했는데 안전하다고 답했다');

  // ⑤ 정상 경로는 그대로다.
  let asked = 0;
  const off = guard.registerLeaveGuard({ safe: () => false,
    confirm: (proceed) => { asked += 1; proceed(); } });
  went = 0;
  assert.equal(guard.confirmLeave(() => { went += 1; }), 'asked');
  assert.equal(asked, 1); assert.equal(went, 1);
  off();
  assert.equal(guard.canLeaveNow(), true, '해제했는데 보호가 남았다');
});

// ── [FIX2 · 실화면 실측] 첫 렌더부터 열려 있어야 군더더기 칸이 안 생긴다 ──────
//   ⚠️⚠️ 브라우저에서 잡았다. `?target=new` 로 들어가면 히스토리 칸이 **둘** 생기고
//     뒤로가기가 중간의 `?space=build` 로 갔다. effect 로 뒤늦게 열면 그 «사이» 렌더에서
//     `openTarget` 이 비어 URL 동기화가 목록 주소를 밀어 넣기 때문이다.
//   ★ 초기값을 «실행» 해서 본다 — 소스 문자열 검사가 아니다.
await test('FIX2 `new`·릴리스는 첫 렌더부터 열린다(중간 칸이 안 생긴다)', () => {
  const ast = appAst(); const inits = {};
  (function walk(node) {
    if (ts.isVariableDeclaration(node) && node.initializer && ts.isCallExpression(node.initializer)
        && node.initializer.expression.getText(ast) === 'useState'
        && ts.isArrayBindingPattern(node.name)) {
      const first = node.name.elements[0];
      const name = first && ts.isBindingElement(first) ? first.name.getText(ast) : '';
      if (['buildStart', 'pendingRelease'].includes(name) && !(name in inits)) {
        inits[name] = node.initializer.arguments[0] ? node.initializer.arguments[0].getText(ast) : 'undefined';
      }
    }
    ts.forEachChild(node, walk);
  })(ast);
  for (const name of ['buildStart', 'pendingRelease']) assert.ok(name in inits, name + ' 초기값을 찾지 못했다');
  const value = (source, entry) =>
    compileApp('(initialEntry) => (' + source + ')')({ current: entry });
  const none = { project: null, isNew: false, release: null, kitApp: null, mega: null, draft: null };
  assert.equal(value(inits.buildStart, { ...none, isNew: true }), true,
    '`?target=new` 인데 첫 렌더에 만들기 화면이 닫혀 있다 — 그 사이 렌더가 주소를 목록으로 민다');
  assert.equal(value(inits.buildStart, none), false, '아무 말 없는 주소인데 만들기 화면을 열었다');
  assert.equal(value(inits.pendingRelease, { ...none, release: 'rel_9' }), 'rel_9',
    '릴리스 주소인데 첫 렌더에 목적지를 들고 있지 않다');
  assert.equal(value(inits.pendingRelease, none), null);
});

// ── [FIX3 · 2026-09-18 실화면 실측] 화면을 닫는 곳은 «대상도» 놓아야 한다 ──────
//   ⚠️⚠️ 브라우저에서 잡았다. 「⌂ 경영 홈」을 누르면 업무앱 **화면은 닫히는데**
//     `openedKitApp` 이 남아 주소는 계속 `target=kit_app…` 이었다. 화면은 홈인데 주소는
//     업무앱이고, 새로고침하면 방금 떠난 화면이 다시 열린다.
//   ★ 「닫기」 하나만 고쳐 두면 **반대편 문**이 열려 있다. 화면을 내리는 자리를 모두 찾아
//     같은 짝을 단언한다. 소스 문자열 검사가 아니라 **뽑아서 실행한다.**
await test('FIX3 업무앱 화면을 내리는 곳은 «주소의 대상»도 함께 놓는다', () => {
  const ast = appAst();
  const run = (source, names) => {
    const seen = {};
    const make = compileApp('(' + names.join(', ') + ') => (' + source + ')');
    make(...names.map((n) => (v) => { seen[n] = v === undefined ? '(호출)' : v; }))();
    return seen;
  };

  // ① goHome — 모든 화면을 닫는 단 하나의 문.
  let goHome = null;
  (function walk(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'goHome'
        && node.initializer && ts.isCallExpression(node.initializer)) {
      goHome = node.initializer.arguments[0].getText(ast);
    }
    ts.forEachChild(node, walk);
  })(ast);
  assert.ok(goHome, 'goHome 을 찾지 못했다');
  //: 이 콜백은 화면 상태 setter 를 수십 개 부른다 — 이름을 본문에서 뽑아 전부 대역으로 준다.
  const names = Array.from(new Set(goHome.match(/set[A-Za-z]+|leaveRelease|closeRelease/g) || []));
  assert.ok(names.includes('setShowPathCalc'), 'goHome 이 업무앱 화면을 닫지 않는다');
  const home = run(goHome, names);
  assert.equal(home.setShowPathCalc, false);
  assert.equal(home.setOpenedKitApp, null,
    '홈으로 갔는데 주소는 업무앱을 가리킨다 — 새로고침하면 방금 떠난 화면이 다시 열린다');
  assert.equal(home.setCurrentProject, null, '홈으로 갔는데 주소에 프로젝트가 남는다');

  // ② 「경로 계산」 전체 화면 — 모달을 닫고 공간으로 간다. 같은 짝을 지켜야 한다.
  let pathCalc = null;
  (function walk(node) {
    if (ts.isObjectLiteralExpression(node)) {
      const id = node.properties.find((x) => ts.isPropertyAssignment(x)
        && x.name.getText(ast) === 'id' && x.initializer.getText(ast) === "'path-calc'");
      const sel = node.properties.find((x) => ts.isPropertyAssignment(x)
        && x.name.getText(ast) === 'onSelect');
      if (id && sel) pathCalc = sel.initializer.getText(ast);
    }
    ts.forEachChild(node, walk);
  })(ast);
  assert.ok(pathCalc, '「경로 계산」 메뉴의 onSelect 를 찾지 못했다');
  const calcNames = Array.from(new Set(pathCalc.match(/set[A-Za-z]+/g) || []));
  const calc = run(pathCalc, calcNames);
  assert.equal(calc.setShowPathCalc, false);
  assert.equal(calc.setOpenedKitApp, null,
    '전체 화면으로 갔는데 주소는 모달의 업무앱을 가리킨다');
  assert.equal(calc.setSpace, 'path');
});

// ── [FIX4 · 검토 A] 배너로 주소를 «되돌린 뒤» 의 연속 이동 ──────────────────
//   ⚠️⚠️ 검토가 짚은 자리: 「이 화면의 주소로 되돌리기」가 현재 칸의 주소만 바꾸고
//     **우리 눈금(historyIndex)은 옛 화면 것을 그대로** 두면, 다음 명시 이동에 잘못된
//     번호를 붙인다. 그 뒤의 뒤로/앞으로는 **남의 눈금**으로 계산된다.
//   ★ 그래서 번호에 «구간»(epoch)을 함께 찍고, 같은 구간일 때만 차이를 쓴다. 번호를
//     모르면 지어내지 않고 기존 안전 동작(배너)으로 간다.
await test('FIX4 미관리 칸 → 주소 복구 → 다른 대상 → 뒤로: 남의 눈금으로 계산하지 않는다', () => {
  const ast = appAst();
  const pick = (kind) => {
    const out = [];
    (function walk(node) {
      if (ts.isCallExpression(node) && node.expression.getText(ast) === 'useEffect'
          && node.getText(ast).includes(kind)) out.push(node.arguments[0]);
      ts.forEachChild(node, walk);
    })(ast);
    assert.equal(out.length, 1, kind + ' 효과를 정확히 하나 찾아야 한다');
    return out[0].getText(ast);
  };
  const urlEffect = pick('serializeStudioLocation');
  const popEffect = pick("'popstate'");
  //: 배너 버튼의 onClick 을 **라벨로** 찾아 뽑는다 — 소스 문자열 검사가 아니라 실행이다.
  let restoreClick = null;
  (function walk(node) {
    if (ts.isJsxElement(node) && node.openingElement.tagName.getText(ast) === 'button'
        && node.children.map((c) => c.getText(ast)).join('').includes('이 화면의 주소로 되돌리기')) {
      const attr = node.openingElement.attributes.properties.find(
        (a) => ts.isJsxAttribute(a) && a.name.getText(ast) === 'onClick');
      if (attr) restoreClick = attr.initializer.expression.getText(ast);
    }
    ts.forEachChild(node, walk);
  })(ast);
  assert.ok(restoreClick, '배너의 「되돌리기」 onClick 을 찾지 못했다');

  const makeUrl = compileApp('(routeRestored, window, openTarget, serializeStudioLocation, space,'
    + ' restoringFromPop, historyIndex, historyEpoch, newEpoch) => (' + urlEffect + ')');
  const makePop = compileApp('(window, skipNextPop, leavingAnyway, canLeaveNow, confirmLeave,'
    + ' applyStudioEntry, readStudioEntry, restoringFromPop, historyIndex, pendingApproval,'
    + ' setStrandedEntry, historyEpoch, newEpoch, setContextBlocked) => (' + popEffect + ')');
  const makeRestore = compileApp('(window, historyIndex, historyEpoch, newEpoch,'
    + ' setStrandedEntry, restoringFromPop, setAddressNonce, setContextBlocked) => ('
    + restoreClick + ')');

  //: ① 미관리 칸  ② 우리 칸(번호 0, 구간 E1)  — 지금은 ② 에 있다.
  const stack = [{ url: '/app?a', state: {} },
                 { url: '/app?space=build&target=draft&draft_kind=blueprint&draft=d1&revision=1',
                   state: { __studioIndex: 0, __studioEpoch: 'E1' } }];
  let at = 1;
  const queue = [], log = [], win = { location: null };
  const sync = () => { const u = new URL(stack[at].url, 'http://x');
    win.location = { href: u.href, pathname: u.pathname, search: u.search, hash: u.hash }; };
  win.history = {
    get state() { return stack[at].state; },
    get length() { return stack.length; },
    go(n) { log.push('go:' + n); if (n === 0) { log.push('RELOAD'); return; }
      const to = Math.max(0, Math.min(stack.length - 1, at + n));
      if (to === at) { log.push('nowhere'); return; }
      at = to; sync(); queue.push({ state: stack[at].state }); },
    back() { win.history.go(-1); },
    pushState(state, _t, url) { log.push('push'); stack.splice(at + 1);
      stack.push({ url, state }); at = stack.length - 1; sync(); },
    replaceState(state, _t, url) { log.push('replace'); stack[at] = { url, state }; sync(); },
  };
  let popHandler = null;
  win.addEventListener = (e, f) => { if (e === 'popstate') popHandler = f; };
  win.removeEventListener = () => {};
  sync();

  const index = { current: 0 }, epoch = { current: 'E1' }, restoring = { current: false };
  const stranded = [];
  const newEpoch = () => { epoch.current = 'E' + (Math.random() * 1e6 | 0); return epoch.current; };
  let target = { kind: 'draft', draftKind: 'blueprint', draftId: 'd1', revision: 1 };
  let space = 'build', safe = false, nonce = 0;
  const render = () => makeUrl(true, win, target, location.serializeStudioLocation, space,
    restoring, index, epoch, newEpoch)();
  makePop(win, { current: false }, { current: false }, () => safe, () => {},
    () => { target = null; space = 'build'; },
    () => ({ project: null, isNew: false, release: null, kitApp: null, mega: null, draft: null }),
    restoring, index, { current: null }, (v) => { if (v) stranded.push(v); }, epoch, newEpoch,
    () => {})();
  //: ⚠️ 붙잡히지 않은(배너로 남긴) popstate 는 `openTarget`·`space` 를 바꾸지 않으므로
  //:   실제 앱에서도 URL 효과가 **다시 돌지 않는다.** 여기서 자동으로 render 하면
  //:   제품에 없는 이동을 만들어 낸다.
  const press = (n) => { at = Math.max(0, Math.min(stack.length - 1, at + n)); sync();
    popHandler({ state: stack[at].state }); while (queue.length) popHandler(queue.shift()); };

  // ① 미관리 칸으로 뒤로 — 미저장 입력이 있으니 붙잡지 않고 «배너» 로 남긴다.
  press(-1);
  assert.equal(at, 0, '미관리 칸으로 가지 못했다');
  assert.equal(stranded.length, 1, '어긋난 주소를 보이지 않았다');
  assert.equal(log.some((x) => x.startsWith('go:')), false, '위치를 모르면서 이동을 지어냈다');
  assert.equal(index.current, 0, '적용도 안 했는데 번호를 옮겼다');

  // ②★★★ 「이 화면의 주소로 되돌리기」 — 현재 칸에는 번호가 «없다».
  makeRestore(win, index, epoch, newEpoch, () => {}, restoring, (fn) => { nonce = fn(nonce); },
    () => {})();
  assert.equal(index.current, null,
    '번호 없는 칸으로 눈금을 맞추지 않고 «옛 화면의 번호»를 그대로 들고 있다');
  assert.notEqual(epoch.current, 'E1', '구간을 새로 열지 않아 옛 눈금과 섞인다');
  render();
  assert.equal(at, 0, '되돌리기가 칸을 옮겼다');
  assert.equal(log.includes('push'), false, '되돌리기가 새 칸을 만들었다');
  assert.ok(log.includes('replace'), '현재 칸의 주소를 바꾸지 않았다');
  assert.ok(win.location.search.includes('draft=d1'), '이 화면의 주소로 돌아오지 않았다');

  // ③ 다른 대상으로 명시 이동 — 새 구간에서 0 부터 센다.
  const fresh = epoch.current;
  target = { kind: 'project', projectId: 'P9' };
  render();
  assert.equal(at, 1); assert.equal(stack.length, 2, '앞쪽 칸을 정리하지 않았다');
  assert.equal(stack[1].state.__studioIndex, 0, '번호를 모르는데 옛 번호 + 1 을 붙였다');
  assert.equal(stack[1].state.__studioEpoch, fresh, '새 칸에 현재 구간을 안 찍었다');
  assert.equal(index.current, 0);

  // ④ 그 뒤 뒤로 — 앞의 칸은 **구간이 다른 남의 칸**이다. 정수 차이로 방향을 추정하지 않는다.
  const before = log.length;
  press(-1);
  assert.equal(log.slice(before).some((x) => x.startsWith('go:')), false,
    '구간이 다른 칸과의 정수 차이로 이동을 계산했다');
  assert.equal(stranded.length, 2, '다시 어긋났는데 사용자에게 보이지 않았다');

  // ─────────────────────────────────────────────────────────────────────────
  /** 짧은 대역 하나 — 구간이 섞인 히스토리를 만들어 popstate 만 돌린다. */
  const scene = ({ entries, at: start, here, epoch: mine, safe: ok }) => {
    let pos = start;
    const moves = [], applied = [], strandedHere = [];
    const w = {
      location: { search: '?x' },
      history: {
        get state() { return entries[pos].state; },
        get length() { return entries.length; },
        go(n) { moves.push(n); },
        back() { moves.push(-1); },
      },
      addEventListener: (e, f) => { if (e === 'popstate') w._h = f; },
      removeEventListener: () => {},
    };
    const idx = { current: here }, ep = { current: mine };
    makePop(w, { current: false }, { current: false }, () => ok, () => {},
      () => applied.push(pos),
      () => ({ project: null, isNew: false, release: null, kitApp: null, mega: null, draft: null }),
      { current: false }, idx, { current: null },
      (v) => { if (v) strandedHere.push(v); }, ep,
      () => { ep.current = 'E' + (Math.random() * 1e6 | 0); return ep.current; }, () => {})();
    return { go: (n) => { pos += n; w._h({ state: entries[pos].state }); },
             moves, applied, stranded: strandedHere, idx, ep };
  };

  // ⑤★★★ [검토 A] **구간이 다른 «번호 있는» 칸** — 정수 차이가 그럴듯해도 쓰지 않는다.
  //   ⚠️ 번호를 잃은 뒤 0 부터 다시 세므로, 옛 구간의 2 와 새 구간의 0 사이에 「2」라는
  //     멀쩡해 보이는 차이가 생긴다. 구간을 안 보면 그 차이로 `go(-2)` 를 부른다.
  const mixed = scene({
    entries: [{ state: { __studioIndex: 2, __studioEpoch: 'OLD' } },
              { state: {} },
              { state: { __studioIndex: 0, __studioEpoch: 'NEW' } }],
    at: 2, here: 0, epoch: 'NEW', safe: false });
  mixed.go(-2);
  assert.deepEqual(mixed.moves, [],
    '구간이 다른 칸의 번호로 이동을 계산했다 — 남의 눈금이다');
  assert.deepEqual(mixed.applied, [], '확인 전에 화면을 바꿨다');
  assert.equal(mixed.stranded.length, 1, '어긋난 주소를 보이지 않았다');

  // ⑥ 같은 구간이면 종전처럼 «정확히» 되돌린다 — 구간 검사가 정상 이동을 막지 않는다.
  const same = scene({
    entries: [{ state: { __studioIndex: 0, __studioEpoch: 'NEW' } },
              { state: { __studioIndex: 1, __studioEpoch: 'NEW' } },
              { state: { __studioIndex: 2, __studioEpoch: 'NEW' } }],
    at: 2, here: 2, epoch: 'NEW', safe: false });
  same.go(-2);
  assert.deepEqual(same.moves, [2], '같은 구간인데 두 칸을 되돌리지 않았다');
  assert.equal(same.stranded.length, 0, '같은 구간인데 배너로 넘겼다');

  // ⑦★★★ 번호를 «잃으면» 구간도 새로 연다 — 안 열면 다음 칸이 옛 눈금과 섞인다.
  const lost = scene({
    entries: [{ state: {} }, { state: { __studioIndex: 3, __studioEpoch: 'OLD' } }],
    at: 1, here: 3, epoch: 'OLD', safe: true });
  lost.go(-1);
  assert.deepEqual(lost.applied, [0], '잃을 것이 없는데 화면을 안 맞췄다');
  assert.equal(lost.idx.current, null, '없는 번호를 지어냈다');
  assert.notEqual(lost.ep.current, 'OLD',
    '남의 칸으로 왔는데 옛 구간을 그대로 쓴다 — 다음에 만드는 칸이 옛 눈금과 섞인다');

});

// ── [B6-CONTEXT-SSE-01 · 결정 ②] 회사·행위자가 바뀌면 «여섯 대상 모두» 다시 확인한다 ──
//   ⚠️⚠️ 종전에는 `project` 하나만 다시 확인했다. 초안·업무앱·메가·릴리스가 열려 있으면
//     **옛 문맥의 화면이 그대로 남는다** — 권한이 좁아진 문맥에서도 보이던 것이 계속 보인다.
//   ★ 뽑아서 **실행한다**. 주소를 여섯 가지로 바꿔 가며 「무엇을 다시 확인하는가」를 본다.
await test('B6 문맥이 바뀌면 열린 «조회 대상» 다섯을 다시 확인한다(new 는 조회 대상이 아니다)', () => {
  const ast = appAst();
  let fn = null;
  (function walk(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'revalidateOpenEntry'
        && node.initializer && ts.isCallExpression(node.initializer)) {
      fn = node.initializer.arguments[0].getText(ast);
    }
    ts.forEachChild(node, walk);
  })(ast);
  assert.ok(fn, 'revalidateOpenEntry 를 찾지 못했다');

  //: 실제 `readStudioEntry`(문법은 파서 한 곳)로 주소를 해석한다 — 대역 규칙을 새로 만들지 않는다.
  let entryFn = null;
  (function walk(node) {
    if (ts.isFunctionDeclaration(node) && node.name && node.name.getText(ast) === 'readStudioEntry') {
      entryFn = node.getText(ast);
    }
    ts.forEachChild(node, walk);
  })(ast);
  assert.ok(entryFn, 'readStudioEntry 를 찾지 못했다');
  const js = ts.transpileModule('export ' + entryFn, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  const em = { exports: {} };
  new Function('module', 'exports', 'parseStudioLocation', js)(em, em.exports, location.parseStudioLocation);

  const make = compileApp('(window, readStudioEntry, applyStudioEntryRef, strandedRef) => ('
    + fn + ')');
  const run = (search, stranded = null) => {
    const applied = [];
    globalThis.window.location = { search };
    make(globalThis.window, em.exports.readStudioEntry, { current: (e) => applied.push(e) },
      { current: stranded })();
    return applied;
  };

  const F = '?space=build&target=';
  //: ★ 조회 대상 다섯 — 전부 서버에 다시 물어야 한다.
  //:   ⚠️ [검토 2026-09-18] `new` 는 **조회할 대상이 없다.** 그래서 여기 없고, 「여섯 대상
  //:     모두 서버 재확인」이라고 쓰지 않는다. 새 문맥에서의 입력 분리는 별개 경우다.
  const cases = [
    ['project', F + 'project&project=P1', (e) => e.project === 'P1'],
    ['mega', F + 'mega&mega=M1&child=C1', (e) => e.mega && e.mega.megaProjectId === 'M1'],
    ['draft', F + 'draft&draft_kind=blueprint&draft=adv_1&revision=2', (e) => e.draft && e.draft.draftId === 'adv_1'],
    ['kit_app', F + 'kit_app&instance=ki_1&app=APP-01', (e) => e.kitApp && e.kitApp.instanceId === 'ki_1'],
    ['release', F + 'release&release=rel_9', (e) => e.release === 'rel_9'],
  ];
  for (const [name, search, ok] of cases) {
    const applied = run(search);
    assert.equal(applied.length, 1, name + ' 을 다시 확인하지 않았다 — 옛 문맥 화면이 남는다');
    assert.ok(ok(applied[0]), name + ' 의 대상이 그대로 전달되지 않았다');
  }

  // ★ 목록·홈·`new` 는 «조회할» 것이 없다 — 괜히 화면을 흔들지 않는다.
  for (const search of ['?space=build', '?space=operate', '', F + 'new']) {
    assert.deepEqual(run(search), [], '확인할 대상이 없는데 화면을 다시 그렸다: ' + (search || '(빈 주소)'));
  }

  //: ★★★ [결정 1] **주소와 화면이 어긋난 동안에는 URL 을 «열린 대상» 으로 믿지 않는다.**
  //:   그 값으로 다시 확인하면 엉뚱한 것을 확인한다. 안전하게 «정리만» 한다.
  const strandedRun = run(F + 'project&project=P1', { project: 'P9' });
  assert.equal(strandedRun.length, 1, '어긋난 상태에서 아무 정리도 하지 않았다');
  assert.equal(strandedRun[0].project, null, '어긋난 주소를 그대로 믿고 다시 확인했다');
  assert.equal(strandedRun[0].draft, null);
  assert.equal(strandedRun[0].kitApp, null);
});

// ── 두 전환 이벤트 «모두» 가 그 재확인을 부른다 ─────────────────────────────
await test('B6 회사 전환과 행위자 전환 둘 다 재확인을 부른다', () => {
  const ast = appAst();
  const found = [];
  (function walk(node) {
    if (ts.isCallExpression(node) && node.expression.getText(ast) === 'useEffect') {
      const text = node.getText(ast);
      //: ⚠️ 같은 이벤트에 구독이 «여럿» 이다(예: 릴리스 목적지 정리). 재확인을 부르는
      //:   효과만 고른다 — 아무거나 집으면 있는 통제를 없다고 답한다.
      for (const ev of ['factory:acting-user-changed', 'factory:enterprise-context-changed']) {
        if (text.includes(ev) && text.includes('revalidateOpenEntry')) {
          found.push([ev, node.arguments[0].getText(ast)]);
        }
      }
    }
    ts.forEachChild(node, walk);
  })(ast);
  for (const ev of ['factory:acting-user-changed', 'factory:enterprise-context-changed']) {
    const hit = found.filter(([e]) => e === ev);
    assert.equal(hit.length, 1, ev + ' 구독 효과를 정확히 하나 찾아야 한다');
    //: ⚠️ 문자열 검사가 아니라 **효과를 실행해** 리스너를 붙이고, 이벤트를 던져서 본다.
    //: 효과 본문이 부르는 다른 setter 도 이름을 뽑아 대역으로 준다(행위자 쪽은 목록 갱신자가 있다).
    const extra = Array.from(new Set((hit[0][1].match(/set[A-Za-z]+/g) || [])));
    const make = compileApp('(window, connectSSE, revalidateOpenEntry'
      + extra.map((n) => ', ' + n).join('') + ') => (' + hit[0][1] + ')');
    const calls = [];
    let handler = null;
    const win = { addEventListener: (e, f) => { if (e === ev) handler = f; },
                  removeEventListener: () => {} };
    const cleanup = make(win, () => calls.push('sse'), () => calls.push('revalidate'),
      ...extra.map(() => () => {}))();
    assert.ok(handler, ev + ' 에 리스너를 붙이지 않았다');
    handler();
    assert.deepEqual(calls, ['sse', 'revalidate'],
      ev + ' 가 SSE 재연결과 대상 재확인을 둘 다 하지 않는다');
    cleanup();
  }
});

// ── [B6-CONTEXT · 결정 1] 전환을 여는 «단 하나의 문» ────────────────────────
//   ⚠️ 대상을 연 화면에도 칩을 달았으므로 **미저장 입력을 든 채로** 눌릴 수 있다.
//     새 정책을 만들지 않고 기존 보호(`confirmLeave`)를 그대로 태운다.
//   ⚠️⚠️ 그리고 주소·화면이 어긋난 동안에는 **무엇이 열려 있는지 URL 로 알 수 없다.**
//     그 상태로 전환하면 「무엇을 다시 확인할지」를 모른 채 확인하게 된다 — 먼저 고르게 한다.
await test('B6 전환 버튼: 미저장이면 묻고, 취소하면 «문맥이 바뀌지 않는다»', () => {
  const ast = appAst();
  let door = null;
  (function walk(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'openContextSwitcher'
        && node.initializer && ts.isCallExpression(node.initializer)) {
      door = node.initializer.arguments[0].getText(ast);
    }
    ts.forEachChild(node, walk);
  })(ast);
  assert.ok(door, 'openContextSwitcher 를 찾지 못했다');

  const run = ({ stranded = null, safe = true, decide = null }) => {
    const seen = { opened: 0, blocked: 0, asked: 0 };
    const make = compileApp('(strandedEntry, setContextBlocked, confirmLeave, setShowContextSwitcher)'
      + ' => (' + door + ')');
    make(stranded,
      (v) => { if (v) seen.blocked += 1; },
      (proceed) => { seen.asked += 1; if (safe || decide === 'leave') proceed(); },
      (v) => { if (v) seen.opened += 1; })();
    return seen;
  };

  // ① 잃을 것이 없으면 그대로 열린다.
  assert.deepEqual(run({ safe: true }), { opened: 1, blocked: 0, asked: 1 });

  // ②★★★ 미저장인데 **취소** 하면 전환 창이 열리지 않는다 — 문맥이 바뀔 기회 자체가 없다.
  assert.deepEqual(run({ safe: false }), { opened: 0, blocked: 0, asked: 1 },
    '취소했는데 전환 창이 열렸다 — 그대로 고르면 미저장 입력이 사라진다');

  // ③ 「떠난다」를 고르면 그때 열린다.
  assert.deepEqual(run({ safe: false, decide: 'leave' }), { opened: 1, blocked: 0, asked: 1 });

  // ④★★★ 주소가 어긋난 동안에는 **열지 않고** 먼저 고르라고 말한다.
  assert.deepEqual(run({ stranded: { project: 'P9' }, safe: true }),
    { opened: 0, blocked: 1, asked: 0 },
    '무엇이 열려 있는지 모르는 상태에서 문맥을 바꿨다');
});

// ── 칩은 «한 벌» 이다 — 셸과 대상 화면이 같은 것을 쓴다 ─────────────────────
await test('B6 회사 문맥 칩을 화면마다 새로 그리지 않는다', () => {
  const shell = fs.readFileSync(new URL('../src/components/ProductShell.tsx', import.meta.url), 'utf8');
  const app = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const dialog = fs.readFileSync(new URL('../src/components/BuildStartDialog.tsx', import.meta.url), 'utf8');
  //: 접근 이름과 클래스를 «만드는» 곳은 공용 컴포넌트 한 곳뿐이어야 한다.
  const made = (src) => (src.match(/className="afs-context"/g) || []).length;
  assert.equal(made(shell), 1, '셸에서 칩 마크업이 하나가 아니다');
  assert.equal(made(app), 0, 'App 이 칩을 직접 그린다 — 모양·접근 이름이 갈라진다');
  assert.equal(made(dialog), 0, '대화상자가 칩을 직접 그린다 — 모양·접근 이름이 갈라진다');
  //: ★ 대신 **공용 컴포넌트를 쓴다** — 작업공간과 초안 편집기 두 곳 모두.
  //: ⚠️ [검토 §3] **거절(Gate) 화면에도** 같은 칩이 있어야 한다 — 없으면 권한 있는 범위로
  //:   돌아가려고 홈까지 나갔다 와야 한다. 작업공간·초안 편집기·거절 화면 셋이다.
  assert.equal((app.match(/<OperatingContextChip/g) || []).length, 3,
    '작업공간·초안 편집기·거절 화면 세 곳에서 공용 칩을 쓰지 않는다');
  //: ⚠️ 대화상자는 초점을 가둔다 — 칩을 **자기 안** 에 받아 그려야 키보드로 닿는다.
  assert.match(dialog, /\{contextChip\}/);
  //: ★ 전환 창은 기존 하나다. 새 전환 UI 를 만들지 않았다.
  assert.equal((app.match(/<OperatingContextSwitcher/g) || []).length, 1);
});


// ── [§10.1 「코드·문서 내려받기」] 앵커가 아니라 «세션을 실어» 받는다 ──────────
//   ⚠️⚠️ 2026-09-19 격리 실측: `a.href = .../export` 는 헤더를 못 실어 **401** 이었다.
//     서버는 세션 헤더가 있으면 200 · application/zip 을 준다. 즉 **서버는 멀쩡한데
//     버튼만 되지 않았고**, 그 실패가 화면에 나오지도 않아 「눌렀는데 아무 일도 없다」였다.
//   ★ 실제 모듈을 불러 **실행** 한다 — 어떤 요청이 나가는지, 실패 사유를 나누는지 본다.
await test('§10.1 내려받기: 앵커 대신 fetch 로 받고 실패 사유를 구분한다', async () => {
  const calls = [];
  const savedAnchors = [];
  const api = {
    API_BASE_URL: 'https://synthetic.invalid',
    //: ★ 앱의 `fetch` 는 세션·문맥 헤더를 자동으로 붙인다 — 그래서 «fetch 로 받는가» 가 핵심이다.
    apiFetch: async (path, init) => { calls.push({ path, init }); return api.__reply(path); },
    __reply: async () => new Response('zip-bytes', { status: 200,
      headers: { 'content-type': 'application/zip',
                 'content-disposition': 'attachment; filename="prj_x-2026.zip"' } }),
  };
  //: 이 시험이 보는 것은 «내려받기» 하나다. 실행 명령 모듈은 부르지 않으므로 대역으로 막고,
  //: 혹시 불리면 **터지게** 둔다 — 조용히 통과시키면 무엇을 쟀는지 알 수 없다.
  let identity = 'A';
  const mod = load('../src/factory/sprintActions.ts', {
    '../lib/api': api,
    './studioInputMemory': { studioIdentityKey: () => identity },
    '../lib/studioExecutionApi': new Proxy({}, { get: (_, key) => {
      if (key === 'PROJECT_TASK') return 'project';
      return () => { throw new Error('이 시험은 실행 명령을 부르지 않는다: ' + String(key)); };
    } }),
  });

  //: 브라우저 저장 경로를 대역으로 잡는다 — 무엇을 어떤 이름으로 저장하는지 본다.
  const prevURL = globalThis.URL.createObjectURL, prevRevoke = globalThis.URL.revokeObjectURL;
  const prevDoc = globalThis.document;
  let objectUrls = 0;
  globalThis.URL.createObjectURL = () => { objectUrls += 1; return 'blob:synthetic'; };
  globalThis.URL.revokeObjectURL = () => {};
  globalThis.document = { createElement: () => { const a = { click() { savedAnchors.push({ ...a }); } }; return a; },
    body: { appendChild() {}, removeChild() {} } };
  try {
    // ① 성공 — 서버가 준 파일명을 쓴다(우리가 지어내지 않는다).
    const ok = await mod.downloadProjectArchive('prj_x');
    assert.equal(calls.length, 1, 'fetch 로 받지 않았다 — 앵커면 세션이 안 실린다');
    assert.equal(calls[0].path, '/api/v1/factory/prj_x/export');
    assert.equal(ok.ok, true);
    assert.equal(ok.filename, 'prj_x-2026.zip', '서버가 정한 파일명을 쓰지 않았다');
    assert.equal(savedAnchors.length, 1, '받은 내용을 저장하지 않았다');
    assert.equal(savedAnchors[0].download, 'prj_x-2026.zip');
    assert.equal(savedAnchors[0].href, 'blob:synthetic', '앵커가 서버 URL 로 직접 이동한다');

    // ②★★★ 실패 사유를 **나눈다** — 셋은 사용자가 할 일이 서로 다르다.
    //: ⚠️ 404 는 「없다」를 확정하지 않는다 — 은닉 계약(현재 문맥에서 안 보일 수도 있다).
    const cases = [[401, /로그인/], [403, /권한/], [404, /찾을 수 없거나 현재 문맥/], [500, /500/]];
    for (const [status, shape] of cases) {
      api.__reply = async () => new Response('', { status });
      const bad = await mod.downloadProjectArchive('prj_x');
      assert.equal(bad.ok, false, status + ' 인데 성공이라고 했다');
      assert.equal(bad.status, status);
      assert.match(bad.reason, shape, status + ' 의 사유가 구분되지 않는다: ' + bad.reason);
    }
    //: ⚠️ 실패했으면 **저장하지 않는다** — 빈 파일을 내려받게 하면 더 나쁘다.
    assert.equal(savedAnchors.length, 1, '실패했는데 파일을 저장했다');

    //: ★★★ [보완 1] 받기·저장 준비 실패도 **결과 계약**으로 돌아온다(예외로 새지 않는다).
    api.__reply = async () => ({ ok: true, status: 200,
      headers: { get: () => '' }, blob: async () => { throw new Error('stream broke'); } });
    const broken = await mod.downloadProjectArchive('prj_x');
    assert.equal(broken.ok, false, 'blob 실패가 예외로 샜다');
    assert.match(broken.reason, /끝까지 읽지 못했습니다/);
    assert.doesNotMatch(broken.reason, /stream broke/, '예외 원문을 그대로 노출했다');

    const prevCreate = globalThis.URL.createObjectURL;
    globalThis.URL.createObjectURL = () => { throw new Error('no blob url'); };
    api.__reply = async () => new Response('zip', { status: 200, headers: { 'content-disposition': '' } });
    const noSave = await mod.downloadProjectArchive('prj_x');
    globalThis.URL.createObjectURL = prevCreate;
    assert.equal(noSave.ok, false, '저장 준비 실패가 예외로 샜다');
    assert.match(noSave.reason, /저장을 시작하지 못했습니다/);
    assert.equal(savedAnchors.length, 1, '실패했는데 파일 저장을 시작했다');

    //: ★★★ [보완 2] **늦게 도착한 결과**는 저장을 시작하지 않는다.
    //:   ⚠️ 이미 브라우저로 넘긴 다운로드는 취소할 수 없다 — 그래서 «시작 전» 만 막는다.
    //: ★ 응답 «직후» 에 멈추면 본문을 읽지도, blob URL 을 만들지도 않는다 — 일을 더 하지 않는다.
    let blobReads = 0;
    const urlsBefore = objectUrls;
    api.__reply = async () => { identity = 'B'; return { ok: true, status: 200,
      headers: { get: () => '' }, blob: async () => { blobReads += 1; return new Blob(['zip']); } }; };
    const stale = await mod.downloadProjectArchive('prj_x');
    assert.equal(stale.ok, false, '문맥이 바뀐 뒤에도 내려받기를 시작했다');
    assert.match(stale.reason, /회사·사용자가 바뀌어/);
    assert.equal(savedAnchors.length, 1, '늦은 결과가 파일 저장을 시작했다');
    assert.equal(blobReads, 0, '문맥이 바뀌었는데 본문을 계속 읽었다');
    assert.equal(objectUrls, urlsBefore, '문맥이 바뀌었는데 blob URL 을 만들었다');
    identity = 'A';

    //: ★★★ 문맥이 «본문을 읽는 동안» 바뀌어도 막는다. 응답 직후 검사만 있으면 여기서 샌다.
    const urlsAfterStale = objectUrls;
    api.__reply = async () => ({ ok: true, status: 200, headers: { get: () => '' },
      blob: async () => { identity = 'C'; return new Blob(['zip']); } });
    const lateBody = await mod.downloadProjectArchive('prj_x');
    assert.equal(lateBody.ok, false, '본문을 읽는 동안 문맥이 바뀌었는데 저장을 시작했다');
    assert.match(lateBody.reason, /회사·사용자가 바뀌어/);
    assert.equal(savedAnchors.length, 1, '늦은 본문이 파일 저장을 시작했다');
    //: ★ 본문을 읽는 동안 바뀌었으면 **blob URL 도 만들지 않는다**.
    assert.equal(objectUrls, urlsAfterStale, '본문 중 문맥이 바뀌었는데 blob URL 을 만들었다');
    identity = 'A';

    //: ★★★ 저장 «준비 중» 에 바뀌어도 막는다 — 클릭 직전 검사가 없으면 여기서 샌다.
    const prevCreate2 = globalThis.URL.createObjectURL;
    globalThis.URL.createObjectURL = () => { identity = 'D'; return 'blob:synthetic'; };
    api.__reply = async () => new Response('zip', { status: 200 });
    const lateSave = await mod.downloadProjectArchive('prj_x');
    globalThis.URL.createObjectURL = prevCreate2;
    assert.equal(lateSave.ok, false, '클릭 직전에 문맥이 바뀌었는데 저장을 시작했다');
    assert.equal(savedAnchors.length, 1, '클릭 직전 검사가 없다');
    identity = 'A';

    //: ★ 결과에 **요청 대상**이 실린다 — 호출부가 남의 화면에 안내를 붙이지 않게.
    api.__reply = async () => new Response('zip', { status: 200 });
    const tagged = await mod.downloadProjectArchive('prj_y');
    assert.equal(tagged.projectId, 'prj_y');

    // ③ 연결 자체가 끊겨도 «조용히» 끝내지 않는다.
    api.apiFetch = async () => { throw new Error('offline'); };
    const off = await mod.downloadProjectArchive('prj_x');
    assert.equal(off.ok, false);
    assert.match(off.reason, /연결/);

    // ④ 대상이 없으면 부르지도 않는다.
    const none = await mod.downloadProjectArchive('');
    assert.equal(none.ok, false);
  } finally {
    globalThis.URL.createObjectURL = prevURL;
    globalThis.URL.revokeObjectURL = prevRevoke;
    globalThis.document = prevDoc;
  }
});

// ── 두 화면이 «같은 함수» 를 부른다 — 각자 앵커를 만들면 다시 갈라진다 ──────
await test('§10.1 내려받기: 두 화면이 앵커를 직접 만들지 않는다', () => {
  const run = fs.readFileSync(new URL('../src/factory/RunControls.tsx', import.meta.url), 'utf8');
  const panel = fs.readFileSync(new URL('../src/components/ControlPanel.tsx', import.meta.url), 'utf8');
  for (const [name, src] of [['RunControls', run], ['ControlPanel', panel]]) {
    assert.match(src, /downloadProjectArchive\(/, name + ' 이 공용 내려받기 함수를 쓰지 않는다');
    //: ⚠️ `/export` 주소를 화면이 다시 조립하면 그 순간 세션 없는 앵커로 돌아간다.
    assert.doesNotMatch(src, /a\.href\s*=\s*[^;]*\/export/,
      name + ' 이 아직 서버 주소로 직접 이동한다 — 세션이 실리지 않는다');
  }
});


// ── [검토 2026-09-19] 안내는 «완료 시점의 화면» 에만 붙는다 ────────────────
//   ⚠️⚠️ 종전에는 `result.projectId !== pid` 였다. `pid` 는 **요청을 시작한 렌더**의
//     클로저 값이라 결과와 늘 같다 — A 요청 뒤 B 로 옮겨도 통과했다. 「대상 확인」이 아니라
//     자기 자신과의 비교였고, 특히 `ControlPanel` 의 `alert` 는 **전역**이라 다른 화면 위에 떴다.
//   ★ 두 호출부의 onClick 을 **뽑아서 실행** 한다 — A 요청 → B 전환 → A 완료.
await test('내려받기 안내: A 요청 → B 전환 → A 완료 시 B 화면에 붙지 않는다', async () => {
  const read = (rel) => fs.readFileSync(new URL(rel, import.meta.url), 'utf8');

  /** 파일에서 「코드·문서 내려받기」 onClick 본문을 뽑는다(라벨로 찾는다). */
  const pickHandler = (src, marker) => {
    const file = ts.createSourceFile('x.tsx', src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    let found = null;
    (function walk(node) {
      if (ts.isJsxAttribute(node) && node.name.getText(file) === 'onClick'
          && node.initializer && ts.isJsxExpression(node.initializer)) {
        //: ⚠️ `JsxAttribute.parent` 는 여는 태그가 아니라 **속성 묶음**(`JsxAttributes`) 이다.
        //:   두 칸 올려야 여는 태그이고, 그것만 읽으면 «자식 텍스트»가 빠진다 —
        //:   구 ControlPanel 은 라벨이 `<button>` 안에 글로 있어서 못 찾았다(실제로 한 번 빨강).
        const open = node.parent && node.parent.parent;
        const element = open && open.parent && ts.isJsxElement(open.parent) ? open.parent : open;
        const text = element ? element.getText(file) : '';
        if (text.includes(marker)) found = node.initializer.expression.getText(file);
      }
      ts.forEachChild(node, walk);
    })(file);
    assert.ok(found, marker + ' 의 onClick 을 찾지 못했다');
    return found;
  };

  //: 대역 store — 「지금 열린 프로젝트」를 시험이 바꿀 수 있게 한다.
  let current = 'A';
  const store = { getState: () => ({ currentProjectId: current }) };
  let pending = null;
  const download = (pid) => new Promise((resolve) => { pending = { pid, resolve }; });

  // ── ① 새 Studio(RunControls) ───────────────────────────────────────────
  const runHandler = pickHandler(read('../src/factory/RunControls.tsx'), '코드·문서 내려받기');
  const notes = [];
  const alive = { current: true };
  const runClick = compileApp('(pid, downloadProjectArchive, setNote, alive, useFactoryStore) => ('
    + runHandler + ')')('A', download, (v) => notes.push(v), alive, store);

  runClick();                                   // A 에서 요청
  current = 'B';                                // 화면이 B 로 바뀐다
  pending.resolve({ ok: true, projectId: 'A', filename: 'A.zip', bytes: 1 });
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(notes, [], 'A 결과가 B 화면에 안내를 남겼다');

  //: 실패 결과도 마찬가지다 — 오류 문구가 남의 화면에 뜨면 더 나쁘다.
  runClick();
  current = 'B';
  pending.resolve({ ok: false, projectId: 'A', reason: '권한이 없습니다.', status: 403 });
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(notes, [], 'A 의 오류가 B 화면에 떴다');

  //: ★ 양성 대조 — 화면이 그대로면 **반드시** 붙는다. 없으면 「아무것도 안 붙는」 시험이 된다.
  current = 'A';
  runClick();
  pending.resolve({ ok: true, projectId: 'A', filename: 'A.zip', bytes: 1 });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(notes.length, 1, '현재 화면인데 안내가 붙지 않았다');
  assert.equal(notes[0].ok, true);
  assert.match(notes[0].text, /시작했습니다/);

  //: ⚠️ 화면이 사라졌으면(unmount) 붙이지 않는다 — 같은 A 로 다시 들어온 새 화면도 별개다.
  alive.current = false;
  runClick();
  pending.resolve({ ok: true, projectId: 'A', filename: 'A.zip', bytes: 1 });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(notes.length, 1, '사라진 화면에 안내를 남겼다');
  alive.current = true;

  // ── ② 종전 통제실(ControlPanel) — `alert` 는 전역이라 더 위험하다 ────────
  const panelHandler = pickHandler(read('../src/components/ControlPanel.tsx'), '산출물 코드 ZIP 다운로드');
  const alerts = [];
  const panelClick = compileApp('(currentProjectId, downloadProjectArchive, alert, useFactoryStore)'
    + ' => (' + panelHandler + ')')('A', download, (m) => alerts.push(m), store);

  current = 'A';
  panelClick();
  current = 'B';
  pending.resolve({ ok: false, projectId: 'A', reason: '권한이 없습니다.', status: 403 });
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(alerts, [], 'A 의 오류 alert 가 B 화면 위에 떴다');

  current = 'A';
  panelClick();
  pending.resolve({ ok: false, projectId: 'A', reason: '권한이 없습니다.', status: 403 });
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(alerts, ['권한이 없습니다.'], '현재 화면인데 오류를 알리지 않았다');
});

// ── [FIX3] 중복 mount·재조회 — React 훅을 «흉내 내어 실제로 두 번 렌더»한다 ──────
//   ⚠️ 정적 검사가 아니다. useCallback/useMemo 는 실제 React 처럼 의존성 얕은비교로
//     기억하고, useEffect 는 의존성을 기록한다. 두 번째 렌더에서 의존성이 그대로면
//     React 는 효과를 **다시 돌리지 않는다** — 그 사실을 여기서 확인한다.
function hookHarness() {
  const slots = []; let index = 0; const effects = [];
  const same = (a, b) => Array.isArray(a) && Array.isArray(b) && a.length === b.length
    && a.every((v, i) => Object.is(v, b[i]));
  const api = {
    __esModule: true,
    useState: (init) => { const i = index++; if (!slots[i]) slots[i] = { v: typeof init === 'function' ? init() : init }; return [slots[i].v, (n) => { slots[i].v = n; }]; },
    useRef: (init) => { const i = index++; if (!slots[i]) slots[i] = { current: init }; return slots[i]; },
    useCallback: (fn, deps) => { const i = index++; if (!slots[i] || !same(slots[i].deps, deps)) slots[i] = { fn, deps }; return slots[i].fn; },
    useMemo: (fn, deps) => { const i = index++; if (!slots[i] || !same(slots[i].deps, deps)) slots[i] = { v: fn(), deps }; return slots[i].v; },
    useEffect: (fn, deps) => { effects.push(deps); },
    useSyncExternalStore: (_s, snap) => snap(),
  };
  api.default = api;
  //: ⚠️ 효과는 «렌더별로» 묶는다 — 한 컴포넌트가 효과를 둘 이상 쓰면 평평한 배열의
  //:   인덱스가 밀려, 같은 렌더의 다른 효과를 «다음 렌더» 로 착각한다(실제로 당했다).
  return { api, effects, render(component, props) {
    index = 0; effects.length = 0; component(props); return effects.slice();
  } };
}
function appComponent(name, extraParams = []) {
  const ast = appAst(); let found = null;
  (function walk(node) {
    if (ts.isFunctionDeclaration(node) && node.name && node.name.getText(ast) === name) found = node;
    ts.forEachChild(node, walk);
  })(ast);
  assert.ok(found, name + ' 을 찾지 못했다');
  // ⚠️ 함수만 뽑으면 `React` 가 자유변수로 남는다 — 같은 가짜 모듈을 주입한다.
  const js = ts.transpileModule('const React = require("react");'
    + ' const { useCallback, useEffect, useState, useMemo, useRef, useSyncExternalStore } = React;'
    + ' export ' + found.getText(ast), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  return (react, extras = {}) => {
    const mod = { exports: {} };
    new Function('module', 'exports', 'require', js)(mod, mod.exports, (dep) => {
      if (dep === 'react') return react;
      if (Object.hasOwn(extras, dep)) return extras[dep];
      if (dep === 'react/jsx-runtime') return { jsx: () => null, jsxs: () => null, Fragment: null };
      throw new Error('예상하지 않은 의존성: ' + dep);
    });
    return mod.exports[name];
  };
}

await test('FIX3 진입 커밋은 «콜백 신원»이 바뀌어도 다시 돌지 않는다', () => {
  const load = appComponent('StudioEntryCommit');
  const h = hookHarness();
  const Commit = load(h.api);
  const entry = { project_id: 'P1', child: null };
  const first = h.render(Commit, { entry, onCommit: () => 'first' });
  const second = h.render(Commit, { entry, onCommit: () => 'second' });   // ★ 새 인라인 화살표
  assert.deepEqual(first, second,
    '콜백 신원이 바뀌자 효과 의존성이 바뀌었다 — setCurrentProject 가 반복된다');
  assert.equal(first[0].length, 1, '의존성은 «무엇을 열 것인가» 하나여야 한다');
  // 대상이 실제로 바뀌면 «다시» 돌아야 한다 — 통제가 너무 조여 있지 않은지 반대편도 본다.
  const third = h.render(Commit, { entry: { project_id: 'P2', child: null }, onCommit: () => 'third' });
  assert.notDeepEqual(third, second, '대상이 바뀌었는데 다시 돌지 않는다');
});

await test('FIX3 업무앱 커밋도 같은 규칙을 지킨다', () => {
  const load = appComponent('KitAppEntryCommit');
  const h = hookHarness();
  const Commit = load(h.api);
  const entry = { instance_id: 'ki_1', app_id: 'app_1' };
  const a = h.render(Commit, { entry, onCommit: () => 'a' });
  const b = h.render(Commit, { entry, onCommit: () => 'b' });
  assert.deepEqual(a, b);
  assert.equal(a[0].length, 2);
});

await test('FIX3 초안 열기도 콜백 때문에 다시 부르지 않는다', () => {
  const load = appComponent('DraftOpenCommit');
  const h = hookHarness();
  const Commit = load(h.api, { './lib/studioRequirementDraft': { openDraftRevision: async () => ({ deliverable: 'software_app' }) } });
  const entry = { draft_id: 'adv_1', revision: 2,
    ownership: { tenant_id: 't', context_root_id: 'r', entity_mode: 'REAL', scope_node_id: 's' } };
  const a = h.render(Commit, { entry, onOpened: () => 'a' });
  // ⚠️ ownership 을 «새 객체»로 넘긴다 — 실제 App 이 그렇게 넘길 수 있다.
  const b = h.render(Commit, { entry: { ...entry, ownership: { ...entry.ownership } }, onOpened: () => 'b' });
  assert.deepEqual(a, b, '콜백·소유객체 신원 때문에 초안을 다시 불러온다');
  //: ★ 폐기용 효과가 하나 더 있어야 한다 — 화면이 사라지면 버튼 요청도 함께 끊는다.
  assert.equal(a.length, 2, '언마운트 폐기 효과가 없다');
});
await test('소스·검사 해시 보존', () => assert.deepEqual(hashes(), before));
const failed = results.filter(row => row.result === 'FAIL');
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length,
  browser: 'NOT_RUN', network: 'MOCK_ONLY', source_hashes: before, results }, null, 2));
if (failed.length) process.exitCode = 1;
