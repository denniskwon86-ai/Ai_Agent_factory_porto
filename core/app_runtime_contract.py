"""★★★ [I-4 1단계] **App Runtime Contract** — 생성 앱이 무엇을 할 수 있는지의 정본.

`app_manifest` 가 «앱이 자기 로그인을 갖지 않는다» 를 강제한다면, 이 파일은 «이 앱이 어떤
데이터를, 어떤 행동으로, 어떤 의미로 다루는가» 를 강제한다.

## 이 파일이 정하는 것

1. **능력 상태 다섯** — 「지원 대기」와 「허용되지 않음」은 다른 말이다(§1).
2. **결정표** — 어떤 요구가 어느 상태인가. **닫힌 목록**이고 코드 상수다.
3. **JSON Schema** — 계약 문서의 형태(`schema_version = "1.0"`).
4. **조건부 규칙** — Schema 만으로 못 잡는 것(단위 없는 수량, 금지 항목의 개발 요청화 등).
5. **의미 지문** — 무엇이 바뀌면 재승인인가.

## ★★★ 왜 판정을 LLM 에서 떼어 내는가

같은 요구에 대해 어제와 오늘의 답이 달라지면, 그 차이는 **릴리스가 나온 뒤에야** 드러난다.
결정표는 두 번 물어도 같은 답을 준다. 그래서 LLM(Tech Lead)은 자연어 요구를 구조화할 뿐
**지원 여부를 정하지 않는다** — 이 파일이 정한다.

## ⚠️⚠️ 「지원 대기」로 적으면 사용자는 언젠가 열린다고 읽는다

자체 로그인·직접 API 호출은 **영원히 열리지 않는다.** 그것을 `NOT_YET_SUPPORTED` 로 적으면
사용자는 그때까지 우회로를 찾는다. 그래서 상태를 다섯으로 나누고 `PROHIBITED` 에는
`REQUEST_HOST_FEATURE` 를 **허용하지 않는다**(§19-5) — 허용하면 금지 정책이 개발 요청으로
변질되고, 「요청해 뒀으니 언젠가 열리겠지」가 된다.

## ⚠️ 모르는 요구를 자동 허용하지 않는다

결정표에 없는 capability 는 `NOT_YET_SUPPORTED` 로 떨어지고 사용자 선택을 받는다.
「모르니까 되겠지」가 곧 통제 없는 기능이다.

LLM 0콜.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Tuple

from core import app_manifest, host_runtime_wire

#: 계약 **문서 형식**의 버전. `ProjectState.schema_version`(5.2.0)이나
#: `runtime_contract_version`(앱↔Host 런타임 계약 세대)과 **다른 것**이다.
#: ⚠️ 셋을 한 숫자로 묶으면 이후 한쪽만 올릴 수 없게 된다.
SCHEMA_VERSION = "1.0"

#: 앱↔Host 런타임 계약 세대. `host_runtime_wire.WIRE_VERSION` 과 짝이다.
RUNTIME_CONTRACT_VERSION = 1

# ── 1. 능력 상태 다섯 ──────────────────────────────────────────────────────
SUPPORTED = "SUPPORTED"
CONDITIONAL = "CONDITIONAL"
HOST_SERVICE_REQUIRED = "HOST_SERVICE_REQUIRED"
NOT_YET_SUPPORTED = "NOT_YET_SUPPORTED"
PROHIBITED = "PROHIBITED"

CAPABILITY_STATUSES: Tuple[str, ...] = (
    SUPPORTED, CONDITIONAL, HOST_SERVICE_REQUIRED, NOT_YET_SUPPORTED, PROHIBITED)

#: 사용자에게 보이는 문구. ⚠️ 코드 상태값을 그대로 노출하지 않는다 —
#: 「PROHIBITED」는 화면에서 「플랫폼 정책상 허용되지 않음」이라고 읽혀야 한다.
STATUS_LABEL: Dict[str, str] = {
    SUPPORTED: "지원됨",
    CONDITIONAL: "조건부 지원",
    HOST_SERVICE_REQUIRED: "Host 기능 필요",
    NOT_YET_SUPPORTED: "지원 대기",
    PROHIBITED: "플랫폼 정책상 허용되지 않음",
}

#: 계약이 성립하려면 이 상태여야 한다. 나머지는 `unsupported_requirements` 로 간다.
BUILDABLE: Tuple[str, ...] = (SUPPORTED, CONDITIONAL)

# ── 1-1. 결정표 (닫힌 목록) ────────────────────────────────────────────────
#: capability → (상태, 근거). ⚠️ 여기 없는 것은 `NOT_YET_SUPPORTED` 다(`decide()` 참조).
CAPABILITY_DECISION: Dict[str, Tuple[str, str]] = {
    "app_data.read":        (SUPPORTED, "window.afs.data"),
    "app_data.create":      (SUPPORTED, "window.afs.data"),
    "app_data.update":      (SUPPORTED, "window.afs.data"),
    "app_data.delete":      (SUPPORTED, "window.afs.data"),

    "auth.local_login":     (PROHIBITED, "회사 권한 체계 밖에서 인증하게 된다"),
    "auth.local_roles":     (PROHIBITED, "권한 판정이 두 곳이 된다"),
    "auth.local_session":   (PROHIBITED, "회사 권한 체계 밖에서 세션을 갖게 된다"),
    "api.direct_call":      (PROHIBITED, "증명 경계를 우회한다"),
    "storage.credentials":  (PROHIBITED, "B02 — 앱에 자격증명을 두지 않는다"),
    "storage.local_db":     (PROHIBITED, "판정이 두 곳이 된다"),

    "app_data.aggregate":   (CONDITIONAL, "§1-2 의 경계 안에서만"),
    "app_data.query":       (CONDITIONAL, "§1-2 의 경계 안에서만"),

    "file.upload":          (NOT_YET_SUPPORTED, "데이터 평면에 바이너리가 없다"),
    "job.background":       (NOT_YET_SUPPORTED, "앱은 프레임 수명 안에서만 산다"),

    "network.external_api": (HOST_SERVICE_REQUIRED, "CSP connect-src 'none' — Host 가 중개한다"),
    "network.mcp":          (HOST_SERVICE_REQUIRED, "CSP connect-src 'none' — Host 가 중개한다"),
    "action.business":      (HOST_SERVICE_REQUIRED, "원장·승인 흐름을 지나야 한다"),
    "compute.simulation":   (HOST_SERVICE_REQUIRED, "G4 계산 그래프 — afs.data 가 아니다"),
    "server.custom_logic":  (HOST_SERVICE_REQUIRED, "임의 FastAPI 생성 금지"),
}

#: 결정표에 없을 때의 상태. ⚠️ **`SUPPORTED` 로 떨어뜨리지 않는다.**
UNKNOWN_CAPABILITY_STATUS = NOT_YET_SUPPORTED
UNKNOWN_CAPABILITY_REASON = "결정표에 없는 요구입니다 — 사용자 선택을 받습니다."

# ── 1-2. CONDITIONAL 의 경계를 숫자로 ──────────────────────────────────────
#: 데이터 평면이 **실제로** 할 수 있는 것. 화면이 이 상한 안에서 계산하는 집계만 지원한다.
#: ★ 상한은 **런타임이 실제로 강제하는 값에서 가져온다**(`host_runtime_wire`). 여기에 숫자를
#:   다시 적으면 둘이 갈라지고, 갈라진 날 계약은 없는 능력을 「조건부 지원」이라고 말한다.
CONDITIONAL_LIMITS: Dict[str, Any] = {
    "max_page_size": host_runtime_wire.MAX_PAGE_LIMIT,
    "datasets_per_query": 1,
    "sort": "생성 역순 고정",
    "filter": False,
}
#: ⚠️ 「일단 다 받아서 계산한다」를 허용하지 않는다 — 데이터가 늘어난 날 **조용히 틀린 합계**를
#: 보여주고, 그때 화면은 아무 오류도 내지 않는다.
CONDITIONAL_DEFERRED: Tuple[str, ...] = (
    "조인", "데이터셋 간 집계", "전체 스캔 통계", "정렬·필터 지정", "상한을 넘는 전수 집계")

# ── 19-5. 상태별로 허용되는 사용자 결정 (닫힌 집합) ─────────────────────────
REDUCE = "REDUCE"
WAIT = "WAIT"
REQUEST_HOST_FEATURE = "REQUEST_HOST_FEATURE"

#: ★★★ `PROHIBITED` 에 `REQUEST_HOST_FEATURE` 가 없는 것이 이 표의 핵심이다.
ALLOWED_USER_DECISIONS: Dict[str, Tuple[str, ...]] = {
    PROHIBITED:            (REDUCE,),
    NOT_YET_SUPPORTED:     (REDUCE, WAIT),
    HOST_SERVICE_REQUIRED: (REDUCE, WAIT, REQUEST_HOST_FEATURE),
}

# ── 닫힌 목록들 ────────────────────────────────────────────────────────────
CONTRACT_STATUSES: Tuple[str, ...] = ("DRAFT", "COMPILED", "APPROVED", "SUPERSEDED")
#: ★ 이름으로 부른다 — 문자열을 여기저기 적으면 오타 하나가 **판정하지 않음**이 된다.
#: ⚠️ 튜플에서 풀어 쓴다: 목록이 바뀌면 여기서 **즉시 깨진다**(조용히 어긋나지 않는다).
STATUS_DRAFT, STATUS_COMPILED, STATUS_APPROVED, STATUS_SUPERSEDED = CONTRACT_STATUSES
APPROVAL_STATUSES: Tuple[str, ...] = ("PENDING", "APPROVED", "REJECTED")
FIELD_TYPES: Tuple[str, ...] = ("string", "text", "number", "boolean", "date")
ACTIONS: Tuple[str, ...] = ("read", "create", "update", "delete")
CLASSIFICATIONS: Tuple[str, ...] = ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED")
SEMANTIC_ROLES: Tuple[str, ...] = ("", "identifier", "event_time", "quantity", "amount",
                                   "status", "party", "location", "note")
KNOWLEDGE_ELIGIBILITY: Tuple[str, ...] = ("OPERATIONAL_UNVERIFIED", "OPERATIONAL_VERIFIED",
                                          "REFERENCE_CANDIDATE", "NOT_ELIGIBLE")
#: 단위 없는 수량은 나중에 합산될 때 **조용히 틀린다**(톤과 개를 더한다).
UNIT_REQUIRED_ROLES: Tuple[str, ...] = ("quantity", "amount")

# ── [BDR-1 / I-4 2.2] 데이터 출처·역할·중복입력 ────────────────────────────
#
# ★★★ **상수와 판정은 `core.business_data_semantics` 한 곳에만 있다.**
#
# 2.2 초판은 같은 규칙을 계약 계층과 물질화 계층에 **각각** 적었다. 그래서 물질화 쪽이
# 표의 일부만 보았고, `DERIVED_RESULT + AFS_NATIVE` 같은 조합이 **계약에서는 막히고 DB 에는
# 들어갔다**(실측 재현). 그리고 그렇게 들어간 상태는 3단계에서 **정상으로 봉인된다** —
# 봉인은 「그때와 같은가」에 답할 뿐 「옳은가」에는 답하지 않는다.
#
# ⚠️ 아래는 **재수출(re-export)** 이다. 값을 여기서 다시 적지 않는다.

from core.business_data_semantics import (  # noqa: E402  (문서 순서를 지킨다)
    AFS_NATIVE, ALLOW_SUPPLEMENT_ONLY, DATA_ROLES, DENY_IF_AUTHORITATIVE_SOURCE_EXISTS,
    DERIVED_READ, DERIVED_RESULT, DUPLICATE_ENTRY_MESSAGE, DUPLICATE_ENTRY_POLICIES,
    ENTERPRISE_ACTUAL, ENTERPRISE_READ, EXTERNAL_REFERENCE, FRESHNESS_MESSAGE,
    FRESHNESS_PATTERN, NATIVE_SUPPLEMENT, NO_DUPLICATE_CHECK_REQUIRED, OPERATIONAL_FORECAST,
    OPERATIONAL_PLAN, ROLE_SOURCE_MATRIX, SCENARIO_INPUT, SOURCE_INTENTS, WRITE_ACTIONS,
    duplicate_policy_errors, is_declared_enterprise_actual, role_source_errors)

#: ★★★ 출처별 현재 지원 상태(§6.3). **`AFS_NATIVE` 만 지금 물질화된다.**
#: ⚠️⚠️ 나머지를 `AFS_NATIVE` 로 **조용히 폴백하지 않는다** — 그 폴백이 곧 이중 입력이다.
SOURCE_INTENT_DECISION: Dict[str, Tuple[str, str]] = {
    AFS_NATIVE:         (SUPPORTED, "window.afs.data 로 입력받는다"),
    #: ★★★ [Wave F-0] `HOST_SERVICE_REQUIRED` → `SUPPORTED`. **그 Host 서비스를 실제로
    #:   만들었기 때문이다** — BDR-5·6(`core/host_runtime_provider.py`)이 승인된 파일
    #:   Snapshot 을 `window.afs.data.*` 뒤에서 읽어 준다.
    #: ⚠️ 「곧 될 것」이라서 여는 것이 아니다. 아래 둘은 여전히 없으므로 **그대로 둔다** —
    #:   여기서 함께 열면 앱이 빈 응답을 정상으로 받는다.
    #: ⚠️ 읽기만 열린다. 쓰기는 `business_data_semantics.role_source_errors` 가 별도
    #:   계층에서 계속 막는다(이중 입력 금지). 두 곳이 같은 규칙을 갖지 않게 한다.
    ENTERPRISE_READ:    (SUPPORTED,
                         "승인된 파일 Snapshot 을 Host Runtime 이 읽어 줍니다 — 앱이 "
                         "원천을 직접 호출하지 않고, 화면에서 다시 입력받지도 않습니다."),
    EXTERNAL_REFERENCE: (HOST_SERVICE_REQUIRED,
                         "외부 공표 지표는 Host 외부지표 서비스가 가져옵니다 — 앱이 직접 "
                         "호출하지 않습니다."),
    DERIVED_READ:       (HOST_SERVICE_REQUIRED,
                         "계산 결과는 Host 계산 서비스가 만듭니다 — 앱이 임의로 계산·저장하지 "
                         "않습니다."),
}

NAME_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
CONTRACT_ID_PATTERN = r"^contract_[a-z0-9]{12}$"
#: ★★★ [I-4 3단계] 이 값은 **증명에 봉인된다** — 64비트 축약은 권한 결속에
#: 좁다. 화면에는 `app_data.short_fingerprint()` 로 줄여 보여 준다.
FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"

# ── 5. JSON Schema ────────────────────────────────────────────────────────
_FIELD_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    # ★ `classification` 만 필수다. 전부 필수로 하면 Tech Lead 가 값을 **지어낸다** —
    #   지어낸 등급은 없느니만 못하다.
    "required": ["name", "type", "required", "classification"],
    "properties": {
        "name": {"type": "string", "pattern": NAME_PATTERN},
        "type": {"enum": list(FIELD_TYPES)},
        "required": {"type": "boolean"},
        "label": {"type": "string"},
        "business_term_id": {"type": "string"},
        "semantic_role": {"enum": list(SEMANTIC_ROLES)},
        "unit": {"type": "string"},
        "classification": {"enum": list(CLASSIFICATIONS)},
        "master_reference": {"type": "string"},
    },
}

_DATASET_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    #: ⚠️ [BDR-1] `data_role`·`source_intent`·`duplicate_entry_policy` 는 **필수**다.
    #:   선택으로 두면 빠진 계약이 「모르니까 입력 화면」으로 처리되고, 그것이 정확히
    #:   막으려던 이중 입력이다. 빠뜨린 초안은 `DRAFT` 로 남고 사람이 정한다.
    "required": ["name", "label", "purpose", "allowed_actions", "fields",
                 "data_role", "source_intent", "duplicate_entry_policy"],
    "properties": {
        "name": {"type": "string", "pattern": NAME_PATTERN},
        #: ★★★ [§18] **불변 식별자.** `name` 은 앱이 부르는 이름이고 이것은 데이터셋의
        #:   정체다. 둘을 하나로 두면 이름을 바꾸는 날 «이름이 같은 다른 것» 과 «이름이
        #:   다른 같은 것» 을 구분할 방법이 사라진다. 비우면 `name` 을 쓴다.
        "dataset_key": {"type": "string", "pattern": NAME_PATTERN},
        "label": {"type": "string"},
        "purpose": {"type": "string", "minLength": 1},
        #: ⚠️ `minItems` 가 **0** 이다. 빈 목록은 «선언을 빠뜨렸다» 가 아니라 계약이
        #:   **«아무 행동도 허용하지 않는다» 고 말한 것**이다(2단계의 세 값 중 하나).
        #:   1로 막으면 계약은 그 사실을 표현할 수 없고, 그러면 그 상태는 계약 밖 경로로만
        #:   만들어진다 — 계약이 설명할 수 없는 상태가 DB 에 생긴다.
        "allowed_actions": {"type": "array", "minItems": 0, "uniqueItems": True,
                            "items": {"enum": list(ACTIONS)}},
        "ontology_entity_type": {"type": "string"},
        "knowledge_eligibility": {"enum": list(KNOWLEDGE_ELIGIBILITY)},
        "data_role": {"enum": list(DATA_ROLES)},
        "source_intent": {"enum": list(SOURCE_INTENTS)},
        "duplicate_entry_policy": {"enum": list(DUPLICATE_ENTRY_POLICIES)},
        #: 회사 Data Contract 의 키(`PRC-02` 등). 아직 없을 수 있으므로 선택이다.
        "enterprise_contract_key": {"type": "string"},
        "required_freshness": {"type": "string", "pattern": FRESHNESS_PATTERN},
        "fields": {"type": "array", "minItems": 1, "items": _FIELD_SCHEMA},
    },
}

_INTENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent_id", "requirement_ref", "capability", "status"],
    "properties": {
        "intent_id": {"type": "string"},
        "requirement_ref": {"type": "string"},
        "capability": {"type": "string"},
        "status": {"enum": list(CAPABILITY_STATUSES)},
        "reason": {"type": "string"},
        "user_decision": {"enum": ["", REDUCE, WAIT, REQUEST_HOST_FEATURE]},
    },
}

_UNSUPPORTED_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["requirement_ref", "status", "user_decision"],
    "properties": {
        "requirement_ref": {"type": "string"},
        "status": {"enum": [HOST_SERVICE_REQUIRED, NOT_YET_SUPPORTED, PROHIBITED]},
        "reason": {"type": "string"},
        "user_decision": {"enum": [REDUCE, WAIT, REQUEST_HOST_FEATURE]},
    },
}

CONTRACT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": f"afs://contracts/app_runtime_contract/{SCHEMA_VERSION}",
    "title": "App Runtime Contract",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "contract_id", "revision", "project_id",
                 "runtime_contract_version", "status", "app_class",
                 "capability_intents", "manifest", "datasets",
                 "unsupported_requirements", "semantic_fingerprint", "approval"],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "contract_id": {"type": "string", "pattern": CONTRACT_ID_PATTERN},
        "revision": {"type": "integer", "minimum": 1},
        "project_id": {"type": "string"},
        "task_id": {"type": "string"},
        "runtime_contract_version": {"type": "integer", "enum": [RUNTIME_CONTRACT_VERSION]},
        "status": {"enum": list(CONTRACT_STATUSES)},
        "app_class": {"enum": list(app_manifest.APP_CLASSES)},
        "capability_intents": {"type": "array", "items": _INTENT_SCHEMA},
        "manifest": {"type": "object"},
        "datasets": {"type": "array", "items": _DATASET_SCHEMA},
        "unsupported_requirements": {"type": "array", "items": _UNSUPPORTED_SCHEMA},
        "semantic_fingerprint": {"type": "string", "pattern": FINGERPRINT_PATTERN},
        "approval": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status"],
            "properties": {
                "status": {"enum": list(APPROVAL_STATUSES)},
                "approved_by": {"type": "string"},
                "approved_at": {"type": "string"},
                "decision_ledger_id": {"type": "string"},
            },
        },
    },
}


class ContractError(ValueError):
    """계약 위반 — 4xx 로 전달한다."""


# ── 판정 ──────────────────────────────────────────────────────────────────
def decide(capability: Any) -> Tuple[str, str]:
    """capability → (상태, 근거). **결정론적이고 부작용이 없다.**

    ⚠️ 모르는 값은 `NOT_YET_SUPPORTED` 다. 「모르니까 되겠지」가 곧 통제 없는 기능이다."""
    key = str(capability or "").strip()
    hit = CAPABILITY_DECISION.get(key)
    if hit is None:
        return UNKNOWN_CAPABILITY_STATUS, UNKNOWN_CAPABILITY_REASON
    return hit


def decide_source_intent(source_intent: Any) -> Tuple[str, str]:
    """출처 의도 → (지원 상태, 사용자에게 할 말).

    ⚠️⚠️ **모르는 출처를 `AFS_NATIVE` 로 떨어뜨리지 않는다.** 그 폴백 하나가 곧
      「기존 시스템에 있는 값을 화면에서 또 받는」 앱을 만든다."""
    key = str(source_intent or "").strip()
    hit = SOURCE_INTENT_DECISION.get(key)
    if hit is None:
        return (NOT_YET_SUPPORTED,
                "알 수 없는 데이터 출처입니다 — 어디서 오는지 정해야 만들 수 있습니다.")
    return hit


def materializable(source_intent: Any) -> bool:
    """지금 **실제로 데이터셋을 만들 수 있는가.**

    ★ [Wave F-0] `AFS_NATIVE` 와 `ENTERPRISE_READ` 둘이다 — 후자는 승인된 파일
      Snapshot 을 Host Runtime 이 읽어 준다. 나머지는 아직 없다."""
    return decide_source_intent(source_intent)[0] == SUPPORTED


def is_declared_enterprise_actual_dataset(dataset: Any) -> bool:
    """이 데이터셋이 **기업 실적이라고 «선언» 됐는가.**

    ★★★ 이름이 «선언» 에서 멈추는 이유: 정본 설계상 **공식 실적**은 선언 하나로 되지
      않는다 — 승인된 Source Binding · 대사 완료 · Data Owner 인증 · 유효한 CERTIFIED
      Snapshot 이 모두 있어야 한다(BDR-2~3). 그것들이 없는 지금 이 함수를
      `is_official_actual` 이라고 부르면 **선언 하나가 공식 실적처럼 읽히고**, 그 이름
      위에서 경영 보고가 만들어진다.
    ⚠️⚠️ **미분류를 Actual 로 승격하지 않는다.** 「역할이 안 적혀 있으니 실적이겠지」는
      추측이다."""
    return isinstance(dataset, dict) and is_declared_enterprise_actual(
        str(dataset.get("data_role", "")))


def duplicate_entry_errors(dataset: Any) -> List[str]:
    """★★★ **Zero Duplicate Entry Gate**(§6.4) — 계약 하나로 판정 가능한 조건들.

    현업의 이중 입력을 막는 **첫 번째 제품 게이트**다. 여기서 막지 못하면 그 앱은
    「ERP 에 있는 값을 한 번 더 받는 화면」을 갖고 배포된다."""
    if not isinstance(dataset, dict):
        return ["데이터셋이 객체가 아닙니다."]
    name = str(dataset.get("name", "?"))
    role = str(dataset.get("data_role", ""))
    intent = str(dataset.get("source_intent", ""))
    policy = str(dataset.get("duplicate_entry_policy", ""))
    actions = [str(a) for a in (dataset.get("allowed_actions") or [])]
    #: ★★★ 판정은 **공통 모듈 하나**가 한다 — 물질화 계층이 부르는 것과 같은 함수다.
    errs = (role_source_errors(role, intent, actions)
            + duplicate_policy_errors(role, policy, actions))
    return [f"{name}: {e}" for e in errs]


def is_buildable(status: Any) -> bool:
    """이 상태의 요구를 지금 만들 수 있는가."""
    return str(status or "") in BUILDABLE


def allowed_decisions(status: Any) -> Tuple[str, ...]:
    """이 상태에서 사용자가 고를 수 있는 것. 지원되는 상태에는 고를 것이 없다."""
    return ALLOWED_USER_DECISIONS.get(str(status or ""), ())


# ── 의미 지문 ──────────────────────────────────────────────────────────────
def canonical_json(obj: Any) -> str:
    """정렬된 canonical JSON — 지문의 입력.

    ⚠️ 키 순서가 다르면 같은 내용이 다른 지문을 갖는다. 그러면 「계약이 바뀌었다」는 판정이
      거짓이 되고, 아무도 그 판정을 믿지 않게 된다."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_material(contract: Dict[str, Any]) -> Dict[str, Any]:
    """지문에 **들어가는 것만** 추린다.

    ★ `label`·`purpose`·`reason` 같은 설명 문구는 **들어가지 않는다.** 문구를 다듬었다고
      재승인을 요구하면 사람이 게이트를 습관으로 통과시킨다 — 그러면 게이트가 아니다."""
    c = contract if isinstance(contract, dict) else {}
    datasets = []
    for ds in (c.get("datasets") or []):
        d = ds if isinstance(ds, dict) else {}
        datasets.append({
            "name": str(d.get("name", "")),
            #: 정체가 바뀌면 그것은 다른 데이터셋이다 — 지문이 움직여야 한다.
            "dataset_key": str(d.get("dataset_key", "") or d.get("name", "")),
            "allowed_actions": sorted({str(a) for a in (d.get("allowed_actions") or [])}),
            "ontology_entity_type": str(d.get("ontology_entity_type", "")),
            #: ★★★ [BDR-1] 출처·역할·중복입력은 **의미**다. 이것이 바뀌면 앱이 다루는 것이
            #:   달라진다 — 「기존 시스템에서 읽는다」가 「화면에서 받는다」로 바뀌는 것은
            #:   설명 문구가 아니라 업무 자체의 변경이고, **재승인 대상**이다.
            "data_role": str(d.get("data_role", "")),
            "source_intent": str(d.get("source_intent", "")),
            "duplicate_entry_policy": str(d.get("duplicate_entry_policy", "")),
            "enterprise_contract_key": str(d.get("enterprise_contract_key", "")),
            "required_freshness": str(d.get("required_freshness", "")),
            "fields": sorted(
                ({"name": str(f.get("name", "")), "type": str(f.get("type", "")),
                  "required": bool(f.get("required", False)), "unit": str(f.get("unit", "")),
                  "classification": str(f.get("classification", "")),
                  "semantic_role": str(f.get("semantic_role", ""))}
                 for f in (d.get("fields") or []) if isinstance(f, dict)),
                key=lambda x: x["name"]),
        })
    #: ★★★ 능력은 **집합**이다 — 같은 것이 몇 번 적혔는지는 권한이 아니다.
    #:
    #: ⚠️⚠️ [2026-08-26 실측] 종전에는 중복째 실었다. 그런데 이 재료에는
    #:   `requirement_ref` 가 **빠져 있다**(설명이므로 옳다). 그 결과 「같은 `app_data.read`
    #:   를 몇 개의 FR 이 인용했는가」만으로 지문이 바뀌었다 — 권한은 한 글자도 안 달라졌는데.
    #:   실측: Tech Lead 가 매 실행마다 FR 인용 수를 달리 적어 지문이
    #:   `56ac83 → 906969 → 56ac83 → 2fcd71` 로 오갔고, **승인이 영영 수렴하지 않았다.**
    #:   사용자는 승인을 눌러도 계속 재승인을 요구받는다.
    #: ★ 머리말이 「문구를 다듬었다고 재승인을 요구하면 사람이 게이트를 습관으로 통과시킨다」
    #:   고 적어 둔 것과 **같은 이유**다. 인용 횟수도 문구다.
    #: ⚠️ 「같음」의 기준은 (능력·상태·사용자결정) 셋이다. 하나라도 다르면 **남는다** —
    #:   예: `network.external_api` 를 FR-1 은 `REDUCE`, FR-2 는 `WAIT` 로 정했다면 둘 다
    #:   실린다. 그것은 실제로 다른 결정이고, 합치면 하나가 조용히 사라진다.
    _seen_intents: set = set()
    intents = []
    for i in (c.get("capability_intents") or []):
        if not isinstance(i, dict):
            continue
        item = {"capability": str(i.get("capability", "")),
                "status": str(i.get("status", "")),
                "user_decision": str(i.get("user_decision", ""))}
        key = (item["capability"], item["status"], item["user_decision"])
        if key in _seen_intents:
            continue
        _seen_intents.add(key)
        intents.append(item)
    intents.sort(key=lambda x: (x["capability"], x["status"], x["user_decision"]))
    return {
        "app_class": str(c.get("app_class", "")),
        "datasets": sorted(datasets, key=lambda x: x["name"]),
        "capability_intents": intents,
    }


