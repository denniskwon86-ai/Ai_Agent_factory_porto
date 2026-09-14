/**
 * B6-C0: 진입 위치의 문법만 판정한다. 인증·귀속·존재·실행 허용을 증명하지 않는다.
 * React/store/API/window 의존, GET/POST, history 변경, 프로젝트·초안 생성은 없다.
 *
 * 정규 query:
 * space=build&target=new
 * target=draft&draft_kind=consultation|blueprint&draft=<ID>&revision=<양의 안전 정수>
 * target=project&project=<ID>
 * target=kit_app&instance=<ID>&app=<ID>[&release=<ID>]
 * target=release&release=<ID>
 * target=mega&mega=<ID>[&child=<ID>]
 * 공통 선택 힌트: configuration=<ID>[&process=<ID>].
 * return_to는 URLSearchParams로 한 번 인코딩한 InternalReturnTarget JSON이다.
 * 내부 목록/대상만 허용하고 중첩 return, 임의 URL, 회사/권한 정보는 허용하지 않는다.
 *
 * target 없는 build는 LIST이며 new를 만들지 않는다. 구 project 단독 링크만 정규화한다.
 * 무관한 query(tab, 필터, utm 등)는 무시하며 반환값/직렬화 결과에 복사하지 않는다.
 * 이 모듈이 전체 App URL의 화이트리스트는 아니다. 다른 공간은 NOT_STUDIO로 넘긴다.
 * 호출자는 필요하면 자신이 소유한 무관한 query만 별도로 보존한다. 권한·문맥 키와
 * 미지원 대상 별칭은 Studio URL에서 거절한다. 모르는 키로 행동/권한을 추론하지 않는다.
 */

export type StudioTarget =
  | { kind: 'new' }
  | { kind: 'draft'; draftKind: 'consultation' | 'blueprint'; draftId: string; revision: number }
  | { kind: 'project'; projectId: string }
  | { kind: 'kit_app'; instanceId: string; appId: string; releaseId?: string }
  | { kind: 'release'; releaseId: string }
  | { kind: 'mega'; megaProjectId: string; childProjectId?: string };

export type ProcessSelection = { configurationId: string; processId?: string };
export type InternalReturnTarget =
  | { kind: 'list'; list: 'build' | 'advisor' | 'operate' | 'report' | 'mega' }
  | { kind: 'process'; selection: ProcessSelection }
  | { kind: 'target'; target: StudioTarget; selection?: ProcessSelection };
export type StudioLocation = {
  target: StudioTarget; selection?: ProcessSelection; returnTo?: InternalReturnTarget;
};
export type StudioLocationResult =
  | { kind: 'MATCH'; location: StudioLocation }
  | { kind: 'LIST'; selection?: ProcessSelection; returnTo?: InternalReturnTarget }
  | { kind: 'NOT_STUDIO' }
  | { kind: 'INVALID_TARGET'; reason: string };

export class StudioLocationError extends Error {
  readonly code = 'INVALID_TARGET';
  readonly reason: string;
  constructor(reason: string) { super(reason); this.reason = reason; this.name = 'StudioLocationError'; }
}
const invalid = (reason: string): never => { throw new StudioLocationError(reason); };
const MAX_QUERY = 16384;
const MAX_RETURN = 4096;
const ownedKeys = ['space', 'target', 'draft_kind', 'draft', 'revision', 'project', 'instance', 'app',
  'release', 'mega', 'child', 'configuration', 'process', 'return_to'];
const targetKeys = ['draft_kind', 'draft', 'revision', 'project', 'instance', 'app', 'release', 'mega', 'child'];
// 다른 화면의 모든 query를 막지 않는다. 이 목록은 Studio가 받아들이지 않는 의미를 명시한다.
const forbiddenKeys = new Set(['tenantid', 'companyid', 'contextrootid', 'entitymode', 'scopenodeid',
  'actorid', 'userid', 'token', 'accesstoken', 'authorization', 'permissions', 'role', 'roles',
  'authorized', 'context', 'processcontext', 'studiocontext',
  'projectid', 'draftid', 'instanceid', 'appid', 'releaseid', 'megaprojectid', 'childprojectid',
  'configurationid', 'processid', 'return', 'returnurl', 'redirect', 'redirecturi']);
