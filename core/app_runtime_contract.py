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
# ★★★ 왜 이것이 계약에 들어가야 하는가
#
# 지금 Dataset Contract 는 `name`·`purpose`·`allowed_actions`·`fields` 뿐이다. 그래서
# **앱이 다룰 데이터가 이미 회사에 있는 것인지, AFS 에서 새로 받는 것인지 구분할 수 없다.**
# 구분하지 못하면 생성기는 모든 것을 입력 화면으로 만든다 — 그리고 현업은 ERP 에 이미
# 있는 값을 **한 번 더 손으로 넣는다.** 그 이중 입력은 조용하고, 두 값이 갈라진 뒤에야
# 드러나며, 그때는 어느 쪽이 맞는지 아무도 모른다.

#: 이 데이터가 **무엇인가**. ⚠️ 섞으면 시나리오 값이 공식 실적으로 보고된다.
ENTERPRISE_ACTUAL = "ENTERPRISE_ACTUAL"      # 회사에서 실제 발생·확정된 것
OPERATIONAL_PLAN = "OPERATIONAL_PLAN"        # 승인된 계획
OPERATIONAL_FORECAST = "OPERATIONAL_FORECAST"  # 전망 — ⚠️ Actual 로 승격 불가
NATIVE_SUPPLEMENT = "NATIVE_SUPPLEMENT"      # 원천 결손을 AFS 에서 보완
SCENARIO_INPUT = "SCENARIO_INPUT"            # 사용자가 바꾼 가정
DERIVED_RESULT = "DERIVED_RESULT"            # 결정론적 계산 결과

DATA_ROLES: Tuple[str, ...] = (ENTERPRISE_ACTUAL, OPERATIONAL_PLAN, OPERATIONAL_FORECAST,
                               NATIVE_SUPPLEMENT, SCENARIO_INPUT, DERIVED_RESULT)

#: 이 데이터가 **어디서 오는가**.
AFS_NATIVE = "AFS_NATIVE"                    # AFS 에서 입력받는다
ENTERPRISE_READ = "ENTERPRISE_READ"          # 기존 회사 시스템에서 읽는다
EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"    # 외부 공표 지표
DERIVED_READ = "DERIVED_READ"                # 계산 서비스가 만든다

SOURCE_INTENTS: Tuple[str, ...] = (AFS_NATIVE, ENTERPRISE_READ, EXTERNAL_REFERENCE, DERIVED_READ)

#: ★★★ 출처별 현재 지원 상태(§6.3). **`AFS_NATIVE` 만 지금 물질화된다.**
#: ⚠️⚠️ 나머지를 `AFS_NATIVE` 로 **조용히 폴백하지 않는다** — 그 폴백이 곧 이중 입력이다.
SOURCE_INTENT_DECISION: Dict[str, Tuple[str, str]] = {
    AFS_NATIVE:         (SUPPORTED, "window.afs.data 로 입력받는다"),
    ENTERPRISE_READ:    (HOST_SERVICE_REQUIRED,
                         "기존 회사 시스템에서 가져오도록 정의돼 있습니다 — 입력 화면을 "
                         "만들지 않습니다. 먼저 데이터 연결·준비에서 원천을 연결하십시오."),
    EXTERNAL_REFERENCE: (HOST_SERVICE_REQUIRED,
                         "외부 공표 지표는 Host 외부지표 서비스가 가져옵니다 — 앱이 직접 "
                         "호출하지 않습니다."),
    DERIVED_READ:       (HOST_SERVICE_REQUIRED,
                         "계산 결과는 Host 계산 서비스가 만듭니다 — 앱이 임의로 계산·저장하지 "
                         "않습니다."),
}

#: 중복 입력 정책.
DENY_IF_AUTHORITATIVE_SOURCE_EXISTS = "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS"
ALLOW_SUPPLEMENT_ONLY = "ALLOW_SUPPLEMENT_ONLY"
NO_DUPLICATE_CHECK_REQUIRED = "NO_DUPLICATE_CHECK_REQUIRED"

DUPLICATE_ENTRY_POLICIES: Tuple[str, ...] = (DENY_IF_AUTHORITATIVE_SOURCE_EXISTS,
                                             ALLOW_SUPPLEMENT_ONLY,
                                             NO_DUPLICATE_CHECK_REQUIRED)

#: ★★★ 역할 × 출처 — **어떤 조합이 말이 되는가**(닫힌 표).
#:
#: ⚠️⚠️ `ENTERPRISE_ACTUAL` 에 `AFS_NATIVE` 가 **없는 것**이 이 표의 핵심이다. 회사의 확정
#:   실적을 AFS 화면에서 받겠다는 선언은 곧 **이중 입력**이고, 두 값이 갈라진 뒤에야
#:   드러난다.
ROLE_SOURCE_MATRIX: Dict[str, Tuple[str, ...]] = {
    ENTERPRISE_ACTUAL:     (ENTERPRISE_READ,),
    OPERATIONAL_PLAN:      (ENTERPRISE_READ, AFS_NATIVE),
    OPERATIONAL_FORECAST:  (EXTERNAL_REFERENCE, DERIVED_READ, AFS_NATIVE),
    NATIVE_SUPPLEMENT:     (AFS_NATIVE,),
    SCENARIO_INPUT:        (AFS_NATIVE,),
    DERIVED_RESULT:        (DERIVED_READ,),
}

