// 실제 Zustand store와 App 상태 분기를 실행한다. 통신은 대역, 브라우저/서버 승인은 별도다.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { createHash, randomUUID } from 'node:crypto';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const files = ['../src/store/useFactoryStore.ts', '../src/App.tsx', './check-release-entry.mjs'];
const hashes = () => Object.fromEntries(files.map(file => [file,
  createHash('sha256').update(fs.readFileSync(new URL(file, import.meta.url))).digest('hex')]));
const before = hashes();
const source = fs.readFileSync(new URL(files[0], import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
} }).outputText;
const native = createRequire(import.meta.url);
const initialIdentity = { token: 'synthetic-token', user: 'synthetic-user',
  tenantId: 'tenant-a', scopeNodeId: 'scope-a', entityMode: 'REAL' };
const payload = id => ({ release_id: id, project_name: '합성 결과물 ' + id,
  frontend_code_summary: 'SYNTHETIC_ONLY', lifecycle: { usable: false } });
const response = (id, status = 200) => new Response(JSON.stringify({
  status: 'success', data: payload(id),
}), { status });
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => {
  resolve = yes; reject = no;
}); return { promise, resolve, reject }; };
function world() {
  let identity = { ...initialIdentity };
  const window = new EventTarget(), calls = [];
  let reply = async () => response('A');
  const api = { API_BASE_URL: 'https://synthetic.invalid',
    getSessionToken: () => identity.token, getActingUser: () => identity.user,
    getEnterpriseContext: () => identity };
  const fetch = async (url, options = {}) => { calls.push({ url, options }); return reply(url, options); };
  const module = { exports: {} };
  new Function('module', 'exports', 'require', 'window', 'fetch', compiled)(
    module, module.exports, name => {
      if (name === 'zustand') return native(name);
      if (name === '../lib/api') return api;
      if (name === '../factory/sprintActions') return new Proxy({}, {
        get: (_, key) => () => { throw new Error('예상하지 않은 쓰기 호출: ' + String(key)); },
      });
      throw new Error('허용하지 않은 의존성: ' + name);
    }, window, fetch);
  const store = module.exports.useFactoryStore;
  return { store, window, calls, read: id => store.getState().viewRelease(id),
    close: () => store.getState().closeRelease(),
    state: () => store.getState(),
    reply: fn => { reply = fn; },
    identity: patch => { identity = { ...identity, ...patch }; } };
}
const results = [];
async function test(name, fn) {
  const w = world();
  try { await fn(w); results.push({ name, result: 'PASS' }); }
  catch (error) { results.push({ name, result: 'FAIL', error: String(error.stack || error) }); }
  finally { w.close(); }
}
function closed(w) {
  assert.equal(w.state().viewingRelease, null);
  assert.equal(w.state().releaseLoad, 'idle');
  assert.equal(w.state().releaseError, '');
}

