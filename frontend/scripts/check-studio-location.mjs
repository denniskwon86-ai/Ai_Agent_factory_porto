// B6-C0 순수 문법 검사. 제품 라우팅·브라우저·서버 권한 검증이 아니다.
// 기존 TS transpile/assert 패턴만 사용하며 보고서/DB/소스 파일을 쓰지 않는다.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createHash } from 'node:crypto';
import ts from 'typescript';

const sourceUrl = new URL('../src/factory/studioLocation.ts', import.meta.url);
const scriptUrl = new URL('./check-studio-location.mjs', import.meta.url);
const hash = url => createHash('sha256').update(fs.readFileSync(url)).digest('hex');
const before = [hash(sourceUrl), hash(scriptUrl)];
const source = fs.readFileSync(sourceUrl, 'utf8');
const js = ts.transpileModule(source, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
} }).outputText;
let sideEffects = 0;
const forbidden = () => { sideEffects++; throw new Error('순수 모듈 외부 접근 금지'); };
const mod = { exports: {} };
// 같은 realm에서 객체를 검사하되 외부 효과/모듈 로더를 인자로 막는다.
new Function('module', 'exports', 'require', 'fetch', 'window', 'document', 'localStorage', js)(
  mod, mod.exports, forbidden, forbidden, undefined, undefined, undefined);
