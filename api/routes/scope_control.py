"""[M2 §2.1/§2.2] 범위 계약 REST API. prefix `/api/v1/scope`.

소유 조직 지정 · 조직 간 공유 · 전사 공용 신청/승인 · 한시 예외 이행.

## 권한 배치의 이유

  · 소유 지정·조직 공유 — 데이터 표준 관리자(`assert_can_manage_standard`)
  · **전사 공용 승인 — 전사 권한자(`assert_enterprise`)**. 신청과 승인의 권한을 같은 등급으로
    두면 자기 승인 금지를 계정 하나로 우회한다(다른 사람 계정만 있으면 되니까).
  · 한시 예외 목록 조회는 표준 관리자면 볼 수 있다 — 정리해야 할 일감을 감출 이유가 없다.

⚠️ `_actor()` 로 **식별을 강제**한다. 행위자 없는 권한 변경은 "누가 열었나"에 답할 수 없고,
  그러면 되돌릴 근거도 없다(§3.2 — 익명은 `""` 가 아니라 거부다).
"""
import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import (Principal, assert_can_manage_standard, assert_enterprise,
                      current_principal)
from core.scope_contract import ScopeContractError, scope_contract

router = APIRouter(prefix="/api/v1/scope")


def _actor(p: Principal, what: str) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=(f"{what}에는 사용자 식별이 필요합니다. X-User-Id 헤더를 포함하거나 "
                    f"ORG_ENFORCE 를 켜십시오 — 행위자 없는 권한 변경은 '누가 열었나'에 "
                    f"답할 수 없고, 그러면 되돌릴 근거도 없습니다."))
    return uid


class OwnerRequest(BaseModel):
    owner_organization_id: str
    reason: Optional[str] = ""


class ShareRequest(BaseModel):
    organizations: List[str]
    reason: Optional[str] = ""


class ReasonRequest(BaseModel):
    reason: Optional[str] = ""


class RejectRequest(BaseModel):
    reason: str          # 반려는 사유가 필수다 — 없으면 같은 신청이 반복된다


class AdoptRequest(BaseModel):
    owner_organization_id: str
    reason: Optional[str] = ""


async def _run(fn, *args):
    try:
        return await asyncio.to_thread(fn, *args)
    except ScopeContractError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/contract/{resource_type}/{resource_id}")
async def get_contract(resource_type: str, resource_id: str,
                       p: Principal = Depends(current_principal)):
    """범위 계약 + **지금 어떻게 보이는지에 대한 설명**(`visibility`).

    ★ 값만 주면 "왜 안 보이는지"를 사람이 조립해야 하고, 그러면 `ORG_SHARED` 인데 대상이
      비어 있는 상태 같은 것을 아무도 눈치채지 못한다."""
    return {"status": "success",
            "data": await _run(scope_contract.contract, resource_type, resource_id)}


@router.post("/owner/{resource_type}/{resource_id}")
async def set_owner(resource_type: str, resource_id: str, req: OwnerRequest,
                    p: Principal = Depends(current_principal)):
    """책임 조직을 지정한다 — 모든 공유의 전제다."""
    assert_can_manage_standard(p)
    return {"status": "success",
            "data": await _run(scope_contract.set_owner, resource_type, resource_id,
                               req.owner_organization_id, _actor(p, "소유 조직 지정"),
                               req.reason or "")}


@router.post("/share/{resource_type}/{resource_id}")
async def share_with(resource_type: str, resource_id: str, req: ShareRequest,
                     p: Principal = Depends(current_principal)):
    """지정한 조직들에 공유한다(`ORG_SHARED`). 대상 목록은 필수다."""
    assert_can_manage_standard(p)
    return {"status": "success",
            "data": await _run(scope_contract.share_with, resource_type, resource_id,
                               req.organizations, _actor(p, "조직 공유"), req.reason or "")}


@router.delete("/share/{resource_type}/{resource_id}")
async def revoke_sharing(resource_type: str, resource_id: str,
                         p: Principal = Depends(current_principal)):
    """공유를 회수해 `ORG_PRIVATE` 로 되돌린다(승인 이력도 함께 비운다)."""
    assert_can_manage_standard(p)
    return {"status": "success",
            "data": await _run(scope_contract.revoke_sharing, resource_type, resource_id,
                               _actor(p, "공유 회수"), "")}


@router.post("/enterprise/request/{resource_type}/{resource_id}")
async def request_enterprise(resource_type: str, resource_id: str, req: ReasonRequest,
                             p: Principal = Depends(current_principal)):
    """전사 공용 전환을 신청한다. ⚠️ **신청만으로는 보이지 않는다.**"""
    assert_can_manage_standard(p)
    return {"status": "success",
            "data": await _run(scope_contract.request_enterprise_shared, resource_type,
                               resource_id, _actor(p, "전사 공용 신청"), req.reason or "")}


@router.post("/enterprise/approve/{resource_type}/{resource_id}")
async def approve_enterprise(resource_type: str, resource_id: str, req: ReasonRequest,
                             p: Principal = Depends(current_principal)):
    """전사 공용을 승인한다 — 이 순간부터 전 조직에서 보인다.

    ⚠️ 신청자와 승인자가 같으면 400 으로 거부한다. 자기 승인은 승인이 아니다."""
    assert_enterprise(p)
    return {"status": "success",
            "data": await _run(scope_contract.approve_enterprise_shared, resource_type,
                               resource_id, _actor(p, "전사 공용 승인"), req.reason or "")}


@router.post("/enterprise/reject/{resource_type}/{resource_id}")
async def reject_enterprise(resource_type: str, resource_id: str, req: RejectRequest,
                            p: Principal = Depends(current_principal)):
    """전사 공용 신청을 반려한다(사유 필수 · `ORG_PRIVATE` 로 되돌림)."""
    assert_enterprise(p)
    return {"status": "success",
            "data": await _run(scope_contract.reject_enterprise_shared, resource_type,
                               resource_id, _actor(p, "전사 공용 반려"), req.reason)}


@router.get("/legacy/pending")
async def legacy_pending(resource_type: str = "",
                         p: Principal = Depends(current_principal)):
    """한시 예외로 버티는 자원 목록 — **만료 전에 정리해야 하는 일감**이다.

    만료일을 아는 것과 무엇을 정리해야 하는지 아는 것은 다르고, 사람은 후자로 움직인다."""
    assert_can_manage_standard(p)
    return {"status": "success",
            "data": await _run(scope_contract.legacy_pending, resource_type)}


@router.post("/legacy/adopt/{resource_type}/{resource_id}")
async def adopt_legacy(resource_type: str, resource_id: str, req: AdoptRequest,
                       p: Principal = Depends(current_principal)):
    """한시 예외를 정상 상태로 이행한다.

    ⚠️ 이 조치는 가시성을 **좁힌다**(전 조직 → 소유 조직 + 하위). 응답의 `note` 를 그대로
      보여줘야 "정리했더니 안 보인다"는 놀람이 없다."""
    assert_can_manage_standard(p)
    return {"status": "success",
            "data": await _run(scope_contract.adopt_legacy, resource_type, resource_id,
                               req.owner_organization_id, _actor(p, "한시 예외 이행"),
                               req.reason or "")}
