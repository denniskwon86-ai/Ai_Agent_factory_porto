"""실제 합성 cold 설치와 backup 복제의 동등성·독립성. 실행은 main 격리 runner만 한다."""
from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from tests import org_seed as org
from tests import b3_kit_seed as seeds
from tests.test_b3_kit_contract_v2 import (kit, installation, workspace, enforced_org,  # noqa: F401
    cold_kit, producer, draft, hold, error, _state)


def test_actual_cold_install_and_eight_certifications_equal_independent_backup(
        installation, monkeypatch, tmp_path, request):
    """캐시를 조회하지 않고 매 실행 실제 cold 설치·8인증을 수행하는 보존 시험이다."""
    cold = cold_kit(installation, monkeypatch)
    expected = producer(cold)
    before = _state(cold)
    seed = seeds.capture_seed(cold, tmp_path / "cold-sealed", run_id=id(request.session))
    with monkeypatch.context() as patch:
        cloned = seeds.clone_seed(seed, tmp_path / "cold-copy", patch, run_id=id(request.session))
        assert producer(cloned) == expected
        assert _state(cloned) == before
        assert cloned["instance_id"] == cold["instance_id"]
        assert cloned["fixed"] == cold["fixed"] and len(cloned["data"]) == 8
        for key in ("store", "directory", "ledger", "svc", "ctx", "install"):
            assert cloned[key] is not cold[key]
        assert cloned["svc"].repo is not cold["svc"].repo
        assert set(cloned["paths"].values()).isdisjoint(cold["paths"].values())
        assert all(p.is_relative_to(cloned["root"]) for p in cloned["paths"].values())
        assert Path(cloned["ledger"].db_path).is_relative_to(cloned["root"])
        assert cloned["ledger"].verify_chain()["ok"]
    assert _state(cold) == before and producer(cold) == expected
    seeds.validate_seed(seed, run_id=id(request.session))


@pytest.mark.parametrize("mutation", ["role", "hold", "contract"])
def test_role_hold_and_contract_changes_never_propagate_to_next_clone(
        kit, monkeypatch, tmp_path, request, mutation):
    seed = seeds.session_seed(request)
    baseline = producer(kit)
    if mutation == "role":
        kit["directory"].set_user_roles(org.MEMBER_A, {org.DEPT_A: "viewer"}, actor="test")
        error(lambda: producer(kit), 403, "PROCESS_ACTION_FORBIDDEN")
    elif mutation == "hold":
        hold(kit)
        error(lambda: producer(kit), 409, "DATA_USAGE_HOLD")
    else:
        assert draft(kit)["revision"] == 1
        assert draft(kit, expected_revision=1, app_class="personal")["revision"] == 2
    mutated = _state(kit)
    with monkeypatch.context() as patch:
        sibling = seeds.clone_seed(seed, tmp_path / "next-clone", patch, run_id=id(request.session))
        assert producer(sibling) == baseline
        assert sibling["fixed"] == kit["fixed"] and sibling["instance_id"] == kit["instance_id"]
        assert sibling["store"] is not kit["store"] and sibling["svc"].repo is not kit["svc"].repo
        assert sibling["directory"] is not kit["directory"] and sibling["ledger"] is not kit["ledger"]
        # 계약 변경도 독립이다. 깨끗한 복사본의 첫 계약은 언제나 revision 1이다.
        assert draft(sibling)["revision"] == 1
        assert sibling["ledger"].verify_chain()["ok"]
    assert _state(kit) == mutated
    seeds.validate_seed(seed, run_id=id(request.session))


def test_second_session_cache_use_never_repeats_cold_installer_or_certifier(
        kit, installation, monkeypatch, tmp_path, tmp_path_factory, request):
    original = seeds.session_seed(request)
    def forbidden(*_args):
        pytest.fail("두 번째 cache 사용이 cold 설치/인증을 반복했습니다.")
    with monkeypatch.context() as patch:
        second = seeds.cached_kit(request, {**installation, "root": tmp_path / "second-use"},
            patch, tmp_path_factory, forbidden)
        assert producer(second) == seeds.validate_seed(original, run_id=id(request.session))["contract"]
        assert second["root"] != kit["root"] and second["store"] is not kit["store"]
    assert seeds.session_seed(request) is original


@pytest.mark.parametrize("damage", ["payload", "source", "run", "database"])
def test_seed_tampering_or_cross_run_reuse_fails_closed_without_rebuilding(
        kit, tmp_path, request, damage):
    original = seeds.session_seed(request)
    if damage == "payload":
        damaged = replace(original, payload=original.payload + " ")
    elif damage == "source":
        damaged = replace(original, source_hash="0" * 64)
    elif damage == "run":
        damaged = replace(original, run_id=original.run_id + 1)
    else:
        # 공유 seed는 절대 고치지 않는다. 별도 backup 복사본만 손상시킨다.
        root = tmp_path / "tampered-seed"
        root.mkdir()
        databases = []
        for kind, filename, _, logical in original.databases:
            path = root / (kind + ".db")
            seeds._backup(Path(filename), path)
            assert seeds._signature(path, kind) == logical
            databases.append((kind, str(path), seeds._hash(path.read_bytes()), logical))
        damaged = replace(original, root=str(root), databases=tuple(databases))
        path = root / "org.db"
        assert path.resolve().is_relative_to(tmp_path.resolve())
        conn = sqlite3.connect(str(path))
        try:
            with conn:
                conn.execute("UPDATE users SET display_name=? WHERE user_id=?", ("손상된 합성 이름", org.MEMBER_A))
        finally:
            conn.close()
    with pytest.raises(seeds.SeedIntegrityError):
        seeds.validate_seed(damaged, run_id=id(request.session))
    assert seeds.validate_seed(original, run_id=id(request.session))["instance_id"] == kit["instance_id"]


def test_restored_global_aliases_nodes_and_ledger_paths_match_current_clone(kit):
    from core.org_directory import org_directory
    from core.decision_ledger import decision_ledger
    from core.enterprise_context.repository import ecm_repository
    from core.data_preparation.store import data_preparation_store
    assert org_directory is kit["directory"] and decision_ledger is kit["ledger"]
    assert ecm_repository is kit["svc"].repo and data_preparation_store is kit["store"]
    assert org.NODES[org.DEPT_A] == kit["context"]["scope_node_id"]
    assert org.NODES[org.DEPT_ROOT] == kit["boundary"].context_root_id
    assert all(Path(obj.db_path).resolve().is_relative_to(kit["root"])
               for obj in (org_directory, decision_ledger, ecm_repository, data_preparation_store))
    assert decision_ledger.verify_chain()["ok"]
