"""M3 MCP 데이터 브로커 REST API. prefix /api/v1/mcp.

core/mcp_broker.py 의 온디맨드 조회(읽기 전용)·캐시 무효화·헬스체크를 노출한다.
v1 은 목 어댑터 기반(실 MCP 커넥터는 set_adapter 로 교체). 응답 봉투는 리포 관례.
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from api.deps import Principal, current_principal
from core.mcp_broker import mcp_broker, MCPError
from core.scope_guard import resolve_effective_scope

router = APIRouter(prefix="/api/v1/mcp")


async def _require_visible(system_id: str, scope_node_id: str = "", tenant_id: str = "",
                           entity_mode: str = "REAL", p: Principal = None) -> str:
    """이 문맥에서 그 시스템에 접근할 수 있는가. **모든 경로가 이 함수 하나를 쓴다** —
    같은 판정을 두 곳에 쓰면 한쪽만 고쳐졌을 때 그 경로만 열린다.

    ★ [M2 관문 B-4] 클라이언트가 보낸 `scope_node_id` 는 **요청이지 권한이 아니다.**
      서버가 인증 주체로부터 범위를 계산하고, 요청 범위는 그 안에서만 교차 검증한다.
      반환값은 **검증을 통과한 실효 범위** — 호출부는 이것을 브로커에 넘겨야 한다."""
    eff = await asyncio.to_thread(resolve_effective_scope, p, scope_node_id)
    if eff.denied:
        # 존재하지 않는 시스템과 **같은 응답** — 존재 자체를 알려주지 않는다.
        try:
            from core.enterprise_context import audit
            audit.denied_scope("mcp_resource", system_id, actor=eff.actor,
                               actor_scopes=eff.allowed_scopes, requested_scope=scope_node_id,
                               detail=eff.reason)
        except Exception:
            pass
        raise HTTPException(status_code=404, detail=f"등록되지 않은 시스템: {system_id}")
    if not (eff.scope_node_id or tenant_id):
        return ""                    # 범위 미지정 — 종전 동작(ECM 미도입 흐름 보존)
    from core.crosswalk import crosswalk
    ok = await asyncio.to_thread(crosswalk.is_system_visible, system_id, eff.scope_node_id,
                                 tenant_id, entity_mode or "REAL")
    if not ok:
        try:
            from core.enterprise_context import audit
            audit.denied_scope("external_system", system_id, actor=eff.actor,
                               actor_scopes=eff.allowed_scopes, requested_scope=scope_node_id)
        except Exception:
            pass
        raise HTTPException(status_code=404, detail=f"등록되지 않은 시스템: {system_id}")
    return eff.scope_node_id


# ── [ECM E2] 조직 범위 ────────────────────────────────────────────────
# ⚠️ MCP 조회는 **남의 조직 실측값을 가져올 수 있는 경로**다. 범위를 주면 브로커가 보이지 않는
#   시스템의 조회를 거부하고, 그 거부는 '등록되지 않은 시스템'과 **같은 문구**다(존재 노출 금지).
#   범위를 주지 않으면 종전 동작(ECM 미도입 흐름 보존).
class _Scoped(BaseModel):
    scope_node_id: Optional[str] = ""
    tenant_id: Optional[str] = ""
    entity_mode: Optional[str] = "REAL"


class ResolveRequest(_Scoped):
    master_code: str
    system_id: str
    ttl: Optional[int] = None
    force: bool = False


class ResolveBatchRequest(_Scoped):
    master_codes: List[str]
    system_id: str
    ttl: Optional[int] = None


class InvalidateRequest(_Scoped):
    system_id: str
    external_key: Optional[str] = None


@router.post("/resolve")
async def resolve(req: ResolveRequest, p: Principal = Depends(current_principal)):
    eff = await _require_visible(req.system_id, req.scope_node_id or "", req.tenant_id or "",
                                 req.entity_mode or "REAL", p)
    try:
        data = await asyncio.to_thread(mcp_broker.resolve, req.master_code, req.system_id,
                                       req.ttl, req.force, eff,
                                       req.tenant_id or "", req.entity_mode or "REAL",
                                       p.user_id, sorted(p.scope.readable_dept_ids or ()))
        return {"status": "success", "data": data}
    except MCPError as e:
        # ★ [M2 관문 B-1 / §3.3 경계표] "등록되지 않은 시스템"은 **404** 다 — 존재 여부를
        #   알려주지 않기 위함이고, 권한 없는 경우와 **같은 응답**이어야 은폐가 성립한다.
        #   나머지(비활성·매핑 없음)는 자원의 존재를 이미 아는 상태의 **상태 충돌**이라 409 다.
        #   전부 404 로 뭉개면 "왜 안 되는지"를 알 수 없어 운영 진단이 불가능해진다.
        _msg = str(e)
        raise HTTPException(status_code=404 if "등록되지 않은 시스템" in _msg else 409,
                            detail=_msg)


@router.post("/resolve-batch")
async def resolve_batch(req: ResolveBatchRequest, p: Principal = Depends(current_principal)):
    eff = await _require_visible(req.system_id, req.scope_node_id or "", req.tenant_id or "",
                                 req.entity_mode or "REAL", p)
    data = await asyncio.to_thread(mcp_broker.resolve_batch, req.master_codes, req.system_id,
                                   req.ttl, eff, req.tenant_id or "",
                                   req.entity_mode or "REAL",
                                   p.user_id, sorted(p.scope.readable_dept_ids or ()))
    return {"status": "success", "data": data}


@router.post("/invalidate")
async def invalidate(req: InvalidateRequest, p: Principal = Depends(current_principal)):
    # 캐시 무효화도 그 시스템에 대한 조작이다 — 볼 수 없는 시스템의 캐시를 남이 비우게 두지 않는다.
    await _require_visible(req.system_id, req.scope_node_id or "", req.tenant_id or "",
                           req.entity_mode or "REAL", p)
    n = await asyncio.to_thread(mcp_broker.invalidate, req.system_id, req.external_key)
    return {"status": "success", "data": {"invalidated": n}}


@router.get("/systems/{system_id}/health")
async def health(system_id: str, scope_node_id: str = "", tenant_id: str = "",
                 entity_mode: str = "REAL", p: Principal = Depends(current_principal)):
    # 헬스체크만으로도 '그 시스템이 있다'는 사실이 새어 나간다.
    await _require_visible(system_id, scope_node_id, tenant_id, entity_mode, p)
    try:
        return {"status": "success", "data": await asyncio.to_thread(mcp_broker.health, system_id)}
    except MCPError as e:
        raise HTTPException(status_code=404, detail=str(e))