def semantic_fingerprint(contract: Dict[str, Any]) -> str:
    """의미 지문(전체 sha256). **이 값이 바뀔 때만** 재승인이 필요하다.

    ⚠️ 축약하지 않는다 — 3단계부터 이 값이 증명에 봉인된다."""
    return hashlib.sha256(
        canonical_json(semantic_material(contract)).encode("utf-8")).hexdigest()


def contract_id_for(project_id: Any, task_id: Any = "") -> str:
    """계약 id 는 **결정론적**이다 — 같은 (project, task) 를 다시 컴파일해도 같은 id 다.

    ⚠️ 무작위 id 를 쓰면 재컴파일마다 새 계약이 생기고, 승인 원장이 무엇을 가리키는지
      알 수 없게 된다."""
    seed = f"{str(project_id or '')}\x1f{str(task_id or '')}"
    return "contract_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


# ── 검증 ──────────────────────────────────────────────────────────────────
def _schema_errors(contract: Any) -> List[str]:
    """JSON Schema 위반. `jsonschema` 가 없으면 **통과시키지 않고** 그 사실을 오류로 낸다."""
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - 의존성 누락은 배포 사고다
        return ["jsonschema 가 설치되어 있지 않아 계약을 검증할 수 없습니다 — "
                "검증 없이 통과시키지 않습니다."]
    validator = jsonschema.Draft202012Validator(CONTRACT_SCHEMA)
    out: List[str] = []
    for e in sorted(validator.iter_errors(contract), key=lambda x: list(x.path)):
        where = "/".join(str(p) for p in e.path) or "(최상위)"
        out.append(f"{where}: {e.message}")
    return out


