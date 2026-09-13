"""B5 개인 입력 초안 HTTP. 현재 실제 차수를 읽고 별도 저장한다."""
import asyncio
from dataclasses import replace
import hashlib
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from pydantic import ValidationError

from api.deps import (Principal, current_principal, assert_project_readable,
                      assert_project_writable, viewing_context, require_caps)
from api.routes.process_configuration_control import error
from core.advisor_revision_store import RevisionStoreError
from core.admin_capability import PROJECT_RUN
from core.enterprise_context.process_schema import StrictModel, ProcessError
from core.studio_input_drafts import (Target, Content, InputDraftStore, fail, digest,
                                     verify_decision_submission, validate_selections)

router = APIRouter()


class SaveIn(StrictModel):
    target: Target
    content: Content
    draft_id: str = Field(default="", max_length=128)
    expected_revision: int = Field(ge=0)
    expected_digest: str = Field(pattern=r"^([0-9a-f]{64})?$")
    client_request_id: str = Field(min_length=1, max_length=160)


class ChangeIn(StrictModel):
    expected_revision: int = Field(ge=1)
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    client_request_id: str = Field(min_length=1, max_length=160)


class ConsumeIn(ChangeIn):
    submission_id: str = Field(min_length=1, max_length=200)


def _storage():
    from core.advisor_store import advisor_store
    return InputDraftStore(advisor_store)


def _authorized(project_id, p, write=False):
    from api.routes import factory_control as factory
    from core.org_directory import org_directory
    from core import project_visibility as pv
    from core.studio_project_context import for_principal
    from core.paths import workspace_path
    factory._safe_id(project_id, "project_id")
    if not p.user_id:
        raise HTTPException(401, "초안은 로그인한 사용자만 사용할 수 있습니다.")
    try:
        p = replace(p, scope=org_directory.resolve_scope(p.user_id, fresh=True))
    except Exception as exc:
        raise ProcessError("INPUT_DRAFT_AUTHORITY_UNAVAILABLE", "현재 사용자 권한을 확인하지 못했습니다.", 503) from exc
    try:
        assert_project_readable(p, project_id)
    except HTTPException as exc:
        if exc.status_code == 403:
            fail("NOT_FOUND", "현재 문맥에서 프로젝트를 찾을 수 없습니다.", 404)
        raise
    if write:
        assert_project_writable(p, project_id)
        require_caps(p, PROJECT_RUN, resource="project", action="input_drafts:write")
    # 일반 프로젝트 READ는 실행/승인 권한으로 격상하지 않는다.
    studio = for_principal(project_id, p, "DRAFT" if write else "READ")
    own = pv.read_project_ownership(workspace_path(project_id))
    if own.get("binding_state") == pv.INVALID:
        fail("PROJECT_UNAVAILABLE", "프로젝트 서버 소속을 확인할 수 없습니다.", 503)
    view = viewing_context(p)
    visible, reason = pv.context_visible(view, own)
    if not visible:
        if reason == pv.CTX_LOOKUP_FAILED:
            fail("CONTEXT_UNAVAILABLE", "프로젝트 문맥을 확인하지 못했습니다.", 503)
        fail("NOT_FOUND", "현재 문맥에서 프로젝트를 찾을 수 없습니다.", 404)
    owner = {k: own[k] for k in ("tenant_id", "enterprise_scope_id", "entity_mode")}
    return dict(ownership=owner, viewing_context=view,
                process_context=studio.get("process_context", {}) if studio else {}), studio


async def _state(project_id, task_id, studio):
    from api.routes import factory_control as factory
    from core.paths import workspace_path
    factory._safe_id(task_id, "task_id")
    state = await factory.orchestrator.read_reconcile_state(task_id, project_id)
    if (not isinstance(state, dict) or not state.get("workspace_root")
            or Path(state["workspace_root"]).resolve() != Path(workspace_path(project_id)).resolve()
            or state.get("current_sprint_task_id", "") not in ((task_id, "") if task_id == "sprint_init" else (task_id,))):
        fail("TARGET_CONFLICT", "실제 작업의 프로젝트·task 결속을 확인하십시오.")
    if studio and any(state.get(k) != studio.get(k) for k in (
            "runtime_document_version", "process_context", "approved_blueprint_revision_id",
            "approved_blueprint_digest", "bootstrap_operation_id")):
        fail("TARGET_CONFLICT", "작업의 고정 업무 문맥이 바뀌었습니다.")
    return state


