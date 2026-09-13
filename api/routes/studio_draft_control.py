"""B3 통합 제작기의 명시 문맥·초안 revision·승격 API. 글로벌 진입점 변경 없음."""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from api.deps import Principal, current_principal, enterprise_context
from api.routes.process_configuration_control import boundary_for, error, explicit_context
from core.advisor_revision_store import RevisionStoreError
from core.enterprise_context.context import EnterpriseContext
from core.enterprise_context.process_schema import StrictModel, ProcessError
from core.studio_drafts import StudioDraftService

router = APIRouter()


class BoundaryIn(StrictModel):
    context_root_id: str = Field(min_length=1)
    scope_node_id: str = ""


class SaveIn(BoundaryIn):
    draft_id: str = ""
    expected_revision: int = Field(ge=0)
    expected_digest: str
    patch: list[dict] = Field(min_length=1, max_length=200)
    client_request_id: str = Field(min_length=1, max_length=160)
    process_selection: dict | None = None


class DecideIn(BoundaryIn):
    expected_revision: int = Field(ge=1)
    draft_digest: str = Field(min_length=64, max_length=64)
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=1, max_length=4000)


class BootstrapIn(BoundaryIn):
    approved_revision_id: str = Field(min_length=1)
    approved_digest: str = Field(min_length=64, max_length=64)
    expected_process_semantic_digest: str = Field(min_length=64, max_length=64)
    client_request_id: str = Field(min_length=1, max_length=160)


class ContextIn(BoundaryIn):
    profile_id: str = Field(min_length=1)
    process_ids: list[str] = Field(min_length=1, max_length=200)


def arguments(req, request, p, ctx):
    return dict(boundary=boundary_for(ctx, req.context_root_id, req.scope_node_id), actor=p.user_id,
                context=explicit_context(request, ctx))


@router.post("/drafts/process-context")
async def process_context(req: ContextIn, request: Request, p: Principal = Depends(current_principal),
                          ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        from core.enterprise_context.process_context import ProcessContextService
        result = await asyncio.to_thread(ProcessContextService().build, **arguments(req, request, p, ctx),
                                         profile_id=req.profile_id, process_ids=req.process_ids)
        return {"status": "success", "data": result}
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id)


@router.post("/drafts")
async def save(req: SaveIn, request: Request, p: Principal = Depends(current_principal),
               ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        fields = req.model_dump(exclude={"context_root_id", "scope_node_id", "process_selection"})
        if "process_selection" in req.model_fields_set:
            fields["process_selection"] = req.process_selection
        result = await asyncio.to_thread(StudioDraftService().save, **arguments(req, request, p, ctx), **fields)
        return {"status": "success", "data": result}
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id, req.draft_id)


@router.get("/drafts/{draft_id}")
async def get(draft_id: str, request: Request, context_root_id: str, scope_node_id: str = "", revision: int | None = None,
              p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        req = BoundaryIn(context_root_id=context_root_id, scope_node_id=scope_node_id)
        result = await asyncio.to_thread(StudioDraftService().get, **arguments(req, request, p, ctx),
                                         draft_id=draft_id, revision=revision)
        return {"status": "success", "data": result}
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id, draft_id)


@router.post("/drafts/{draft_id}/decision")
async def decide(draft_id: str, req: DecideIn, request: Request, p: Principal = Depends(current_principal),
                 ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        result = await asyncio.to_thread(StudioDraftService().decide, **arguments(req, request, p, ctx),
            draft_id=draft_id, **req.model_dump(exclude={"context_root_id", "scope_node_id"}))
        return {"status": "success", "data": result}
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id, draft_id)


@router.post("/drafts/bootstrap-project")
async def bootstrap(req: BootstrapIn, request: Request, p: Principal = Depends(current_principal),
                    ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        from core.studio_bootstrap import StudioBootstrapService
        result = await asyncio.to_thread(StudioBootstrapService().bootstrap, **arguments(req, request, p, ctx),
                                         **req.model_dump(exclude={"context_root_id", "scope_node_id"}))
        return {"status": "success", "data": result}
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id, req.approved_revision_id)


@router.get("/drafts/bootstrap-operations/{operation_id}")
async def get_operation(operation_id: str, request: Request, context_root_id: str, scope_node_id: str = "",
                        p: Principal = Depends(current_principal), ctx: EnterpriseContext = Depends(enterprise_context)):
    try:
        from core.studio_bootstrap import StudioBootstrapService
        req = BoundaryIn(context_root_id=context_root_id, scope_node_id=scope_node_id)
        result = await asyncio.to_thread(StudioBootstrapService().get, **arguments(req, request, p, ctx), operation_id=operation_id)
        return {"status": "success", "data": result}
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id, operation_id)