def conditional_errors(contract: Any) -> List[str]:
    """★★★ JSON Schema 만으로는 부족한 것들(§19).

    `manifest` 가 단순 객체라 **유효하지 않은 매니페스트도 스키마를 통과한다.**"""
    errs: List[str] = []
    if not isinstance(contract, dict):
        return ["계약이 객체가 아닙니다."]

    # 1. 매니페스트 자체 검증
    errs.extend(f"manifest: {m}" for m in app_manifest.validate(contract.get("manifest")))

    # 2. 매니페스트 ↔ 계약 일치 — 선언된 데이터셋·행동이 서로를 벗어나지 않는가
    errs.extend(_manifest_contract_mismatch(contract))

    # ★★★ [2026-08-26 실측] **예약 필드 이름은 여기서 잡는다.**
    #
    # ⚠️⚠️ 이 규칙은 **물질화 단계에만** 있었다(`core/app_data.py`). 그래서 실제 가동에서
    #   이렇게 됐다:
    #
    #     계약 컴파일 통과 → 승인 통과 → 코드 생성 → 태스크 「완료」 → 릴리스
    #       → 물질화 FAILED('created_at' 은 예약된 이름)
    #       → 릴리스 매니페스트의 능력이 **빈 배열**
    #       → 증명 발급 거절(「매니페스트 미선언」)
    #       → 앱이 데이터를 못 읽고 「초기화 중 오류」로 멈춤
    #
    #   **완주했다고 보고된 앱이 실제로는 못 도는 상태로 릴리스까지 갔다.** 사람이 그것을
    #   화면에서 처음 알았다.
    # ★ 규칙은 이미 `skills/tech_lead_skill.md` 에 적혀 있었다 — 모델이 어겼는데 **아무
    #   관문도 잡지 않은 것**이 문제다. 잡는 자리를 앞으로 당긴다.
    # ⚠️ 목록은 `app_data.RESERVED_FIELD_NAMES` 하나를 쓴다 — 여기서 다시 적으면 두 목록이
    #   갈라지고, 그러면 한쪽만 통과하는 계약이 생긴다.
    from core.app_data import RESERVED_FIELD_NAMES

    for ds in (contract.get("datasets") or []):
        if not isinstance(ds, dict):
            continue
        for f in (ds.get("fields") or []):
            if not isinstance(f, dict):
                continue
            fname = str(f.get("name", "")).strip().lower()
            if fname in RESERVED_FIELD_NAMES:
                errs.append(
                    f"{ds.get('name', '?')}.{fname}: 예약된 이름이라 필드로 쓸 수 없습니다 — "
                    f"레코드가 이미 갖는 항목이며, 앱이 같은 이름을 쓰면 «누가 언제 만들었나» "
                    f"를 덮어쓸 수 있습니다(감사 표시 위조). **업무의 뜻이 드러나는 이름**을 "
                    f"쓰십시오(예: registered_at · ordered_at · closed_at).")

    # 3. 수량·금액에는 단위가 필요하다 + [BDR-1] 이중 입력 게이트
    for ds in (contract.get("datasets") or []):
        if not isinstance(ds, dict):
            continue
        errs.extend(duplicate_entry_errors(ds))
        dsname = str(ds.get("name", "?"))
        for f in (ds.get("fields") or []):
            if not isinstance(f, dict):
                continue
            if str(f.get("semantic_role", "")) in UNIT_REQUIRED_ROLES and not str(f.get("unit", "")).strip():
                errs.append(
                    f"{dsname}.{f.get('name', '?')}: semantic_role 이 "
                    f"{f.get('semantic_role')} 인데 unit 이 없습니다 — "
                    f"단위 없는 수량은 나중에 합산될 때 조용히 틀립니다.")

    # 4. 승인됐다면 누가·언제·어느 원장인지가 있어야 한다
    ap = contract.get("approval") or {}
    if isinstance(ap, dict) and ap.get("status") == "APPROVED":
        for k, ko in (("approved_by", "승인자"), ("approved_at", "승인 시각"),
                      ("decision_ledger_id", "결정 원장 id")):
            if not str(ap.get(k, "")).strip():
                errs.append(f"approval.{k} 가 없습니다 — 승인에는 {ko}가 남아야 합니다.")

    # 5. 상태별 사용자 결정의 허용 집합
    errs.extend(_decision_errors(contract))

    # 6. 데이터셋 이름 중복 — 같은 이름 둘은 런타임에서 어느 쪽인지 알 수 없다
    seen: Dict[str, int] = {}
    for ds in (contract.get("datasets") or []):
        if isinstance(ds, dict):
            n = str(ds.get("name", ""))
            seen[n] = seen.get(n, 0) + 1
    dup = sorted(n for n, c in seen.items() if c > 1)
    if dup:
        errs.append(f"데이터셋 이름이 중복됩니다: {dup} — 런타임이 어느 쪽인지 알 수 없습니다.")

    # 7. 지문이 내용과 맞는가 (COMPILED 이상에서만 — DRAFT 는 아직 지문이 없다)
    if str(contract.get("status", "")) in ("COMPILED", "APPROVED", "SUPERSEDED"):
        want = semantic_fingerprint(contract)
        got = str(contract.get("semantic_fingerprint", ""))
        if got != want:
            errs.append(f"semantic_fingerprint 가 내용과 다릅니다(선언 {got!r} · 계산 {want!r}) — "
                        f"지문이 내용을 따라가지 않으면 재승인 판정이 거짓이 됩니다.")
    return errs


