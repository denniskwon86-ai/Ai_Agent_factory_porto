"""Contract Review Gate — 「이 계약을 사람이 다시 봐야 하는가」를 답하는 **비-LLM 노드**.

설계서 [I-4 §3·§13] 의 규칙은 두 줄이다:

  · 최초 계약 또는 **지문 변경** → 사용자 검토
  · 지문 불변 → 자동 통과

★ 지문 불변을 자동 통과시키는 이유는 편의가 아니다. **사람이 게이트를 습관으로
  통과시키지 않게** 하기 위해서다 — 바뀐 것이 없는데도 매번 승인 버튼을 누르게 하면,
  진짜로 바뀐 날에도 같은 손놀림으로 누른다. 게이트가 열리는 것 자체가 신호여야 한다.

⚠️⚠️ 그래서 **「같다」의 정의가 이 모듈의 전부**다. 두 지문이 모두 비어 있는 것은
  「같다」가 아니다 — 그것은 「계약이 없다」이고, 그대로 통과시키면 계약 대상 태스크가
  계약 없이 빌드된다. 봉인이 「그때와 같은가」에만 답하고 「그때가 옳았는가」에는
  답하지 않는 것과 같은 함정이다([I-4 3단계]).

⚠️ 판정 함수(`evaluate`)는 **아무것도 import 하지 않는다.** 원장 기록은 아래쪽
  `record_decision` 이 따로 한다 — 판정과 기록이 한 함수에 있으면 기록을 건너뛰는
  경로가 곧 판정을 건너뛰는 경로가 된다.
"""
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

#: 판정. 닫힌 목록이다.
NOT_APPLICABLE = "NOT_APPLICABLE"   # 계약이 필요 없는 산출물
AUTO_PASS = "AUTO_PASS"             # 승인된 지문과 동일 — 사람을 부르지 않는다
REVIEW_REQUIRED = "REVIEW_REQUIRED"  # 최초 승인 또는 지문 변경
BLOCKED = "BLOCKED"                 # 계약 대상인데 볼 계약이 없다

VERDICTS = (NOT_APPLICABLE, AUTO_PASS, REVIEW_REQUIRED, BLOCKED)

#: 계약 상태(`ProjectState.app_runtime_contract_status`).
DRAFT = "DRAFT"
COMPILED = "COMPILED"
APPROVED = "APPROVED"

#: 원장 이벤트·주체(값은 `core.decision_ledger` 의 목록과 같아야 한다).
EVENT_REVIEW_REQUESTED = "APP_CONTRACT_REVIEW_REQUESTED"
EVENT_APPROVED = "APP_CONTRACT_APPROVED"
EVENT_REJECTED = "APP_CONTRACT_REJECTED"
SUBJECT_TYPE = "app_contract"

#: 지문은 64자리 소문자 16진수다. 그 밖의 것은 **지문이 아니다.**
_FP_LEN = 64


class GateDecision(NamedTuple):
    """판정과 **그 이유**. 이유가 없으면 사람은 화면에서 무엇을 볼지 모른다."""
    verdict: str
    reason: str
    compiled_fingerprint: str
    approved_fingerprint: str
    #: 사람이 승인해야 하는가(원장에 남길 일이 생기는가).
    needs_human: bool


def _clean_fingerprint(raw: Any) -> str:
    """지문으로 **쓸 수 있는 값**만 통과시킨다. 아니면 빈 문자열.

    ⚠️ `None`·공백·`"UNAPPROVED"`·길이가 다른 문자열을 그대로 비교에 넣으면, 둘 다
      같은 쓰레기 값일 때 「같다」가 되어 게이트가 열리지 않는다. 정규화를 여기서
      한 번만 한다."""
    if not isinstance(raw, str):
        return ""
    value = raw.strip().lower()
    if len(value) != _FP_LEN:
        return ""
    if any(c not in "0123456789abcdef" for c in value):
        return ""
    return value


