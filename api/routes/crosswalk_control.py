"""M2 크로스워크 REST API. prefix /api/v1/crosswalk.

core/crosswalk.py 의 시스템·스키마·제안·승인 로직을 노출한다. propose(use_llm=True)만 LLM(Flash,
옵트인) 사용, 나머지는 LLM 0콜. 매핑은 승인(approve)해야만 유효(confirmed=1)하다.
응답 봉투는 리포 관례 {"status": "success", "data": ...}.
"""
import io
import csv
import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List

# [§6-2] 목록에 등급 가림을 적용하려면 주체가 필요하다(등급은 권한에서 파생한다).
from api.deps import (Principal, assert_governance_readable, current_principal,
                      visibility_block_reason)
from core.crosswalk import crosswalk, CrosswalkError

router = APIRouter(prefix="/api/v1/crosswalk")


def _err(e: CrosswalkError):
    msg = str(e)
    if "이미 존재" in msg or "이미 처리" in msg or "활성화" in msg:
        raise HTTPException(status_code=409, detail=msg)
    if "존재하지 않는" in msg or "먼저" in msg:
        raise HTTPException(status_code=404, detail=msg)
    raise HTTPException(status_code=400, detail=msg)


# ── [ECM E2] 조직 범위 게이트 ─────────────────────────────────────────
# ⚠️ 자식 자원(스키마·매핑·제안)에는 범위 키를 **복제하지 않았다** — 소유 조직은 시스템 하나에만
#   있다. 그 대가로 자식 경로의 접근 판정은 전부 이 게이트 하나를 지나야 한다. 한 경로라도
#   빠뜨리면 그 경로만 열려 있는 구멍이 된다(그래서 라우트마다 같은 한 줄을 반복한다).
async def _gate(system_id: str, scope_node_id: str = "", tenant_id: str = "",
                entity_mode: str = "REAL"):
    if not (scope_node_id or tenant_id):
        return                      # 범위 미지정 호출 — 종전 동작(ECM 미도입 흐름 보존)
    try:
        await asyncio.to_thread(crosswalk.require_system_visible, system_id,
                                scope_node_id, tenant_id, entity_mode)
    except CrosswalkError as e:
        # 존재하지 않는 것과 **같은 응답**이다 — 다른 조직 시스템의 존재를 알려주지 않는다.
        raise HTTPException(status_code=404, detail=str(e))


# ── 시스템 ────────────────────────────────────────────────────────────
class SystemRequest(BaseModel):
    system_id: str
    name: str = ""
    mcp_endpoint: Optional[str] = ""
    scope: Optional[str] = "read"
    # 이 시스템을 소유·운영하는 조직(비우면 전사 공용 — coverage 로 관측된다)
    tenant_id: Optional[str] = "tenant_default"
    enterprise_scope_id: Optional[str] = ""
    entity_mode: Optional[str] = "REAL"


class SystemUpdateRequest(BaseModel):
    name: Optional[str] = None
    mcp_endpoint: Optional[str] = None
    scope: Optional[str] = None
    status: Optional[str] = None


@router.get("/systems")
async def list_systems(scope_node_id: str = "", tenant_id: str = "", entity_mode: str = "REAL",
                       p: Principal = Depends(current_principal)):
    """범위를 주면 그 조직이 볼 수 있는 시스템만. 미지정이면 전량(종전 동작).

    ★ [§6-2] 등급은 주체 권한에서 파생한다 — 낮으면 제목만 보이고 내용은 가려진다."""
    # ⚠️ 이 라우트는 이미 **등급 기반 가림**이 있다(§6-2 사용자 결정) — 낮은 등급에는
    #   제목만 주고 내용을 가린다. 그 설계를 403 으로 덮지 않는다. 다만 익명·미등록·폐지
    #   계정에는 아무것도 주지 않는다(관문 A). 목록형이므로 0건 + 이유로 답한다.
    _reason = visibility_block_reason(p)
    if _reason:
        return {"status": "success", "data": [], "blocked_reason": _reason}
    from core.enterprise_context.classification import clearance_of_scope
    # [경영진 드릴다운] 하위 조직까지 볼 수 있는 주체인가 — 이것도 권한에서 파생한다.
    from core.enterprise_context.scoping import may_drill_down
    return {"status": "success",
            "data": await asyncio.to_thread(crosswalk.list_systems, scope_node_id,
                                            tenant_id, entity_mode,
                                            clearance_of_scope(p.scope),
                                            may_drill_down(p.scope))}


@router.get("/systems/coverage")
async def systems_coverage(p: Principal = Depends(current_principal)):
    """범위 미지정(= 모든 조직에 노출) 시스템 관측 (D-014).

    ⚠️ 경로 변수 라우트(`/systems/{system_id}/...`)보다 **위에** 둔다 — FastAPI 는 정의 순서로
      매칭하므로 아래에 두면 'coverage' 가 system_id 로 잡아먹힌다(실측 사고 이력)."""
    assert_governance_readable(p)
    return {"status": "success", "data": await asyncio.to_thread(crosswalk.systems_coverage)}


@router.post("/systems")
async def create_system(req: SystemRequest):
    try:
        data = await asyncio.to_thread(crosswalk.create_system, req.system_id, req.name,
                                       req.mcp_endpoint or "", "", req.scope or "read",
                                       req.tenant_id or "tenant_default",
                                       req.enterprise_scope_id or "", req.entity_mode or "REAL")
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.put("/systems/{system_id}")
async def update_system(system_id: str, req: SystemUpdateRequest,
                        scope_node_id: str = "", tenant_id: str = "", entity_mode: str = "REAL"):
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    try:
        data = await asyncio.to_thread(crosswalk.update_system, system_id, req.name,
                                       req.mcp_endpoint, req.scope, req.status)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.delete("/systems/{system_id}")
