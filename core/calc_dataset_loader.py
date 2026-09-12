"""★★★ [G2 B2 / M0-3] **봉인된 인증판 → 계산 입력 행.**

## 이 층이 하는 일

    sealed_snapshots {계약키: snapshot_id}
      → 인증판 조회(범위·상태 확인)
      → 불변 RAW 파일 읽기
      → 지문 대조
      → `__snapshot_id__` 를 붙인 행 목록

계산 실행기(`core/path_calculation.py`)는 이 행을 받아 투영·계산한다. 실행기가 직접
저장소를 읽지 않는 이유는 **읽는 규칙과 계산하는 규칙을 따로 시험하기 위해서**다.

## ⚠️ 여기서 반드시 하는 것

1. **인증(`CERTIFIED`)판만 읽는다.** 인증 전 판으로 만든 숫자는 검증되지 않은 자료다.
2. **범위를 대조한다.** 다른 tenant·mode·조직의 판을 봉인 목록에 적어 보내면 그것이
   곧 교차 조회다 — 봉인은 「무엇을 읽었는가」의 기록이지 「무엇을 읽어도 되는가」의
   허가가 아니다.
3. **내용 지문을 다시 계산해 대조한다.** RAW 파일은 디스크에 있고 디스크는 바뀔 수
   있다. 인증한 그 파일이 맞는지는 지문만이 답한다.
4. 못 읽으면 **던진다.** 빈 목록으로 접으면 「자료가 없다」가 되고, 실행기는 그것을
   `BLOCKED` 로 답한다 — 실제로는 **읽지 못한 것**인데 「아직 준비 안 됨」으로 보인다.
"""
from __future__ import annotations

import csv
import io
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.data_preparation import models as m
from core.data_preparation import snapshot_service as svc
from core.data_preparation import usage_policy


class SealedDatasetError(Exception):
    """봉인된 판을 읽을 수 없다. ⚠️ 「자료 없음」으로 접지 않는다."""


def _read_rows(path: str, *, key: str) -> List[Dict[str, str]]:
    """RAW CSV 를 읽는다. **문자열 그대로** 돌려준다.

    ⚠️ 여기서 수로 바꾸지 않는다 — 형 변환은 계산 모델의 일이고, 두 곳에서 하면
      「빈 값을 0 으로」 같은 규칙이 갈린다."""
    if not path or not os.path.exists(path):
        raise SealedDatasetError(
            f"{key}: 인증판의 원본 파일이 없습니다({path or '(빈 경로)'}) — 「자료 없음」이 "
            f"아니라 읽지 못한 것입니다.")
    try:
        with io.open(path, "r", encoding="utf-8-sig", newline="") as fh:
            return [dict(r) for r in csv.DictReader(fh)]
    except OSError as e:
        raise SealedDatasetError(f"{key}: 인증판 원본을 읽지 못했습니다: {e}")


