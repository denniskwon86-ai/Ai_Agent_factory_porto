// 데이터 거버넌스 API 클라이언트 (명세서 §6 / §12 · M1)
//
// ⚠️ 화면(GovernanceConsole.tsx)과 **의도적으로 분리**한다. 디자인 시안이 확정되면 화면을
//   대대적으로 개편할 예정이므로, 그때 이 파일은 **그대로 재사용**되어야 한다.
//   따라서 여기에는 표현 관련 코드를 두지 않는다(문구·색·레이아웃 금지, 데이터 형태와 호출만).
//
// 인증: `installFetchInterceptor` 가 `X-Factory-User` 를 자동으로 붙인다(lib/api.ts).
// 조직 범위는 각 호출의 `scopeNodeId` 인자로 넘긴다 — 전역 컨텍스트 스위처가 생기면
//   인터셉터로 옮긴다.
import { API_BASE_URL } from './api';

// ── 공통 ──────────────────────────────────────────────────────────────────
// ⚠️ [2026-08-04 이관 5/10] 종전에는 상태 코드를 **버렸다**(`new Error(문구)` 만 던졌다).
//   그래서 화면이 «권한 없음(403)»과 «서버 장애»를 구분할 수 없었고, 거버넌스 콘솔은 둘 다
//   "불러오지 못한 항목"으로 뭉갠 뒤 각 섹션에 «후보 없음» 을 표시했다.
//   거버넌스 화면에서 그 오독은 특히 무겁다 — «결손 없음»으로 읽히면 정비가 끝났다고 믿는다.
export type GovernanceError = Error & { status?: number };

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const e = new Error(j?.detail || `요청 실패 (${r.status})`) as GovernanceError;
    e.status = r.status;
    throw e;
  }
  return j.data as T;
}

function scoped(path: string, scopeNodeId?: string): string {
  if (!scopeNodeId) return path;
  return `${path}${path.includes('?') ? '&' : '?'}scope_node_id=${encodeURIComponent(scopeNodeId)}`;
}

// ── 기준정보: 조직 범위 커버리지 ─────────────────────────────────────────
// 미바인딩 = 모든 조직에 노출. 점진 도입 규칙(D-014)의 대가로 반드시 관측한다.
export type MasterCoverage = {
  total_records: number;
  bound_records: number;
  exposed_records: number;
  exposed_codes: string[];
  coverage_ratio: number;
  note: string;
};

export const fetchMasterCoverage = () =>
  get<MasterCoverage>('/api/v1/master/scope-bindings/coverage');

// ── 기준정보: 중복 후보 ───────────────────────────────────────────────────
export type DuplicateCandidate = {
  kind: string;
  confidence: 'high' | 'medium' | 'low';
  codes: [string, string];
  why: string;
  names: Record<string, string>;
  suggested_action: string;
};

export const fetchDuplicates = () =>
  get<{ candidates: DuplicateCandidate[]; total: number; high_confidence: number }>(
    '/api/v1/master/records/duplicates',
  );

// ── 기준정보: 문서 품질 보정 목록 ────────────────────────────────────────
export type QualityFinding = {
  kind: string;
  severity: 'high' | 'medium' | 'low';
  document: string;
  subject: string;
  evidence: Record<string, unknown>;
  suggested_action: string;
};

export const fetchDocumentQuality = () =>
  get<{ findings: QualityFinding[] }>('/api/v1/master/documents/quality');

// ── 카탈로그 ──────────────────────────────────────────────────────────────
export type DataAsset = {
  asset_id: string;
  name: string;
  asset_type: string;
  owner_dept_id: string;
  sensitivity: string;
  refresh_cadence: string;
  enterprise_scope_id: string;
  status: string;
};

export type GovernanceGap = {
  kind: string;
  severity: 'high' | 'medium' | 'low';
  asset_id: string;
  asset: string;
  why: string;
  suggested_action: string;
};

