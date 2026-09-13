"""기록된 Host 승인의 상태 반영 복구. 새 승인이나 실행을 만들지 않는다."""
import asyncio
from functools import wraps

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from api.deps import Principal, current_principal, require_caps, assert_project_writable
from api.routes.process_configuration_control import error
from core.admin_capability import PROJECT_RUN
from core.advisor_revision_store import RevisionStoreError
from core.enterprise_context.process_schema import StrictModel, ProcessError

router = APIRouter()


class ReconcileIn(StrictModel):
    task_id: str = Field(min_length=1, max_length=128)
    request_event_id: str = Field(min_length=1, max_length=200)
    event_id: str = Field(min_length=1, max_length=200)
    compiled_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def contract_command(fn):
    """기존 결정 요청의 await 기간에도 복구가 겹치지 않도록 예약한다."""
    @wraps(fn)
    async def guarded(project_id, req, p):
        from api.routes import factory_control as factory
        from core.studio_execution_guard import command, finish_before_cancel
        factory._safe_id(project_id, "project_id")
        assert_project_writable(p, project_id)
        async def invoke():
            with command(factory.orchestrator, project_id, exclusive=True, quiescent=True):
                return await fn(project_id, req, p)
        try:
            return await finish_before_cancel(invoke())
        except ProcessError as exc:
            error(exc, p.user_id, project_id)
    return guarded


async def _authorized(project_id, p):
    from dataclasses import replace
    from core import project_visibility as pv
    from core.org_directory import org_directory
    from core.paths import workspace_path
    from core.studio_project_context import for_principal
    try:
        fresh_scope = await asyncio.to_thread(org_directory.resolve_scope, p.user_id, fresh=True)
        p = replace(p, scope=fresh_scope)
    except Exception as exc:
        raise ProcessError("CONTRACT_AUTHORITY_UNAVAILABLE", "현재 프로젝트 작업 권한을 확인하지 못했습니다.", 503) from exc
    assert_project_writable(p, project_id)
    require_caps(p, PROJECT_RUN, resource="project", action="contract_review:reconcile")
    studio = await asyncio.to_thread(for_principal, project_id, p, "GENERATE")
    own = await asyncio.to_thread(pv.read_project_ownership, workspace_path(project_id))
    if own.get("binding_state") == pv.INVALID:
        raise ProcessError("CONTRACT_PROJECT_UNAVAILABLE", "프로젝트의 고정 소유 문맥을 확인하지 못했습니다.", 503)
    return studio, {k: own[k] for k in ("tenant_id", "enterprise_scope_id", "entity_mode")}


def _checkpoint_matches(state, req, studio):
    fixed = ("runtime_document_version", "process_context", "approved_blueprint_revision_id",
             "approved_blueprint_digest", "bootstrap_operation_id")
    if (state.get("app_runtime_contract_fingerprint") != req.compiled_fingerprint
            or state.get("contract_review_request_event_id", "") not in ("", req.request_event_id)
            or (studio and any(state.get(k) != studio[k] for k in fixed))):
        raise ProcessError("CONTRACT_RECONCILE_CONFLICT", "현재 작업의 계약 또는 승인 업무 참조가 다릅니다.", 409)


@router.post("/{project_id}/contract-review/reconcile")
async def reconcile(project_id: str, req: ReconcileIn, p: Principal = Depends(current_principal)):
    from core.studio_execution_guard import finish_before_cancel
    return await finish_before_cancel(_reconcile(project_id, req, p))


async def _reconcile(project_id, req, p):
    from api.routes import factory_control as factory
    from core import studio_contract_reconcile as recovery
    from core.decision_ledger import decision_ledger
    from core.paths import workspace_path
    from core.studio_execution_guard import reconcile as reserve

    factory._safe_id(project_id, "project_id")
    factory._safe_id(req.task_id, "task_id")
    try:
        # 비가시 대상의 현재 실행/복구 상태를 먼저 노출하지 않는다.
        await _authorized(project_id, p)
        with reserve(factory.orchestrator, project_id):
            studio, boundary = await _authorized(project_id, p)
            state = await factory.orchestrator.read_reconcile_state(req.task_id, project_id)
            _checkpoint_matches(state, req, studio)
            event_args = {**req.model_dump(), "project_id": project_id, **boundary}
            event = await asyncio.to_thread(recovery.validate_approval, decision_ledger, **event_args)
            # 검증 후 권한 회수/프로젝트 문맥 변경을 쓰기 직전에 다시 검사한다.
            current_studio, current_boundary = await _authorized(project_id, p)
            if current_studio != studio or current_boundary != boundary:
                raise ProcessError("CONTRACT_RECONCILE_CONFLICT", "검사 중 프로젝트 문맥이 바뀌었습니다.", 409)
            applied, reason = False, ""
            try:
                await asyncio.to_thread(recovery.stamp_approval, workspace_path(project_id),
                                        event=event, fingerprint=req.compiled_fingerprint)
                # 새 검토 차수/무효화 사건은 옛 승인으로 재적용하지 않는다.
                await asyncio.to_thread(recovery.validate_approval, decision_ledger, **event_args)
                await _authorized(project_id, p)
                applied = await factory.orchestrator.apply_reconciled_contract_decision(
                    req.task_id, project_id, fingerprint=req.compiled_fingerprint,
                    request_event_id=req.request_event_id, expected_state=state)
                if not applied:
                    reason = "CONTRACT_CHECKPOINT_READBACK_FAILED"
            except (ProcessError, RevisionStoreError, HTTPException) as exc:
                if exc.status_code != 503:
                    raise
                reason = getattr(exc, "reason_code", "CONTRACT_RECONCILE_AUTHORITY_UNAVAILABLE")
            return {"status": "success", "data": {
                "event_id": req.event_id, "request_event_id": req.request_event_id,
                "contract_fingerprint": req.compiled_fingerprint,
                "state_applied": applied, "execution_started": False, "reason_code": reason,
                "note": ("승인 반영을 확인했습니다. 작업 재개는 별도로 요청하십시오." if applied else
                         "승인은 원장에 있습니다. 다시 승인하지 말고 같은 사건의 반영 상태를 복구하십시오.")}}
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id, project_id)
