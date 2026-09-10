import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';
import { createKitAppPager, emptyKitAppPage, kitAppPageInfo } from '../src/lib/kitAppPaging.ts';

const datasets = ['log_03', 'prc_02'].map(name => ({ name, label: name, dataset_id: name, record_count: 0 }));
const records = (count, total = count, start = 0) => ({
  records: Array.from({ length: count }, (_, i) => ({ row: start + i })), total,
  as_of: '2026-08-24', stale: false,
});
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function setup(overrides = {}) {
  let state = emptyKitAppPage(), issued = 0;
  const calls = [];
  const pager = createKitAppPager({
    listDatasets: async () => datasets,
    issueProof: async () => 'memory-proof-' + (++issued),
    chooseDataset: () => 'log_03',
    readRecords: async (proof, name, limit, offset) => {
      calls.push({ proof, name, limit, offset });
      return records(Math.min(limit, 36 - offset), 36, offset);
    },
    ...overrides,
    onChange: next => { state = next; },
  });
  return { pager, calls, get state() { return state; }, get issued() { return issued; } };
}

test('36행은 1–20 → 21–36 → 1–20으로 이동하고 경계 밖 요청을 하지 않는다', async () => {
  const s = setup();
  await s.pager.load();
  assert.deepEqual(kitAppPageInfo(s.state), { start: 1, end: 20, total: 36, page: 1, pages: 2, hasPrevious: false, hasNext: true });
  await s.pager.move(-1);
  assert.equal(s.calls.length, 1);
  await s.pager.move(1);
  assert.deepEqual(kitAppPageInfo(s.state), { start: 21, end: 36, total: 36, page: 2, pages: 2, hasPrevious: true, hasNext: false });
  assert.equal(s.state.rows.records[0].row, 20);
  await s.pager.move(1);
  assert.equal(s.calls.length, 2);
  await s.pager.move(-1);
  assert.deepEqual(s.calls.map(c => c.offset), [0, 20, 0]);
  assert.ok(s.calls.every(c => c.limit === 20));
});

test('다른 자료로 바꾸면 첫 페이지로 돌아간다', async () => {
  const s = setup();
  await s.pager.load(); await s.pager.move(1);
  await s.pager.select('prc_02', 20);
  assert.equal(s.state.offset, 0);
  assert.equal(s.state.picked, 'prc_02');
  assert.deepEqual(s.calls.at(-1), { proof: 'memory-proof-1', name: 'prc_02', limit: 20, offset: 0 });
});

test('0행과 정확히 20행에는 다음 페이지가 없다', async () => {
  for (const total of [0, 20]) {
    const s = setup({ readRecords: async () => records(total) });
    await s.pager.load();
    assert.equal(kitAppPageInfo(s.state).hasNext, false);
    assert.equal(kitAppPageInfo(s.state).hasPrevious, false);
    assert.equal(kitAppPageInfo(s.state).start, total ? 1 : 0);
  }
});

test('늦게 도착한 다른 자료의 응답이 선택한 자료를 덮지 않는다', async () => {
  const late = deferred(); let phase = 'initial';
  const s = setup({ readRecords: async (_, name) => phase === 'initial' ? records(20, 36)
    : name === 'log_03' ? late.promise : records(6) });
  await s.pager.load(); phase = 'switch';
  const pending = s.pager.move(1);
  assert.equal(s.state.rows, null);
  await s.pager.select('prc_02');
  late.resolve(records(16, 36, 20)); await pending;
  assert.equal(s.state.picked, 'prc_02');
  assert.equal(s.state.rows.total, 6);
  assert.equal(s.state.offset, 0);
});

test('이전 요청 실패도 새 자료의 정상 응답을 지우지 않는다', async () => {
  const late = deferred(); let count = 0;
  const s = setup({ readRecords: async () => ++count === 2 ? late.promise : records(20, 36) });
  await s.pager.load(); const pending = s.pager.move(1);
  await s.pager.select('prc_02'); late.reject(new Error('old request')); await pending;
  assert.equal(s.state.error, ''); assert.ok(s.state.rows);
});

test('문맥 재조회는 기존 행을 즉시 지우고 새 증명으로 첫 페이지를 읽는다', async () => {
  const s = setup(); await s.pager.load(); await s.pager.move(1);
  const pending = s.pager.load();
  assert.equal(s.state.rows, null); assert.equal(s.state.offset, 0);
  await pending;
  assert.equal(s.issued, 2);
  assert.equal(s.calls.at(-1).proof, 'memory-proof-2');
  assert.equal(s.calls.at(-1).offset, 0);
});

test('문맥 변경 뒤 이전 증명이 늦게 발급돼도 사용하지 않는다', async () => {
  const oldProof = deferred(); let count = 0; const reads = [];
  const s = setup({ issueProof: async () => ++count === 1 ? oldProof.promise : 'new-proof',
    readRecords: async proof => { reads.push(proof); return records(6); } });
  const oldLoad = s.pager.load(); await Promise.resolve();
  await s.pager.load(); oldProof.resolve('old-proof'); await oldLoad;
  assert.deepEqual(reads, ['new-proof']); assert.equal(s.state.rows.total, 6);
});