await test('정상 단건 GET·no-store·취소 신호·실행 권한은 그대로', async w => {
  await w.read('A');
  assert.equal(w.calls.length, 1);
  assert.equal(w.calls[0].url, 'https://synthetic.invalid/api/v1/factory/library/item/A');
  assert.equal(w.calls[0].options.method, 'GET');
  assert.equal(w.calls[0].options.cache, 'no-store');
  assert.ok(w.calls[0].options.signal instanceof AbortSignal);
  assert.deepEqual(w.state().viewingRelease, payload('A'));
  assert.equal(w.state().releaseLoad, 'idle');
});
await test('새 조회 시작 즉시 이전 결과물을 숨긴다', async w => {
  await w.read('A');
  const gate = deferred(); w.reply(() => gate.promise);
  const pending = w.read('B');
  assert.equal(w.state().viewingRelease, null);
  assert.equal(w.state().releaseLoad, 'loading');
  gate.resolve(response('B')); await pending;
  assert.equal(w.state().viewingRelease.release_id, 'B');
});
for (const stage of ['headers', 'body']) {
  await test('닫기 뒤 늦은 ' + stage + ' 응답은 화면을 열지 않는다', async w => {
    const gate = deferred(), reached = deferred();
    w.reply(() => stage === 'headers' ? gate.promise : {
      ok: true, json: () => { reached.resolve(); return gate.promise; },
    });
    const pending = w.read('A');
    if (stage === 'body') await reached.promise;
    w.close(); closed(w);
    gate.resolve(stage === 'headers' ? response('A') : { status: 'success', data: payload('A') });
    await pending; closed(w);
    assert.equal(w.calls[0].options.signal.aborted, true);
  });
}
for (const late of ['success', 'http-error', 'network-error', 'invalid-json']) {
  await test('A→B 역순 응답에서 늦은 A ' + late + ' 폐기', async w => {
    const gate = deferred();
    w.reply(url => url.endsWith('/A') ? gate.promise : response('B'));
    const a = w.read('A'); await w.read('B');
    if (late === 'network-error') gate.reject(new Error('PRIVATE'));
    else if (late === 'invalid-json') gate.resolve({ ok: true, json: async () => { throw new Error('PRIVATE'); } });
    else gate.resolve(response('A', late === 'http-error' ? 403 : 200));
    await a;
    assert.equal(w.state().viewingRelease.release_id, 'B');
    assert.equal(w.state().releaseLoad, 'idle');
    assert.equal(w.state().releaseError, '');
  });
}
await test('최신 B 거절을 늦은 A 성공이 지우지 않는다', async w => {
  const gate = deferred();
  w.reply(url => url.endsWith('/A') ? gate.promise : response('B', 403));
  const a = w.read('A'); await w.read('B');
  gate.resolve(response('A')); await a;
  assert.equal(w.state().viewingRelease, null);
  assert.equal(w.state().releaseLoad, 'forbidden');
});
await test('같은 ID 재조회와 닫기 후 재열기도 요청을 구분한다', async w => {
  const gate = deferred(); w.reply(() => gate.promise);
  const first = w.read('A');
  w.close(); w.reply(async () => new Response(JSON.stringify({
    status: 'success', data: { ...payload('A'), project_name: '최신' },
  })));
  await w.read('A'); gate.resolve(response('A')); await first;
  assert.equal(w.state().viewingRelease.project_name, '최신');
});
await test('닫지 않고 같은 ID 재조회해도 최신 요청만 표시한다', async w => {
  const gate = deferred(); w.reply(() => gate.promise);
  const first = w.read('A');
  w.reply(async () => new Response(JSON.stringify({
    status: 'success', data: { ...payload('A'), project_name: '재조회' },
  })));
  await w.read('A'); gate.resolve(response('A')); await first;
  assert.equal(w.state().viewingRelease.project_name, '재조회');
  assert.equal(w.calls[0].options.signal.aborted, true);
});
await test('오래된 요청의 finally가 최신 취소 신호를 지우지 않는다', async w => {
  const a = deferred(), b = deferred();
  w.reply(url => url.endsWith('/A') ? a.promise : b.promise);
  const first = w.read('A'), second = w.read('B');
  a.resolve(response('A')); await first;
  assert.equal(w.calls[0].options.signal.aborted, true);
  assert.equal(w.calls[1].options.signal.aborted, false);
  w.close(); assert.equal(w.calls[1].options.signal.aborted, true);
  b.resolve(response('B')); await second; closed(w);
});
for (const event of ['factory:session-changed', 'factory:acting-user-changed', 'factory:enterprise-context-changed']) {
  for (const pending of [false, true]) {
    await test(event + (pending ? ' 중 늦은 응답 폐기' : ' 시 표시된 원문 즉시 제거'), async w => {
      const gate = deferred();
      if (pending) w.reply(() => gate.promise);
      const read = w.read('A');
      if (!pending) await read;
      // 값이 A→B→A로 돌아와도 이벤트 세대가 지난 요청은 재사용하지 않는다.
      w.window.dispatchEvent(new Event(event)); closed(w);
      w.window.dispatchEvent(new Event(event));
      if (pending) { gate.resolve(response('A')); await read; closed(w); }
      assert.equal(w.calls.length, 1, '전환은 자동 재조회/쓰기하지 않는다');
      w.reply(async () => response('B')); await w.read('B');
      assert.equal(w.state().viewingRelease.release_id, 'B');
    });
  }
}
for (const key of Object.keys(initialIdentity)) {
  await test('이벤트 없는 ' + key + ' 변경도 이전 응답 수용 금지', async w => {
    const gate = deferred(); w.reply(() => gate.promise);
    const read = w.read('A'); w.identity({ [key]: 'other' });
    gate.resolve(response('A')); await read;
    closed(w);
  });
}
for (const status of [401, 403, 404, 500]) {
  await test('최신 HTTP ' + status + ' 안내 보존·원문 노출 없음', async w => {
    w.reply(async () => response('PRIVATE', status));
    await w.read('A');
    assert.equal(w.state().releaseLoad, status === 500 ? 'failed' : 'forbidden');
    assert.equal(w.state().viewingRelease, null);
    assert.doesNotMatch(w.state().releaseError, /PRIVATE/);
    if (status !== 500) assert.equal(w.state().releaseError, '현재 회사·권한에서 결과물을 찾을 수 없습니다.');
  });
}
await test('다른 ID·누락 ID·잘못된 응답 형태는 표시하지 않는다', async w => {
  for (const data of [payload('B'), {}, [], 'PRIVATE', null, { ...payload('A'), release_id: 7 }]) {
    w.reply(async () => new Response(JSON.stringify({ status: 'success', data })));
    await w.read('A');
    assert.equal(w.state().viewingRelease, null);
    assert.equal(w.state().releaseLoad, 'failed');
  }
});
await test('최신 통신/JSON 장애는 안내 후 재시도 가능', async w => {
  for (const reply of [
    async () => { throw new Error('PRIVATE'); },
    async () => ({ ok: true, json: async () => { throw new Error('PRIVATE'); } }),
  ]) {
    w.reply(reply); await w.read('A');
    assert.equal(w.state().releaseLoad, 'failed');
    assert.doesNotMatch(w.state().releaseError, /PRIVATE/);
  }
  w.reply(async () => response('A')); await w.read('A');
  assert.equal(w.state().viewingRelease.release_id, 'A');
});
await test('잘못된 ID는 통신 전 거절하고 이전 화면을 비운다', async w => {
  await w.read('A');
  for (const id of ['', '../A', 'a/b', 'A?x=1', '한글']) {
    await w.read(id);
    assert.equal(w.state().viewingRelease, null);
    assert.equal(w.state().releaseLoad, 'failed');
  }
  assert.equal(w.calls.length, 1);
});
await test('목록에서 받은 긴 서버 ID에 새 길이 제한을 만들지 않는다', async w => {
  const id = 'x'.repeat(161);
  w.reply(async () => response(id)); await w.read(id);
  assert.equal(w.state().viewingRelease.release_id, id);
});

