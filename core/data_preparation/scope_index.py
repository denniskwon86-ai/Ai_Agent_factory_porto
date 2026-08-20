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


#: ★★★ [2026-08-21] **인증판은 «전체판» 이다.** 각 CSV 는 그 시점의 전 목록이다.
#:
#: ⚠️⚠️ 그래서 **새 판에서 빠진 객체는 사라진 것**이다. 옛 판의 줄이 남아 있다고 해서
#:   그 객체가 아직 있는 것처럼 답하면, 폐기된 선적이 영원히 살아 있게 된다.
#: ⚠️ 증분판을 쓰게 되면 이 상수부터 바꾸고 삭제 정책을 다시 정해야 한다 —
#:   의미를 안 적어 두면 다음 사람이 «남아 있으니 유효하다» 로 읽는다.
SNAPSHOT_SEMANTICS = "FULL"


def _utc(text: Any) -> str:
    """시각을 **UTC 로 정규화**한 문자열. 못 읽으면 빈 문자열.

    ★★★ [2026-08-21 P1] 종전에는 시각을 **문자열 그대로** 비교했다. 그러면
      `2026-06-01T00:00:00Z` 와 `2026-06-01T09:00:00+09:00` 이 **같은 순간인데 다르게**
      정렬되고, 소수초가 붙으면 또 달라진다.
    ⚠️ 그 어긋남은 조용하다 — `as_of` 가 몇 시간씩 밀려도 답은 그럴듯하게 나온다."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    from datetime import datetime, timezone

    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        #: ⚠️ 시간대가 없는 값은 **UTC 로 본다.** 지역시로 읽으면 9시간이 조용히 밀린다.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


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
    with store.transaction() as conn:
        return write_conn(conn, payload, certified_at)


def write_conn(conn: Any, payload: List[tuple], certified_at: str) -> int:
    """이미 열린 트랜잭션 위에서 기록한다.

    ★★★ [2026-08-21 P1] 인증 상태 전환과 **같은 트랜잭션**에서 돌기 위해 있다.
    ⚠️⚠️ 나누면 「인증됐는데 색인이 없는」 구간이 아무리 짧아도 생기고, 그 사이에 읽은
      쪽은 승인된 관계의 끝점에서 **503** 을 만난다 — 아무도 잘못하지 않았는데."""
    if not payload:
        return 0
    stamped = [row[:10] + (str(certified_at or ""), row[11]) for row in payload]
    if True:
        conn.executemany(
            "INSERT OR REPLACE INTO object_scope_index ("
            "namespace, object_type, object_id, snapshot_id, dataset_contract_key,"
            "row_evidence, tenant_id, scope_node_id, entity_mode, data_kind,"
            "certified_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", stamped)
    return len(stamped)


def versions(store: Any, namespace: str, object_type: str, object_id: str,
             tenant_id: str, entity_mode: str,
             include_dead: bool = False) -> List[Dict[str, Any]]:
    """한 객체의 **판 이력.** 오래된 것부터(UTC 기준).

    ★★★ [2026-08-21 P0] `tenant_id`·`entity_mode` 로 **정체성을 가른다.**

    ⚠️⚠️ 종전에는 `(namespace, object_type, object_id)` 만으로 찾았다. 그런데 업무
      레코드 ID 는 회사마다 겹친다 — `SHP-000001` 은 어느 회사에나 있다. 그러면 **다른
      회사의 최신 줄이 우리 줄을 가리거나** 동점을 만들어 `AMBIGUOUS` 가 된다.
    ★ 이것은 **권한 판정이 아니라 정체성 분리**다. 다른 tenant 의 `SHP-000001` 은
      「내가 볼 수 없는 우리 배」가 아니라 **아예 다른 배**다. 그래서 PDP 보다 앞선다.
    ★ `entity_mode` 도 같다 — 실적의 `SHP-000001` 과 시나리오의 것은 다른 객체다.

    ★★★ [2026-08-21 P0] **살아 있는 인증판만 본다.**
    ⚠️⚠️ 색인 줄은 인증판이 철회(`REVOKED`)돼도 남는다. 상태를 안 보면 **폐기된 판의
      객체가 영원히 `FOUND`** 로 답한다 — 철회가 아무 일도 하지 않는 셈이 된다."""
    sql = ("SELECT i.*, s.state AS snapshot_state FROM object_scope_index i "
           "JOIN dataset_snapshots s ON s.snapshot_id = i.snapshot_id "
           "WHERE i.namespace=? AND i.object_type=? AND i.object_id=? "
           "AND i.tenant_id=? AND i.entity_mode=?")
    args = [namespace, object_type, object_id, tenant_id, entity_mode]
    if not include_dead:
        sql += " AND s.state=?"
        args.append(m.DEMO_CERTIFIED)
    with store.transaction() as conn:
        rows = [dict(r) for r in conn.execute(sql, tuple(args)).fetchall()]
    #: ★ 정렬은 **UTC 로 정규화한 값**으로 한다 — 문자열 정렬은 표기가 섞이면 어긋난다.
    rows.sort(key=lambda r: (_utc(r.get("certified_at")), str(r.get("snapshot_id"))))
    return rows


def current_snapshot(store: Any, dataset_contract_key: str, tenant_id: str,
                     entity_mode: str, as_of_utc: str = "") -> Optional[str]:
    """그 시점의 **현재 인증판** id. 없으면 `None`.

    ★ 인증판이 «전체판» 이므로(§`SNAPSHOT_SEMANTICS`), 「지금 유효한 목록」은 이 판
      하나다. 여기에 없는 객체는 **빠진 것**이다."""
    with store.transaction() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT i.snapshot_id, s.certified_at FROM ("
            "  SELECT DISTINCT snapshot_id FROM object_scope_index "
            "  WHERE dataset_contract_key=? AND tenant_id=? AND entity_mode=?) i "
            "JOIN dataset_snapshots s ON s.snapshot_id = i.snapshot_id "
            "WHERE s.state=?",
            (dataset_contract_key, tenant_id, entity_mode, m.DEMO_CERTIFIED)).fetchall()]
    live = [(_utc(r["certified_at"]), str(r["snapshot_id"])) for r in rows]
    if as_of_utc:
        live = [x for x in live if x[0] and x[0] <= as_of_utc]
    if not live:
        return None
    live.sort()
    return live[-1][1]


#: 조회 결과의 종류. ★ 런타임의 `ObjectResolution` 상태와 **같은 어휘**를 쓴다 —
#: 여기서 다른 이름을 쓰면 옮겨 담는 자리에서 뜻이 바뀐다.
FOUND, NOT_FOUND, AMBIGUOUS = "FOUND", "NOT_FOUND", "AMBIGUOUS"
#: 객체는 아는데 **그 시점에는 어느 살아 있는 인증판에도 묶여 있지 않다.**
#: ⚠️ 「그런 것이 없다」와 다르다 — 있는데 아직 인증 전이거나, 폐기됐거나, 새 판에서
#:   빠진 것이고, 사람이 할 일도 각각 다르다.
UNBOUND = "UNBOUND"


def lookup(store: Any, namespace: str, object_type: str, object_id: str,
           tenant_id: str, entity_mode: str,
           as_of: str = "") -> Tuple[str, Optional[Dict[str, Any]], Tuple[str, ...]]:
    """`as_of` 시점의 판 하나를 고른다 → `(상태, 줄, 후보들)`.

    ## 고르는 규칙

        as_of 이하에서 인증된 **살아 있는** 판 중 가장 최근
        같은 시각의 후보가 둘이면 → AMBIGUOUS (아무거나 고르지 않는다)
        그 판이 **현재 인증판이 아니면** → UNBOUND (새 판에서 빠진 객체다)

    ⚠️⚠️ 「그냥 최신」은 **과거 시점 질의에 오늘의 답**을 준다.
    ⚠️⚠️ 동점을 임의로 고르면 같은 질문의 답이 실행마다 달라지고, 재실행 지문이 흔들린다.
    ⚠️⚠️ 새 판에서 빠진 객체를 옛 줄로 답하면 **폐기된 선적이 영원히 살아 있다.**

    ★ 「없다」와 「묶여 있지 않다」를 가른다 — 앞엣것은 오타를 의심하고, 뒤엣것은
      인증 일정·철회 이력을 본다."""
    live = versions(store, namespace, object_type, object_id, tenant_id, entity_mode)
    if not live:
        #: ★ 죽은 줄까지 세어 「아예 없다」와 「있었는데 지금은 아니다」를 가른다.
        any_row = versions(store, namespace, object_type, object_id, tenant_id,
                           entity_mode, include_dead=True)
        if any_row:
            return UNBOUND, None, ()
        return NOT_FOUND, None, ()

    cutoff = _utc(as_of)
    if str(as_of or "").strip() and not cutoff:
        #: ⚠️ 읽을 수 없는 시점으로 «지금» 을 대신하지 않는다 — 조용히 다른 질문에 답하게 된다.
        raise ScopeIndexError(f"as_of 를 시각으로 읽지 못했습니다: {as_of!r}")
    if cutoff:
        live = [r for r in live if _utc(r.get("certified_at")) <= cutoff]
        if not live:
            #: ★★★ 그 시점에는 **아직 인증되지 않았다.** 「그런 객체가 없다」가 아니다.
            return UNBOUND, None, ()

    newest = _utc(live[-1].get("certified_at"))
    tied = [r for r in live if _utc(r.get("certified_at")) == newest]
    if len(tied) > 1:
        return AMBIGUOUS, None, tuple(str(r.get("snapshot_id")) for r in tied)

    chosen = live[-1]
    #: ★★★ 전체판이므로 **현재 판에 없으면 빠진 것**이다.
    current = current_snapshot(store, str(chosen.get("dataset_contract_key", "")),
                               tenant_id, entity_mode, cutoff)
    if current and str(chosen.get("snapshot_id")) != current:
        return UNBOUND, None, ()
    return FOUND, chosen, ()


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
