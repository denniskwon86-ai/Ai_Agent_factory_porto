import { apiFetch } from './api';
import { unwrap } from './dataPrepApi';

// [Wave H / H-4] 승격 API — 후보 판을 운영으로 올리는 **단 하나의 문**.
//
// ★★★ 왜 별도 파일인가
//   승격은 데이터 준비·기준선과 다른 축이다. 같은 파일에 두면 「데이터 화면에서
//   운영 판을 바꿀 수 있다」는 모양이 되고, 그것은 이 제품이 나눠 둔 경계와 어긋난다.
//
// ⚠️ 여기서 판단하지 않는다. 서버가 다섯 검사를 돌리고 그 결과를 그대로 옮긴다 —
//   화면이 자기 규칙으로 「올려도 되겠다」를 만들면 두 판정이 갈라진다.

const F = '/api/v1/factory';

export type LifecycleStatus = 'candidate' | 'active' | 'deprecated' | 'disabled' | string;

export type ReleaseItem = {
  release_id: string;
  project_id: string;
  project_name: string;
  created_at: string;
  lifecycle_status: LifecycleStatus;
  /** `false` = 관리자가 정한 적이 없다(추정값이다). 「승인됨」으로 읽지 않는다. */
  lifecycle_recorded: boolean;
  lifecycle_reason: string;
  /** [§4.2] 운영이 될 때 봉인된 업무 데이터 판 집합의 지문. */
  data_fingerprint: string;
};

export type Check = { name: string; ok: boolean; reason: string };

export async function listReleases() {
  return unwrap<ReleaseItem[]>(await apiFetch(`${F}/library/list`), '결과물 목록');
}

/** 승격하면 무엇이 막히는가 — **바꾸지 않고** 본다. */
export async function promotionCheck(
  projectId: string, releaseId: string, noBusinessData: boolean,
) {
  const q = noBusinessData ? '?no_business_data=true' : '';
  return unwrap<{ ok: boolean; checks: Check[] }>(
    await apiFetch(
      `${F}/${encodeURIComponent(projectId)}/releases/${encodeURIComponent(releaseId)}`
      + `/promotion-check${q}`),
    '승격 사전 점검',
  );
}

export async function promote(
  projectId: string, releaseId: string, reason: string, noBusinessData: boolean,
) {
  return unwrap<{ release_id: string; status: string; data_fingerprint: string;
                  checks: Check[] }>(
    await apiFetch(
      `${F}/${encodeURIComponent(projectId)}/releases/${encodeURIComponent(releaseId)}`
      + '/promote',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason, no_business_data: noBusinessData }),
      }),
    '운영 승격',
  );
}
