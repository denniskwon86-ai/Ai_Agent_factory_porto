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
        note=descriptor.coverage_note)


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
    rows = store.staged_rows(job_id=job_id, limit=5000)
    if not rows:
        return PromotionReport(job_id=job_id, next_actions=(
            "이 작업에 적재된 행이 없습니다. 먼저 dry-run 과 apply 를 완료하십시오.",))

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

        try:
            intel.record_observation(
                indicator_code=code, observed_at=observed_at, value=float(value),
                vintage=str(payload.get("vintage_date") or observed_at),
                grade=str(payload.get("trust_grade") or grade_default),
                source_id=str(payload.get("source_id") or ""),
                published_at=str(payload.get("published_at") or ""),
                unit=str(payload.get("unit") or ""),
                #: ★ 계보의 마지막 고리 — 관측값에서 원문 파일까지 되짚는다.
                source_record_ref=str(row.get("raw_object_ref") or ""),
                note="수집 작업 " + job_id + " 에서 승격")
            promoted += 1
        except Exception as exc:                              # noqa: BLE001
            rejected.append(Rejected(key, REJECT_GATE, str(exc)[:220]))

    actions: List[str] = []
    if missing:
        actions.append("먼저 지표를 등록하십시오: " + " · ".join(missing)
                       + " (또는 register_missing 을 명시하십시오)")
    if any(r.reason == REJECT_GATE and "승인되지 않은" in r.detail for r in rejected):
        actions.append("원천이 아직 승인되지 않았습니다 — 데이터 관리자가 승인해야 "
                       "관측값으로 올라갑니다(§12.4).")
    if promoted:
        actions.append("계획 동인(plan_drivers)에 이 지표를 external_code 로 연결하면 "
                       "시나리오가 실제 관측값으로 계산됩니다.")

    return PromotionReport(job_id=job_id, contract_key=contract, considered=len(rows),
                           promoted=promoted, rejected=tuple(rejected),
                           indicators_registered=tuple(registered),
                           next_actions=tuple(actions))
