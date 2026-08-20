"""★★★ 인증판 → **업무 객체 범위 색인.** (§7 3단계 · 2026-08-20)

## 무엇을 잇는가

온톨로지 계약의 `dataset` 객체 id 는 **업무 레코드 ID** 다:

    dataset:shipment           → SHP-000001
    dataset:inventory-snapshot → STK-20260811-MAT-0001-WH01

⚠️⚠️ **인증판 ID(`ds_…`)가 아니다.** 특히 `INV-01` 은 자기 열쇠 이름이 하필
  `snapshot_id` 라서 더 헷갈린다 — 그 값은 `STK-…` 이고, 인증판은 `ds_…` 다.
  첫 구현은 업무 레코드 ID 를 그대로 `get_snapshot()` 에 넣었고, **영영 못 찾는데**
  결과가 `None` 이라 「범위 밖」과 구분되지 않았다.

그런데 범위(`tenant_id`·`entity_mode`·`scope_node_id`)는 **인증판이** 들고 있다.
이 표가 그 사이를 잇는다.

## ⚠️ 본문을 복제하지 않는다

여기 있는 것은 「어느 판의 어느 행에서 왔고 그 범위가 무엇인가」뿐이다. 본문을 옮기면
두 벌이 되고, 두 벌은 언젠가 갈라진다. 그때 어느 쪽이 사실인지 아무도 모른다.

## 판 고르기 — 「그냥 최신」 금지

    as_of 이하에서 유효한 DEMO_CERTIFIED 판 중 가장 최근
    같은 시점 후보가 둘이면 → AMBIGUOUS (503)

⚠️⚠️ 「최신을 고르면 되지」가 가장 위험하다. **과거 시점 질의에 오늘의 답**을 준다.
  동점을 임의로 고르는 것은 더 나쁘다 — 같은 질문의 답이 실행마다 달라지고,
  재실행 지문이 흔들린다.

## 옛 판은 지우지 않는다

새 인증판이 오면 **새 줄**이 생긴다. 옛 줄은 남는다 — 그것이 `as_of` 질의의 전제다.
옛 판을 지우면 과거 시점 질의가 오늘의 답을 내게 되고, 그것은 조용한 거짓말이다.

LLM 0콜.
"""
from __future__ import annotations

import csv
import io
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from core.data_preparation import models as m

#: ★★★ 계약키 → (namespace, object_type, 업무 레코드 ID 열). **닫힌 표다.**
#:
#: ⚠️ 여기 없는 계약키는 색인하지 않는다 — 그것이 «온톨로지 MVP 대상은 다섯뿐» 이라는
#:   결정이 코드에 남는 자리다. 넓히려면 Resolver·관계·계산이 함께 준비돼야 한다.
#: ⚠️ `object_type` 은 계약의 **하이픈 표기**를 그대로 쓴다(`purchase-order-line`).
#:   여기서 표기를 바꾸면 계약과 런타임이 서로 다른 이름을 부르게 된다.
CONTRACT_OBJECTS: Dict[str, Tuple[str, str, str]] = {
    "PRC-02": ("dataset", "purchase-order-line", "po_line_id"),
    "LOG-02": ("dataset", "shipment", "shipment_id"),
    #: ⚠️ 이 열의 이름이 `snapshot_id` 다. **인증판 ID 와 다른 것이다.**
    "INV-01": ("dataset", "inventory-snapshot", "snapshot_id"),
    "MFG-01": ("dataset", "production-plan-line", "plan_line_id"),
    "SLS-01": ("dataset", "sales-line", "sales_line_id"),
}


class ScopeIndexError(m.DataPreparationError):
    """색인을 세우지 못했다. ⚠️ 인증을 통과시키지 않는다."""


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rows_from_raw(raw_path: str, expected_checksum: str) -> Tuple[List[dict], List[str]]:
    """보관된 원본을 되읽는다. ★ **지문을 먼저 확인한다.**

    ⚠️⚠️ 색인은 「인증한 바로 그 바이트」에서 나와야 한다. 지문을 안 보고 읽으면
      파일이 바뀐 뒤에도 색인이 생기고, 그 색인은 **인증하지 않은 자료**를 가리킨다."""
    from core.data_preparation import snapshot_service as svc

    if not raw_path or not os.path.exists(raw_path):
        raise ScopeIndexError(f"인증판의 원본을 찾지 못했습니다: {raw_path or '(경로 없음)'}")
    if not svc.verify_raw(raw_path, expected_checksum):
        raise ScopeIndexError(
            "인증판의 원본 지문이 맞지 않습니다 — 인증한 그 파일이 아닙니다.")
    with open(raw_path, "rb") as f:
        text = f.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader], list(reader.fieldnames or [])


