"""M2 크로스워크 REST API. prefix /api/v1/crosswalk.

core/crosswalk.py 의 시스템·스키마·제안·승인 로직을 노출한다. propose(use_llm=True)만 LLM(Flash,
옵트인) 사용, 나머지는 LLM 0콜. 매핑은 승인(approve)해야만 유효(confirmed=1)하다.
응답 봉투는 리포 관례 {"status": "success", "data": ...}.
"""
import io
import csv
import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List

from core.crosswalk import crosswalk, CrosswalkError

router = APIRouter(prefix="/api/v1/crosswalk")


def _err(e: CrosswalkError):
    msg = str(e)
    if "이미 존재" in msg or "이미 처리" in msg or "활성화" in msg:
        raise HTTPException(status_code=409, detail=msg)
    if "존재하지 않는" in msg or "먼저" in msg:
        raise HTTPException(status_code=404, detail=msg)
    raise HTTPException(status_code=400, detail=msg)


# ── 시스템 ────────────────────────────────────────────────────────────
class SystemRequest(BaseModel):
    system_id: str
    name: str = ""
    mcp_endpoint: Optional[str] = ""
    scope: Optional[str] = "read"


class SystemUpdateRequest(BaseModel):
    name: Optional[str] = None
    mcp_endpoint: Optional[str] = None
    scope: Optional[str] = None
    status: Optional[str] = None


@router.get("/systems")
async def list_systems():
    return {"status": "success", "data": await asyncio.to_thread(crosswalk.list_systems)}


@router.post("/systems")
async def create_system(req: SystemRequest):
    try:
        data = await asyncio.to_thread(crosswalk.create_system, req.system_id, req.name,
                                       req.mcp_endpoint or "", "", req.scope or "read")
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.put("/systems/{system_id}")
async def update_system(system_id: str, req: SystemUpdateRequest):
    try:
        data = await asyncio.to_thread(crosswalk.update_system, system_id, req.name,
                                       req.mcp_endpoint, req.scope, req.status)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.delete("/systems/{system_id}")
async def delete_system(system_id: str):
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
async def get_schema(system_id: str):
    return {"status": "success", "data": await asyncio.to_thread(crosswalk.get_schema, system_id)}


@router.post("/systems/{system_id}/schema/field")
async def add_field(system_id: str, req: FieldRequest):
    try:
        data = await asyncio.to_thread(crosswalk.add_schema_field, system_id, req.entity, req.field,
                                       req.field_type or "", req.is_key, req.mapped_type or "",
                                       req.mapped_attr or "")
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.post("/systems/{system_id}/schema/import")
async def import_schema(system_id: str, file: UploadFile = File(...)):
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
async def set_mapping(system_id: str, req: FieldMappingRequest):
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
async def propose(system_id: str, use_llm: bool = False):
    """매핑 초안 생성. use_llm=True 는 Flash(옵트인, 쿼터 소비)."""
    try:
        data = await crosswalk.propose(system_id, use_llm=use_llm)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.get("/systems/{system_id}/proposals")
async def list_proposals(system_id: str, status: Optional[str] = None):
    data = await asyncio.to_thread(crosswalk.list_proposals, system_id, status)
    return {"status": "success", "data": data}


@router.post("/proposals/{proposal_id}/approve")
async def approve(proposal_id: int, req: ApproveRequest = None):
    try:
        ext = req.external_key if req else None
        data = await asyncio.to_thread(crosswalk.approve_proposal, proposal_id, ext)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.post("/proposals/{proposal_id}/reject")
async def reject(proposal_id: int):
    try:
        data = await asyncio.to_thread(crosswalk.reject_proposal, proposal_id)
        return {"status": "success", "data": data}
    except CrosswalkError as e:
        _err(e)


@router.get("/systems/{system_id}/mappings")
async def list_mappings(system_id: str):
    return {"status": "success", "data": await asyncio.to_thread(crosswalk.list_mappings, system_id)}