def load_sealed(store: Any, *, sealed_snapshots: Mapping[str, str],
                tenant_id: str, entity_mode: str, scope_node_id: str,
                verify_fingerprint: bool = True
                ) -> Dict[str, List[Dict[str, Any]]]:
    """봉인 목록의 판을 읽어 계약키별 행 목록을 돌려준다.

    ★ 각 행에 `__snapshot_id__` 를 붙인다 — 실행기가 「봉인한 판을 읽었는가」를 확인하는
      근거이고, 그 확인은 **모든 행**에 대해 이뤄진다.

    ⚠️⚠️ 범위 대조를 여기서 한다. 실행기는 봉인 목록을 «주어진 것» 으로 보므로, 다른
      조직의 판 id 를 적어 보내면 그대로 읽힌다 — 봉인은 기록이지 허가가 아니다.
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    for key in sorted(sealed_snapshots):
        sid = str(sealed_snapshots[key] or "").strip()
        if not sid:
            raise SealedDatasetError(f"{key}: 봉인된 판 id 가 비어 있습니다.")
        row = store.get_snapshot(sid)
        if not row:
            raise SealedDatasetError(f"{key}: 봉인된 판을 찾을 수 없습니다({sid}).")
        #: ① 계약키가 맞는가. ⚠️ 다른 계약의 판을 이 자리에 넣으면 열이 통째로 다르다.
        if str(row.get("dataset_contract_key", "")) != key:
            raise SealedDatasetError(
                f"{key}: 봉인된 판({sid})은 다른 계약키의 것입니다"
                f"({row.get('dataset_contract_key')}).")
        #: ② 범위. **교차 조회를 여기서 막는다.**
        if (str(row.get("tenant_id", "")) != tenant_id
                or str(row.get("entity_mode", "")) != entity_mode
                or str(row.get("scope_node_id", "")) != scope_node_id):
            raise SealedDatasetError(
                f"{key}: 봉인된 판({sid})이 이 문맥의 것이 아닙니다 — 봉인은 무엇을 "
                f"읽었는가의 기록이지 무엇을 읽어도 되는가의 허가가 아닙니다.")
        #: ③ 인증판만. 인증 전 판으로 만든 숫자는 검증되지 않은 자료다.
        state = str(row.get("state", ""))
        if not m.is_certified(state):
            raise SealedDatasetError(
                f"{key}: 봉인된 판({sid})이 인증 상태가 아닙니다({state}) — 인증 전 "
                f"자료로 만든 숫자는 검증되지 않았습니다.")

        try:
            usage_policy.require_usable(store, row)
        except usage_policy.UsageHoldError as exc:
            raise SealedDatasetError(str(exc)) from exc

        #: ④ 원본 체크섬. RAW 는 디스크에 있고 디스크는 바뀔 수 있다.
        #: ★ 제품이 이미 쓰는 `snapshot_service.verify_raw` 를 쓴다 — 같은 판정을 두 벌로
        #:   만들면 한쪽만 고쳐지는 날이 오고, 그날 이 경로만 조용히 헐거워진다.
        raw_path = str(row.get("raw_path", ""))
        want = str(row.get("checksum", "") or "")
        if verify_fingerprint and want:
            if not svc.verify_raw(raw_path, want):
                raise SealedDatasetError(
                    f"{key}: 인증판({sid})의 원본 체크섬이 다릅니다 — 인증한 그 파일이 "
                    f"아닙니다. 디스크의 파일이 바뀌었거나 다른 파일을 가리킵니다.")
        rows = _read_rows(raw_path, key=key)
        out[key] = [{**r, "__snapshot_id__": sid} for r in rows]
    return out


def active_seals(store: Any, *, instance_id: str, contract_keys: Sequence[str]
                 ) -> Dict[str, str]:
    """이 인스턴스의 계약키별 **가장 최근 인증판** id.

    ★ 봉인 목록을 만드는 편의 함수다. 관계 승인 때 봉인한 판이 따로 있으면 그것을 쓴다 —
      이 함수는 「지금 최신」이지 「승인 때 봉인된 것」이 아니다.
    ⚠️ 그 둘을 섞으면 승인 이후 올라온 판으로 계산하면서 옛 승인을 근거로 삼게 된다.
    """
    latest: Dict[str, Dict[str, Any]] = {}
    for row in store.list_snapshots(instance_id):
        key = str(row.get("dataset_contract_key", ""))
        if key not in contract_keys or not m.is_certified(row.get("state", "")):
            continue
        prev = latest.get(key)
        at = str(row.get("certified_at", "") or row.get("created_at", ""))
        if prev is None or at > str(prev.get("certified_at", "")
                                    or prev.get("created_at", "")):
            latest[key] = row
    # 보류된 최신판을 빼고 옛 판으로 조용히 폴백하지 않는다.
    for row in latest.values():
        try:
            usage_policy.require_usable(store, row)
        except usage_policy.UsageHoldError as exc:
            raise SealedDatasetError(str(exc)) from exc
    return {k: str(v["snapshot_id"]) for k, v in sorted(latest.items())}
