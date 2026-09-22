"""B3 승인 Blueprint → 프로젝트 승격 saga. 실행/배포는 수행하지 않는다."""
import json
from pathlib import Path

from core.advisor_revision_store import RevisionStoreError
from core.enterprise_context.process_schema import ProcessError
from core.studio_drafts import StudioDraftService, context_key
from core.studio_project_files import (STUDIO_FIELDS, operation_lock, projection,
                                      read_json, read_json_with_digest, verify_files,
                                      write_json)


def fixed_project_fields(approved, operation):
    key = operation["context_key"]
    return {"runtime_document_version": "2.0", "process_context": approved["process_ref"],
            "approved_blueprint_revision_id": approved["revision_id"],
            "approved_blueprint_digest": approved["digest"],
            "bootstrap_operation_id": operation["operation_id"],
            "context_root_id": key["context_root_id"], "setup_status": "SETUP_INCOMPLETE",
            "tenant_id": key["tenant_id"], "enterprise_scope_id": key["scope_node_id"] or key["context_root_id"],
            "entity_mode": key["entity_mode"], "blueprint_id": approved["draft_id"],
            "owner_user_id": approved["author_actor"]}


class StudioBootstrapService:
    def __init__(self, *, drafts=None, ledger=None, provision=None):
        self.drafts = drafts or StudioDraftService()
        self.revisions = self.drafts.revisions
        if ledger is None:
            from core.decision_ledger import decision_ledger
            ledger = decision_ledger
        if provision is None:
            from api.routes.factory_control import provision_project
            provision = provision_project
        self.ledger, self.provision = ledger, provision

    def _advance(self, operation, stage, **result):
        return self.revisions.advance(operation_id=operation["operation_id"],
            boundary=operation["context_key"], actor=operation["actor"], current_stage=operation["stage"],
            next_stage=stage, expected_version=operation["version"], result=result)

    def get(self, *, boundary, actor, context, operation_id):
        self.drafts.authorize(boundary, actor, context, "READ")
        return self.revisions.get(boundary=context_key(boundary), actor=actor, operation_id=operation_id)

    @staticmethod
    def _ledger_payload(approved, operation, template_id):
        key = operation["context_key"]
        return dict(event_type="PROJECT_BOOTSTRAPPED", subject_type="project", subject_id=operation["project_id"],
            actor_type="user", actor_id=operation["actor"], decision="승인된 Blueprint 판본으로 프로젝트 준비 완료",
            rationale="업무 참조 고정 및 프로젝트 저장 상태 확인. 생성·실행·배포 승인을 대체하지 않음.",
            evidence_refs=[{"kind": "approved_blueprint_revision", "revision_id": approved["revision_id"],
                            "digest": approved["digest"], "decision_actor": approved["decision_actor"]}],
            input_version_refs=[{"kind": "process_context", "profile_id": approved["process_ref"]["profile_id"],
                                 "context_key": dict(key),
                                 "process_semantic_fingerprint": operation["process_semantic_digest"]}],
            output_version_refs=[{"project_id": operation["project_id"], "template_id": template_id,
                                  "bootstrap_operation_id": operation["operation_id"]}],
            tenant_id=key["tenant_id"], enterprise_scope_id=key["scope_node_id"] or key["context_root_id"],
            entity_mode=key["entity_mode"], project_id=operation["project_id"], blueprint_id=approved["draft_id"])

    def _append_event(self, approved, operation, template_id):
        from core.advisor_bootstrap_ledger import BootstrapLedgerError, append_bootstrap_once
        try:
            return append_bootstrap_once(self.ledger, operation["event_id"],
                **self._ledger_payload(approved, operation, template_id))
        except BootstrapLedgerError as exc:
            raise RevisionStoreError(exc.reason_code, str(exc), exc.status_code) from exc
        except Exception as exc:
            raise RevisionStoreError("ADVISOR_LEDGER_INTEGRITY", "승격 원장을 확인할 수 없습니다.", 503) from exc

    def bootstrap(self, *, boundary, actor, context, approved_revision_id, approved_digest,
                  expected_process_semantic_digest, client_request_id):
        from core.paths import workspace_path
        from core.advisor_bootstrap_ledger import append_bootstrap_once

        approved = self.drafts.approved(boundary=boundary, actor=actor, context=context,
            approved_revision_id=approved_revision_id, approved_digest=approved_digest)
        operation = self.revisions.reserve_bootstrap(approved_revision_id=approved_revision_id,
            digest=approved_digest, context_key=context_key(boundary), actor=actor,
            client_request_id=client_request_id, semantic_digest=expected_process_semantic_digest)
        workspace = Path(workspace_path(operation["project_id"]))
        expected = fixed_project_fields(approved, operation)
        blueprint = approved["blueprint"]
        system = blueprint.get("system") or {}
        if not isinstance(system, dict):
            raise RevisionStoreError("STUDIO_TEMPLATE_INVALID", "시스템 요구사항 형식을 확인하십시오.", 422)
        template_id = system.get("template_id") or "default"
        project_name = blueprint.get("title") or "새 업무"
        if not isinstance(template_id, str) or not isinstance(project_name, str):
            raise RevisionStoreError("STUDIO_TEMPLATE_INVALID", "프로젝트 이름과 템플릿 형식을 확인하십시오.", 422)

        with operation_lock(operation["project_id"]):
            operation = self.revisions.get(boundary=context_key(boundary), actor=actor,
                                             operation_id=operation["operation_id"])
            if operation["stage"] == "COMPLETED":
                verify_files(workspace, expected, ready=True)
                # 완료 응답을 잃은 재시도도 원래 사건이 남아 있는지 확인한다.
                try:
                    event = self.ledger.get_event_strict(operation["event_id"])
                except Exception as exc:
                    raise RevisionStoreError("ADVISOR_LEDGER_INTEGRITY", "완료한 승격 사건을 확인할 수 없습니다.", 503) from exc
                if not event or event.get("project_id") != operation["project_id"]:
                    raise RevisionStoreError("ADVISOR_LEDGER_INTEGRITY", "완료한 승격 사건을 확인할 수 없습니다.", 503)
                self._append_event(approved, operation, template_id)
                return operation
            if operation["stage"] == "FAILED_BLOCKED":
                raise RevisionStoreError("STUDIO_BOOTSTRAP_BLOCKED", "복구 불가 상태입니다. 부분 프로젝트와 초안을 보존하고 원인을 확인하십시오.")
            try:
                if operation["stage"] == "FAILED_RETRYABLE":
                    operation = self._advance(operation, operation["resume_stage"])
                if operation["stage"] == "RESERVED":
                    operation = self._advance(operation, "PROVISIONING")
                if operation["stage"] == "PROVISIONING":
                    # 메타와 상태 모두 성공적으로 다시 읽은 뒤에만 다음 단계로 간다.
                    for name in ("project_meta.json", "latest_state.json"):
                        saved_path = workspace / name
                        if saved_path.exists() and projection(read_json(saved_path)) != projection(expected):
                            raise RevisionStoreError("STUDIO_PROJECT_CONTEXT_CONFLICT", "부분 프로젝트의 고정 참조가 다릅니다. 덮어쓰지 않습니다.")
                    self.provision(operation["project_id"], template_id,
                        owner_dept_id="", owner_user_id=expected["owner_user_id"],
                        tenant_id=expected["tenant_id"], enterprise_scope_id=expected["enterprise_scope_id"],
                        entity_mode=expected["entity_mode"], blueprint_id=expected["blueprint_id"],
                        project_name=project_name, studio_context={k: expected[k] for k in STUDIO_FIELDS})
                    state = {**expected, "project_name": project_name, "template_id": template_id,
                             "owner_dept_id": "", "runtime_contract_profile": "v1",
                             "initial_idea": json.dumps(blueprint, ensure_ascii=False, sort_keys=True),
                             "workspace_root": str(workspace)}
                    #: ★★★ [10.2-B] 이 파일은 **공유 정본**이다 —
                    #:   `async_orchestrator._save_latest_state` · `advisor_control` 도 쓴다.
                    #:   `operation_lock` 은 잠금 파일이 노드 로컬이라 **다른 노드의 writer 를
                    #:   막지 못한다.** 그래서 저장 수준의 보장은 조건부 저장으로 세운다 —
                    #:   잠금 하나에 두 가지 다른 일을 시키지 않는다.
                    #:
                    #: ⚠️ 기준은 **이 조작이 읽은 판본**이다. 단계가 재시도되면 앞선 부분
                    #:   시도가 남긴 판본을 읽어 이어간다(이 조작은 `operation_lock` 아래에서
                    #:   자기 작업공간을 소유한다). 남이 그 사이에 바꿨으면 거절된다.
                    state_path = workspace / "latest_state.json"
                    _, state_digest = read_json_with_digest(state_path)
                    write_json(state_path, state, expected_digest=state_digest)
                    operation = self._advance(operation, "CONTEXT_WRITTEN", **verify_files(workspace, expected))
                if operation["stage"] == "CONTEXT_WRITTEN":
                    verify_files(workspace, expected)
                    operation = self._advance(operation, "LEDGER_PENDING")
                if operation["stage"] == "LEDGER_PENDING":
                    # 과거 승인은 현재 권한이 아니다. 접수 직전 다시 확인한다.
                    self.drafts.approved(boundary=boundary, actor=actor, context=context,
                        approved_revision_id=approved_revision_id, approved_digest=approved_digest)
                    verify_files(workspace, expected)
                    event = self._append_event(approved, operation, template_id)
                    if event.get("event_id") != operation["event_id"]:
                        raise RevisionStoreError("ADVISOR_LEDGER_ACK_REQUIRED", "원장 접수를 확인하지 못했습니다.", 503)
                    for name in ("project_meta.json", "latest_state.json"):
                        path = workspace / name
                        #: ★★ [10.2-B] 읽기-수정-쓰기의 기준은 **그 읽기** 다.
                        #:   따로 `digest_of` 를 부르면 그 사이가 창이다.
                        value, base_digest = read_json_with_digest(path)
                        if value is None:
                            raise RevisionStoreError(
                                "STUDIO_PROJECT_UNREADABLE",
                                "프로젝트 저장 상태를 확인할 수 없습니다.", 503)
                        value["setup_status"] = "READY"
                        write_json(path, value, expected_digest=base_digest)
                    verify_files(workspace, expected, ready=True)
                    operation = self._advance(operation, "COMPLETED", ledger_event_id=event["event_id"], ledger_acknowledged=True)
                return operation
            except Exception as exc:
                # 고정 project/event ID를 유지한다. DB 실패로 상태 기록도 실패하면 원래 단계에서 재시도한다.
                blocked = isinstance(exc, FileExistsError) or (isinstance(exc, (RevisionStoreError, ProcessError)) and exc.status_code < 500)
                try:
                    self._advance(operation, "FAILED_BLOCKED" if blocked else "FAILED_RETRYABLE",
                                  error_code=getattr(exc, "reason_code", "STUDIO_SETUP_IO_FAILED"),
                                  error_message="프로젝트 준비가 완료되지 않았습니다. 동일 승인판·요청 키로 상태를 확인하십시오.")
                except RevisionStoreError:
                    pass
                if isinstance(exc, (RevisionStoreError, ProcessError)):
                    raise
                if isinstance(exc, FileExistsError):
                    raise RevisionStoreError("STUDIO_PROJECT_ID_CONFLICT", "예약 경로에 출처를 확인할 수 없는 파일이 있습니다. 덮어쓰지 않았습니다.") from exc
                raise RevisionStoreError("STUDIO_SETUP_IO_FAILED", "프로젝트 준비가 중단되었습니다. 부분 상태를 보존했으며 같은 요청으로 재개할 수 있습니다.", 503) from exc
