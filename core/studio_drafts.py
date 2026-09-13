"""B3 상담 초안의 서버 권한·명시 문맥·patch/CAS 어댑터.

요구사항 초안은 실행 계약이 아니다. 데이터가 없어도 보존할 수 있지만 미확정
업무 참조를 승인된 ProcessContext로 꾸미거나 프로젝트 승격에 사용하지 않는다.
"""
import copy

from core.advisor_revision_store import RevisionStore, RevisionStoreError
from core.enterprise_context.process_configuration import ProcessConfigurationService
from core.enterprise_context.process_schema import ProcessBoundary, ProcessError, fingerprint

_UNSET = object()


def context_key(boundary):
    return {k: getattr(boundary, k) for k in ("tenant_id", "context_root_id", "entity_mode", "scope_node_id")}


class StudioDraftService:
    def __init__(self, *, revisions=None, processes=None, repo=None, store=None):
        if revisions is None:
            from core.advisor_store import advisor_store
            revisions = RevisionStore(advisor_store)
        if processes is None:
            from core.enterprise_context.process_context import ProcessContextService
            processes = ProcessContextService(repo=repo, store=store)
        self.revisions, self.processes = revisions, processes
        self.configurations = ProcessConfigurationService(repo, store)

    def authorize(self, boundary, actor, context, action):
        from core.admin_capability import PROJECT_CREATE, PROJECT_RELEASE
        mode = {"READ": "read", "DRAFT": "propose", "DECIDE": "publish", "BOOTSTRAP": "propose"}[action]
        with self.configurations.transaction() as conn:
            rights = self.configurations._authorize(conn, boundary, actor, context, mode)
            if action == "BOOTSTRAP" and not rights.has(PROJECT_CREATE):
                raise ProcessError("STUDIO_PROJECT_CREATE_FORBIDDEN", "현재 문맥에서 프로젝트를 생성할 권한이 없습니다.", 403)
            if action == "DECIDE" and not rights.has(PROJECT_RELEASE):
                raise ProcessError("STUDIO_APPROVAL_FORBIDDEN", "현재 문맥에서 Blueprint를 승인할 권한이 없습니다.", 403)
            return rights

    def _process_ref(self, boundary, actor, context, selection):
        if selection is None:
            return None
        if not isinstance(selection, dict):
            raise ProcessError("PROCESS_REFERENCE_INVALID", "업무 참조 형식을 확인하십시오.", 422)
        kind = selection.get("kind")
        if kind == "APPROVED" and set(selection) == {"kind", "profile_id", "process_ids"}:
            return self.processes.build(boundary=boundary, actor=actor, context=context,
                                        profile_id=selection["profile_id"], process_ids=selection["process_ids"])
        if kind == "DRAFT" and set(selection) == {"kind", "change_id", "draft_digest"}:
            draft = self.configurations.validate(change_id=selection["change_id"], actor=actor,
                                                  context=context, draft_digest=selection["draft_digest"])
            # validate는 대상 change 자체의 문맥을 검사한다. 요청이 선언한 정확한 boundary도 일치해야 한다.
            with self.configurations.transaction() as conn:
                _, _, actual = self.configurations._change(conn, selection["change_id"], actor, context)
            if actual != boundary:
                raise ProcessError("PROCESS_NOT_FOUND", "현재 문맥에서 업무 초안을 찾을 수 없습니다.", 404)
            return {"state": "DRAFT", "reference_schema": "PROCESS_DRAFT_REFERENCE_V1",
                    "change_id": draft["change_id"], "draft_digest": draft["draft_digest"],
                    "configuration_id": draft["configuration_id"], "context_key": context_key(boundary)}
        raise ProcessError("PROCESS_REFERENCE_INVALID", "승인판 또는 업무 초안 참조를 명시하십시오.", 422)

    @staticmethod
    def apply_patch(blueprint, patch):
        if not isinstance(patch, list) or not patch or len(patch) > 200:
            raise RevisionStoreError("ADVISOR_PATCH_INVALID", "1~200개 명시 변경이 필요합니다.", 422)
        result = copy.deepcopy(blueprint)
        for item in patch:
            if not isinstance(item, dict) or item.get("op") not in {"SET", "REMOVE"}:
                raise RevisionStoreError("ADVISOR_PATCH_INVALID", "SET/REMOVE 변경만 허용합니다.", 422)
            if set(item) != ({"op", "path", "value"} if item["op"] == "SET" else {"op", "path"}):
                raise RevisionStoreError("ADVISOR_PATCH_INVALID", "변경 필드를 확인하십시오.", 422)
            path = item["path"]
            if (not isinstance(path, list) or not 1 <= len(path) <= 12 or
                    any(not isinstance(k, str) or not k or k in {"__proto__", "prototype", "constructor"} for k in path)):
                raise RevisionStoreError("ADVISOR_PATCH_INVALID", "변경 경로는 명시한 JSON 키 목록이어야 합니다.", 422)
            target = result
            for key in path[:-1]:
                if key not in target or not isinstance(target[key], dict):
                    raise RevisionStoreError("ADVISOR_PATCH_INVALID", "부모 객체가 없는 경로입니다. 부모 내용을 먼저 저장하십시오.", 422)
                target = target[key]
            if item["op"] == "REMOVE":
                if path[-1] not in target:
                    raise RevisionStoreError("ADVISOR_PATCH_INVALID", "제거할 필드가 없습니다.", 422)
                del target[path[-1]]
            else:
                target[path[-1]] = copy.deepcopy(item["value"])
        return result

    def save(self, *, boundary, actor, context, draft_id, expected_revision, expected_digest,
             patch, client_request_id, process_selection=_UNSET):
        self.authorize(boundary, actor, context, "DRAFT")
        key = context_key(boundary)
        command_digest = fingerprint({"draft_id": draft_id, "expected_revision": expected_revision,
            "expected_digest": expected_digest, "patch": patch,
            "process_selection_present": process_selection is not _UNSET,
            "process_selection": process_selection if process_selection is not _UNSET else None})
        prior = self.revisions.replay_save(boundary=key, actor=actor, client_request_id=client_request_id,
                                           command_digest=command_digest)
        if prior:
            return prior
        if draft_id:
            previous = self.revisions.get(boundary=key, actor=actor, draft_id=draft_id, revision=expected_revision)
            blueprint = previous["blueprint"]
        else:
            blueprint = {}
        merged = self.apply_patch(blueprint, patch)
        ref = (previous.get("process_ref") if draft_id else None) if process_selection is _UNSET else self._process_ref(boundary, actor, context, process_selection)
        return self.revisions.save(boundary=key, actor=actor, draft_id=draft_id,
            expected_revision=expected_revision, expected_digest=expected_digest, blueprint=merged,
            client_request_id=client_request_id, process_ref=ref, command_digest=command_digest)

    def get(self, *, boundary, actor, context, draft_id, revision=None):
        self.authorize(boundary, actor, context, "READ")
        return self.revisions.get(boundary=context_key(boundary), actor=actor, draft_id=draft_id, revision=revision)

    def decide(self, *, boundary, actor, context, draft_id, expected_revision, draft_digest, decision, reason):
        self.authorize(boundary, actor, context, "DECIDE")
        row = self.revisions.get(boundary=context_key(boundary), actor=actor, draft_id=draft_id, revision=expected_revision)
        ref = row.get("process_ref")
        if ref and ref.get("state", "APPROVED") == "APPROVED":
            self.processes.revalidate(fixed_context=ref, actor=actor, current_context=context, for_action="DRAFT")
        return self.revisions.decide(boundary=context_key(boundary), actor=actor, draft_id=draft_id,
            expected_revision=expected_revision, draft_digest=draft_digest, decision=decision, reason=reason)

    def approved(self, *, boundary, actor, context, approved_revision_id, approved_digest):
        self.authorize(boundary, actor, context, "BOOTSTRAP")
        row = self.revisions.get(boundary=context_key(boundary), actor=actor, approved_revision_id=approved_revision_id)
        if row["digest"] != approved_digest:
            raise RevisionStoreError("ADVISOR_REVISION_CONFLICT", "승인한 Blueprint 판본의 지문이 다릅니다.")
        ref = row.get("process_ref")
        if not ref or ref.get("state", "APPROVED") != "APPROVED":
            raise RevisionStoreError("ADVISOR_PROCESS_CONTEXT_REQUIRED", "업무 참조가 미확정입니다. 초안은 보존되며 승인된 업무를 먼저 선택해야 합니다.")
        self.processes.revalidate(fixed_context=ref, actor=actor, current_context=context, for_action="BOOTSTRAP")
        return row
