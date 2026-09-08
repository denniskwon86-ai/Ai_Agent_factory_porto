/**
 * 만든 업무 키트 앱을 **열어서 본다.**
 *
 * ## 왜 두 단계인가
 *
 * 앱 데이터는 세션 토큰만으로 읽히지 않는다. 호스트가 **앱 증명**(`X-App-Proof`)을
 * 발급하고, 런타임이 그 증명으로 「어느 평면의 무엇을 읽는가」를 정한다. 증명에 담기는
 * 권한은 «사용자가 실제로 할 수 있는 것 ∩ 앱 매니페스트가 선언한 것» 의 교집합이다.
 *
 * ★★★ 증명 전문은 **이 모듈의 호출부 메모리에만** 둔다 — `localStorage` 에도, iframe
 *   에도, 로그에도 보내지 않는다(`test_app_runtime_no_credentials.py` 가 잠근다).
 * ⚠️ 후보 판(`candidate`)은 증명이 나오지 않는다(403). 운영으로 올려야 열린다 —
 *   그것이 「승인 전 판이 실적 숫자를 그리는」 것을 막는 경계다.
 */
import { apiFetch } from './api';
import { unwrap } from './dataPrepApi';

const APPDATA = '/api/v1/appdata';

export interface AppDatasetRow {
  dataset_id: string;
  name: string;
  label: string;
  record_count: number;
}

/** 이 앱이 가진 데이터셋 목록. ★ 평면은 **서버가** 릴리스 상태로 고른다. */
export async function listAppDatasets(releaseId: string): Promise<AppDatasetRow[]> {
  const res = await apiFetch(`${APPDATA}/datasets?release_id=${encodeURIComponent(releaseId)}`);
  if (!res.ok) throw new Error(`데이터셋 목록을 불러오지 못했습니다 (${res.status})`);
  const body = await res.json();
  // ⚠️ 이 라우트는 `{status,data}` 봉투를 쓰지 않는다 — 벗기려 들면 undefined 가 된다.
  return (body.datasets || []) as AppDatasetRow[];
}

/** 앱 증명 발급. ⚠️ 후보 판이면 403, 없는 릴리스면 404 다. */
export async function issueAppProof(releaseId: string): Promise<string> {
  return (await unwrap<{ token: string }>(
    await apiFetch(`${APPDATA}/runtime/proof`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ release_id: releaseId }),
    }), '앱 증명')).token;
}

export interface AppRecords {
  records: Record<string, unknown>[];
  total: number;
  /** 앱에 공개 가능한 판 정보. 내부 Snapshot/Binding ID는 의도적으로 공개하지 않는다. */
  as_of: string;
  stale: boolean;
}

/**
 * 앱이 보는 **실제 업무 데이터**.
 *
 * ★ 인증판을 통해 읽는 데이터셋(`ENTERPRISE_READ`)은 여기서 인증된 판의 행이 온다 —
 *   앱에 복사본을 만들지 않는다. 그래서 원천이 바뀌면 앱도 같이 바뀐다.
 */
export async function readAppRecords(
  proof: string, name: string, limit = 20, offset = 0,
): Promise<AppRecords> {
  const res = await apiFetch(
    `${APPDATA}/runtime/datasets/${encodeURIComponent(name)}/records?limit=${limit}&offset=${offset}`,
    { headers: { 'X-App-Proof': proof } });
  if (!res.ok) throw new Error(`«${name}» 을(를) 읽지 못했습니다 (${res.status})`);
  const body = await res.json();
  const d = (body && typeof body === 'object' && 'data' in body) ? body.data : body;
  return {
    records: d.records || [],
    total: Number(d.total ?? (d.records || []).length),
    as_of: String(d.as_of || ''),
    stale: Boolean(d.stale),
  };
}
