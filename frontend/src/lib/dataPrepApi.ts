// [BDR-2·3·5 / BDR-7] 업무 데이터 준비 · 기준선 API 클라이언트.
//
// ⚠️ 여기서 판정하지 않는다. 서버가 준 상태·문구를 **그대로 화면에 옮긴다** —
//   화면이 자기 규칙으로 다시 판단하면 두 판정이 갈라지고, 갈린 날 사용자는
//   서버가 막은 것을 화면이 허용하는 상태를 본다.
import { apiFetch } from './api';

// ── 서버 어휘를 그대로 가져온다 ─────────────────────────────────────────
//
// ★ 이 목록은 `core/data_preparation/readiness.py` 의 `DATASET_STATES` 와 **같아야**
//   한다. 다르면 화면이 모르는 상태를 만나 빈 칸을 그린다.
export type DatasetState =
  | 'NOT_CONFIGURED'
  | 'SOURCE_CONFIGURED'
  | 'DATA_AVAILABLE'
  | 'QUALITY_FAILED'
  | 'RECONCILIATION_FAILED'
  | 'APPROVAL_PENDING'
  | 'READY'
  | 'STALE'
  | 'UNAVAILABLE';

export type OutputState = 'AVAILABLE' | 'AVAILABLE_WITH_WARNING' | 'BLOCKED';

export interface DatasetReadiness {
  /** 계약이 선언한 사람이 읽는 이름. **없을 수 있다** — 없으면 화면이 계약
   *  이름을 그대로 쓴다(계약 이름을 여기 복사하지 않는다). */
  label?: string;
  /** 이 데이터가 무엇에 쓰이는지. 없을 수 있다. */
  purpose?: string;
  dataset_contract_key: string;
  state: DatasetState;
  next_action: string;
  responsible_role: string;
  detail: string;
  as_of: string;
  snapshot_id: string;
  data_kind: string;
}

export interface OutputReadiness {
  output: string;
  state: OutputState;
  reason_code: string;
  user_message: string;
  next_action: string;
  responsible_role: string;
  blocking_datasets: string[];
}

export interface InstanceReadiness {
  status: 'READY' | 'PARTIAL' | 'BLOCKED';
  as_of: string;
  coverage: { required: number; ready: number; stale: number; blocked: number };
  datasets: DatasetReadiness[];
  available_outputs: string[];
  blocked_outputs: OutputReadiness[];
  outputs: OutputReadiness[];
  context_omitted: number;
  binding_set_fingerprint: string;
  snapshot_set_fingerprint: string;
  kit_id: string;
  version: string;
  instance_id: string;
  data_kind: string;
}

// ── 응답 봉투를 벗긴다 ──────────────────────────────────────────────────
//
// ⚠️⚠️ 서버는 `{status, data}` 로 답한다. 봉투째 읽으면 필드가 전부 `undefined` 가
//   되고, 화면은 **빈 값을 «데이터 없음» 으로** 그린다. 그 화면은 오류를 내지 않는다.
async function unwrap<T>(res: Response, what: string): Promise<T> {
  if (!res.ok) {
    let detail = '';
    try {
      detail = (await res.json())?.detail || '';
    } catch {
      /* 본문이 JSON 이 아니면 상태 코드만으로 말한다 */
    }
    // ★ 상태 코드를 그대로 실어 보낸다 — 화면이 「없음(404)」과 「아직 못 읽음(503)」을
    //   다르게 그려야 하기 때문이다. 하나로 뭉치면 사용자가 할 일이 정해지지 않는다.
    throw new DataPrepError(detail || `${what}을(를) 불러오지 못했습니다.`, res.status);
  }
  const body = await res.json();
  return (body?.data ?? body) as T;
}

export class DataPrepError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'DataPrepError';
    this.status = status;
  }
}

const BASE = '/api/v1/data-preparation';

export async function listKits() {
  return unwrap<{ kits: any[] }>(await apiFetch(`${BASE}/kits`), '데이터 키트 목록');
}

// ★ 사용자에게 `ki_…` 를 타이핑하라고 요구하지 않기 위한 목록.
export async function listInstances() {
  return unwrap<{ instances: any[] }>(
    await apiFetch(`${BASE}/instances`), '키트 인스턴스 목록');
}

export async function getInstance(instanceId: string) {
  return unwrap<any>(
    await apiFetch(`${BASE}/instances/${encodeURIComponent(instanceId)}`),
    '키트 인스턴스',
  );
}

export async function getReadiness(instanceId: string) {
  return unwrap<InstanceReadiness>(
    await apiFetch(`${BASE}/instances/${encodeURIComponent(instanceId)}/readiness`),
    '데이터 준비 상태',
  );
}

