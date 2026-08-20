"""[CL-4 선행] Jarvis 문맥 어댑터 — **두 번째 비서를 만들지 않는다.**

작업서 §3 명칭 호환: "별도 비서 세션이나 두 번째 채팅 API 를 만들지 말고, **기존 계약 위에
호환 adapter 를 둔다**." 그래서 이 라우트는 새 엔진이 아니라 **주소 변환기**다 — 기존
`supervisor_daemon.handle_user_chat()` 을 그대로 부른다.

## 왜 어댑터가 필요했나

기존 계약은 `POST /api/v1/factory/{project_id}/supervisor/chat` 이다. **프로젝트 id 를 요구한다.**
그런데 협업·의사결정·발간 화면에는 프로젝트가 없다(릴리스·전달·결정이 대상이다). 그 상태에서
선택지는 셋이었다:

1. 가짜 project_id 를 넣는다 → 브리핑이 없는 프로젝트를 조회하고, 로그에 존재하지 않는
   프로젝트가 남는다. **거짓 데이터를 만드는 쪽**이므로 버렸다.
2. 두 번째 채팅 API 를 만든다 → §3 가 금지한다. 대화 이력이 갈라지고 "어느 비서에게 물었나"가
   생긴다.
3. **문맥을 표준화해 같은 엔진에 넘긴다** → 이 파일.

## JarvisContext (교차검토 지적 3)

화면마다 임시 응답 문자열을 복제하지 않기 위해 문맥 계약을 하나로 둔다:

    enterprise_scope · acting_user · current_module · selected_object ·
    object_snapshot · available_actions · evidence_refs

⚠️ `selected_object` 는 **화면이 강조 중인 객체와 같아야 한다.** 다르면 사용자는 A 를 보면서
  B 에 대한 답을 읽는다 — 그것이 가장 발견하기 어려운 오답이다.

⚠️ Task ID 를 사용자에게 묻지 않는다(§3-8). 문맥은 화면이 이미 알고 있는 것으로 채운다.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from api.deps import (Principal, assert_identified, current_principal)

from core.route_authority import guard as _route_authority_guard
# ★★ [2026-08-07] 권한 배정표를 **라우터에 붙인다.** 라우트마다 `require_caps` 를 적지
#   않는 이유: 37개에 적으면 37번 빠뜨릴 기회가 생기고, 새 라우트가 생겨도 아무도
#   알려 주지 않는다. 표는 `core/route_authority.ROUTE_CAPS` 하나뿐이며,
#   `tests/test_route_authority_table.py` 가 표와 라우터를 **양방향으로** 대조한다.
router = APIRouter(prefix="/api/v1/jarvis", tags=["Jarvis"], dependencies=[Depends(_route_authority_guard)])

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "자비스 컨텍스트"



class JarvisContext(BaseModel):
    """화면이 보내는 문맥. **서버는 이 값을 그대로 신뢰하지 않는다** — 회사 범위와 사용자는
    서버가 다시 판정해 덮어쓴다(도메인 §5.2: "클라이언트가 전달한 값을 그대로 신뢰하지 않는다")."""
    model_config = ConfigDict(extra="forbid")
    current_module: str                       # 'collaboration' | 'decision' | 'publication' …
    selected_object_type: str = ""            # 'app_delivery' | 'decision_case' | 'release' …
    selected_object_id: str = ""
    object_snapshot: Dict[str, Any] = {}      # 화면이 보고 있는 값(요약)
    available_actions: List[str] = []
    evidence_refs: List[Dict[str, Any]] = []


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str
    context: JarvisContext
    #: 프로젝트 화면에서 부를 때만 채운다. 없으면 프로젝트 없는 문맥으로 처리한다 —
    #: **가짜 id 를 만들지 않는다.**
    project_id: str = ""


def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail="사용자 식별이 필요합니다 — 비서는 현재 사용자 권한 안에서만 답합니다.")
    return uid


@router.get("/context-contract")
async def context_contract(
        p: Principal = Depends(current_principal)):
    """문맥 계약 스키마. 화면이 필드를 지어내지 않도록 서버가 알려준다.

    ★ 이 엔드포인트가 있는 이유: 화면 5개가 각자 다른 필드명을 쓰기 시작하면 어댑터가 문맥을
      해석하지 못하고, 그때부터 화면마다 임시 응답을 넣게 된다(지적 3 의 그 상태)."""
    assert_identified(p, WHAT)
    return {"status": "success", "data": {
        "fields": list(JarvisContext.model_fields.keys()),
        "note": ("selected_object 는 화면이 강조 중인 객체와 같아야 합니다 — 다르면 사용자는 "
                 "A 를 보면서 B 에 대한 답을 읽습니다."),
        "task_id_required": False,
    }}


@router.post("/ask")
async def ask(req: AskBody, p: Principal = Depends(current_principal)):
    """기존 Supervisor(=Jarvis) 엔진에 **문맥을 붙여** 그대로 넘긴다.

    ⚠️ 응답을 여기서 만들지 않는다. 고정 문자열로 답하면 화면은 동작하는 것처럼 보이지만
      비서는 없는 것이고, 그 상태가 화면 5개로 복제된다(교차검토 지적 3)."""
    actor = _actor(p)
    if not (req.message or "").strip():
        raise HTTPException(status_code=400, detail="질문이 비어 있습니다.")

    ctx = req.context
    # ★ 회사 범위·사용자는 **서버가 판정한 값**을 쓴다. 화면이 보낸 값은 참고하지 않는다.
    scope = p.scope
    snapshot: List[str] = [
        f"[요청자] {actor} · 무제한권한={bool(scope.unrestricted)} · "
        f"열람부서={len(scope.readable_dept_ids)}개 · 주부서={scope.primary_dept_id or '(미배정)'}",
        f"[화면] {ctx.current_module}",
    ]
    if ctx.selected_object_id:
        snapshot.append(f"[선택 객체] {ctx.selected_object_type or '?'} = {ctx.selected_object_id}")
    if ctx.object_snapshot:
        snapshot.append("[화면이 보고 있는 값] "
                        + json.dumps(ctx.object_snapshot, ensure_ascii=False)[:1200])
    if ctx.evidence_refs:
        snapshot.append("[근거] " + json.dumps(ctx.evidence_refs, ensure_ascii=False)[:800])
    if ctx.available_actions:
        snapshot.append("[이 화면에서 가능한 행동] " + ", ".join(ctx.available_actions[:12]))
    snapshot.append(
        "[지시] 위 문맥만 근거로 답하십시오. 문맥에 없는 수치·상태를 추측하지 말고 "
        "'화면에서 확인할 수 없다'고 말한 뒤 어디를 봐야 하는지 알려주십시오.")
    #: ★★ [UI 설계서 §7.2 답변 패턴] 답을 **여섯 단**으로 적게 한다.
    #
    #  ⚠️ 왜 형식을 강제하는가: 「핵심 답변」만 있는 답은 그럴듯하지만 검증할 수 없다. 특히
    #    **④ 부족하거나 확인하지 못한 데이터**를 적게 하지 않으면 비서는 모르는 것도 아는
    #    것처럼 말한다 — 이 저장소가 화면 전체에서 «조회 실패 ≠ 0건» 으로 지켜 온 규칙이
    #    비서 답변에서만 무너지면 아무 의미가 없다.
    #
    #  ⚠️ 형식을 어겨도 화면은 깨지지 않는다 — 프론트가 머리말을 못 찾으면 평문 그대로
    #    보여 준다. LLM 출력에 화면의 동작을 걸지 않는다.
    snapshot.append(
        "[답변 형식] 아래 여섯 머리말을 **그대로** 쓰고 각 줄 아래에 내용을 적으십시오. "
        "해당 없으면 '없음' 이라고 쓰되 머리말은 지우지 마십시오.\n"
        "핵심 답변:\n왜 그렇게 판단했는가:\n근거와 기준시각:\n"
        "부족하거나 확인하지 못한 데이터:\n선택 가능한 다음 행동:\n실행 시 영향과 승인 필요 여부:")

    state_data: Dict[str, Any] = {}
    pid = (req.project_id or "").strip()
    if pid:
        # 프로젝트 문맥이 있으면 기존 경로와 같은 권한 판정을 통과해야 한다.
        from api.deps import assert_project_readable
        assert_project_readable(p, pid)
        import os

        # ★ [2026-08-05] 상대경로였다. Jarvis 가 프로젝트 상태를 못 읽으면 오류가 아니라
        #   **덜 아는 답**이 나온다 — 그래서 아무도 눈치채지 못한다.
        from core.paths import workspace_path
        path = workspace_path(pid, "latest_state.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
            except Exception:
                state_data = {}

    try:
        from core.supervisor_daemon import supervisor_daemon
        # 기존 엔진 · 기존 세션. 새 대화 저장소를 만들지 않는다(§3).
        result = await supervisor_daemon.handle_user_chat(
            pid, "", req.message.strip(), state_data, system_snapshot="\n".join(snapshot))
    except Exception as e:
        # ⚠️ 실패를 그럴듯한 답으로 대체하지 않는다 — 비서가 답한 것처럼 보이면 사용자는 그
        #   내용을 근거로 판단한다.
        raise HTTPException(status_code=502,
                            detail=f"비서 응답을 받지 못했습니다: {e}")

    #: ★★★ [2026-08-20 실측] **엔진이 예외를 삼킨다.** `supervisor_daemon.handle_user_chat`
    #:   는 실패해도 던지지 않고 `{"status": "error", "reply": "…오류가 발생했습니다"}` 를
    #:   돌려준다. 그래서 위 `except` 는 **한 번도 돌지 않았고**, LLM 키가 없어 답을 못
    #:   만든 상황이 그대로 **HTTP 200 «success»** 로 나갔다.
    #:
    #: ⚠️ 이 파일이 바로 위에서 「실패를 그럴듯한 답으로 대체하지 않는다」고 적어 둔 바로
    #:   그 일이 일어나고 있었다 — 말과 코드가 갈라져 있었다. 봉투의 `status` 를 보는
    #:   호출부는 «성공» 으로 읽는다.
    if str((result or {}).get("status", "")) == "error":
        raise HTTPException(
            status_code=502,
            detail=str((result or {}).get("reply")
                       or "비서 응답을 받지 못했습니다."))
    return {"status": "success", "data": {
        "reply": (result or {}).get("reply", ""),
        "intervene": bool((result or {}).get("intervene")),
        "context_echo": {"module": ctx.current_module,
                         "selected_object_id": ctx.selected_object_id},
    }}
