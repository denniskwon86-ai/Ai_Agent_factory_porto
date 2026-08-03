"""[CL-1] 개인 앱 전달 API — 작업서 §CL-BE-02.

## 오류 코드 규약 (§3-10)

| 상황 | 코드 | 이유 |
|---|---|---|
| 식별 안 됨 | **401** | 인증 실패는 숨기지 않는다 — 사용자가 로그인해야 함을 알아야 한다 |
| 요청 형식 오류 | **422** | FastAPI 기본. 형식은 알려줘도 정보가 새지 않는다 |
| 남의 자원·없는 자원 | **404** | 403 은 "있지만 못 본다"를 알려주므로 **존재가 새어나간다** |
| 정책 위반(만료·중복응답 등) | **400** | 내 자원에 대한 판정이므로 이유를 말해도 된다 |

⚠️ 404 와 403 의 차이가 이 작업의 보안 요건이다. `NotFoundOrHidden` 하나로 묶어 라우트에서
  구분하지 않는 것이 그 장치다 — 구분할 수 있으면 언젠가 구분해서 답한다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from api.deps import Principal, current_principal
from core.app_delivery import AppDeliveryError, NotFoundOrHidden, app_delivery

router = APIRouter(tags=["AppDelivery"])


def _actor(p: Principal) -> str:
    """식별된 사용자. **없으면 401** — 개인 전달은 "누가 누구에게"가 전부이므로 익명은 성립하지 않는다."""
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("사용자 식별이 필요합니다 — 개인 앱 전달은 보내는 사람과 받는 사람이 "
                    "누구인지가 기록의 전부입니다. 우측 상단에서 사용자를 지정하십시오."))
    return uid


def _hidden(e: NotFoundOrHidden):
    raise HTTPException(status_code=404, detail="요청을 찾을 수 없습니다.")


def _bad(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


class DeliveryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")     # §CL-BE-01
    release_id: str
    recipient_user_id: str
    purpose: str
    expires_in_days: int = 14
    idempotency_key: str = ""


class RespondBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = ""
    display_name: str = ""


class RevokeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = ""


class PocketPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: Optional[str] = None
    pinned: Optional[bool] = None
    mark_opened: bool = False


@router.post("/api/v1/app-deliveries")
async def create_delivery(req: DeliveryCreate, p: Principal = Depends(current_principal)):
    """앱을 **지정 사용자 한 명**에게 전달한다.

    ★ 조직 공유(`workspace_shares`)·업무 배정·전사 승격과 다른 경로다(§3-1,2). 여기서 만든
      상태는 그 세 곳에 섞이지 않는다."""
    sender = _actor(p)
    try:
        data = app_delivery.create(
            release_id=req.release_id, sender_user_id=sender,
            recipient_user_id=req.recipient_user_id.strip(), purpose=req.purpose,
            expires_in_days=req.expires_in_days, idempotency_key=req.idempotency_key,
            enterprise_scope_id=(p.scope.primary_dept_id or ""),
            permission_snapshot={
                # 전달 시점의 **보낸 사람** 권한을 남긴다. 수신자 권한이 아니다 —
                # 수락은 권한을 넓히지 않으므로 수신자 권한은 실행 시점에 판정된다.
                "sender_readable_dept_ids": sorted(p.scope.readable_dept_ids),
                "sender_unrestricted": bool(p.scope.unrestricted),
            })
    except NotFoundOrHidden as e:
        _hidden(e)
    except AppDeliveryError as e:
        _bad(e)
    return {"status": "success", "data": data}


@router.get("/api/v1/app-deliveries/inbox")
async def inbox(only_pending: bool = False, p: Principal = Depends(current_principal)):
    """받은 요청 — **본인 것만.**"""
    uid = _actor(p)
    return {"status": "success",
            "data": app_delivery.inbox(uid, include_responded=not only_pending)}


@router.get("/api/v1/app-deliveries/outbox")
async def outbox(p: Principal = Depends(current_principal)):
    """보낸 요청 — 본인이 보낸 것만."""
    return {"status": "success", "data": app_delivery.outbox(_actor(p))}


@router.get("/api/v1/app-deliveries/{delivery_id}")
async def get_delivery(delivery_id: str, p: Principal = Depends(current_principal)):
    """상세. **당사자가 아니면 404** — URL 을 직접 입력해도 존재가 드러나지 않는다."""
    try:
        return {"status": "success", "data": app_delivery.get(delivery_id, _actor(p))}
    except NotFoundOrHidden as e:
        _hidden(e)


@router.post("/api/v1/app-deliveries/{delivery_id}/accept")
async def accept_delivery(delivery_id: str, req: RespondBody = RespondBody(),
                          p: Principal = Depends(current_principal)):
    """수락 → 내 앱 주머니에 등록.

    ⚠️ **수락은 데이터 접근 범위를 넓히지 않는다.** 응답의 `scope_note` 가 그것을 말한다 —
      화면이 이 문구를 보여주지 않으면 사용자는 앱을 받으면 자료도 보인다고 믿는다.
    ★ 재호출은 같은 결과를 주고 주머니를 중복 생성하지 않는다."""
    uid = _actor(p)
    try:
        return {"status": "success",
                "data": app_delivery.accept(delivery_id, uid, req.display_name)}
    except NotFoundOrHidden as e:
        _hidden(e)
    except AppDeliveryError as e:
        _bad(e)


@router.post("/api/v1/app-deliveries/{delivery_id}/reject")
async def reject_delivery(delivery_id: str, req: RespondBody = RespondBody(),
                          p: Principal = Depends(current_principal)):
    try:
        return {"status": "success",
                "data": app_delivery.reject(delivery_id, _actor(p), req.note)}
    except NotFoundOrHidden as e:
        _hidden(e)
    except AppDeliveryError as e:
        _bad(e)


@router.post("/api/v1/app-deliveries/{delivery_id}/revoke")
async def revoke_delivery(delivery_id: str, req: RevokeBody = RevokeBody(),
                          p: Principal = Depends(current_principal)):
    """보낸 사람이 회수한다.

    ★ 이미 수락된 앱은 조용히 사라지지 않는다 — 주머니가 `REVOKED` 로 표시되고 이유가 남는다.
      말없이 없어지면 수신자는 이유를 알 수 없다."""
    try:
        return {"status": "success",
                "data": app_delivery.revoke(delivery_id, _actor(p), req.reason)}
    except NotFoundOrHidden as e:
        _hidden(e)
    except AppDeliveryError as e:
        _bad(e)


@router.post("/api/v1/app-deliveries/{delivery_id}/reassign-request")
async def reassign_request(delivery_id: str, req: RespondBody = RespondBody(),
                           p: Principal = Depends(current_principal)):
    """"담당자가 아니다"를 알리는 경로(§CL-BE-02 목록).

    ⚠️ 여기서 시스템이 **다른 사람에게 자동 재배정하지 않는다.** 누가 담당인지는 조직이 정하는
      것이고, 시스템이 추측해 넘기면 아무도 그 배정을 근거로 설명할 수 없다. 지금은 거절 사유를
      `reassign_requested` 로 남기고 보낸 사람에게 되돌린다."""
    uid = _actor(p)
    note = (req.note or "").strip()
    if not note:
        raise HTTPException(
            status_code=400,
            detail=("재배정 요청에는 사유가 필요합니다 — 누가 담당인지에 대한 정보가 없으면 "
                    "보낸 사람이 다시 판단할 수 없습니다."))
    try:
        data = app_delivery.reject(delivery_id, uid, f"[재배정 요청] {note}")
    except NotFoundOrHidden as e:
        _hidden(e)
    except AppDeliveryError as e:
        _bad(e)
    data["reassign_requested"] = True
    data["note"] = ("재배정을 요청했습니다. 시스템이 자동으로 다른 담당자를 지정하지 않습니다 — "
                    "보낸 사람이 새 수신자를 지정해 다시 전달해야 합니다.")
    return {"status": "success", "data": data}


@router.get("/api/v1/me/apps")
async def my_apps(include_revoked: bool = False, p: Principal = Depends(current_principal)):
    """내 앱 주머니."""
    return {"status": "success",
            "data": app_delivery.my_apps(_actor(p), include_revoked=include_revoked)}


@router.patch("/api/v1/me/apps/{pocket_id}")
async def patch_my_app(pocket_id: str, req: PocketPatch,
                       p: Principal = Depends(current_principal)):
    """표시 이름·고정·열람시각 갱신. **남의 주머니는 404.**"""
    try:
        return {"status": "success",
                "data": app_delivery.update_pocket(
                    pocket_id, _actor(p), display_name=req.display_name,
                    pinned=req.pinned, mark_opened=req.mark_opened)}
    except NotFoundOrHidden as e:
        _hidden(e)
    except AppDeliveryError as e:
        _bad(e)
