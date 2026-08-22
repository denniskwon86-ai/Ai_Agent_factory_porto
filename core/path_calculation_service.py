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
    """**폐기됨** — 이 함수는 더 이상 승인 대상이 아니다.

    ⚠️⚠️ [M0-0 / 2026-08-22] 승인 대상은 산식 정체성 하나가 아니라 **결속 지문**이다
      (산식·단위·부호·필수 계약키·인증판 집합·코드 지문·정본 규칙·실행 범위).
      `core.calc_execution_approval.binding_fingerprint()` 가 정본이다.

    ★ 왜 남겨 두는가: 이 이름으로 만든 옛 승인 사건이 원장에 남아 있을 수 있고, 그것이
      **왜 이제 유효하지 않은지**를 코드가 말할 수 있어야 한다. 지우면 그 사건들이
      「알 수 없는 대상」이 된다."""
    raise NotImplementedError(
        "승인 대상은 결속 지문입니다 — core.calc_execution_approval.binding_fingerprint() "
        "를 쓰십시오. 산식 정체성만으로 승인하면 판·범위·코드가 바뀌어도 승인이 삽니다.")
class PathRequestError(Exception):
    """요청을 산출할 수 없다. ⚠️ 「빈 요청으로 계산해 본다」를 하지 않는다."""


# ── 실제 검증기 ──────────────────────────────────────────────────────────

def context_verifier(store: Any, *, instance_id: str, tenant_id: str, entity_mode: str,
                     scope_node_id: str, data_kind: str = "",
                     contract_fingerprint: str = "") -> Callable[[Any], bool]:
    """요청이 아직 없을 때(화면·준비도) 쓰는 승인 확인기.

    ★ 결속을 만드는 함수는 `cea.binding` **하나**다. 다른 것은 판이 어디서 오는가뿐이다:
      · 실행 때 — `request.sealed_snapshots`(그 계산이 실제로 읽은 판)
      · 화면·준비도 — `loader.active_seals`(지금 최신 인증판)
    ⚠️ `build_request` 가 후자로 전자를 채우므로 실무에서는 같은 값이다. 그래도 실행
      경로는 **요청의 판**을 본다 — 그 사이에 새 판이 인증되면 승인은 죽어야 한다.

    ⚠️ 판을 못 읽으면 **던진다.** 「판 없음 = 승인 없음」으로 접지 않는다."""
    from core import calc_execution_approval as cea

    seals = loader.active_seals(store, instance_id=instance_id,
                                contract_keys=pc.REQUIRED_DATASETS)

    def _verify(cap: Any) -> bool:
        bound = cea.binding(
            cap, data_kind=data_kind or cea.DEFAULT_DATA_KIND, entity_mode=entity_mode,
            tenant_id=tenant_id, scope_node_id=scope_node_id,
            snapshots={k: v for k, v in seals.items() if k in cap.required_datasets},
            contract_fingerprint=contract_fingerprint)
        got = cea.active(store, ref=cap.ref, bound=bound)
        return bool(got) and str(got["ledger_event_id"]) == str(
            getattr(cap, "ledger_event_id", ""))
    return _verify


def context_resolver(store: Any, *, instance_id: str, tenant_id: str, entity_mode: str,
                     scope_node_id: str, data_kind: str = "",
                     contract_fingerprint: str = "") -> Callable[[str], Any]:
    """요청이 아직 없을 때의 **실효 능력** 해석기(화면·준비도·어댑터)."""
    from core import calc_execution_approval as cea

    seals = loader.active_seals(store, instance_id=instance_id,
                                contract_keys=pc.REQUIRED_DATASETS)

    def _resolve(ref: str) -> Any:
        cap = cc.get(ref)
        bound = cea.binding(
            cap, data_kind=data_kind or cea.DEFAULT_DATA_KIND, entity_mode=entity_mode,
            tenant_id=tenant_id, scope_node_id=scope_node_id,
            snapshots={k: v for k, v in seals.items() if k in cap.required_datasets},
            contract_fingerprint=contract_fingerprint)
        return cea.effective(store, ref, bound=bound)
    return _resolve