def evaluate(*, requires_contract: bool,
             compiled_fingerprint: Any,
             approved_fingerprint: Any,
             contract_status: Any = "") -> GateDecision:
    """게이트 판정. **예외를 올리지 않는다** — 판독 실패도 답이어야 한다.

    ⚠️ `contract_status` 는 보조 근거일 뿐 판정의 근거가 아니다. 상태 문자열은
      노드가 쓰는 값이고, 지문은 계약 원문에서 계산된 값이다 — 둘이 어긋나면
      **지문을 믿는다.** 상태만 믿으면 `APPROVED` 라고 적어 두는 것만으로 게이트를
      지날 수 있다."""
    compiled = _clean_fingerprint(compiled_fingerprint)
    approved = _clean_fingerprint(approved_fingerprint)

    if not requires_contract:
        return GateDecision(NOT_APPLICABLE,
                            "계약이 필요 없는 산출물입니다.",
                            compiled, approved, False)

    if not compiled:
        #: ★★★ 여기가 가장 조용한 구멍이다. 계약이 없는데 승인 지문도 없으면
        #:   「둘 다 비었으니 같다 → 자동 통과」로 읽히기 쉽다. 그러면 계약 대상
        #:   태스크가 **계약 없이** 빌드된다.
        return GateDecision(BLOCKED,
                            "계약 대상인데 컴파일된 계약이 없습니다 — 먼저 계약을 "
                            "컴파일하십시오(Tech Lead 초안 → HostContractCompiler).",
                            compiled, approved, False)

    if not approved:
        return GateDecision(REVIEW_REQUIRED,
                            "이 프로젝트의 **최초 계약**입니다 — 사용자 검토가 필요합니다.",
                            compiled, approved, True)

    if compiled != approved:
        return GateDecision(REVIEW_REQUIRED,
                            f"계약 지문이 바뀌었습니다(승인 {approved[:12]}… → "
                            f"현재 {compiled[:12]}…) — 재승인이 필요합니다.",
                            compiled, approved, True)

    #: ★★★ 지문이 같은 것만으로는 부족하다. **승인이 지금도 유효한가**를 함께 본다.
    #:
    #: ⚠️ [I-4 3단계] 에서 닫은 「승인 취소 후 기존 증명이 살아남는 문제」와 같은
    #:   종류다. 지문은 「그때와 같은가」에만 답한다 — 그 승인이 **취소·반려됐는지**
    #:   에는 답하지 않는다. 상태가 `APPROVED` 가 아닌데 지문만 같다고 통과시키면,
    #:   반려된 계약이 반려된 채로 빌드된다.
    #: ★ 상태를 **여기서만** 본다. 위쪽 판정들은 상태와 무관하게 사람을 부르므로
    #:   상태를 믿어서 게이트가 «열리는» 경로는 이 한 줄뿐이다.
    if str(contract_status or "").strip().upper() != APPROVED:
        return GateDecision(REVIEW_REQUIRED,
                            f"지문은 같지만 계약 상태가 «{contract_status or '미지정'}» 입니다 "
                            f"— 승인이 취소·반려되었거나 아직 확정되지 않았습니다.",
                            compiled, approved, True)

    return GateDecision(AUTO_PASS,
                        "승인된 계약과 지문이 같고 승인 상태가 유효합니다 — 사람을 "
                        "부르지 않습니다.",
                        compiled, approved, False)


def evaluate_state(state: Any, *, requires_contract: bool) -> GateDecision:
    """`ProjectState`(또는 dict)에서 값을 뽑아 판정한다.

    ⚠️ 필드 이름을 호출부마다 적지 않게 한다 — 오타 하나가 「항상 최초 계약」이나
      「항상 자동 통과」로 조용히 바뀐다."""
    def _get(name: str) -> Any:
        if isinstance(state, dict):
            return state.get(name, "")
        return getattr(state, name, "")

    return evaluate(requires_contract=requires_contract,
                    compiled_fingerprint=_get("app_runtime_contract_fingerprint"),
                    approved_fingerprint=_get("approved_contract_fingerprint"),
                    contract_status=_get("app_runtime_contract_status"))


class GateTransitionError(ValueError):
    """승인·반려로 넘어갈 수 없는 판정에서 상태를 바꾸려 했다."""


