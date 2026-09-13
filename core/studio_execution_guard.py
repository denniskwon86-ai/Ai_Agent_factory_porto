"""한 실행 프로세스 안에서 계약 복구와 작업 시작/재개를 겹치지 않는다.

원장/파일/체크포인트의 분산 잠금은 아니다. 실행 명령의 await 구간도 예약에
포함해 '아직 active_tasks에 없어서 복구가 시작되는' 틈을 막는다.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import signature
import asyncio

from core.enterprise_context.process_schema import ProcessError

_owner = ContextVar('studio_execution_owner', default=None)


def owns_execution_command(orchestrator, project_id):
    try:
        task = asyncio.current_task()
    except RuntimeError:
        return False
    value = _owner.get()
    return bool(value and value[0] is orchestrator and value[1] == project_id
                and value[2] is task and task is not None and _state(orchestrator)[0].get(project_id))


def _state(orchestrator):
    if not hasattr(orchestrator, "_studio_commands"):
        orchestrator._studio_commands = {}
        orchestrator._studio_reconciling = set()
    return orchestrator._studio_commands, orchestrator._studio_reconciling


@contextmanager
def command(orchestrator, project_id, *, exclusive=False, quiescent=False, allow_nested_execution=False):
    commands, recovering = _state(orchestrator)
    if project_id in recovering:
        raise ProcessError("CONTRACT_RECONCILE_BUSY", "계약 승인 반영을 복구하고 있습니다. 완료 후 다시 시도하십시오.", 409)
    running = quiescent and any(not task.done() and (
        orchestrator.task_projects.get(key) == project_id or key.startswith(project_id + "__"))
        for key, task in orchestrator.active_tasks.items())
    if (exclusive and commands.get(project_id)) or running:
        raise ProcessError("STUDIO_COMMAND_BUSY", "같은 프로젝트의 처리가 진행 중입니다. 완료 후 다시 시도하십시오.", 409)
    owner_task = asyncio.current_task() if allow_nested_execution else None
    commands[project_id] = commands.get(project_id, 0) + 1
    token = _owner.set((orchestrator, project_id, owner_task)) if allow_nested_execution else None
    try:
        yield
    finally:
        if token is not None:
            _owner.reset(token)
        remaining = commands[project_id] - 1
        if remaining:
            commands[project_id] = remaining
        else:
            commands.pop(project_id, None)


@contextmanager
def reconcile(orchestrator, project_id):
    commands, recovering = _state(orchestrator)
    running = any(not task.done() and (orchestrator.task_projects.get(key) == project_id
                  or key.startswith(project_id + "__"))
                  for key, task in orchestrator.active_tasks.items())
    if project_id in recovering or commands.get(project_id) or running:
        raise ProcessError("CONTRACT_RECONCILE_BUSY", "진행 중인 작업 또는 계약 반영이 있습니다. 정지 확인 후 복구하십시오.", 409)
    recovering.add(project_id)
    try:
        yield
    finally:
        recovering.discard(project_id)


def is_reconciling(orchestrator, project_id):
    return project_id in _state(orchestrator)[1]


async def finish_before_cancel(awaitable):
    """요청 취소가 파일 worker보다 먼저 예약을 해제하지 못하게 한다.

    worker는 취소하지 않고 끝까지 회수한다. 호출자는 완료 후 원래 취소를 받으며
    성공 응답이나 자동 재시작으로 바꾸지 않는다. 반복 cancel도 같은 작업을 기다린다.
    """
    task = asyncio.ensure_future(awaitable)
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
        except BaseException:
            if cancelled:
                raise asyncio.CancelledError() from None
            raise
    if cancelled:
        raise asyncio.CancelledError()
    return result


def execution_command(project_argument):
    """기존 실행 서비스의 bool 반환 계약을 유지하는 명령 예약 장식자."""
    def decorate(fn):
        sig = signature(fn)
        @wraps(fn)
        async def guarded(self, *args, **kwargs):
            values = sig.bind(self, *args, **kwargs).arguments
            project_id = values[project_argument]
            if project_argument == "workspace_root":
                from core.async_orchestrator import _pid
                project_id = _pid(project_id)
            # 같은 HTTP 명령의 호출 스택만 재진입한다. context를 상속한 자식 task는 소유자가 아니다.
            if owns_execution_command(self, project_id):
                return await fn(self, *args, **kwargs)
            if is_reconciling(self, project_id) or _state(self)[0].get(project_id):
                return False
            with command(self, project_id):
                return await fn(self, *args, **kwargs)
        return guarded
    return decorate