#: 쓰기 행동. ⚠️ 이 셋 중 하나라도 있으면 «입력 화면이 생긴다» 는 뜻이다.
WRITE_ACTIONS: Tuple[str, ...] = ("create", "update", "delete")

#: 사용자에게 보여 줄 차단 문구. ★ 기술 용어를 쓰지 않는다 —
#: 「ENTERPRISE_READ 이므로 create 가 금지됩니다」는 현업에게 아무것도 알려 주지 않는다.
DUPLICATE_ENTRY_MESSAGE = (
    "이 데이터는 기존 회사 시스템에서 가져오도록 정의되어 있어 새 입력 화면을 만들지 "
    "않습니다. 먼저 ‘데이터 연결·준비’에서 원천을 연결하거나 검증 파일을 등록해 주십시오.")

#: ISO-8601 기간(`P1D`·`PT6H`…). 신선도 요구를 자유 문장으로 두면 비교할 수 없다.
FRESHNESS_PATTERN = r"^P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)?$"

NAME_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
CONTRACT_ID_PATTERN = r"^contract_[a-z0-9]{12}$"
FINGERPRINT_PATTERN = r"^[0-9a-f]{16}$"

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
        "label": {"type": "string"},
        "purpose": {"type": "string", "minLength": 1},
        "allowed_actions": {"type": "array", "minItems": 1, "uniqueItems": True,
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
    """지금 **실제로 데이터셋을 만들 수 있는가.** `AFS_NATIVE` 만 참이다."""
    return decide_source_intent(source_intent)[0] == SUPPORTED


def is_official_actual(dataset: Any) -> bool:
    """이 데이터셋이 **공식 실적**인가.

    ★★★ 명시적으로 `ENTERPRISE_ACTUAL` 이라고 선언된 것만 참이다.
    ⚠️⚠️ **미분류를 Actual 로 승격하지 않는다.** 「역할이 안 적혀 있으니 실적이겠지」는
      추측이고, 그 추측 위에서 경영 보고가 만들어진다."""
    return isinstance(dataset, dict) and str(dataset.get("data_role", "")) == ENTERPRISE_ACTUAL


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
    actions = {str(a) for a in (dataset.get("allowed_actions") or [])}
    writes = sorted(actions & set(WRITE_ACTIONS))
    errs: List[str] = []

    # ① 기업 읽기 데이터셋에 입력·수정·삭제가 있다
    if intent and intent != AFS_NATIVE and writes:
        errs.append(f"{name}: 이 데이터는 {intent} 로 선언됐는데 {writes} 가 열려 있습니다 — "
                    f"{DUPLICATE_ENTRY_MESSAGE}")

    # ② 권위 원천이 있으면 입력을 만들지 않는다
    if policy == DENY_IF_AUTHORITATIVE_SOURCE_EXISTS and writes:
        errs.append(f"{name}: 중복입력 정책이 «권위 원천이 있으면 금지» 인데 {writes} 가 "
                    f"열려 있습니다 — 입력 화면이 생기면 그 정책은 글자로만 남습니다.")

    # ⑤ 역할과 출처가 서로 다른 말을 한다
    allowed_sources = ROLE_SOURCE_MATRIX.get(role)
    if role and intent and allowed_sources is not None and intent not in allowed_sources:
        extra = ""
        if role == ENTERPRISE_ACTUAL and intent == AFS_NATIVE:
            #: ⚠️ 가장 위험한 조합이라 따로 말한다.
            extra = (" — 회사의 확정 실적을 AFS 화면에서 받겠다는 뜻이 되고, 그것이 곧 "
                     "이중 입력입니다. 두 값이 갈라진 뒤에야 드러납니다.")
        errs.append(f"{name}: 역할 {role} 에는 출처 {list(allowed_sources)} 만 맞습니다"
                    f"(선언 {intent}){extra}")

    # 보완 전용 정책은 보완 역할에만 붙는다
    if policy == ALLOW_SUPPLEMENT_ONLY and role and role != NATIVE_SUPPLEMENT:
        errs.append(f"{name}: 중복입력 정책이 «보완만 허용» 인데 역할이 {role} 입니다 — "
                    f"보완이 아닌 데이터에 그 정책을 붙이면 아무것도 막지 못합니다.")
    return errs


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
    intents = sorted(
        ({"capability": str(i.get("capability", "")), "status": str(i.get("status", "")),
          "user_decision": str(i.get("user_decision", ""))}
         for i in (c.get("capability_intents") or []) if isinstance(i, dict)),
        key=lambda x: (x["capability"], x["status"]))
    return {
        "app_class": str(c.get("app_class", "")),
        "datasets": sorted(datasets, key=lambda x: x["name"]),
        "capability_intents": intents,
    }


def semantic_fingerprint(contract: Dict[str, Any]) -> str:
    """의미 지문(sha256 앞 16자). **이 값이 바뀔 때만** 재승인이 필요하다."""
    return hashlib.sha256(
        canonical_json(semantic_material(contract)).encode("utf-8")).hexdigest()[:16]


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
