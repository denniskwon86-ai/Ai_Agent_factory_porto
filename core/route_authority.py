"""★★★ 라우트 → 필요한 권한. **표가 곧 코드다.**

## 왜 문서가 아니라 코드인가

권한 배정을 문서로 두면 코드와 갈라진다. 이 저장소는 그 유형을 아홉 번 겪었고, 트랙 G 도
「손으로 관리하는 `READ_PATHS`」에 `/facts` 가 빠져 익명 유출을 통과시켰다. 그래서 표를
**실행되는 값**으로 두고, 라우터 의존성 하나가 매 요청 이 표를 읽는다. 표에 없는 라우트는
통과하며, 테스트가 «표에 없는 쓰기 라우트» 를 잡는다.

## 어떻게 붙는가

라우터에 **한 줄**만 더한다:

    router = APIRouter(prefix="...", dependencies=[Depends(route_authority.guard)])

★ 라우트마다 `require_caps(...)` 를 적지 않는다. 37개에 적으면 37번 빠뜨릴 기회가 생기고,
  새 라우트가 생길 때 아무도 알려 주지 않는다. 의존성은 **라우터에 들어오는 모든 요청**이
  지나므로, 새 라우트는 «표에 넣거나 명시적으로 면제하거나» 둘 중 하나를 해야 한다.

## 배정 기준 — **되돌리기 비용**으로 끊었다

| 계층 | 무엇이 다른가 | 코드 |
|---|---|---|
| 만들기 | 되돌리기 쉽다(빈 프로젝트) | `project.create` |
| 돌리기 | LLM 비용이 나가고 되돌릴 수 없다 | `project.run` |
| 고치기 | 남의 자료를 끌어온다(지식·기준정보·소유권) | `project.edit` |
| 게시 | **남에게 나간다.** 회수해도 이미 본 사람이 있다 | `project.release` |

역할 배정(`admin_capability._ROLE_CAPS`):
· viewer — 없음 · member — create·run·edit · manager — 넷 다
· AI 거버넌스 관리자 — 넷 다(어느 부서의 실행이든 멈출 수 있어야 한다)

## ⚠️ 이 표가 **하지 않는** 것

**범위 판정을 대신하지 않는다.** 「이 사람이 프로젝트를 돌릴 수 있는가」와 「이 프로젝트를
돌릴 수 있는가」는 다른 질문이다. 후자는 `assert_project_writable`·`classify()` 같은
자원별 판정이 답한다. 이 표는 **앞의 질문만** 답하고, 자원별 판정을 지우지 않는다 —
둘 다 있어야 「내 부서 프로젝트는 되고 남의 것은 안 된다」가 성립한다.
"""
from __future__ import annotations

from typing import Dict, Tuple

from fastapi import Depends, Request

# ⚠️ `api.deps` 를 모듈 최상단에서 가져온다 — `Depends(...)` 는 **함수 정의 시점**에 평가되므로
#   함수 안에서 늦게 import 할 수 없다. `api.deps` 는 이 모듈을 참조하지 않으므로 순환은 없다.
from api.deps import current_principal as _current_principal

from core.admin_capability import (ADMIN_DATA_ACCESS, ADMIN_ORGANIZATION, AGENT_EXECUTE,
                                   PROJECT_CREATE, PROJECT_EDIT, PROJECT_RELEASE, PROJECT_RUN)

F = "/api/v1/factory"

