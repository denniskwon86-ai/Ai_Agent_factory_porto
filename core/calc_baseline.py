"""★★★ [G2 M0-3.2b] **계산 기준선** — 배분·인식규칙·기준 인식일을 한 봉인으로.

## 무엇을 정본화하나

계산 요청에는 정본 자료에 **없는** 값 셋이 들어간다:

    sales_allocation        생산계획 → 판매행 배분   (관계 `FULFILLS_SALES` 의 근거)
    recognition_span_days   매출 인식 기간
    baseline_recognition    기준선 예상 인식일       (이연을 재는 기준점)

⚠️⚠️ 앞 판은 이 셋을 **호출자가 넣었다.** 지문에 들어가긴 했지만 「어디서 왔는가」가
  없으면 근거가 아니다 — 이 저장소가 반복해서 지운 자기진술 패턴이다.

★ 그래서 셋을 **하나의 기준선**으로 묶어 저장소에 봉인하고, 그 지문을 원장 사건이
  승인한다. 계산은 봉인된 기준선에서만 값을 읽는다.

    저장소 `baseline_builds`   내용 + 지문
      ↕
    원장 `CALC_BASELINE_SEALED`  대상 = 그 지문

## 왜 셋을 한 봉인으로 묶는가

⚠️ 따로 두면 「배분은 새 것, 인식 규칙은 옛 것」 같은 조합이 생기고, 그 조합은 아무도
  승인한 적이 없다. 셋은 **함께 검토되고 함께 승인**되어야 한다 — 매출 이연은 셋의
  곱이기 때문이다.

## 봉인 이후

⚠️ 내용을 고치면 지문이 바뀌고 승인은 **자동으로 죽는다.** 그것이 노림수다 —
  「같은 기준선 다른 값」이 승인을 물려받지 못한다.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.data_preparation import store as dp

#: 원장 사건. ⚠️ 대상은 **기준선 내용의 지문**이다 — build_id 가 아니다.
#: build_id 를 대상으로 삼으면 내용을 고쳐도 승인이 살아남는다.
BASELINE_SEALED = "CALC_BASELINE_SEALED"
BASELINE_REVOKED = "CALC_BASELINE_REVOKED"
BASELINE_SUBJECT = "calc_baseline"

ACTIVE = "active"
REVOKED = "revoked"


class BaselineError(Exception):
    """기준선을 만들거나 읽을 수 없다. ⚠️ 「빈 기준선으로 계산해 본다」를 하지 않는다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_fingerprint(*, tenant_id: str, entity_mode: str, scope_node_id: str,
                        instance_id: str, sales_allocation: Mapping[str, str],
                        recognition_span_days: Mapping[str, Any],
                        baseline_recognition: Mapping[str, str]) -> str:
    """기준선 **내용**의 지문. 정렬해서 굳힌다.

    ⚠️ 문맥 세 값과 인스턴스를 넣는다 — 같은 배분이라도 **다른 조직의 것**이면 다른
      기준선이다."""
    return dp.fingerprint({
        "tenant_id": tenant_id, "entity_mode": entity_mode,
        "scope_node_id": scope_node_id, "instance_id": instance_id,
        "sales_allocation": {str(k): str(v) for k, v in sorted(sales_allocation.items())},
        "recognition_span_days": {str(k): str(v)
                                  for k, v in sorted(recognition_span_days.items())},
        "baseline_recognition": {str(k): str(v)
                                 for k, v in sorted(baseline_recognition.items())},
    })


