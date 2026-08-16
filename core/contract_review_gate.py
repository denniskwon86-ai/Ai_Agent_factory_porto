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


def record_decision(ledger: Any, decision: GateDecision, *,
                    project_id: str, task_id: str = "",
                    actor_id: str = "", approved: Optional[bool] = None,
                    rationale: str = "") -> Optional[Dict[str, Any]]:
    """게이트 결과를 원장에 남긴다. 남길 것이 없으면 `None`.

    ⚠️ **자동 통과는 원장에 남기지 않는다.** 사람이 판단하지 않은 일을 「승인」으로
      쌓으면, 원장에서 승인 건수를 세는 순간 실제보다 많아진다 — 그리고 그 숫자는
      「우리는 계약을 N번 검토했다」로 읽힌다.
    ⚠️ 기록 실패는 삼키지 않는다(`DecisionLedger.append` 의 규칙 그대로) — 승인
      이력이 없는 승인이 생기면 그것은 승인이 아니다."""
    if not decision.needs_human:
        return None

    if approved is None:
        event = EVENT_REVIEW_REQUESTED
        verdict_text = "검토 요청"
    else:
        event = EVENT_APPROVED if approved else EVENT_REJECTED
        verdict_text = "승인" if approved else "반려"

    return ledger.append(
        event_type=event,
        subject_type=SUBJECT_TYPE,
        subject_id=decision.compiled_fingerprint,
        actor_type="user" if approved is not None else "system",
        actor_id=actor_id,
        decision=verdict_text,
        rationale=rationale or decision.reason,
        #: 승인 이전 지문도 함께 남긴다 — 「무엇에서 무엇으로 바뀐 승인인가」가
        #: 지문 하나만으로는 복원되지 않는다.
        evidence_refs=[{"compiled_fingerprint": decision.compiled_fingerprint,
                        "previous_approved_fingerprint": decision.approved_fingerprint,
                        "task_id": task_id}],
        project_id=project_id,
    )


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
