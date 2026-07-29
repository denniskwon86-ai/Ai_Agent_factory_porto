"""[§9 / §14 M3] 부서 워크스페이스 REST API. prefix `/api/v1/workspace`.

공유(`/shares`) · 복제(`/forks`) · 승격 게이트(`/promotions`).

⚠️ **공유는 승격이 아니다.** 엔드포인트를 일부러 갈라 두었다 — 한 동작으로 묶으면
  "잠깐 보여주려던 것"이 전사 자산이 된다.
⚠️ **강제 승격 우회로를 만들지 않았다.** 게이트가 막으면 게이트 항목을 고쳐야 하고,
  그 변경은 기록에 남는다(Shadow Mode 의 `allow_breached` 와 다른 판단 — 여기서는
  데이터 계약 위반·PII 전사 공개라 되돌릴 수 없다).
⚠️ 라우트 순서: 고정 경로는 경로 변수보다 위에 둔다.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, assert_can_manage_standard, current_principal
from core.workspace_promotion import WorkspaceError, workspace

router = APIRouter(prefix="/api/v1/workspace")


def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("공유·승인·승격에는 사용자 식별이 필요합니다. X-User-Id 헤더를 포함하거나 "
                    "ORG_ENFORCE 를 켜십시오. 행위자 없는 승인은 '누가 데이터 공개를 결정했나'에 "
                    "답할 수 없습니다."))
    return uid


def _err(e: WorkspaceError):
    raise HTTPException(status_code=400, detail=str(e))


class ShareRequest(BaseModel):
    release_id: str
    from_scope: str
    to_scope: str
    mode: str = "read"          # read | fork
    reason: str = ""


class ForkRequest(BaseModel):
    source_release_id: str
    new_project_id: str
    owner_scope: str
    reason: str = ""


class PromotionRequest(BaseModel):
    release_id: str
    from_scope: str
    target_scope: str = "enterprise"
    project_id: str = ""        # 품질 기록 조회 키 — 릴리스 id 에서 추론하지 않는다


class OwnerApproveRequest(BaseModel):
    release_id: str
    target_scope: str = "enterprise"
    note: str = ""


class RejectRequest(BaseModel):
    release_id: str
    target_scope: str = "enterprise"
    reason: str


class PromoteRequest(BaseModel):
    release_id: str
    target_scope: str = "enterprise"


# ── 공유 ──────────────────────────────────────────────────────────────────
@router.get("/shares")
async def list_shares(release_id: str = "", to_scope: str = "",
                      include_revoked: bool = False):
    return {"status": "success",
            "data": await asyncio.to_thread(workspace.list_shares, release_id, to_scope,
                                            include_revoked)}


@router.post("/shares")
async def create_share(req: ShareRequest, p: Principal = Depends(current_principal)):
    """다른 부서에 읽기 또는 복제 권한을 연다. **승격이 아니다.**"""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(workspace.share, req.release_id, req.from_scope,
                                      req.to_scope, _actor(p), req.mode, req.reason)
    except WorkspaceError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.delete("/shares/{share_id}")
async def revoke_share(share_id: str, p: Principal = Depends(current_principal)):
    """회수는 소프트 삭제 — "누가 언제 무엇을 봤나"가 감사 대상이다."""
    assert_can_manage_standard(p)
    ok = await asyncio.to_thread(workspace.revoke_share, share_id)
    if not ok:
        raise HTTPException(status_code=404, detail="활성 공유를 찾을 수 없습니다.")
    return {"status": "success", "data": {"share_id": share_id, "revoked": True}}


@router.get("/access")
async def can_access(release_id: str, scope_node_id: str, owner_scope: str = ""):
    return {"status": "success",
            "data": await asyncio.to_thread(workspace.can_access, release_id,
                                            scope_node_id, owner_scope)}


# ── 복제 ──────────────────────────────────────────────────────────────────
@router.get("/forks")
async def list_forks(source_release_id: str = ""):
    return {"status": "success",
            "data": await asyncio.to_thread(workspace.list_forks, source_release_id)}


@router.post("/forks")
async def create_fork(req: ForkRequest, p: Principal = Depends(current_principal)):
    """릴리스를 복제한다. **계보를 함께 남긴다** — 원본이 바뀔 때 영향을 알기 위해서."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(workspace.fork, req.source_release_id,
                                      req.new_project_id, req.owner_scope, _actor(p),
                                      req.reason)
    except WorkspaceError as e:
        _err(e)
    return {"status": "success", "data": out}


# ── 승격 게이트 ───────────────────────────────────────────────────────────
@router.get("/promotions")
async def list_promotions(status: str = ""):
    return {"status": "success",
            "data": await asyncio.to_thread(workspace.list_promotions, status)}


@router.get("/promotions/gate")
async def evaluate_gate(release_id: str, target_scope: str = "enterprise",
                        project_id: str = ""):
    """§9.3 네 가지(데이터 계약·보안·품질·소유자 승인)를 **실제로 조회해** 판정한다.

    ⚠️ `unverifiable` 은 통과가 아니라 확인하지 못한 것이며 승격을 막는다."""
    return {"status": "success",
            "data": await asyncio.to_thread(workspace.evaluate_gate, release_id,
                                            target_scope, None, None, None, project_id)}


@router.post("/promotions")
async def request_promotion(req: PromotionRequest,
                            p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(workspace.request_promotion, req.release_id,
                                      req.from_scope, _actor(p), req.target_scope,
                                      req.project_id)
    except WorkspaceError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.post("/promotions/owner-approve")
async def owner_approve(req: OwnerApproveRequest,
                        p: Principal = Depends(current_principal)):
    """§9.3 「소유자 승인」 — 데이터 오너의 명시적 승인."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(workspace.owner_approve, req.release_id, _actor(p),
                                      req.target_scope, req.note)
    except WorkspaceError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.post("/promotions/reject")
async def reject_promotion(req: RejectRequest, p: Principal = Depends(current_principal)):
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(workspace.reject_promotion, req.release_id,
                                      _actor(p), req.reason, req.target_scope)
    except WorkspaceError as e:
        _err(e)
    return {"status": "success", "data": out}


@router.post("/promotions/promote")
async def promote(req: PromoteRequest, p: Principal = Depends(current_principal)):
    """전사 승격. 게이트를 통과하지 못하면 **409** 로 거절한다(강제 우회로 없음)."""
    assert_can_manage_standard(p)
    try:
        out = await asyncio.to_thread(workspace.promote, req.release_id, _actor(p),
                                      req.target_scope)
    except WorkspaceError as e:
        raise HTTPException(status_code=409 if "게이트를 통과하지" in str(e) else 400,
                            detail=str(e))
    return {"status": "success", "data": out}