export async function listSnapshots(instanceId: string) {
  return unwrap<{ snapshots: any[] }>(
    await apiFetch(`${BASE}/instances/${encodeURIComponent(instanceId)}/snapshots`),
    '데이터 판 목록',
  );
}

export async function uploadSnapshot(bindingId: string, file: File) {
  const form = new FormData();
  form.append('file', file);
  // ⚠️ `Content-Type` 을 직접 지정하지 않는다 — 브라우저가 multipart 경계를 붙여야 한다.
  return unwrap<any>(
    await apiFetch(`${BASE}/bindings/${encodeURIComponent(bindingId)}/snapshots`, {
      method: 'POST',
      body: form,
    }),
    '파일 등록',
  );
}

export async function certifySnapshot(
  snapshotId: string,
  control: Record<string, unknown> = {},
) {
  // ★★★ `control` 은 **원천이 말한 값**(행 수·합계)이다. 이것 없이 인증하면
  //   「잘린 파일」을 잡을 방법이 없다 — 그래서 화면이 그 사실을 말해야 한다.
  return unwrap<any>(
    await apiFetch(`${BASE}/snapshots/${encodeURIComponent(snapshotId)}/certify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ control }),
    }),
    '판 인증',
  );
}

export async function decideBinding(bindingId: string, action: string, reason = '') {
  return unwrap<any>(
    await apiFetch(`${BASE}/bindings/${encodeURIComponent(bindingId)}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, reason }),
    }),
    '원천 결속 상태 변경',
  );
}

// ── 기준선·시뮬레이션 ───────────────────────────────────────────────────
const BASELINE = '/api/v1/baseline';

export async function createBaseline(
  instanceId: string,
  snapshotIds: string[],
  label = '',
) {
  return unwrap<any>(
    await apiFetch(`${BASELINE}/builds`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // ★★★ `snapshot_ids` 를 **명시**해 보낸다 — 「최신으로 알아서」를 서버가 받지
      //   않는다. 그것을 받는 순간 재현할 수 없는 기준선이 생긴다.
      body: JSON.stringify({
        instance_id: instanceId,
        snapshot_ids: snapshotIds,
        label,
      }),
    }),
    '기준선',
  );
}

export async function simulate(
  instanceId: string,
  snapshotIds: string[],
  baseValues: Record<string, number>,
  assumptions: Record<string, number>,
) {
  return unwrap<any>(
    await apiFetch(`${BASELINE}/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        instance_id: instanceId,
        snapshot_ids: snapshotIds,
        base_values: baseValues,
        assumptions,
      }),
    }),
    '시뮬레이션',
  );
}

export async function createDecision(payload: {
  instance_id: string;
  snapshot_ids: string[];
  base_values: Record<string, number>;
  assumptions: Record<string, number>;
  title: string;
  owner: string;
  due: string;
  path_from?: string;
  path_to?: string;
}) {
  // ★★★ `owner` · `due` 를 **보낸다**. 서버가 없으면 거부한다 — 책임자·기한 없는
  //   안건은 「검토하겠습니다」로 끝나고 아무 일도 안 난다.
  return unwrap<any>(
    await apiFetch(`${BASELINE}/decisions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    '의사결정 안건',
  );
}

// ★ 기준선을 함께 보내면 **그 기준선으로** 근거를 잇는다. 보내지 않으면 근거를
//   «확인하지 않은» 것이지 «없는» 것이 아니다 — 응답의 `evidence_checked` 가 가른다.
// ★ 인증된 판에서 뽑을 수 있는 기준값. ⚠️ 뽑을 수 없는 칸은 `value: null` 로
//   오고 `reason` 이 왜인지 말한다 — 0 이 오지 않는다.
export async function deriveBaseValues(instanceId: string, snapshotIds: string[]) {
  return unwrap<{
    fields: { key: string; value: number | null; source: string; reason: string;
              derived_from: string[] }[];
    derived_count: number; manual_count: number; note: string;
  }>(
    await apiFetch(`${BASELINE}/base-values`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instance_id: instanceId, snapshot_ids: snapshotIds }),
    }),
    '기준값',
  );
}

export async function getImpactPath(
  start: string, end: string, instanceId = '', snapshotIds: string[] = [],
) {
  const q = new URLSearchParams({ start, end });
  if (instanceId) {
    q.set('instance_id', instanceId);
    for (const s of snapshotIds) q.append('snapshot_ids', s);
  }
  return unwrap<any>(await apiFetch(`${BASELINE}/impact-path?${q.toString()}`), '영향 경로');
}