def capability_verifier(store: Any, request: pc.PathCalculationRequest, *,
                        data_kind: str = "", contract_fingerprint: str = ""
                        ) -> Callable[[Any], bool]:
    """실행 **직전** 승인 재확인.

    ★★★ 확인은 `calc_execution_approval.active()` **한 벌**이 한다. 여기서 원장 대조를
      다시 만들지 않는다 — 두 벌이면 한쪽만 고쳐지고, 그날 이 경로만 헐거워진다.

    ## 왜 해석기와 **또** 확인하는가 — 두 벌이 아니다

    해석기(`capability_resolver`)는 관문 3 **앞**에서 실효 능력을 만든다. 그 사이에
    승인이 철회될 수 있다. 그래서 실행 직전에 **같은 함수**를 한 번 더 부른다 —
    같은 규칙을 두 시점에 적용하는 것이지 두 규칙을 두는 것이 아니다.

    ⚠️ 그리고 **해석기가 본 그 사건인지**까지 본다. 그 사이에 철회 후 재승인이 있었다면
      다른 승인이고, 다른 승인으로 계산했다고 적으면 안 된다.

    ⚠️ 원장을 못 읽으면 `active()` 가 던진다 — `assert_executable` 이 그것을 장애로
      올린다. 「모르니까 승인 없음」으로 접지 않는다."""
    from core import calc_execution_approval as cea

    def _verify(cap: Any) -> bool:
        bound = execution_binding(store, cap, request, data_kind=data_kind,
                                  contract_fingerprint=contract_fingerprint)
        got = cea.active(store, ref=cap.ref, bound=bound)
        if not got:
            return False
        return str(got["ledger_event_id"]) == str(getattr(cap, "ledger_event_id", ""))
    return _verify


def relation_verifier() -> Callable[[str, str], bool]:
    """관계 승인을 **제품 판정기로** 확인하는 검증기를 만든다.

    ★ `product_approval_resolver` 를 그대로 쓴다 — 전용 이벤트 유형·대상 대조·철회
      확인을 이미 한다. 여기서 다시 만들면 두 벌이 되고, 한쪽만 고쳐진다.

    ## ⚠️⚠️ [2026-08-22] 요청자를 승인자 자리에 넣고 있었다

    종전에는 `relation_verifier(actor)` 가 **계산 요청자**를 판정기의 `actor` 로 넘겼다.
    판정기의 ④ 는 「승인 사건의 `actor_id` 가 이 행위자와 같은가」를 본다 — 그래서 제품
    경로에서는 **자기가 직접 승인한 관계로만 계산할 수 있었다.** 실제로 라우트 종단을
    처음 돌렸을 때 모든 계산이 `relation_approvals 가 비어 있습니다` 로 막혔다.

    ⚠️ 앞선 시험이 이것을 놓친 이유: 승인자와 요청자를 **같은 문자열**로 두었다. 배역이
      같으면 두 질문의 차이가 사라진다 — 「fixture 가 계약을 대신 정의하는」 유형이다.

    ★★★ 그래서 묻는 질문을 바로잡았다. 계산은 「내가 승인했는가」를 주장하지 않는다.
      묻는 것은 **「온톨로지가 이 관계에 묶은 그 승인이 지금도 살아 있는가」**이고,
      대조할 행위자는 **그 사건이 적어 둔 승인자**다.

    ⚠️ 그래서 판정기의 ④ 는 여기서 **구조적으로 참이 된다.** 감춰 두지 않는다. 그 자리를
      대신하는 것은 두 가지다:
        · 승인 시점에 온톨로지 런타임이 이미 ①~⑤ 를 **승인자를 행위자로 두고** 통과시켰다.
        · 그리고 이제 계산은 **아무 사건이나** 받지 않는다 — 온톨로지가 관계에 묶어 둔
          `ledger_correlation_id` 그 사건만 본다(`resolve_relation_approvals`).
      뒤지지 않으므로 「그 관계를 언급하는 다른 승인 사건」이 근거가 될 길이 없다.

    ⚠️ 원장 장애는 판정기가 예외로 올린다. 실행기가 그것을 503 으로 바꾼다."""
    from core.decision_ledger import decision_ledger
    from core.ontology_resolvers import (ACTION_RELATION_APPROVE,
                                         product_approval_resolver)

    def _verify(relation_id: str, event_id: str) -> bool:
        #: ★ 승인자는 **사건이 적어 둔 사람**이다. 못 읽으면 예외가 그대로 올라간다 —
        #:   「못 읽었다」를 「승인 없음」으로 접지 않는다.
        event = decision_ledger.get_event_strict(str(event_id or "").strip())
        approver = str((event or {}).get("actor_id") or "").strip()
        if not approver:
            return False
        return bool(product_approval_resolver(
            event_id, ACTION_RELATION_APPROVE, approver,
            target_type="relation", target_id=relation_id))
    return _verify