def state_updates_for_approval(decision: GateDecision) -> Dict[str, str]:
    """승인이 확정됐을 때 상태에 반영할 값.

    ★ 승인은 **그때 본 지문**을 박아 넣는 것이다. 「승인됨」 플래그만 세우면 다음에
      계약이 바뀌어도 플래그가 남아 게이트가 다시 열리지 않는다.

    ⚠️⚠️ **승인할 수 있는 판정은 `REVIEW_REQUIRED` 하나뿐이다.** 예전에는 어떤
      판정을 넘겨도 `APPROVED` 를 돌려줬다 — 그래서 계약이 아예 없는 `BLOCKED`
      상태에서 이 함수를 잘못 부르면 **빈 지문이 승인된 지문으로 박혔다.** 그러면
      다음 판정은 「지문이 없다」가 아니라 「승인된 것과 다르다」로 읽히고, 사람은
      계약이 있다고 믿는다. 호출부의 실수를 조용히 승인으로 바꾸지 않는다."""
    if decision.verdict != REVIEW_REQUIRED:
        raise GateTransitionError(
            f"«{decision.verdict}» 판정은 승인할 수 없습니다 — 사람이 검토해야 하는 "
            f"판정(REVIEW_REQUIRED)에서만 승인이 성립합니다. 사유: {decision.reason}")
    if not decision.compiled_fingerprint:
        #: 위 검사를 지나면 지문은 이미 유효하지만, 두 조건이 **따로** 지켜지는지
        #: 보이게 남긴다 — 한쪽이 느슨해질 때 다른 쪽이 버텨야 한다.
        raise GateTransitionError("승인할 계약 지문이 없습니다.")
    return {"approved_contract_fingerprint": decision.compiled_fingerprint,
            "app_runtime_contract_status": APPROVED}


def state_updates_for_rejection(decision: GateDecision) -> Dict[str, str]:
    """반려됐을 때 상태에 반영할 값.

    ★ 반려는 **승인 지문을 비우는 것**이다. 상태만 `COMPILED` 로 되돌리고 지문을
      남겨 두면, 다음 판정에서 「지문이 같다」가 먼저 걸려 자동 통과로 새어 나간다.
    ⚠️ 계약 원문은 지우지 않는다 — 무엇이 반려됐는지 볼 수 없으면 고칠 수도 없다."""
    if decision.verdict != REVIEW_REQUIRED:
        raise GateTransitionError(
            f"«{decision.verdict}» 판정은 반려할 수 없습니다 — 사람이 검토 중인 "
            f"판정에서만 반려가 성립합니다. 사유: {decision.reason}")
    return {"approved_contract_fingerprint": "",
            "app_runtime_contract_status": COMPILED}


class ReviewRequestError(ValueError):
    """검토 요청·결정을 만들 수 없다. 라우트가 4xx/409 로 바꾼다."""


def _open_request(txn: Any, project_id: str, fingerprint: str) -> Optional[Dict[str, Any]]:
    """이 프로젝트·이 지문에 대해 **아직 결정되지 않은** 검토 요청을 찾는다.

    ★ 「열린」의 정의는 **원장으로만** 판정한다 — 승인·반려 자식 이벤트가 없는
      요청이 열린 요청이다.
    ⚠️ 상태 필드(`contract_review_request_event_id`)는 **캐시**다. 상태만 보면
      체크포인트 저장이 실패했을 때 「요청이 없다」로 읽혀 두 번째 요청이 생기고,
      그러면 승인이 어느 쪽에 붙었는지 아무도 답할 수 없다."""
    for ev in txn.find_events(event_type=EVENT_REVIEW_REQUESTED,
                              project_id=project_id,
                              subject_type=SUBJECT_TYPE, subject_id=fingerprint):
        kinds = set(txn.child_event_types(ev.get("event_id", "")))
        if not (kinds & {EVENT_APPROVED, EVENT_REJECTED}):
            return ev
    return None