async def delete_system(system_id: str, scope_node_id: str = "", tenant_id: str = "",
                        entity_mode: str = "REAL"):
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    await asyncio.to_thread(crosswalk.delete_system, system_id)
    return {"status": "success"}


# ── 스키마 ────────────────────────────────────────────────────────────
class FieldRequest(BaseModel):
    entity: str
    field: str
    field_type: Optional[str] = ""
    is_key: bool = False
    mapped_type: Optional[str] = ""
    mapped_attr: Optional[str] = ""


class FieldMappingRequest(BaseModel):
    entity: str
    field: str
    mapped_type: Optional[str] = ""
    mapped_attr: Optional[str] = ""


@router.get("/systems/{system_id}/schema")
async def get_schema(system_id: str, scope_node_id: str = "", tenant_id: str = "",
                     entity_mode: str = "REAL",
                     p: Principal = Depends(current_principal)):
    assert_governance_readable(p)
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    return {"status": "success", "data": await asyncio.to_thread(crosswalk.get_schema, system_id)}


@router.post("/systems/{system_id}/schema/field")
async def add_field(system_id: str, req: FieldRequest, scope_node_id: str = "",
                    tenant_id: str = "", entity_mode: str = "REAL"):
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    try:
        data = await asyncio.to_thread(crosswalk.add_schema_field, system_id, req.entity, req.field,
                                       req.field_type or "", req.is_key, req.mapped_type or "",
                                       req.mapped_attr or "")
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.post("/systems/{system_id}/schema/import")
async def import_schema(system_id: str, file: UploadFile = File(...), scope_node_id: str = "",
                        tenant_id: str = "", entity_mode: str = "REAL"):
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise HTTPException(status_code=400, detail="빈 CSV 이거나 헤더만 있습니다.")
    try:
        report = await asyncio.to_thread(crosswalk.import_schema_rows, system_id, rows)
        return {"status": "success", "data": report}
    except CrosswalkError as e:
        _err(e)


@router.put("/systems/{system_id}/schema/mapping")
async def set_mapping(system_id: str, req: FieldMappingRequest, scope_node_id: str = "",
                      tenant_id: str = "", entity_mode: str = "REAL"):
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    try:
        data = await asyncio.to_thread(crosswalk.set_field_mapping, system_id, req.entity, req.field,
                                       req.mapped_type or "", req.mapped_attr or "")
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


# ── 제안 / 승인 ───────────────────────────────────────────────────────
class ApproveRequest(BaseModel):
    external_key: Optional[str] = None


@router.post("/systems/{system_id}/propose")
async def propose(system_id: str, use_llm: bool = False, scope_node_id: str = "",
                  tenant_id: str = "", entity_mode: str = "REAL"):
    """매핑 초안 생성. use_llm=True 는 Flash(옵트인, 쿼터 소비)."""
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    try:
        data = await crosswalk.propose(system_id, use_llm=use_llm)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.get("/systems/{system_id}/proposals")
async def list_proposals(system_id: str, status: Optional[str] = None, scope_node_id: str = "",
                         tenant_id: str = "", entity_mode: str = "REAL",
                         p: Principal = Depends(current_principal)):
    assert_governance_readable(p)
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    data = await asyncio.to_thread(crosswalk.list_proposals, system_id, status)
    return {"status": "success", "data": data}


async def _gate_proposal(proposal_id: int, scope_node_id: str, tenant_id: str, entity_mode: str):
    """제안은 시스템에 종속된다 — 부모 시스템이 안 보이면 승인·기각도 안 된다."""
    if not (scope_node_id or tenant_id):
        return
    sid = await asyncio.to_thread(crosswalk.system_of_proposal, proposal_id)
    if not sid:
        raise HTTPException(status_code=404, detail=f"존재하지 않는 제안입니다: {proposal_id}")
    await _gate(sid, scope_node_id, tenant_id, entity_mode)


@router.post("/proposals/{proposal_id}/approve")
async def approve(proposal_id: int, req: ApproveRequest = None, scope_node_id: str = "",
                  tenant_id: str = "", entity_mode: str = "REAL"):
    await _gate_proposal(proposal_id, scope_node_id, tenant_id, entity_mode)
    try:
        ext = req.external_key if req else None
        data = await asyncio.to_thread(crosswalk.approve_proposal, proposal_id, ext)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.post("/proposals/{proposal_id}/reject")
async def reject(proposal_id: int, scope_node_id: str = "", tenant_id: str = "",
                 entity_mode: str = "REAL"):
    await _gate_proposal(proposal_id, scope_node_id, tenant_id, entity_mode)
    try:
        data = await asyncio.to_thread(crosswalk.reject_proposal, proposal_id)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.get("/systems/{system_id}/mappings")
async def list_mappings(system_id: str, scope_node_id: str = "", tenant_id: str = "",
                       entity_mode: str = "REAL",
                        p: Principal = Depends(current_principal)):
    assert_governance_readable(p)
    await _gate(system_id, scope_node_id, tenant_id, entity_mode)
    return {"status": "success", "data": await asyncio.to_thread(crosswalk.list_mappings, system_id)}
