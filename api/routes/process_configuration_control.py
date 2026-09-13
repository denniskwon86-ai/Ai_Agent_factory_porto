"""B1 업무 구성 API. 기존 ECM router에 포함되며 권한표와 동일하게 검사한다."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field

from api.deps import Principal, current_principal, enterprise_context
from core.enterprise_context.context import EnterpriseContext
from core.enterprise_context.process_configuration import ProcessConfigurationService
from core.enterprise_context.process_schema import ProcessBoundary, ProcessError, StrictModel

router = APIRouter()


def error(exc, actor="", resource_id=""):
    if exc.status_code in (401, 403, 404):
        from core.enterprise_context import audit
        audit.record(audit.ACCESS_DENIED_SCOPE_MISMATCH, resource_type="process_configuration",
                     resource_id=resource_id, actor=actor, outcome="denied", reason=exc.reason_code)
    raise HTTPException(status_code=exc.status_code, detail={"reason_code": exc.reason_code,
                         "message": str(exc), "next_action": "입력을 보존하고 문맥·권한·최신 승인판을 확인하십시오."})


def explicit_context(request, ctx):
    import config
    scope = (request.headers.get(getattr(config, "ECM_SCOPE_HEADER", "X-Enterprise-Scope"))
             or request.query_params.get("enterprise_scope") or "")
    if not scope:
        raise ProcessError("PROCESS_CONTEXT_REQUIRED", "회사·조직 문맥을 명시적으로 선택하십시오.", 422)
    service = ProcessConfigurationService()
    with service.transaction() as conn:
        rows = conn.execute(
            "SELECT n.node_id FROM organization_nodes n JOIN enterprise_entities e ON n.entity_id=e.entity_id "
            "WHERE n.tenant_id=? AND e.tenant_id=? AND e.entity_mode=? AND n.status='ACTIVE' AND e.status='ACTIVE' "
            "AND (n.node_id=? OR n.code=? OR n.dept_id=?)",
            (ctx.tenant_id, ctx.tenant_id, ctx.entity_mode, scope, scope, scope)).fetchall()
        if len(rows) != 1:
            raise ProcessError("PROCESS_NOT_FOUND", "업무 구성을 찾을 수 없습니다.", 404)
    return {"tenant_id": ctx.tenant_id, "entity_mode": ctx.entity_mode, "scope_node_id": rows[0][0]}


def boundary_for(ctx, root, scope):
    try:
        return ProcessBoundary(tenant_id=ctx.tenant_id, context_root_id=root,
                               entity_mode=ctx.entity_mode, scope_node_id=scope)
    except ValueError as exc:
        raise ProcessError("PROCESS_CONTEXT_INVALID", "회사·조직 루트·모드 형식을 확인하십시오.", 422) from exc


def guard_old_profile_target(profile_id, request, ctx, actor):
    """ID로 구 API를 호출해도 저장된 v2 대상의 문맥부터 검사한다."""
    if not profile_id:
        return
    service = ProcessConfigurationService()
    with service.transaction() as conn:
        row = conn.execute("SELECT * FROM enterprise_profiles WHERE profile_id=?", (profile_id,)).fetchone()
        if row and row["configuration_id"]:
            boundary = ProcessBoundary(tenant_id=row["tenant_id"], context_root_id=row["context_root_id"],
                                       entity_mode=row["entity_mode"], scope_node_id=row["scope_node_id"])
            service._authorize(conn, boundary, actor, explicit_context(request, ctx))
            raise ProcessError("PROCESS_SCHEMA_UPGRADE_REQUIRED", "새 업무 구성 편집기를 사용하십시오.")


def legacy_projection(request, ctx, actor, scope_node_id, company_wide):
    """구 화면에는 승인된 L1만 읽기 전용으로 보여준다. 저장 시 repository guard가 409."""
    service = ProcessConfigurationService()
    try:
        context = explicit_context(request, ctx)
    except ProcessError as exc:
        if exc.reason_code == "PROCESS_CONTEXT_REQUIRED":
            # 구 호출자에게 다른 루트의 v2 존재 여부에 따라 응답을 달리하지 않는다.
            return []
        raise
    provisional = boundary_for(ctx, context["scope_node_id"], "")
    with service.transaction() as conn:
        chain = service._chain(conn, context["scope_node_id"], provisional)
    boundary = boundary_for(ctx, chain[-1], "" if company_wide else (scope_node_id or context["scope_node_id"]))
    value = service.resolved(boundary=boundary, actor=actor, context=context)
    if value["state"] != "APPROVED":
        return []
    nodes = [{"key": n["process_id"], "label": n["label"], "note": n["note"]}
             for n in value["payload"]["nodes"] if n["level"] == "L1"]
    return [{"profile_id": value["profile_id"], "tenant_id": ctx.tenant_id,
             "scope_node_id": boundary.scope_node_id, "profile_kind": "process_profile",
             "payload": {"nodes": nodes}, "status": "ACTIVE", "is_effective": True,
             "version": value["version"], "read_only": True, "editor_schema_required": 2,
             "reason_code": "PROCESS_SCHEMA_UPGRADE_REQUIRED", "configuration_id": value["configuration_id"],
             "digest": value["digest"], "note": "편집기 업데이트 필요: L1 읽기 전용 보기입니다."}]


class ChangeIn(StrictModel):
    context_root_id: str = Field(min_length=1)
    scope_node_id: str = ""
    commands: list[dict]
    expected_head_version: int = Field(ge=0)
    base_profile_id: str
    base_fingerprint: str
    client_request_id: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=4000)
    legacy_token: str = ""


class ValidateIn(StrictModel):
    draft_digest: str = Field(min_length=64, max_length=64)


class ApproveIn(ValidateIn):
    expected_head_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=4000)


@router.get("/process-configurations/context")
async def process_context(request: Request, company_wide: bool = False,
                          p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessConfigurationService().resolve_context,
            actor=p.user_id, context=explicit_context(request, ctx), company_wide=company_wide)
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id)


@router.get("/process-configurations/resolved")
async def resolved(request: Request, context_root_id: str, scope_node_id: str = "", profile_id: str = "",
                   p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessConfigurationService().resolved,
            boundary=boundary_for(ctx, context_root_id, scope_node_id), actor=p.user_id,
            context=explicit_context(request, ctx), profile_id=profile_id)
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id, profile_id)


@router.get("/process-configurations/events")
async def events(request: Request, context_root_id: str, scope_node_id: str = "",
                 p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessConfigurationService().events,
            boundary=boundary_for(ctx, context_root_id, scope_node_id), actor=p.user_id,
            context=explicit_context(request, ctx))
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id)


@router.post("/process-configurations/changes")
@router.post("/process-configurations/{configuration_id}/changes")
async def propose(req: ChangeIn, request: Request, configuration_id: str = "",
                  p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        values = req.model_dump(exclude={"context_root_id", "scope_node_id"})
        result = await asyncio.to_thread(ProcessConfigurationService().propose,
            boundary=boundary_for(ctx, req.context_root_id, req.scope_node_id), actor=p.user_id,
            context=explicit_context(request, ctx), configuration_id=configuration_id, **values)
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id, configuration_id)


@router.get("/process-changes")
async def list_changes(request: Request, context_root_id: str, scope_node_id: str = "", status: str = "DRAFT",
                       limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
                       p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessConfigurationService().list_changes,
            boundary=boundary_for(ctx, context_root_id, scope_node_id), actor=p.user_id,
            context=explicit_context(request, ctx), status=status, limit=limit, offset=offset)
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id)


@router.get("/process-changes/{change_id}")
async def get_change(change_id: str, request: Request, context_root_id: str, scope_node_id: str = "",
                     p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessConfigurationService().get_change,
            change_id=change_id, boundary=boundary_for(ctx, context_root_id, scope_node_id),
            actor=p.user_id, context=explicit_context(request, ctx))
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id, change_id)


@router.post("/process-changes/{change_id}/validate")
async def validate(change_id: str, req: ValidateIn, request: Request,
                   p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessConfigurationService().validate,
            change_id=change_id, actor=p.user_id, context=explicit_context(request, ctx), **req.model_dump())
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id, change_id)


@router.post("/process-changes/{change_id}/approve")
async def approve(change_id: str, req: ApproveIn, request: Request,
                  p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessConfigurationService().approve,
            change_id=change_id, actor=p.user_id, context=explicit_context(request, ctx), **req.model_dump())
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id, change_id)


@router.post("/process-changes/{change_id}/reject")
async def reject(change_id: str, req: ApproveIn, request: Request,
                 p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessConfigurationService().reject,
            change_id=change_id, actor=p.user_id, context=explicit_context(request, ctx), **req.model_dump())
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id, change_id)