def seal(store: Any, *, instance_id: str, tenant_id: str, entity_mode: str,
         scope_node_id: str, sales_allocation: Mapping[str, str],
         recognition_span_days: Mapping[str, Any],
         baseline_recognition: Mapping[str, str], actor: str, rationale: str
         ) -> Dict[str, Any]:
    """계산 기준선을 **저장소에 봉인하고 원장에 승인 사건을 남긴다.**

    ⚠️ 세 값이 서로 맞아야 한다 — 배분에 있는 판매행은 인식 기간과 기준 인식일도
      있어야 한다. 하나라도 없으면 계산이 그 행을 `missing_baseline` 으로 드러내고,
      그때는 **봉인 자체가 반쪽**이었던 것이다.
    ⚠️ 사유 없이 봉인하지 않는다 — 「왜 이 배분인가」에 답할 수 없는 기준선은 나중에
      아무도 뒤집을 수 없다."""
    if not str(actor or "").strip():
        raise BaselineError("봉인 행위자가 필요합니다.")
    if not str(rationale or "").strip():
        raise BaselineError(
            "봉인 사유가 필요합니다 — 「왜 이 배분·기준선인가」에 답할 수 없으면 나중에 "
            "아무도 뒤집을 수 없습니다.")
    if not sales_allocation:
        raise BaselineError(
            "생산-판매 배분이 비어 있습니다 — 빈 배분을 봉인하면 계산은 모든 판매행을 "
            "「기준선 없음」으로 답하고, 그것이 「영향 없음」으로 읽힙니다.")
    missing: List[str] = []
    for sales_line in sorted(sales_allocation):
        if str(recognition_span_days.get(sales_line, "") or "").strip() == "":
            missing.append(f"{sales_line}.recognition_span_days")
        if str(baseline_recognition.get(sales_line, "") or "").strip() == "":
            missing.append(f"{sales_line}.baseline_recognition")
    if missing:
        raise BaselineError(
            f"기준선이 반쪽입니다: {missing} — 배분에 있는 판매행은 인식 기간과 기준 "
            f"인식일이 함께 있어야 합니다(셋은 함께 검토되고 함께 승인됩니다).")

    fp = content_fingerprint(
        tenant_id=tenant_id, entity_mode=entity_mode, scope_node_id=scope_node_id,
        instance_id=instance_id, sales_allocation=sales_allocation,
        recognition_span_days=recognition_span_days,
        baseline_recognition=baseline_recognition)

    #: ★ 원장 사건을 **먼저** 남긴다. 저장소 행만 있고 승인이 없으면 그 행은 근거가
    #:   없는데, 반대(승인은 있고 행이 없음)는 조회에서 곧바로 드러난다.
    from core.decision_ledger import decision_ledger
    try:
        ev = decision_ledger.append(
            event_type=BASELINE_SEALED, subject_type=BASELINE_SUBJECT, subject_id=fp,
            actor_type="user", actor_id=actor, decision="SEALED", rationale=rationale,
            evidence_refs=[f"instance:{instance_id}",
                           f"allocation_count:{len(sales_allocation)}"],
            tenant_id=tenant_id, enterprise_scope_id="", entity_mode=entity_mode)
    except Exception as e:
        raise BaselineError(f"기준선 승인 사건을 원장에 남기지 못했습니다: {e}")

    build_id = f"bl_{uuid.uuid4().hex[:14]}"
    detail = {"sales_allocation": dict(sales_allocation),
              "recognition_span_days": {k: str(v)
                                        for k, v in recognition_span_days.items()},
              "baseline_recognition": dict(baseline_recognition),
              "ledger_event_id": str(ev.get("event_id", "")),
              "sealed_by": actor}
    now = _now()
    with store.transaction() as conn:
        #: ⚠️ 같은 인스턴스의 옛 기준선은 **내린다.** 둘이 살아 있으면 어느 것으로
        #:   계산했는지 말할 수 없다.
        conn.execute("UPDATE baseline_builds SET status=?, updated_at=? "
                     "WHERE instance_id=? AND status=?",
                     (REVOKED, now, instance_id, ACTIVE))
        conn.execute(
            "INSERT INTO baseline_builds (build_id, instance_id, status, fingerprint,"
            " detail_json, tenant_id, scope_node_id, entity_mode, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (build_id, instance_id, ACTIVE, fp,
             json.dumps(detail, ensure_ascii=False, sort_keys=True),
             tenant_id, scope_node_id, entity_mode, now, now))
    return {"build_id": build_id, "fingerprint": fp,
            "ledger_event_id": str(ev.get("event_id", ""))}