def plan(snapshot: Dict[str, Any]) -> List[tuple]:
    """색인할 줄들을 **미리 계산한다.** 아직 아무것도 쓰지 않는다.

    ★★★ 인증 **전에** 부른다. 여기서 막히면 인증 자체가 서지 않으므로 「인증은 됐는데
      색인이 없는 판」이 생길 수 없다.
    ⚠️ 반대 순서(인증 먼저)로 하면 사고가 질의 시점에 터진다 — 그때는 고칠 사람이
      그 자리에 없다.

    ★ 계약키가 `CONTRACT_OBJECTS` 에 없으면 **빈 목록**이다(설계상 대상 아님).
    ⚠️ 대상인데 세우지 못하면 `ScopeIndexError` — 조용히 0줄로 넘어가지 않는다."""
    key = str(snapshot.get("dataset_contract_key", "") or "")
    target = CONTRACT_OBJECTS.get(key)
    if target is None:
        return []
    namespace, object_type, id_column = target

    rows, columns = rows_from_raw(str(snapshot.get("raw_path", "") or ""),
                                  str(snapshot.get("checksum", "") or ""))
    if id_column not in columns:
        raise ScopeIndexError(
            f"{key} 에 «{id_column}» 열이 없습니다 — 업무 객체 ID 를 정할 수 없습니다.")

    snapshot_id = str(snapshot.get("snapshot_id", ""))
    now = _now()
    seen: Dict[str, int] = {}
    payload = []
    for line_no, row in enumerate(rows, start=2):        # 2 = 머리글 다음 줄
        object_id = str(row.get(id_column, "") or "").strip()
        if not object_id:
            raise ScopeIndexError(
                f"{key} {line_no}행: «{id_column}» 이 비어 있습니다 — "
                f"범위를 잇지 못하는 행은 색인할 수 없습니다.")
        if object_id in seen:
            #: ⚠️ 같은 판 안에서 업무 ID 가 겹치면 **어느 행이 그 객체인지** 알 수 없다.
            raise ScopeIndexError(
                f"{key}: «{object_id}» 가 {seen[object_id]}행과 {line_no}행에 겹칩니다.")
        seen[object_id] = line_no

        tenant = str(row.get("tenant_id", "") or "").strip()
        scope = str(row.get("scope_node_id", "") or "").strip()
        if not tenant or not scope:
            #: ★ 범위 없는 행은 권한 필터에서 «미기록» 이 되어 통제 밖에 놓인다.
            raise ScopeIndexError(
                f"{key} {line_no}행: 범위(tenant·scope_node)가 없습니다.")
        if tenant != str(snapshot.get("tenant_id", "")):
            #: ⚠️⚠️ 행의 tenant 와 인증판의 tenant 가 다르면 **남의 조직 자료**가 우리
            #:   범위로 들어온다. 행 수는 그대로여서 눈으로는 보이지 않는다.
            raise ScopeIndexError(
                f"{key} {line_no}행: tenant 가 인증판과 다릅니다 "
                f"({tenant} ≠ {snapshot.get('tenant_id')}).")

        payload.append((namespace, object_type, object_id, snapshot_id, key,
                        f"line={line_no};{id_column}={object_id}",
                        tenant, scope,
                        str(snapshot.get("entity_mode", "")),
                        str(snapshot.get("data_kind", "")),
                        "", now))                        # certified_at 은 기록 때 채운다
    return payload


def write(store: Any, payload: List[tuple], certified_at: str) -> int:
    """계산해 둔 줄들을 기록한다. ★ 인증 **직후**에 부른다.

    ⚠️ `certified_at` 은 인증판이 실제로 받은 값을 그대로 넣는다 — 여기서 «지금» 을
      쓰면 `as_of` 로 판을 고를 때 **몇 초씩 어긋난다.**"""
    if not payload:
        return 0
    stamped = [row[:10] + (str(certified_at or ""), row[11]) for row in payload]
    with store.transaction() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO object_scope_index ("
            "namespace, object_type, object_id, snapshot_id, dataset_contract_key,"
            "row_evidence, tenant_id, scope_node_id, entity_mode, data_kind,"
            "certified_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", stamped)
    return len(stamped)


