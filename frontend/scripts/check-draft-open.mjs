// [DRAFT-OPEN-01] 확인된 초안의 «지정 판본» 불러오기. 모의 HTTP + **실제 제품 모듈**.
// ★ processInstallationApi 와 studioRequirementDraft 를 대역이 아니라 실제로 싣는다 —
//   검증 경로가 제품 경로여야 한다. 대역으로 만들면 계약을 내 말로 다시 쓰게 된다.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import ts from 'typescript';
const files = ['../src/lib/studioRequirementDraft.ts', '../src/lib/processInstallationApi.ts',
  './check-draft-open.mjs'];
const hashes = () => Object.fromEntries(files.map(f => [f, createHash('sha256').update(fs.readFileSync(new URL(f, import.meta.url))).digest('hex')]));
const before = hashes();
function load(file, deps = {}) {
  const url = new URL(file, import.meta.url), native = createRequire(url), mod = { exports: {} };
  const js = ts.transpileModule(fs.readFileSync(url, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  } }).outputText;
  new Function('module', 'exports', 'require', js)(mod, mod.exports, name => {
    if (Object.hasOwn(deps, name)) return deps[name];
    if (['react'].includes(name)) return native(name);
    throw new Error('예상하지 않은 의존성: ' + name);
  });
  return mod.exports;
}
globalThis.window = new EventTarget();
let context, actor, calls, responder;
const api = {
  apiFetch: async (url, init) => { calls.push({ url, init }); return responder(url, init); },
  getEnterpriseContext: () => context, getActingUser: () => actor, getSessionToken: () => 'synthetic',
};
const process_ = load(files[1], { './api': api });
const module = load(files[0], { './api': api, './processInstallationApi': process_ });

const OWNER = { tenant_id: 'tenant-a', context_root_id: 'root-a', entity_mode: 'REAL', scope_node_id: 'scope-a' };
const DRAFT = 'adv_1ea9be5dfff4468e9508ac85c61f9b28';
const revision = (changes = {}) => ({ draft_id: DRAFT, revision_id: 'rev_1', revision: 2,
  digest: 'a'.repeat(64), status: 'DRAFT', author_actor: 'someone-else@test.invalid',
  context_key: { ...OWNER },
  blueprint: { title: '구매 승인 자동화', business: { objective: '구매 승인을 빠르게' },
    system: { template_id: 'tpl-1' },
    request_options: { deliverable_type: 'software_app', is_mega: false,
      knowledge_pack_ids: ['pack-1'], master_domains: ['purchase', 'finance'],
      mcp_live_grounding: true, kit_instance_id: 'ki_1', kit_start_instance_id: '' } },
  process_ref: null, ...changes });
const ok = (data) => new Response(JSON.stringify({ status: 'success', data }), { status: 200 });
const fail = (status, reason_code) => new Response(
  JSON.stringify({ detail: { reason_code, message: '서버 원문' } }), { status });
const target = (changes = {}) => ({ draftId: DRAFT, revision: 2, ownership: { ...OWNER }, ...changes });
const results = [];
async function test(name, run) {
  context = { tenantId: 'tenant-a', scopeNodeId: 'scope-a', entityMode: 'REAL' };
  actor = 'viewer@test.invalid'; calls = []; responder = async () => ok(revision());
  // 싱글턴 메모리를 시험마다 비운다 — 앞 시험의 입력이 다음 판정을 바꾸면 안 된다.
  window.dispatchEvent(new Event('factory:session-changed'));
  try { await run(); results.push({ name, result: 'PASS' }); }
  catch (error) { results.push({ name, result: 'FAIL', error: String(error.stack || error) }); }
}