#: **라우트 → 요구 권한.** 키는 `"<METHOD> <path>"` 이며 path 는 FastAPI 가 등록한 그대로다
#: (경로 파라미터 포함). ⚠️ 손으로 문자열을 짓지 말 것 — 테스트가 라우터와 대조한다.
ROUTE_CAPS: Dict[str, Tuple[str, ...]] = {

    # ── 프로젝트 만들기 ─────────────────────────────────────────────────────
    f"POST {F}/projects": (PROJECT_CREATE,),
    f"POST {F}/projects/mega": (PROJECT_CREATE,),
    f"POST {F}/projects/{{project_id}}/copy": (PROJECT_CREATE,),
    # 청사진에서 프로젝트가 태어난다 — 만드는 일이다.
    "POST /api/v1/advisor/blueprints/{blueprint_id}/bootstrap-project": (PROJECT_CREATE,),

    # ── 프로젝트 돌리기 (LLM 비용·되돌릴 수 없음) ───────────────────────────
    f"POST {F}/{{project_id}}/sprint/start": (PROJECT_RUN,),
    f"POST {F}/{{project_id}}/sprint/pause": (PROJECT_RUN,),
    f"POST {F}/{{project_id}}/sprint/stop": (PROJECT_RUN,),
    f"POST {F}/{{project_id}}/sprint/resume-quota": (PROJECT_RUN,),
    f"POST {F}/{{project_id}}/sprint/revision": (PROJECT_RUN,),
    f"POST {F}/{{project_id}}/heal": (PROJECT_RUN,),
    f"POST {F}/{{project_id}}/wbs/replan": (PROJECT_RUN,),
    f"POST {F}/{{project_id}}/resimulate": (PROJECT_RUN,),
    f"POST {F}/projects/{{project_id}}/mega/plan": (PROJECT_RUN,),
    f"POST {F}/projects/{{project_id}}/mega/start_all": (PROJECT_RUN,),
    # ★ HOTL 재개 = **사람이 답해야 하는 지점을 통과시키는 일**이다. 실측 이력: 익명이 이
    #   경로로 중단점을 넘길 수 있었고, 그때 「중단점을 지우려면 관리자 권한」이라는 통제는
    #   지울 필요 없이 우회됐다(`api/deps._assert_identified_for_project` 주석).
    f"POST {F}/{{project_id}}/hotl/resume": (PROJECT_RUN,),
    # ★ [I-4 4c-3] 계약 검토 결정도 파이프라인을 진행시킨다 — 같은 권한이다.
    #   ⚠️ 짝인 `GET .../contract-review/pending` 은 이 표에 넣지 않는다. 이 표는
    #     **쓰기 라우트 전용**이고(회귀가 라우터와 대조한다), 읽기 쪽 권한은 핸들러가
    #     `require_caps(PROJECT_RUN)` 로 직접 요구한다 — 승인할 수 없는 사람에게
    #     「승인할 것이 있다」를 알릴 이유가 없다.
    f"POST {F}/{{project_id}}/contract-review/decision": (PROJECT_RUN,),

    # ── [I-4 7 / Wave F-2] 후보 판을 **운영으로 올린다** ────────────────
    #   ★★★ 이것은 «만들기» 가 아니라 «운영에 내보내기» 다. 이 순간부터 그 앱은
    #     실제 조직 데이터를 만지므로, 프로젝트를 굴릴 수 있는 권한을 요구한다.
    #   ⚠️ 사전 확인(`GET .../promotion-check`)은 읽기라 표에 넣지 않는다 —
    #     표는 쓰기 전용이고, 그쪽은 핸들러가 직접 `assert_project_readable` 한다.
    f"POST {F}/{{project_id}}/releases/{{release_id}}/promote": (PROJECT_RUN,),

    # ── [BDR-2] 업무 데이터 준비 ────────────────────────────────────────
    #   ★ 키트를 조직에 «적용» 하는 것은 자원을 만드는 일이다 → `PROJECT_CREATE`.
    #     결속을 붙이고 상태를 옮기는 것은 운영이다 → `PROJECT_RUN`.
    "POST /api/v1/data-preparation/instances": (PROJECT_CREATE,),
    "POST /api/v1/data-preparation/instances/{instance_id}/bindings": (PROJECT_RUN,),
    "POST /api/v1/data-preparation/bindings/{binding_id}/decision": (PROJECT_RUN,),
    #   ★ [BDR-3] 파일 적재도 운영이다 — 「올리기만 하는 것」이 아니라 그 파일이
    #     이후 계산의 원천이 된다.
    "POST /api/v1/data-preparation/bindings/{binding_id}/snapshots": (PROJECT_RUN,),
    # 감독관 대화도 LLM 을 태운다 — 「채팅이니까」로 열어 두면 비용 통제에 구멍이 난다.
    f"POST {F}/{{project_id}}/supervisor/chat": (PROJECT_RUN,),
    f"POST {F}/ai-recommend/pipeline": (PROJECT_RUN,),

    # ── 프로젝트 고치기 (남의 자료를 끌어온다) ──────────────────────────────
    f"PUT {F}/projects/{{project_id}}/knowledge": (PROJECT_EDIT,),
    # ★ 소유권 변경은 **이 표의 통제를 무력화할 수 있는 행위**다 — 소유자를 자기로 바꾸면
    #   자원별 판정이 전부 통과한다. 그래서 `project.edit` 에 조직 관리 권한을 **함께** 요구한다.
    f"PUT {F}/{{project_id}}/ownership": (PROJECT_EDIT, ADMIN_ORGANIZATION),
    "POST /api/v1/advisor/blueprints/{blueprint_id}/create-data-tasks": (PROJECT_EDIT,),

    # ── 게시·회수 (남에게 나간다) ───────────────────────────────────────────
    f"POST {F}/{{project_id}}/release": (PROJECT_RELEASE,),
    f"DELETE {F}/library/item/{{release_id}}": (PROJECT_RELEASE,),
    # 게시된 프로그램의 사용 여부 통제. `library_paths` 주석이 적은 그 사고 —
    # 「IT 관리자는 사고를 낸 프로그램을 끌 수 없다」 — 의 반대편 통제다.
    "POST /api/v1/programs/{release_id}/disable": (PROJECT_RELEASE,),
    "POST /api/v1/programs/{release_id}/deprecate": (PROJECT_RELEASE,),
    "POST /api/v1/programs/{release_id}/reactivate": (PROJECT_RELEASE,),
    "POST /api/v1/programs/{release_id}/status": (PROJECT_RELEASE,),
    # 청사진 승인 = 「이대로 만든다」를 확정한다.
    "POST /api/v1/advisor/blueprints/{blueprint_id}/approve": (PROJECT_RELEASE,),

    # ── 데이터 관리 ─────────────────────────────────────────────────────────
    # 커넥터 조회 실행은 **실제로 외부 시스템 데이터를 가져온다.**
    "POST /api/v1/connectors/{connector_id}/execute": (ADMIN_DATA_ACCESS,),
    # 참조 데이터 스캔·색인.
    "POST /api/v1/reference/scan": (ADMIN_DATA_ACCESS,),
    # 전사 집계·경영진 보드 생성 — 조직 전체를 가로지른다.
    "POST /api/v1/enterprise-context/rollup": (ADMIN_DATA_ACCESS,),
    "POST /api/v1/enterprise-context/executive-board": (ADMIN_DATA_ACCESS,),
    "POST /api/v1/enterprise-context/contexts/select": (ADMIN_ORGANIZATION,),

    # ── 실행(LLM) ───────────────────────────────────────────────────────────
    # viewer 도 가진 권한이다. 막으려는 것이 아니라 **익명·미등록을 걸러내고 감사에 남기는**
    # 것이 목적이다 — 비용이 나가는 경로는 누가 눌렀는지 남아야 한다.
    "POST /api/v1/jarvis/ask": (AGENT_EXECUTE,),
    "POST /api/v1/advisor/consultations": (AGENT_EXECUTE,),
    "POST /api/v1/advisor/consultations/{consultation_id}/messages": (AGENT_EXECUTE,),
    "POST /api/v1/advisor/consultations/{consultation_id}/blueprint": (AGENT_EXECUTE,),
}

