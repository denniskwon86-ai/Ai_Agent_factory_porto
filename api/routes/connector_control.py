"""[M2] 커넥터 등록부 + Query Contract REST API. prefix `/api/v1/connectors`. **LLM 0콜.**

§7.1 커넥터 계층 · §7.2 MCP 원칙(최소 권한·읽기 전용·명시적 등록·감사).

권한은 M2 자산(`core/scope_guard.py`)을 그대로 쓴다 — 커넥터도 조직 자산이고,
남의 사업부 연결은 **존재 자체가 보이면 안 된다**(404 은폐 + 감사).
"""
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Principal, current_principal
from core.connector_registry import ConnectorError, connector_registry
from core.scope_guard import resolve_effective_scope

router = APIRouter(prefix="/api/v1/connectors", tags=["Connectors"])


def _err(e: ConnectorError):
    raise HTTPException(status_code=400, detail=str(e))


async def _scope(p: Principal, requested: str, resource_id: str = "") -> str:
    eff = await asyncio.to_thread(resolve_effective_scope, p, requested)
    if eff.denied:
        try:
            from core.enterprise_context import audit
            audit.denied_scope("connector", resource_id or requested, actor=eff.actor,
                               actor_scopes=eff.allowed_scopes, requested_scope=requested,
                               detail=eff.reason)
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    return eff.scope_node_id


class ConnectorRequest(BaseModel):
    connector_id: str
    name: str
    kind: str                       # mcp | api | db | file
    endpoint: Optional[str] = ""
    #: ★ 자격증명이 아니라 **참조**(환경변수명·비밀관리자 키). 실제 비밀은 거부된다.
    auth_ref: Optional[str] = ""
    access_mode: str = "read"       # 기본 읽기 전용(§7.2)
    owner_organization_id: Optional[str] = ""
    scope_type: Optional[str] = "ORG_PRIVATE"
    note: Optional[str] = ""


class ContractRequest(BaseModel):
    query_name: str
    #: 비울 수 없다 — 빈 화이트리스트는 "아무거나 다 준다"가 된다.
    allowed_fields: List[str]
    required_params: Optional[List[str]] = None
    max_rows: int = 1000
    #: 허용 목록에 있어도 **프롬프트로는 나가지 않는다**(§7.2).
    sensitive_fields: Optional[List[str]] = None
    description: Optional[str] = ""


class ValidateRequest(BaseModel):
    query_name: str
    fields: List[str]
    params: Optional[Dict[str, Any]] = None
    limit: int = 0
    #: True 면 민감 필드를 제거한다(오류가 아니라 제거이며, 무엇이 빠졌는지 알려준다).
    for_prompt: bool = False


@router.get("")
async def list_connectors(scope_node_id: str = "", tenant_id: str = "",
                          entity_mode: str = "REAL",
                          p: Principal = Depends(current_principal)):
    eff = await _scope(p, scope_node_id)
    data = await asyncio.to_thread(connector_registry.list_connectors, eff,
                                   tenant_id, entity_mode)
    return {"status": "success", "data": data,
            "permission": {"scope": eff or "(범위 필터 없음)"}}


@router.post("")
async def register_connector(req: ConnectorRequest,
                             p: Principal = Depends(current_principal)):
    await _scope(p, req.owner_organization_id or "", req.connector_id)
    try:
        data = await asyncio.to_thread(
            connector_registry.register, req.connector_id, req.name, req.kind,
            req.endpoint or "", req.auth_ref or "", req.access_mode,
            req.owner_organization_id or "", req.scope_type or "ORG_PRIVATE")
        return {"status": "success", "data": data}
    except ConnectorError as e:
        _err(e)


@router.post("/{connector_id}/activate")
async def activate(connector_id: str, p: Principal = Depends(current_principal)):
    """활성화 — 승인된 Query Contract 가 1건 이상 있어야 하고, 승인자가 식별돼야 한다."""
    if not p.user_id:
        raise HTTPException(status_code=401, detail="승인자 식별 정보가 없습니다.")
    try:
        return {"status": "success",
                "data": await asyncio.to_thread(connector_registry.activate,
                                                connector_id, p.user_id)}
    except ConnectorError as e:
        _err(e)


@router.get("/{connector_id}/contracts")
async def list_contracts(connector_id: str):
    return {"status": "success",
            "data": await asyncio.to_thread(connector_registry.list_contracts, connector_id)}


@router.post("/{connector_id}/contracts")
async def add_contract(connector_id: str, req: ContractRequest,
                       p: Principal = Depends(current_principal)):
    """Query Contract 등록. 승인자는 인증 주체로 기록된다(익명이면 미승인 상태)."""
    try:
        data = await asyncio.to_thread(
            connector_registry.add_contract, connector_id, req.query_name,
            req.allowed_fields, req.required_params, req.max_rows,
            req.sensitive_fields, req.description or "", p.user_id)
        return {"status": "success", "data": data}
    except ConnectorError as e:
        _err(e)


@router.post("/{connector_id}/validate")
async def validate_request(connector_id: str, req: ValidateRequest):
    """조회 요청이 계약을 지키는지 검증한다.

    ⚠️ 거부 사유를 **한 번에 전부** 돌려준다. 하나씩 튕기면 사용자가 여러 번 시도하며
      무엇이 되는지 탐색하게 되고, 그 탐색 자체가 스키마 정보 유출이다."""
    data = await asyncio.to_thread(connector_registry.validate_request, connector_id,
                                   req.query_name, req.fields, req.params or {},
                                   req.limit, req.for_prompt)
    return {"status": "success", "data": data}
