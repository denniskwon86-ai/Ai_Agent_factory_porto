"""[DAO-6] 연결 추천과 스키마 매핑 — **제안은 AI 가, 적용 판정은 여기가.**

## 두 가지 일을 한다

    ① 라우팅   받아온 자료를 **어느 데이터 계약**에 둘 것인가(지시 5)
    ② 매핑     원천 필드를 **계약의 표준 필드**에 어떻게 잇는가(지시 6)

둘 다 「AI 가 제안하고 결정론적 검증기가 판정한다」는 같은 모양이다. 이 파일에는 LLM 호출이
0회다 — 제안을 **읽고 판정하는** 쪽만 있다.

## ★★★ 억지로 연결하지 않는다

지시 5 — 「기존 계약과 의미가 다르면 억지로 연결하지 말고 **새 데이터 계약 제안으로
분리**한다」. 라우팅표에 없는 자료를 가장 비슷한 계약에 밀어 넣으면, 그 계약을 읽는 쪽은
자기가 아는 뜻으로 읽는다. 공개 재무제표가 `FIN-03 예산·회계실적` 자리에 앉으면 상세
계산이 그것을 **내부 실적으로** 읽는다.

그래서 라우팅이 실패하면 `None` 을 돌려주고, 호출부는 `build_contract_proposal()` 로
**새 계약 제안**을 만든다. 제안은 인증된 키트를 건드리지 않는다 — 사람이 승인해야 계약이 된다.

## ★★★ 단위는 조용히 바뀌지 않는다

설계서 §6.1 — 「USD/MT 와 KRW/kg 혼용 → **명시적 환산 규칙 없으면 차단**」. 매핑이
`unit_conversion` 없이 단위가 다른 두 필드를 이으면 거부한다. 「대충 맞겠지」로 넘어간
환산은 나중에 자릿수로 돌아온다.

## ★★★ 계정과목 매핑은 자동 승인되지 않는다

`account_id` → 회사 계정과목은 **업무 판단**이다. 검증기는 「형식이 맞다」까지만 말하고
`requires_human_approval` 을 세운다. 형식 검사를 승인으로 읽으면, 아무도 보지 않은 계정
대응으로 손익이 만들어진다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am

#: ★★★ 지시 5 의 라우팅표. **이 표 하나만 있다.**
#:   자료의 성격(kind) → 데이터 계약 키. 표에 없으면 새 계약을 제안한다.
ROUTING_TABLE: Dict[str, str] = {
    "company_identity": "MDM-01",        # 회사·법인·종목 식별정보 → MDM 후보
    "public_financials": "PUB-01",       # DART 재무제표 → 공개 재무실적(신규)
    "fx_rate": "EXT-01",                 # 환율
    "interest_rate": "EXT-01",           # 금리
    "price_index": "EXT-01",             # 물가
    "commodity_price": "EXT-02",         # 원자재 가격
    "energy": "EXT-03",                  # 에너지
    "freight": "EXT-03",                 # 운임
    "weather": "EXT-03",                 # 기상
    "industry_indicator": "EXT-03",      # 산업지표
    "disclosure_document": "KNW-01",     # 공시·보고서 원문 → 지식·근거 저장소
}

#: 내부 상세 추정치는 계약이 아니라 **성격**으로 표시한다(지시 5 마지막 줄).
DERIVED_ORIGIN = am.ORIGIN_SYNTHETIC_DERIVED

#: 계약이 모든 데이터셋에 요구하는 공통 봉투. 기존 계약 35개가 전부 이 목록을 쓴다 —
#: 새 계약도 같아야 한다(`quality.required_common_fields`).
REQUIRED_COMMON_FIELDS: Tuple[str, ...] = (
    "record_id", "tenant_id", "scope_node_id", "data_class", "business_data_kind",
    "data_origin", "quality_status", "certification_status", "as_of_date", "lineage_id",
)

#: 시점을 담는 필드. **셋이 다 있어야** 「그 계획이 당시 어떤 발표값을 썼는가」에 답한다.
TEMPORAL_FIELDS: Tuple[str, ...] = ("as_of_date", "published_at", "vintage_date")

_UNIT_SHAPE = re.compile(r"^[A-Za-z0-9%/·_.-]{1,32}$")


class MappingError(ValueError):
    """매핑 제안이 관문을 통과하지 못했다 — 4xx 로 전달한다."""


@dataclass(frozen=True)
class RoutingSuggestion:
    """이 자료를 어디에 둘 것인가. `contract_key` 가 비면 **새 계약이 필요하다**는 뜻이다."""
    kind: str
    contract_key: str = ""
    reason: str = ""
    needs_new_contract: bool = False
    data_origin: str = ""


@dataclass(frozen=True)
class MappingProblem:
    source_field: str
    target_field: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class MappingReport:
    """매핑 검증 결과. **던지지 않는다** — dry-run 화면이 통째로 보여줘야 한다."""
    problems: Tuple[MappingProblem, ...] = ()
    unmapped_required: Tuple[str, ...] = ()
    #: ★ 형식은 맞지만 **사람이 봐야 하는** 항목(계정과목 대응 등).
    requires_human_approval: Tuple[str, ...] = ()
    conversions: Tuple[Mapping[str, Any], ...] = ()
    #: 매핑이 채우지 않고 **적용 시점에 시스템이 씌우는** 공통 봉투. 화면이 「이건 왜
    #: 비어 있나」에 답할 수 있어야 한다.
    system_assigned: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems and not self.unmapped_required

    @property
    def auto_appliable(self) -> bool:
        """★★★ 형식이 맞다 ≠ 적용해도 된다. 사람 승인이 걸린 항목이 하나라도 있으면 아니다."""
        return self.ok and not self.requires_human_approval


# ── ① 라우팅 ────────────────────────────────────────────────────────────────
def route(kind: str, *, known_contract_keys: Sequence[str],
          data_origin: str = "") -> RoutingSuggestion:
    """자료의 성격을 계약으로 옮긴다. **표에 없거나 계약이 없으면 새 계약을 제안한다.**"""
    k = str(kind or "").strip()
    known = {str(x) for x in known_contract_keys}
    if data_origin:
        am.assert_origin(data_origin)

    target = ROUTING_TABLE.get(k)
    if not target:
        return RoutingSuggestion(
            kind=k, needs_new_contract=True, data_origin=data_origin,
            reason=(f"라우팅표에 '{k}' 가 없습니다. 가장 비슷한 계약에 밀어 넣지 않습니다 — "
                    f"읽는 쪽이 자기가 아는 뜻으로 읽습니다."))
    if target not in known:
        return RoutingSuggestion(
            kind=k, contract_key=target, needs_new_contract=True, data_origin=data_origin,
            reason=(f"'{k}' 는 {target} 로 가야 하는데 그 계약이 아직 없습니다. "
                    f"새 계약으로 제안합니다."))
    return RoutingSuggestion(kind=k, contract_key=target, data_origin=data_origin,
                             reason=f"라우팅표: {k} → {target}")


def route_all(kinds: Sequence[str], *, known_contract_keys: Sequence[str]
              ) -> Tuple[Tuple[RoutingSuggestion, ...], Tuple[RoutingSuggestion, ...]]:
    """여러 성격을 한 번에. (연결된 것, 새 계약이 필요한 것)."""
    routed, pending = [], []
    for k in kinds:
        s = route(k, known_contract_keys=known_contract_keys)
        (pending if s.needs_new_contract else routed).append(s)
    return tuple(routed), tuple(pending)


# ── ② 매핑 검증 ─────────────────────────────────────────────────────────────
def validate_mapping(mapping: Sequence[Mapping[str, Any]], *,
                     contract: Mapping[str, Any],
                     source_fields: Sequence[str],
                     account_mapping_fields: Sequence[str] = ("account_id", "account_nm"),
                     ) -> MappingReport:
    """제안된 매핑이 **적용해도 되는지** 판정한다.

    각 항목: `{"source": 원천필드, "target": 계약필드, "source_unit": "", "target_unit": "",
              "unit_conversion": {"factor": 1000, "note": "..."} }`"""
    fields = _contract_fields(contract)
    known_targets = set(fields)
    required = {n for n, f in fields.items() if f.get("required")}
    sources = {str(s) for s in source_fields}

    problems: List[MappingProblem] = []
    conversions: List[Dict[str, Any]] = []
    needs_human: List[str] = []
    covered: set = set()
    seen_targets: Dict[str, str] = {}

    for entry in mapping:
        if not isinstance(entry, Mapping):
            problems.append(MappingProblem("", "", "매핑 항목이 객체가 아닙니다.", str(entry)[:80]))
            continue
        src = str(entry.get("source") or "").strip()
        tgt = str(entry.get("target") or "").strip()
        if not src or not tgt:
            problems.append(MappingProblem(src, tgt, "원천 필드와 대상 필드가 모두 필요합니다."))
            continue
        #: ★★★ 계약에 없는 필드를 만들어 내지 못한다.
        if tgt not in known_targets:
            problems.append(MappingProblem(
                src, tgt, "계약에 없는 대상 필드입니다 — 필드를 지어내지 않습니다.",
                f"계약이 아는 필드 {len(known_targets)}개"))
            continue
        if src not in sources:
            problems.append(MappingProblem(
                src, tgt, "원천에 없는 필드입니다 — 이번 응답에서 확인된 필드만 잇습니다.",
                f"원천 필드 {len(sources)}개"))
            continue
        #: 한 대상에 둘이 붙으면 어느 쪽이 이기는지 아무도 모른다.
        if tgt in seen_targets:
            problems.append(MappingProblem(
                src, tgt, "같은 대상 필드에 두 원천이 붙었습니다.", f"먼저: {seen_targets[tgt]}"))
            continue
        seen_targets[tgt] = src
        covered.add(tgt)

        #: ★★★ 단위가 다르면 **명시적 환산 규칙**이 있어야 한다.
        s_unit = str(entry.get("source_unit") or "").strip()
        t_unit = str(entry.get("target_unit") or "").strip()
        rule = entry.get("unit_conversion")
        for label, unit in (("source_unit", s_unit), ("target_unit", t_unit)):
            if unit and not _UNIT_SHAPE.match(unit):
                problems.append(MappingProblem(src, tgt, f"{label} 형식이 이상합니다.", unit))
        if s_unit and t_unit and s_unit != t_unit:
            factor = _factor(rule)
            if factor is None:
                problems.append(MappingProblem(
                    src, tgt, "단위가 다른데 환산 규칙이 없습니다 — 「대충 맞겠지」로 넘어간 "
                              "환산은 나중에 자릿수로 돌아옵니다.", f"{s_unit} → {t_unit}"))
            else:
                conversions.append({"source": src, "target": tgt, "from": s_unit,
                                    "to": t_unit, "factor": factor,
                                    "note": str((rule or {}).get("note") or "")})
        elif rule and _factor(rule) not in (None, 1.0):
            #: 단위가 같은데 환산이 붙어 있다 — 둘 중 하나가 거짓말이다.
            problems.append(MappingProblem(
                src, tgt, "단위가 같은데 환산 규칙이 있습니다 — 단위 표기나 규칙 중 하나가 "
                          "틀렸습니다.", f"{s_unit or '(없음)'} = {t_unit or '(없음)'}"))

        #: 계정과목 대응은 업무 판단이다 — 형식 검사를 승인으로 읽지 않는다.
        if src in set(account_mapping_fields) or tgt in set(account_mapping_fields):
            needs_human.append(f"{src} → {tgt}")

    #: ★★★ 공통 봉투는 **매핑의 책임이 아니다.** Provider 는 테넌트·범위를 모르는 것이
    #:   설계이고(`normalize()` 가 일부러 안 채운다), 적용 시점에 오케스트레이터가 씌운다.
    #:   ⚠️ 이것을 미매핑으로 세면 어떤 매핑도 통과하지 못하고, 그러면 사람이 검사를 끈다.
    system_assigned = tuple(sorted(f for f in REQUIRED_COMMON_FIELDS if f in known_targets))
    unmapped = tuple(sorted(required - covered - set(REQUIRED_COMMON_FIELDS)))
    #: 시점 필드가 빠지면 재현성이 조용히 깨진다 — 필수가 아니어도 짚는다.
    #: ⚠️ `as_of_date` 는 봉투라 시스템이 채운다. 여기서 보는 것은 **원천이 줘야만 아는**
    #:   `published_at`·`vintage_date` 다.
    for f in TEMPORAL_FIELDS:
        if f in REQUIRED_COMMON_FIELDS:
            continue
        if f in known_targets and f not in covered and f not in unmapped:
            problems.append(MappingProblem(
                "", f, "시점 필드가 매핑되지 않았습니다 — 「그 계획이 당시 어떤 발표값을 "
                       "썼는가」에 답할 수 없게 됩니다."))

    return MappingReport(problems=tuple(problems), unmapped_required=unmapped,
                         requires_human_approval=tuple(sorted(set(needs_human))),
                         conversions=tuple(conversions),
                         system_assigned=system_assigned)


def _factor(rule: Any) -> Optional[float]:
    if not isinstance(rule, Mapping):
        return None
    try:
        value = float(rule.get("factor"))
    except (TypeError, ValueError):
        return None
    return value if value != 0 else None


def _contract_fields(contract: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    raw = (contract or {}).get("schema", {})
    fields = raw.get("fields", []) if isinstance(raw, Mapping) else []
    return {str(f.get("name") or ""): f for f in fields
            if isinstance(f, Mapping) and f.get("name")}


# ── ③ 새 계약 제안 ──────────────────────────────────────────────────────────
def build_contract_proposal(*, dataset_id: str, dataset_name: str,
                            business_keys: Sequence[str],
                            domain_fields: Sequence[Mapping[str, Any]],
                            data_origin: str,
                            rationale: str,
                            provider_id: str = "",
                            allowed_scope_types: Optional[Sequence[str]] = None
                            ) -> Dict[str, Any]:
    """기존 계약 35개와 **같은 그릇**으로 새 계약을 제안한다.

    ⚠️ 인증된 키트를 건드리지 않는다. 이것은 제안 문서이고, `status` 가
      `PROPOSED` 다 — 사람이 승인해야 계약이 된다."""
    origin = am.assert_origin(data_origin)
    key = str(dataset_id or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}-\d{2}", key):
        raise MappingError(f"계약 키는 `ABC-01` 모양이어야 합니다: {dataset_id!r}")
    if not str(rationale or "").strip():
        raise MappingError("새 계약에는 «왜 기존 계약으로 안 되는가» 가 필요합니다 — "
                           "이유 없는 새 계약은 곧 두 번째 정본이 됩니다.")
    keys = [str(k).strip() for k in business_keys if str(k).strip()]
    if not keys:
        raise MappingError("업무 키가 없으면 같은 행인지 다른 행인지 판정할 수 없습니다.")

    fields: List[Dict[str, Any]] = [
        {"name": name, "type": "string", "required": True, "business_key": False,
         "description": f"{dataset_name}의 {name}"} for name in REQUIRED_COMMON_FIELDS]
    seen = set(REQUIRED_COMMON_FIELDS)
    for f in domain_fields:
        name = str((f or {}).get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        fields.append({
            "name": name, "type": str(f.get("type") or "string"),
            "required": bool(f.get("required", False)),
            "business_key": name in keys,
            "description": str(f.get("description") or f"{dataset_name}의 {name}"),
        })
    missing_keys = [k for k in keys if k not in seen]
    if missing_keys:
        raise MappingError(f"업무 키가 필드 목록에 없습니다: {missing_keys}")

    return {
        "dataset_id": key,
        "dataset_name": str(dataset_name or key),
        "contract_version": "0.1.0",
        #: ★ 인증된 계약과 **구별되는 상태**. 기존 35개는 `APPROVED_FOR_DEMO` 다.
        "status": "PROPOSED",
        "scope": {
            "tenant_required": True, "scope_required": True,
            "allowed_scope_types": list(allowed_scope_types or
                                        ["ENTERPRISE_GROUP", "LEGAL_ENTITY",
                                         "BUSINESS_DIVISION", "PLANT", "DEPARTMENT"]),
        },
        "classification": {
            "data_class": origin, "data_origin": origin,
            #: ★★★ 공개 자료는 사실이지만 내부 실적이 아니다.
            "not_for_management_decision": origin not in am.ORIGINS_FOR_INTERNAL_ACTUAL,
        },
        "business_keys": keys,
        "dependencies": [],
        "schema": {"fields": fields},
        "quality": {
            "required_common_fields": list(REQUIRED_COMMON_FIELDS),
            "fail_closed_on_scope_missing": True,
            "quarantine_on_reference_failure": True,
        },
        "lineage": {"generator": "core/external_intelligence/mapping.py",
                    "proposed_by_provider": str(provider_id or "")},
        "proposal": {"rationale": str(rationale).strip(),
                     "requires_human_approval": True},
    }


#: OpenDART 가 채울 `PUB-01` 의 도메인 필드. Provider 의 `normalize()` 출력과 **같은 이름**이다.
#: ⚠️ 이름이 갈리면 매핑 검증은 통과하는데 적재에서 빈 칸이 된다.
PUB01_DOMAIN_FIELDS: Tuple[Dict[str, Any], ...] = (
    {"name": "disclosure_row_id", "type": "string", "required": True,
     "description": "공시 재무 행의 업무 키(접수번호 + 재무제표구분 + 계정)"},
    {"name": "corp_code", "type": "string", "required": True, "description": "공시 법인코드"},
    {"name": "bsns_year", "type": "string", "required": True, "description": "사업연도"},
    {"name": "reprt_code", "type": "string", "required": True, "description": "보고서 종류"},
    {"name": "fs_div", "type": "string", "required": True,
     "description": "연결(CFS)·별도(OFS) 구분 — 섞으면 합계가 조용히 틀린다"},
    {"name": "fs_nm", "type": "string", "required": False, "description": "재무제표명"},
    {"name": "sj_div", "type": "string", "required": True, "description": "재무제표 종류"},
    {"name": "sj_nm", "type": "string", "required": False, "description": "재무제표 종류명"},
    {"name": "account_id", "type": "string", "required": True,
     "description": "공시 계정 식별자 — 회사 계정과목이 아니다(매핑은 사람이 승인한다)"},
    {"name": "account_nm", "type": "string", "required": False, "description": "계정명"},
    {"name": "account_detail", "type": "string", "required": False, "description": "계정 상세"},
    {"name": "ord", "type": "string", "required": False, "description": "표시 순서"},
    {"name": "term_name", "type": "string", "required": False, "description": "당기 표기"},
    {"name": "amount", "type": "number", "required": False,
     "description": "당기 금액 — 읽지 못하면 비운다(0 으로 채우지 않는다)"},
    {"name": "prior_amount", "type": "number", "required": False, "description": "전기 금액"},
    {"name": "currency", "type": "string", "required": True, "description": "통화"},
    {"name": "rcept_no", "type": "string", "required": True,
     "description": "접수번호 — 정정공시 대체 순서의 근거"},
    {"name": "published_at", "type": "string", "required": True,
     "description": "발표일(접수번호 앞 8자리) — 받은 날이 아니다"},
    {"name": "vintage_date", "type": "string", "required": True,
     "description": "재현성의 근거(§12.5). 발표일과 같다"},
    {"name": "superseded_by_rcept_no", "type": "string", "required": False,
     "description": "이 행을 대체한 정정공시의 접수번호(없으면 빈 값)"},
    {"name": "source_id", "type": "string", "required": True, "description": "승인된 원천"},
    {"name": "raw_object_ref", "type": "string", "required": True,
     "description": "원문 보관소 참조 — 계보의 마지막 고리"},
    {"name": "trust_grade", "type": "string", "required": True, "description": "원천 등급"},
)


def pub01_proposal() -> Dict[str, Any]:
    """`PUB-01 공개 재무실적` 계약 제안. **결정론적** — 같은 입력이면 같은 문서다."""
    return build_contract_proposal(
        dataset_id="PUB-01", dataset_name="공개 재무실적",
        business_keys=["disclosure_row_id"],
        domain_fields=PUB01_DOMAIN_FIELDS,
        data_origin=am.ORIGIN_PUBLIC_DISCLOSED,
        provider_id="OPENDART",
        rationale=(
            "업무키트의 FIN-03(예산·회계실적·현금흐름)은 **내부 회계 실적**이다. 공시 재무제표는 "
            "사실이지만 내부 실적이 아니고 상세 매입·고객·BOM 을 담지 않는다. 같은 그릇에 넣으면 "
            "상세 계산이 공개 총계를 내부 실적으로 읽는다. 또한 이 자료에는 접수번호·정정공시 "
            "대체 관계처럼 내부 회계에 없는 축이 있어, 기존 스키마로는 「어느 판을 썼나」를 "
            "표현할 수 없다."),
    )


#: `EXT-01 환율·금리·물가` 의 도메인 필드. **키트의 EXT-01 과 같은 열 이름**을 쓴다 —
#: 이름이 갈리면 나중에 두 판을 나란히 놓고 비교할 수 없다.
EXT01_DOMAIN_FIELDS: Tuple[Dict[str, Any], ...] = (
    {"name": "observation_id", "type": "string", "required": True,
     "description": "관측값의 업무 키(통계표:세부항목:시점)"},
    {"name": "indicator_code", "type": "string", "required": True,
     "description": "지표 코드(FX_USDKRW · BOK_BASE_RATE · CPI_TOTAL)"},
    {"name": "stat_code", "type": "string", "required": True, "description": "원천 통계표 코드"},
    {"name": "item_code", "type": "string", "required": True, "description": "원천 세부항목 코드"},
    {"name": "item_name", "type": "string", "required": False, "description": "세부항목 이름"},
    {"name": "observed_at", "type": "string", "required": True, "description": "관측 시점"},
    {"name": "published_at", "type": "string", "required": False,
     "description": "발표일 — 원천이 주지 않으면 비운다(받은 날을 적지 않는다)"},
    {"name": "vintage_date", "type": "string", "required": True,
     "description": "재현성의 근거(§12.5). 발표일이 없으면 관측 시점을 쓴다"},
    {"name": "value", "type": "number", "required": True,
     "description": "값 — 읽지 못한 줄은 적재하지 않는다(0 으로 채우지 않는다)"},
    {"name": "unit", "type": "string", "required": True, "description": "단위"},
    {"name": "cycle", "type": "string", "required": False, "description": "공표 주기"},
    {"name": "source_id", "type": "string", "required": True, "description": "승인된 원천"},
    {"name": "raw_object_ref", "type": "string", "required": True,
     "description": "원문 보관소 참조 — 계보의 마지막 고리"},
    {"name": "trust_grade", "type": "string", "required": True, "description": "원천 등급"},
)


def ext01_public_proposal() -> Dict[str, Any]:
    """`EXT-01` 을 **공개 통계용으로 고치는 제안**. 인증 키트 파일은 건드리지 않는다.

    ⚠️⚠️ 왜 «고치는 제안» 인가: 키트의 `EXT-01` 은 열 모양이 관측값 그대로인데 분류만
      `SYNTHETIC`(시연용)이다. ECOS 같은 공표 통계를 그 선언 아래 넣으면 **계약이 거짓말을
      한다** — 「시연 자료」라고 적힌 그릇에 사실인 값이 담긴다.

    ★ 새 계약 키를 만들지 않는 이유: 라우팅표가 이미 `fx_rate → EXT-01` 이고, 키를 나누면
      「환율은 어느 계약인가」에 답이 둘이 된다. 담기는 **성격**만 고친다.

    ⚠️ 그래도 정의가 두 곳(키트 파일 · 승인된 제안)에 생긴다. 이것은 **의도된 분리**다 —
      키트의 것은 시연 데이터셋을, 이쪽은 격리 적재본을 설명한다. 두 저장소가 다르므로
      한쪽이 다른 쪽을 덮지 않는다(`test_08b` 가 표가 섞이지 않았음을 센다).
      ★★★ 사람이 「키트에도 공개 자료를 넣겠다」고 정하면 그때는 키트 파일을 고쳐야 하고,
        이 제안은 폐기해야 한다. 그 결정은 이 코드가 하지 않는다.
    """
    return build_contract_proposal(
        dataset_id="EXT-01", dataset_name="환율·금리·물가(공표 통계)",
        business_keys=["observation_id"],
        domain_fields=EXT01_DOMAIN_FIELDS,
        data_origin=am.ORIGIN_PUBLIC_DISCLOSED,
        provider_id="ECOS",
        rationale=(
            "업무키트의 EXT-01 은 열 모양이 관측값 그대로이지만 분류가 SYNTHETIC(시연용)이다. "
            "한국은행 공표 통계는 사실이고 PUBLIC_DISCLOSED 이므로, 그 선언 아래 넣으면 계약이 "
            "말하는 것과 담기는 것이 갈린다. 계약 키는 그대로 두고(라우팅표가 fx_rate → EXT-01) "
            "담기는 성격만 고친다. ⚠️ 이 계약은 격리 적재본을 설명하며, 키트의 시연 데이터셋을 "
            "대체하지 않는다 — 두 저장소는 다른 곳이다."),
    )


#: `EXT-03 운임·에너지·기상·산업지표` 의 도메인 필드.
#: ⚠️⚠️ 키트의 `EXT-03` 에는 형제 계약(`EXT-01`)에 있는 **`vintage_date` 가 없다.**
#:   그것이 없으면 「그 계획이 당시 어떤 발표값을 썼는가」에 답할 수 없다(§12.5).
#:   세 번째 Provider(KOSIS)를 붙이다 드러났고, 이 제안이 그 열을 **더한다.**
EXT03_DOMAIN_FIELDS: Tuple[Dict[str, Any], ...] = (
    {"name": "observation_id", "type": "string", "required": True,
     "description": "관측값의 업무 키(기관:통계표:분류축:항목:시점)"},
    {"name": "indicator_code", "type": "string", "required": True, "description": "지표 코드"},
    {"name": "org_id", "type": "string", "required": True, "description": "작성 기관"},
    {"name": "tbl_id", "type": "string", "required": True, "description": "통계표"},
    {"name": "target_ref", "type": "string", "required": True,
     "description": "무엇에 대한 지표인가(분류축 이름) — 섞으면 다른 계열이 뭉친다"},
    {"name": "category_code", "type": "string", "required": True, "description": "분류축 코드"},
    {"name": "item_code", "type": "string", "required": False, "description": "항목 코드"},
    {"name": "item_name", "type": "string", "required": False, "description": "항목 이름"},
    {"name": "observed_at", "type": "string", "required": True, "description": "관측 시점"},
    {"name": "published_at", "type": "string", "required": False,
     "description": "발표일 — 원천이 주지 않으면 비운다(받은 날을 적지 않는다)"},
    {"name": "vintage_date", "type": "string", "required": True,
     "description": "★ 키트 EXT-03 에 없던 열. 재현성의 근거(§12.5)"},
    {"name": "value", "type": "number", "required": True,
     "description": "값 — 읽지 못한 줄은 적재하지 않는다(0 으로 채우지 않는다)"},
    {"name": "unit", "type": "string", "required": True, "description": "단위"},
    {"name": "cycle", "type": "string", "required": False, "description": "공표 주기"},
    {"name": "source_id", "type": "string", "required": True, "description": "승인된 원천"},
    {"name": "raw_object_ref", "type": "string", "required": True,
     "description": "원문 보관소 참조 — 계보의 마지막 고리"},
    {"name": "trust_grade", "type": "string", "required": True, "description": "원천 등급"},
)


def ext03_public_proposal() -> Dict[str, Any]:
    """`EXT-03` 을 공표 통계용으로 고치는 제안. **`vintage_date` 를 더한다.**

    ⚠️⚠️ 키트의 `EXT-03` 은 `EXT-01`·`EXT-02` 와 달리 `vintage_date` 가 없다. 시연 자료
      에서는 티가 안 나지만, 공표 통계는 **정정 공표**가 있어서 그 열이 없으면 「그 계획이
      당시 어떤 값을 썼는가」를 재현할 수 없다. 세 번째 Provider 를 붙이다 드러났다."""
    return build_contract_proposal(
        dataset_id="EXT-03", dataset_name="운임·에너지·기상·산업지표(공표 통계)",
        business_keys=["observation_id"],
        domain_fields=EXT03_DOMAIN_FIELDS,
        data_origin=am.ORIGIN_PUBLIC_DISCLOSED,
        provider_id="KOSIS",
        rationale=(
            "키트의 EXT-03 은 분류가 SYNTHETIC(시연용)이고, 형제 계약(EXT-01·EXT-02)에 있는 "
            "vintage_date 가 **빠져 있다**. 공표 통계는 정정 공표가 있으므로 그 열이 없으면 "
            "「그 계획이 당시 어떤 값을 썼는가」를 재현할 수 없다(§12.5). 계약 키는 그대로 두고"
            "(라우팅표가 industry_indicator → EXT-03) 성격을 고치고 vintage_date 를 더한다. "
            "⚠️ 이 계약은 격리 적재본을 설명하며, 키트의 시연 데이터셋을 대체하지 않는다."),
    )


def observation_row_id(row: Mapping[str, Any]) -> str:
    """`EXT-01` 의 업무 키. 통계표·세부항목·시점이 같으면 같은 관측값이다.

    ⚠️ 원천이 값을 정정하면 같은 키가 된다 — 관측값은 공시와 달리 «접수번호» 축이 없다.
      그래서 정정은 **덮어쓰기가 아니라 거부**로 드러난다(중복 적재 방지 인덱스가 잡는다).
      정정을 반영하려면 사람이 판단해야 한다."""
    parts = [str(row.get(k) or "") for k in ("stat_code", "item_code", "observed_at")]
    if not all(parts):
        raise MappingError(
            "업무 키를 만들 수 없습니다 — stat_code·item_code·observed_at 가 필요합니다.")
    return ":".join(parts)


def indicator_row_id(row: Mapping[str, Any]) -> str:
    """`EXT-03` 의 업무 키. **분류축이 들어간다.**

    ⚠️ 축을 빼면 「제조업 생산지수」와 「광업 생산지수」가 같은 키가 되어 하나가 다른
      하나를 덮어쓴다 — 그리고 어느 쪽이 남았는지 아무도 모른다."""
    parts = [str(row.get(k) or "")
             for k in ("org_id", "tbl_id", "category_code", "observed_at")]
    if not all(parts):
        raise MappingError(
            "업무 키를 만들 수 없습니다 — org_id·tbl_id·category_code·observed_at 이 필요합니다.")
    return ":".join(parts)


def disclosure_row_id(row: Mapping[str, Any]) -> str:
    """`PUB-01` 의 업무 키. **정정공시가 다른 행이 되도록** 접수번호를 포함한다.

    ⚠️ 접수번호를 빼면 정정 전후가 같은 키가 되어 하나가 다른 하나를 덮어쓴다 —
      그 순간 「그 계획이 당시 어떤 발표값을 썼는가」가 사라진다."""
    parts = [str(row.get(k) or "") for k in ("rcept_no", "fs_div", "sj_div", "account_id")]
    if not all(parts[:2]) or not parts[3]:
        raise MappingError("업무 키를 만들 수 없습니다 — rcept_no·fs_div·account_id 가 필요합니다.")
    return ":".join(parts)