// ── ★★★ 지정 판본을, 서버가 준 경계로 ────────────────────────────────────
await test('OPEN 지정 판본을 «서버가 준 경계» 로 부른다', async () => {
  const result = await module.openDraftRevision(target());
  assert.equal(result.deliverable, 'software_app');
  assert.equal(result.revision.revision, 2);
  assert.equal(calls.length, 1);
  const url = calls[0].url;
  assert.ok(url.startsWith(`/api/v1/advisor/drafts/${DRAFT}?`), url);
  assert.ok(url.includes('context_root_id=root-a'), url);   // ★ 선택 문맥이 아니라 소유 경계
  assert.ok(url.includes('scope_node_id=scope-a'), url);
  assert.ok(url.includes('revision=2'), url);               // ★ 최신판이 아니라 지정 판본
  assert.equal(calls[0].init.cache, 'no-store');
  assert.equal(calls[0].init.method, undefined);            // 조회만. 쓰기 0회
});
await test('OPEN 선택 문맥이 달라도 «소유 경계» 로 부른다', async () => {
  context = { tenantId: 'tenant-a', scopeNodeId: 'another-scope', entityMode: 'REAL' };
  await module.openDraftRevision(target());
  assert.ok(calls[0].url.includes('scope_node_id=scope-a'), calls[0].url);
  assert.ok(!calls[0].url.includes('another-scope'), calls[0].url);
});
await test('OPEN 내용이 입력 양식으로 «되돌아온다»', async () => {
  await module.openDraftRevision(target());
  const state = module.getStudioRequirementDraft('software_app').getSnapshot();
  assert.equal(state.form.initialIdea, '구매 승인을 빠르게');
  assert.equal(state.form.projectName, '구매 승인 자동화');
  assert.equal(state.form.templateId, 'tpl-1');
  assert.deepEqual(state.form.packIds, ['pack-1']);
  assert.equal(state.form.masterDomains, 'purchase, finance');
  assert.equal(state.form.mcpLiveGrounding, true);
  assert.equal(state.form.kitInstanceId, 'ki_1');
  assert.equal(state.receipt.revision, 2);
  // ★ 불러온 판본은 «저장된» 상태다 — 화면이 미저장으로 오해하지 않는다.
  assert.equal(state.savedForm, JSON.stringify(state.form));
  assert.equal(state.attempt, null);
});
await test('OPEN 제목이 아이디어 대체값이면 이름 칸을 비운다', async () => {
  const idea = '이 문장이 곧 제목이 된다';
  responder = async () => ok(revision({ blueprint: { ...revision().blueprint,
    title: idea, business: { objective: idea } } }));
  await module.openDraftRevision(target());
  // ⚠️ 채우면 사용자가 적지 않은 이름을 적은 것처럼 보인다. 재저장 제목은 그대로다.
  assert.equal(module.getStudioRequirementDraft('software_app').getSnapshot().form.projectName, '');
});

// ── ⑤ 종류를 모르면 «막는다» ──────────────────────────────────────────────
for (const [label, options] of [['없음', {}], ['모르는 값', { deliverable_type: 'spaceship' }],
    ['문자열 아님', { deliverable_type: 7 }]]) {
  await test('OPEN 산출물 종류를 모르면 막는다 — ' + label, async () => {
    responder = async () => ok(revision({ blueprint: { ...revision().blueprint,
      request_options: { ...revision().blueprint.request_options, ...options,
        ...(Object.keys(options).length ? {} : { deliverable_type: undefined }) } } }));
    await assert.rejects(module.openDraftRevision(target()),
      e => e.reasonCode === 'STUDIO_DELIVERABLE_UNKNOWN');
    // 어떤 편집기에도 앉히지 않는다 — 추측해 덮지 않는다.
    for (const kind of ['software_app', 'hybrid_simulation', 'document_report']) {
      assert.equal(module.getStudioRequirementDraft(kind).getSnapshot().receipt, null);
    }
  });
}
await test('OPEN 종류가 다르면 그 종류의 편집기에 앉는다', async () => {
  responder = async () => ok(revision({ blueprint: { ...revision().blueprint,
    request_options: { ...revision().blueprint.request_options, deliverable_type: 'document_report' } } }));
  const result = await module.openDraftRevision(target());
  assert.equal(result.deliverable, 'document_report');
  assert.equal(module.getStudioRequirementDraft('document_report').getSnapshot().receipt.revision, 2);
  assert.equal(module.getStudioRequirementDraft('software_app').getSnapshot().receipt, null);
});

