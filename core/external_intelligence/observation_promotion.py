"""[F-6] 격리 적재본 → 외생 지표 관측값 «승격» — Q2 가 막혀 있던 이유.

## 무엇이 끊겨 있었나

F-0 탐침이 찾아낸 것: 계획 동인(`plan_drivers`)이 0건이고, 그래서 경영자의 Q2
「환율·원자재가 바뀌면 어느 부서·계정에 영향?」에 답할 경로가 없다.

파고들었더니 기계적 원인은 **두 저장소가 만나지 않는 것**이었다:

    수집 오케스트레이터  →  `data_acquisition_rows`      (격리 적재본)
    계획이 읽는 것       →  `external_observations`
                             ↑ 둘을 잇는 코드가 «없었다»

`planning_drivers.resolve_external_change()` 는 `external_intelligence.resolve_value()`
를 부르고, 그것은 `external_observations` 를 읽는다. 그래서 Provider 를 다섯 개 만들어도
계획에는 한 방울도 흐르지 않았다.

## 이 모듈이 «하지 않는» 것 — 경계가 요점이다

★★★ **관문을 다시 만들지 않는다.** `record_observation()` 이 이미 강제한다:
  vintage 필수(§12.5) · **승인된 원천만**(§12.4) · 출처보다 높은 등급 금지.
  여기서 재구현하면 두 곳이 어긋나고 한쪽만 고쳐졌을 때 정책이 조용히 뚫린다.

★★★ **`EXT-*` 만 승격한다.** `PUB-01`(공시 재무제표)은 지표가 아니다 — 그것을 관측값으로
  올리면 「외생 지표」와 「회사 실적」이 한 통에 섞인다. 계약 키로 막는다.

★★★ **원천 승인은 사람이 한다.** 이 모듈은 `register_source()` 까지만 하고
  `approve_source()` 는 부르지 않는다. 승인은 「이 출처의 값을 회사 계획에 쓴다」는
  결정이고, 그것을 코드가 대신하면 §12.4 가 장식이 된다.
  ⚠️ 그래서 승인 전에는 승격이 **전부 거부된다.** 그것이 정상이다.

★★★ **지표를 말없이 만들지 않는다.** 없는 지표는 사유와 함께 거부하고, 무엇을 등록해야
  하는지 알려 준다. `register_missing=True` 를 «명시»해야 만든다 — 어휘를 자동 생성하면
  같은 뜻의 지표가 둘 생기고 그때부터 집계가 조각난다.

## 계보는 끊기지 않는다

`source_record_ref` 에 원문 참조(`raw_object_ref`)를 넣는다. 그래서 계획에 쓰인 값에서
원문 파일까지 되짚을 수 있다 — 「그 판단은 어떤 데이터에 근거했나」(Q4)의 마지막 고리다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am


class PromotionError(ValueError):
    pass


#: ★ 승격 가능한 계약. **`PUB-01` 은 없다** — 공시 재무제표는 외생 지표가 아니다.
PROMOTABLE_CONTRACTS: Tuple[str, ...] = ("EXT-01", "EXT-02", "EXT-03")

#: 거부 사유 — 닫힌 어휘. 화면·집계가 이 코드로 묶는다.
REJECT_CONTRACT = "승격 대상 계약이 아닙니다"
REJECT_NO_INDICATOR = "등록되지 않은 지표입니다"
REJECT_NO_VALUE = "값 또는 관측 시점이 없습니다"
REJECT_ORIGIN = "외생 지표가 아닌 성격입니다"
REJECT_GATE = "관측값 등록 관문이 거부했습니다"
#: ★★★ [2026-09-09 Codex 지적] 빈 원천 ID 는 «여기서» 막는다.
#:   `record_observation()` 은 `if source_id:` 로 감싸 **빈 값이면 승인 검사를 통째로
#:   건너뛴다.** 즉 아래 관문에 기대면 빈 값이 §12.4 를 우회한다 — 통제는 자기가 막을
#:   것에 기대면 안 된다. (재현 확인: 빈 source_id 로 관측값이 그냥 등록됐다.)
REJECT_NO_SOURCE = "원천 ID 가 비어 있습니다"
#: ⚠️ 장애를 «정상 차단»으로 접지 않는다. 승인 대기와 DB 장애는 다음 행동이 다르다.
REJECT_ERROR = "처리 중 오류가 났습니다"

#: 저장소가 한 번에 돌려주는 최대 행. **이 수에 닿으면 잘렸을 수 있다.**
STAGED_READ_LIMIT = 5000


@dataclass(frozen=True)
class Rejected:
    business_key: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class PromotionReport:
    """무엇이 올라갔고 무엇이 왜 안 올라갔나. **부분 성공을 성공으로 말하지 않는다.**"""
    job_id: str
    contract_key: str = ""
    considered: int = 0
    promoted: int = 0
    rejected: Tuple[Rejected, ...] = ()
    indicators_registered: Tuple[str, ...] = ()
    #: ⚠️ 사람이 다음에 무엇을 해야 하는가. 비어 있으면 화면이 「그래서 뭘 하지」에 답 못 한다.
    next_actions: Tuple[str, ...] = ()

    @property
    def accounted(self) -> bool:
        return self.considered == self.promoted + len(self.rejected)

    def as_dict(self) -> Dict[str, Any]:
        return {"job_id": self.job_id, "contract_key": self.contract_key,
                "considered": self.considered, "promoted": self.promoted,
                "rejected": [{"business_key": r.business_key, "reason": r.reason,
                              "detail": r.detail} for r in self.rejected],
                "indicators_registered": list(self.indicators_registered),
                "next_actions": list(self.next_actions),
                "accounted": self.accounted}


def _intel():
    from core.external_intelligence import external_intelligence
    return external_intelligence


def _policy_errors():
    """«정책이 막은 것»의 예외 유형. 장애와 갈라야 다음 행동이 갈린다."""
    from core.external_intelligence import ExternalIntelligenceError
    return (ExternalIntelligenceError, ValueError)


def register_provider_source(descriptor, *, owner_department: str = "") -> Dict[str, Any]:
    """Provider 카드를 «원천»으로 등록한다. **승인하지 않는다**(`enabled=0`).

    ⚠️ 카드의 값을 그대로 옮긴다 — 여기서 문구를 새로 만들면 화면이 보는 설명과 정책이
      보는 설명이 갈린다."""
    intel = _intel()
    existing = None
    for s in intel.list_sources():
        if s.get("name") == descriptor.name:
            existing = s
            break
    if existing:
        return existing
    return intel.register_source(
        name=descriptor.name, source_type=descriptor.source_type,
        base_url="https://" + descriptor.allowed_hosts[0] if descriptor.allowed_hosts else "",
        license_type=descriptor.license_url, allowed_usage=descriptor.allowed_usage,
        refresh_frequency=descriptor.refresh_frequency,
        owner_department=owner_department, trust_grade=descriptor.default_trust_grade,
        note=descriptor.coverage_note,
        #: ★★★ [2026-09-09 Codex 지적] **원천 id = provider_id 로 못 박는다.**
        #:   수집 행은 `orchestrator.py:587` 이 `provider_id`(예: WB_PINK_SHEET)를 담는데
        #:   등록은 `src_...` 를 발급했다. 그러면 승인 여부 이전에 «존재하지 않는 원천»으로
        #:   전부 거부된다 — 실제로 그랬다(재현 확인).
        #:   ⚠️ 매핑표를 따로 두지 않는다. 두면 언젠가 한쪽만 갱신된다.
        source_id=descriptor.provider_id)


def _row_payload(row: Mapping[str, Any]) -> Dict[str, Any]:
    """저장소가 `payload` 로 파싱해 준다. 최상위에는 봉투만 있다."""
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else {}


def promote(store, job_id: str, *, actor_id: str, register_missing: bool = False,
            grade_default: str = "silver") -> PromotionReport:
    """한 수집 작업의 격리 적재본을 «외생 지표 관측값»으로 올린다.

    ⚠️ 이 함수는 관문을 만들지 않는다 — `record_observation()` 이 거부하면 그 사유를
      그대로 담는다. 승인되지 않은 원천이면 **전부 거부되는 것이 정상**이다."""
    intel = _intel()
    rows = store.staged_rows(job_id=job_id, limit=STAGED_READ_LIMIT)
    if not rows:
        return PromotionReport(job_id=job_id, next_actions=(
            "이 작업에 적재된 행이 없습니다. 먼저 dry-run 과 apply 를 완료하십시오.",))
    #: ★★★ [2026-09-09 Codex 지적] 저장소가 5,000행에서 자른다. 그것을 모르고 세면
    #:   «실제보다 적게 세면서 accounted=True» 가 된다 — 정산이 거짓말을 한다.
    #:   ⚠️ 조용히 일부만 올리지 않는다. 아예 멈추고 사람에게 나누라고 말한다.
    if len(rows) >= STAGED_READ_LIMIT:
        return PromotionReport(
            job_id=job_id, contract_key=str(rows[0].get("contract_key") or ""),
            considered=0, next_actions=(
                "적재 행이 저장소 조회 한도(" + str(STAGED_READ_LIMIT) + "행)에 닿았습니다 — "
                "일부만 올리면 정산이 거짓이 되므로 승격을 중단했습니다.",
                "수집 작업을 기간·품목으로 나누어 다시 만드십시오."))

    contract = str(rows[0].get("contract_key") or "")
    if contract not in PROMOTABLE_CONTRACTS:
        return PromotionReport(
            job_id=job_id, contract_key=contract, considered=len(rows),
            rejected=tuple(Rejected(str(r.get("business_key") or ""), REJECT_CONTRACT,
                                    contract + " 은 외생 지표 계약이 아닙니다.")
                           for r in rows),
            next_actions=("외생 지표(" + " · ".join(PROMOTABLE_CONTRACTS) + ")만 관측값으로 "
                          "올릴 수 있습니다. 공시 재무제표는 회사 실적이지 지표가 아닙니다.",))

    promoted = 0
    rejected: List[Rejected] = []
    registered: List[str] = []
    missing: List[str] = []

    for row in rows:
        key = str(row.get("business_key") or "")
        payload = _row_payload(row)
        origin = str(row.get("data_origin") or "")
        if origin not in (am.ORIGIN_PUBLIC_DISCLOSED,):
            rejected.append(Rejected(key, REJECT_ORIGIN,
                                     "성격이 " + (origin or "(없음)") + " 입니다 — 외생 지표는 "
                                     "PUBLIC_DISCLOSED 여야 합니다."))
            continue

        code = str(payload.get("indicator_code") or "").strip()
        observed_at = str(payload.get("observed_at") or "").strip()
        value = payload.get("value")
        if not code or not observed_at or value is None:
            rejected.append(Rejected(key, REJECT_NO_VALUE,
                                     "indicator_code·observed_at·value 가 모두 필요합니다."))
            continue

        if not intel.get_indicator(code):
            if not register_missing:
                if code not in missing:
                    missing.append(code)
                rejected.append(Rejected(key, REJECT_NO_INDICATOR,
                                         code + " 를 먼저 등록하십시오."))
                continue
            intel.upsert_indicator(
                code, str(payload.get("commodity_name") or payload.get("item_name") or code),
                required_grade=str(payload.get("trust_grade") or grade_default),
                vintage_required=True)
            if code not in registered:
                registered.append(code)

        source_id = str(payload.get("source_id") or "").strip()
        if not source_id:
            #: ★★★ 아래 관문은 빈 값이면 승인 검사를 건너뛴다. 여기서 막지 않으면
            #:   §12.4 가 «빈 문자열 하나로» 우회된다.
            rejected.append(Rejected(key, REJECT_NO_SOURCE,
                                     "원천 ID 가 없으면 승인 여부를 판정할 수 없습니다 — "
                                     "빈 값은 검사를 건너뛰므로 여기서 막습니다(§12.4)."))
            continue

        try:
            intel.record_observation(
                indicator_code=code, observed_at=observed_at, value=float(value),
                vintage=str(payload.get("vintage_date") or observed_at),
                grade=str(payload.get("trust_grade") or grade_default),
                source_id=source_id,
                published_at=str(payload.get("published_at") or ""),
                unit=str(payload.get("unit") or ""),
                #: ★ 계보의 마지막 고리 — 관측값에서 원문 파일까지 되짚는다.
                source_record_ref=str(row.get("raw_object_ref") or ""),
                note="수집 작업 " + job_id + " 에서 승격")
            promoted += 1
        except _policy_errors() as exc:
            #: 정책이 «의도적으로» 막은 것 — 승인 대기·등급 미달 등.
            rejected.append(Rejected(key, REJECT_GATE, str(exc)[:220]))
        except Exception as exc:                              # noqa: BLE001
            #: ★★★ [2026-09-09 Codex 지적] 장애를 «정상 차단»으로 접지 않는다.
            #:   DB 장애를 「승인 대기」로 표시하면 사람이 승인하러 가서 헛수고한다.
            rejected.append(Rejected(key, REJECT_ERROR,
                                     type(exc).__name__ + ": " + str(exc)[:200]))

    actions: List[str] = []
    if missing:
        actions.append("먼저 지표를 등록하십시오: " + " · ".join(missing)
                       + " (또는 register_missing 을 명시하십시오)")
    if any(r.reason == REJECT_GATE and "승인되지 않은" in r.detail for r in rejected):
        actions.append("원천이 아직 승인되지 않았습니다 — 데이터 관리자가 승인해야 "
                       "관측값으로 올라갑니다(§12.4).")
    if any(r.reason == REJECT_GATE and "존재하지 않는 원천" in r.detail for r in rejected):
        actions.append("원천이 등록돼 있지 않습니다 — `register_provider_source()` 로 먼저 "
                       "등록하십시오(원천 id 는 provider_id 와 같습니다).")
    if any(r.reason == REJECT_NO_SOURCE for r in rejected):
        actions.append("원천 ID 가 빈 행이 있습니다 — 수집 경로가 provider_id 를 싣는지 "
                       "확인하십시오. 빈 값은 승인 검사를 건너뛰므로 올리지 않습니다.")
    if any(r.reason == REJECT_ERROR for r in rejected):
        #: ⚠️ 이것은 «승인하러 가라»가 아니다. 사람을 헛걸음시키지 않는다.
        actions.append("⚠️ 처리 중 오류가 났습니다 — 정책 거부가 아니라 «장애»입니다. "
                       "승인으로 풀리지 않으니 로그를 확인하십시오.")
    if promoted:
        actions.append("계획 동인(plan_drivers)에 이 지표를 external_code 로 연결하면 "
                       "시나리오가 실제 관측값으로 계산됩니다.")

    return PromotionReport(job_id=job_id, contract_key=contract, considered=len(rows),
                           promoted=promoted, rejected=tuple(rejected),
                           indicators_registered=tuple(registered),
                           next_actions=tuple(actions))
