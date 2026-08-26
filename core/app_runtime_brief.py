"""★★★ 기획 에이전트에게 **이 플랫폼이 무엇을 만들 수 있는지** 알려 주는 고지문. (2026-08-26)

## ⚠️⚠️ 왜 생겼는가 — 기획이 호스팅 불가 아키텍처를 설계했다

실제 가동(`live-walk-02`)에서 Architect 가 이렇게 설계했다:

    백엔드 API 서버 … **경량 백엔드 프레임워크(예: Spring Boot)** 를 사용하여 구현합니다
    프론트엔드가 백엔드 API 서버에 데이터를 요청하고…

그래서 공장은 `InboundApplication.java` · `schema.sql` 을 만들었다. 그런데 런타임 계약은
정확히 그것을 금지한다 — `server.custom_logic`·`api.direct_call` 은 `PROHIBITED` 다.
결과는 프론트 렌더 검증 8회 반려 → `FAILED_REVIEW`. **앱이 한 줄도 안 나왔다.**

`skills/architect_skill.md` 에는 이 제약이 **한 글자도 없었다.** 오히려 「High FR 은 반드시
REST API 엔드포인트로 설계하라」고 적혀 있었다. 모델이 틀린 것이 아니라 **못 만드는 것을
만들라고 시킨 것**이다(같은 날 `capability` 닫힌 목록에서 똑같은 일이 있었다).

## 왜 스킬 파일에 직접 적지 않는가

두 가지 이유다.

  ① **계약 프로필이 꺼진 레거시 프로젝트**가 있다(`runtime_contract_profile == ""`).
     그 프로젝트들은 자유 형식 앱을 만들어 왔고, 스킬 파일에 못박으면 그것들이 깨진다.
     ★ 그래서 **상태를 보고** 붙인다 — 판정은 `profile_enforces_contract` 하나를 쓴다.
  ② 금지 목록은 `app_runtime_contract` 의 **닫힌 목록**이다. 스킬에 손으로 옮겨 적으면
     둘이 조용히 어긋난다. 여기서 **코드를 읽어 렌더링**한다 — 목록이 바뀌면 고지문도
     같이 바뀐다.
"""
from __future__ import annotations

from typing import Any, Dict, List

from core import app_runtime_contract as arc
from core.wbs_artifact_kind import profile_enforces_contract


def _group(decision: Dict[str, Any], status: str) -> List[str]:
    return sorted(k for k, (s, _r) in decision.items() if s == status)


def _lines(decision: Dict[str, Any], status: str) -> List[str]:
    """`이름 — 이유` 줄. **이유도 코드에서 가져온다** — 내 말로 다시 쓰면 근거가 둘이 된다."""
    return [f"  · `{k}` — {decision[k][1]}" for k in _group(decision, status)]


def applies(state: Any) -> bool:
    """이 프로젝트가 런타임 계약을 타는가.

    ⚠️ 여기서 다시 판정하지 않는다 — `profile_enforces_contract` 하나를 쓴다.
      두 곳에서 판정하면 「계약은 거는데 고지는 안 하는」 프로젝트가 생긴다."""
    return profile_enforces_contract(getattr(state, "runtime_contract_profile", "") or "")


def render(state: Any) -> str:
    """기획 프롬프트 뒤에 붙일 고지문. 계약을 안 타는 프로젝트에는 **빈 문자열**이다."""
    if not applies(state):
        return ""

    caps = arc.CAPABILITY_DECISION
    src = arc.SOURCE_INTENT_DECISION

    out = [
        "",
        "",
        "[🚨 이 플랫폼이 실제로 만들 수 있는 것 — 런타임 계약]",
        "",
        "이 프로젝트의 산출물은 **회사 호스트 안에서 도는 단일 화면 앱**입니다. 별도의 서버를",
        "띄우지 않고, 호스트가 내주는 데이터 평면만 씁니다. 아래는 규칙이 아니라 **사실**입니다 —",
        "여기에 없는 구조로 설계하면 그 설계로는 코드가 만들어지지 않습니다.",
        "",
        "■ 절대 설계하지 마십시오(계약상 금지 — 설계에 넣으면 계약 컴파일이 막힙니다)",
        *_lines(caps, arc.PROHIBITED),
        "",
        "  ⚠️ 그러므로 **백엔드 API 서버(Spring Boot·FastAPI·Express 등)를 설계하지 않습니다.**",
        "    REST 엔드포인트 목록·서버 라우팅·서버측 인증/세션/역할 설계는 이 프로젝트의",
        "    산출물이 아닙니다. DB 스키마도 **앱이 직접 붙는 DB** 가 아니라 «앱이 다루는",
        "    데이터셋의 모양»으로 적으십시오.",
        "",
        "■ 호스트가 대신 해 주는 것(앱이 직접 하지 않습니다)",
        *_lines(caps, arc.HOST_SERVICE_REQUIRED),
        "",
        "■ 앱이 바로 쓸 수 있는 것",
        *_lines(caps, arc.SUPPORTED),
        "",
        "■ 데이터는 어디서 오는가",
        *[f"  · `{k}` — {src[k][1]}" for k in sorted(_group(src, arc.SUPPORTED))],
        "",
        "  ⚠️ 기존 시스템(ERP·SCM)의 값은 **호스트가 읽어 줍니다.** 앱이 그 시스템을 직접",
        "    호출하도록 설계하지 마십시오 — 화면에서 다시 입력받게 설계하는 것도 안 됩니다.",
        "",
        "★ 요약: **화면 하나 + 호스트가 주는 데이터**입니다. 「무엇을 보여 주고 무엇을",
        "  결정하게 하는가」를 설계하십시오. 서버·인증·통신 계층은 이미 있고, 그것을 다시",
        "  설계하는 순간 그 산출물은 만들어질 수 없습니다.",
    ]
    return "\n".join(out)
