"""B3 신규 L2 팩 적용본의 별도 2.0 계약 API. 기존 1.0 입력 계약을 바꾸지 않는다."""
import asyncio

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from api.deps import Principal, current_principal, require_caps, viewing_context
from api.routes.process_configuration_control import error
from core.admin_capability import ADMIN_DATA_ACCESS, PROJECT_RUN
from core.enterprise_context.process_schema import ProcessBoundary, ProcessError, StrictModel

router = APIRouter()


class KitDraftIn(StrictModel):
    profile_id: str = Field(min_length=1)
    process_ids: list[str] = Field(min_length=1, max_length=200)
    app_class: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)


class KitRevisionIn(StrictModel):
    revision: int = Field(ge=1)
    expected_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class KitApproveIn(KitRevisionIn):
    rationale: str = Field(min_length=1, max_length=4000)


class KitRejectIn(StrictModel):
    revision: int = Field(ge=1)
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    rationale: str = Field(min_length=1, max_length=4000)


def selection(instance_id, p):
    from api.routes import data_preparation_control as api
    from core.data_preparation.process_kit_instances import binding_for_instance
    instance = api._instance_or_404(p, instance_id)
    context = viewing_context(p)
    if not p.requested_scope_node_id or not context.get("scope_node_id"):
        raise ProcessError("PROCESS_CONTEXT_REQUIRED", "회사·조직 문맥을 명시적으로 선택하십시오.", 422)
    link = binding_for_instance(api.store, instance)
    if not link:
        raise ProcessError("PROCESS_INSTANCE_NOT_FOUND", "새 업무 팩 적용본을 찾을 수 없습니다.", 404)
    root = link["context_root_id"]
    boundary = ProcessBoundary(tenant_id=instance["tenant_id"], context_root_id=root,
        entity_mode=instance["entity_mode"], scope_node_id="" if instance["scope_node_id"] == root else instance["scope_node_id"])
    return api.store, boundary, context


@router.get("/instances/{instance_id}/apps/{app_id}/contract/v2")
async def read(instance_id: str, app_id: str, revision: int | None = Query(default=None, ge=1),
               p: Principal = Depends(current_principal)):
    """고정 계약 열람은 PROJECT_RUN이나 데이터 사용 권한을 발급하지 않는다."""
    try:
        from core import kit_app_contract
        store, _, context = selection(instance_id, p)
        result = await asyncio.to_thread(kit_app_contract.read_v2, store, instance_id=instance_id,
            app_id=app_id, actor_id=p.user_id, context=context, revision=revision)
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id, instance_id)


@router.post("/instances/{instance_id}/apps/{app_id}/contract/v2")
async def draft(instance_id: str, app_id: str, req: KitDraftIn, p: Principal = Depends(current_principal)):
    require_caps(p, PROJECT_RUN, resource="data_preparation", action="apps:contract:v2:draft")
    try:
        from core.enterprise_context.process_context import ProcessContextService
        from core import kit_app_contract
        store, boundary, context = selection(instance_id, p)
        fixed = await asyncio.to_thread(ProcessContextService(store=store).build, boundary=boundary, actor=p.user_id,
                                        context=context, profile_id=req.profile_id, process_ids=req.process_ids)
        result = await asyncio.to_thread(kit_app_contract.draft_v2, store, instance_id=instance_id,
            app_id=app_id, actor_id=p.user_id, context=context, process_context=fixed,
            app_class=req.app_class, expected_revision=req.expected_revision)
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id, instance_id)


@router.post("/instances/{instance_id}/apps/{app_id}/contract/v2/approve")
async def approve(instance_id: str, app_id: str, req: KitApproveIn, p: Principal = Depends(current_principal)):
    require_caps(p, ADMIN_DATA_ACCESS, resource="data_preparation", action="apps:contract:v2:approve")
    try:
        from core import kit_app_contract
        store, _, context = selection(instance_id, p)
        result = await asyncio.to_thread(kit_app_contract.approve_v2, store, instance_id=instance_id,
            app_id=app_id, actor_id=p.user_id, context=context, **req.model_dump())
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id, instance_id)


@router.post("/instances/{instance_id}/apps/{app_id}/contract/reject")
async def reject(instance_id: str, app_id: str, req: KitRejectIn, p: Principal = Depends(current_principal)):
    require_caps(p, ADMIN_DATA_ACCESS, resource="data_preparation", action="apps:contract:reject")
    try:
        from api.routes import data_preparation_control as api
        from core.data_preparation.process_kit_instances import binding_for_instance
        from core import kit_app_contract
        instance = api._instance_or_404(p, instance_id)
        context = viewing_context(p)
        if not p.requested_scope_node_id or not context.get("scope_node_id"):
            raise ProcessError("PROCESS_CONTEXT_REQUIRED", "회사·조직 문맥을 명시적으로 선택하십시오.", 422)
        # 계약 판본은 사용자 선택이 아니라 서버 적용본에서 결정한다.
        linked = binding_for_instance(api.store, instance)
        reject_contract = kit_app_contract.reject_v2 if linked else kit_app_contract.reject
        result = await asyncio.to_thread(reject_contract, api.store, instance_id=instance_id,
            app_id=app_id, revision=req.revision, expected_fingerprint=req.expected_digest,
            actor_id=p.user_id, context=context, rationale=req.rationale)
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id, instance_id)


@router.post("/instances/{instance_id}/apps/{app_id}/build/v2")
async def build(instance_id: str, app_id: str, req: KitRevisionIn, p: Principal = Depends(current_principal)):
    require_caps(p, PROJECT_RUN, resource="data_preparation", action="apps:build:v2")
    try:
        from core import app_preview, kit_app_builder
        store, _, context = selection(instance_id, p)
        result = await asyncio.to_thread(kit_app_builder.build_v2, store=store,
            app_data=app_preview.app_data_for(app_preview.AUDIENCE_PREVIEW), instance_id=instance_id,
            app_id=app_id, actor_id=p.user_id, context=context, **req.model_dump())
        return {"status": "success", "data": result}
    except ProcessError as exc:
        error(exc, p.user_id, instance_id)
