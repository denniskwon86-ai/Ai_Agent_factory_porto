// [ECM §9] 회사 구성 — 회사(tenant)·법인/가상회사(entity)·조직 노드·공정 프로필.
//
// ## ⚠️⚠️ [2026-08-25 사용자 지적] 왜 이 파일이 생겼는가
//
// > 회사 구성 정보를 등록하는 화면이 없는 것 같네요.
// > 가상회사를 구성하고 선택할 수도 있어야 합니다.
//
// **백엔드는 이미 다 있었다.** `enterprise_entities` 표에 `entity_mode`(REAL/VIRTUAL/
// COMPETITOR)와 `base_entity_id`(복제)가 있고, 생성·승인·노드·간선·프로필 경로가 전부
// 서 있다. 없는 것은 **부르는 화면**뿐이었다 — 이 저장소가 반복해서 겪은
// 「통제는 있는데 부르는 경로가 없다」와 같은 자리다.
//
// ★ 여기서 판정하지 않는다. 서버가 준 상태·문구를 그대로 옮긴다.
import { apiFetch } from './api';

const BASE = '/api/v1/enterprise-context';

async function unwrap<T>(res: Response, what: string): Promise<T> {
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json())?.detail || ''; } catch { /* 본문이 JSON 이 아닐 수 있다 */ }
    // ⚠️ 실패를 «없음» 으로 바꾸지 않는다 — 상태코드를 그대로 들고 올린다.
    throw Object.assign(new Error(detail || `${what}을(를) 처리하지 못했습니다.`),
      { status: res.status });
  }
  //: ★ 봉투를 벗긴다. `{status, data}` 를 그대로 읽으면 `undefined` 가 나온다.
  return (await res.json())?.data as T;
}

// ── 회사(tenant) ─────────────────────────────────────────────────────────
export type Tenant = {
  tenant_id: string; name_ko: string; legal_name?: string; status?: string;
};

export async function listTenants() {
  return unwrap<Tenant[]>(await apiFetch(`${BASE}/tenants`), '회사 목록');
}

export async function upsertTenant(body: Tenant) {
  return unwrap<Tenant>(await apiFetch(`${BASE}/tenants`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }), '회사 이름');
}

// ── 법인 · 가상회사(entity) ──────────────────────────────────────────────
//
// ★ `entity_mode` 가 실제/가상/경쟁사를 가른다. 비협상 규칙 3: **한 트리에 섞이지 않는다.**
// ⚠️ 가상회사는 «장난감» 이 아니다 — 시나리오·복제 회사의 숫자가 실적으로 읽히면
//   그것이 이 시스템에서 가장 위험한 실패다. 그래서 화면은 모드를 **항상** 표시한다.
export type Entity = {
  entity_id: string; tenant_id: string; entity_type: string; entity_mode: string;
  name_ko: string; legal_name?: string; industry_code?: string;
  base_entity_id?: string; status: string; approved_by?: string; approved_at?: string;
};

export async function listEntities() {
  return unwrap<Entity[]>(await apiFetch(`${BASE}/entities`), '회사 구성');
}

export async function createEntity(body: {
  entity_type?: string; entity_mode?: string; name_ko: string;
  legal_name?: string; industry_code?: string; base_entity_id?: string;
  source_ref?: string; evidence_ref?: string;
}) {
  return unwrap<Entity>(await apiFetch(`${BASE}/entities`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }), '회사 등록');
}

/** ⚠️ 승인 전에는 `DRAFT` 다 — 미승인 구성은 상속·판정에 참여하지 않는다(§4.1). */
export async function approveEntity(entityId: string) {
  return unwrap<Entity>(await apiFetch(
    `${BASE}/entities/${encodeURIComponent(entityId)}/approve`, { method: 'POST' }),
    '회사 승인');
}

// ── 조직 노드 ────────────────────────────────────────────────────────────
export type EcmNode = {
  node_id: string; tenant_id: string; entity_id: string; node_type: string;
  name_ko: string; code?: string; dept_id?: string; status: string;
  children?: EcmNode[];
};

export async function getTree() {
  return unwrap<EcmNode[]>(await apiFetch(`${BASE}/tree`), '조직 트리');
}

export async function createNode(body: {
  entity_id: string; node_type?: string; name_ko: string;
  code?: string; default_parent_id?: string; dept_id?: string; status?: string;
}) {
  return unwrap<EcmNode>(await apiFetch(`${BASE}/nodes`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }), '조직 노드');
}

// ── 문맥 선택 ────────────────────────────────────────────────────────────
/** 「이 범위를 이 모드로 볼 수 있는가」를 **서버가 판정한다.**
 *
 * ⚠️ 서버는 상태를 저장하지 않는다(ECM-lite) — 클라이언트가 헤더로 문맥을 보낸다.
 *   그래서 이 호출은 «허가» 를 받는 것이고, 통과한 뒤에 클라이언트 문맥을 바꾼다.
 * ★ 통과하지 않은 문맥으로 화면을 바꾸면, 보이는 것과 권한이 갈린다. */