export type ScopeCoverage = {
  total: number;
  scoped: number;
  unscoped: number;
  coverage_ratio: number;
  unscoped_assets: string[];
  note: string;
};

export const fetchAssets = (scopeNodeId?: string) =>
  get<DataAsset[]>(scoped('/api/v1/catalog/assets', scopeNodeId));

export const fetchGovernanceGaps = (scopeNodeId?: string) =>
  get<{ gaps: GovernanceGap[]; total: number; high: number }>(
    scoped('/api/v1/catalog/governance/gaps', scopeNodeId),
  );

export const fetchScopeCoverage = () =>
  get<ScopeCoverage>('/api/v1/catalog/governance/coverage');

// ── 연계 시스템(M2 크로스워크) 범위 커버리지 ─────────────────────────────
// 범위 미지정 시스템의 실측값은 **모든 조직의 프롬프트**에 병기될 수 있다(MCP 실측 병기).
// 화면 유출보다 찾기 어려운 경로라 여기서 함께 센다.
export type SystemsCoverage = ScopeCoverage & { unscoped_systems: string[] };

export const fetchSystemsCoverage = () =>
  get<SystemsCoverage>('/api/v1/crosswalk/systems/coverage');

// ── 데이터 계약 ───────────────────────────────────────────────────────────
// `unverifiable` 은 통과가 아니라 **확인하지 못한 것**이다. 화면에서 kept 와 섞으면 안 된다.
export type ContractEvaluation = {
  contract_id: string;
  contract_key: string;
  version: number;
  consumer: string;
  state: 'kept' | 'at_risk' | 'breached' | 'unverifiable';
  findings: { kind: string; severity: string; why: string }[];
  checked: string[];
  unverifiable: { kind: string; why: string }[];
};

export const fetchContractEvaluations = () =>
  get<{ total: number; by_state: Record<string, number>; results: ContractEvaluation[] }>(
    '/api/v1/contracts/evaluate',
  );

// ── 외부 인텔리전스 준비도 ───────────────────────────────────────────────
// 수집기는 만들지 않았다. 지금 산출물은 "무엇이 없는지 정확히 아는 것"이다.
export type ExternalIndicatorReadiness = {
  code: string;
  name: string;
  required_grade: string;
  acceptable_latency: string;
  usable_for_baseline: boolean;
  reason: string;
  gap_impact: string;
  next_action: string;
};

export const fetchExternalReadiness = () =>
  get<{
    total: number;
    usable_for_baseline: number;
    blocked: number;
    approved_sources: number;
    indicators: ExternalIndicatorReadiness[];
    note: string;
  }>('/api/v1/external/readiness');

// ── 조직 트리 (범위 선택용) ──────────────────────────────────────────────
// 백엔드는 **중첩 트리**를 준다(`GET /tree`). 셀렉트 박스에 쓰려면 평탄화가 필요한데,
// 그 변환을 화면에 두면 개편 때 같이 버려진다 — 데이터 계층의 책임으로 둔다.
export type EcmNode = {
  node_id: string;
  code: string;
  name_ko: string;
  node_type: string;
  depth: number;
  readable: boolean;
  children?: EcmNode[];
};

export type FlatNode = { node_id: string; label: string; depth: number; readable: boolean };

export function flattenTree(roots: EcmNode[]): FlatNode[] {
  const out: FlatNode[] = [];
  const walk = (n: EcmNode, depth: number) => {
    out.push({ node_id: n.node_id, label: n.name_ko || n.code, depth, readable: n.readable });
    (n.children || []).forEach((c) => walk(c, depth + 1));
  };
  roots.forEach((r) => walk(r, 0));
  return out;
}

export async function fetchOrgNodes(): Promise<FlatNode[]> {
  try {
    return flattenTree(await get<EcmNode[]>('/api/v1/enterprise-context/tree'));
  } catch {
    return []; // ECM 미도입 환경 — 범위 선택 없이 전체를 본다
  }
}