// ── ID·판본·경계 불일치 거절 ──────────────────────────────────────────────
for (const [label, changes] of [
    ['다른 초안', { draft_id: 'adv_other' }],
    ['다른 판본', { revision: 3 }],
    ['다른 경계', { context_key: { ...OWNER, scope_node_id: 'scope-b' } }],
    ['지문 형식 위반', { digest: 'not-a-digest' }],
    ['모르는 상태', { status: 'WHATEVER' }],
    ['내용 없음', { blueprint: null }]]) {
  await test('OPEN 응답 불일치 거절 — ' + label, async () => {
    responder = async () => ok(revision(changes));
    await assert.rejects(module.openDraftRevision(target()), e => e.status === 503);
    assert.equal(module.getStudioRequirementDraft('software_app').getSnapshot().receipt, null);
  });
}
await test('OPEN 잘못된 대상은 통신 전 차단', async () => {
  for (const bad of [target({ draftId: '' }), target({ revision: 0 }), target({ revision: 1.5 }),
      target({ ownership: { ...OWNER, context_root_id: '' } })]) {
    await assert.rejects(module.openDraftRevision(bad), e => e.reasonCode === 'STUDIO_OPEN_TARGET_INVALID');
  }
  assert.equal(calls.length, 0);
});
await test('OPEN 서버 거절은 그대로 전달된다 — 진입 확인이 권한 토큰이 아니다', async () => {
  responder = async () => fail(404, 'PROCESS_NOT_FOUND');
  const error = await module.openDraftRevision(target()).catch(e => e);
  assert.equal(error.status, 404);
  assert.equal(module.getStudioRequirementDraft('software_app').getSnapshot().receipt, null);
});

// ── ⑥ 미저장 입력을 «말없이» 덮지 않는다 ─────────────────────────────────
await test('OPEN 미저장 입력이 있으면 멈추고 묻는다', async () => {
  const draft = module.getStudioRequirementDraft('software_app');
  draft.update({ initialIdea: '내가 적던 내용' });
  await assert.rejects(module.openDraftRevision(target()), e => e.reasonCode === 'STUDIO_UNSAVED_INPUT');
  // ★ 입력이 **그대로 남아 있다**.
  assert.equal(draft.getSnapshot().form.initialIdea, '내가 적던 내용');
  assert.equal(draft.getSnapshot().receipt, null);
});
await test('OPEN 확인을 받으면 그때 바꾼다', async () => {
  const draft = module.getStudioRequirementDraft('software_app');
  draft.update({ initialIdea: '내가 적던 내용' });
  await module.openDraftRevision(target(), { replaceUnsaved: true });
  assert.equal(draft.getSnapshot().form.initialIdea, '구매 승인을 빠르게');
  assert.equal(draft.getSnapshot().receipt.revision, 2);
});

// ── ⑦ 조회가 수정 권한이 되지 않는다 · 과거판 충돌 유지 ──────────────────
await test('OPEN 불러오기가 권한을 만들지 않는다', async () => {
  const draft = module.getStudioRequirementDraft('software_app');
  await module.openDraftRevision(target());
  const state = draft.getSnapshot();
  // 권한은 access 응답이 정한다. 불러오기는 그것을 건드리지 않는다.
  assert.equal(state.access, null);
  assert.equal(calls.length, 1, '불러오기가 추가 요청을 보냈다');
});
await test('OPEN 과거판을 불러오면 저장 기대값이 «그 판본» 이다', async () => {
  responder = async () => ok(revision({ revision: 1, revision_id: 'rev_old' }));
  await module.openDraftRevision(target({ revision: 1 }));
  const state = module.getStudioRequirementDraft('software_app').getSnapshot();
  // ★ 최신판으로 조용히 바꾸지 않는다 — 저장하면 서버가 충돌로 막는다.
  assert.equal(state.receipt.revision, 1);
  assert.equal(state.receipt.revision_id, 'rev_old');
});