const normalizedKey = (key: string) => key.replace(/[_-]/g, '').toLowerCase();

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return invalid('OBJECT_REQUIRED');
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).some(key => typeof key !== 'string')
      || Object.values(descriptors).some(field => !('value' in field))) return invalid('PLAIN_DATA_REQUIRED');
  return value as Record<string, unknown>;
}
function keys(row: Record<string, unknown>, required: string[], optional: string[] = []) {
  if (Object.getOwnPropertyNames(row).some(key => !required.includes(key) && !optional.includes(key))
      || required.some(key => !Object.hasOwn(row, key))) invalid('FIELDS_MISMATCH');
}
function id(value: unknown): string {
  // ID는 불투명 위치 토큰이다. 접두사로 자산 종류/회사 소속을 추측하지 않는다.
  // 유니코드·최대 200 UTF-16 단위는 URL 문법 제한일 뿐이다. 실제 ID 형식은 서버가 재검증한다.
  if (typeof value !== 'string' || !value || value.length > 200 || value === '.' || value === '..'
      || /[\s/\\:?#%]/u.test(value)
      || Array.from(value).some(char => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127)
      || /[\ud800-\udfff]/u.test(value)) return invalid('ID_INVALID');
  return value;
}
function revision(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 1) return invalid('REVISION_INVALID');
  return value;
}
function selection(value: unknown): ProcessSelection {
  const row = object(value); keys(row, ['configurationId'], ['processId']);
  return { configurationId: id(row.configurationId),
    ...(Object.hasOwn(row, 'processId') ? { processId: id(row.processId) } : {}) };
}
function target(value: unknown): StudioTarget {
  const row = object(value);
  switch (row.kind) {
    case 'new': keys(row, ['kind']); return { kind: 'new' };
    case 'draft':
      keys(row, ['kind', 'draftKind', 'draftId', 'revision']);
      if (row.draftKind !== 'consultation' && row.draftKind !== 'blueprint') return invalid('DRAFT_KIND_INVALID');
      return { kind: 'draft', draftKind: row.draftKind, draftId: id(row.draftId), revision: revision(row.revision) };
    case 'project':
      keys(row, ['kind', 'projectId']); return { kind: 'project', projectId: id(row.projectId) };
    case 'kit_app':
      keys(row, ['kind', 'instanceId', 'appId'], ['releaseId']);
      return { kind: 'kit_app', instanceId: id(row.instanceId), appId: id(row.appId),
        ...(Object.hasOwn(row, 'releaseId') ? { releaseId: id(row.releaseId) } : {}) };
    case 'release':
      keys(row, ['kind', 'releaseId']); return { kind: 'release', releaseId: id(row.releaseId) };
    case 'mega':
      keys(row, ['kind', 'megaProjectId'], ['childProjectId']);
      return { kind: 'mega', megaProjectId: id(row.megaProjectId),
        ...(Object.hasOwn(row, 'childProjectId') ? { childProjectId: id(row.childProjectId) } : {}) };
    default: return invalid('TARGET_KIND_INVALID');
  }
}
function returnTarget(value: unknown): InternalReturnTarget {
  const row = object(value);
  if (row.kind === 'list') {
    keys(row, ['kind', 'list']);
    if (typeof row.list !== 'string' || !['build', 'advisor', 'operate', 'report', 'mega'].includes(row.list)) return invalid('RETURN_LIST_INVALID');
    return { kind: 'list', list: row.list as 'build' | 'advisor' | 'operate' | 'report' | 'mega' };
  }
  if (row.kind === 'process') {
    keys(row, ['kind', 'selection']); return { kind: 'process', selection: selection(row.selection) };
  }
  keys(row, ['kind', 'target'], ['selection']);
  if (row.kind !== 'target') return invalid('RETURN_KIND_INVALID');
  return { kind: 'target', target: target(row.target),
    ...(Object.hasOwn(row, 'selection') ? { selection: selection(row.selection) } : {}) };
}
function location(value: unknown): StudioLocation {
  const row = object(value); keys(row, ['target'], ['selection', 'returnTo']);
  return { target: target(row.target),
    ...(Object.hasOwn(row, 'selection') ? { selection: selection(row.selection) } : {}),
    ...(Object.hasOwn(row, 'returnTo') ? { returnTo: returnTarget(row.returnTo) } : {}) };
}

