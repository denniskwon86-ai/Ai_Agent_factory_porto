// [이관 3/10] 업무표준(규정·지침) API 어댑터
//
// ⚠️ 종전 `WorkStandardPanel` 은 `API_BASE_URL` 을 **자기 파일에 다시 선언**하고 `fetch` 를
//   직접 불렀다. 그래서 ① 주소가 저장소에서 아홉 번째로 중복 선언됐고, ② 응답 봉투의 통제
//   메타데이터(`blocked_reason`)를 버렸고, ③ 실패와 «없음»이 같은 코드로 흘렀다.
//   → 공용 `closedLoopEnvelopeFetch` 를 쓰고, 통제 메타데이터를 그대로 올려 보낸다.
import { closedLoopEnvelopeFetch } from './closedLoopFetch';

const S = '/api/v1/standards';

export type StandardRow = {
  master_code: string;
  name: string;
  version: number;
  valid_from: string;
  status: string;
  type_id: string;
  /** 'regulation' | 'guideline' — 내부 값. 화면은 반드시 한국어로 바꿔 보여준다. */
  kind: string;
  /** 'RFP' | 'QA' … 내부 단계 코드. 사용자에게 그대로 보이지 않게 한다. */
  stage: string;
  agent_id: string;
  role_statement: string;
  pass_threshold: number | null;
  gate_count: number;
  advisory_count: number;
};

export type StandardCheck = {
  id: string;
  desc: string;
  weight: number;
  type: string;
  advisory: boolean;
};

export type StandardDetail = {
  standard: {
    stage?: string;
    standard_kind?: string;
    role_statement?: string;
    evaluates?: string;
    inputs?: string;
    deliverable?: string;
    must_include?: string[];
    principles?: string[];
    must_not?: string[];
    checks?: StandardCheck[];
    pass_threshold?: number | null;
    hard_fail_checks?: string[];
    _meta?: { master_code?: string; version?: number; source?: string };
  } | null;
  agent_brief: string;
};

export type HistoryRow = {
  version: number;
  name: string;
  valid_from: string;
  valid_to: string | null;
  status: string;
  source: string;
  updated_at: string;
};

export type KindMeta = { kind: string; type_id: string; label: string; desc: string };

/** 목록 응답 — `blockedReason` 을 버리지 않는다. «없다»와 «안 보인다»는 정반대의 사실이다. */
export type StandardList = { rows: StandardRow[]; blockedReason: string };
export type KindList = { rows: KindMeta[]; blockedReason: string };

export const standardApi = {
  list: async (): Promise<StandardList> => {
    const e = await closedLoopEnvelopeFetch<StandardRow[]>('GET', S);
    return { rows: e.data || [], blockedReason: String(e.blocked_reason || '') };
  },

  kinds: async (): Promise<KindList> => {
    const e = await closedLoopEnvelopeFetch<KindMeta[]>('GET', `${S}/kinds`);
    return { rows: e.data || [], blockedReason: String(e.blocked_reason || '') };
  },

  detail: async (stage: string): Promise<StandardDetail> => {
    const e = await closedLoopEnvelopeFetch<StandardDetail>('GET', `${S}/${encodeURIComponent(stage)}`);
    return e.data;
  },

  history: async (stage: string): Promise<HistoryRow[]> => {
    const e = await closedLoopEnvelopeFetch<HistoryRow[]>(
      'GET', `${S}/${encodeURIComponent(stage)}/history`);
    return e.data || [];
  },

  reseed: async (): Promise<Record<string, unknown>> => {
    const e = await closedLoopEnvelopeFetch<Record<string, unknown>>(
      'POST', `${S}/seed?force=true`, {});
    return e.data;
  },
};
