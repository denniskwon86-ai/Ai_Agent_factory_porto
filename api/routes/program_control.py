"""[사용자 결정 2026-07-30] 프로그램 사용여부 제어 API. prefix `/api/v1/programs`. **LLM 0콜.**

> "이미 생성되어 다른 사용자가 기록을 남긴 코드(프로그램)을 삭제하면 꼬일 수 있으니
>  그냥 사용여부만 제어해서 더이상 사용하지 않는 프로그램이라고 비활성화 조치만 하는 것이
>  좋을 것 같습니다."

IT 관리자만 바꿀 수 있다. 여기서 쓰는 권한은 **새로 만들지 않고** 기존 관리자 판정
(`scope.is_admin` / `can_edit_org` / `unrestricted`)을 재사용한다 —
새 플래그를 도입하면 아무에게도 켜져 있지 않아 **기능이 있는데 아무도 못 쓰는 상태**가 된다.

조회는 누구나 할 수 있다. "이 프로그램을 왜 못 쓰는가"는 막힌 사람이 알아야 하는 정보다.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import (Principal, assert_identified, current_principal)
from core.route_authority import guard as _route_authority_guard
from core.program_lifecycle import (DEPRECATED, DISABLED, STATUSES,
                                    ProgramLifecycleError, program_lifecycle)

# ★★ [2026-08-07] 권한 배정표를 **라우터에 붙인다.** 라우트마다 `require_caps` 를 적지
#   않는 이유: 37개에 적으면 37번 빠뜨릴 기회가 생기고, 새 라우트가 생겨도 아무도
#   알려 주지 않는다. 표는 `core/route_authority.ROUTE_CAPS` 하나뿐이며,
#   `tests/test_route_authority_table.py` 가 표와 라우터를 **양방향으로** 대조한다.
router = APIRouter(prefix="/api/v1/programs", tags=["Programs"], dependencies=[Depends(_route_authority_guard)])

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "프로그램"



def _admin(p: Principal) -> str:
    """IT 관리자 판정 + 변경자 식별. 둘 다 없으면 감사 기록이 성립하지 않는다."""
    if not p.user_id:
        raise HTTPException(
            status_code=401,
            detail="변경자 식별 정보가 없습니다 — X-User-Id 를 보내십시오. "
                   "누가 껐는지 모르는 비활성화는 감사 대상이 될 수 없습니다.")
    if not (p.scope.unrestricted or p.scope.is_admin or p.scope.can_edit_org):
        raise HTTPException(
            status_code=403,
            detail="프로그램 사용여부는 IT 관리자만 변경할 수 있습니다.")
    return p.user_id


def _err(e: ProgramLifecycleError):
    raise HTTPException(status_code=409, detail=str(e))


class StatusRequest(BaseModel):
    #: 사유는 비활성/예고 시 필수 — 없으면 나중에 되돌릴 근거가 없어 아무도 다시 켜지 못한다.
    reason: str = ""
    #: 갈 곳을 알려주지 않으면 사용자는 같은 프로그램을 다시 만든다.
    replacement_release_id: Optional[str] = ""
    #: 의존 대상이 있을 때만 필요하다. 조용히 끄면 끊긴 쪽이 원인을 모른 채 고장난다.
    acknowledge_dependents: bool = False


class SetStatusRequest(StatusRequest):
    status: str


@router.get("")
async def list_statuses(status: str = "",
        p: Principal = Depends(current_principal)):
    """사용여부가 **기록된** 프로그램 목록. 미기록 프로그램은 여기 나오지 않는다."""
    assert_identified(p, WHAT)
    if status and status not in STATUSES:
        raise HTTPException(status_code=400,
                            detail=f"허용되지 않은 상태입니다(허용: {', '.join(STATUSES)}).")
    data = await asyncio.to_thread(program_lifecycle.list_statuses, status)
    return {"status": "success", "data": data,
            "note": ("사용여부를 한 번도 지정하지 않은 프로그램은 이 목록에 없습니다 — "
                     "사용 가능으로 간주되지만 관리자가 승인한 상태는 아닙니다.")}


@router.get("/{release_id}")
async def get_status(release_id: str,
        p: Principal = Depends(current_principal)):
    """현재 사용여부 + 변경 이력 + 의존 관계. 막힌 사람도 볼 수 있어야 한다."""
    assert_identified(p, WHAT)
    st = await asyncio.to_thread(program_lifecycle.get_status, release_id)
    st["history"] = await asyncio.to_thread(program_lifecycle.history, release_id)
    st["dependents"] = await asyncio.to_thread(program_lifecycle.dependents, release_id)
    return {"status": "success", "data": st}


@router.post("/{release_id}/disable")
async def disable(release_id: str, req: StatusRequest,
                  p: Principal = Depends(current_principal)):
    """사용 중단 — **삭제가 아니다.** 기록·이력은 그대로 보존된다."""
    actor = _admin(p)
    try:
        data = await asyncio.to_thread(
            program_lifecycle.disable, release_id, actor, req.reason,
            req.replacement_release_id or "", req.acknowledge_dependents)
        return {"status": "success", "data": data}
    except ProgramLifecycleError as e:
        _err(e)


@router.post("/{release_id}/deprecate")
async def deprecate(release_id: str, req: StatusRequest,
                    p: Principal = Depends(current_principal)):
    """사용 중단 **예고** — 아직 쓸 수 있지만 소비 화면에 경고가 붙는다.

    예고 없이 죽이면 의존하던 부서가 원인 모를 고장을 겪는다."""
    actor = _admin(p)
    try:
        data = await asyncio.to_thread(
            program_lifecycle.set_status, release_id, DEPRECATED, actor, req.reason,
            req.replacement_release_id or "", req.acknowledge_dependents)
        return {"status": "success", "data": data}
    except ProgramLifecycleError as e:
        _err(e)


@router.post("/{release_id}/reactivate")
async def reactivate(release_id: str, req: StatusRequest,
                     p: Principal = Depends(current_principal)):
    """사용 재개. 되돌릴 수 있어야 관리자가 겁내지 않고 끌 수 있다."""
    actor = _admin(p)
    try:
        data = await asyncio.to_thread(program_lifecycle.reactivate, release_id, actor,
                                       req.reason)
        return {"status": "success", "data": data}
    except ProgramLifecycleError as e:
        _err(e)


@router.post("/{release_id}/status")
async def set_status(release_id: str, req: SetStatusRequest,
                     p: Principal = Depends(current_principal)):
    """상태를 직접 지정한다(위 3개 경로의 일반형)."""
    actor = _admin(p)
    try:
        data = await asyncio.to_thread(
            program_lifecycle.set_status, release_id, req.status, actor, req.reason,
            req.replacement_release_id or "", req.acknowledge_dependents)
        return {"status": "success", "data": data}
    except ProgramLifecycleError as e:
        _err(e)


@router.get("/{release_id}/usable")
async def check_usable(release_id: str,
        p: Principal = Depends(current_principal)):
    """사용 가능 여부만 묻는다. 소비 화면이 실행 버튼을 열기 전에 호출한다.

    ⚠️ 이 판정을 **UI 만** 믿게 두면 통제가 아니다 — 실행 payload 는 서버가
      `GET /factory/library/item/{id}` 에서 직접 막는다."""
    assert_identified(p, WHAT)
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(program_lifecycle.assert_usable,
                                                release_id)}
    except ProgramLifecycleError as e:
        st = await asyncio.to_thread(program_lifecycle.get_status, release_id)
        return {"status": "success",
                "data": {"usable": False, "status": st["status"], "reason": str(e),
                         "replacement_release_id":
                             st.get("replacement_release_id", "")}}