#: **표에 없어도 되는 쓰기 라우트**와 그 이유. 비워 두면 테스트가 잡는다.
#:
#: ⚠️ 「나중에 넣자」로 여기 올리지 않는다 — 면제 목록은 조용히 자란다. 각 항목은 «다른 곳에
#:   이미 판정이 있다» 여야 하고, 그 위치를 적는다.
EXEMPT: Dict[str, str] = {
    f"DELETE {F}/projects/{{project_id}}":
        "core/project_deletion.classify() — 등록자/공유여부/실제삭제를 함께 본다",
    f"POST {F}/projects/{{project_id}}/restore":
        "core/project_deletion.classify() — 삭제와 같은 판정",
    "POST /api/v1/connectors/{connector_id}/validate":
        "쓰지 않는 조회(계약 위반 계산). 식별만 요구한다",
}


def required_caps(method: str, path: str) -> Tuple[str, ...]:
    """이 라우트에 필요한 권한. 없으면 빈 튜플(= 이 표는 관여하지 않는다)."""
    return ROUTE_CAPS.get(f"{(method or '').upper()} {path}", ())


async def guard(request: Request, p=Depends(_current_principal)) -> None:
    """★ 라우터 의존성. **표에 있는 라우트만** 막는다.

    ⚠️ 라우트 경로는 `request.scope["route"].path` 에서 읽는다 — URL 문자열이 아니라
      **등록된 패턴**이다. URL 로 맞추면 `{project_id}` 자리에 들어온 값 때문에 표를 못 찾고,
      그러면 통제가 조용히 사라진다(가장 위험한 실패 방식이다).

    ⚠️⚠️ **`request: Request` 의 타입 표기를 지우지 말 것.** 표기가 없으면 FastAPI 는 이것을
      **쿼리 파라미터** `?request=` 로 읽고, 그 라우터의 **모든 요청이 422** 가 된다.
      2026-08-07 에 실제로 그렇게 붙였고 `tests/test_route_authority_table.py` 가 잡았다 —
      통제를 붙이려다 라우터 전체를 못 쓰게 만들 뻔했다.

    ★★ **주체는 `Depends` 로 받는다 — 직접 `await current_principal(request)` 하지 않는다.**
      직접 부르면 `app.dependency_overrides` 를 지나친다. 실제로 그렇게 만들었더니 주체를
      대역으로 바꾼 테스트에서 **미등록·폐지 계정이 익명으로 보였다**(403 이어야 할 자리에
      401). 더 나쁜 것은 «막히긴 했다» 는 점이다 — 통제는 작동하는데 **이유가 틀렸고**,
      틀린 이유는 사용자를 엉뚱한 조치로 보낸다(로그인했는데 또 로그인하라고 한다).
      운영에서도 주체를 두 번 해석하는 셈이라 그 둘이 갈라질 자리를 만든다.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", "") if route is not None else ""
    if not path:
        return
    caps = required_caps(request.method, path)
    if not caps:
        return

    # ★★ **권한 강제 스위치를 존중한다.** 이 저장소의 다른 판정은 전부
    #   `visibility_block_reason` 처럼 강제가 꺼져 있으면 «아무것도 막지 않는다» 는 하위호환
    #   계약을 지킨다. 이 표만 예외로 두면 강제를 켜지 않은 환경에서 **쓰기 라우트가 전부**
    #   401 이 된다.
    #
    # ⚠️ 실제로 그렇게 만들었다가 전체 테스트 15건이 깨졌다(2026-08-07). 증상은
    #   「혼자 돌면 통과, 전체로 돌면 401」이었는데, 원인은 순서가 아니라 **계약 위반**이었다 —
    #   앞선 테스트가 조직에 사용자를 심으면 익명이 `unrestricted` 를 잃고, 그때부터 이 표가
    #   막았다. 스위치를 존중하니 조건이 사라졌다.
    #
    # ★ 이것은 통제를 약하게 만드는 것이 아니다. 살아 있는 서버에서 `_org_enforce_effective()`
    #   는 **True** 다(2026-08-07 실측). 즉 운영에서는 표가 그대로 작동하고, 강제를 켜지 않은
    #   개발·테스트 환경만 종전처럼 흐른다.
    from api.deps import _enforced, require_caps
    if not _enforced():
        return
    require_caps(p, *caps, resource="route", action=f"{request.method} {path}")
