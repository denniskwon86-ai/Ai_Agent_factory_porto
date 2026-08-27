"""★★★ 요구가 **들어오는 자리**에서 「이 플랫폼에서 이미 충족된 것」을 못박는다. (2026-08-27)

## ⚠️⚠️ 왜 뒤에서 잡으면 안 되는가 — 두 시간을 태우고 배웠다

사용자 아이디어에 「사용자 로그인과 권한 관리를 포함한다」가 들어왔다. 이 플랫폼에서
그것은 **만들 수 없다**(`auth.local_login`·`auth.local_roles`·`auth.local_session` 은
`PROHIBITED`). 그런데 파이프라인은 그것을 안고 끝까지 돌았다:

    RFP     REQ-008 «관리자가 권한을 제어한다» Must 로 채택
    PRD·WBS 그 요구를 추적성 검사가 **밀어 올림** (E2E-06 태스크 생성)
    계약    그 요구를 **말없이 빠뜨림**(능력에도, 미지원 목록에도 없음)
    이후    5개 태스크가 더 돌고 두 시간 뒤 사람이 화면에서 발견

## 왜 고지문·비평·채점이 다 못 막았나 (실측)

  ① **고지문은 작성자에게만 갔다.** `debate.run_debate` 는 `extra_instruction` 을
     작성자 프롬프트에만 붙이고 **비평가에게는 안 붙인다** — 비평가는 이 플랫폼이
     무엇을 못 만드는지 **한 글자도 모른 채** 비평한다.
  ② **채점에 그 축이 없다.** 8단계 35개 검사 중 «만들 수 있는가» 는 **0개**이고,
     완성도·추적성 검사가 **7개**다. `must_have_components` 는 「요청한 것이 빠짐없이
     있는가」를 본다 — 즉 루브릭이 그 요구의 **포함을 보상**했다.
  ③ 그리고 `context_engine` 은 `initial_idea` 를 **모든 에이전트 문맥**에
     `[초기 기획]` 으로 넣는다. 원문이 «목표» 로 매 단계에 뿌려지는데, 고지문은
     그 뒤에 붙는 부록이었다. **측정되는 것과 부탁하는 것이 싸우면 측정되는 쪽이 이긴다.**

★★★ 그래서 **목표 자체를 고친다.** 요구가 들어오는 한 지점에서 못박으면, 뒤의 모든
  독자(RFP 작성자·비평가·PRD·WBS·문맥 엔진·그라운딩)가 같은 사실을 본다.

## ⚠️ 사용자의 말을 **지우지 않는다**

원문은 그대로 두고 **확정 사실을 덧붙인다.** 지우면 사용자는 자기가 요청한 것이 어디
갔는지 알 수 없고, 완성도 검사도 「빠졌다」고 깎는다. 「이미 충족됨(구현 대상 아님)」으로
적을 길을 열어 주면 **완성도와 실현가능성이 동시에 만족**된다 — 둘이 싸우지 않는다.

## ⚠️ 목록을 손으로 적지 않는다

금지 항목은 `app_runtime_contract.CAPABILITY_DECISION` 에서 읽는다. 컴파일러가 막는 것과
고지하는 것이 **같은 출처**여야 한다 — 손으로 옮기면 바뀐 날 조용히 갈린다(이 저장소가
같은 실수를 세 번 했다).

LLM 0콜.
"""
from __future__ import annotations

from typing import Any, Dict, List

#: 덧붙인 블록의 시작 표지. **재진입해도 두 번 붙지 않게** 하는 근거다.
#: ⚠️ `start_sprint` 는 태스크마다 불린다 — 표지가 없으면 목표가 매번 길어진다.
MARKER = "[🚨 이 플랫폼의 확정 사실 — 아래는 이미 충족되어 있습니다]"

#: 금지 능력을 사람 말로 옮길 때 쓰는 이름. **판정에는 쓰지 않는다** — 판정은 닫힌 목록이
#: 하고, 이것은 그 항목을 사람이 읽을 수 있게만 만든다.
_KO: Dict[str, str] = {
    "auth.local_login": "사용자 인증 — 로그인·로그아웃·회원가입·비밀번호",
    "auth.local_roles": "사용자별 권한 부여·변경·관리",
    "auth.local_session": "세션 유지·로그인 상태 관리",
    "storage.credentials": "자격증명 보관",
    "storage.local_db": "앱 자체 데이터베이스",
    "api.direct_call": "앱이 외부 API 를 직접 호출",
}

#: 「이미 충족됨」이라고 말할 수 있는 것만 여기 담는다.
#: ⚠️ `storage.local_db`·`api.direct_call` 은 «이미 충족» 이 아니라 «다른 길이 있다» 다 —
#:   문구를 나눈다. 같은 말로 뭉개면 「DB 가 이미 있으니 쓰면 되겠네」로 읽힌다.
_ALREADY_PROVIDED = ("auth.local_login", "auth.local_roles", "auth.local_session")


def _prohibited() -> List[str]:
    """금지 능력 목록. **닫힌 목록에서 읽는다.**"""
    from core import app_runtime_contract as arc

    return sorted(k for k, (s, _r) in arc.CAPABILITY_DECISION.items()
                  if s == arc.PROHIBITED)


def already_applied(idea: Any) -> bool:
    return MARKER in str(idea or "")


def render_clause() -> str:
    """요구문 뒤에 붙일 확정 사실 블록."""
    prohibited = _prohibited()
    provided = [c for c in prohibited if c in _ALREADY_PROVIDED]
    other = [c for c in prohibited if c not in _ALREADY_PROVIDED]
    out = ["", "", MARKER, "",
           "이 앱은 회사 시스템 **안에서** 열립니다(앱인앱). 그래서 아래는 회사 시스템이",
           "이미 처리했고, **이 프로젝트가 만들 항목이 아닙니다.**", ""]
    for cap in provided:
        out.append(f"  · {_KO.get(cap, cap)}  →  회사 시스템이 이미 제공합니다")
    if other:
        out.append("")
        out.append("아래는 **다른 길로만** 됩니다(앱이 직접 하지 않습니다):")
        for cap in other:
            out.append(f"  · {_KO.get(cap, cap)}  →  호스트 데이터 평면을 씁니다")
    out += [
        "",
        "★ 위에 해당하는 요구가 **위 요구문에 적혀 있더라도**, 그것은 이미 충족된 것으로",
        "  다루십시오. 요구사항·기획·WBS 어디에도 «만들 항목»으로 넣지 마십시오.",
        "★ 지우지는 마십시오 — 「**호스트가 제공(구현 대상 아님)**」으로 적으면 됩니다.",
        "  그렇게 적으면 누락이 아니라 **처리된 것**입니다.",
        "⚠️ 만들 수 없는 것을 «Must» 로 남기면 그것을 위한 태스크가 생기고, 계약 단계에서",
        "  막히며, 그 프로젝트는 거기서 멈춥니다(실측: 두 시간을 그렇게 태웠습니다).",
    ]
    return "\n".join(out)


def normalize_idea(idea: Any, *, enforced: bool) -> str:
    """요구문에 확정 사실을 덧붙인다. **원문은 건드리지 않는다.**

    · `enforced` 가 거짓이면(계약 프로필 꺼진 레거시) **그대로 돌려준다** —
      그 프로젝트들은 자유 형식 앱을 만들어 왔고, 소급하면 깨진다.
    · 이미 붙어 있으면 다시 붙이지 않는다(`start_sprint` 는 태스크마다 불린다).
    """
    text = str(idea or "")
    if not enforced or not text.strip() or already_applied(text):
        return text
    return text + render_clause()
