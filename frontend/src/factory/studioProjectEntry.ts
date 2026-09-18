// B6 단건 진입 확인. 조회 가능은 실행·게시·준비 완료를 뜻하지 않는다.
import { apiFetch, getEnterpriseContext } from '../lib/api';
import { studioIdentityKey } from './studioInputMemory';
import { createEntryFlow } from './studioEntryFlow';
import type { EntryState } from './studioEntryFlow';

export type ProjectEntryFacts = {
  project_id: string; project_name: string; runtime_document_version: '1.0' | '2.0';
  ownership: { tenant_id: string; enterprise_scope_id: string; entity_mode: string };
  viewing_context: { tenant_id: string; scope_node_id: string; entity_mode: string };
};
/** [MEGA-ENTRY-01] 소속 두 칸이 계약에 늘었다(설계안 §10.3).
 *
 *  ⚠️⚠️ `child` 는 **서버가 관계까지 확인해 준 자식**이다. 여기서 두 응답을 맞춰 보고
 *    관계를 «지어내지» 않는다 — 「부모를 볼 수 있다」와 「자식을 볼 수 있다」에서
 *    「자식이 이 부모의 것이다」는 나오지 않는다. 그건 서버만 아는 사실이다. */
export type ProjectEntry = ProjectEntryFacts & {
  is_mega_project: boolean; child: ProjectEntryFacts | null;
};
export class ProjectEntryError extends Error {
  readonly status: number; readonly reasonCode: string;
  constructor(message: string, status = 503, reasonCode = 'ENTRY_UNAVAILABLE') {
    super(message); this.name = 'ProjectEntryError'; this.status = status; this.reasonCode = reasonCode;
  }
}
const contextChanged = () => new ProjectEntryError('회사 또는 사용자가 바뀌었습니다. 현재 문맥에서 다시 확인하세요.', 409, 'ENTRY_CONTEXT_CHANGED');
const malformed = () => new ProjectEntryError('프로젝트 확인 응답이 올바르지 않습니다. 다시 확인하세요.', 503, 'ENTRY_RESPONSE_INVALID');
/** [FIX1 · 보완1] 통합 프로젝트 링크로 왔는데 서버가 «아니다» 라고 답한 경우.
 *
 *  ⚠️ 이것은 응답 오류가 아니다 — 서버는 정확히 답했다. **요청 종류와 사실이 다른 것**이고,
 *    그대로 열면 통합 프로젝트 링크가 일반 프로젝트를 여는 통로가 된다. */
const notMega = () => new ProjectEntryError(
  '통합 프로젝트 링크인데 해당 프로젝트는 통합 프로젝트가 아닙니다. 목록에서 다시 선택하세요.',
  404, 'ENTRY_NOT_MEGA');
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw malformed();
  return value as Record<string, unknown>;
}
const text = (value: unknown, allowEmpty = false): value is string => typeof value === 'string'
  && (allowEmpty || value.trim().length > 0) && value.length <= 2000;

const ID = /^[A-Za-z0-9_-]{1,160}$/;