const { parseStudioLocation: parse, serializeStudioLocation: serialize, StudioLocationError } = mod.exports;
const results = [];
function test(name, run) {
  try { run(); results.push({ name, result: 'PASS' }); }
  catch (error) { results.push({ name, result: 'FAIL', error: String(error.stack || error) }); }
}
function bad(query, reason) {
  const result = parse(query); assert.equal(result.kind, 'INVALID_TARGET', query);
  if (reason) assert.equal(result.reason, reason, query);
}
function throws(value) { assert.throws(() => serialize(value), StudioLocationError); }
function deepFreeze(value) {
  if (value && typeof value === 'object') { Object.values(value).forEach(deepFreeze); Object.freeze(value); }
  return value;
}
const targets = [
  { kind: 'new' },
  { kind: 'draft', draftKind: 'consultation', draftId: 'consult_1', revision: 1 },
  { kind: 'draft', draftKind: 'blueprint', draftId: 'blueprint_1', revision: 7 },
  { kind: 'project', projectId: 'project_1' },
  { kind: 'kit_app', instanceId: 'instance_1', appId: 'app_1' },
  { kind: 'kit_app', instanceId: 'instance_1', appId: 'app_1', releaseId: 'release_1' },
  { kind: 'release', releaseId: 'release_1' },
  { kind: 'mega', megaProjectId: 'mega_1' },
  { kind: 'mega', megaProjectId: 'mega_1', childProjectId: 'child_1' },
];
for (const target of targets) test('UNIT 대상 왕복 ' + JSON.stringify(target), () => {
  const location = deepFreeze({ target, selection: { configurationId: 'config_1', processId: '업무_입고' } });
  const encoded = serialize(location);
  assert.equal(parse(encoded).kind, 'MATCH');
  assert.deepEqual(parse(encoded).location, location);
  assert.equal(serialize(parse(encoded).location), encoded);
});
test('UNIT 대상 없는 build는 LIST, 기타 공간은 NOT_STUDIO이며 신규 생성 없음', () => {
  assert.deepEqual(parse('?space=build'), { kind: 'LIST' });
  assert.deepEqual(parse('?space=build&configuration=c&process=p'), {
    kind: 'LIST', selection: { configurationId: 'c', processId: 'p' } });
  for (const query of ['', '?space=enterprise', '?space=advisor&draft=d&revision=2&tenant_id=t',
    '?space=operate&release=R', '?release=r']) {
    assert.deepEqual(parse(query), { kind: 'NOT_STUDIO' });
  }
});
test('UNIT legacy project만 명시 정규화하고 명시 대상의 다른 space는 거절', () => {
  for (const query of ['?project=p', '?space=report&project=p']) {
    assert.deepEqual(parse(query), { kind: 'MATCH', location: { target: { kind: 'project', projectId: 'p' } } });
  }
  assert.equal(serialize(parse('?project=p').location), '?space=build&target=project&project=p');
  bad('?space=report&target=project&project=p', 'SPACE_MISMATCH');
  bad('?space=build&project=p&release=r', 'CONFLICTING_IDS');
});
test('UNIT 대상별 필수 ID 누락·상충 ID·다른 draft 종류를 거절', () => {
  for (const query of [
    'target=new&project=p', 'target=project', 'target=project&project=p&release=r',
    'target=kit_app&instance=i', 'target=kit_app&instance=i&app=a&project=p',
    'target=release&release=r&app=a', 'target=mega&mega=m&project=p',
    'target=draft&draft_kind=project&draft=d&revision=1',
    'target=draft&draft_kind=blueprint&draft=d', 'target=unknown', 'release=r',
  ]) bad('?space=build&' + query);
});
test('UNIT 같은 값 중복·인코딩 중복·빈 값도 모호하므로 거절', () => {
  for (const query of ['space=build&space=build', 'space=build&target=new&target=new',
    'space=build&project=p&%70roject=p', 'space=build&project=', 'space=build&target=',
    'space=build&target=new&configuration=c&configuration=c',
    'space=build&target=new&return_to=x&return_to=x']) bad(query);
});
test('UNIT 초안 revision은 양의 정규 안전 정수만 허용', () => {
  for (const value of ['0', '-1', '01', '+1', '1.0', '1e3', 'Infinity', 'NaN', '9007199254740992', '9'.repeat(310)]) {
    bad('?space=build&target=draft&draft_kind=blueprint&draft=d&revision=' + encodeURIComponent(value));
  }
  const location = { target: { kind: 'draft', draftKind: 'blueprint', draftId: 'd', revision: Number.MAX_SAFE_INTEGER } };
  assert.deepEqual(parse(serialize(location)).location, location);
  for (const value of [0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, '1']) {
    throws({ target: { ...location.target, revision: value } });
  }
});
test('UNIT 내부 목록·업무·6종 대상 복귀는 중첩 없이 왕복', () => {
  const returns = [
    ...['build', 'advisor', 'operate', 'report', 'mega'].map(list => ({ kind: 'list', list })),
    { kind: 'process', selection: { configurationId: 'c', processId: 'p' } },
    ...targets.map(target => ({ kind: 'target', target, selection: { configurationId: 'c' } })),
  ];
  for (const returnTo of returns) {
    const location = deepFreeze({ target: { kind: 'new' }, returnTo });
    assert.deepEqual(parse(serialize(location)).location, location);
  }
});
test('UNIT return 외부 URL·프로토콜 상대 URL·중첩·오염 키 거절', () => {
  for (const returnTo of ['https://evil.invalid', '//evil.invalid', '/other',
    { kind: 'url', url: 'https://evil.invalid' }, { kind: 'list', list: 'https://evil.invalid' },
    { kind: 'target', target: { kind: 'new' }, returnTo: { kind: 'list', list: 'build' } },
    { kind: 'process', selection: {} }, JSON.parse('{"kind":"list","list":"build","__proto__":{}}')]) {
    throws({ target: { kind: 'new' }, returnTo });
    bad('?space=build&target=new&return_to=' + encodeURIComponent(JSON.stringify(returnTo)));
  }
});
test('UNIT 내부 목록은 배열·문자열 변환 객체를 허용하지 않는다', () => {
  let invoked = false;
  for (const list of [['build'], { toString() { invoked = true; return 'build'; } }]) {
    throws({ target: { kind: 'new' }, returnTo: { kind: 'list', list } });
  }
  assert.equal(invoked, false);
  bad('?space=build&target=new&return_to=' + encodeURIComponent(JSON.stringify({ kind: 'list', list: ['build'] })));
});
test('UNIT 선택 힌트에 process만 주거나 권한 필드를 섞으면 거절', () => {
  bad('?space=build&target=new&process=p');
  throws({ target: { kind: 'new' }, selection: { configurationId: 'c', authorized: true } });
  throws({ target: { kind: 'new' }, selection: { configurationId: 'c', processId: undefined } });
  const location = { target: { kind: 'project', projectId: 'missing_resource' }, selection: { configurationId: 'unverified' } };
  assert.deepEqual(parse(serialize(location)).location, location);
  assert.equal('authorized' in parse(serialize(location)), false);
});
test('UNIT 무관한 query는 무시하되 Studio의 권한·문맥·별칭은 거절', () => {
  assert.deepEqual(parse('?space=build&target=new&tab=recent&tab=all&utm_source=demo&filter=x'), {
    kind: 'MATCH', location: { target: { kind: 'new' } } });
  for (const key of ['tenant_id', 'companyId', 'context_root_id', 'entityMode', 'scope_node_id',
    'actor_id', 'userId', 'access_token', 'authorization', 'role', 'permissions', 'process_context',
    'project_id', 'return_url', 'redirect', 'Target']) bad('?space=build&target=new&' + key + '=x');
});
test('UNIT ID를 경로·URL로 바꾸거나 잘못된 escape로 치환하지 않는다', () => {
  for (const value of ['', '.', '..', '../p', 'a/b', 'a\\b', 'https://evil.invalid', 'javascript:alert(1)',
    'a b', 'a\nb', 'p%2Fq', 'x'.repeat(201)]) {
    bad('?space=build&target=project&project=' + encodeURIComponent(value));
  }
  for (const query of ['https://host/?space=build', '//host/?space=build',
    '?space=build#x', '?space=build&project=%GG', '?space=build&project=%C0%AF']) bad(query);
  throws({ target: { kind: 'project', projectId: '\ud800' } });
  const location = { target: { kind: 'project', projectId: '한글&=+😀' } };
  assert.deepEqual(parse(serialize(location)).location, location);
});
test('UNIT 원형 객체·getter·prototype·숨긴 추가 필드를 거절하고 실행하지 않는다', () => {
  const cyclic = { target: { kind: 'new' } }; cyclic.returnTo = cyclic;
  throws(cyclic);
  const targetCycle = { kind: 'target' }; targetCycle.target = targetCycle;
  throws({ target: { kind: 'new' }, returnTo: targetCycle });
  let reads = 0;
  const getter = { get target() { reads++; return { kind: 'new' }; } };
  throws(getter); assert.equal(reads, 0);
  throws(Object.create({ target: { kind: 'new' } }));
  throws({ target: Object.assign(Object.create({ authorized: true }), { kind: 'new' }) });
  throws({ target: { kind: 'new' }, [Symbol('hidden')]: true });
  throws(Object.defineProperty({ target: { kind: 'new' } }, 'authorized', { value: true }));
});
test('UNIT 입력 객체·query를 변경하지 않고 직렬화 순서는 결정적', () => {
  const first = { target: { kind: 'kit_app', instanceId: 'i', appId: 'a', releaseId: 'r' },
    returnTo: { kind: 'list', list: 'build' }, selection: { configurationId: 'c', processId: 'p' } };
  const second = { selection: { processId: 'p', configurationId: 'c' }, returnTo: { list: 'build', kind: 'list' },
    target: { releaseId: 'r', appId: 'a', instanceId: 'i', kind: 'kit_app' } };
  const original = structuredClone(first); deepFreeze(first);
  assert.equal(serialize(first), serialize(second)); assert.deepEqual(first, original);
});
test('UNIT 큰 query·return JSON과 잘못된 JSON은 닫힌 오류 반환', () => {
  bad('?space=build&x=' + 'x'.repeat(16384));
  bad('?space=build&return_to=' + encodeURIComponent('"'.repeat(4097)));
  bad('?space=build&return_to=%7B');
  assert.equal(parse(null).kind, 'INVALID_TARGET');
});
test('STATIC 제품 외부 의존·동적 평가·쓰기 호출 없음 (라우팅 동작 검증 아님)', () => {
  const tree = ts.createSourceFile('studioLocation.ts', source, ts.ScriptTarget.ES2022, true);
  function visit(node) {
    assert.notEqual(node.kind, ts.SyntaxKind.ImportDeclaration);
    assert.notEqual(node.kind, ts.SyntaxKind.ExportDeclaration);
    if (ts.isCallExpression(node)) {
      const name = node.expression.getText(tree);
      assert.ok(!/^(fetch|require|eval|setTimeout|setInterval)$/.test(name), name);
      assert.ok(!/^(window|document|localStorage|sessionStorage|history)\./.test(name), name);
    }
    ts.forEachChild(node, visit);
  }
  visit(tree);
  // 코드가 브라우저 global 없이도 평가되는지만 확인한다. DOM/effect 검사는 아니다.
  vm.runInNewContext(js, { exports: {}, URLSearchParams });
  assert.equal(sideEffects, 0);
});
test('소스·검사 파일 전후 해시 동일', () => assert.deepEqual([hash(sourceUrl), hash(scriptUrl)], before));
const failed = results.filter(row => row.result === 'FAIL');
console.log(JSON.stringify({ scope: 'B6-C0 UNIT/STATIC ONLY; 브라우저·서버·전역진입 NOT_RUN',
  passed: results.length - failed.length, failed: failed.length, source_sha256: before[0], results }, null, 2));
if (failed.length) process.exitCode = 1;