def versions(store: Any, namespace: str, object_type: str,
             object_id: str) -> List[Dict[str, Any]]:
    """한 객체의 **판 이력.** 오래된 것부터. ⚠️ 옛 판을 지우지 않으므로 여러 줄이 나온다."""
    with store.transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM object_scope_index WHERE namespace=? AND object_type=? "
            "AND object_id=? ORDER BY certified_at, snapshot_id",
            (namespace, object_type, object_id)).fetchall()
    return [dict(r) for r in rows]


#: 조회 결과의 종류. ★ 런타임의 `ObjectResolution` 상태와 **같은 어휘**를 쓴다 —
#: 여기서 다른 이름을 쓰면 옮겨 담는 자리에서 뜻이 바뀐다.
FOUND, NOT_FOUND, AMBIGUOUS = "FOUND", "NOT_FOUND", "AMBIGUOUS"


def lookup(store: Any, namespace: str, object_type: str, object_id: str,
           as_of: str = "") -> Tuple[str, Optional[Dict[str, Any]], Tuple[str, ...]]:
    """`as_of` 시점의 판 하나를 고른다 → `(상태, 줄, 후보들)`.

    ★★★ **「그냥 최신」을 쓰지 않는다.** `as_of` 이하에서 인증된 판 중 가장 최근을
      고른다. 과거 시점 질의는 그때의 답을 그대로 내야 한다.

    ⚠️⚠️ 같은 인증 시각의 판이 둘이면 **고르지 않는다.** 임의로 고르면 같은 질문의
      답이 실행마다 달라지고, 재실행 지문이 흔들린다 — 그러면 「이 숫자는 무엇으로
      만들었나」에 답할 수 없다.

    ⚠️ `as_of` 가 비면 「지금」이다. 그때도 최신이 아니라 **전 구간 중 가장 최근**을
      고르므로 결과는 같지만, 규칙은 하나로 유지된다."""
    rows = versions(store, namespace, object_type, object_id)
    if not rows:
        return NOT_FOUND, None, ()
    cutoff = str(as_of or "").strip()
    if cutoff:
        rows = [r for r in rows if str(r.get("certified_at") or "") <= cutoff]
        if not rows:
            #: ★ 그 시점에는 **아직 인증되지 않았다.** 「없다」와 같은 답이지만 사유가 다르다.
            return NOT_FOUND, None, ()
    newest = str(rows[-1].get("certified_at") or "")
    tied = [r for r in rows if str(r.get("certified_at") or "") == newest]
    if len(tied) > 1:
        return AMBIGUOUS, None, tuple(str(r.get("snapshot_id")) for r in tied)
    return FOUND, rows[-1], ()


def bound_to(store: Any, snapshot_id: str) -> int:
    """그 인증판에 묶인 객체 수. ⚠️ 0이면 색인이 안 세워진 판이다."""
    with store.transaction() as conn:
        return int(conn.execute(
            "SELECT COUNT(*) FROM object_scope_index WHERE snapshot_id=?",
            (snapshot_id,)).fetchone()[0])


def evidence_bound(store: Any, evidence_refs: Any, snapshot_id: str) -> Tuple[bool, str]:
    """근거들이 **그 인증판에 묶여 있는가.** `(참/거짓, 사유)`.

    ★ 관계 승인 때 「양 끝점과 근거가 승인된 판에 결속됐는가」를 보는 자리다.
    ⚠️ 근거가 다른 판을 가리키면 「그때 승인한 그 자료」가 아니게 된다."""
    refs = evidence_refs
    if isinstance(refs, str):
        try:
            refs = json.loads(refs or "[]")
        except Exception:
            return False, "근거 목록을 읽지 못했습니다."
    refs = [str(r).strip() for r in (refs or []) if str(r).strip()]
    if not refs:
        return False, "근거가 없습니다 — 근거 없는 관계는 승인하지 않습니다."
    with store.transaction() as conn:
        known = {str(r[0]) for r in conn.execute(
            "SELECT DISTINCT dataset_contract_key FROM object_scope_index "
            "WHERE snapshot_id=?", (snapshot_id,)).fetchall()}
    if not known:
        return False, f"인증판 {snapshot_id} 에 색인이 없습니다."
    #: 근거는 `PRC-02.po_line_id` 처럼 **계약키로 시작**한다.
    missing = [r for r in refs if r.split(".", 1)[0] not in known]
    if missing:
        return False, f"이 판에 없는 근거입니다: {missing[:3]}"
    return True, ""
