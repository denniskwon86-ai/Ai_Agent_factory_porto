"""B5 산출물·저장 초안에 결속된 수정 요청 접수. 접수는 실행 시작이 아니다."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException

from api.deps import Principal, current_principal, require_caps, assert_project_readable
from api.routes import studio_input_draft_control as drafts
from api.routes.process_configuration_control import error
from core.admin_capability import PROJECT_RUN
from core.advisor_revision_store import RevisionStoreError
from core.enterprise_context.process_schema import ProcessError
from core.paths import workspace_path
from core import studio_revision_requests as requests

router = APIRouter()
RevisionRequestIn = requests.Submission


def _same_context(project_id, p, boundary, studio, *, write):
    current, current_studio = drafts._authorized(project_id, p, write)
    if current != boundary or current_studio != studio:
        requests.fail("CONTEXT_CONFLICT", "처리 중 프로젝트·사용자 문맥이 변경되었습니다.")


def _same_submission(receipt, command):
    if (receipt["request_id"] != command["client_request_id"] or any(
            receipt[k] != command[k] for k in ("target", "feedback", "input_draft"))):
        requests.fail("IDEMPOTENCY_CONFLICT", "같은 요청 ID의 제출 내용이 다릅니다.")


async def _existing(project_id, p, boundary, command):
    receipt = await asyncio.to_thread(requests.read_receipt, workspace_path(project_id),
        project_id=project_id, actor_id=p.user_id, boundary=boundary,
        client_request_id=command["client_request_id"], allow_missing=True)
    if receipt:
        _same_submission(receipt, command)
    return receipt


def _visible_before_reservation(project_id, p):
    # AdvisorStore에 진입하지 않는 기존 조직/프로젝트 가시성 검사다.
    # 비가시 프로젝트에 BUSY를 반환해 존재·처리 상태를 알리지 않는다.
    from api.routes import factory_control as factory
    from core.org_directory import org_directory
    factory._safe_id(project_id, 'project_id')
    if not p.user_id:
        raise HTTPException(401, '로그인한 사용자만 요청할 수 있습니다.')
    p = replace(p, scope=org_directory.resolve_scope(p.user_id, fresh=True))
    try:
        assert_project_readable(p, project_id)
    except HTTPException as exc:
        if exc.status_code == 403:
            requests.fail('NOT_FOUND', '현재 문맥에서 프로젝트를 찾을 수 없습니다.', 404)
        raise


async def _submit(project_id, req, p):
    from api.routes import factory_control as factory
    from core.studio_execution_guard import command as reserve
    await asyncio.to_thread(_visible_before_reservation, project_id, p)
    # 초안 저장소 락을 기다리기 전부터 전체 요청을 예약한다. 순간 검사만 하면
    # 동시 두 요청이 검사 직후 같은 저장소 락을 기다리는 틈이 남는다.
    with reserve(factory.orchestrator, project_id, exclusive=True):
        return await _submit_reserved(project_id, req, p)


async def _submit_reserved(project_id, req, p):
    from api.routes import factory_control as factory
    from core.studio_execution_guard import command as reserve
    command = req.model_dump()
    boundary, studio = await asyncio.to_thread(drafts._authorized, project_id, p, True)
    # 재전송은 이미 소비한 초안·새 산출물·현재 실행 상태 때문에 새 접수로 바뀌지 않는다.
    previous = await _existing(project_id, p, boundary, command)
    if previous:
        await asyncio.to_thread(_same_context, project_id, p, boundary, studio, write=True)
        return previous
    with reserve(factory.orchestrator, project_id, quiescent=True):
        await asyncio.to_thread(_same_context, project_id, p, boundary, studio, write=True)
        previous = await _existing(project_id, p, boundary, command)
        if previous:
            await asyncio.to_thread(_same_context, project_id, p, boundary, studio, write=True)
            return previous
        await drafts._current(project_id, command["target"], studio)
        state = await drafts._state(project_id, command["target"]["task_id"], studio)
        storage = drafts._storage()

        @contextmanager
        def before_write(replay):
            # AdvisorStore 비재진입 락을 잡기 전에 현재 PDP/프로젝트 권한을 검사한다.
            _same_context(project_id, p, boundary, studio, write=True)
            if replay:
                yield
                return
            with storage.transaction() as conn:
                row = storage._get(conn, storage._key(boundary, p.user_id, project_id), command["input_draft"]["draft_id"])
                requests.verify_input_draft(row, command)
                if drafts._artifact_digest(project_id, state) != command["target"]["target_digest"]:
                    requests.fail("TARGET_CONFLICT", "접수 직전 산출물 원문이 바뀌었습니다. 기존 입력을 보존하십시오.")
                # 같은 프로세스의 초안 수정/폐기는 이 읽기 락 해제 뒤 진행된다.
                yield

        return await asyncio.to_thread(requests.accept_request, workspace_path(project_id),
            project_id=project_id, actor_id=p.user_id, boundary=boundary, submission=command, before_write=before_write)


@router.post("/{project_id}/sprint/revision-requests")
async def submit(project_id: str, req: RevisionRequestIn, p: Principal = Depends(current_principal)):
    from core.studio_execution_guard import finish_before_cancel
    require_caps(p, PROJECT_RUN, resource="project", action="revision_requests:submit")
    try:
        result = await finish_before_cancel(_submit(project_id, req, p))
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id, project_id)
    except Exception as exc:
        raise HTTPException(503, detail={"reason_code": "REVISION_REQUEST_UNAVAILABLE",
            "message": "접수 결과를 확정하지 못했습니다. 입력과 요청 ID를 보존하고 영수증을 조회하십시오."}) from exc


@router.get("/{project_id}/sprint/revision-requests/{client_request_id}")
async def get(project_id: str, client_request_id: str, p: Principal = Depends(current_principal)):
    try:
        boundary, studio = await asyncio.to_thread(drafts._authorized, project_id, p, False)
        result = await asyncio.to_thread(requests.read_receipt, workspace_path(project_id), project_id=project_id,
            actor_id=p.user_id, boundary=boundary, client_request_id=client_request_id)
        await asyncio.to_thread(_same_context, project_id, p, boundary, studio, write=False)
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id, project_id)
    except Exception as exc:
        raise HTTPException(503, detail={"reason_code": "REVISION_REQUEST_UNAVAILABLE",
            "message": "고정 접수 기록을 확인하지 못했습니다. 요청 ID를 보존하십시오."}) from exc