def _decision_errors(contract: Dict[str, Any]) -> List[str]:
    """★★★ 금지 항목에 `REQUEST_HOST_FEATURE` 를 허용하면 **금지 정책이 개발 요청으로
    변질된다** — 「요청해 뒀으니 언젠가 열리겠지」가 되고, 그 사이 사용자는 우회로를 쓴다."""
    errs: List[str] = []
    for i in (contract.get("capability_intents") or []):
        if not isinstance(i, dict):
            continue
        st, dec = str(i.get("status", "")), str(i.get("user_decision", ""))
        if not dec:
            continue
        ok = allowed_decisions(st)
        if is_buildable(st):
            errs.append(f"{i.get('capability', '?')}: 상태가 {st} 인데 user_decision "
                        f"{dec!r} 가 있습니다 — 지원되는 요구에는 고를 것이 없습니다.")
        elif dec not in ok:
            errs.append(f"{i.get('capability', '?')}: {st} 에는 {dec} 를 고를 수 없습니다"
                        f"(가능: {list(ok)}).")
    for u in (contract.get("unsupported_requirements") or []):
        if not isinstance(u, dict):
            continue
        st, dec = str(u.get("status", "")), str(u.get("user_decision", ""))
        if dec and dec not in allowed_decisions(st):
            errs.append(f"{u.get('requirement_ref', '?')}: {st} 에는 {dec} 를 고를 수 없습니다"
                        f"(가능: {list(allowed_decisions(st))}).")
    return errs


