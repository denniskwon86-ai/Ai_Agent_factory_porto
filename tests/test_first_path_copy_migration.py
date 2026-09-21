"""[P05.1] 사본 이관·백업·복원 리허설 — 합성 자료로 **끝까지 이어서** 확인한다.

    합성 원본 → 일관 백업 → 별도 «새 schema» 로 행 이관 → 대사
              → 다른 빈 경로에 복원 → **제품 ECM 이 그것을 읽는다**

★ 출구는 「도구가 있다」가 아니라 **「복원된 것을 제품이 실제로 소비한다」**이다.
  README·설계·샘플 ZIP 은 여기서 아무것도 증명하지 않는다.

⚠️ 입력도 출력도 전부 `tmp_path`. 운영 `data/`·`library/`·실계정·`auth.db` 무접촉.
⚠️ 격리 러너는 저장소 `conftest.py` 를 읽지 않는다 — 스스로 격리한다.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3

import pytest

from core.db.managed_schema import ddl_statements, recording_factory
from core.enterprise_context.repository import EcmRepository

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_ROOT, "scripts", filename))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


mig = _load("_mig_under_test", "first_path_copy_migration.py")
snapshot = mig.snapshot
installer = mig.installer


def _sha(path) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _synthetic_source(tmp_path):
    """참조가 있는 최소 ECM 묶음. **합성 값만** 쓴다(`.invalid`/`_syn`)."""
    root = tmp_path / "source"
    (root / "data").mkdir(parents=True)
    (root / "output").mkdir(parents=True)
    installer.install(installer.SQLITE, ["enterprise_context"], str(root / "data"))
    conn = sqlite3.connect(root / "data" / "enterprise_context.db")
    try:
        conn.execute("INSERT INTO tenants VALUES "
                     "('t_syn','합성테넌트','','ACTIVE','2026-01-01','2026-01-01')")
        conn.execute("INSERT INTO enterprise_entities "
                     "(entity_id,tenant_id,name_ko,created_at,updated_at) VALUES "
                     "('e_syn','t_syn','합성법인','2026-01-01','2026-01-01')")
        for node, name in (("n_root", "합성본부"), ("n_child", "합성팀")):
            conn.execute(
                "INSERT INTO organization_nodes (node_id,entity_id,tenant_id,"
                "node_type,name_ko,status,created_at,updated_at) VALUES "
                "(?,?,?,?,?,'ACTIVE','2026-01-01','2026-01-01')",
                (node, "e_syn", "t_syn", "DIVISION", name))
        conn.execute("INSERT INTO organization_edges (edge_id,tenant_id,from_node_id,"
                     "to_node_id,relation_type,status,created_at) VALUES "
                     "('edge1','t_syn','n_root','n_child','OPERATING_PARENT',"
                     "'ACTIVE','2026-01-01')")
        conn.execute("INSERT INTO organization_node_code_aliases "
                     "(alias_id,node_id,code,tenant_id,recorded_at) VALUES "
                     "('a1','n_root','OLD_CODE','t_syn','2026-01-01')")
        conn.commit()
    finally:
        conn.close()
    #: 첨부 1건 — 기존 도구가 지원하는 형식(RAW CSV)만, **합성 값만**.
    #:   지시의 「첨부가 있으면 파일 digest 를 대사한다」를 실제로 누르기 위해서다.
    raw = root / "data" / "raw"
    raw.mkdir(parents=True)
    (raw / "synthetic_probe.csv").write_text(
        "node_id,metric,value\nn_root,합성지표,42\n", encoding="utf-8")
    return root


def _backup(root):
    """**기존 도구**로 일관 백업한다 — 새 백업 엔진을 만들지 않는다."""
    bundle = root / "output" / "bundle.afs"
    key = root / "output" / "key.txt"
    report = snapshot.export_snapshot(root, bundle, key, root / "output" / "r.json")
    return bundle, key, report


# ═══ ① 끝까지 이어지는 소비 ═════════════════════════════════════════════
def test_backup_migrate_restore_then_the_product_reads_it(tmp_path):
    """★★ 이 시험 하나가 P05.1 의 출구다 — **복원된 것을 제품이 읽는다.**"""
    root = _synthetic_source(tmp_path)
    source_db = root / "data" / "enterprise_context.db"
    before = _sha(source_db)
    bundle, key, public = _backup(root)

    #: 백업 도구가 «원본이 안 변했음» 을 스스로 보증한다.
    assert public["source_main_and_wal_unchanged"] is True
    assert public["requires_separate_key"] is True

    #: ② 별도 «새» schema 로 행 이관 + 대사
    target = tmp_path / "migrated"
    report = mig.run(bundle, key, target)
    assert report["ok"] is True, report["findings"]
    assert report["moved_rows"] == {"tenants": 1, "enterprise_entities": 1,
                                    "organization_nodes": 2, "organization_edges": 1,
                                    "organization_node_code_aliases": 1}
    assert report["bundle_unchanged"] is True

    #: ③ «다른 빈 경로» 에 복원
    restored_root = tmp_path / "restored"
    result = snapshot.restore_snapshot(bundle, key, restored_root, copy_only=True)
    assert result["credentials_restored"] is False
    restored_db = restored_root / "inspection-files" / "data" / "enterprise_context.db"
    assert restored_db.is_file()

    #: ④ **제품 ECM 이 복원본을 읽는다** — 관리 모드(P03.1 의 그 경로) 그대로.
    log: list = []
    repo = EcmRepository(db_path=str(restored_db),
                         connect=recording_factory(str(restored_db), log), managed=True)
    node = repo.get_node("n_root")
    assert node is not None and node.name_ko == "합성본부"
    assert node.tenant_id == "t_syn" and node.entity_id == "e_syn"
    assert repo.get_node("n_child").name_ko == "합성팀"
    assert ddl_statements(log) == [], "복원본을 읽는 데 DDL 이 돌았다"

    #: ⑤ 이관 대상도 제품이 읽는다(파일 복사가 아니라 «행이 앉았는지»).
    migrated_db = tmp_path / "migrated" / "data" / "enterprise_context.db"
    log2: list = []
    repo2 = EcmRepository(db_path=str(migrated_db),
                          connect=recording_factory(str(migrated_db), log2),
                          managed=True)
    assert repo2.get_node("n_child").name_ko == "합성팀"
    assert ddl_statements(log2) == []

    #: ⑥ 첨부(RAW CSV)도 **digest 로 대사**한다 — 건수만 세지 않는다.
    attachment = "data/raw/synthetic_probe.csv"
    manifest, files = snapshot.read_snapshot(bundle, key)
    assert attachment in files, list(files)
    original_bytes = (root / "data" / "raw" / "synthetic_probe.csv").read_bytes()
    restored_file = restored_root / "inspection-files" / attachment
    assert restored_file.is_file(), "첨부가 복원되지 않았다"
    assert restored_file.read_bytes() == original_bytes
    expected = hashlib.sha256(original_bytes).hexdigest()
    assert manifest["files"][attachment]["sha256"] == expected
    assert hashlib.sha256(restored_file.read_bytes()).hexdigest() == expected

    #: ⑦ 원본은 처음 그대로.
    assert _sha(source_db) == before


def test_the_bundle_carries_no_credentials(tmp_path):
    """⚠️ 기존 도구의 auth·credential 배제 목록을 **완화하지 않는다.**"""
    root = _synthetic_source(tmp_path)
    bundle, key, _ = _backup(root)
    _, files = snapshot.read_snapshot(bundle, key)
    assert not [n for n in files if "auth" in n or "credential" in n or "connector" in n]


# ═══ ② 대사가 «늘 ok» 가 아님 ═══════════════════════════════════════════
def test_the_reconciler_actually_catches_a_difference(tmp_path):
    """★ 음성 대조 — 대사가 늘 통과하면 ①의 초록은 아무 뜻이 없다."""
    root = _synthetic_source(tmp_path)
    bundle, key, _ = _backup(root)
    target = tmp_path / "migrated"
    assert mig.run(bundle, key, target)["ok"] is True

    migrated_db = target / "data" / "enterprise_context.db"
    conn = sqlite3.connect(migrated_db)
    try:
        conn.execute("DELETE FROM organization_nodes WHERE node_id='n_child'")
        conn.execute("UPDATE tenants SET name_ko='몰래 바꾼 이름'")
        conn.commit()
    finally:
        conn.close()

    source_copy = tmp_path / "src_copy.db"
    _, files = snapshot.read_snapshot(bundle, key)
    source_copy.write_bytes(files[mig.STORE_DB])
    again = mig.reconcile(source_copy, migrated_db)
    assert again["ok"] is False
    joined = " ".join(again["findings"])
    assert "organization_nodes" in joined and "tenants" in joined, again["findings"]
    #: 참조도 함께 끊겼음을 본다(간선이 사라진 노드를 가리킨다).
    assert any("참조 끊김" in f for f in again["findings"]), again["findings"]


# ═══ ③ 적용 «전에» 막는 경계 ════════════════════════════════════════════
def test_a_second_run_is_refused_not_silently_reused(tmp_path):
    """★ 재실행 계약을 애매하게 두지 않는다 — **명시적 거절**이다."""
    root = _synthetic_source(tmp_path)
    bundle, key, _ = _backup(root)
    target = tmp_path / "migrated"
    mig.run(bundle, key, target)
    with pytest.raises(mig.MigrationRefused):
        mig.run(bundle, key, target)


@pytest.mark.parametrize("kind", ["same", "nested-under-bundle", "bundle-under-target"])
def test_overlapping_paths_are_refused(tmp_path, kind):
    """⚠️ 상·하위로 겹치면 쓰는 도중에 읽는 것을 건드린다."""
    root = _synthetic_source(tmp_path)
    bundle, key, _ = _backup(root)
    target = {"same": bundle.parent,
              "nested-under-bundle": bundle.parent / "inside",
              "bundle-under-target": bundle.parent.parent}[kind]
    with pytest.raises(mig.MigrationRefused):
        mig.run(bundle, key, target)


def test_the_operational_data_dir_is_refused(tmp_path):
    """⚠️ 기준을 `PROJECT_ROOT` 로 **고정**한다 — 작업 디렉터리로 판단하면 격리 실행에서

    판정이 반대로 뒤집힌다."""
    root = _synthetic_source(tmp_path)
    bundle, key, _ = _backup(root)
    with pytest.raises(mig.MigrationRefused):
        mig.run(bundle, key, mig._OPERATIONAL / "p051_should_not_exist")
    assert not (mig._OPERATIONAL / "p051_should_not_exist").exists()


# ═══ ④ 실패 주입 — 원본도 기존 대상도 그대로 ═══════════════════════════
def test_a_mid_migration_failure_leaves_everything_as_it_was(tmp_path, monkeypatch):
    """★★ 중단·충돌 시 **부분 산출물을 ready 로 표시하지 않는다.**

    한 트랜잭션이므로 대상에 행이 남지 않고, 대사를 통과하지 못했으므로
    리포트도 쓰이지 않는다."""
    root = _synthetic_source(tmp_path)
    source_db = root / "data" / "enterprise_context.db"
    bundle, key, _ = _backup(root)
    first_target = tmp_path / "already_there"
    mig.run(bundle, key, first_target)

    source_before = _sha(source_db)
    bundle_before = _sha(bundle)
    existing_before = _sha(first_target / "data" / "enterprise_context.db")

    original = mig._read_rows

    def flaky(conn, table, columns):
        if table == "organization_nodes":
            raise sqlite3.OperationalError("주입: 이관 도중 실패")
        return original(conn, table, columns)

    monkeypatch.setattr(mig, "_read_rows", flaky)
    failed_target = tmp_path / "failed"
    with pytest.raises(sqlite3.OperationalError):
        mig.run(bundle, key, failed_target)

    assert _sha(source_db) == source_before, "원본이 변했다"
    assert _sha(bundle) == bundle_before, "번들이 변했다"
    assert _sha(first_target / "data" / "enterprise_context.db") == existing_before, \
        "기존 대상이 변했다"
    assert not (failed_target / "migration_report.json").exists(), \
        "실패한 산출물에 리포트가 남았다"

    broken = failed_target / "data" / "enterprise_context.db"
    if broken.is_file():
        conn = sqlite3.connect(broken)
        try:
            counts = [conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                      for t, _k, _c in mig.TABLES]
        finally:
            conn.close()
        assert counts == [0] * len(mig.TABLES), f"반쪽 이관이 남았다: {counts}"


def test_the_column_mapping_is_written_out_not_a_star_select():
    """⚠️ `SELECT *` 면 스키마가 달라졌을 때 «자리로» 맞춰진다 —

    tenant_id 에 entity_id 가 들어가는 사고가 조용히 난다. 이름으로 적혀 있어야 하고,
    그 이름은 **정본 DDL 에 실제로 있어야** 한다."""
    from core.db.managed_schema import REQUIRED, STORE_ENTERPRISE_CONTEXT

    mapped = {table: set(columns) for table, _key, columns in mig.TABLES}
    for table, required in REQUIRED[STORE_ENTERPRISE_CONTEXT].items():
        assert table in mapped, f"{table} 이 이관 대응표에 없다"
        missing = set(required) - mapped[table]
        assert not missing, f"{table}: 첫 경로 필수 컬럼이 빠졌다 {missing}"
