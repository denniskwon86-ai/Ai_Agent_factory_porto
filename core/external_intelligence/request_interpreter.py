"""[DAO-5] 자연어 요청 → 구조화 요청. **LLM 은 제안하고, 판정은 여기서 한다.**

    사용자 자연어 요청
          ↓
    ① 카탈로그 뷰 만들기      ← 필드명·설명·건수만. **원문 레코드는 넣지 않는다.**
          ↓
    ② LLM 제안               ← 호출부가 한다. 이 모듈은 프롬프트를 만들고 응답을 읽기만.
          ↓
    ③ 결정론적 검증          ← ★★★ 여기가 관문이다. 통과 못 하면 아무 일도 안 일어난다.
          ↓
    구조화 요청(AcquisitionRequest)

## ★★★ LLM 이 정할 수 없는 것

  · **조직 범위** — 서버가 요청자의 권한에서 판정한다. 제안에 들어 있어도 **버린다.**
    ⚠️ 이것을 제안에서 받으면 「범위를 넓혀 달라」는 문장 한 줄로 남의 부서 자료가 열린다.
  · **신뢰등급** — 용도가 등급을 정한다(`PURPOSE_MIN_GRADE`). 제안이 낮춰 부를 수 없다.
    출처보다 값이 더 신뢰될 수 없듯, 제안이 정책보다 셀 수 없다.
  · **원천** — 등록되지 않은 Provider 이름은 통과하지 않는다.
  · **데이터 계약** — 목록에 없는 계약 키는 통과하지 않는다.

## ⚠️ 빈 값이 「전부」가 되지 않게 한다

기간이 비면 「전 기간」이 아니라 **오류**다. 이 저장소는 빈 파라미터가 범위를 조용히
넓히는 것을 겪었다 — 빈 값은 «지정 안 함»이지 «제한 없음»이 아니다.

## ⚠️ 사용자에게 내부 ID 를 입력시키지 않는다(지시 1)

사람은 회사명·부서명·업무키트 이름을 고르고 내부 식별자는 시스템이 붙인다. 그래서
**요청의 사람용 칸에 내부 ID 모양의 값이 오면 거부한다** — 화면이 ID 를 노출하고 있다는
신호이고, 고지문으로는 막히지 않는다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am
from core.external_intelligence.providers import AcquisitionRequest, ProviderDescriptor

#: `core.system_ids` 가 발급하는 모양(`prj_…`·`dst_…`). 사람용 칸에 오면 거부한다.
_SYSTEM_ID_SHAPE = re.compile(r"\b[a-z]{3}_[0-9a-f]{16,32}\b")
#: 수집 작업 자신의 id 모양도 같이 본다.
_JOB_ID_SHAPE = re.compile(r"\bdaq_[0-9a-f]{16,32}\b")

#: 사람이 직접 쓰는 칸. 여기에 내부 ID 가 오면 화면이 ID 를 노출하고 있다는 뜻이다.
_HUMAN_FIELDS = ("subject_name", "purpose", "department_name", "kit_name")

MAX_PERIOD_YEARS = 30
MAX_INDICATORS = 40


class RequestInterpretationError(ValueError):
    """제안이 관문을 통과하지 못했다 — 4xx 로 전달한다."""


@dataclass(frozen=True)
class Problem:
    """왜 통과 못 했는지. **사람이 고칠 수 있는 문장으로** 적는다."""
    field: str
    reason: str
    got: str = ""


@dataclass(frozen=True)
class InterpretationResult:
    """검증 결과. 통과하면 `request` 가 있고, 아니면 `problems` 가 있다."""
    ok: bool
    request: Optional[AcquisitionRequest] = None
    problems: Tuple[Problem, ...] = ()
    #: 제안에 있었지만 **서버가 무시한** 값들. 화면이 「왜 내가 쓴 대로 안 됐나」에 답해야 한다.
    overridden: Tuple[Problem, ...] = ()
    resolved_scope_node_id: str = ""
    required_grade: str = ""


# ── ① LLM 에게 보여 줄 것 ────────────────────────────────────────────────────
def build_catalog_view(*, descriptors: Sequence[ProviderDescriptor],
                       contracts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """LLM 에게 보낼 카탈로그. **필드명·설명·건수만** 담는다(지시 6).

    ★★★ 원문 레코드를 넣지 않는다. 「요약이니까 괜찮다」로 시작해 값이 섞여 들어가는 것을
      막으려면, 이 함수가 **값을 만질 수 있는 자리 자체를 갖지 않아야** 한다 — 그래서
      계약의 `schema.fields` 에서 이름·형·설명만 뽑고 데이터는 인자로도 받지 않는다."""
    provider_cards = [{
        "provider_id": d.provider_id, "name": d.name, "publisher": d.publisher,
        "source_type": d.source_type, "cost": d.cost,
        "requires_credential": d.requires_credential,
        "default_trust_grade": d.default_trust_grade,
        "refresh_frequency": d.refresh_frequency, "coverage_note": d.coverage_note,
        "allowed_usage": d.allowed_usage,
        "redistribution_allowed": d.redistribution_allowed,
        "target_contract_keys": list(d.target_contract_keys),
        "data_origin": d.data_origin, "known_limits": list(d.known_limits),
    } for d in descriptors]

    contract_cards = []
    for c in contracts:
        fields = c.get("schema", {}).get("fields", []) if isinstance(c, Mapping) else []
        contract_cards.append({
            "contract_key": str(c.get("dataset_id") or ""),
            "name": str(c.get("dataset_name") or ""),
            "field_names": [str(f.get("name") or "") for f in fields if isinstance(f, Mapping)],
            "field_notes": {str(f.get("name") or ""): str(f.get("description") or "")
                            for f in fields if isinstance(f, Mapping)},
        })
    return {"providers": provider_cards, "contracts": contract_cards,
            "data_origins": list(am.DATA_ORIGINS),
            "note": "값이 아니라 «무엇이 있는가»만 담겨 있습니다."}


def build_prompt(user_text: str, catalog: Mapping[str, Any]) -> str:
    """구조화 요청을 제안하게 하는 프롬프트.

    ⚠️ 조직 범위·신뢰등급을 **묻지 않는다.** 물으면 답이 오고, 답이 오면 언젠가 그 답을
      쓰게 된다. 서버가 정하는 값은 애초에 질문에 없어야 한다."""
    return (
        "당신은 데이터 수집 요청을 구조화합니다. **값을 지어내지 마십시오.**\n\n"
        f"[사용자 요청]\n{str(user_text or '').strip()}\n\n"
        f"[사용할 수 있는 원천과 데이터 계약]\n"
        f"{json.dumps(catalog, ensure_ascii=False, indent=1)}\n\n"
        "[지시]\n"
        "아래 JSON 한 개만 출력하십시오. 모르는 값은 빈 문자열로 두고 추측하지 마십시오.\n"
        "조직 범위·권한·신뢰등급은 **묻지 않았습니다** — 넣지 마십시오. 서버가 정합니다.\n"
        "내부 식별자(prj_…, dst_… 같은 값)를 만들어 넣지 마십시오.\n\n"
        "{\n"
        '  "subject_name": "대상 회사·조직의 사람용 이름",\n'
        '  "purpose": "이 자료로 무엇을 할 것인가",\n'
        '  "period_from": "YYYY", "period_to": "YYYY",\n'
        '  "indicators": ["필요한 지표"],\n'
        '  "target_contract_keys": ["연결할 데이터 계약 키"],\n'
        '  "provider_ids": ["쓸 원천"],\n'
        '  "frequency": "annual|quarterly|monthly|daily",\n'
        '  "data_origin": "' + "|".join(am.DATA_ORIGINS) + '",\n'
        '  "refresh_frequency": "정기 갱신 주기(없으면 빈 문자열)",\n'
        '  "excluded_providers": [{"provider_id": "", "reason": "고르지 않은 이유"}]\n'
        "}\n")


def parse_proposal(llm_text: str) -> Dict[str, Any]:
    """LLM 응답에서 제안 JSON 을 꺼낸다. **여기서 판정하지 않는다** — 읽기만 한다."""
    from nodes.utils.json_utils import loads_lenient
    data = loads_lenient(llm_text)
    return data if isinstance(data, dict) else {}


# ── ③ 결정론적 관문 ──────────────────────────────────────────────────────────
def validate_proposal(proposal: Mapping[str, Any], *,
                      known_provider_ids: Sequence[str],
                      known_contract_keys: Sequence[str],
                      scope_node_id: str,
                      purpose_kind: str = "scenario",
                      now_year: Optional[int] = None) -> InterpretationResult:
    """제안을 구조화 요청으로 바꾼다. **통과 못 하면 아무 일도 일어나지 않는다.**

    `scope_node_id` 는 **호출부가 요청자의 권한에서 판정해 넘긴 값**이다. 제안에 들어 있는
    범위는 무시하고 무시했다는 사실을 `overridden` 으로 알린다."""
    p = dict(proposal or {})
    problems: List[Problem] = []
    overridden: List[Problem] = []

    # ── 서버가 정하는 값: 제안에 있으면 버린다 ─────────────────────────
    for taken in ("scope_node_id", "tenant_id", "enterprise_scope_id", "department_id",
                  "required_grade", "trust_grade", "unrestricted"):
        if p.get(taken) not in (None, "", [], {}):
            overridden.append(Problem(
                taken, "서버가 정하는 값이라 제안의 값을 쓰지 않았습니다.", str(p.get(taken))))
    resolved_scope = str(scope_node_id or "").strip()

    #: ★ 등급은 **용도**가 정한다. 제안이 낮춰 부를 수 없다.
    from core.external_intelligence import PURPOSE_MIN_GRADE
    required_grade = PURPOSE_MIN_GRADE.get(str(purpose_kind or "").strip())
    if not required_grade:
        problems.append(Problem("purpose_kind",
                                f"용도는 {tuple(PURPOSE_MIN_GRADE)} 중 하나여야 합니다.",
                                str(purpose_kind)))
        required_grade = ""

    # ── 사람용 칸에 내부 ID 가 오면 거부 ───────────────────────────────
    for f in _HUMAN_FIELDS:
        value = str(p.get(f) or "")
        if _SYSTEM_ID_SHAPE.search(value) or _JOB_ID_SHAPE.search(value):
            problems.append(Problem(
                f, "사람이 쓰는 칸에 내부 식별자가 들어왔습니다 — 화면이 ID 를 노출하고 "
                   "있다는 뜻입니다. 사람용 이름으로 다시 고르십시오.", value[:80]))

    # ── 필수 ───────────────────────────────────────────────────────────
    subject = str(p.get("subject_name") or "").strip()
    if not subject:
        problems.append(Problem("subject_name", "대상 회사·조직 이름이 필요합니다."))
    purpose = str(p.get("purpose") or "").strip()
    if not purpose:
        problems.append(Problem("purpose", "이 자료를 무엇에 쓸지가 필요합니다 — "
                                           "목적이 없으면 어느 등급이 필요한지 정할 수 없습니다."))

    # ── 기간: 빈 값은 「전부」가 아니라 오류 ────────────────────────────
    y_from, y_to = _year(p.get("period_from")), _year(p.get("period_to"))
    if y_from is None or y_to is None:
        problems.append(Problem("period", "기간(연도)이 필요합니다 — 비워 두면 «전 기간»이 "
                                          "아니라 «지정 안 함»입니다.",
                                f"{p.get('period_from')}~{p.get('period_to')}"))
    else:
        if y_to < y_from:
            y_from, y_to = y_to, y_from
        if y_to - y_from + 1 > MAX_PERIOD_YEARS:
            problems.append(Problem("period", f"기간이 {MAX_PERIOD_YEARS}년을 넘습니다 — "
                                              f"나누어 요청하십시오.", f"{y_from}~{y_to}"))
        if now_year is not None and y_to > now_year:
            #: ⚠️ 아직 오지 않은 해를 요청하면 「자료 없음」이 아니라 요청이 틀린 것이다.
            problems.append(Problem("period_to", f"아직 오지 않은 연도입니다(현재 {now_year}).",
                                    str(y_to)))

    # ── 원천·계약: 목록 밖은 통과하지 않는다 ───────────────────────────
    known_p = {str(x) for x in known_provider_ids}
    known_c = {str(x) for x in known_contract_keys}
    provider_ids = _clean_list(p.get("provider_ids"))
    for pid in provider_ids:
        if pid not in known_p:
            problems.append(Problem("provider_ids", "등록되지 않은 원천입니다 — "
                                                    "먼저 원천을 등록·승인하십시오.", pid))
    contract_keys = _clean_list(p.get("target_contract_keys"))
    for key in contract_keys:
        if key not in known_c:
            problems.append(Problem("target_contract_keys",
                                    "목록에 없는 데이터 계약입니다 — 의미가 다르면 "
                                    "새 계약을 제안하십시오(억지로 연결하지 않습니다).", key))

    # ── 자료 성격 ──────────────────────────────────────────────────────
    origin = str(p.get("data_origin") or "").strip()
    if origin:
        try:
            am.assert_origin(origin)
        except am.AcquisitionStateError as exc:
            problems.append(Problem("data_origin", str(exc), origin))
        else:
            if origin in am.ORIGINS_FOR_INTERNAL_ACTUAL:
                #: ★★★ 외부에서 받아 온 값을 내부 실적(REAL)으로 표시할 수 없다.
                problems.append(Problem(
                    "data_origin",
                    "외부 수집 자료를 내부 실적(REAL)으로 표시할 수 없습니다 — "
                    "공시·공식통계는 PUBLIC_DISCLOSED 입니다.", origin))

    indicators = _clean_list(p.get("indicators"))
    if len(indicators) > MAX_INDICATORS:
        problems.append(Problem("indicators", f"지표가 {MAX_INDICATORS}개를 넘습니다 — "
                                              f"나누어 요청하십시오.", str(len(indicators))))

    if problems:
        return InterpretationResult(ok=False, problems=tuple(problems),
                                    overridden=tuple(overridden),
                                    resolved_scope_node_id=resolved_scope,
                                    required_grade=required_grade)

    request = AcquisitionRequest(
        subject_name=subject, purpose=purpose,
        period_from=str(y_from), period_to=str(y_to),
        indicators=tuple(indicators),
        target_contract_keys=tuple(contract_keys),
        frequency=str(p.get("frequency") or "").strip(),
        required_grade=required_grade,
        extras={"provider_ids": provider_ids,
                "data_origin": origin,
                "refresh_frequency": str(p.get("refresh_frequency") or "").strip(),
                "excluded_providers": _excluded(p.get("excluded_providers")),
                "scope_node_id": resolved_scope,
                "purpose_kind": str(purpose_kind or "")},
    )
    return InterpretationResult(ok=True, request=request, overridden=tuple(overridden),
                                resolved_scope_node_id=resolved_scope,
                                required_grade=required_grade)


# ── 보조 ─────────────────────────────────────────────────────────────────────
def _year(value: Any) -> Optional[int]:
    m = re.search(r"(\d{4})", str(value or ""))
    return int(m.group(1)) if m else None


def _clean_list(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    out, seen = [], set()
    for item in value:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _excluded(value: Any) -> List[Dict[str, str]]:
    """제외한 원천과 사유(지시 3). **사유 없는 제외는 버린다** — 화면이 설명할 수 없다."""
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        pid = str(item.get("provider_id") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if pid and reason:
            out.append({"provider_id": pid, "reason": reason})
    return out
