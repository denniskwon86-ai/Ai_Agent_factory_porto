"""B1 승인설계 §6/12/14: 부정·경합·회수·원자성 회귀 25개.

메인 담당의 audit 격리 runner 전용이다. 전역 conftest나 운영 DB에 기대지 않고
tests.usage_hold_test_plugin의 enforced_org 및 .invalid 합성 계정만 사용한다.
수집 시 저장소를 만들지 않는다. 직접 SQL은 경로 검증한 tmp fixture에만 사용한다.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def b1(enforced_org, tmp_path):
    from core.enterprise_context.process_configuration import ProcessConfigurationService
    from core.enterprise_context.process_schema import ProcessBoundary
    from core.enterprise_context.repository import ecm_repository
    from core.org_directory import org_directory

    root = tmp_path.resolve()
    db_path = Path(ecm_repository.db_path).resolve()
    org_path = Path(org_directory.db_path).resolve()
    assert db_path.is_relative_to(root) and org_path.is_relative_to(root)
    assert db_path.is_file() and org_path.is_file()
    seed = enforced_org
    boundary = ProcessBoundary(
        tenant_id="tenant_default", context_root_id=seed.NODES[seed.DEPT_ROOT],
        entity_mode="REAL", scope_node_id=seed.NODES[seed.DEPT_A],
    )
    return SimpleNamespace(
        root=root, db_path=db_path, org_path=org_path, repo=ecm_repository,
        directory=org_directory, seed=seed, boundary=boundary,
        context={"tenant_id": boundary.tenant_id, "entity_mode": boundary.entity_mode,
                 "scope_node_id": boundary.scope_node_id},
        service=ProcessConfigurationService(ecm_repository),
    )


@contextmanager
def _db(env):
    """고장 주입·영속 결과 확인용 연결도 tmp 밖이면 열지 않는다."""
    path = env.db_path.resolve()
    assert path.is_relative_to(env.root) and path.is_file()
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _state(env):
    tables = {
        "enterprise_profiles": "profile_id",
        "enterprise_process_heads": "configuration_id",
        "enterprise_process_changes": "change_id",
        "enterprise_process_outbox": "event_id",
    }
    with _db(env) as conn:
        conn.execute("BEGIN")
        return {table: [dict(row) for row in conn.execute(
            f"SELECT * FROM {table} ORDER BY {key}"
        )] for table, key in tables.items()}


def _read(env, **kwargs):
    args = dict(boundary=env.boundary, actor=env.seed.MEMBER_A, context=env.context)
    return env.service.resolved(**{**args, **kwargs})


def _propose(env, *, key="initial", commands=None, actor=None, **overrides):
    current = _read(env)
    if commands is None:
        commands = [
            {"op": "ADD_NODE", "node": {"process_id": "adversarial_l1", "level": "L1",
                                        "label": "합성 원료구매"}},
            {"op": "ADD_NODE", "node": {"process_id": "adversarial_l2", "level": "L2",
                                        "parent_process_id": "adversarial_l1",
                                        "label": "합성 구매계획"}},
        ]
    args = dict(
        boundary=env.boundary, actor=actor or env.seed.MEMBER_A, context=env.context,
        commands=commands, expected_head_version=current["head_version"],
        base_profile_id=current["profile_id"], base_fingerprint=current["digest"],
        client_request_id=key, reason="격리된 B1 변경 제안", legacy_token=current["legacy_token"],
    )
    return env.service.propose(**{**args, **overrides})


def _approval_args(env, change, **overrides):
    return {
        "change_id": change["change_id"], "actor": env.seed.MANAGER_A,
        "context": env.context, "expected_head_version": change["base_head_version"],
        "draft_digest": change["draft_digest"], "reason": "격리된 B1 독립 검토",
        **overrides,
    }


def _approve(env, change, **overrides):
    return env.service.approve(**_approval_args(env, change, **overrides))


def _installed(env):
    change = _propose(env)
    return change, _approve(env, change)


def _rename(env, *, key="rename", label="합성 구매계획 개정", actor=None):
    return _propose(env, key=key, actor=actor, commands=[
        {"op": "RENAME", "process_id": "adversarial_l2", "label": label},
    ])


def _error(call, status, reason, *, hidden=()):
    from core.enterprise_context.process_schema import ProcessError

    with pytest.raises(ProcessError) as raised:
        call()
    error = raised.value
    assert error.status_code == status
    assert error.reason_code == reason
    visible_error = f"{error.reason_code} {error}"
    assert all(secret not in visible_error for secret in hidden if secret)
    return error


def _other_repository(env):
    from core.enterprise_context.repository import EcmRepository

    assert env.db_path.is_relative_to(env.root)
    return EcmRepository(db_path=str(env.db_path))


def _other_directory(env):
    from core.org_directory import OrgDirectory

    assert env.org_path.is_relative_to(env.root)
    return OrgDirectory(db_path=str(env.org_path))


def test_two_repository_approvals_have_one_winner_and_one_head_conflict(b1):
    from core.enterprise_context.process_configuration import ProcessConfigurationService
    from core.enterprise_context.process_schema import ProcessError

    first = _propose(b1, key="race-first")
    second = _propose(b1, key="race-second")
    other_repo = _other_repository(b1)
    assert other_repo is not b1.repo and other_repo._lock is not b1.repo._lock
    other_service = ProcessConfigurationService(other_repo)
    barrier = threading.Barrier(2)

    def attempt(service, change, actor):
        barrier.wait(timeout=10)
        try:
            return service.approve(**_approval_args(b1, change, actor=actor))
        except ProcessError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(attempt, b1.service, first, b1.seed.MANAGER_A),
            pool.submit(attempt, other_service, second, b1.seed.MANAGER_ROOT),
        ]
        results = [future.result(timeout=20) for future in futures]
    winners = [result for result in results if isinstance(result, dict)]
    conflicts = [result for result in results if isinstance(result, ProcessError)]
    assert len(winners) == len(conflicts) == 1
    assert (conflicts[0].status_code, conflicts[0].reason_code) == (409, "PROCESS_HEAD_CONFLICT")
    state = _state(b1)
    assert len(state["enterprise_process_heads"]) == 1
    assert state["enterprise_process_heads"][0]["head_version"] == 1
    assert state["enterprise_process_heads"][0]["active_profile_id"] == winners[0]["profile_id"]
    assert sorted(row["status"] for row in state["enterprise_profiles"]) == ["ACTIVE", "DRAFT"]
    assert sorted(row["status"] for row in state["enterprise_process_changes"]) == ["APPLIED", "DRAFT"]
    assert len(state["enterprise_process_outbox"]) == 1
    assert state["enterprise_process_outbox"][0]["event_id"] == winners[0]["event_id"]


def test_legacy_writer_before_first_v2_approval_invalidates_transition(b1):
    from core.enterprise_context.models import EnterpriseProfile

    change = _propose(b1)
    legacy = _other_repository(b1).upsert_profile(EnterpriseProfile(
        profile_id="adversarial-legacy-before-approval", tenant_id=b1.boundary.tenant_id,
        scope_node_id=b1.boundary.scope_node_id, profile_kind="process_profile",
        payload={"nodes": [{"key": "legacy", "label": "검토 후 바뀐 합성 v1", "overlay": None}]},
    ))
    before = _state(b1)
    _error(lambda: _approve(b1, change), 409, "PROCESS_LEGACY_CONFLICT")
    assert _state(b1) == before
    assert any(row["profile_id"] == legacy.profile_id for row in before["enterprise_profiles"])
    assert before["enterprise_process_heads"][0]["head_version"] == 0
    assert before["enterprise_process_outbox"] == []


def test_v2_approval_blocks_later_flat_writer_on_separate_repository(b1):
    from core.enterprise_context.models import EnterpriseProfile

    _installed(b1)
    before = _state(b1)
    other = _other_repository(b1)
    _error(lambda: other.upsert_profile(EnterpriseProfile(
        tenant_id=b1.boundary.tenant_id, scope_node_id=b1.boundary.scope_node_id,
        profile_kind="process_profile", payload={"nodes": []},
    )), 409, "PROCESS_SCHEMA_UPGRADE_REQUIRED")
    assert _state(b1) == before
    assert {node["level"] for node in _read(b1)["payload"]["nodes"]} == {"L1", "L2"}


@pytest.mark.parametrize("spoofed_kind", ["process_profile", "data_profile"])
def test_old_writer_checks_stored_v2_id_not_spoofed_kind_or_scope(b1, spoofed_kind):
    from core.enterprise_context.models import EnterpriseProfile

    _installed(b1)
    draft = _rename(b1)
    before = _state(b1)
    other = _other_repository(b1)
    # 승인판 트리거에 기대지 않는다. 아직 DRAFT인 v2 ID를 미전환 B 조직으로 위장한다.
    _error(lambda: other.upsert_profile(EnterpriseProfile(
        profile_id=draft["draft_profile_id"], tenant_id=b1.boundary.tenant_id,
        scope_node_id=b1.seed.NODES[b1.seed.DEPT_B], profile_kind=spoofed_kind,
        payload={"nodes": []}, status="DRAFT",
    )), 409, "PROCESS_SCHEMA_UPGRADE_REQUIRED")
    assert _state(b1) == before


@pytest.mark.parametrize("stored_status", ["ACTIVE", "ARCHIVED"])
def test_old_approval_cannot_reapprove_or_reactivate_v2(b1, stored_status):
    _, initial = _installed(b1)
    if stored_status == "ARCHIVED":
        _approve(b1, _rename(b1))
    before = _state(b1)
    row = next(row for row in before["enterprise_profiles"] if row["profile_id"] == initial["profile_id"])
    assert row["status"] == stored_status
    other = _other_repository(b1)
    _error(lambda: other.approve_profile(
        initial["profile_id"], actor=b1.seed.MANAGER_ROOT, tenant_id=b1.boundary.tenant_id,
    ), 409, "PROCESS_SCHEMA_UPGRADE_REQUIRED")
    assert _state(b1) == before


def test_old_writer_cannot_inject_v2_before_a_head_exists(b1):
    from core.enterprise_context.models import EnterpriseProfile
    from core.enterprise_context.process_schema import ProcessDocument

    before = _state(b1)
    assert before["enterprise_process_heads"] == []
    document = ProcessDocument(configuration_id="adversarial-forged-config").model_dump()
    _error(lambda: b1.repo.upsert_profile(EnterpriseProfile(
        tenant_id=b1.boundary.tenant_id, scope_node_id=b1.boundary.scope_node_id,
        profile_kind="process_profile", payload=document,
    )), 409, "PROCESS_SCHEMA_UPGRADE_REQUIRED")
    assert _state(b1) == before


@pytest.mark.parametrize("existing_approval", [False, True], ids=["first-approval", "next-revision"])
def test_outbox_insert_failure_rolls_back_profile_head_change_and_allows_retry(b1, existing_approval):
    if existing_approval:
        _installed(b1)
        change = _rename(b1)
    else:
        change = _propose(b1)
    before = _state(b1)
    # 승인 트랜잭션의 마지막 INSERT만 실제 SQLite 오류로 실패시킨다.
    with _db(b1) as conn:
        conn.execute("""CREATE TRIGGER b1_adversarial_outbox_failure
            BEFORE INSERT ON enterprise_process_outbox
            BEGIN SELECT RAISE(ABORT, 'B1 합성 outbox 저장 실패'); END""")
    _error(lambda: _approve(b1, change), 503, "PROCESS_STORAGE_UNAVAILABLE")
    assert _state(b1) == before
    with _db(b1) as conn:
        conn.execute("DROP TRIGGER b1_adversarial_outbox_failure")
    result = _approve(b1, change)
    assert result["status"] == "APPLIED"
    assert result["head_version"] == change["base_head_version"] + 1
    assert result["audit_delivery"] == "PENDING"
    after = _state(b1)
    assert len(after["enterprise_process_outbox"]) == len(before["enterprise_process_outbox"]) + 1
    assert _approve(b1, change) == result
    assert _state(b1) == after


def test_retired_reviewer_cannot_approve_even_with_warmed_scope_cache(b1):
    change = _propose(b1)
    reviewer = b1.seed.MANAGER_A
    cached = b1.directory.resolve_scope(reviewer)
    assert b1.seed.DEPT_A in cached.manageable_dept_ids
    other = _other_directory(b1)
    assert other.delete_user(reviewer, actor=b1.seed.ADMIN)
    assert b1.directory.resolve_scope(reviewer) is cached
    before = _state(b1)
    _error(lambda: _approve(b1, change), 403, "PROCESS_ACTOR_INELIGIBLE")
    assert _state(b1) == before


def test_other_instance_role_revocation_rechecks_publish_scope_fresh(b1):
    change = _propose(b1)
    reviewer = b1.seed.MANAGER_A
    b1.directory.set_user_roles(reviewer, {
        b1.seed.DEPT_A: "manager", b1.seed.DEPT_B: "manager",
    }, actor=b1.seed.ADMIN)
    cached = b1.directory.resolve_scope(reviewer)
    assert b1.seed.DEPT_A in cached.manageable_dept_ids
    other = _other_directory(b1)
    # B의 manager 권한은 유지: 전역 capability 유무만 재확인하면 이 시험을 통과하지 못한다.
    other.set_user_roles(reviewer, {
        b1.seed.DEPT_A: "viewer", b1.seed.DEPT_B: "manager",
    }, actor=b1.seed.ADMIN)
    assert b1.directory.resolve_scope(reviewer) is cached
    before = _state(b1)
    _error(lambda: _approve(b1, change), 403, "PROCESS_ACTION_FORBIDDEN")
    assert _state(b1) == before


def test_other_instance_read_role_revocation_hides_profile_and_events(b1):
    _, approved = _installed(b1)
    reader = b1.seed.MEMBER_B
    b1.directory.set_user_roles(reader, {
        b1.seed.DEPT_A: "viewer", b1.seed.DEPT_B: "member",
    }, actor=b1.seed.ADMIN)
    cached = b1.directory.resolve_scope(reader)
    assert b1.seed.DEPT_A in cached.readable_dept_ids
    assert _read(b1, actor=reader)["profile_id"] == approved["profile_id"]
    assert len(b1.service.events(boundary=b1.boundary, actor=reader, context=b1.context)) == 1
    _other_directory(b1).set_user_roles(
        reader, {b1.seed.DEPT_B: "member"}, actor=b1.seed.ADMIN,
    )
    assert b1.directory.resolve_scope(reader) is cached
    before = _state(b1)
    hidden = (approved["profile_id"], approved["event_id"], approved["configuration_id"])
    _error(lambda: _read(b1, actor=reader), 404, "PROCESS_NOT_FOUND", hidden=hidden)
    _error(lambda: b1.service.events(
        boundary=b1.boundary, actor=reader, context=b1.context,
    ), 404, "PROCESS_NOT_FOUND", hidden=hidden)
    assert _state(b1) == before


def test_qualified_author_cannot_publish_own_structural_change(b1):
    _installed(b1)
    change = _propose(b1, key="self-review", actor=b1.seed.MANAGER_A, commands=[
        {"op": "ADD_NODE", "node": {"process_id": "self-added-l2", "level": "L2",
                                    "parent_process_id": "adversarial_l1", "label": "합성 발주"}},
    ])
    before = _state(b1)
    _error(lambda: _approve(b1, change), 403, "PROCESS_DISTINCT_REVIEWER_REQUIRED")
    assert _state(b1) == before
    assert _approve(b1, change, actor=b1.seed.MANAGER_ROOT)["status"] == "APPLIED"


def test_same_proposal_request_key_cannot_replace_draft_body(b1):
    first = _propose(b1, key="fixed-request")
    before = _state(b1)
    assert _propose(b1, key="fixed-request") == first
    _error(lambda: _propose(b1, key="fixed-request", reason="같은 키로 바꾼 요청"),
           409, "PROCESS_IDEMPOTENCY_CONFLICT")
    assert _state(b1) == before


@pytest.mark.parametrize("dimension", ["tenant", "root", "mode", "scope"])
def test_wrong_context_hides_known_profile_change_and_event_even_from_admin(b1, dimension):
    from core.enterprise_context.models import EnterpriseEntity, OrganizationNode

    _, approved = _installed(b1)
    draft = _rename(b1)
    context = dict(b1.context)
    if dimension in ("tenant", "root"):
        tenant = "adversarial-other-tenant" if dimension == "tenant" else b1.boundary.tenant_id
        entity_id, node_id = f"adversarial-{dimension}-entity", f"adversarial-{dimension}-root"
        b1.repo.upsert_entity(EnterpriseEntity(
            entity_id=entity_id, tenant_id=tenant, entity_mode="REAL", name_ko="합성 다른 법인",
            legal_name="합성 다른 법인", status="ACTIVE",
        ))
        b1.repo.upsert_node(OrganizationNode(
            node_id=node_id, tenant_id=tenant, entity_id=entity_id,
            node_type="business_division", name_ko="합성 다른 루트", status="ACTIVE",
        ))
        context.update(tenant_id=tenant, scope_node_id=node_id)
    elif dimension == "mode":
        context.update(entity_mode="VIRTUAL", scope_node_id=b1.seed.NODES[b1.seed.VIRTUAL_CODE_B])
    else:
        context["scope_node_id"] = b1.seed.NODES[b1.seed.DEPT_B]
    before = _state(b1)
    hidden = (approved["profile_id"], approved["event_id"], approved["configuration_id"],
              draft["change_id"], draft["draft_profile_id"], "합성 구매계획")
    _error(lambda: _read(b1, actor=b1.seed.ADMIN, context=context, profile_id=approved["profile_id"]),
           404, "PROCESS_NOT_FOUND", hidden=hidden)
    _error(lambda: b1.service.validate(
        change_id=draft["change_id"], actor=b1.seed.ADMIN, context=context,
        draft_digest=draft["draft_digest"],
    ), 404, "PROCESS_NOT_FOUND", hidden=hidden)
    _error(lambda: b1.service.events(
        boundary=b1.boundary, actor=b1.seed.ADMIN, context=context,
    ), 404, "PROCESS_NOT_FOUND", hidden=hidden)
    assert _state(b1) == before


@pytest.mark.parametrize("damage", ["malformed-json", "unsupported-schema", "dangling-parent", "digest-only"])
def test_corrupt_approved_payload_fails_closed_instead_of_legacy_fallback(b1, damage):
    _, approved = _installed(b1)
    document = copy.deepcopy(_read(b1)["payload"])
    if damage == "unsupported-schema":
        document["schema_version"] = 999
    elif damage == "dangling-parent":
        document["nodes"][1]["parent_process_id"] = "nonexistent-parent"
    elif damage == "digest-only":
        document["nodes"][1]["label"] = "승인 지문과 다른 합성 표시명"
    raw = "{invalid-json" if damage == "malformed-json" else json.dumps(document, ensure_ascii=False)
    with _db(b1) as conn:
        # 저장장치 손상을 모사한다. tmp 트리거를 같은 연결에서 원형 복구한 뒤 조회한다.
        trigger = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' "
                               "AND name='process_profile_immutable_update'").fetchone()
        assert trigger and trigger[0]
        conn.execute("DROP TRIGGER process_profile_immutable_update")
        conn.execute("UPDATE enterprise_profiles SET payload_json=? WHERE profile_id=?",
                     (raw, approved["profile_id"]))
        conn.execute(trigger[0])
    before = _state(b1)
    _error(lambda: _read(b1), 503, "PROCESS_PROFILE_UNAVAILABLE")
    _error(lambda: _read(b1, profile_id=approved["profile_id"]), 503, "PROCESS_PROFILE_UNAVAILABLE")
    assert _state(b1) == before


def test_wrong_base_fingerprint_cannot_create_partial_draft(b1):
    _installed(b1)
    before = _state(b1)
    _error(lambda: _propose(b1, key="bad-fingerprint", base_fingerprint="0" * 64, commands=[
        {"op": "RENAME", "process_id": "adversarial_l2", "label": "합성 변경"},
    ]), 409, "PROCESS_DIGEST_CONFLICT")
    assert _state(b1) == before


def test_ecm_connection_failure_is_503_not_an_unconfigured_success(b1, monkeypatch):
    _installed(b1)
    before = _state(b1)

    def unavailable():
        raise sqlite3.OperationalError("B1 합성 ECM 연결 실패")

    monkeypatch.setattr(b1.repo, "_connect", unavailable)
    _error(lambda: _read(b1), 503, "PROCESS_STORAGE_UNAVAILABLE")
    assert _state(b1) == before