function appAst() {
  const source = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  return ts.createSourceFile('App.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
}
function compileExpression(expression, dependencies) {
  const js = ts.transpileModule('export const value = ' + expression, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  } }).outputText;
  const mod = { exports: {} };
  new Function('module', 'exports', ...Object.keys(dependencies), js)(
    mod, mod.exports, ...Object.values(dependencies));
  return mod.exports.value;
}
await test('로그인 완료 콜백은 회사 확정 게이트를 거치고 직접 셸을 열지 않는다', () => {
  const ast = appAst(), callbacks = [];
  function walk(node) {
    if (ts.isJsxAttribute(node) && node.name.getText(ast) === 'onLoggedIn') callbacks.push(node.initializer.expression);
    ts.forEachChild(node, walk);
  }
  walk(ast); assert.equal(callbacks.length, 1);
  const actions = [];
  const callback = compileExpression(callbacks[0].getText(ast), {
    check: () => { actions.push('check'); },
    setState: value => { actions.push(value); },
  });
  callback(); assert.deepEqual(actions, ['check']);
});
for (const previousTenant of ['tenant-old', 'tenant-current']) {
  await test('실제 인증 게이트: ' + previousTenant + ' 보정 후에만 셸 진입', async () => {
    const ast = appAst(), callbacks = [];
    function walk(node) {
      if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'check'
          && ts.isCallExpression(node.initializer) && node.initializer.expression.getText(ast) === 'useCallback') {
        callbacks.push(node.initializer.arguments[0]);
      }
      ts.forEachChild(node, walk);
    }
    walk(ast); assert.equal(callbacks.length, 1);
    const gate = deferred(), actions = [];
    let context = { tenantId: previousTenant, scopeNodeId: 'chosen-scope', entityMode: 'REAL' };
    const check = compileExpression(callbacks[0].getText(ast), {
      getSessionToken: () => 'synthetic-token', API_BASE_URL: 'https://synthetic.invalid',
      getEnterpriseContext: () => context,
      setEnterpriseContext: patch => { context = { ...context, ...patch }; actions.push('context'); },
      setState: value => { actions.push(value); if (value === 'in') assert.equal(context.tenantId, 'tenant-current'); },
      setOffline: () => {}, setSessionToken: () => assert.fail('성공에서 토큰 삭제'),
      setActingUser: () => assert.fail('성공에서 사용자 삭제'),
      fetch: () => gate.promise,
    });
    const pending = check(); assert.deepEqual(actions, ['checking']);
    gate.resolve(new Response(JSON.stringify({ data: { tenant_id: 'tenant-current' } })));
    await pending;
    assert.deepEqual(actions, previousTenant === 'tenant-old' ? ['checking', 'context', 'in'] : ['checking', 'in']);
    assert.equal(context.scopeNodeId, previousTenant === 'tenant-old' ? '' : 'chosen-scope');
  });
}