def _artifact_digest(project_id, state):
    """현재 결과 원문을 해시한다. 과거 manifest hash를 실제 원문으로 간주하지 않는다."""
    from core.paths import workspace_path
    root = Path(workspace_path(project_id))
    if root.is_symlink() or getattr(root, "is_junction", lambda: False)():
        fail("ARTIFACT_UNAVAILABLE", "연결 경로의 결과를 읽을 수 없습니다.", 503)
    root = root.resolve()
    material = {key: state[key] for key in (
        "artifacts", "artifact_summaries", "rfp_summary", "prd_summary", "architecture_summary",
        "tech_spec_summary", "code_review_report_summary", "qa_report_summary", "supervisor_report_summary")
        if state.get(key)}
    index = state.get("file_index", {})
    if not isinstance(index, dict) or len(index) > 2000:
        fail("ARTIFACT_UNAVAILABLE", "현재 결과 목록을 확인하지 못했습니다.", 503)
    files, total = {}, 0
    for key, item in sorted(index.items()):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            fail("ARTIFACT_UNAVAILABLE", "결과 경로가 손상됐습니다.", 503)
        relative = Path(item["path"])
        path = relative if relative.is_absolute() else root / relative
        if not path.resolve().is_relative_to(root):
            fail("ARTIFACT_UNAVAILABLE", "프로젝트 외부의 결과는 읽을 수 없습니다.", 503)
        for part in (path, *path.parents):
            if part == root:
                break
            if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
                fail("ARTIFACT_UNAVAILABLE", "연결된 결과 경로는 사용할 수 없습니다.", 503)
        try:
            before = path.stat()
            if before.st_size > 16 * 1024 * 1024:
                raise ValueError("size")
            with path.open("rb") as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
            after = path.stat()
            total += len(raw)
            stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
            if any(getattr(before, k) != getattr(after, k) for k in stable) or len(raw) != before.st_size or total > 64 * 1024 * 1024:
                raise ValueError("changed")
            files[key] = hashlib.sha256(raw).hexdigest()
        except (OSError, ValueError) as exc:
            raise ProcessError("INPUT_DRAFT_ARTIFACT_UNAVAILABLE", "현재 결과 원문을 확인하지 못했습니다.", 503) from exc
    if files:
        material["files"] = files
    if not material:
        fail("ARTIFACT_REQUIRED", "수정 의견을 연결할 현재 결과가 없습니다.")
    return digest(material)


async def _target(project_id, *, kind, task_id, decision_kind="", request_id="", subject_id="", studio=None):
    from api.routes import factory_control as factory
    from core.paths import workspace_path
    # 능력/데이터셋 선택은 실제 WBS+초안 판 reader가 대상을 증명한다.
    # 아직 실행 전인 task에 체크포인트 생성을 요구하지 않는다.
    state = (await _state(project_id, task_id, studio)
             if decision_kind not in {"CAPABILITY", "DATASET"} else None)
    value = dict(kind=kind, task_id=task_id, decision_kind=decision_kind, subject_id=subject_id)
    if kind == "REVISION_REQUEST":
        fp = await asyncio.to_thread(_artifact_digest, project_id, state)
        value.update(request_id="artifact_" + fp, target_digest=fp)
    elif kind == "CLARIFICATION" or decision_kind == "GENERAL_HOTL":
        current = await factory.orchestrator.read_hotl_context(task_id, project_id)
        if current.get("status") == "UNKNOWN":
            fail("TARGET_UNAVAILABLE", "현재 질문 차수를 확인하지 못했습니다.", 503)
        expected = "CLARIFICATION" if kind == "CLARIFICATION" else "GENERAL_HOTL"
        if not current.get("available") or current.get("decision_kind") != expected:
            fail("TARGET_CONFLICT", "현재 질문 또는 결정 대기 차수가 다릅니다.")
        value.update(request_id=current["request_id"], target_digest=current["questions_digest"])
    elif decision_kind == "HOST_CONTRACT":
        from core import contract_review_gate as gate
        from core.decision_ledger import decision_ledger
        decision, _ = await factory._contract_review_context(project_id, task_id, strict=True)
        if decision.verdict != gate.REVIEW_REQUIRED:
            fail("TARGET_CONFLICT", "현재 계약 검토 대기가 아닙니다.")
        def current_request():
            with decision_ledger.transaction() as txn:
                return gate._open_request(txn, project_id, decision.compiled_fingerprint)
        pending = await asyncio.to_thread(current_request)
        if not pending:
            fail("TARGET_CONFLICT", "현재 계약 검토 요청이 아직 열리지 않았습니다.")
        from core.project_visibility import read_project_ownership
        owner = await asyncio.to_thread(read_project_ownership, workspace_path(project_id))
        if (any(pending.get(k) != owner.get(k) for k in ("tenant_id", "enterprise_scope_id", "entity_mode"))
                or pending.get("event_id") != state.get("contract_review_request_event_id")
                or not any(isinstance(ref, dict) and task_id in ref.get("task_ids", [])
                           for ref in pending.get("evidence_refs", []))):
            fail("TARGET_CONFLICT", "실제 task에 결속된 계약 요청이 아닙니다.")
        value.update(request_id=pending["event_id"], target_digest=decision.compiled_fingerprint)
    elif decision_kind in {"CAPABILITY", "DATASET"}:
        from core import contract_decision
        try:
            pending = await asyncio.to_thread(contract_decision.pending_for_workspace,
                                             workspace_path(project_id), require_metadata=bool(studio))
        except contract_decision.DecisionRoundError as exc:
            raise ProcessError(exc.reason_code, str(exc), exc.status_code) from exc
        group = "capability_decisions" if decision_kind == "CAPABILITY" else "dataset_conflicts"
        choices = [item for item in pending[group] if item.get("decision_request_id") == request_id
                   and item.get("capability" if decision_kind == "CAPABILITY" else "dataset_key") == subject_id
                   and (item.get("task_id") == task_id if decision_kind == "CAPABILITY" else task_id in item.get("tasks", []))]
        if len(choices) != 1 or not choices[0].get("expected_digest"):
            fail("TARGET_CONFLICT", "현재 결정 대상·차수를 다시 확인하십시오.")
        value.update(request_id=request_id, target_digest=choices[0]["expected_digest"])
    else:
        fail("INVALID", "지원하지 않는 입력 대상입니다.", 422)
    return Target.model_validate(value).model_dump()


