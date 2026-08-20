"""★★★ 계산 **Capability Registry.** (§7 5a · 2026-08-21)

## 이것은 계산기가 아니다

여기서는 **숫자를 하나도 만들지 않는다.** 이 파일이 답하는 질문은 둘뿐이다:

    이 계산 참조가 계약에 있는가?
    지금 실행할 수 있는가 — 없다면 **무엇이 막고 있는가?**

⚠️⚠️ 그래서 **5a 완료를 「계산 연동 완료」로 보고하지 않는다.** 이름을 부를 수 있는
  자리가 생겼을 뿐이고, 그 자리는 전부 비어 있다.

## 왜 비워 두는가 — 같은 「재고」가 다른 것을 가리킨다

기존 엔진(`calc_graph`)과 계약은 재고를 정반대로 쓴다:

    기존 엔진   지연 ↑ → 생산 ↓ → 기말재고 ↑   (안 쓰고 **남은** 원료)
    계약        지연 ↑ → 가용재고 ↓ → 생산 ↓   (**쓸 수 있는** 원료)

⚠️⚠️ 이름만 이으면 화면에 「지연 15일 → 재고 +230톤」이 뜬다. 숫자는 계산되고 단위도
  맞고 지문도 결정론적이다. **그런데 뜻이 반대다.** 그 화면을 본 사람은 「재고가
  늘었으니 여유가 있다」고 읽고, 실제로는 원료가 없어 라인이 선다.

★ 「참조가 있다」를 「계산이 된다」로 바꿔 적는 것보다 나쁘다 — 뒤엣것은 비어 있어서
  아무도 속지 않지만, 앞엣것은 **채워져 있어서** 속는다.

## fail-closed

    모르는 참조        → 거부
    NOT_IMPLEMENTED   → 거부
    범위 밖            → 거부
    저장소·모델 장애    → 거부

⚠️ 0·빈 결과·기존 scenario engine 으로 **접지 않는다.** 그렇게 접으면 「계산이 안
  됐다」가 「영향이 없다」로 보이고, 그것이 이 저장소가 계속 잡아 온 고장이다.

LLM 0콜.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

# ── 실행 상태 ────────────────────────────────────────────────────────────
#: 계약에 있고 **아직 구현되지 않았다.**
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
#: 계약에는 있으나 이번 MVP **범위 밖**이다. ⚠️ 「빠뜨린 것」과 다르다.
OUT_OF_SCOPE = "OUT_OF_SCOPE"
#: 구현됐고 **승인 전**이다. 실행하지 않는다.
IMPLEMENTED_UNAPPROVED = "IMPLEMENTED_UNAPPROVED"
#: 구현됐고 승인됐다. 실행할 수 있다.
APPROVED = "APPROVED"

CAPABILITY_STATES: Tuple[str, ...] = (NOT_IMPLEMENTED, OUT_OF_SCOPE,
                                      IMPLEMENTED_UNAPPROVED, APPROVED)

#: ★★★ **실행할 수 있는 상태는 하나뿐이다.**
#: ⚠️ 이 집합을 넓히는 것은 승인 없는 계산을 하나 허용하는 일이다.
EXECUTABLE = frozenset({APPROVED})


class CapabilityError(Exception):
    """계산 능력에 관한 거부. ⚠️ 사유가 **반드시** 붙는다."""


@dataclass(frozen=True)
class Capability:
    """계산 참조 하나의 계약.

    ⚠️ 「무엇을 넣고 무엇이 나오는가」를 적지 않으면, 나중에 아무 계산이나 이 이름에
      꽂힐 수 있다. 그때는 이름이 뜻을 보증하지 못한다."""

    ref: str
    #: 어느 관계의 계산인가 — 계약의 `subject -relation-> object`.
    subject_type: str
    relation: str
    object_type: str
    #: 이 계산에 들어가야 하는 계약키(인증판이 있어야 한다).
    required_datasets: Tuple[str, ...]
    #: 무엇이 나오는가 — (지표, 단위, 부호 방향). §5-0 §2 의 어휘를 그대로 쓴다.
    outputs: Tuple[Tuple[str, str, str], ...]
    state: str
    #: 왜 못 쓰는가. ⚠️ `APPROVED` 가 아니면 **비어 있을 수 없다.**
    blocked_reason: str = ""
    #: 산식 판. 바뀌면 지문이 바뀌고 옛 실행 증명이 무효가 된다.
    model_version: str = ""
    effective_from: str = ""
    effective_to: str = ""
    #: 승인 원장 이벤트. ⚠️ 없으면 `APPROVED` 가 될 수 없다.
    ledger_event_id: str = ""
    mvp_scope: bool = True

    def __post_init__(self) -> None:
        if self.state not in CAPABILITY_STATES:
            raise ValueError(f"state must be one of {CAPABILITY_STATES}: {self.state!r}")
        if self.state != APPROVED and not self.blocked_reason.strip():
            #: ★ 사유 없는 차단은 나중에 「왜 막혔지?」에 답할 수 없고, 그러면 아무도
            #:   되돌리지 못한다(원장의 비활성화 사유와 같은 규칙).
            raise ValueError(f"{self.ref}: 실행 불가 상태에는 사유가 필요합니다.")
        if self.state == APPROVED and not self.ledger_event_id.strip():
            #: ⚠️⚠️ 승인 원장 없이 `APPROVED` 가 되면 **누가 승인했는지 없는 승인**이다.
            raise ValueError(f"{self.ref}: 승인 원장 없이 APPROVED 가 될 수 없습니다.")
        if self.state == APPROVED and not self.model_version.strip():
            raise ValueError(f"{self.ref}: 산식 판 없이 APPROVED 가 될 수 없습니다.")

    @property
    def executable(self) -> bool:
        return self.state in EXECUTABLE

    def fingerprint(self) -> str:
        """이 능력의 **결정론적 지문.** 계약이 바뀌면 값이 바뀐다.

        ★ 실행 증명이 이 값을 함께 싣는다 — 나중에 산식이 바뀌면 옛 증명이 **스스로
          무효**임을 드러낸다. 「같은 판인데 다른 답」을 막는 축이다."""
        body = json.dumps({
            "ref": self.ref, "relation": f"{self.subject_type}-{self.relation}->{self.object_type}",
            "datasets": list(self.required_datasets),
            "outputs": [list(o) for o in self.outputs],
            "state": self.state, "model_version": self.model_version,
            "effective_from": self.effective_from, "effective_to": self.effective_to,
            #: ★★★ [2026-08-21 감사] **범위와 승인도 지문에 든다.**
            #: ⚠️ `mvp_scope` 를 빼면 「범위 밖이던 것을 범위 안으로 옮긴」 변경이
            #:   지문을 안 바꾸고, 옛 실행 증명이 그대로 유효해 보인다.
            #: ⚠️ 승인 이벤트가 바뀌는 것도 **다른 승인**이다.
            "mvp_scope": bool(self.mvp_scope),
            "ledger_event_id": self.ledger_event_id,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


#: ★★★ [2026-08-21] **계약 안에서는 코드를 쓴다.** 한글은 화면 표시명으로 분리한다.
#:
#: ⚠️ 계약에 「일」·「원」을 적으면 그 문자열이 비교·집계에 쓰이게 되고, 표기를 다듬는
#:   순간 **판정이 조용히 바뀐다**(격리 «사유» 와 «종류» 를 가른 것과 같은 규칙).
UNIT_TON, UNIT_DAY, UNIT_KRW = "TON", "DAY", "KRW"
UNITS: Tuple[str, ...] = (UNIT_TON, UNIT_DAY, UNIT_KRW)
UNIT_DISPLAY: Dict[str, str] = {UNIT_TON: "톤", UNIT_DAY: "일", UNIT_KRW: "원"}

#: 부호 방향도 코드로 둔다 — 산문으로 두면 문구를 고칠 때 뜻이 흔들린다.
UP, DOWN = "UP", "DOWN"
DIRECTIONS: Tuple[str, ...] = (UP, DOWN)

#: §5-0 §2 에서 확정한 지표 어휘. ⚠️ 부호 방향까지 함께 못 박는다 —
#: 방향을 안 적으면 「재고 +230」이 좋은 소식인지 나쁜 소식인지 두 사람이 다르게 읽는다.
#: ⚠️⚠️ [2026-08-21 감사] `on_hand_qty` 는 **네 칸의 합이 아니다.**
#:   `safety_stock_quantity` 는 물리적 재고가 아니라 **정책 기준량**이다(실측: 540행
#:   전부 50.0). 합에 넣으면 있지도 않은 재고를 세게 된다.
#:
#:       on_hand_qty   = unrestricted + quality + blocked
#:       available_qty = max(unrestricted − safety_stock − reserved, 0)
#:
#: ⚠️ `reserved_quantity` 는 **현재 데이터에 없다.** 0 으로 가정하고 그 사실을 여기
#:   적어 둔다 — 안 적으면 다음 사람이 「예약이 없는 회사」로 읽는다.
_AVAILABLE = ("available_qty", UNIT_TON, DOWN)
_IN_TRANSIT = ("in_transit_qty", UNIT_TON, UP)
_SHORTAGE = ("shortage_qty", UNIT_TON, UP)
_PRODUCIBLE = ("producible_qty", UNIT_TON, DOWN)
#: ⚠️⚠️ 두 지표를 **가른다.**
#:   `delivery_delay_days` 는 이미 일어난 납기 지연 **실적**(출하일 − 약속일)이고,
#:   `revenue_shift_days` 는 시나리오와 기준선의 **예상 인식일 차이**다.
#: ★ 앞엣것을 뒤엣것으로 쓰면 「시뮬레이션 결과」라며 **과거 실적을 보여 주게** 된다.
_REVENUE_SHIFT = ("revenue_shift_days", UNIT_DAY, UP)


#: ★★★ 계약이 요구하는 계산 참조. **닫힌 목록**이고 계약의 넷과 일대일이다.
#:
#: ⚠️⚠️ 넷 다 `NOT_IMPLEMENTED`·`OUT_OF_SCOPE` 다. 하나라도 `APPROVED` 로 올리려면
#:   §5-0 의 의미 계약이 승인되고, 산식이 구현되고, 승인 원장이 있어야 한다.
#: ⚠️ 「일단 켜 놓고 나중에 검증」은 하지 않는다 — 켜진 순간 화면이 숫자를 보여 주고,
#:   그 숫자는 검증 여부와 무관하게 회의에 올라간다.
_REGISTRY: Dict[str, Capability] = {
    c.ref: c for c in (
        Capability(
            ref="CALC.LOGISTICS.ARRIVAL_DELAY.v1",
            subject_type="shipment", relation="AFFECTS",
            object_type="inventory-snapshot",
            #: ⚠️⚠️ [2026-08-21 감사] `LOG-03` 이 **반드시** 있어야 한다. `eta` 는
            #:   «예정» 시점이고, 운송 중 여부는 실제 출발·도착으로 가른다:
            #:       ETD(또는 실제 출발) ≤ as_of  AND  ATA > as_of
            #:   실측: `LOG-02.status` 는 120건 **전부 DELIVERED** 이고 실제 도착은
            #:   `LOG-03` 의 `ATA` 사건에만 있다. 예정으로 판정하면 이미 도착한 배를
            #:   «운송 중» 으로 세게 된다.
            required_datasets=("LOG-02", "LOG-03", "INV-01"),
            outputs=(_IN_TRANSIT, _AVAILABLE),
            state=NOT_IMPLEMENTED,
            blocked_reason=(
                "승인된 지연 모델이 없습니다. 기존 계산 엔진은 «안 쓰고 남은» 재고를 "
                "올리므로 부호의 뜻이 반대입니다 — 이름만 이으면 「재고가 늘었으니 "
                "여유가 있다」로 읽히고 실제로는 라인이 섭니다. 또한 운송 중 판정에 "
                "예정 시각이 아니라 실제 도착 사건이 필요합니다.")),
        Capability(
            ref="CALC.INVENTORY.MATERIAL_SHORTAGE.v1",
            subject_type="inventory-snapshot", relation="AFFECTS",
            object_type="production-plan-line",
            #: ⚠️⚠️ [2026-08-21 감사] **낟알이 맞지 않아 `MDM-05` 가 필요하다.**
            #:   `INV-01` 은 자재×창고×일자인데 `MFG-01.material_requirement` 는 여러
            #:   BOM 투입을 합친 **계획행 총량**이다. 단일 자재 재고와 바로 뺄 수 없다.
            #:
            #:       계획행 → BOM 투입자재 → 자재별 필요량·수율
            #:              → 같은 자재·사업장 가용재고 → 자재별 부족량
            #:
            #: ⚠️ 실측에서 하나 더 나왔다 — `material_requirement` 66.4 가 BOM×수율로
            #:   계산한 67.35 와 **맞지 않는다.** 어느 쪽이 정본인지 5b 에서 정해야 한다.
            required_datasets=("INV-01", "MFG-01", "MDM-05"),
            outputs=(_SHORTAGE, _PRODUCIBLE),
            state=NOT_IMPLEMENTED,
            blocked_reason=(
                "재고를 «원인» 으로 받는 계산이 없습니다. 기존 엔진은 재고를 생산의 "
                "«결과» 로 계산하므로 인과 방향이 반대입니다. 또한 가용 원료와 완제품 "
                "계획을 BOM 소요계수·수율 없이 직접 비교할 수 없습니다.")),
        Capability(
            ref="CALC.PRODUCTION.REVENUE_TIMING.v1",
            subject_type="production-plan-line", relation="AFFECTS",
            object_type="sales-line",
            #: ⚠️⚠️ [2026-08-21 감사] `actual_ship_date − due_date` 는 **이미 일어난
            #:   납기 지연 실적**(`delivery_delay_days`)이지 시뮬레이션 결과가 아니다.
            #:   `revenue_shift_days` 는 **시나리오 예상 인식일 − 기준선 예상 인식일**
            #:   이고, 승인된 생산-판매 배분과 **기준선**이 있어야 계산할 수 있다.
            #: ★ 앞엣것을 뒤엣것으로 쓰면 「시뮬레이션 결과」라며 과거 실적을 보여 준다.
            required_datasets=("MFG-01", "SLS-01"),
            outputs=(_REVENUE_SHIFT,),
            state=NOT_IMPLEMENTED,
            blocked_reason=(
                "매출 «인식 시점» 을 내는 계산이 없습니다. 실적 납기 지연은 시나리오 "
                "이연이 아니며, 기준선과 승인된 생산-판매 배분이 있어야 합니다.")),
        Capability(
            ref="CALC.FINANCE.COST_MARGIN_CASH.v1",
            subject_type="cost-record", relation="AFFECTS", object_type="ledger-line",
            required_datasets=("FIN-01", "FIN-03"),
            outputs=(("margin_delta", UNIT_KRW, DOWN),
                     ("cash_delta", UNIT_KRW, DOWN)),
            state=OUT_OF_SCOPE, mvp_scope=False,
            blocked_reason=(
                "MVP 최소 경로 4관계 밖입니다 — cost-record → ledger-line 은 그 사슬과 "
                "떨어져 있습니다. **빠뜨린 것이 아니라 범위 밖**입니다.")),
    )
}


def known_refs() -> Tuple[str, ...]:
    """계약이 요구하는 참조 전부(범위 밖 포함)."""
    return tuple(sorted(_REGISTRY))


def mvp_refs() -> Tuple[str, ...]:
    """MVP 최소 경로가 지나는 참조만."""
    return tuple(sorted(r for r, c in _REGISTRY.items() if c.mvp_scope))


def get(ref: str) -> Capability:
    """능력 하나. **모르는 참조는 거부한다.**

    ⚠️ 모르는 이름을 `None` 으로 돌려주면 호출부가 「없으니 건너뛰자」로 접는다.
      그러면 계약에 없는 계산이 조용히 실행되지 않고 지나간다."""
    cap = _REGISTRY.get(str(ref or "").strip())
    if cap is None:
        raise CapabilityError(
            f"계약에 없는 계산 참조입니다: {ref or '(없음)'} — "
            f"가능한 것은 {list(known_refs())} 입니다.")
    return cap


def assert_executable(ref: str, ledger_verifier: Optional[Any] = None) -> Capability:
    """실행 직전 관문. **통과하지 못하면 예외**이고, 사유가 붙는다.

    ★★★ 0·빈 결과·기존 엔진 fallback 으로 **접지 않는다.**
    ⚠️⚠️ 접으면 「계산이 안 됐다」가 「영향이 없다」로 보인다. 화면은 평온하고 사람은
      그것을 사실로 읽는다 — 이 저장소가 계속 잡아 온 바로 그 고장이다.

    ## ⚠️⚠️ 승인은 **매번** 원장에서 다시 확인한다

    등록부의 `state` 는 «그때 그랬다» 이지 «지금도 그렇다» 가 아니다. 승인은 **철회될
    수 있고**, 철회는 등록부를 고치지 않는다.

    ★ 그래서 `APPROVED` 를 실행하려면 `ledger_verifier(cap)` 가 있어야 하고, 그것이
      참을 돌려줘야 한다. 검증기가 **없으면 실행하지 않는다** — 「검증기를 안 넘겼으니
      그냥 통과」는 승인 확인을 통째로 건너뛰는 문이다.

    ⚠️ 지금은 아무것도 `APPROVED` 가 아니므로 이 길은 한 번도 돌지 않는다. 그래도 지금
      넣는다 — 승인이 생긴 뒤에 넣으면 **그 사이에 승인 없는 실행이 지나간다.**"""
    cap = get(ref)
    if not cap.executable:
        raise CapabilityError(f"{cap.ref} 을(를) 실행할 수 없습니다 "
                              f"[{cap.state}]: {cap.blocked_reason}")
    if ledger_verifier is None:
        raise CapabilityError(
            f"{cap.ref}: 승인 원장을 확인할 방법 없이 실행하지 않습니다.")
    try:
        confirmed = bool(ledger_verifier(cap))
    except Exception as exc:
        #: ⚠️ 원장을 못 읽은 것을 «승인 없음» 도 «승인 있음» 도 아닌 **장애**로 올린다.
        raise CapabilityError(
            f"{cap.ref}: 승인 원장을 확인하지 못했습니다: {exc}") from exc
    if not confirmed:
        raise CapabilityError(
            f"{cap.ref}: 승인이 확인되지 않았습니다(철회됐거나 대상이 다릅니다).")
    return cap


def report() -> Dict[str, Dict[str, object]]:
    """지금 무엇이 실행 가능하고 무엇이 왜 막혀 있는가.

    ★ 화면·보고서가 이것을 그대로 보여 준다 — 「왜 숫자가 없나」에 답할 수 있어야 한다.
    ⚠️ 존재하지 않는 능력을 지어내지 않는다. 여기 없는 이름은 계약에도 없다."""
    return {ref: {"state": cap.state, "executable": cap.executable,
                  "mvp_scope": cap.mvp_scope, "blocked_reason": cap.blocked_reason,
                  "relation": f"{cap.subject_type} -{cap.relation}-> {cap.object_type}",
                  "required_datasets": list(cap.required_datasets),
                  "outputs": [list(o) for o in cap.outputs],
                  "model_version": cap.model_version,
                  "fingerprint": cap.fingerprint()}
            for ref, cap in sorted(_REGISTRY.items())}


def registry_fingerprint() -> str:
    """레지스트리 전체의 지문. ⚠️ 하나라도 바뀌면 값이 바뀐다 — 옛 실행 증명이
    스스로 무효임을 드러내는 축이다."""
    body = "|".join(f"{ref}:{cap.fingerprint()}" for ref, cap in sorted(_REGISTRY.items()))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