def ensure_review_request(ledger: Any, decision: GateDecision, *,
                          project_id: str, task_ids: Any = (),
                          tenant_id: str = "tenant_default",
                          enterprise_scope_id: str = "",
                          entity_mode: str = "REAL") -> Tuple[Dict[str, Any], bool]:
    """검토 요청 이벤트를 **한 건만** 보장한다. `(이벤트, 새로 만들었는가)`.

    ★★★ 조회와 기록이 **하나의 락·트랜잭션** 안에서 일어난다. 그 사이에 틈이 있으면
      재시작이 겹치거나 동시 요청이 들어올 때 같은 요청이 두 건 생긴다.

    ⚠️ 「같은 요청」의 기준은 `project_id + 계약 지문` 이다. 지문이 다르면 **다른
      계약**이므로 옛 요청을 재사용하지 않는다 — 재사용하면 사람이 A 를 보고 승인한
      기록이 B 의 승인이 된다.
    ⚠️ 기록에 실패하면 **예외가 그대로 올라간다.** 요청 없이 게이트를 지나면 승인
      이력이 없는 승인이 생긴다."""
    if decision.verdict != REVIEW_REQUIRED:
        raise ReviewRequestError(
            f"«{decision.verdict}» 판정으로는 검토 요청을 만들지 않습니다 — 사람이 볼 것이 "
            f"없습니다. 사유: {decision.reason}")
    fp = decision.compiled_fingerprint
    if not fp:
        raise ReviewRequestError("검토할 계약 지문이 없습니다.")

    ids = [str(t) for t in (task_ids or [])]
    with ledger.transaction() as txn:
        existing = _open_request(txn, project_id, fp)
        if existing:
            #: ★ 체크포인트 저장이 실패했어도 여기서 **다시 찾아 재사용**한다.
            return existing, False
        ev = txn.append(
            event_type=EVENT_REVIEW_REQUESTED, subject_type=SUBJECT_TYPE, subject_id=fp,
            actor_type="system", decision="검토 요청",
            rationale=decision.reason,
            evidence_refs=[{"compiled_fingerprint": fp,
                            "previous_approved_fingerprint": decision.approved_fingerprint,
                            "task_ids": ids}],
            project_id=project_id, tenant_id=tenant_id,
            enterprise_scope_id=enterprise_scope_id, entity_mode=entity_mode)
    return ev, True


def assert_decidable(ledger: Any, request_event_id: str, *,
                     project_id: str, compiled_fingerprint: str) -> Dict[str, Any]:
    """이 요청에 지금 승인·반려를 붙일 수 있는가. 부모 이벤트를 돌려준다.

    네 가지를 **모두** 본다. 하나라도 빼면 그것이 우회로가 된다:

      1. 이벤트가 `APP_CONTRACT_REVIEW_REQUESTED` 인가
         — 아무 이벤트나 부모로 삼으면 승인이 엉뚱한 것에 붙는다.
      2. 같은 프로젝트인가 — 남의 프로젝트 요청으로 내 계약을 승인할 수 없다.
      3. 같은 계약 지문인가 — **요청 이후 계약이 바뀌었으면 그 승인은 다른 것을
         본 승인**이다. 이것이 「사람이 A 를 보고 B 를 승인하는」 경로를 막는 유일한 검사다.
      4. 아직 승인·반려 자식이 없는가 — 두 번째 결정은 409 다.

    ⚠️ 클라이언트가 보낸 지문을 믿지 않는다. `compiled_fingerprint` 는 **서버가**
      체크포인트에서 파생해 넘겨야 한다."""
    with ledger.transaction() as txn:
        return _decidable_in_txn(txn, request_event_id, project_id=project_id,
                                 compiled_fingerprint=compiled_fingerprint)


def _decidable_in_txn(txn: Any, request_event_id: str, *, project_id: str,
                      compiled_fingerprint: str) -> Dict[str, Any]:
    """위 네 검사의 **본체**. 트랜잭션 안에서만 부른다.

    ⚠️ 검사와 기록이 다른 트랜잭션이면, 두 사람이 동시에 승인 버튼을 눌렀을 때
      **둘 다 검사를 통과**하고 결정이 두 건 붙는다. 그래서 `record_decision` 은
      이 함수를 자기 트랜잭션 안에서 다시 부른다."""
    if not request_event_id:
        raise ReviewRequestError("결정할 검토 요청이 지정되지 않았습니다.")
    rows = txn.find_events(subject_type=SUBJECT_TYPE, limit=100000)
    ev = next((r for r in rows if r.get("event_id") == request_event_id), None)
    if ev is None:
        raise ReviewRequestError(f"존재하지 않는 검토 요청입니다: {request_event_id}")
    if ev.get("event_type") != EVENT_REVIEW_REQUESTED:
        raise ReviewRequestError(
            f"검토 요청 이벤트가 아닙니다({ev.get('event_type')}) — 승인은 검토 요청에만 "
            f"붙습니다.")
    if str(ev.get("project_id", "")) != str(project_id):
        raise ReviewRequestError("다른 프로젝트의 검토 요청입니다.")
    if str(ev.get("subject_id", "")) != str(compiled_fingerprint or ""):
        raise ReviewRequestError(
            f"요청 당시 계약과 현재 계약이 다릅니다(요청 {str(ev.get('subject_id'))[:12]}… "
            f"→ 현재 {str(compiled_fingerprint or '')[:12]}…) — 그 승인은 지금 계약을 "
            f"본 승인이 아닙니다. 다시 검토해야 합니다.")
    decided = set(txn.child_event_types(request_event_id)) & {EVENT_APPROVED, EVENT_REJECTED}
    if decided:
        raise ReviewRequestError(
            f"이미 결정된 검토 요청입니다({sorted(decided)[0]}) — 같은 요청에 두 번째 "
            f"결정을 붙이지 않습니다.")
    return ev