def active(store: Any, *, instance_id: str, tenant_id: str, entity_mode: str,
           scope_node_id: str) -> Optional[Dict[str, Any]]:
    """살아 있는 기준선. **승인이 지금도 유효한 것만** 돌려준다.

    ★★★ 확인하는 것:
      ① 저장소에 `active` 행이 있는가
      ② 문맥이 같은가 — 다른 조직의 기준선으로 계산하지 않는다
      ③ **내용 지문이 저장된 지문과 같은가** — 행을 직접 고쳤으면 봉인이 깨진 것이다
      ④ 원장 사건이 실재하고 **철회되지 않았는가**

    ⚠️ 못 읽으면 던진다. 「기준선 없음」으로 접으면 계산이 `BLOCKED` 로 답하고, 실제로는
      **읽지 못한 것**인데 「아직 준비 안 됨」으로 보인다."""
    try:
        with store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM baseline_builds WHERE instance_id=? AND status=? "
                "ORDER BY created_at DESC LIMIT 1", (instance_id, ACTIVE)).fetchone()
    except sqlite3.Error as e:
        raise BaselineError(f"기준선을 읽지 못했습니다: {e}")
    if row is None:
        return None
    r = dict(row)
    #: ② 문맥.
    if (str(r.get("tenant_id", "")) != tenant_id
            or str(r.get("entity_mode", "")) != entity_mode
            or str(r.get("scope_node_id", "")) != scope_node_id):
        raise BaselineError(
            f"기준선({r.get('build_id')})이 이 문맥의 것이 아닙니다 — 다른 조직의 "
            f"배분으로 계산하지 않습니다.")
    try:
        detail = json.loads(r.get("detail_json") or "{}")
    except json.JSONDecodeError as e:
        raise BaselineError(f"기준선 내용을 읽지 못했습니다: {e}")

    #: ③ 내용 지문 재계산. **행을 직접 고쳤으면 여기서 드러난다.**
    recomputed = content_fingerprint(
        tenant_id=tenant_id, entity_mode=entity_mode, scope_node_id=scope_node_id,
        instance_id=instance_id,
        sales_allocation=detail.get("sales_allocation") or {},
        recognition_span_days=detail.get("recognition_span_days") or {},
        baseline_recognition=detail.get("baseline_recognition") or {})
    if recomputed != str(r.get("fingerprint", "")):
        raise BaselineError(
            f"기준선({r.get('build_id')})의 내용이 봉인 지문과 다릅니다 — 행을 직접 "
            f"고쳤거나 자료가 어긋났습니다. 이 기준선으로 계산하지 않습니다.")

    #: ④ 원장 승인이 살아 있는가.
    from core.decision_ledger import DecisionLedgerError, decision_ledger
    event_id = str(detail.get("ledger_event_id", "") or "")
    if not event_id:
        raise BaselineError(
            f"기준선({r.get('build_id')})에 승인 사건이 없습니다 — 봉인되지 않은 "
            f"기준선으로 계산하지 않습니다.")
    try:
        ev = decision_ledger.get_event_strict(event_id)
        if not ev:
            raise BaselineError(
                f"기준선 승인 사건({event_id})이 없습니다 — 승인 없는 기준선입니다.")
        if str(ev.get("event_type", "")) != BASELINE_SEALED \
                or str(ev.get("subject_type", "")) != BASELINE_SUBJECT:
            raise BaselineError(
                f"사건({event_id})은 기준선 봉인이 아닙니다({ev.get('event_type')}).")
        if str(ev.get("subject_id", "")) != recomputed:
            raise BaselineError(
                f"기준선 승인 사건({event_id})이 이 내용을 가리키지 않습니다 — 내용이 "
                f"바뀌었으면 다시 봉인해야 합니다.")
        if decision_ledger.has_invalidating_child(event_id, (BASELINE_REVOKED,)):
            return None                    # 철회됐다 — 「없음」이 맞다(장애가 아니다)
    except DecisionLedgerError as e:
        raise BaselineError(f"기준선 승인을 확인하지 못했습니다: {e}")

    return {"build_id": str(r.get("build_id", "")), "fingerprint": recomputed,
            "ledger_event_id": event_id,
            "sales_allocation": dict(detail.get("sales_allocation") or {}),
            "recognition_span_days": dict(detail.get("recognition_span_days") or {}),
            "baseline_recognition": dict(detail.get("baseline_recognition") or {})}


def revoke(store: Any, *, build_id: str, actor: str, reason: str) -> bool:
    """기준선을 철회한다. **원장에 자식 사건을 남기고** 저장소 행을 내린다.

    ⚠️ 행만 내리면 원장에는 봉인만 남아 여전히 유효해 보인다 — 소유권 결속에서 이미
      고친 유형이다."""
    if not str(actor or "").strip():
        raise BaselineError("철회에도 행위자가 필요합니다.")
    if not str(reason or "").strip():
        raise BaselineError("철회 사유가 필요합니다.")
    with store.transaction() as conn:
        row = conn.execute("SELECT * FROM baseline_builds WHERE build_id=? AND status=?",
                           (build_id, ACTIVE)).fetchone()
        if row is None:
            return False
        r = dict(row)
    detail = json.loads(r.get("detail_json") or "{}")
    from core.decision_ledger import decision_ledger
    try:
        decision_ledger.append(
            event_type=BASELINE_REVOKED, subject_type=BASELINE_SUBJECT,
            subject_id=str(r.get("fingerprint", "")), actor_type="user", actor_id=actor,
            decision="REVOKED", rationale=reason,
            parent_event_id=str(detail.get("ledger_event_id", "")),
            tenant_id=str(r.get("tenant_id", "")),
            entity_mode=str(r.get("entity_mode", "")))
    except Exception as e:
        raise BaselineError(f"기준선 철회 사건을 원장에 남기지 못했습니다: {e}")
    now = _now()
    with store.transaction() as conn:
        return conn.execute(
            "UPDATE baseline_builds SET status=?, updated_at=? WHERE build_id=? "
            "AND status=?", (REVOKED, now, build_id, ACTIVE)).rowcount == 1