/** query 문자열만 받는다. 전체 URL이나 hash 전달은 호출 계약 위반이다. */
export function parseStudioLocation(search: string): StudioLocationResult {
  try {
    if (typeof search !== 'string' || search.length > MAX_QUERY || search.includes('#')
        || /^[a-z][a-z0-9+.-]*:/i.test(search) || search.startsWith('//')) return invalid('QUERY_INVALID');
    const raw = search.startsWith('?') ? search.slice(1) : search;
    // URLSearchParams의 관대한 잘못된 %/UTF-8 치환으로 ID가 조용히 바뀌지 않게 한다.
    for (const pair of raw.split('&')) for (const part of pair.split('=')) decodeURIComponent(part.replace(/\+/g, ' '));
    const params = new URLSearchParams(raw);
    // 다른 공간의 release/draft/revision 등은 그 화면 소유다. 명시 target/legacy project만 경계를 넘는다.
    const relevant = params.get('space') === 'build' || params.has('target') || params.has('project');
    if (!relevant) return { kind: 'NOT_STUDIO' };
    for (const key of ownedKeys) if (params.getAll(key).length > 1) return invalid('DUPLICATE_FIELD');
    for (const key of params.keys()) {
      if (forbiddenKeys.has(normalizedKey(key))
          || (ownedKeys.some(owned => normalizedKey(owned) === normalizedKey(key)) && !ownedKeys.includes(key))) {
        return invalid('UNSUPPORTED_CONTEXT_OR_ALIAS');
      }
    }
    const get = (key: string) => params.get(key) ?? undefined;
    let kind = get('target');
    // legacy project는 기존 App과 같이 space를 build로 정규화하되 다른 대상 ID와 섞지 않는다.
    if (kind === undefined && params.has('project')) kind = 'project';
    else if (get('space') !== 'build') return invalid('SPACE_MISMATCH');
    const common = {
      ...(params.has('configuration') || params.has('process') ? { selection: selection({
        configurationId: get('configuration'), ...(params.has('process') ? { processId: get('process') } : {}),
      }) } : {}),
      ...(params.has('return_to') ? { returnTo: returnTarget(JSON.parse(
        (get('return_to')!.length <= MAX_RETURN ? get('return_to') : invalid('RETURN_TOO_LONG'))!,
      )) } : {}),
    };
    if (kind === undefined) {
      if (targetKeys.some(key => params.has(key))) return invalid('TARGET_REQUIRED');
      return { kind: 'LIST', ...common };
    }
    const fields: Record<string, string[]> = {
      new: [], draft: ['draft_kind', 'draft', 'revision'], project: ['project'],
      kit_app: ['instance', 'app', 'release'], release: ['release'], mega: ['mega', 'child'],
    };
    if (!Object.hasOwn(fields, kind)) return invalid('TARGET_KIND_INVALID');
    if (targetKeys.some(key => params.has(key) && !fields[kind!].includes(key))) return invalid('CONFLICTING_IDS');
    let draftRevision: number | undefined;
    if (kind === 'draft') {
      const rawRevision = get('revision');
      if (!rawRevision || !/^[1-9][0-9]*$/.test(rawRevision)) return invalid('REVISION_INVALID');
      draftRevision = revision(Number(rawRevision));
    }
    const candidate = kind === 'new' ? { kind }
      : kind === 'draft' ? { kind, draftKind: get('draft_kind'), draftId: get('draft'), revision: draftRevision }
      : kind === 'project' ? { kind, projectId: get('project') }
      : kind === 'kit_app' ? { kind, instanceId: get('instance'), appId: get('app'),
        ...(params.has('release') ? { releaseId: get('release') } : {}) }
      : kind === 'release' ? { kind, releaseId: get('release') }
      : { kind, megaProjectId: get('mega'), ...(params.has('child') ? { childProjectId: get('child') } : {}) };
    return { kind: 'MATCH', location: { target: target(candidate), ...common } };
  } catch (error) {
    return { kind: 'INVALID_TARGET', reason: error instanceof StudioLocationError ? error.reason : 'QUERY_INVALID' };
  }
}

/** 정규 query만 반환한다. history/입력을 바꾸지 않고 잘못된 객체는 예외로 거절한다. */
export function serializeStudioLocation(input: StudioLocation): string {
  const value = location(input), row = value.target;
  const params = new URLSearchParams({ space: 'build', target: row.kind });
  if (row.kind === 'draft') {
    params.set('draft_kind', row.draftKind); params.set('draft', row.draftId); params.set('revision', String(row.revision));
  } else if (row.kind === 'project') params.set('project', row.projectId);
  else if (row.kind === 'kit_app') {
    params.set('instance', row.instanceId); params.set('app', row.appId);
    if (row.releaseId !== undefined) params.set('release', row.releaseId);
  } else if (row.kind === 'release') params.set('release', row.releaseId);
  else if (row.kind === 'mega') {
    params.set('mega', row.megaProjectId);
    if (row.childProjectId !== undefined) params.set('child', row.childProjectId);
  }
  if (value.selection) {
    params.set('configuration', value.selection.configurationId);
    if (value.selection.processId !== undefined) params.set('process', value.selection.processId);
  }
  if (value.returnTo) {
    const encoded = JSON.stringify(value.returnTo);
    if (encoded.length > MAX_RETURN) return invalid('RETURN_TOO_LONG');
    params.set('return_to', encoded);
  }
  const output = '?' + params.toString();
  if (output.length > MAX_QUERY) return invalid('QUERY_TOO_LONG');
  return output;
}