// ── 문맥 전환 ─────────────────────────────────────────────────────────────
await test('OPEN 회사·사용자가 바뀌면 앉힌 초안도 사라진다', async () => {
  const draft = module.getStudioRequirementDraft('software_app');
  await module.openDraftRevision(target());
  assert.equal(draft.getSnapshot().receipt.revision, 2);
  window.dispatchEvent(new Event('factory:session-changed'));
  assert.equal(draft.getSnapshot().receipt, null);
  // 새 싱글턴도 비어 있다.
  assert.equal(module.getStudioRequirementDraft('software_app').getSnapshot().receipt, null);
});
await test('OPEN 조회만으로 저장·승인·생성이 일어나지 않는다', async () => {
  await module.openDraftRevision(target());
  const writes = calls.filter(row => (row.init?.method || 'GET') !== 'GET');
  assert.deepEqual(writes, [], '조회 중 쓰기 요청이 나갔다');
  assert.equal(module.getStudioRequirementDraft('software_app').getSnapshot().creationState, 'IDLE');
});

// ── ⑥ seed/싱글턴과 로드 결과가 서로 덮지 않는다 ────────────────────────
await test('OPEN 편집기 mount 의 initialize(seed) 가 «불러온 내용을 덮지 않는다»', async () => {
  //: ★★★ `BuildStartDialog` 는 mount 때 `flow.initialize({templateId: 첫 템플릿, ...seed})`
  //:   를 부른다. 불러오기가 «초기화됨» 을 세우지 않으면 그 호출이 빈 양식으로 덮는다.
  //:   실제로 그랬고, 이 시험이 그 순서를 고정한다.
  const draft = module.getStudioRequirementDraft('software_app');
  await module.openDraftRevision(target());
  draft.initialize({ templateId: 'tpl-from-mount', initialIdea: '화면이 넣는 seed' });
  const form = draft.getSnapshot().form;
  assert.equal(form.initialIdea, '구매 승인을 빠르게', 'seed 가 불러온 내용을 덮었다');
  assert.equal(form.templateId, 'tpl-1', 'seed 템플릿이 불러온 템플릿을 덮었다');
  assert.equal(draft.getSnapshot().receipt.revision, 2);
});
await test('OPEN 반대로, 먼저 초기화한 화면에 불러오면 «확인» 을 요구한다', async () => {
  const draft = module.getStudioRequirementDraft('software_app');
  draft.initialize({ initialIdea: '화면이 넣은 seed' });
  await assert.rejects(module.openDraftRevision(target()), e => e.reasonCode === 'STUDIO_UNSAVED_INPUT');
  assert.equal(draft.getSnapshot().form.initialIdea, '화면이 넣은 seed');
});

// ── [FIX1 · P1] 늦은 응답이 «새 문맥» 입력에 반영되면 안 된다 ──────────────
//   ⚠️⚠️ 화면의 alive 검사로는 못 막는다 — adopt 는 그보다 «먼저» 저장소에 쓴다.
//     그래서 여기서는 화면이 아니라 **adopt 부작용 자체**를 본다.
const deferred = () => { let resolve; const p = new Promise(r => { resolve = r; }); return { p, resolve }; };
const stores = () => ['software_app', 'hybrid_simulation', 'document_report']
  .map(k => ({ kind: k, state: module.getStudioRequirementDraft(k).getSnapshot() }));
const contaminated = () => stores().filter(s => s.state.receipt || s.state.form.initialIdea);

