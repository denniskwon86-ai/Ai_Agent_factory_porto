"""원본 참고문서 등록부 조회·승인·재스캔 API.

원문을 자동으로 전사 RAG에 넣지 않는다. 등록 상태를 투명하게 만들고, **승인된 범위만** 실제
지식팩에 색인하도록 하는 안전한 진입점이다.

## [2026-07-30] 승인 문을 열었다

이 파일은 "M2 권한 모델이 완성된 뒤 승인된 범위만 색인한다"고 적어 두고 그 문을 만들지
않았다. 그 결과 실측에서 자산 68건이 전부 `PENDING_REVIEW` · 색인 0 이었다 — **아무것도
지식팩에 들어갈 수 없는 상태**였다. M2 범위 계약이 완성됐으므로 문을 연다.

⚠️ 색인은 되돌릴 수 없다(프롬프트에 실려 나간 산출물은 되돌아오지 않는다). 그래서
  `/indexable` 은 **소유 조직 + 승인 + 추출 가능**을 모두 요구하고, 빠진 이유를 건수로 준다.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, assert_can_manage_standard, current_principal
from core.reference_registry import (approve_asset, build_registry, indexable, load_registry,
                                     registry_summary, reject_asset, visible_assets)


router = APIRouter(prefix="/api/v1/reference")


def _actor(p: Principal) -> str:
    uid = (p.user_id or "").strip()
    if not uid:
        raise HTTPException(
            status_code=401,
            detail=("문서 승인에는 사용자 식별이 필요합니다. X-User-Id 헤더를 포함하거나 "
                    "ORG_ENFORCE 를 켜십시오 — 누가 이 문서를 사내 지식으로 승인했는지 없으면 "
                    "감사에서 근거가 되지 못합니다."))
    return uid


class ApproveRequest(BaseModel):
    note: Optional[str] = ""


class RejectRequest(BaseModel):
    reason: str            # 사유 필수 — 없으면 같은 문서가 계속 다시 올라온다


@router.get("/summary")
async def get_summary():
    """등록 현황 + **색인 가능 건수.**

    등록 건수만 보여주면 "68건이 등록됐는데 지식팩이 왜 비어 있나"를 아무도 설명할 수 없다."""
    return {"status": "success", "data": await asyncio.to_thread(registry_summary)}


@router.get("/indexable")
async def list_indexable():
    """지금 색인할 수 있는 자산과, 나머지가 **왜** 안 되는지."""
    return {"status": "success", "data": await asyncio.to_thread(indexable)}


@router.get("/assets")
async def list_assets(pack_id: str = "", approval_status: str = "",
                      scope_node_id: str = "",
                      p: Principal = Depends(current_principal)):
    """자산 목록. `scope_node_id` 를 주면 **조직 범위 + 등급**이 적용된다.

    ★ 등급 판정은 주체의 권한에서 파생한다 — 등급이 낮으면 제목만 보이고 내용은 가려진다
      (2026-07-30 결정). 범위를 주지 않으면 필터하지 않는다(ECM 미도입 흐름 보호)."""
    if scope_node_id:
        from core.enterprise_context.classification import clearance_of_scope
        items = await asyncio.to_thread(visible_assets, scope_node_id,
                                        clearance_of_scope(p.scope))
    else:
        items = (await asyncio.to_thread(load_registry)).get("assets", [])
    if pack_id:
        items = [a for a in items if a.get("pack_id") == pack_id]
    if approval_status:
        items = [a for a in items if a.get("approval_status") == approval_status]
    return {"status": "success", "data": items}


@router.post("/assets/{asset_id}/approve")
async def approve(asset_id: str, req: ApproveRequest,
                  p: Principal = Depends(current_principal)):
    """이 문서를 지식팩 색인 대상으로 승인한다(데이터 표준 관리자)."""
    assert_can_manage_standard(p)
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(approve_asset, asset_id, _actor(p),
                                                req.note or "")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/assets/{asset_id}/reject")
async def reject(asset_id: str, req: RejectRequest,
                 p: Principal = Depends(current_principal)):
    """색인 대상에서 제외한다(사유 필수)."""
    assert_can_manage_standard(p)
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(reject_asset, asset_id, _actor(p),
                                                req.reason)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scan")
async def scan_reference_documents():
    """원본 폴더의 신규·변경 문서를 등록부에 반영한다. 색인·LLM 호출은 수행하지 않는다."""
    registry = await asyncio.to_thread(build_registry)
    return {"status": "success", "data": registry.get("summary", {})}