def _manifest_contract_mismatch(contract: Dict[str, Any]) -> List[str]:
    """매니페스트가 계약을 벗어나면 **계약이 설명서가 된다.**

    매니페스트의 `resource.action` 을 계약의 데이터셋·행동과 대조한다. 매니페스트에만 있는
    권한은 «계약에 없는 권한»이고, 그것이 런타임에서 실제로 열린다면 계약은 아무것도 막지 못한다.
    ⚠️ 반대 방향(계약에만 있는 데이터셋)은 오류가 아니다 — 매니페스트는 Compiler 가 계약에서
      다시 만들어 낼 수 있고, 그 순서가 정상이다."""
    m = contract.get("manifest")
    if not isinstance(m, dict):
        return []
    ds_actions: Dict[str, set] = {}
    for ds in (contract.get("datasets") or []):
        if isinstance(ds, dict):
            ds_actions[str(ds.get("name", ""))] = {
                str(a) for a in (ds.get("allowed_actions") or [])}
    errs: List[str] = []
    for cap in (m.get("capabilities") or []):
        s = str(cap or "").strip()
        if not s or "." not in s:
            continue
        res, _, act = s.rpartition(".")
        if res not in ds_actions:
            errs.append(f"manifest 의 {s} 가 계약에 없는 데이터셋을 가리킵니다 — "
                        f"계약 밖 권한은 열리지 않습니다.")
        elif act not in ds_actions[res]:
            errs.append(f"manifest 의 {s} 가 계약의 allowed_actions"
                        f"({sorted(ds_actions[res])})를 벗어납니다.")
    return errs


