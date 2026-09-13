"""B2 설치 API. 명시 문맥·현재 권한을 B1 서비스와 공유한다."""
import asyncio

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from api.deps import Principal, current_principal
from api.routes.process_configuration_control import explicit_context, boundary_for, error
from core.enterprise_context.context import EnterpriseContext
from api.deps import enterprise_context
from core.enterprise_context.process_schema import ProcessError, StrictModel
from core.enterprise_context.process_installation import ProcessInstallationService

router = APIRouter()


class RegisterIn(StrictModel):
    context_root_id: str = Field(min_length=1)
    scope_node_id: str = ""
    kit_id: str = Field(min_length=1)
    version: str = Field(min_length=1)


def _catalog_bundle(kit_id, version):
    # 클라이언트가 로컬 경로·URL·임의 패키지를 지정할 수 없다.
    from pathlib import Path
    from core.data_preparation.process_pack_artifacts import load_bundle
    if (kit_id, version) != ("KIT-MFG-NONFERROUS-PROCUREMENT", "1.1.0"):
        raise ProcessError("PROCESS_PACK_NOT_FOUND", "검토 가능한 팩 판본을 찾지 못했습니다.", 404)
    path = Path(__file__).resolve().parents[2] / "process_packs/afs.manufacturing.materials-processes/1.1.0/manifest.json"
    return load_bundle(path)


def _business_kits(bundle):
    """검증된 팩의 L1 표준 이름이 키트 선택 이름이다. BK 코드로 추정하지 않는다."""
    templates = bundle["pack"]["templates"]
    keys = {t["business_kit_id"] for t in templates}
    roots = [t for t in templates if t["level"] == "L1"]
    if len(roots) != len(keys) or {t["business_kit_id"] for t in roots} != keys:
        raise ProcessError("PROCESS_PACK_METADATA_UNAVAILABLE", "업무키트별 표준 명칭을 확정하지 못했습니다.", 503)
    return [{"business_kit_id": t["business_kit_id"], "label": t["label"]}
            for t in sorted(roots, key=lambda t: t["business_kit_id"])]


@router.get("/process-packs")
async def catalog(request: Request, context_root_id: str, scope_node_id: str = "",
                  p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        service = ProcessInstallationService()
        boundary = boundary_for(ctx, context_root_id, scope_node_id)
        with service.transaction() as conn:
            service._authorize(conn, boundary, p.user_id, explicit_context(request, ctx))
        bundle = await asyncio.to_thread(_catalog_bundle, "KIT-MFG-NONFERROUS-PROCUREMENT", "1.1.0")
        return {"status": "success", "data": [{"kit_id": bundle["kit_id"], "version": bundle["version"],
            "artifact_digest": bundle["artifact_digest"], "name": bundle["profile"]["name"],
            "state": "DOMAIN_REVIEW_REQUIRED", "data_class": "NO_DATA", "setup_only": True,
            "business_kit_ids": sorted({t["business_kit_id"] for t in bundle["pack"]["templates"]}),
            "business_kits": _business_kits(bundle)}]}
    except ProcessError as exc:
        error(exc, p.user_id)


@router.post("/process-packs/register")
async def register(req: RegisterIn, request: Request, p: Principal = Depends(current_principal),
                   ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        service = ProcessInstallationService()
        with service.transaction() as conn:
            service._authorize(conn, boundary_for(ctx, req.context_root_id, req.scope_node_id),
                               p.user_id, explicit_context(request, ctx), "edit")
        bundle = await asyncio.to_thread(_catalog_bundle, req.kit_id, req.version)
        from core.data_preparation.process_pack_artifacts import pin_bundle
        await asyncio.to_thread(pin_bundle, service.store, bundle)
        return {"status": "success", "data": {"artifact_digest": bundle["artifact_digest"],
                "kit_id": bundle["kit_id"], "version": bundle["version"], "state": "DOMAIN_REVIEW_REQUIRED"}}
    except ProcessError as exc:
        error(exc, p.user_id)


class PlanIn(StrictModel):
    context_root_id: str = Field(min_length=1)
    scope_node_id: str = ""
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    business_kit_ids: list[str] = Field(min_length=1)
    expected_head_version: int = Field(ge=0)
    base_profile_id: str
    base_fingerprint: str
    legacy_decisions: list[dict] = Field(default_factory=list)
    template_mapping: dict[str, str] = Field(default_factory=dict)
    instance_id: str = ""
    reason: str = Field(min_length=1, max_length=4000)


class InstallIn(PlanIn):
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    client_request_id: str = Field(min_length=1, max_length=160)


class ResumeIn(StrictModel):
    expected_revision: int = Field(ge=0)
    adopt: bool = False


@router.get("/process-installations/legacy-preview")
async def legacy_preview(request: Request, context_root_id: str, scope_node_id: str = "",
                         p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessInstallationService().legacy_preview,
            boundary=boundary_for(ctx, context_root_id, scope_node_id), actor=p.user_id, context=explicit_context(request, ctx))
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id)


@router.post("/process-installations/plan")
async def plan(req: PlanIn, request: Request, p: Principal = Depends(current_principal),
               ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessInstallationService().plan,
            boundary=boundary_for(ctx, req.context_root_id, req.scope_node_id), actor=p.user_id,
            context=explicit_context(request, ctx), **req.model_dump(exclude={"context_root_id", "scope_node_id"}))
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id)


@router.post("/process-installations")
async def start(req: InstallIn, request: Request, p: Principal = Depends(current_principal),
                ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessInstallationService().start,
            boundary=boundary_for(ctx, req.context_root_id, req.scope_node_id), actor=p.user_id,
            context=explicit_context(request, ctx), **req.model_dump(exclude={"context_root_id", "scope_node_id"}))
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id)


@router.get("/process-installations")
async def list_operations(request: Request, context_root_id: str, scope_node_id: str = "",
                          limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
                          p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(ProcessInstallationService().list_operations,
            boundary=boundary_for(ctx, context_root_id, scope_node_id), actor=p.user_id,
            context=explicit_context(request, ctx), limit=limit, offset=offset)
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id)


@router.get("/process-installations/{operation_id}")
async def get(operation_id: str, request: Request, p: Principal = Depends(current_principal),
              ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        return {"status": "success", "data": await asyncio.to_thread(ProcessInstallationService().get,
            operation_id=operation_id, actor=p.user_id, context=explicit_context(request, ctx))}
    except ProcessError as exc:
        error(exc, p.user_id, operation_id)


@router.post("/process-installations/{operation_id}/resume")
async def resume(operation_id: str, req: ResumeIn, request: Request, p: Principal = Depends(current_principal),
                 ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        return {"status": "success", "data": await asyncio.to_thread(ProcessInstallationService().resume,
            operation_id=operation_id, actor=p.user_id, context=explicit_context(request, ctx),
            expected_revision=req.expected_revision, adopt=req.adopt)}
    except ProcessError as exc:
        error(exc, p.user_id, operation_id)


@router.post("/process-installations/{operation_id}/cancel")
async def cancel(operation_id: str, request: Request, p: Principal = Depends(current_principal),
                 ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        return {"status": "success", "data": await asyncio.to_thread(ProcessInstallationService().cancel,
            operation_id=operation_id, actor=p.user_id, context=explicit_context(request, ctx))}
    except ProcessError as exc:
        error(exc, p.user_id, operation_id)
