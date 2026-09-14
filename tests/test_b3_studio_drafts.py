"""B3 Studio 초안 서비스 회귀. 작성만: main audit/--noconftest 런너 전용.

unit_*는 권한/ProcessContext만 명시적 대역이다. 실제 AdvisorStore/DecisionLedger를
매 시험 새 tmp_path에 만든다. real_*는 enforced_org의 실제 PDP/ECM/ProcessContext를
연결하되 인증 데이터/RAW/Starter/Factory/API를 검증했다고 주장하지 않는다.
수집 시 제품 모듈 import 없음. autouse 격리가 제품 import보다 먼저 DB/프로젝트 경로를
제한한다. pytest를 직접 실행하지 말 것(메인 source hash/audit 준비 뒤에만 실행).
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from tests.usage_hold_test_plugin import enforced_org  # noqa: F401


AUTHOR = "author@studio.test.invalid"
REVIEWER = "reviewer@studio.test.invalid"
OTHER = "other@studio.test.invalid"
CONTEXT = {"tenant_id": "tenant.test.invalid", "context_root_id": "root.test.invalid",
           "entity_mode": "REAL", "scope_node_id": "scope.test.invalid"}
SELECTION = {"kind": "APPROVED", "profile_id": "profile.test.invalid", "process_ids": ["plan"]}
PATCH = [{"op": "SET", "path": ["title"], "value": "합성 구매계획"},
         {"op": "SET", "path": ["system"], "value": {"template_id": "default"}},
         {"op": "SET", "path": ["business"], "value": {"objective": "미확보 요구 보존"}}]


@pytest.fixture(autouse=True)
def isolated_stores(tmp_path, monkeypatch):
    """AdvisorStore의 eager 전역 생성까지 temp로 제한. 기존 DB로 연결하면 즉시 실패."""
    from core import paths

    root = tmp_path.resolve()
    monkeypatch.setattr(paths, "DATA_DIR", str(root / "data"))
    monkeypatch.setattr(paths, "PROJECTS_DIR", str(root / "projects"))
    connect = sqlite3.connect
    opened = []

    def guarded_connect(database, *args, **kwargs):
        value = os.fspath(database)
        assert isinstance(value, str)
        if value.startswith("file:"):
            from urllib.parse import urlsplit
            from urllib.request import url2pathname
            parts = urlsplit(value)
            path = Path(url2pathname(parts.path)).resolve()
            # 현재 시험의 기존 정규 파일에 대한 정확한 읽기 전용 URI만 허용한다.
            assert kwargs.get("uri") is True and not parts.netloc
            assert value == path.as_uri() + "?mode=ro"
            assert path.is_relative_to(root) and path.is_file()
            opened.append(str(path))
            return connect(database, *args, **kwargs)
        if value != ":memory:":
            assert Path(value).is_absolute() and Path(value).resolve().is_relative_to(root), value
        opened.append(value)
        return connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    # 전역 AdvisorStore가 처음 import될 때도 위 data 경로/SQLite guard가 이미 적용된다.
    from core.advisor_store import AdvisorStore
    from core.advisor_revision_store import RevisionStore
    from core.decision_ledger import DecisionLedger
    from core.enterprise_context import audit

    monkeypatch.setattr(audit, "_LOG_PATH", str(root / "studio-access.test.invalid.jsonl"))

    advisor = AdvisorStore(db_path=str(root / "advisor-studio.test.invalid.db"))
    ledger = DecisionLedger(db_path=str(root / "ledger-studio.test.invalid.db"))
    revisions = RevisionStore(advisor)
    revisions._ensure()
    ledger._ready()
    return SimpleNamespace(root=root, advisor=advisor, ledger=ledger, revisions=revisions, opened=opened)


@contextmanager
def _db(env, ledger=False):
    storage = env.ledger if ledger else env.advisor
    assert Path(storage.db_path).resolve().is_relative_to(env.root)
    conn = storage._connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _count(env, table):
    assert table in {"advisor_v2_revisions", "advisor_v2_requests", "advisor_v2_bootstraps",
                     "solution_blueprints", "decision_ledger_events"}
    with _db(env, table == "decision_ledger_events") as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _error(call, code=None, status=409):
    from core.advisor_revision_store import RevisionStoreError
    from core.advisor_bootstrap_ledger import BootstrapLedgerError
    from core.enterprise_context.process_schema import ProcessError

    with pytest.raises((RevisionStoreError, ProcessError, BootstrapLedgerError)) as failure:
        call()
    assert failure.value.status_code == status
    if code is not None:
        assert failure.value.reason_code == code
    return failure.value


class UnitProcesses:
    """단위 시험 전용 DTO 대역. 실제 서명/PDP/ECM 검사는 real_studio 시험이 담당한다."""
    def __init__(self):
        self.build_calls, self.revalidate_calls = [], []
        self.deny_action = None
        self.dynamic = 0

    def build(self, *, boundary, actor, context, profile_id, process_ids):
        self.build_calls.append((actor, profile_id, list(process_ids)))
        return {"schema_version": 1, "state": "APPROVED", "configuration_id": "cfg.test.invalid",
                "profile_id": profile_id, "process_ids": sorted(process_ids),
                "context_key": {key: getattr(boundary, key) for key in CONTEXT},
                "process_semantic_fingerprint": "a" * 64, "configuration_fingerprint": "b" * 64,
                "blockers": [{"unit_dynamic": self.dynamic}]}

    def revalidate(self, fixed_context, *, actor, current_context, for_action):
        # 일부 fault 시험을 서명 오류와 분리한다. real fixture는 실제 keyword-only 메서드다.
        from core.enterprise_context.process_schema import ProcessError
        self.revalidate_calls.append((actor, for_action, copy.deepcopy(fixed_context)))
        if for_action == self.deny_action:
            raise ProcessError("UNIT_PROCESS_DENIED", "단위시험 문맥 차단", 403)
        return copy.deepcopy(fixed_context)


@pytest.fixture
def unit_studio(isolated_stores, monkeypatch):
    from core.enterprise_context.process_schema import ProcessBoundary, ProcessError
    from core.studio_drafts import StudioDraftService

    def unused_connect():
        raise AssertionError("unit auth/ProcessContext 대역 시험은 실제 ECM을 조회하지 않는다")

    env = SimpleNamespace(**vars(isolated_stores), author=AUTHOR, reviewer=REVIEWER,
                          other=OTHER, boundary=ProcessBoundary(**CONTEXT), context=copy.deepcopy(CONTEXT),
                          selection=copy.deepcopy(SELECTION), processes=UnitProcesses(), denied=set(), auth_calls=[])
    env.drafts = StudioDraftService(revisions=env.revisions, processes=env.processes,
                                     repo=SimpleNamespace(_connect=unused_connect))

    def unit_authorize(boundary, actor, context, action):
        env.auth_calls.append((actor, action))
        if (actor, action) in env.denied:
            raise ProcessError("UNIT_AUTH_DENIED", "단위시험 현재 권한 거부", 403)
        if boundary != env.boundary or context != env.context:
            raise ProcessError("PROCESS_NOT_FOUND", "단위시험 다른 문맥", 404)
        return SimpleNamespace(has=lambda _cap: True)

    monkeypatch.setattr(env.drafts, "authorize", unit_authorize)
    return env


def _save(env, previous=None, **changes):
    args = dict(boundary=env.boundary, actor=env.author, context=env.context,
                draft_id=previous["draft_id"] if previous else "",
                expected_revision=previous["revision"] if previous else 0,
                expected_digest=previous["digest"] if previous else "", patch=copy.deepcopy(PATCH),
                client_request_id=f"save-{previous['revision'] + 1}" if previous else "save-1")
    if previous is None:
        args["process_selection"] = copy.deepcopy(env.selection)
    return env.drafts.save(**{**args, **changes})


def _decide(env, draft, **changes):
    return env.drafts.decide(**{ "boundary": env.boundary, "actor": env.reviewer, "context": env.context,
        "draft_id": draft["draft_id"], "expected_revision": draft["revision"], "draft_digest": draft["digest"],
        "decision": "APPROVED", "reason": "합성 독립 검토", **changes})


def _approved(env, approved, **changes):
    return env.drafts.approved(**{"boundary": env.boundary, "actor": env.author, "context": env.context,
        "approved_revision_id": approved["revision_id"], "approved_digest": approved["digest"], **changes})


def _get(env, draft, **changes):
    return env.drafts.get(**{"boundary": env.boundary, "actor": env.author,
                             "context": env.context, "draft_id": draft["draft_id"], **changes})


def test_unit_patch_is_explicit_deep_copy_and_preserves_unmentioned_fields(unit_studio):
    env = unit_studio
    first = _save(env)
    before = copy.deepcopy(first)
    patch = [{"op": "SET", "path": ["business", "objective"], "value": "변경"},
             {"op": "REMOVE", "path": ["system"]}]
    second = _save(env, first, patch=patch)
    assert first == before
    assert second["blueprint"] == {"title": first["blueprint"]["title"], "business": {"objective": "변경"}}
    assert _get(env, first, revision=1) == first
    assert _count(env, "solution_blueprints") == 0


@pytest.mark.parametrize("patch", [None, [], {}, [{"op": "MERGE", "path": ["title"], "value": "x"}],
    [{"op": "SET", "path": [], "value": "x"}], [{"op": "SET", "path": "title", "value": "x"}],
    [{"op": "SET", "path": ["__proto__"], "value": {}}],
    [{"op": "SET", "path": ["constructor"], "value": {}}],
    [{"op": "SET", "path": ["prototype"], "value": {}}],
    [{"op": "SET", "path": ["missing", "child"], "value": "x"}],
    [{"op": "REMOVE", "path": ["missing"]}], [{"op": "REMOVE", "path": ["title"], "value": None}],
    [{"op": "SET", "path": ["title"], "value": "x", "extra": True}],
    [{"op": "SET", "path": ["title"], "value": "x"}] * 201])
def test_unit_invalid_patch_does_not_write_revision_or_request(unit_studio, patch):
    env = unit_studio
    first = _save(env)
    _error(lambda: _save(env, first, patch=patch), "ADVISOR_PATCH_INVALID", 422)
    assert _get(env, first) == first
    assert _count(env, "advisor_v2_revisions") == _count(env, "advisor_v2_requests") == 1


@pytest.mark.parametrize("field", ["author_actor", "owner_user_id", "approved_revision_id", "status",
                                  "context_key", "process_ref", "command_digest", "runtime_document_version",
                                  "setup_status", "approved_blueprint_revision_id", "approved_blueprint_digest"])
def test_unit_patch_cannot_write_authority_fields(unit_studio, field):
    _error(lambda: _save(unit_studio, patch=[{"op": "SET", "path": [field], "value": "forged"}]),
           "ADVISOR_AUTHORITY_FIELDS_FORBIDDEN", 422)
    assert _count(unit_studio, "advisor_v2_revisions") == 0


def test_unit_exact_http_replay_skips_patch_and_dynamic_context_after_later_head(unit_studio, monkeypatch):
    env = unit_studio
    first = _save(env)
    approved = _decide(env, first)
    later = _save(env, approved)
    calls = len(env.processes.build_calls)
    env.processes.dynamic += 1
    monkeypatch.setattr(env.drafts, "apply_patch", lambda *_args: pytest.fail("멱등 재시도는 patch 재적용 금지"))
    assert _save(env) == first
    assert len(env.processes.build_calls) == calls
    assert _get(env, later) == later
    assert env.auth_calls[-2:] == [(env.author, "DRAFT"), (env.author, "READ")]


def test_unit_current_auth_is_required_even_for_saved_command_replay(unit_studio):
    env = unit_studio
    _save(env)
    env.denied.add((env.author, "DRAFT"))
    _error(lambda: _save(env), "UNIT_AUTH_DENIED", 403)
    assert _count(env, "advisor_v2_revisions") == 1


def test_unit_same_http_request_key_changed_patch_is_conflict(unit_studio):
    env = unit_studio
    first = _save(env)
    _error(lambda: _save(env, patch=[{"op": "SET", "path": ["title"], "value": "다름"}]),
           "ADVISOR_IDEMPOTENCY_CONFLICT")
    assert _get(env, first) == first


def test_unit_omitted_process_selection_inherits_and_explicit_none_clears(unit_studio):
    env = unit_studio
    first = _save(env)
    second = _save(env, first)
    assert second["process_ref"] == first["process_ref"]
    _error(lambda: _save(env, first, process_selection=None), "ADVISOR_IDEMPOTENCY_CONFLICT")
    third = _save(env, second, process_selection=None)
    assert third["process_ref"] is None
    assert _get(env, first, revision=1)["process_ref"] == first["process_ref"]


def test_unit_data_and_process_missing_draft_can_be_preserved_not_bootstrapped(unit_studio):
    env = unit_studio
    first = _save(env, process_selection=None)
    approved = _decide(env, first)
    _error(lambda: _approved(env, approved), "ADVISOR_PROCESS_CONTEXT_REQUIRED")
    assert _get(env, first) == approved
    assert _count(env, "advisor_v2_bootstraps") == 0


def test_unit_stale_cas_does_not_apply_patch_to_new_head(unit_studio):
    env = unit_studio
    first = _save(env)
    second = _save(env, first)
    _error(lambda: _save(env, first, client_request_id="stale-other-command"), "ADVISOR_REVISION_CONFLICT")
    assert _get(env, first) == second and _count(env, "advisor_v2_revisions") == 2


def test_unit_other_actor_cannot_edit_or_self_approve(unit_studio):
    env = unit_studio
    first = _save(env)
    _error(lambda: _save(env, first, actor=env.other), "ADVISOR_NOT_FOUND", 404)
    _error(lambda: _decide(env, first, actor=env.author), "ADVISOR_SELF_APPROVAL_FORBIDDEN", 403)
    assert _get(env, first) == first


def test_unit_process_denial_prevents_approval_without_mutating_draft(unit_studio):
    env = unit_studio
    first = _save(env)
    env.processes.deny_action = "DRAFT"
    _error(lambda: _decide(env, first), "UNIT_PROCESS_DENIED", 403)
    assert _get(env, first) == first


def test_unit_approved_lookup_revalidates_current_process_and_digest(unit_studio):
    env = unit_studio
    approved = _decide(env, _save(env))
    _error(lambda: _approved(env, approved, approved_digest="0" * 64), "ADVISOR_REVISION_CONFLICT")
    env.processes.deny_action = "BOOTSTRAP"
    _error(lambda: _approved(env, approved), "UNIT_PROCESS_DENIED", 403)
    env.processes.deny_action = None
    assert _approved(env, approved) == approved


@pytest.mark.parametrize("selection", ["auto", {}, {"kind": "APPROVED"},
    {**SELECTION, "permitted_actions": ["BOOTSTRAP"]}, {**SELECTION, "actor": AUTHOR},
    {"kind": "DRAFT", "change_id": "x", "draft_digest": "a" * 64, "state": "APPROVED"}])
def test_unit_process_selection_shape_is_closed(unit_studio, selection):
    _error(lambda: _save(unit_studio, process_selection=selection), "PROCESS_REFERENCE_INVALID", 422)
    assert _count(unit_studio, "advisor_v2_revisions") == 0


def _propose(env, commands, key):
    base = env.configurations.resolved(boundary=env.boundary, actor=env.author, context=env.context)
    return env.configurations.propose(boundary=env.boundary, actor=env.author, context=env.context,
        commands=commands, expected_head_version=base["head_version"], base_profile_id=base["profile_id"],
        base_fingerprint=base["digest"], legacy_token=base["legacy_token"], client_request_id=key,
        reason="실제 ProcessContext 연결용 합성 L2")


def _approve_process(env, change):
    return env.configurations.approve(change_id=change["change_id"], actor=env.reviewer, context=env.context,
        expected_head_version=change["base_head_version"], draft_digest=change["draft_digest"], reason="합성 업무 독립 승인")


@pytest.fixture
def real_studio(isolated_stores, enforced_org):
    """실제 역할강제 + 승인 ECM + ProcessContext. 인증 데이터/팩은 합성하지 않는다."""
    from core.data_preparation.store import data_preparation_store
    from core.enterprise_context.repository import ecm_repository
    from core.enterprise_context.process_schema import ProcessBoundary
    from core.enterprise_context.process_configuration import ProcessConfigurationService
    from core.enterprise_context.process_context import ProcessContextService
    from core.studio_drafts import StudioDraftService

    org = enforced_org
    boundary = ProcessBoundary(tenant_id="tenant_default", context_root_id=org.NODES[org.DEPT_ROOT],
                                entity_mode="REAL", scope_node_id=org.NODES[org.DEPT_A])
    env = SimpleNamespace(**vars(isolated_stores), author=org.MEMBER_A, reviewer=org.MANAGER_A,
        other=org.MEMBER_B, boundary=boundary, context={"tenant_id": "tenant_default", "entity_mode": "REAL",
        "scope_node_id": org.NODES[org.DEPT_A], "context_root_id": org.NODES[org.DEPT_ROOT]}, org=org)
    assert Path(ecm_repository.db_path).resolve().is_relative_to(env.root)
    assert Path(data_preparation_store.db_path).resolve().is_relative_to(env.root)
    env.configurations = ProcessConfigurationService(repo=ecm_repository, store=data_preparation_store)
    env.processes = ProcessContextService(repo=ecm_repository, store=data_preparation_store)
    env.drafts = StudioDraftService(revisions=env.revisions, processes=env.processes,
                                    repo=ecm_repository, store=data_preparation_store)
    change = _propose(env, [
        {"op": "ADD_NODE", "node": {"process_id": "purchase", "level": "L1", "label": "원료구매"}},
        {"op": "ADD_NODE", "node": {"process_id": "plan", "level": "L2", "parent_process_id": "purchase", "label": "구매계획"}},
    ], "seed-process")
    env.profile = _approve_process(env, change)
    env.selection = {"kind": "APPROVED", "profile_id": env.profile["profile_id"], "process_ids": ["plan"]}
    return env


def test_real_process_context_save_approve_and_bootstrap_eligibility(real_studio):
    env = real_studio
    first = _save(env)
    ref = first["process_ref"]
    assert ref["profile_id"] == env.profile["profile_id"] and ref["process_ids"] == ["plan"]
    assert set(ref["context_key"]) == set(CONTEXT)
    assert ref["verified_binding_refs"] == [] and ref["blockers"]
    assert "BOOTSTRAP" in ref["permitted_actions"] and "RUN" not in ref["permitted_actions"]
    # 실제 revalidate의 keyword-only 서명까지 통합 검증. 대역으로 호환 오류를 숨기지 않는다.
    approved = _decide(env, first)
    assert _approved(env, approved) == approved
    assert _count(env, "solution_blueprints") == _count(env, "advisor_v2_bootstraps") == 0


def test_real_draft_process_reference_is_preserved_but_not_executable(real_studio):
    env = real_studio
    change = _propose(env, [{"op": "RENAME", "process_id": "plan", "label": "검토 중"}], "pending-map")
    first = _save(env, process_selection={"kind": "DRAFT", "change_id": change["change_id"],
                                          "draft_digest": change["draft_digest"]})
    assert first["process_ref"]["state"] == "DRAFT"
    approved = _decide(env, first)
    _error(lambda: _approved(env, approved), "ADVISOR_PROCESS_CONTEXT_REQUIRED")
    assert _get(env, first) == approved


def test_real_viewer_cannot_save_and_foreign_actor_cannot_read(real_studio):
    env = real_studio
    first = _save(env)
    _error(lambda: _save(env, actor=env.org.VIEWER_A, client_request_id="viewer"), status=403)
    _error(lambda: _get(env, first, actor=env.other), status=404)
    _error(lambda: _decide(env, first, actor=env.author), status=403)
    assert _get(env, first) == first


def test_real_disabled_process_blocks_old_blueprint_bootstrap(real_studio):
    env = real_studio
    approved = _decide(env, _save(env))
    _approve_process(env, _propose(env, [{"op": "SET_USAGE", "process_id": "plan", "enabled": False}], "disable"))
    _error(lambda: _approved(env, approved), "PROCESS_DISABLED")
    assert _get(env, approved) == approved


def test_real_display_rename_does_not_replace_fixed_profile_reference(real_studio):
    env = real_studio
    approved = _decide(env, _save(env))
    current = _approve_process(env, _propose(env, [{"op": "RENAME", "process_id": "plan", "label": "표시만 변경"}], "rename"))
    assert current["profile_id"] != approved["process_ref"]["profile_id"]
    assert _approved(env, approved) == approved