test('조회 중 중복 다음 이동은 추가 요청을 만들지 않는다', async () => {
  const late = deferred(); let count = 0;
  const s = setup({ readRecords: async () => ++count === 1 ? records(20, 36) : late.promise });
  await s.pager.load(); const pending = s.pager.move(1);
  await s.pager.move(1); assert.equal(count, 2);
  assert.equal(kitAppPageInfo(s.state).hasNext, false);
  late.resolve(records(16, 36)); await pending;
});

test('조회 실패는 0건이 아니라 오류이며 같은 페이지를 재시도할 수 있다', async () => {
  let count = 0;
  const s = setup({ readRecords: async () => {
    count++; if (count === 2) throw new Error('offline');
    return count === 1 ? records(20, 36) : records(16, 36, 20);
  } });
  await s.pager.load(); await s.pager.move(1);
  assert.equal(s.state.rows, null); assert.equal(s.state.error, 'offline');
  await s.pager.retry(); assert.equal(s.state.offset, 20);
  assert.equal(s.state.rows.records[0].row, 20); assert.equal(s.state.error, '');
});

test('닫기·언마운트 이후 응답은 화면을 갱신하지 않는다', async () => {
  for (const method of ['reset', 'invalidate']) {
    const late = deferred(); let count = 0;
    const s = setup({ readRecords: async () => ++count === 1 ? records(20, 36) : late.promise });
    await s.pager.load(); const pending = s.pager.move(1);
    s.pager[method](); const before = s.state;
    late.resolve(records(16, 36)); await pending;
    assert.equal(s.state, before);
  }
});

test('빈 연결 목록은 증명·자료 조회를 부르지 않는다', async () => {
  const s = setup({ listDatasets: async () => [] });
  await s.pager.load(); assert.equal(s.issued, 0); assert.equal(s.calls.length, 0);
  assert.equal(s.state.busy, false); assert.deepEqual(s.state.datasets, []);
});

test('자료가 줄어 마지막 페이지가 없어지면 유효한 마지막 페이지를 재조회한다', async () => {
  const offsets = [];
  const s = setup({ readRecords: async (_, __, ___, offset) => {
    offsets.push(offset);
    return offsets.length === 1 ? records(20, 36) : offset === 20 ? records(0, 6) : records(6);
  } });
  await s.pager.load(); await s.pager.move(1);
  assert.deepEqual(offsets, [0, 20, 0]);
  assert.equal(s.state.offset, 0); assert.equal(s.state.rows.total, 6);
});

// 실제 API 함수를 실행하되 HTTP 경계만 대체한다. 로그인·실제 DB 조회는 하지 않는다.
async function loadApi(fetcher) {
  const source = await readFile(new URL('../src/lib/kitAppViewApi.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
  const context = vm.createContext({});
  const api = new vm.SourceTextModule(compiled, { context });
  await api.link(specifier => new vm.SyntheticModule(
    specifier === './api' ? ['apiFetch'] : ['unwrap'], function () {
      this.setExport(specifier === './api' ? 'apiFetch' : 'unwrap', fetcher);
    }, { context }));
  await api.evaluate(); return api.namespace;
}

test('실제 API 요청에 offset·limit과 앱 증명 헤더를 전달한다', async () => {
  const requests = [];
  const api = await loadApi(async (url, init) => {
    requests.push({ url, init });
    return { ok: true, json: async () => ({ status: 'ok', data: records(16, 36, 20) }) };
  });
  const result = await api.readAppRecords('test-only-proof', 'log/03', 20, 20);
  const request = requests[0], url = new URL(request.url, 'http://test.invalid');
  assert.equal(url.pathname, '/api/v1/appdata/runtime/datasets/log%2F03/records');
  assert.equal(url.searchParams.get('offset'), '20');
  assert.equal(url.searchParams.get('limit'), '20');
  assert.equal(request.init.headers['X-App-Proof'], 'test-only-proof');
  assert.equal(request.url.includes('test-only-proof'), false);
  assert.equal(result.total, 36); assert.equal(result.records[0].row, 20);
});

test('기존 API 호출은 첫 20건이며 평면 응답도 읽는다', async () => {
  let url;
  const api = await loadApi(async path => { url = path; return { ok: true, json: async () => records(6) }; });
  const result = await api.readAppRecords('test-only-proof', 'prc_02');
  assert.match(url, /limit=20&offset=0$/); assert.equal(result.total, 6);
});

test('실제 API 실패는 빈 행으로 바뀌지 않는다', async () => {
  const api = await loadApi(async () => ({ ok: false, status: 503 }));
  await assert.rejects(api.readAppRecords('test-only-proof', 'log_03'), /503/);
});
