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

from api.deps import (Principal, assert_can_manage_standard, assert_identified,
                      current_principal)
from core.workspace_promotion import WorkspaceError, workspace

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "작업공간 공유·승격 기록"

# ── [2026-08-07 · 트랙 G] 무방비 라우트 봉합 ─────────────────────────────────
#
# 실측: 쓰기 7개는 전부 `assert_can_manage_standard` 를 지나는데 **읽기 5개에는 주체가
# 아예 없었다** — `/shares` · `/access` · `/forks` · `/promotions` · `/promotions/gate`.
# 익명이 알 수 있었던 것: 어느 부서가 어느 릴리스를 **누구에게 열어 줬는지**, 무엇을 복제해
# 갔는지(계보), 어떤 승격이 심사 중인지, 그리고 그 승격이 **어느 관문에서 막혔는지**.
#
# ⚠️ 「쓰기가 막혀 있으니 통제된다」로 보였다. `crosswalk_control` 과 정확히 **반대 모양**이며
#   (거기는 읽기만 막혀 있었다), 둘 다 한쪽만 훑는 점검에는 초록으로 보인다.
#
# ⬜ **남은 구멍을 완료로 세지 않는다.** 봉합은 «익명이 못 본다» 까지다. 식별된 사용자에게는
#   여전히 **범위 필터가 없어** 남의 부서 공유·승격 기록이 보인다. 그것은 행 단위 필터
#   (`viewer_scope_nodes`)를 저장소까지 내려야 하는 일이라 트랙 G 범위가 아니다 —
#   `PROGRESS.md` §G 에 남긴다.

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
                      include_revoked: bool = False,
                      p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
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
async def can_access(release_id: str, scope_node_id: str, owner_scope: str = "",
                     p: Principal = Depends(current_principal)):
    # ⚠️ 이 라우트는 «누가 무엇을 볼 수 있는가» 를 알려 준다 — 익명에게는 권한 지도 자체가
    #   정찰 자료다(어느 릴리스가 어느 범위에 열려 있는지 훑을 수 있다).
    assert_identified(p, WHAT)
    return {"status": "success",
            "data": await asyncio.to_thread(workspace.can_access, release_id,
                                            scope_node_id, owner_scope)}


# ── 복제 ──────────────────────────────────────────────────────────────────
@router.get("/forks")
async def list_forks(source_release_id: str = "",
                     p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
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
async def list_promotions(status: str = "",
                          p: Principal = Depends(current_principal)):
    assert_identified(p, WHAT)
    return {"status": "success",
            "data": await asyncio.to_thread(workspace.list_promotions, status)}


@router.get("/promotions/recommendations")
async def promotion_recommendations(target_scope: str = "enterprise",
                                    p: Principal = Depends(current_principal)):
    """[D-017 §9 P4-3] **지금 승격 신청하면 게이트를 통과할 릴리스**를 추천한다.

    ★ 그 이상을 말하지 않는다 — 「좋은 자산」·「가치 있는 자산」은 사람의 판단이고, 우리가
      가진 데이터로는 근사조차 할 수 없다.
    ★★ 판정을 여기서 다시 하지 않는다. `evaluate_gate` 의 `promotable` 을 **그대로** 쓴다 —
      다시 세면 화면과 실제 게이트가 다른 말을 하게 되고, 「승격 준비됨」이라던 것이 신청하면
      막힌다. 그때 사용자는 추천을 신뢰하지 않게 된다.
    ⚠️ `unverifiable` 을 완화하지 않는다. 게이트에서 가장 흔한 상태가 그것이므로 통과로 세면
      거의 전부가 추천된다.
    ⚠️ 자격은 「전사 정비 상태」 기준이다 — 어디가 비어 있는지는 그 자체로 보호 대상이다."""
    from api.deps import assert_governance_readable
    from core.promotion_advisor import recommend
    assert_governance_readable(p)
    data = await asyncio.to_thread(recommend, target_scope)
    return {"status": "success", "data": data}


@router.get("/promotions/gate")
async def evaluate_gate(release_id: str, target_scope: str = "enterprise",
                        project_id: str = "",
                        p: Principal = Depends(current_principal)):
    """§9.3 네 가지(데이터 계약·보안·품질·소유자 승인)를 **실제로 조회해** 판정한다.

    ⚠️ `unverifiable` 은 통과가 아니라 확인하지 못한 것이며 승격을 막는다."""
    assert_identified(p, WHAT)
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