await test('P1 A문맥 요청 → B문맥 전환 → A응답: 어느 저장소도 오염되지 않는다', async () => {
  const gate = deferred();
  responder = () => gate.p;
  const pending = module.openDraftRevision(target()).catch(e => e);
  // ★ 응답이 오기 «전에» 회사가 바뀐다.
  context = { tenantId: 'tenant-B', scopeNodeId: 'scope-B', entityMode: 'REAL' };
  actor = 'someone.else@test.invalid';
  gate.resolve(ok(revision()));
  const outcome = await pending;
  assert.ok(outcome instanceof Error, '문맥이 바뀌었는데 성공으로 끝났다');
  assert.deepEqual(contaminated(), [], '늦은 응답이 입력 저장소에 반영됐다');
  // 옛 문맥으로 돌아가도 남아 있으면 안 된다.
  context = { tenantId: 'tenant-a', scopeNodeId: 'scope-a', entityMode: 'REAL' };
  actor = 'viewer@test.invalid';
  assert.deepEqual(contaminated(), [], '옛 문맥 저장소에 반영됐다');
});

await test('P1 초안1 → 초안2 «역순» 응답: 늦게 온 옛 요청이 덮지 않는다', async () => {
  const first = deferred(), second = deferred();
  let n = 0;
  responder = () => (++n === 1 ? first.p : second.p);
  const a = module.openDraftRevision(target({ draftId: 'adv_first' })).catch(e => e);
  const b = module.openDraftRevision(target({ draftId: 'adv_second' })).catch(e => e);
  // 둘째가 먼저 도착하고, 첫째가 «나중에» 도착한다.
  second.resolve(ok(revision({ draft_id: 'adv_second' })));
  await b;
  first.resolve(ok(revision({ draft_id: 'adv_first' })));
  await a;
  const state = module.getStudioRequirementDraft('software_app').getSnapshot();
  assert.equal(state.receipt && state.receipt.draft_id, 'adv_second',
    '늦게 온 옛 요청이 최신 결과를 덮었다');
});

await test('P1 요청 폐기 후 도착한 응답은 반영되지 않는다', async () => {
  const gate = deferred();
  responder = () => gate.p;
  const handle = module.openDraftRevision(target(), { signal: (() => {
    const c = new AbortController(); setTimeout(() => c.abort(), 0); return c.signal; })() }).catch(e => e);
  await new Promise(r => setTimeout(r, 10));
  gate.resolve(ok(revision()));
  const outcome = await handle;
  assert.ok(outcome instanceof Error, '폐기했는데 성공으로 끝났다');
  assert.deepEqual(contaminated(), [], '폐기된 요청의 응답이 반영됐다');
});

await test('P1 저장소가 «다른 문맥에서 시작한» 결과를 스스로 거부한다', async () => {
  //: ★★★ 호출부가 아니라 **쓰는 자리**가 막는지 본다. 앞선 세 시험은 `openDraftRevision`
  //:   을 통해서만 확인하므로, 그 함수를 우회하는 경로가 생기면 조용히 뚫린다.
  const draft = module.getStudioRequirementDraft('software_app');
  const row = revision();
  // 지금 문맥에서 시작한 결과는 앉는다.
  draft.adoptRevision(row, { expectIdentity: draft.identity });
  assert.equal(draft.getSnapshot().receipt.draft_id, DRAFT);
  // ⚠️ 다른 문맥에서 시작한 결과는 거부된다 — 이 인스턴스의 문맥은 «지금» 이라
  //   assertCurrent 만으로는 통과해 버린다.
  const before = JSON.stringify(draft.getSnapshot().form);
  assert.throws(() => draft.adoptRevision(revision({ draft_id: 'adv_from_other_company' }),
    { expectIdentity: 'some-other-identity', replaceUnsaved: true }),
    (e) => e.reasonCode === 'STUDIO_FOREIGN_CONTEXT_RESULT');
  assert.equal(draft.getSnapshot().receipt.draft_id, DRAFT, '남의 문맥 결과가 앉았다');
  assert.equal(JSON.stringify(draft.getSnapshot().form), before, '입력이 바뀌었다');
});

await test('소스·검사 해시 보존', () => assert.deepEqual(hashes(), before));
const failed = results.filter(row => row.result === 'FAIL');
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length,
  browser: 'NOT_RUN', network: 'MOCK_ONLY', modules: 'REAL_PRODUCT_MODULES',
  source_hashes: before, results }, null, 2));
if (failed.length) process.exitCode = 1;
