"""B3 서버 cohort 판독과 현재 업무 권한 검사. 클라이언트 marker는 opt-in 수단이 아니다."""
from pathlib import Path

from core.advisor_revision_store import RevisionStore, RevisionStoreError
from core.enterprise_context.process_schema import ProcessBoundary, ProcessError
from core.studio_bootstrap import fixed_project_fields
from core.studio_project_files import STUDIO_FIELDS, read_json, verify_files


def project_context(project_id, *, actor, context, for_action, revisions=None, processes=None):
    """반환 None만 레거시. 신규 예약 행은 marker가 없어져도 1.0으로 내리지 않는다."""
    from core.paths import workspace_path
    if revisions is None:
        from core.advisor_store import advisor_store
        # 화면 진입 조회가 DB/판본 테이블을 새로 만들거나 복구하지 않게 한다.
        # 저장·승격·실행 경로의 기존 초기화 계약은 그대로 유지한다.
        revisions = RevisionStore(advisor_store, read_only=for_action == "READ")
    indexed = revisions.is_v2_project(project_id)
    workspace = Path(workspace_path(project_id))
    if not indexed and (workspace / "latest_state.json").exists():
        saved = read_json(workspace / "latest_state.json")
        if saved.get("runtime_document_version", "1.0") != "1.0" or any(
                saved.get(k) for k in STUDIO_FIELDS if k != "runtime_document_version"):
            raise RevisionStoreError("STUDIO_PROJECT_PROVENANCE_REQUIRED", "복원한 신규 상태의 서버 승격 기록을 확인해야 합니다.")
    # 레거시의 기존 오류 처리 계약은 유지한다. 신규 metadata 판독 실패는 아래에서 차단한다.
    if not indexed and not (workspace / "project_meta.json").exists():
        return None
    meta = read_json(workspace / "project_meta.json")
    version = meta.get("runtime_document_version", "1.0")
    if not indexed:
        if version != "1.0" or any(meta.get(k) for k in STUDIO_FIELDS if k != "runtime_document_version"):
            raise RevisionStoreError("STUDIO_PROJECT_PROVENANCE_REQUIRED", "서버가 확인한 신규 프로젝트 승격 기록이 없습니다.")
        return None
    if version != "2.0":
        raise RevisionStoreError("STUDIO_PROJECT_CONTEXT_MISSING", "신규 프로젝트의 업무 참조가 누락되거나 변경되었습니다.")
    try:
        key = meta["process_context"]["context_key"]
        boundary = ProcessBoundary.model_validate(key)
    except (KeyError, TypeError, ValueError) as exc:
        raise RevisionStoreError("STUDIO_PROJECT_CONTEXT_MISSING", "프로젝트의 명시적 회사·조직 문맥이 필요합니다.") from exc
    if not isinstance(context, dict) or not context.get("scope_node_id"):
        raise ProcessError("PROCESS_CONTEXT_REQUIRED", "회사·조직 문맥을 명시적으로 선택하십시오.", 422)
    if processes is None:
        from core.enterprise_context.process_context import ProcessContextService
        processes = ProcessContextService()
    with processes.configuration.transaction() as conn:
        rights = processes.configuration._authorize(conn, boundary, actor, context,
            "propose" if for_action in {"DRAFT", "GENERATE"} else "read")
        from core.admin_capability import PROJECT_RUN, PROJECT_RELEASE
        cap = PROJECT_RELEASE if for_action == "RELEASE" else PROJECT_RUN
        if for_action in {"GENERATE", "RUN", "RELEASE"} and not rights.has(cap):
            raise ProcessError("STUDIO_ACTION_FORBIDDEN", "현재 문맥에서 이 프로젝트 작업을 수행할 권한이 없습니다.", 403)
    operation = revisions.get_for_project(boundary=key, project_id=project_id)
    if not operation or operation["stage"] != "COMPLETED":
        raise RevisionStoreError("STUDIO_SETUP_INCOMPLETE", "프로젝트 준비가 완료되지 않았습니다. 승격 요청을 먼저 재개하십시오.")
    approved = revisions.get(boundary=key, actor=actor, approved_revision_id=operation["approved_revision_id"])
    expected = fixed_project_fields(approved, operation)
    verify_files(workspace, expected, ready=True)
    processes.revalidate(fixed_context=approved["process_ref"], actor=actor, current_context=context, for_action=for_action)
    return {**{k: meta[k] for k in STUDIO_FIELDS}, "blueprint_id": approved["draft_id"],
            "tenant_id": expected["tenant_id"], "enterprise_scope_id": expected["enterprise_scope_id"],
            "entity_mode": expected["entity_mode"]}


def for_principal(project_id, principal, for_action):
    """기존 Factory HTTP 경계용. 상세 오류는 기존 공통 오류 응답으로 변환한다."""
    from api.deps import viewing_context
    from api.routes.process_configuration_control import error
    # 문맥 없는 legacy 호출은 유지하되 신규는 project_context에서 명시 선택을 요구한다.
    context = viewing_context(principal) if principal is not None else {}
    try:
        return project_context(project_id, actor=getattr(principal, "user_id", ""),
                               context=context, for_action=for_action)
    except (RevisionStoreError, ProcessError) as exc:
        error(exc, getattr(principal, "user_id", ""), project_id)
