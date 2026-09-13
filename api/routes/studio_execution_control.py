"""B5 영속 실행 명령 접수. 접수 확인은 작업 완료/승인을 뜻하지 않는다."""
import asyncio
from contextvars import ContextVar
from functools import wraps
from inspect import signature
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator

from api.deps import Principal, current_principal, require_caps
from api.routes import studio_input_draft_control as drafts
from api.routes.process_configuration_control import error
from api.routes.studio_revision_control import _visible_before_reservation, _same_context
from core.admin_capability import PROJECT_RUN
from core.advisor_revision_store import RevisionStoreError
from core.enterprise_context.process_schema import ProcessError, StrictModel
from core.studio_execution_commands import CommandStore, _request, fail
from core.studio_execution_guard import command as reserve, owns_execution_command, finish_before_cancel

router = APIRouter()
_dispatch = ContextVar("studio_command_dispatch", default=None)


class CommandIn(StrictModel):
    client_request_id: str = Field(min_length=36, max_length=36)
    operation: Literal["START", "RESUME", "RESUME_QUOTA", "PAUSE", "STOP", "HEAL"]
    task_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,160}$")
    input: dict[str, str]

    @model_validator(mode="after")
    def closed_input(self):
        try:
            command = _request(self.model_dump())
            allowed = {"START": {"initial_idea", "master_data", "feedback"}, "HEAL": {"error_log"}}
            if set(self.input) - allowed.get(self.operation, set()):
                raise ValueError("이 명령에 허용되지 않는 입력입니다.")
            if self.operation == "HEAL" and not self.input.get("error_log", "").strip():
                raise ValueError("복구할 오류 근거가 필요합니다.")
            if self.operation == "START" and self.task_id.startswith("PLANNING"):
                if len(self.task_id.split("_")) != 2 or not self.input.get("initial_idea", "").strip():
                    raise ValueError("새 기획 ID와 아이디어가 필요합니다.")
            self.client_request_id = command["client_request_id"]
        except ProcessError as exc:
            raise ValueError(str(exc)) from exc
        return self


def _storage():
    from core.advisor_store import advisor_store
    return CommandStore(advisor_store)


def dispatch_context():
    value = _dispatch.get()
    return value if value and value["task"] is asyncio.current_task() else None


def mark_effect_started():
    context = dispatch_context()
    if context:
        context["effect_started"] = True


def execution_route(*, quiescent=False):
    """레거시 호출도 설정/WBS 변경 전부터 예약한다. 새 명령의 소유 호출만 재진입."""
    def decorate(fn):
        sig = signature(fn)
        @wraps(fn)
        async def guarded(*args, **kwargs):
            from api.routes import factory_control as factory
            values = sig.bind(*args, **kwargs).arguments
            project_id, p = values["project_id"], values.get("p")
            if owns_execution_command(factory.orchestrator, project_id):
                return await fn(*args, **kwargs)
            async def run():
                await asyncio.to_thread(_visible_before_reservation, project_id, p)
                with reserve(factory.orchestrator, project_id, exclusive=True, quiescent=quiescent, allow_nested_execution=True):
                    if quiescent:
                        await asyncio.to_thread(drafts._authorized, project_id, p, True)
                        await asyncio.to_thread(_storage().assert_execution_clear, project_id)
                    return await fn(*args, **kwargs)
            try:
                return await finish_before_cancel(run())
            except ProcessError as exc:
                error(exc, getattr(p, "user_id", ""), project_id)
        return guarded
    return decorate


async def _run(project_id, command, p):
    from api.routes import factory_control as factory
    operation, task_id, content = command["operation"], command["task_id"], command["input"]
    if operation == "START":
        payload = dict(project_name=project_id, current_sprint_task_id=task_id,
            factory_mode="PLANNING" if task_id.startswith("PLANNING") else "REVISION" if task_id.startswith("TASK_REV_") else "EXECUTION")
        payload.update({k: v for k, v in content.items() if k in {"initial_idea", "master_data"}})
        feedback = content.get("feedback", "").strip()
        if feedback:
            payload.update(reviewer_decision="REWORK_DEV", reviewer_feedback="[사용자 재시도 지시]\n" + feedback,
                human_feedback_queue=[dict(task_id=task_id, feedback=feedback)])
        return await factory.start_sprint(project_id, factory.SprintStartRequest(task_id=task_id, project_state_payload=payload), p)
    req = factory.SprintPauseRequest(task_id=task_id)
    if operation == "PAUSE":
        return await factory.pause_sprint(project_id, req, p)
    if operation == "STOP":
        return await factory.stop_sprint(project_id, req, p)
    if operation == "RESUME_QUOTA":
        return await factory.resume_from_quota(project_id, req, p)
    if operation == "RESUME":
        await factory._assert_resumable(project_id, p, task_id)
        if not await factory.orchestrator.resume_existing(task_id, project_id):
            fail("NOT_RESUMABLE", "같은 작업의 수동 중지 체크포인트를 확인하지 못했습니다. 새 기획으로 대체하지 않습니다.")
        mark_effect_started()
        return dict(status="resumed", task_id=task_id)
    return await factory.trigger_self_healing(project_id, factory.HealRequest(error_log=content["error_log"]), p)


