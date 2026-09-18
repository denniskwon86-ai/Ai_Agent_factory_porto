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
from core.studio_drafts import StudioDraftService, context_key

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


#: [DRAFT-ENTRY-01 · 2026-09-15] URL 문법이 받는 초안 종류. 문법 모듈과 같은 목록이다.
DRAFT_KINDS = ("consultation", "blueprint")
#: ★★★ 모든 거절이 **같은 문구**여야 한다 — 나누면 존재 여부가 응답으로 샌다.
#:
#: ⚠️⚠️ 그래서 문구를 «내가 짓지 않는다». 권한 층(`_authorize`)이 못 보는 대상에
#:   쓰는 바로 그 `missing()` 을 그대로 쓴다. 손으로 같은 문자열을 적어 두면 한쪽이
#:   바뀌는 날 조용히 갈라지고, 그날 「없는 초안」과 「내 문맥이 아닌 초안」이
#:   구분된다 — 실제로 시험이 그 갈라짐을 잡았다(둘의 문구가 달랐다).


@router.get("/drafts/{draft_id}/entry-metadata")
async def entry_metadata(draft_id: str, request: Request, kind: str, revision: int,
                         p: Principal = Depends(current_principal),
                         ctx: EnterpriseContext = Depends(enterprise_context)):
    """[DRAFT-ENTRY-01] 선택 문맥에서의 **읽기 진입 확인**만 제공한다.

    ## ★★★ 기존 `GET /drafts/{draft_id}` 와 결정적으로 다른 점

    그 경로는 `context_root_id` 를 **인자로 받는다.** 그러면 프런트가 경계를 «어디선가
    만들어» 넣어야 하고, 만든 값이 사용자의 현재 선택과 다르면 **다른 문맥의 초안을 여는
    길**이 열린다. URL 로 들어온 초안이 어느 문맥 것인지 프런트는 알 수 없다.

    여기서는 **서버가 유도한다** — 초안이 자기 경계를 들고 있으므로(`advisor_v2_drafts`
    의 `draft_id` 는 PRIMARY KEY 다) id 로 찾아 소유 문맥을 읽고, 선택 문맥(헤더)과
    기존 권한 층이 대조한다. `project` 진입과 같은 모양이 된다.

    ## 판정 순서 — 순서가 곧 규칙이다

        ① 종류·판본 형식        (지원 종류인가 · 판본이 1 이상인가)
        ② 선택 문맥 확정        `explicit_context` 가 헤더를 조직 정본에 대조한다
        ③ 소유 문맥 판독        초안이 들고 있는 경계 4키를 «찾는다». 받지 않는다
        ④ 권한·문맥 대조        기존 `_authorize` — 테넌트·모드·범위 사슬·권한을 본다
        ⑤ 판본 존재            제품 경로(`revisions.get`)로 확인하고 **내용은 버린다**

    ⚠️ ④를 다시 만들지 않는다. 그 함수가 이미 「선택 문맥이 이 초안의 사슬 안에 있는가」
      까지 본다 — 두 벌로 만들면 한쪽만 느슨해진다.
    ⚠️ **초안 원문·판본 목록·승인 상태를 주지 않는다.** 진입 확인은 「볼 수 있는가」만
      답한다. ⑤의 결과에서 꺼내는 것은 판본 번호 하나뿐이다.
    """
    from core.enterprise_context.process_configuration import missing
    from core.enterprise_context.process_schema import ProcessBoundary

    try:
        wanted = (kind or "").strip()
        if wanted not in DRAFT_KINDS:
            raise ProcessError("STUDIO_DRAFT_KIND_INVALID", "지원하지 않는 초안 종류입니다.", 422)
        if wanted == "consultation":
            #: ⚠️⚠️ **조용히 열지 않는다.** 상담에는 판본 개념이 없는데 URL 문법은 판본을
            #:   필수로 받는다 — 확인할 대상이 없는 값을 그냥 버리면 kit_app `releaseId`
            #:   와 같은 결함이 된다. 「지원 전」임을 서버가 «말한다».
            raise ProcessError("STUDIO_DRAFT_KIND_UNSUPPORTED",
                               "상담 초안은 아직 진입 확인을 지원하지 않습니다.", 422)
        if type(revision) is not int or revision < 1:
            raise ProcessError("STUDIO_DRAFT_REVISION_INVALID", "초안 판본은 1 이상이어야 합니다.", 422)

        context = explicit_context(request, ctx)
        service = StudioDraftService()
        found = await asyncio.to_thread(service.revisions.boundary_of, draft_id=draft_id)
        if found is None:
            raise missing()
        try:
            boundary = ProcessBoundary(**found["boundary"])
        except (TypeError, ValueError):
            raise missing()

        await asyncio.to_thread(service.authorize, boundary, p.user_id, context, "READ")
        row = await asyncio.to_thread(service.revisions.get, boundary=context_key(boundary),
                                      actor=p.user_id, draft_id=draft_id, revision=revision)
        owned = context_key(boundary)
        return {"status": "success", "data": {
            "draft_id": draft_id, "draft_kind": wanted, "revision": int(row["revision"]),
            "ownership": owned,
            "viewing_context": {"tenant_id": ctx.tenant_id,
                                "scope_node_id": context["scope_node_id"],
                                "entity_mode": ctx.entity_mode}}}
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
