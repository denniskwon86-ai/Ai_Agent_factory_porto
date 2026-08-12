// 연계 / 크로스워크 API 클라이언트 (M2·M3).
//
// ⚠️ 화면과 **의도적으로 분리**한다(`shadowApi`·`qualityApi` 와 같은 관례).
//
// ## ★★ 종전 화면이 자기 `API_BASE_URL` 을 선언하고 있었다
//
// `CrosswalkPanel` 상단에 `const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '…8080'`
// 이 있었다. `lib/api.ts` 머리말이 경고한 «8곳 중복 선언» 중 하나이며, 예전에 같은 방식으로
// `KnowledgeHubPanel` 의 모든 호출이 **조용히 익명으로** 나갔다(무제한 관리자인데 화면은
// 「등록된 지식팩이 없습니다」였다). 지금은 인터셉터가 origin 으로 판정해 덮이지만,
// 중복 선언을 남겨 두면 다음에 포트가 갈릴 때 같은 사고가 재현된다. 여기서 없앤다.
//
// ## ★★★ 그리고 조회 실패를 `{ data: [] }` 로 바꿔치기하고 있었다
//
// `fetch(...).then(r => r.ok ? r.json() : { data: [] })` — 403 도 500 도 **빈 목록**이 됐다.
// 이 화면에서 빈 목록은 「매핑할 것이 없다」·「승인 대기가 없다」로 읽힌다. 실패는 던진다.
import { API_BASE_URL } from './api';

export type ApiError = Error & { status?: number };

const X = '/api/v1/crosswalk';

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = (j as any)?.detail;
    const msg = typeof d === 'string' ? d
      : Array.isArray(d) ? d.map((e: any) => e?.msg || JSON.stringify(e)).join(' · ')
        : `요청 실패 (${r.status})`;
    const err = new Error(msg) as ApiError;
    err.status = r.status;
    throw err;
  }
  return (j as any).data as T;
}

/** `data` 밖의 통제 메타데이터(`write_blocked`)까지 보존해야 하는 요청에 쓴다.
 *  ⚠️ 위 `req` 는 `.data` 만 꺼내므로 그 값들이 **조용히 버려진다.** */
async function reqEnvelope(method: string, path: string, body?: unknown): Promise<any> {
  const r = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = (j as any)?.detail;
    const msg = typeof d === 'string' ? d : `요청 실패 (${r.status})`;
    const err = new Error(msg) as ApiError;
    err.status = r.status;
    throw err;
  }
  return j;
}

// ── 타입 ─────────────────────────────────────────────────────────────────
export type Sys = {
  system_id: string; name: string; mcp_endpoint: string; scope: string; status: string;
};
export type Field = {
  system_id: string; entity: string; field: string; field_type: string;
  is_key: number; mapped_type: string; mapped_attr: string;
};
export type Proposal = {
  id: number; master_code: string; external_key: string;
  confidence: number; rationale: string; status: string;
};
export type Mapping = { master_code: string; external_key: string };

export type LiveValue = {
  ok?: boolean; values?: Record<string, unknown>; as_of?: string; cached?: boolean;
  error?: string;
};

/** 시스템 목록 + **쓰기 가능 여부.**
 *
 * ★★★ 서버가 「지금 이 사람이 바꿀 수 있는가」를 함께 준다(`write_blocked`). 빈 문자열이면
 *   바꿀 수 있고, 아니면 그 문장이 곧 못 바꾸는 이유다.
 *   ⚠️ **화면이 이 판정을 다시 만들지 말 것** — 만들면 서버와 서서히 갈라져 「버튼은 보이는데
 *   서버는 거부」가 생긴다. 실제로 그 상태였다(2026-08-08 행동 단위 대조에서 발견). */
export type SystemsResult = { rows: Sys[]; writeBlocked: string };

export const crosswalkApi = {
  systems: () => req<Sys[]>('GET', `${X}/systems`),

  systemsWithRights: async (): Promise<SystemsResult> => {
    const j = await reqEnvelope('GET', `${X}/systems`);
    return { rows: (j.data as Sys[]) || [], writeBlocked: String(j.write_blocked || '') };
  },
  schema: (sid: string) => req<Field[]>('GET', `${X}/systems/${sid}/schema`),
  proposals: (sid: string) => req<Proposal[]>('GET', `${X}/systems/${sid}/proposals`),
  mappings: (sid: string) => req<Mapping[]>('GET', `${X}/systems/${sid}/mappings`),

  createSystem: (b: { system_id: string; name: string; mcp_endpoint: string }) =>
    req<Sys>('POST', `${X}/systems`, b),
  setStatus: (sid: string, status: string) =>
    req<Sys>('PUT', `${X}/systems/${sid}`, { status }),

  addField: (sid: string, b: {
    entity: string; field: string; field_type: string; is_key: boolean; mapped_attr: string;
  }) => req<Field>('POST', `${X}/systems/${sid}/schema/field`, b),

  /** CSV 는 multipart 라 `req` 를 쓰지 않는다 — 대신 오류 규약은 같게 맞춘다. */
  importCsv: async (sid: string, file: File): Promise<{ imported: number; total: number }> => {
    const form = new FormData();
    form.append('file', file);
    const r = await fetch(`${API_BASE_URL}${X}/systems/${sid}/schema/import`,
      { method: 'POST', body: form });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err = new Error((j as any)?.detail || `등록 실패 (${r.status})`) as ApiError;
      err.status = r.status;
      throw err;
    }
    return (j as any).data;
  },

  /** ⚠️ `use_llm=true` 는 **LLM 쿼터를 소비한다.** 화면이 그 사실을 말해야 한다. */
  propose: (sid: string, useLlm: boolean) => req<{
    proposed: number; deterministic: number; llm_used: boolean;
  }>('POST', `${X}/systems/${sid}/propose?use_llm=${useLlm}`),

  approve: (id: number, externalKey: string | null) =>
    req<Proposal>('POST', `${X}/proposals/${id}/approve`, { external_key: externalKey }),
  reject: (id: number) => req<Proposal>('POST', `${X}/proposals/${id}/reject`),

  /** [M3] 승인 매핑의 외부 실측값 온디맨드 조회(읽기전용). 비활성/미승인이면 409. */
  resolve: (masterCode: string, systemId: string) =>
    req<LiveValue>('POST', '/api/v1/mcp/resolve',
      { master_code: masterCode, system_id: systemId }),
};