// App의 실제 조건/JSX만 추출한다. 거대한 App의 다른 화면은 대역 실행하지 않는다.
await test('App 실제 상태 분기 SSR: 로딩 안내·취소 및 실패 안내', async w => {
  const text = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const ast = ts.createSourceFile('App.tsx', text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const branches = [];
  function walk(node) {
    if (ts.isIfStatement(node) && node.expression.getText(ast).includes('releaseLoad')) branches.push(node);
    ts.forEachChild(node, walk);
  }
  walk(ast); assert.equal(branches.length, 1);
  const js = ts.transpileModule('export function render({ viewingRelease, releaseLoad, releaseError, leaveRelease, setSpace, overlays, ErrorBoundary }) {'
    + branches[0].getText(ast) + ' return null; }', { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const mod = { exports: {} };
  new Function('module', 'exports', 'require', js)(mod, mod.exports, native);
  const props = { viewingRelease: null, releaseError: '합성 오류', leaveRelease: w.close,
    setSpace: () => {}, overlays: null, ErrorBoundary: ({ children }) => children };
  const loading = renderToStaticMarkup(mod.exports.render({ ...props, releaseLoad: 'loading' }));
  assert.match(loading, /role="status"/); assert.match(loading, /결과물을 불러오는 중/);
  assert.match(loading, /조회 취소/); assert.doesNotMatch(loading, /role="alert"/);
  const failed = renderToStaticMarkup(mod.exports.render({ ...props, releaseLoad: 'failed' }));
  assert.match(failed, /role="alert"/); assert.match(failed, /합성 오류/);
  const buttons = [];
  function visit(node) {
    if (!React.isValidElement(node)) return;
    if (node.type === 'button' && node.props.children === '조회 취소') buttons.push(node);
    React.Children.forEach(node.props.children, visit);
  }
  const gate = deferred(); w.reply(() => gate.promise);
  const pending = w.read('A');
  visit(mod.exports.render({ ...props, releaseLoad: 'loading' }));
  assert.equal(buttons.length, 1);
  buttons[0].props.onClick(); closed(w);
  gate.resolve(response('A')); await pending; closed(w);
});
// ── [SINGLE-ENTRY-01-FIX2 · 지시 3] 릴리스는 «조회» 와 «주소 의도» 를 함께 움직인다 ──
//   ⚠️ 종전에는 `viewRelease` 만 부르고 주소는 `viewingRelease` 가 차기를 기다렸다.
//     조회 중·실패 중에는 그 값이 비어 **목적지 주소를 잃었다**. 반대로 닫을 때
//     `closeRelease()` 만 부르면 화면은 닫혔는데 **주소에 릴리스가 남는다.**
await test('FIX2 릴리스 열기·닫기가 조회와 주소 의도를 함께 놓는다', () => {
  const text = fs.readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const ast = ts.createSourceFile('App.tsx', text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const found = {};
  (function walk(node) {
    if (ts.isVariableDeclaration(node) && node.initializer && ts.isCallExpression(node.initializer)
        && ['openRelease', 'leaveRelease'].includes(node.name.getText(ast))) {
      found[node.name.getText(ast)] = node.initializer.arguments[0].getText(ast);
    }
    ts.forEachChild(node, walk);
  })(ast);
  for (const name of ['openRelease', 'leaveRelease']) assert.ok(found[name], name + ' 을 찾지 못했다');
  const call = (source, names, ...args) => {
    const seen = {};
    const js = ts.transpileModule('export const value = (' + names.join(', ') + ') => (' + source + ')',
      { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
    const mod = { exports: {} };
    new Function('module', 'exports', js)(mod, mod.exports);
    mod.exports.value(...names.map((n) => (v) => { seen[n] = v === undefined ? '(호출)' : v; }))(...args);
    return seen;
  };
  const opened = call(found.openRelease, ['setPendingRelease', 'viewRelease'], 'rel_9');
  assert.equal(opened.setPendingRelease, 'rel_9', '조회를 걸면서 주소 의도를 세우지 않았다');
  assert.equal(opened.viewRelease, 'rel_9', '주소만 세우고 조회를 걸지 않았다');
  const left = call(found.leaveRelease, ['setPendingRelease', 'closeRelease']);
  assert.equal(left.setPendingRelease, null, '닫았는데 주소에 릴리스가 남는다');
  assert.equal(left.closeRelease, '(호출)', '주소만 놓고 조회를 닫지 않았다 — 원문이 남는다');
});

// ── [B6-CONTEXT-SSE-01 · 결정 3] «뒤늦은 옛 연결» 이벤트를 무시한다 ──────────
//   ⚠️ 이것은 **네트워크 차단과 다른 사실**이다. 서버가 안 보내는 것(범위 필터)과, 이미
//     닫힌 옛 연결이 늦게 뱉은 것을 화면이 안 먹는 것은 서로를 대체하지 않는다.
//     지시가 「별도 지연 이벤트 실행 시험으로 증명한다」고 못박은 자리다.
//   ★ 실제 store 를 돌린다. `EventSource` 만 대역으로 바꿔 «옛 연결» 을 손에 쥔다.
await test('SSE: 문맥이 바뀐 뒤 «옛 연결» 이 늦게 뱉은 이벤트는 먹지 않는다', async w => {
  const made = [];
  const previous = globalThis.EventSource;
  //: 대역 EventSource — 실제 store 가 만드는 연결을 그대로 붙잡는다.
  globalThis.EventSource = class {
    constructor(url) { this.url = url; this.readyState = 1; made.push(this); }
    close() { this.readyState = 2; }
  };
  try {
    w.reply(async (url) => {
      if (String(url).includes('/auth/sse-ticket')) {
        return new Response(JSON.stringify({ status: 'success', data: { ticket: 'T' + made.length } }),
          { status: 200 });
      }
      return new Response(JSON.stringify({ status: 'success', data: {} }), { status: 200 });
    });

    //: ① A 문맥으로 연결한다.
    await w.state().connectSSE();
    assert.equal(made.length, 1, '첫 연결을 만들지 않았다');
    const oldConn = made[0];

    //: ② 문맥이 바뀌어 **다시 연결**한다(제품이 전환 때 하는 그 일).
    w.identity({ scopeNodeId: 'scope-b' });
    await w.state().connectSSE();
    assert.equal(made.length, 2, '두 번째 연결을 만들지 않았다');
    const newConn = made[1];
    assert.notEqual(oldConn, newConn);

    const logsBefore = w.state().logs.length;

    //: ③★★★ **옛 연결**이 뒤늦게 이벤트를 뱉는다 — 네트워크는 이미 지나간 뒤다.
    const stale = { type: 'B6_SCOPE_PROBE', timestamp: '2026-09-19T00:00:00',
                    payload: { project_id: 'prj_stale', marker: 'STALE-1' } };
    oldConn.onmessage({ data: JSON.stringify(stale) });
    assert.equal(w.state().logs.length, logsBefore,
      '옛 연결이 늦게 뱉은 이벤트를 화면 로그에 먹었다');
    assert.equal(w.state().logs.some(x => x?.marker === 'STALE-1'), false);

    //: ④ 양성 대조 — **지금 연결**이 뱉으면 먹어야 한다. 안 그러면 「아무것도 안 먹는」
    //:   시험이 되어 ③이 공허해진다.
    const fresh = { type: 'B6_SCOPE_PROBE', timestamp: '2026-09-19T00:00:01',
                    payload: { project_id: 'prj_fresh', marker: 'FRESH-1' } };
    newConn.onmessage({ data: JSON.stringify(fresh) });
    assert.equal(w.state().logs.length, logsBefore + 1, '지금 연결의 이벤트를 먹지 않았다');
    assert.equal(w.state().logs.at(-1).marker, 'FRESH-1');
  } finally {
    globalThis.EventSource = previous;
  }
});

await test('검사 중 제품·검사 소스 불변', () => assert.deepEqual(hashes(), before));
const report = { passed: results.filter(x => x.result === 'PASS').length,
  failed: results.filter(x => x.result === 'FAIL').length,
  browser: 'NOT_RUN', network: 'MOCK_ONLY', store: 'ACTUAL_ZUSTAND', source_hashes: before, results };
const output = new URL('../../output/release-entry-' + randomUUID() + '/', import.meta.url);
fs.mkdirSync(output, { recursive: true });
fs.writeFileSync(new URL('report.json', output), JSON.stringify(report, null, 2));
for (const result of results) if (result.result === 'FAIL') process.stderr.write(result.name + ': ' + result.error + '\n');
process.stdout.write(JSON.stringify({ ...report, results: undefined, report: new URL('report.json', output).pathname }) + '\n');
if (report.failed) process.exitCode = 1;