def validate(contract: Any) -> List[str]:
    """위반 목록. **비어 있으면 통과**다(예외를 던지지 않는 판정 — 화면·컴파일러용)."""
    if not isinstance(contract, dict):
        return ["계약이 객체가 아닙니다."]
    errs = _schema_errors(contract)
    # ⚠️ 스키마가 깨진 문서에 조건부 규칙을 돌리면 오류가 두 배로 늘어 원인을 가린다.
    if errs:
        return errs
    return conditional_errors(contract)


def assert_valid(contract: Any) -> Dict[str, Any]:
    """위반이 있으면 던진다. 통과하면 그 계약을 그대로 돌려준다."""
    errs = validate(contract)
    if errs:
        raise ContractError(" / ".join(errs))
    return contract


def summarize(contract: Any) -> str:
    """사람이 읽는 한 줄 요약 — `ProjectState.app_runtime_contract_summary` 에 들어간다.

    ★ 계약 **원문은 workspace 파일이 정본**이다. 상태에는 요약·상태·지문만 둔다 —
      원문을 상태에 넣으면 체크포인터가 매 단계 그것을 복사한다."""
    if not isinstance(contract, dict):
        return ""
    names = [str(d.get("name", "")) for d in (contract.get("datasets") or [])
             if isinstance(d, dict)]
    blocked = [f"{u.get('requirement_ref', '?')}({STATUS_LABEL.get(str(u.get('status', '')), '?')})"
               for u in (contract.get("unsupported_requirements") or []) if isinstance(u, dict)]
    parts = [f"데이터셋 {len(names)}개" + (f": {', '.join(names)}" if names else "")]
    if blocked:
        parts.append(f"보류·불가 {len(blocked)}건: {', '.join(blocked)}")
    parts.append(f"지문 {contract.get('semantic_fingerprint', '') or '(없음)'}")
    return " · ".join(parts)
