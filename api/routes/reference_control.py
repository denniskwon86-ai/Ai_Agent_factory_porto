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

from api.deps import (
    Principal,
    assert_can_manage_standard,
    assert_identified,
    current_principal,
    viewer_may_drill_down,
    viewer_scope_nodes,
    viewer_visible_scopes,
    visibility_block_reason,
)
from core.reference_registry import (REFERENCE_ROOT, REGISTRY_PATH, approve_asset,
                                     build_registry, index_approved, indexable, load_registry,
                                     registry_summary, reject_asset, visible_assets)


router = APIRouter(prefix="/api/v1/reference")

#: 사용자에게 보일 자료 이름. 조사(을/를)는 `deps.eul` 이 맞춘다.
WHAT = "참조 데이터"



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


class IndexRequest(BaseModel):
    dry_run: bool = True                       # ★ 색인은 되돌릴 수 없다 — 예행이 기본
    asset_ids: Optional[list[str]] = None       # 비우면 색인 가능한 전부
    force: bool = False                        # 내용이 같아도 다시 넣는다(임베딩 재생성)


@router.get("/summary")
async def get_summary(
        p: Principal = Depends(current_principal)):
    """등록 현황 + **색인 가능 건수.**

    등록 건수만 보여주면 "68건이 등록됐는데 지식팩이 왜 비어 있나"를 아무도 설명할 수 없다."""
    assert_identified(p, WHAT)
    return {"status": "success", "data": await asyncio.to_thread(registry_summary)}


@router.get("/indexable")
async def list_indexable(p: Principal = Depends(current_principal)):
    """지금 색인할 수 있는 자산과, 나머지가 **왜** 안 되는지.

    ⚠️ 이 응답은 **문서 파일명을 그대로 담는다** — 파일명 자체가 정보다(예: 특정 고객사·공정명).
      집계만 담는 `/summary` 와 달리 목록 통제를 적용한다."""
    reason = visibility_block_reason(p)
    if reason:
        return {"status": "success", "data": [], "blocked_reason": reason}
    return {"status": "success", "data": await asyncio.to_thread(indexable)}


@router.get("/assets")
async def list_assets(pack_id: str = "", approval_status: str = "",
                      scope_node_id: str = "",
                      p: Principal = Depends(current_principal)):
    """자산 목록. `scope_node_id` 를 주면 **조직 범위 + 등급**이 적용된다.

    ★ 등급 판정은 주체의 권한에서 파생한다 — 등급이 낮으면 제목만 보이고 내용은 가려진다
      (2026-07-30 결정).

    ★★ [2026-07-31] 범위를 주지 않으면 필터하지 않던 계약을 **강제가 켜진 동안에는 닫는다.**
      "호출자가 범위를 주면 통제한다"는 것은 곧 **주지 않으면 통제가 없다**는 뜻이었고,
      프론트는 실제로 주지 않고 있었다(실측: 익명이 전 자산을 조회할 수 있었다).
      강제가 꺼진 상태에서는 종전 그대로 둔다 — ECM 미도입 흐름의 하위호환 계약."""
    reason = visibility_block_reason(p)
    if reason:
        return {"status": "success", "data": [], "blocked_reason": reason}
    from core.enterprise_context.classification import clearance_of_scope
    # ★ `visible_assets` 는 상속을 스스로 펼친다 — 그래서 **펼치지 않은** 소속 노드를 준다.
    #   펼친 집합을 다시 펼치면 조상의 자손, 즉 형제 사업부 자료가 들어온다.
    nodes = viewer_scope_nodes(p)
    drill = viewer_may_drill_down(p)
    if scope_node_id:
        # 호출자가 특정 조직을 지정했다 — 단, 자기 범위 밖을 지정해 넘겨다볼 수는 없다.
        allowed = viewer_visible_scopes(p)
        if allowed is not None and scope_node_id not in allowed:
            return {"status": "success", "data": [],
                    "blocked_reason": (f"'{scope_node_id}' 는 소속 조직 범위가 아닙니다 — "
                                       f"다른 조직의 자료를 지정해 조회할 수 없습니다.")}
        items = await asyncio.to_thread(visible_assets, scope_node_id,
                                        clearance_of_scope(p.scope), REGISTRY_PATH, drill)
    elif nodes is not None:
        # 범위를 주지 않았으면 **요청자의 조직 범위**로 필터한다(종전에는 전부 반환했다).
        clearance = clearance_of_scope(p.scope)
        seen, items = set(), []
        for n in sorted(nodes):
            for a in await asyncio.to_thread(visible_assets, n, clearance,
                                             REGISTRY_PATH, drill):
                if a.get("asset_id") not in seen:
                    seen.add(a.get("asset_id"))
                    items.append(a)
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


@router.post("/index")
async def index_assets(req: IndexRequest, p: Principal = Depends(current_principal)):
    """승인된 자산을 **실제로 지식팩에 색인한다.**

    ⚠️ 색인은 되돌릴 수 없다 — 프롬프트에 실려 나간 산출물은 지워도 돌아오지 않는다. 그래서
      `dry_run=true`(기본)로 무엇이 들어갈지 먼저 보고, 조건(소유·승인·추출 가능)을 통과한
      것만 넣는다. 청크에는 `owner_org_id`·`classification` 이 함께 심겨 검색에서 조직 범위로
      걸러낼 수 있다."""
    assert_can_manage_standard(p)
    _actor(p)
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(index_approved, REFERENCE_ROOT, REGISTRY_PATH,
                                                req.dry_run, None, req.asset_ids, req.force)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scan")
async def scan_reference_documents(
        p: Principal = Depends(current_principal)):
    """원본 폴더의 신규·변경 문서를 등록부에 반영한다. 색인·LLM 호출은 수행하지 않는다."""
    assert_identified(p, WHAT)
    registry = await asyncio.to_thread(build_registry)
    return {"status": "success", "data": registry.get("summary", {})}