# ── 요청 산출 ────────────────────────────────────────────────────────────

def resolve_relation_approvals(relation_bindings: Mapping[str, str]) -> Dict[str, str]:
    """관계마다 **온톨로지가 묶어 둔 승인 사건**이 지금도 살아 있는지 확인한다.

    ★★★ [M0-3.2] 앞서는 호출자가 `{관계: 사건}` 을 적어 보냈고, 실행기는 그 주장을
      검사했다 — 사건 id 를 아는 사람이면 아무 값이나 넣을 수 있었다.

    ★★★ [2026-08-22] 그다음 판은 **관계 id 로 원장을 뒤졌다.** 그것도 옳지 않다 —
      그 관계를 언급하는 승인 사건이 여럿이면 «아무거나 살아 있는 것» 이 근거가 된다.
      온톨로지는 승인할 때 **사건 하나를 관계에 묶어 둔다**(`ledger_correlation_id`).
      대조할 것은 그것뿐이고, 이 함수는 이제 뒤지지 않는다.

    ⚠️ 그래서 `relation_bindings` 는 **경로의 간선에서** 와야 한다. 호출자가 적어 보내도
      판정기가 ①존재 ②전용 유형 ③대상 일치 ⑤철회 없음을 보므로, 바꿔 넣을 수 있는 것은
      「같은 관계의 다른 살아 있는 승인」뿐이다 — 뒤졌을 때 나왔을 값과 같다.

    ⚠️ 승인이 없는 관계는 **빼지 않는다.** 빼면 실행기의 「경로의 모든 관계가 승인됐는가」
      검사가 통과해 버린다(집합이 줄었으니 일치한다) — 그것이 검사를 무력화하는 길이다.
    ★ 그래서 **확인된 것만** 돌려주고, 호출부가 경로 전체 집합과 대조한다.
    """
    from core.decision_ledger import DecisionLedgerError
    out: Dict[str, str] = {}
    verify = relation_verifier()
    for rel in sorted(relation_bindings):
        key = str(rel).strip()
        eid = str(relation_bindings[rel] or "").strip()
        if not key or not eid:
            #: ⚠️ **통제가 아니다 — 빠른 경로다.** 비워 두고 넘겨도 아래 검증기가 거짓으로
            #:   답한다(변이로 확인: 이 줄을 지워도 실패 0건 = 등가). 통제처럼 보이게
            #:   두면 나중에 「여기서 막으니 괜찮다」고 믿게 되므로 그렇게 적어 둔다.
            #:   막는 것은 검증기이고, 여기서는 없는 사건을 원장에 묻지 않을 뿐이다.
            continue
        try:
            if verify(key, eid):
                out[key] = eid
        except DecisionLedgerError as e:
            #: ⚠️ **장애를 「승인 없음」으로 접지 않는다.** 접으면 원장이 죽은 동안
            #:   모든 계산이 「승인 안 됨」으로 보이고, 사람들은 승인을 다시 요청한다.
            raise PathRequestError(f"관계 승인을 읽지 못했습니다({key}): {e}")
    return out


def build_request(store: Any, *, query_id: str, path_fingerprint: str,
                  relation_bindings: Mapping[str, str], instance_id: str,
                  tenant_id: str, entity_mode: str, scope_node_id: str,
                  as_of: str, actor: str,
                  assumptions: Optional[Mapping[str, Any]] = None
                  ) -> pc.PathCalculationRequest:
    """서버가 계산 요청을 **산출한다.** 호출자는 «무엇을 묻는가» 만 준다.

    산출하는 것:
      · `relation_approvals` — 온톨로지가 관계에 묶어 둔 승인 중 **지금도 살아 있는 것**
      · `sealed_snapshots`   — 저장소의 인증판(그 인스턴스·그 범위)

    ★ `relation_bindings` 는 `{관계 id: 승인 사건 id}` 이고 **경로의 간선에서** 온다
      (`ontology_path_adapter` 가 `approval_event_id` 로 실어 준다).

    ⚠️ 승인이 하나라도 없으면 그 관계는 목록에서 빠진다. 실행기가 경로 집합과 대조해
      `BLOCKED` 로 답한다 — **여기서 막지 않는 이유**는, 「무엇이 없는가」를 실행기의
      차단 사유가 한 곳에서 말하게 하기 위해서다(두 곳에서 막으면 사유가 갈린다).

    ⚠️ 봉인 판은 **「지금 최신 인증판」**이다. 관계 승인 때 봉인한 판이 따로 있으면
      그것을 써야 한다 — 그 자리는 **아직 비어 있다**(M1 부채).
    """
    if not str(instance_id or "").strip():
        raise PathRequestError("키트 인스턴스가 없습니다 — 어느 자료로 계산할지 모릅니다.")
    approvals = resolve_relation_approvals(relation_bindings)
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
        #: ⚠️ 요구 집합은 **경로의 관계 전부**다 — 승인이 없는 것도 포함한다. 줄이면
        #:   실행기의 일치 검사가 통과해 버린다.
        required_relation_ids=tuple(sorted(
            {str(r).strip() for r in relation_bindings if str(r).strip()})),
        relation_approvals=approvals,
        assumptions=merged)


