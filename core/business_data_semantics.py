"""★★★ [BDR-1 / I-4 2.2a] **데이터의 출처·역할 판정기 — 단 하나.**

## 왜 이 파일이 따로 있는가

2.2 에서 같은 규칙이 **두 곳에** 생겼다:

| 계층 | 무엇을 봤나 |
|---|---|
| 계약 컴파일(`app_runtime_contract`) | 역할×출처 표 **전체** |
| 물질화(`app_data`) | 그중 **두 가지만** |

그래서 아래 조합이 **계약에서는 막히고 DB 에는 들어갔다**(실측 재현):

    DERIVED_RESULT + AFS_NATIVE
    NATIVE_SUPPLEMENT + ENTERPRISE_READ
    SCENARIO_INPUT + DERIVED_READ

계약을 지나지 않는 경로(관리 API·복구 스크립트·후속 물질화)가 그 구멍을 쓴다. 그리고
잘못 결속된 상태는 3단계에서 **정상으로 봉인된다** — 봉인은 「지금 상태가 그때와 같은가」에
답할 뿐 「지금 상태가 옳은가」에는 답하지 않는다.

★ 그래서 상수와 판정을 **중립 모듈 하나**로 내렸다. `app_runtime_contract` 는
`host_runtime_wire` 를 거쳐 `app_data` 에 의존하므로 그 둘은 서로를 import 할 수 없다 —
이 파일은 **아무것도 import 하지 않는다.** 그것이 두 계층이 같은 답을 내는 유일한 방법이다.

LLM 0콜.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

# ── 이 데이터가 «무엇인가» ────────────────────────────────────────────────
ENTERPRISE_ACTUAL = "ENTERPRISE_ACTUAL"        # 회사에서 실제 발생·확정된 것
OPERATIONAL_PLAN = "OPERATIONAL_PLAN"          # 승인된 계획
OPERATIONAL_FORECAST = "OPERATIONAL_FORECAST"  # 전망 — ⚠️ Actual 로 승격 불가
NATIVE_SUPPLEMENT = "NATIVE_SUPPLEMENT"        # 원천 결손을 AFS 에서 보완
SCENARIO_INPUT = "SCENARIO_INPUT"              # 사용자가 바꾼 가정
DERIVED_RESULT = "DERIVED_RESULT"              # 결정론적 계산 결과

DATA_ROLES: Tuple[str, ...] = (ENTERPRISE_ACTUAL, OPERATIONAL_PLAN, OPERATIONAL_FORECAST,
                               NATIVE_SUPPLEMENT, SCENARIO_INPUT, DERIVED_RESULT)

# ── 이 데이터가 «어디서 오는가» ──────────────────────────────────────────
AFS_NATIVE = "AFS_NATIVE"                      # AFS 에서 입력받는다
ENTERPRISE_READ = "ENTERPRISE_READ"            # 기존 회사 시스템에서 읽는다
EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"      # 외부 공표 지표
DERIVED_READ = "DERIVED_READ"                  # 계산 서비스가 만든다

SOURCE_INTENTS: Tuple[str, ...] = (AFS_NATIVE, ENTERPRISE_READ, EXTERNAL_REFERENCE, DERIVED_READ)

# ── 중복 입력 정책 ────────────────────────────────────────────────────────
DENY_IF_AUTHORITATIVE_SOURCE_EXISTS = "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS"
ALLOW_SUPPLEMENT_ONLY = "ALLOW_SUPPLEMENT_ONLY"
NO_DUPLICATE_CHECK_REQUIRED = "NO_DUPLICATE_CHECK_REQUIRED"

DUPLICATE_ENTRY_POLICIES: Tuple[str, ...] = (DENY_IF_AUTHORITATIVE_SOURCE_EXISTS,
                                             ALLOW_SUPPLEMENT_ONLY,
                                             NO_DUPLICATE_CHECK_REQUIRED)

#: ★★★ 역할 × 출처 — **어떤 조합이 말이 되는가**(닫힌 표).
#:
#: ⚠️⚠️ `ENTERPRISE_ACTUAL` 에 `AFS_NATIVE` 가 **없는 것**이 이 표의 핵심이다. 회사의 확정
#:   실적을 AFS 화면에서 받겠다는 선언은 곧 **이중 입력**이고, 두 값이 갈라진 뒤에야 드러난다.
ROLE_SOURCE_MATRIX: Dict[str, Tuple[str, ...]] = {
    ENTERPRISE_ACTUAL:     (ENTERPRISE_READ,),
    OPERATIONAL_PLAN:      (ENTERPRISE_READ, AFS_NATIVE),
    OPERATIONAL_FORECAST:  (EXTERNAL_REFERENCE, DERIVED_READ, AFS_NATIVE),
    NATIVE_SUPPLEMENT:     (AFS_NATIVE,),
    SCENARIO_INPUT:        (AFS_NATIVE,),
    DERIVED_RESULT:        (DERIVED_READ,),
}

#: 쓰기 행동 — 하나라도 있으면 «입력 화면이 생긴다» 는 뜻이다.
WRITE_ACTIONS: Tuple[str, ...] = ("create", "update", "delete")

#: 사용자에게 보여 줄 차단 문구. ★ 기술 용어를 쓰지 않는다 —
#: 「ENTERPRISE_READ 이므로 create 가 금지됩니다」는 현업에게 아무것도 알려 주지 않는다.
DUPLICATE_ENTRY_MESSAGE = (
    "이 데이터는 기존 회사 시스템에서 가져오도록 정의되어 있어 새 입력 화면을 만들지 "
    "않습니다. 먼저 ‘데이터 연결·준비’에서 원천을 연결하거나 검증 파일을 등록해 주십시오.")

# ── 신선도 요구 ──────────────────────────────────────────────────────────
#
# ⚠️⚠️ **월(`M`)·년(`Y`) 은 받지 않는다.** 그 둘은 고정 길이가 아니다 — `P1M` 은 28~31일이고
#   `P1Y` 는 365 또는 366일이다. 최신성 SLA 를 그런 값으로 비교하면 **기준일에 따라 같은
#   데이터가 신선하기도, 낡기도 한다.** 그리고 그 차이는 월말·윤년에만 드러난다.
#   ★ MVP 는 주·일·시·분·초만 허용한다. 「한 달」이 필요하면 `P30D` 처럼 **세어서** 적는다.
#   (ISO-8601 에서 `M` 은 날짜부에서는 월, 시간부에서는 분이다 — 시간부의 분은 허용된다.)
FRESHNESS_PATTERN = r"^P(?!$)(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)?$"

#: 거부 문구를 한 곳에 둔다 — 두 계층이 다른 말을 하면 사용자가 두 번 헷갈린다.
FRESHNESS_MESSAGE = (
    "최신성 요구는 주·일·시·분·초로 적습니다(P7D · PT6H 등). 월·년은 길이가 고정되지 "
    "않아 기준일에 따라 판정이 달라집니다 — 한 달이 필요하면 P30D 처럼 적어 주십시오.")


def allowed_sources_for(data_role: str) -> Tuple[str, ...]:
    """이 역할에 맞는 출처들. 모르는 역할이면 빈 튜플이다(= 아무것도 맞지 않는다)."""
    return ROLE_SOURCE_MATRIX.get(str(data_role or ""), ())


def role_source_errors(data_role: str, source_intent: str,
                       actions: Sequence[str] = ()) -> List[str]:
    """★★★ **두 계층이 함께 쓰는 단 하나의 판정.**

    ⚠️ 여기에만 두는 이유: 규칙이 두 곳에 있으면 한쪽이 늦게 갱신되고, 그 사이에 만들어진
      잘못된 결속은 3단계에서 **정상으로 봉인된다.** 봉인은 「그때와 같은가」에 답할 뿐
      「옳은가」에는 답하지 않는다."""
    role = str(data_role or "")
    intent = str(source_intent or "")
    errs: List[str] = []

    if role not in DATA_ROLES:
        errs.append(f"알 수 없는 데이터 역할입니다: {role or '(없음)'} — "
                    f"가능한 것은 {list(DATA_ROLES)} 입니다.")
    if intent not in SOURCE_INTENTS:
        errs.append(f"알 수 없는 데이터 출처입니다: {intent or '(없음)'} — "
                    f"가능한 것은 {list(SOURCE_INTENTS)} 입니다.")

    writes = sorted(set(str(a) for a in actions) & set(WRITE_ACTIONS))
    if writes and intent and intent != AFS_NATIVE:
        errs.append(f"출처가 {intent} 인데 {writes} 가 열려 있습니다 — {DUPLICATE_ENTRY_MESSAGE}")

    allowed = allowed_sources_for(role)
    if role in DATA_ROLES and intent in SOURCE_INTENTS and intent not in allowed:
        extra = ""
        if role == ENTERPRISE_ACTUAL and intent == AFS_NATIVE:
            #: ⚠️ 가장 위험한 조합이라 따로 말한다.
            extra = (" — 회사의 확정 실적을 AFS 화면에서 받겠다는 뜻이 되고, 그것이 곧 "
                     "이중 입력입니다. 두 값이 갈라진 뒤에야 드러납니다.")
        errs.append(f"역할 {role} 에는 출처 {list(allowed)} 만 맞습니다(선언 {intent}){extra}")
    return errs


def duplicate_policy_errors(data_role: str, duplicate_entry_policy: str,
                            actions: Sequence[str] = ()) -> List[str]:
    """중복 입력 정책이 실제로 무언가를 막는가."""
    role = str(data_role or "")
    policy = str(duplicate_entry_policy or "")
    errs: List[str] = []
    if policy and policy not in DUPLICATE_ENTRY_POLICIES:
        errs.append(f"알 수 없는 중복입력 정책입니다: {policy} — "
                    f"가능한 것은 {list(DUPLICATE_ENTRY_POLICIES)} 입니다.")
    writes = sorted(set(str(a) for a in actions) & set(WRITE_ACTIONS))
    if policy == DENY_IF_AUTHORITATIVE_SOURCE_EXISTS and writes:
        errs.append(f"중복입력 정책이 «권위 원천이 있으면 금지» 인데 {writes} 가 열려 "
                    f"있습니다 — 입력 화면이 생기면 그 정책은 글자로만 남습니다.")
    if policy == ALLOW_SUPPLEMENT_ONLY and role and role != NATIVE_SUPPLEMENT:
        errs.append(f"중복입력 정책이 «보완만 허용» 인데 역할이 {role} 입니다 — "
                    f"보완이 아닌 데이터에 그 정책을 붙이면 아무것도 막지 못합니다.")
    return errs


def is_declared_enterprise_actual(data_role: str) -> bool:
    """★★★ **선언이 그렇다는 것뿐**이다 — 공식 실적이라는 뜻이 아니다.

    ⚠️⚠️ 정본 설계상 «공식 실적» 은 다음을 **모두** 충족해야 한다:

        ENTERPRISE_ACTUAL 선언 + 승인된 Source Binding + 대사 완료
        + Data Owner 인증 + 유효한 CERTIFIED Snapshot/Baseline

    뒤의 넷은 BDR-2~3 이 만든다. 그때까지 이 함수를 `is_official_actual` 이라고 부르면
    **선언 하나로 공식 실적이 되는 것처럼 읽히고**, 그 이름 위에서 경영 보고가 만들어진다.
    ★ 이름이 과장하면 다음 사람은 코드를 읽지 않고 이름을 믿는다."""
    return str(data_role or "") == ENTERPRISE_ACTUAL