async def _submit(project_id, req, p):
    from api.routes import factory_control as factory
    await asyncio.to_thread(_visible_before_reservation, project_id, p)
    # 소유권은 shield가 만든 실제 worker에서 획득한다.
    with reserve(factory.orchestrator, project_id, exclusive=True, allow_nested_execution=True):
        boundary, studio = await asyncio.to_thread(drafts._authorized, project_id, p, True)
        storage, command = _storage(), req.model_dump()
        identity = dict(project_id=project_id, actor_id=p.user_id, boundary=boundary)
        try:
            previous = await asyncio.to_thread(storage.get, **identity, request_id=command["client_request_id"])
        except ProcessError as exc:
            if exc.reason_code != "STUDIO_COMMAND_NOT_FOUND":
                raise
        else:
            if any(previous[k] != command[k] for k in ("operation", "task_id", "input")):
                fail("IDEMPOTENCY_CONFLICT", "같은 요청 ID의 명령 내용이 다릅니다.")
            await asyncio.to_thread(_same_context, project_id, p, boundary, studio, write=True)
            return previous
        with reserve(factory.orchestrator, project_id, quiescent=command["operation"] not in {"PAUSE", "STOP"}):
            await asyncio.to_thread(_same_context, project_id, p, boundary, studio, write=True)
            receipt, created = await asyncio.to_thread(storage.begin, **identity, request=command)
            if not created:
                return receipt
            context = dict(task=asyncio.current_task(), command=command, effect_started=False)
            token = _dispatch.set(context)
            try:
                await asyncio.to_thread(_same_context, project_id, p, boundary, studio, write=True)
                response = await _run(project_id, command, p)
                outcome, result = "ACCEPTED", dict(http_status=200, response=response)
            except (HTTPException, ProcessError) as exc:
                status = exc.status_code
                detail = exc.detail if isinstance(exc, HTTPException) else dict(reason_code=exc.reason_code, message=str(exc))
                outcome = "REJECTED" if 400 <= status < 500 and not context["effect_started"] else "UNKNOWN"
                result = dict(http_status=status, response=dict(detail=detail))
            except Exception:
                outcome, result = "UNKNOWN", dict(http_status=503, response=dict(detail={
                    "reason_code": "STUDIO_COMMAND_RESULT_UNKNOWN",
                    "message": "처리 결과를 확정하지 못했습니다. 원래 요청을 조회하십시오."}))
            finally:
                _dispatch.reset(token)
            receipt = await asyncio.to_thread(storage.finish, **identity, request_id=command["client_request_id"], outcome=outcome, result=result)
            try:
                await asyncio.to_thread(_same_context, project_id, p, boundary, studio, write=True)
            except Exception as exc:
                # 실행 뒤 권한 변경은 클라이언트가 '미접수 4xx'로 오해하면 안 된다.
                raise HTTPException(503, detail={"reason_code": "STUDIO_COMMAND_CONTEXT_CHANGED",
                    "message": "처리 뒤 현재 공개 권한을 확인하지 못했습니다. 원요청 ID로 다시 조회하세요."}) from exc
            return receipt


@router.post("/{project_id}/execution-commands")
async def submit(project_id: str, req: CommandIn, p: Principal = Depends(current_principal)):
    require_caps(p, PROJECT_RUN, resource="project", action="execution_commands:submit")
    try:
        return {"request": await finish_before_cancel(_submit(project_id, req, p))}
    except HTTPException:
        raise
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id, project_id)
    except Exception as exc:
        raise HTTPException(503, detail={"reason_code": "STUDIO_COMMAND_UNAVAILABLE",
            "message": "접수 결과를 확정하지 못했습니다. 원래 요청 ID를 보존하고 조회하세요."}) from exc


async def _read(project_id, p, request_id=None):
    boundary, studio = await asyncio.to_thread(drafts._authorized, project_id, p, False)
    identity = dict(project_id=project_id, actor_id=p.user_id, boundary=boundary)
    result = await asyncio.to_thread(_storage().get, **identity, request_id=request_id) if request_id else await asyncio.to_thread(_storage().list, **identity)
    await asyncio.to_thread(_same_context, project_id, p, boundary, studio, write=False)
    return result


@router.get("/{project_id}/execution-commands")
async def list_commands(project_id: str, p: Principal = Depends(current_principal)):
    try:
        return {"requests": await _read(project_id, p)}
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id, project_id)


@router.get("/{project_id}/execution-commands/{request_id}")
async def get_command(project_id: str, request_id: str, p: Principal = Depends(current_principal)):
    try:
        return {"request": await _read(project_id, p, request_id)}
    except (ProcessError, RevisionStoreError) as exc:
        error(exc, p.user_id, project_id)
