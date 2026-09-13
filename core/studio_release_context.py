"""B3 릴리스/Host가 매 행위 시 호출하는 현재 업무 문맥 경계."""
from core.advisor_revision_store import RevisionStore, RevisionStoreError
from core.enterprise_context.process_schema import ProcessBoundary, ProcessError


def materialization_context(contract, current_context):
    """조회자의 선택 조직과 쓰기 대상 자산의 고정 조직을 섞지 않는다."""
    if not isinstance(contract, dict) or contract.get("schema_version") != "2.0":
        return current_context
    try:
        boundary = ProcessBoundary.model_validate(contract["process_context"]["context_key"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProcessError("STUDIO_RELEASE_CONTEXT_INVALID", "고정 물질화 대상 문맥이 없습니다.", 409) from exc
    return {"tenant_id": boundary.tenant_id, "entity_mode": boundary.entity_mode,
            "scope_node_id": boundary.scope_node_id or boundary.context_root_id}


def assert_project_release(release, studio):
    """일반 2.0 게시의 첫 쓰기 전에 서버 문맥·승인 원문·최종 소유 경계를 대조한다."""
    from core import app_runtime_contract as arc
    contract = release.get("runtime_contract")
    keys = ("runtime_document_version", "process_context", "tenant_id", "enterprise_scope_id", "entity_mode")
    if (not isinstance(contract, dict) or contract.get("schema_version") != "2.0"
            or arc.validate(contract) or (contract.get("approval") or {}).get("status") != "APPROVED"
            or contract.get("project_id") != release.get("project_id")
            or contract.get("process_context") != studio.get("process_context")
            or any(release.get(k) != studio.get(k) for k in keys)):
        raise ProcessError("STUDIO_RELEASE_CONTEXT_CONFLICT", "게시할 승인 계약과 프로젝트의 고정 업무 문맥이 다릅니다.", 409)


def require_published_release(release, *, release_id, actor, context):
    """2.0 운영 쓰기 직전/직후 같은 게시판인지 확인한다. 분산 원자성을 주장하지 않는다."""
    from core import app_proof, app_runtime_contract as arc
    current = app_proof.read_release(release_id)
    keys = ("release_id", "project_id", "runtime_document_version", "tenant_id", "enterprise_scope_id", "entity_mode")
    if (not isinstance(current, dict) or any(current.get(k) != release.get(k) for k in keys)
            or arc.canonical_json(current.get("runtime_contract")) != arc.canonical_json(release.get("runtime_contract"))):
        raise ProcessError("STUDIO_RELEASE_CHANGED", "검사 중 다른 계약 판이 게시되었습니다. 새 판을 다시 검토하십시오.", 409)
    return require_release_context(current, release_id=release_id, actor=actor, context=context, for_action="RELEASE")


def require_release_context(release, *, actor, context, release_id="", for_action="RUN", processes=None, revisions=None, store=None):
    from core import app_runtime_contract as arc
    if store is None:
        from core.data_preparation.store import data_preparation_store
        store = data_preparation_store
    from core.studio_release_cohort import get_release_cohort
    rid = release_id or (str(release.get("release_id") or "") if isinstance(release, dict) else "")
    cohort = get_release_cohort(store, rid) if rid else None
    if revisions is None:
        from core.advisor_store import advisor_store
        revisions = RevisionStore(advisor_store)
    # Factory가 생성하는 일반 release ID에는 예약된 project ID가 들어 있다.
    # 복원 파일에서 project_id/2.0 marker를 모두 지워도 서버 예약 행을 놓치지 않는다.
    import re
    match = re.fullmatch(r"(prj_[0-9a-f]{32})_\d{8}_\d{6}", rid)
    source_project = match.group(1) if match and revisions.is_v2_project(match.group(1)) else ""
    if not isinstance(release, dict):
        if cohort or source_project:
            raise RevisionStoreError("STUDIO_RELEASE_CONTEXT_REQUIRED", "신규 릴리스의 원문을 확인할 수 없습니다.")
        return None
    contract = release.get("runtime_contract")
    document = contract.get("schema_version") if isinstance(contract, dict) else None
    project_id = str(release.get("project_id") or "")
    if source_project and project_id != source_project:
        raise RevisionStoreError("STUDIO_RELEASE_CONTEXT_CONFLICT", "서버가 예약한 원본 프로젝트와 릴리스가 다릅니다.")
    indexed = bool(project_id) and revisions.is_v2_project(project_id)
    declared = release.get("runtime_document_version", "1.0")
    if not indexed and not cohort and document in (None, "1.0") and declared == "1.0":
        return None
    if document != "2.0" or declared != "2.0" or not (indexed or cohort) or (rid and release.get("release_id") != rid):
        raise RevisionStoreError("STUDIO_RELEASE_CONTEXT_REQUIRED", "신규 릴리스의 업무 계약 판본이 누락되거나 변경되었습니다.")
    errors = arc.validate(contract)
    if errors:
        raise RevisionStoreError("STUDIO_RELEASE_CONTEXT_INVALID", "릴리스 업무 계약을 확인할 수 없습니다.")
    fixed = contract["process_context"]
    if not isinstance(context, dict) or not context.get("scope_node_id"):
        raise ProcessError("PROCESS_CONTEXT_REQUIRED", "회사·조직 문맥을 명시적으로 선택하십시오.", 422)
    if processes is None:
        from core.enterprise_context.process_context import ProcessContextService
        processes = ProcessContextService(store=store)
    boundary = ProcessBoundary.model_validate(fixed["context_key"])
    with processes.configuration.transaction() as conn:
        rights = processes.configuration._authorize(conn, boundary, actor, context)
        from core.admin_capability import AGENT_EXECUTE, PROJECT_RELEASE
        # Host의 승인된 앱 사용과 Factory의 LLM 가동(PROJECT_RUN)은 다른 권한이다.
        if not rights.has(PROJECT_RELEASE if for_action == "RELEASE" else AGENT_EXECUTE):
            raise ProcessError("STUDIO_ACTION_FORBIDDEN", "현재 업무를 실행할 권한이 없습니다.", 403)
    if indexed:
        operation = revisions.get_for_project(boundary=fixed["context_key"], project_id=project_id)
        if not operation or operation["stage"] != "COMPLETED":
            raise RevisionStoreError("STUDIO_SETUP_INCOMPLETE", "프로젝트 준비 기록을 확인할 수 없습니다.")
        approved = revisions.get(boundary=fixed["context_key"], actor=actor, approved_revision_id=operation["approved_revision_id"])
        if approved["process_ref"] != fixed:
            raise RevisionStoreError("STUDIO_RELEASE_CONTEXT_CONFLICT", "승인된 프로젝트와 릴리스의 업무 참조가 다릅니다.")
    if cohort:
        from core import kit_app_contract
        if (cohort["context_key"] != fixed["context_key"] or release.get("instance_id") != cohort["instance_id"]
                or release.get("app_id") != cohort["app_id"] or contract.get("project_id") != cohort["instance_id"]
                or contract.get("task_id") != cohort["app_id"]):
            raise RevisionStoreError("STUDIO_RELEASE_CONTEXT_CONFLICT", "릴리스의 고정 적용본·앱 정체성이 다릅니다.")
        with store.transaction() as conn:
            approved = kit_app_contract._v2_row(conn, cohort["instance_id"], cohort["app_id"], contract["revision"])
        # 새 후보 승인만으로 기존 운영 판을 중단하지 않는다. 게시된 고정 개정의
        # 승인 증거와 현재 업무/데이터 사용권은 서로 다른 사실이다.
        if (not approved or approved["status"] not in ("APPROVED", "SUPERSEDED")
                or arc.canonical_json(approved["contract"]) != arc.canonical_json(contract)
                or approved["semantic_fingerprint"] != arc.semantic_fingerprint(contract)):
            raise RevisionStoreError("STUDIO_RELEASE_CONTEXT_CONFLICT", "게시된 고정 승인 개정과 릴리스가 다릅니다.")
        kit_app_contract._proof_v2(approved)
    return processes.revalidate(fixed_context=fixed, actor=actor, current_context=context, for_action=for_action)