def record_decision(ledger: Any, decision: GateDecision, *,
                    project_id: str, request_event_id: str, approved: bool,
                    actor_id: str = "", rationale: str = "", task_id: str = "",
                    tenant_id: str = "tenant_default", enterprise_scope_id: str = "",
                    entity_mode: str = "REAL") -> Dict[str, Any]:
    """사람의 승인·반려를 원장에 남긴다. **요청 이벤트에 이어 붙인다.**

    ★★★ 검사와 기록이 **한 트랜잭션**이다. 나누면 두 사람이 동시에 눌렀을 때 둘 다
      검사를 통과하고 결정이 두 건 붙는다 — 그러면 「승인됐나 반려됐나」에 원장이
      두 답을 준다.

    ⚠️ **자동 통과는 여기로 오지 않는다.** 사람이 판단하지 않은 일을 승인으로 쌓으면
      원장에서 승인 건수를 세는 순간 실제보다 많아지고, 그 숫자는 「우리는 계약을
      N번 검토했다」로 읽힌다.
    ⚠️ 기록 실패는 삼키지 않는다 — 승인 이력이 없는 승인은 승인이 아니다."""
    if decision.verdict != REVIEW_REQUIRED:
        raise ReviewRequestError(
            f"«{decision.verdict}» 판정에는 결정을 붙이지 않습니다. 사유: {decision.reason}")

    with ledger.transaction() as txn:
        _decidable_in_txn(txn, request_event_id, project_id=project_id,
                          compiled_fingerprint=decision.compiled_fingerprint)
        return txn.append(
            event_type=EVENT_APPROVED if approved else EVENT_REJECTED,
            subject_type=SUBJECT_TYPE,
            subject_id=decision.compiled_fingerprint,
            actor_type="user",
            actor_id=actor_id,
            decision="승인" if approved else "반려",
            rationale=rationale or decision.reason,
            #: 승인 이전 지문도 함께 남긴다 — 「무엇에서 무엇으로 바뀐 승인인가」가
            #: 지문 하나만으로는 복원되지 않는다.
            evidence_refs=[{"compiled_fingerprint": decision.compiled_fingerprint,
                            "previous_approved_fingerprint": decision.approved_fingerprint,
                            "task_id": task_id}],
            #: ★ 이 한 줄이 「요청과 결정의 연결」이다. 없으면 승인이 무엇을 본
            #:   승인인지 원장만으로는 복원되지 않는다.
            parent_event_id=request_event_id,
            project_id=project_id, tenant_id=tenant_id,
            enterprise_scope_id=enterprise_scope_id, entity_mode=entity_mode)


def evaluate_project(tasks: Any, state: Any) -> Tuple[GateDecision, List[str]]:
    """WBS 전체를 보고 `(판정, 계약 대상 태스크 목록)` 을 돌려준다.

    ★ WBS 쪽 판정(`wbs_artifact_kind`)과 게이트 판정을 **여기서 한 번만** 잇는다 —
      두 곳에서 이으면 [I-4 2.2a] 처럼 두 계층의 답이 갈린다.

    ⚠️ 판정은 **태스크당 하나가 아니라 프로젝트당 하나**다. `ProjectState` 5.2.0 은
      계약 지문을 프로젝트 수준에 하나만 들고 있기 때문이다. 태스크마다 다른 답을
      내는 것처럼 보이는 API 를 만들면, 나중에 그것을 믿고 태스크별로 다른 계약을
      결속하려다 어긋난다 — 목록과 판정을 **따로** 돌려주는 이유가 그것이다."""
    from core import wbs_artifact_kind as _ak

    required = _ak.contract_required_task_ids(tasks)
    return evaluate_state(state, requires_contract=bool(required)), required