async def _current(project_id, target, studio):
    actual = await _target(project_id, **{k: v for k, v in target.items() if k != "target_digest"}, studio=studio)
    if actual != target:
        fail("TARGET_CONFLICT", "현재 대상·차수가 달라 과거 입력을 복원하지 않습니다.")


async def _receipt(row, submission_id, *, expected_revision=None, expected_digest=None):
    if row["target"]["kind"] == "REVISION_REQUEST":
        from core import studio_revision_requests as requests
        from core.paths import workspace_path
        receipt = await asyncio.to_thread(requests.read_receipt, workspace_path(row["project_id"]),
            project_id=row["project_id"], actor_id=row["actor"], boundary=row["context_key"], submission_id=submission_id)
        return requests.verify_consumption(row, receipt, expected_revision=expected_revision, expected_digest=expected_digest)
    from core.decision_ledger import decision_ledger
    if row["target"]["kind"] != "DECISION_COMMENT" or row["target"]["decision_kind"] == "GENERAL_HOTL":
        fail("CONSUME_UNSUPPORTED", "현재 제출 API에 입력·차수 결속 증거가 없습니다. 초안을 보존합니다.")
    event = await asyncio.to_thread(decision_ledger.get_event_strict, submission_id)
    parent = (await asyncio.to_thread(decision_ledger.get_event_strict, row["target"]["request_id"])
              if row["target"]["decision_kind"] == "HOST_CONTRACT" else None)
    return verify_decision_submission(row, event, parent)