export async function readProjectEntry(projectId: string, signal?: AbortSignal,
                                       childId = '', requireMega = false): Promise<ProjectEntry> {
  if (!ID.test(projectId)) throw new ProjectEntryError('프로젝트 링크를 확인하세요.', 422, 'ENTRY_INVALID_TARGET');
  if (childId && !ID.test(childId)) throw new ProjectEntryError('프로젝트 링크를 확인하세요.', 422, 'ENTRY_INVALID_TARGET');
  const identity = studioIdentityKey(), selected = { ...getEnterpriseContext() };
  const current = () => { if (signal?.aborted || identity !== studioIdentityKey()) throw contextChanged(); };
  current();
  try {
    // ★ 부모·자식을 **한 번에** 묻는다. 두 번 물으면 그 사이에 문맥이 바뀔 수 있고,
    //   두 응답을 맞춰 보는 쪽이 관계를 추론하게 된다.
    const query = childId ? `?child=${encodeURIComponent(childId)}` : '';
    const response = await apiFetch(
      `/api/v1/factory/${encodeURIComponent(projectId)}/entry-metadata${query}`, {
      method: 'GET', cache: 'no-store', signal,
    });
    current();
    const raw: unknown = await response.json().catch(() => null);
    current();
    if (!response.ok) {
      // 비가시 자원의 서버 상세/원문은 화면 오류에 옮기지 않는다.
      const message = response.status === 401 ? '로그인이 필요합니다.'
        : response.status === 403 || response.status === 404 ? '현재 회사·권한에서 프로젝트를 찾을 수 없습니다.'
        : response.status === 409 ? '확인 중 프로젝트 문맥이 바뀌었습니다. 다시 확인하세요.'
        : '프로젝트를 확인하지 못했습니다. 잠시 후 다시 확인하세요.';
      throw new ProjectEntryError(message, response.status, `ENTRY_HTTP_${response.status}`);
    }
    const envelope = object(raw), row = object(envelope.data);
    if (envelope.status !== 'success') throw malformed();
    /** 한 프로젝트의 사실을 검사해서 꺼낸다. **부모와 자식이 같은 규칙을 지난다** —
     *  두 벌로 만들면 한쪽만 느슨해지고, 느슨해진 쪽으로 원문이 샌다. */
    const facts = (source: Record<string, unknown>, expected: string): ProjectEntryFacts => {
      const owner = object(source.ownership), view = object(source.viewing_context);
      if (source.project_id !== expected || !text(source.project_name)
          || (source.runtime_document_version !== '1.0' && source.runtime_document_version !== '2.0')
          || !text(owner.tenant_id) || !text(owner.enterprise_scope_id, true) || !text(owner.entity_mode)
          || !text(view.tenant_id) || !text(view.scope_node_id, true) || !text(view.entity_mode)
          || owner.tenant_id !== view.tenant_id || owner.entity_mode !== view.entity_mode) throw malformed();
      if ((selected.tenantId && selected.tenantId !== view.tenant_id)
          || (selected.scopeNodeId && selected.scopeNodeId !== view.scope_node_id)
          || (selected.entityMode && selected.entityMode !== view.entity_mode)) throw contextChanged();
      // 전체 상태/권한 플래그 등 확장 필드는 복사하지 않는다. 범위 계층은 서버가 판정한다.
      return { project_id: expected, project_name: source.project_name,
        runtime_document_version: source.runtime_document_version as ProjectEntry['runtime_document_version'],
        ownership: { tenant_id: owner.tenant_id, enterprise_scope_id: owner.enterprise_scope_id, entity_mode: owner.entity_mode },
        viewing_context: { tenant_id: view.tenant_id, scope_node_id: view.scope_node_id, entity_mode: view.entity_mode } };
    };
    if (typeof row.is_mega_project !== 'boolean') throw malformed();
    // ⚠️ 물어본 만큼만 받는다. 안 물었는데 자식이 오거나, 물었는데 안 오거나, 다른
    //   자식이 오면 «응답이 계약대로가 아니다» — 관계를 여기서 메우지 않는다.
    if (childId ? row.child === null : row.child !== null) throw malformed();
    // ★★★ [FIX1 · 보완1] **메가 요청은 «명시 true» 일 때만 진행한다.**
    //   서버가 사실을 답해도 아무도 그 사실을 쓰지 않으면 통제가 아니다 — 실제로
    //   그랬다(설계안에 「Gate 가 거절한다」고 적고 구현하지 않았다).
    //   자식 유무와 «무관하게» 본다. 자식 없는 메가 링크도 일반 프로젝트를 열면 안 된다.
    if (requireMega && row.is_mega_project !== true) throw notMega();
    // 서버가 옳다면 「메가가 아닌데 자식이 딸려 온다」는 나올 수 없다 — 계약 위반이다.
    if (row.child !== null && row.is_mega_project !== true) throw malformed();
    return { ...facts(row, projectId), is_mega_project: row.is_mega_project,
      child: childId ? facts(object(row.child), childId) : null };
  } catch (error) {
    current();
    if (error instanceof ProjectEntryError) throw error;
    throw new ProjectEntryError('연결을 확인하지 못했습니다. 입력을 변경하지 않고 다시 조회할 수 있습니다.', 503, 'ENTRY_CONNECTION_FAILED');
  }
}

export type ProjectEntryState = EntryState<ProjectEntry, ProjectEntryError>;

export function createProjectEntryFlow(projectId: string, childId = '', requireMega = false) {
  //: ★ 수명(세대·중단·신원·구독)은 공통부가 맡고, **검증과 오류는 이 모듈이 그대로 쓴다**.
  return createEntryFlow<ProjectEntry, ProjectEntryError>({
    read: signal => readProjectEntry(projectId, signal, childId, requireMega),
    contextChanged, isOwnError: error => error instanceof ProjectEntryError,
  });
}