def execution_binding(store: Any, cap: Any, request: pc.PathCalculationRequest, *,
                      data_kind: str = "", contract_fingerprint: str = "") -> Dict[str, Any]:
    """이 요청이 실제로 서 있는 **조건**. 승인 대상과 대조할 값이다.

    ★★★ 승인 화면이 만든 결속과 **같은 재료로** 만든다 — 다른 재료로 만들면 화면에서
      승인한 것과 실행 때 대조하는 것이 달라지고, 그때는 승인이 무엇을 승인했는지 모른다.
    ⚠️ 판은 **이 요청이 실제로 쓰는 봉인 판**이다. 「지금 최신」을 다시 읽지 않는다 —
      그러면 승인 이후 올라온 판으로 계산하면서 승인이 살아 있게 된다."""
    from core import calc_execution_approval as cea

    return cea.binding(
        cap, data_kind=data_kind or cea.DEFAULT_DATA_KIND,
        entity_mode=request.entity_mode, tenant_id=request.tenant_id,
        scope_node_id=request.scope_node_id,
        snapshots={k: v for k, v in request.sealed_snapshots.items()
                   if k in cap.required_datasets},
        contract_fingerprint=contract_fingerprint)


def capability_resolver(store: Any, request: pc.PathCalculationRequest, *,
                        data_kind: str = "", contract_fingerprint: str = ""
                        ) -> Callable[[str], Any]:
    """참조 → **실효 능력.** 살아 있는 승인이 있으면 `APPROVED`, 없으면 등록부 그대로.

    ⚠️ 등록부 상수를 고치지 않는다 — 고치면 프로세스 전체·모든 테넌트에 걸린다."""
    from core import calc_execution_approval as cea

    def _resolve(ref: str) -> Any:
        cap = cc.get(ref)
        bound = execution_binding(store, cap, request, data_kind=data_kind,
                                  contract_fingerprint=contract_fingerprint)
        return cea.effective(store, ref, bound=bound)
    return _resolve


def run(store: Any, request: pc.PathCalculationRequest, *, actor: str,
        data_kind: str = "", contract_fingerprint: str = "") -> Dict[str, Any]:
    """요청을 **실제 검증기로** 실행한다.

    ⚠️ 검증기를 인자로 받지 않는다 — 받으면 호출부가 대역을 넘길 수 있고, 그것이
      「승인 대역으로 계산」이다. 실제 원장만 본다."""
    datasets = loader.load_sealed(
        store, sealed_snapshots=request.sealed_snapshots,
        tenant_id=request.tenant_id, entity_mode=request.entity_mode,
        scope_node_id=request.scope_node_id)
    return pc.calculate(request, datasets=datasets,
                        ledger_verifier=capability_verifier(
                            store, request, data_kind=data_kind,
                            contract_fingerprint=contract_fingerprint),
                        relation_verifier=relation_verifier(),
                        capability_resolver=capability_resolver(
                            store, request, data_kind=data_kind,
                            contract_fingerprint=contract_fingerprint))


# ── 승인 기록(관리 경로) ─────────────────────────────────────────────────

#: ⚠️⚠️ [M0-0] **`approve_capability()` 를 여기서 지웠다.** 승인을 만드는 곳이 둘이면
#:   하나는 반드시 옛 대상(산식 정체성)으로 남고, 그 승인은 판·범위·코드가 바뀌어도
#:   살아남는다. 승인은 `core.calc_execution_approval.approve()` 한 곳에서만 만든다.