async def _run(project_id, p, operation, req=None, draft_id="", selector=None):
    from core.studio_execution_guard import finish_before_cancel
    async def action():
        try:
            write = operation in {"SAVE", "DISCARD", "CONSUME"}
            boundary, studio = await asyncio.to_thread(_authorized, project_id, p, write)
            store = _storage()
            args = dict(boundary=boundary, actor=p.user_id, project_id=project_id)
            if operation == "TARGET":
                target = await _target(project_id, **selector, studio=studio)
                row = await asyncio.to_thread(store.active, **args, target=target)
                result = dict(target=target, draft=store.public(row) if row else None,
                              consume_supported=(target["kind"] == "REVISION_REQUEST" or
                                  target["decision_kind"] in {"HOST_CONTRACT", "CAPABILITY", "DATASET"}))
            elif operation == "SAVE":
                fields = req.model_dump()
                await _current(project_id, fields["target"], studio)
                result = None
            else:
                row = await asyncio.to_thread(store.get, **args, draft_id=draft_id)
                if operation == "GET":
                    await _current(project_id, row["target"], studio)
                    result = store.public(row)
                elif operation == "DISCARD":
                    # 명시 폐기는 과거 차수도 허용한다. 본문 복원/복사는 하지 않는다.
                    fields = dict(req.model_dump(), draft_id=draft_id)
                    result = None
                else:
                    verified = await _receipt(row, req.submission_id,
                        expected_revision=req.expected_revision, expected_digest=req.expected_digest)
                    fields = dict(req.model_dump(), draft_id=draft_id, verified=verified)
                    result = None
            current_boundary, current_studio = await asyncio.to_thread(_authorized, project_id, p, write)
            if current_boundary != boundary or current_studio != studio:
                fail("CONTEXT_CONFLICT", "조회 중 회사·프로젝트 문맥이 바뀌었습니다.")
            if write:
                if operation == "SAVE":
                    await _current(project_id, fields["target"], studio)
                    if fields["target"]["kind"] == "CLARIFICATION":
                        current_state = await _state(project_id, fields["target"]["task_id"], studio)
                        validate_selections(fields["target"], fields["content"], current_state.get("clarification_questions"))
                def commit():
                    # 마지막 원문/질문 조회 뒤 현재 권한을 다시 확인한 같은 worker에서 쓴다.
                    # AdvisorStore 락 안에서 권한 reader를 호출하면 재진입 교착이 발생한다.
                    final_boundary, final_studio = _authorized(project_id, p, True)
                    if final_boundary != boundary or final_studio != studio:
                        fail("CONTEXT_CONFLICT", "저장 직전 프로젝트 문맥이 바뀌었습니다.")
                    return store.mutate(**args, operation=operation, **fields)
                result = await asyncio.to_thread(commit)
            elif operation == "TARGET":
                await _current(project_id, target, studio)
            elif operation == "GET":
                await _current(project_id, row["target"], studio)
            return {"status": "success", "data": result}
        except HTTPException:
            raise
        except (ProcessError, RevisionStoreError) as exc:
            error(exc, p.user_id, project_id)
        except ValidationError as exc:
            raise HTTPException(422, detail={"reason_code": "INPUT_DRAFT_INVALID", "message": "입력 대상과 내용을 확인하십시오."}) from exc
        except Exception as exc:
            raise HTTPException(503, detail={"reason_code": "INPUT_DRAFT_UNAVAILABLE",
                                "message": "입력 상태를 확인하지 못했습니다. 초안을 보존하십시오."}) from exc
    return await finish_before_cancel(action()) if operation in {"SAVE", "DISCARD", "CONSUME"} else await action()


@router.get("/{project_id}/input-drafts/target")
async def get_target(project_id: str, kind: Literal["CLARIFICATION", "DECISION_COMMENT", "REVISION_REQUEST"],
                     task_id: str, decision_kind: Literal["", "GENERAL_HOTL", "HOST_CONTRACT", "CAPABILITY", "DATASET"] = "",
                     request_id: str = "", subject_id: str = "", p: Principal = Depends(current_principal)):
    return await _run(project_id, p, "TARGET", selector=dict(kind=kind, task_id=task_id,
                     decision_kind=decision_kind, request_id=request_id, subject_id=subject_id))


@router.post("/{project_id}/input-drafts")
async def save(project_id: str, req: SaveIn, p: Principal = Depends(current_principal)):
    require_caps(p, PROJECT_RUN, resource="project", action="input_drafts:save")
    return await _run(project_id, p, "SAVE", req)


@router.get("/{project_id}/input-drafts/{draft_id}")
async def get(project_id: str, draft_id: str, p: Principal = Depends(current_principal)):
    return await _run(project_id, p, "GET", draft_id=draft_id)


@router.post("/{project_id}/input-drafts/{draft_id}/discard")
async def discard(project_id: str, draft_id: str, req: ChangeIn, p: Principal = Depends(current_principal)):
    require_caps(p, PROJECT_RUN, resource="project", action="input_drafts:discard")
    return await _run(project_id, p, "DISCARD", req, draft_id)


@router.post("/{project_id}/input-drafts/{draft_id}/consume")
async def consume(project_id: str, draft_id: str, req: ConsumeIn, p: Principal = Depends(current_principal)):
    require_caps(p, PROJECT_RUN, resource="project", action="input_drafts:consume")
    return await _run(project_id, p, "CONSUME", req, draft_id)
