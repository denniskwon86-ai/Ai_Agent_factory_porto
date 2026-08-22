"""★★★ [G2 M0-3.2] **서버가 계산 요청을 산출하고 실제 원장으로 검증한다.**

## 왜 이 층이 필요한가

`core/path_calculation.py` 는 요청을 **받아서** 관문을 지난다. 그런데 그 요청 안의
값들이 호출자가 적어 보낸 것이면, 관문은 **호출자의 주장을 검사**하는 셈이다:

    required_relation_ids   「이 경로에 관계가 셋이다」        ← 누가 정했나
    relation_approvals      「그 셋이 승인됐다」              ← 누가 확인했나
    sealed_snapshots        「이 판을 봉인했다」              ← 누가 봉인했나
    baseline_id             「이 기준선을 썼다」              ← 어디서 왔나
    sales_allocation        「이 배분이 승인됐다」            ← 누가 승인했나

⚠️⚠️ 이것이 이 저장소가 반복해서 지운 **자기진술** 패턴이다(`calc_binding`,
  「승인됐다고 스스로 적은 결속」). 값이 지문에 들어가도 **어디서 왔는지**가 없으면
  근거가 아니다.

★ 그래서 서버가 산출한다:

    온톨로지 경로(nodes·edges)
      → 관계 ID 집합            (경로에서 나온다)
      → 승인 사건               (원장에서 찾는다)
      → 봉인 판                 (저장소의 인증판에서 나온다)
      → 계산 기준선             (봉인된 배분·인식규칙·기준 인식일 — M0-3.2b)
      → PathCalculationRequest

## 검증기는 **제품의 것을 쓴다**

관계 승인 판정은 `core.ontology_resolvers.product_approval_resolver` 가 이미 한다
(전용 이벤트 유형·대상 대조·행위자 대조·철회 확인). 여기서 다시 만들지 않는다 —
두 벌이면 한쪽만 고쳐지는 날이 오고, 그날 이 경로만 헐거워진다.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from core import calc_capability as cc
from core import calc_dataset_loader as loader
from core import path_calculation as pc

#: 계산 능력 실행 승인 사건. ⚠️ 대상은 **참조 + 산식 판의 지문**이다 — 참조 이름만
#: 대상으로 삼으면 산식을 고쳐도 옛 승인이 유효해 보인다.
CAPABILITY_APPROVED = "CALC_CAPABILITY_APPROVED"
CAPABILITY_REVOKED = "CALC_CAPABILITY_REVOKED"
CAPABILITY_SUBJECT = "calc_capability"


def capability_subject(cap: Any) -> str:
    """실행 승인의 **대상 지문** — 산식 정체성만 담는다.

    ★★★ `Capability.fingerprint()` 를 쓰지 않는다. 그것은 **계약 전체**의 지문이라
      `state`·`ledger_event_id` 까지 들어간다. 승인을 남긴 뒤 상태를 `APPROVED` 로
      올리는 순간 지문이 바뀌어 **승인이 스스로 죽는다**(실측 — 순환이다).

    ★ 승인이 물어야 하는 것은 「이 산식으로 계산해도 되는가」다. 그래서 대상은:

          참조 · 산식 판 · 필요 계약키 · 출력(지표·단위·부호)

    ⚠️ 산식 판이나 출력의 뜻이 바뀌면 지문이 바뀌고 옛 승인은 죽는다 — 그것이 노림수다
      (「같은 이름 다른 계산」이 승인을 물려받지 못한다).
    ⚠️ 상태·승인 사건 id 는 **넣지 않는다.** 그것은 「승인됐는가」이지 「무엇을
      승인하는가」가 아니다."""
    import hashlib
    import json
    payload = {
        "ref": cap.ref,
        "model_version": cap.model_version,
        "subject_type": cap.subject_type,
        "relation": cap.relation,
        "object_type": cap.object_type,
        "required_datasets": sorted(cap.required_datasets),
        "outputs": sorted([list(o) for o in cap.outputs]),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


class PathRequestError(Exception):
    """요청을 산출할 수 없다. ⚠️ 「빈 요청으로 계산해 본다」를 하지 않는다."""


# ── 실제 검증기 ──────────────────────────────────────────────────────────

def capability_verifier(actor: str) -> Callable[[Any], bool]:
    """계산 능력 실행 승인을 **원장에서** 확인하는 검증기를 만든다.

    ★★★ 확인하는 것:
      ① 등록부의 `ledger_event_id` 로 사건이 실재하는가
      ② 유형이 `CALC_CAPABILITY_APPROVED` 이고 주체가 `calc_capability` 인가
      ③ **대상 지문이 지금 등록부의 지문과 같은가** — 산식이 바뀌면 다른 대상이다
      ④ 승인자가 이 실행을 요청한 행위자와 같은가… **가 아니다**(아래 참고)
      ⑤ 철회 자식 사건이 없는가

    ⚠️ ④를 넣지 않는 이유: 계산 능력 승인은 **한 번 승인하면 모두가 쓰는** 것이다.
      관계 승인(`product_approval_resolver`)은 행위자를 대조하지만 그것은 「이 사람이
      이 관계를 승인했는가」를 묻기 때문이고, 여기서는 「이 산식이 승인됐는가」를 묻는다.
      섞으면 승인자 본인만 계산할 수 있게 된다.

    ⚠️ 원장을 못 읽으면 **던진다.** 「모르니까 승인 없음」으로 접으면 장애 중에 모든
      계산이 「아직 준비되지 않았다」로 보이고, 아무도 저장소를 보러 가지 않는다."""
    def _verify(cap: Any) -> bool:
        from core.decision_ledger import DecisionLedgerError, decision_ledger
        event_id = str(getattr(cap, "ledger_event_id", "") or "").strip()
        if not event_id:
            return False
        try:
            row = decision_ledger.get_event_strict(event_id)
        except DecisionLedgerError as e:
            #: ⚠️ 접지 않는다 — 호출부(`assert_executable`)가 이 예외를 그대로 올린다.
            raise
        if not row:
            return False
        if str(row.get("event_type", "")) != CAPABILITY_APPROVED:
            return False
        if str(row.get("subject_type", "")) != CAPABILITY_SUBJECT:
            return False
        #: ★★★ 대상 지문 대조. 산식 판이 바뀌면 등록부 지문이 바뀌고, 옛 승인은 죽는다.
        if str(row.get("subject_id", "")) != capability_subject(cap):
            return False
        #: ⑤ 철회. ⚠️ `has_invalidating_child` 는 제한 없이 묻고 실패를 던진다.
        return not decision_ledger.has_invalidating_child(event_id, (CAPABILITY_REVOKED,))
    return _verify


def relation_verifier(actor: str) -> Callable[[str, str], bool]:
    """관계 승인을 **제품 판정기로** 확인하는 검증기를 만든다.

    ★ `product_approval_resolver` 를 그대로 쓴다 — 전용 이벤트 유형·대상 대조·행위자
      대조·철회 확인을 이미 한다. 여기서 다시 만들면 두 벌이 되고, 한쪽만 고쳐진다.
    ⚠️ 원장 장애는 그쪽이 예외로 올린다. 실행기가 그것을 503 으로 바꾼다."""
    from core.ontology_resolvers import (ACTION_RELATION_APPROVE,
                                         product_approval_resolver)

    def _verify(relation_id: str, event_id: str) -> bool:
        return bool(product_approval_resolver(
            event_id, ACTION_RELATION_APPROVE, actor,
            target_type="relation", target_id=relation_id))
    return _verify


# ── 요청 산출 ────────────────────────────────────────────────────────────

def resolve_relation_approvals(relation_ids: Sequence[str], *, actor: str,
                               tenant_id: str, entity_mode: str
                               ) -> Dict[str, str]:
    """각 관계의 **살아 있는 승인 사건**을 원장에서 찾는다.

    ★★★ 이것이 M0-3.2 의 핵심이다. 앞서는 호출자가 `{관계: 사건}` 을 적어 보냈고,
      실행기는 그 주장을 검사했다 — 사건 id 를 아는 사람이면 아무 값이나 넣을 수 있었다.

    ⚠️ 승인이 없는 관계는 **빼지 않는다.** 빼면 실행기의 「경로의 모든 관계가 승인됐는가」
      검사가 통과해 버린다(집합이 줄었으니 일치한다) — 그것이 검사를 무력화하는 길이다.
    ★ 그래서 **찾은 것만** 돌려주고, 호출부가 경로 전체 집합과 대조한다.
    """
    from core.decision_ledger import DecisionLedgerError, decision_ledger
    out: Dict[str, str] = {}
    verify = relation_verifier(actor)
    for rel in sorted({str(r).strip() for r in relation_ids if str(r).strip()}):
        try:
            events = decision_ledger.list_events_strict(
                event_type="ONTOLOGY_RELATION_APPROVED", subject_type="ontology_relation",
                subject_id=rel, tenant_id=tenant_id, entity_mode=entity_mode, limit=100)
        except DecisionLedgerError as e:
            raise PathRequestError(f"관계 승인을 읽지 못했습니다({rel}): {e}")
        #: ★ 최신부터 본다(`list_events_strict` 는 seq 내림차순). 살아 있는 첫 승인을 쓴다.
        for ev in events:
            eid = str(ev.get("event_id", ""))
            if verify(rel, eid):
                out[rel] = eid
                break
    return out


def build_request(store: Any, *, query_id: str, path_fingerprint: str,
                  relation_ids: Sequence[str], instance_id: str,
                  tenant_id: str, entity_mode: str, scope_node_id: str,
                  as_of: str, actor: str,
                  assumptions: Optional[Mapping[str, Any]] = None
                  ) -> pc.PathCalculationRequest:
    """서버가 계산 요청을 **산출한다.** 호출자는 «무엇을 묻는가» 만 준다.

    산출하는 것:
      · `relation_approvals` — 원장에서 찾은 살아 있는 승인
      · `sealed_snapshots`   — 저장소의 인증판(그 인스턴스·그 범위)

    ⚠️ 승인이 하나라도 없으면 그 관계는 목록에서 빠진다. 실행기가 경로 집합과 대조해
      `BLOCKED` 로 답한다 — **여기서 막지 않는 이유**는, 「무엇이 없는가」를 실행기의
      차단 사유가 한 곳에서 말하게 하기 위해서다(두 곳에서 막으면 사유가 갈린다).

    ⚠️ 봉인 판은 **「지금 최신 인증판」**이다. 관계 승인 때 봉인한 판이 따로 있으면
      그것을 써야 한다 — 그 자리는 **아직 비어 있다**(M1 부채).
    """
    if not str(instance_id or "").strip():
        raise PathRequestError("키트 인스턴스가 없습니다 — 어느 자료로 계산할지 모릅니다.")
    approvals = resolve_relation_approvals(
        relation_ids, actor=actor, tenant_id=tenant_id, entity_mode=entity_mode)
    seals = loader.active_seals(store, instance_id=instance_id,
                                contract_keys=pc.REQUIRED_DATASETS)

    #: ★★★ [M0-3.2b] **기준선은 봉인된 것에서 읽는다.** 호출자가 `baseline_id` 를 적어
    #:   보내던 자리다 — 그러면 「어느 기준선과 비교했는가」가 주장이 된다.
    from core import calc_baseline as cb
    base = cb.active(store, instance_id=instance_id, tenant_id=tenant_id,
                     entity_mode=entity_mode, scope_node_id=scope_node_id)
    if base is None:
        #: ⚠️ 빈 기준선으로 계산하지 않는다. 계산기가 모든 판매행을 `missing_baseline`
        #:   으로 답하고, 그것이 화면에서 「영향 없음」으로 읽힌다.
        raise PathRequestError(
            "봉인된 계산 기준선이 없습니다 — 배분·인식 규칙·기준 인식일을 먼저 봉인해야 "
            "합니다(빈 기준선으로 계산하면 「이연 없음」과 「비교할 기준이 없음」이 같은 "
            "답이 됩니다).")

    #: ★★★ 호출자의 가정 위에 **봉인 값을 덮는다.** 겹치면 기준선이 이긴다 —
    #:   봉인의 뜻이 그것이다.
    #:
    #: ⚠️ 「호출자 가정에서 세 키를 먼저 지운다」를 함께 두었었는데, 덮어쓰기가 있으니
    #:   **등가**였다(변이로 확인 — 지워도 실패가 0건). 통제를 두 겹으로 보이게 두면
    #:   어느 것이 실제로 막는지 알 수 없고, 하나를 지울 때 「다른 하나가 있으니 괜찮다」고
    #:   믿게 된다. 그래서 **한 겹으로 남긴다.**
    merged: Dict[str, Any] = dict(assumptions or {})
    merged["sales_allocation"] = base["sales_allocation"]
    merged["recognition_span_days"] = base["recognition_span_days"]
    merged["baseline_recognition"] = base["baseline_recognition"]

    return pc.PathCalculationRequest(
        query_id=query_id, path_fingerprint=path_fingerprint,
        tenant_id=tenant_id, entity_mode=entity_mode, scope_node_id=scope_node_id,
        as_of=as_of, baseline_id=base["build_id"],
        baseline_fingerprint=base["fingerprint"],
        sealed_snapshots=seals,
        required_relation_ids=tuple(sorted(
            {str(r).strip() for r in relation_ids if str(r).strip()})),
        relation_approvals=approvals,
        assumptions=merged)


def run(store: Any, request: pc.PathCalculationRequest, *, actor: str) -> Dict[str, Any]:
    """요청을 **실제 검증기로** 실행한다.

    ⚠️ 검증기를 인자로 받지 않는다 — 받으면 호출부가 대역을 넘길 수 있고, 그것이
      「승인 대역으로 계산」이다. 실제 원장만 본다."""
    datasets = loader.load_sealed(
        store, sealed_snapshots=request.sealed_snapshots,
        tenant_id=request.tenant_id, entity_mode=request.entity_mode,
        scope_node_id=request.scope_node_id)
    return pc.calculate(request, datasets=datasets,
                        ledger_verifier=capability_verifier(actor),
                        relation_verifier=relation_verifier(actor))


# ── 승인 기록(관리 경로) ─────────────────────────────────────────────────

def approve_capability(ref: str, *, actor: str, rationale: str,
                       evidence_refs: Optional[Sequence[str]] = None,
                       tenant_id: str = "tenant_default",
                       entity_mode: str = "REAL") -> Dict[str, Any]:
    """계산 능력 실행을 승인하고 **원장 사건 id 를 돌려준다.**

    ★★★ 대상은 **참조 + 산식 판의 지문**이다. 산식이 바뀌면 지문이 바뀌고, 이 승인은
      자동으로 죽는다 — 「같은 이름 다른 계산」이 승인을 물려받지 못한다.
    ⚠️ 이 함수는 등록부의 `state` 를 바꾸지 않는다. 상태 전환은 배포 결정이고, 여기서
      하면 승인 한 번으로 코드가 바뀌는 셈이 된다."""
    from core.decision_ledger import decision_ledger
    cap = cc.get(ref)
    if not str(rationale or "").strip():
        raise PathRequestError(
            "승인 사유가 필요합니다 — 「왜 이 산식으로 계산해도 되는가」에 답할 수 없는 "
            "승인은 나중에 아무도 뒤집을 수 없습니다.")
    ev = decision_ledger.append(
        event_type=CAPABILITY_APPROVED, subject_type=CAPABILITY_SUBJECT,
        subject_id=capability_subject(cap), actor_type="user", actor_id=actor,
        decision="APPROVED", rationale=rationale,
        evidence_refs=[*(evidence_refs or []), f"capability:{ref}",
                       f"model_version:{cap.model_version}"],
        tenant_id=tenant_id, entity_mode=entity_mode)
    return {"event_id": str(ev.get("event_id", "")),
            "fingerprint": capability_subject(cap), "capability_ref": ref}