export async function selectContext(enterpriseScopeId: string, entityMode: string) {
  return unwrap<any>(await apiFetch(`${BASE}/contexts/select`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enterprise_scope_id: enterpriseScopeId, entity_mode: entityMode }),
  }), '문맥 선택');
}

// ── 공정 프로필 = Digital Thread 연결구성 ────────────────────────────────
//
// ⚠️⚠️ 경영 홈의 ENTERPRISE DIGITAL THREAD 는 지금 **조직 트리**를 업무 축으로 그린다.
//   설계는 「process profile 기반 동적 렌더링」을 요구하는데 그 원천을 부르는 곳이
//   없었다 — 그런데 `profile_kind` 닫힌 목록에는 `process_profile` 이 처음부터 있었다.
// ★ 회사마다 이 프로필을 세우면 그 회사의 연결 구성이 된다.

/** Digital Thread 한 칸. ★ 서버 `payload` 안의 모양이며 **여기가 그 정의다**. */
export type ThreadOverlayLayer = 'DATA' | 'SW' | 'TWIN';

/** 업무 단계 위에 겹쳐 보는 보조정보 카드 한 장.
 *
 * ★ 업무 단계마다 최대 한 장이다. 화면의 세로 예산 안에서 여러 장을 쌓으면 하단 결정
 * 패널을 침범한다. 여러 근거가 필요한 경우 `body`가 요약하고 상세 화면으로 연결한다. */
export type ThreadOverlay = {
  layer: ThreadOverlayLayer;
  /** 카드 상단 분류 — 예: DATA CONTRACT, 현업 생성 SW. */
  kicker: string;
  /** 카드 본문 — 실제 연결된 근거·도구·예측의 짧은 이름. */
  body: string;
};

/** 승인된 회사 구성이 없을 때 새 초안에 제공하는 시작점. 실행 정본은 아니다. */
export const DEFAULT_THREAD_OVERLAY_BY_NODE: Record<string, ThreadOverlay> = {
  sales: { layer: 'DATA', kicker: 'DATA CONTRACT', body: '인증판·데이터 계약' },
  sourcing: { layer: 'SW', kicker: '현업 생성 SW', body: '업무 키트 산출물 앱' },
  production: { layer: 'SW', kicker: '현업 생성 SW', body: 'Software Factory 프로젝트' },
  logistics: { layer: 'DATA', kicker: 'LIVE SYSTEM', body: '연계 시스템 이벤트' },
  finance: { layer: 'TWIN', kicker: 'DIGITAL TWIN', body: '시나리오·기준선' },
};

export type ThreadNode = {
  /** 기계 이름. 흐름선·오버레이가 이 값으로 이어진다. */
  key: string;
  /** 사람이 읽는 이름. */
  label: string;
  /** 한 줄 설명. 없으면 빈 문자열 — 지어내지 않는다. */
  note?: string;
  /** `null`이면 명시적 빈 카드, 필드 자체가 없으면 옛 프로필이라 기본값을 승계한다. */
  overlay?: ThreadOverlay | null;
};

export type Profile = {
  profile_id: string; tenant_id: string; scope_node_id: string; industry_code?: string;
  profile_kind: string; payload: { nodes?: ThreadNode[] };
  inheritance_mode: string; status: string;
  version: number;
  approved_by?: string; approved_at?: string; is_effective?: boolean;
};

export async function listProfiles(scopeNodeId = '', kind = 'process_profile', companyWide = false) {
  const q = new URLSearchParams();
  if (scopeNodeId) q.set('scope_node_id', scopeNodeId);
  if (kind) q.set('profile_kind', kind);
  if (companyWide) q.set('company_wide', 'true');
  return unwrap<Profile[]>(
    await apiFetch(`${BASE}/profiles?${q.toString()}`), '공정 프로필');
}

export async function saveProfile(body: {
  profile_id?: string;
  profile_kind?: string; scope_node_id: string; industry_code?: string;
  payload: { nodes: ThreadNode[] }; inheritance_mode?: string; status?: string;
  version?: number;
}) {
  return unwrap<Profile>(await apiFetch(`${BASE}/profiles`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_kind: 'process_profile', ...body }),
  }), '연결구성 저장');
}

/** ⚠️ 승인해야 **상속에 참여한다**(`is_effective`). 저장만 하면 DRAFT 다. */
export async function approveProfile(profileId: string) {
  return unwrap<Profile>(await apiFetch(
    `${BASE}/profiles/${encodeURIComponent(profileId)}/approve`, { method: 'POST' }),
    '연결구성 승인');
}
