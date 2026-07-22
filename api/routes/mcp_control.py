"""M3 MCP 데이터 브로커 REST API. prefix /api/v1/mcp.

core/mcp_broker.py 의 온디맨드 조회(읽기 전용)·캐시 무효화·헬스체크를 노출한다.
v1 은 목 어댑터 기반(실 MCP 커넥터는 set_adapter 로 교체). 응답 봉투는 리포 관례.
"""
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from core.mcp_broker import mcp_broker, MCPError

router = APIRouter(prefix="/api/v1/mcp")


class ResolveRequest(BaseModel):
    master_code: str
    system_id: str
    ttl: Optional[int] = None
    force: bool = False


class ResolveBatchRequest(BaseModel):
    master_codes: List[str]
    system_id: str
    ttl: Optional[int] = None


class InvalidateRequest(BaseModel):
    system_id: str
    external_key: Optional[str] = None


@router.post("/resolve")
async def resolve(req: ResolveRequest):
    try:
        data = await asyncio.to_thread(mcp_broker.resolve, req.master_code, req.system_id, req.ttl, req.force)
        return {"status": "success", "data": data}
    except MCPError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/resolve-batch")
async def resolve_batch(req: ResolveBatchRequest):
    data = await asyncio.to_thread(mcp_broker.resolve_batch, req.master_codes, req.system_id, req.ttl)
    return {"status": "success", "data": data}


@router.post("/invalidate")
async def invalidate(req: InvalidateRequest):
    n = await asyncio.to_thread(mcp_broker.invalidate, req.system_id, req.external_key)
    return {"status": "success", "data": {"invalidated": n}}


@router.get("/systems/{system_id}/health")
async def health(system_id: str):
    try:
        return {"status": "success", "data": await asyncio.to_thread(mcp_broker.health, system_id)}
    except MCPError as e:
        raise HTTPException(status_code=404, detail=str(e))
