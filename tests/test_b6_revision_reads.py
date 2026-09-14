"""B6 RevisionStore 읽기 전용 계약. 실행은 main의 strict-writes 격리 런너만 담당한다.

B3 연결 대역과 실제 판본/승인/예약 생성 함수를 재사용한다. 정책/PDP/API를
검증한 것으로 보지 않는다. 모든 합성 DB와 손상 주입은 각 tmp_path 안에서만 한다.
읽기 구간의 SQL은 본문 대신 첫 명령어만 수집한다. 실패 시 원문 SQL을 출력하지 않는다.
mode=ro도 WAL 공유메모리 보조파일을 만들 수 있다. DB 본체·비보조파일 무변경과
SQL DDL/DML 0을 검사하며 전체 파일 무변경을 주장하지 않는다. immutable 우회는 없다.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace

import pytest

from core.advisor_revision_store import RevisionStore, RevisionStoreError
from tests.test_b3_advisor_revisions import (
    AUTHOR, CONTEXT, OTHER, REVIEWER, _AdvisorConnection, _advance, _db,
    _decide, _finish, _reserve, _save, env,
)


_READ_SQL = {"SELECT", "BEGIN", "COMMIT", "ROLLBACK", "PRAGMA_TABLE_INFO"}


def _safe_test_path(path, root):
    if not path.resolve().is_relative_to(root):
        return False
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            return False
        if part == root:
            return True
    return False


def _is_sqlite_aux(path, database, root):
    """시험이 지정한 DB 하나의 정확한 보조파일만 분리한다. 링크/외부 경로는 제외 불가."""
    return (
        _safe_test_path(path, root) and _safe_test_path(database, root)
        and database.suffix == ".db" and database.is_file()
        and path in (Path(str(database) + "-wal"), Path(str(database) + "-shm"))
    )


def _files(root, database=None):
    """DB 본체·비SQLite보조파일의 해시. WAL/SHM의 물리 생성은 별도 회귀로 확인한다."""
    root = Path(root).resolve()
    database = Path(database) if database is not None else root / "advisor.db"
    result = {}
    for path in root.rglob("*"):
        assert _safe_test_path(path, root), "시험 해시 범위에 링크 또는 외부 경로가 있음"
        if path.is_file() and not _is_sqlite_aux(path, database, root):
            result[str(path.relative_to(root))] = sha256(path.read_bytes()).hexdigest()
    return result


def _unavailable(call, code="ADVISOR_STORAGE_UNAVAILABLE", status=503):
    with pytest.raises(RevisionStoreError) as caught:
        call()
    assert caught.value.reason_code == code
    assert caught.value.status_code == status


def _reader(case, monkeypatch, statements=None):
    """준비/쓰기용 연결을 차단한다. 실제 sqlite3.connect·격리 guard는 우회하지 않는다."""
    def forbidden(*args, **kwargs):
        raise AssertionError("읽기 모드에서 준비/쓰기용 연결을 호출함")

    service = RevisionStore(case.adapter, read_only=True)
    monkeypatch.setattr(case.adapter, "_connect", forbidden)
    monkeypatch.setattr(service, "_ensure", forbidden)
    if statements is not None:
        connect = sqlite3.connect

        def traced(*args, **kwargs):
            # 기존 런너가 감싼 connect를 그대로 거친다. URI allowlist 면제는 없다.
            conn = connect(*args, **kwargs)
            def trace(sql):
                verb = sql.strip().split(None, 1)[0].upper()
                if verb == "PRAGMA":
                    match = re.fullmatch(
                        r"\s*PRAGMA\s+table_info\(advisor_v2_(drafts|revisions|requests|bootstraps|transitions)\)\s*;?\s*",
                        sql, re.IGNORECASE)
                    verb = "PRAGMA_TABLE_INFO" if match else "PRAGMA_OTHER"
                statements.append(verb)
            conn.set_trace_callback(trace)
            return conn

        monkeypatch.setattr(sqlite3, "connect", traced)
    return service


def _case(path, root):
    adapter = _AdvisorConnection(path, root)
    return SimpleNamespace(adapter=adapter, root=root, service=RevisionStore(adapter))


def test_readonly_constructor_does_not_create_missing_parent_or_connect(tmp_path, monkeypatch):
    case = _case(tmp_path / "absent" / "advisor.db", tmp_path)
    before = _files(tmp_path)
    reader = _reader(case, monkeypatch)
    assert reader is not None
    assert not (tmp_path / "absent").exists()
    assert _files(tmp_path) == before


def test_cold_legacy_oracle_has_no_ddl_and_keeps_database_and_nonaux_hashes(env, monkeypatch):
    before = _files(env.root)
    statements = []
    reader = _reader(env, monkeypatch, statements)
    assert reader.is_v2_project("legacy_project") is False
    assert reader.is_v2_project("legacy_project") is False
    with reader._transaction() as conn:
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'advisor_v2_%'"
        ).fetchall() == []
        assert conn.execute("SELECT COUNT(*) FROM consultations").fetchone()[0] == 1
    assert statements
    assert set(statements) <= _READ_SQL
    assert _files(env.root) == before


def test_aux_filter_excludes_only_exact_sidecars_of_existing_db(tmp_path):
    names = ("anchor.db", "anchor.db-wal", "anchor.db-shm", "other.db", "other.db-wal", "orphan.db-wal",
             "orphan.db-shm", "notes-wal", "other.txt", "other.txt-shm", "anchor.db-wal.extra")
    for name in names:
        (tmp_path / name).write_bytes(b"SYNTHETIC")
    assert set(_files(tmp_path, tmp_path / "anchor.db")) == set(names) - {"anchor.db-wal", "anchor.db-shm"}
    (tmp_path / "orphan.db-wal").write_bytes(b"CHANGED_SYNTHETIC")
    assert _files(tmp_path, tmp_path / "anchor.db")["orphan.db-wal"] == sha256(b"CHANGED_SYNTHETIC").hexdigest()
    assert not _is_sqlite_aux(tmp_path / "other.db-wal", tmp_path / "anchor.db", tmp_path)
    assert not _is_sqlite_aux(tmp_path.parent / "outside.db-wal", tmp_path.parent / "outside.db", tmp_path)


def test_cold_read_can_create_empty_wal_and_shm_without_sql_or_database_writes(env, monkeypatch):
    database = Path(env.adapter.db_path)
    wal, shm = Path(str(database) + "-wal"), Path(str(database) + "-shm")
    assert not wal.exists() and not shm.exists()
    before = _files(env.root)
    statements = []
    reader = _reader(env, monkeypatch, statements)
    assert reader.is_v2_project("legacy_project") is False
    with reader._transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM consultations").fetchone()[0] == 1
        # 읽는 중 WAL/SHM은 존재할 수 있다. WAL에 데이터 프레임이 추가된 것은 아니다.
        assert wal.is_file() and wal.stat().st_size == 0
        assert shm.is_file() and shm.stat().st_size > 0
        assert _files(env.root) == before
    assert statements
    assert set(statements) <= _READ_SQL
    assert _files(env.root) == before


def test_readonly_sees_committed_reservation_in_live_uncheckpointed_wal(env, monkeypatch):
    database = Path(env.adapter.db_path)
    wal = Path(str(database) + "-wal")
    keeper = env.adapter._connect()
    try:
        # 별도 읽기 snapshot을 유지해 이후 쓰기 커밋이 DB 본체로 checkpoint되지 않게 한다.
        keeper.execute("PRAGMA wal_autocheckpoint=0")
        keeper.execute("BEGIN")
        assert keeper.execute("SELECT COUNT(*) FROM consultations").fetchone()[0] == 1
        main_before_writes = sha256(database.read_bytes()).hexdigest()
        approved = _decide(env, _save(env))
        reserved = _reserve(env, approved)
        writer = _case(database, env.root)
        writer.service._ensure()
        assert keeper.in_transaction
        assert wal.is_file() and wal.stat().st_size > 32
        assert sha256(database.read_bytes()).hexdigest() == main_before_writes
        before = _files(env.root)
        wal_before = sha256(wal.read_bytes()).hexdigest()
        statements = []
        reader = _reader(env, monkeypatch, statements)
        assert reader.is_v2_project(reserved["project_id"]) is True
        assert reader.get_for_project(boundary=CONTEXT, project_id=reserved["project_id"]) == reserved
        assert reader.get(boundary=CONTEXT, actor=AUTHOR, operation_id=reserved["operation_id"]) == reserved
        assert reader.get(boundary=CONTEXT, actor=REVIEWER,
                          approved_revision_id=approved["approved_revision_id"]) == approved
        assert _files(env.root) == before
        assert sha256(wal.read_bytes()).hexdigest() == wal_before
        assert set(statements) <= _READ_SQL
        # 첫 RO 조회가 닫힌 뒤 독립 writer의 다음 커밋도 새 RO transaction에 보여야 한다.
        second = _reserve(writer, approved, actor=OTHER, client_request_id="bootstrap-live-2")
        assert second["project_id"] != reserved["project_id"]
        assert keeper.in_transaction
        assert sha256(database.read_bytes()).hexdigest() == main_before_writes
        before_second = _files(env.root)
        wal_second = sha256(wal.read_bytes()).hexdigest()
        statements.clear()  # 위 합성 writer 구간과 다음 순수 읽기 구간을 명시 분리한다.
        assert reader.is_v2_project(second["project_id"]) is True
        assert reader.get_for_project(boundary=CONTEXT, project_id=second["project_id"]) == second
        assert reader.get(boundary=CONTEXT, actor=OTHER, operation_id=second["operation_id"]) == second
        assert _files(env.root) == before_second
        assert sha256(wal.read_bytes()).hexdigest() == wal_second
        assert set(statements) <= _READ_SQL
    finally:
        # 정리 시 checkpoint 가능성은 fixture 정리이며 위 읽기 구간과 분리한다.
        keeper.rollback()
        keeper.close()


def test_reserved_v2_reads_approved_source_and_exact_operation_without_writes(env, monkeypatch):
    approved = _decide(env, _save(env))
    reserved = _reserve(env, approved)
    before = _files(env.root)
    statements = []
    reader = _reader(env, monkeypatch, statements)
    assert reader.is_v2_project(reserved["project_id"]) is True
    result = reader.get(boundary=CONTEXT, actor=REVIEWER,
                        approved_revision_id=approved["approved_revision_id"])
    assert result == approved
    assert reader.get(boundary=CONTEXT, actor=AUTHOR, operation_id=reserved["operation_id"]) == reserved
    assert reader.get_for_project(boundary=CONTEXT, project_id=reserved["project_id"]) == reserved
    # 호출자가 받은 복사본을 바꿔도 저장 원문은 그대로다.
    result["blueprint"]["title"] = "응답 사본 변경"
    assert reader.get(boundary=CONTEXT, actor=REVIEWER,
                      approved_revision_id=approved["approved_revision_id"]) == approved
    assert set(statements) <= _READ_SQL
    assert _files(env.root) == before


def test_completed_v2_readback_matches_default_writer_result(env, monkeypatch):
    approved = _decide(env, _save(env))
    completed = _finish(env, _reserve(env, approved))
    before = _files(env.root)
    reader = _reader(env, monkeypatch)
    assert reader.is_v2_project(completed["project_id"]) is True
    assert reader.get_for_project(boundary=CONTEXT, project_id=completed["project_id"]) == completed
    assert reader.get(boundary=CONTEXT, actor=AUTHOR, draft_id=approved["draft_id"]) == approved
    assert _files(env.root) == before


def test_prepared_v2_unknown_project_is_false_and_none_without_mutation(env, monkeypatch):
    _save(env)
    before = _files(env.root)
    reader = _reader(env, monkeypatch)
    assert reader.is_v2_project("unknown_project") is False
    assert reader.get_for_project(boundary=CONTEXT, project_id="unknown_project") is None
    assert _files(env.root) == before


def test_public_mutators_reject_readonly_even_with_valid_existing_inputs(env, monkeypatch):
    draft = _save(env)
    approved = _decide(env, draft)
    reserved = _reserve(env, approved)
    before = _files(env.root)
    env.service = _reader(env, monkeypatch)
    actions = [
        lambda: _save(env, approved, client_request_id="readonly-save"),
        lambda: _decide(env, draft),
        lambda: _reserve(env, approved),
        lambda: _advance(env, reserved, "PROVISIONING"),
    ]
    for action in actions:
        _unavailable(action, "ADVISOR_READ_ONLY")
    assert _files(env.root) == before


def test_write_transaction_fails_before_opening_missing_database(tmp_path, monkeypatch):
    case = _case(tmp_path / "missing-parent" / "advisor.db", tmp_path)
    reader = _reader(case, monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("write=True 거절 전에 SQLite 연결을 시도함")

    monkeypatch.setattr(sqlite3, "connect", forbidden)

    def attempt():
        with reader._transaction(write=True):
            raise AssertionError("읽기 전용 쓰기 transaction 본문에 진입함")

    _unavailable(attempt, "ADVISOR_READ_ONLY")
    assert not (tmp_path / "missing-parent").exists()


def test_readonly_connection_itself_blocks_sql_writes_and_closes(env, monkeypatch):
    before = _files(env.root)
    reader = _reader(env, monkeypatch)
    with reader._transaction() as conn:
        # PRAGMA만으로 막은 대역이 아니라 SQLite mode=ro 자체가 쓰기를 거절해야 한다.
        conn.execute("PRAGMA query_only=OFF")
        for sql in ("CREATE TABLE forbidden_write(id TEXT)",
                    "UPDATE consultations SET payload=payload"):
            with pytest.raises(sqlite3.OperationalError) as caught:
                conn.execute(sql)
            assert caught.value.sqlite_errorcode & 0xFF == sqlite3.SQLITE_READONLY
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
    assert _files(env.root) == before


def test_missing_database_is_unavailable_and_never_creates_file_or_parent(tmp_path, monkeypatch):
    for relative in ("missing.db", "missing-parent/advisor.db"):
        with monkeypatch.context() as patch:
            case = _case(tmp_path / relative, tmp_path)
            before = _files(tmp_path)
            reader = _reader(case, patch)
            _unavailable(lambda: reader.is_v2_project("project"))
            _unavailable(lambda: reader.get_for_project(boundary=CONTEXT, project_id="project"))
            _unavailable(lambda: reader.get(boundary=CONTEXT, actor=AUTHOR, draft_id="draft"))
            assert not Path(case.adapter.db_path).exists()
            assert not (tmp_path / "missing-parent").exists()
            assert _files(tmp_path) == before


def test_corrupt_database_is_unavailable_without_repair_or_overwrite(tmp_path, monkeypatch):
    path = tmp_path / "corrupt.db"
    path.write_bytes(b"SYNTHETIC_NOT_A_SQLITE_DATABASE")
    case = _case(path, tmp_path)
    before = _files(tmp_path)
    reader = _reader(case, monkeypatch)
    _unavailable(lambda: reader.is_v2_project("project"))
    _unavailable(lambda: reader.get_for_project(boundary=CONTEXT, project_id="project"))
    assert _files(tmp_path) == before


def test_partial_v2_table_set_is_unavailable_not_legacy_false(tmp_path, monkeypatch):
    tables = ("advisor_v2_drafts", "advisor_v2_revisions", "advisor_v2_requests",
              "advisor_v2_bootstraps")
    # 빈 SQLite/레거시 anchor 하나만 있는 DB도 정상 legacy로 내려가면 안 된다.
    for index, subset in enumerate(((), ("consultations",), ("advisor_v2_bootstraps",), tables)):
        path = tmp_path / ("partial_" + str(index) + ".db")
        conn = sqlite3.connect(str(path))
        try:
            for table in subset:
                # 합성 불완전 스키마. 이 상수 목록 외 테이블/SQL은 입력받지 않는다.
                conn.execute("CREATE TABLE " + table + "(project_id TEXT)")
            conn.commit()
        finally:
            conn.close()
        before = _files(tmp_path)
        with monkeypatch.context() as patch:
            reader = _reader(_case(path, tmp_path), patch)
            _unavailable(lambda: reader.is_v2_project("project"))
            assert _files(tmp_path) == before


def test_all_v2_table_names_with_missing_required_columns_are_unavailable(tmp_path, monkeypatch):
    path = tmp_path / "abbreviated_schema.db"
    tables = ("advisor_v2_drafts", "advisor_v2_revisions", "advisor_v2_requests",
              "advisor_v2_bootstraps", "advisor_v2_transitions")
    conn = sqlite3.connect(str(path))
    try:
        for table in tables:
            # 이름과 oracle 조회 열만 있으면 False로 내려가던 축약 스키마를 재현한다.
            columns = "project_id TEXT" if table == "advisor_v2_bootstraps" else "junk TEXT"
            conn.execute("CREATE TABLE " + table + "(" + columns + ")")
        conn.commit()
    finally:
        conn.close()
    before = _files(tmp_path)
    reader = _reader(_case(path, tmp_path), monkeypatch)
    _unavailable(lambda: reader.is_v2_project("unknown_project"))
    _unavailable(lambda: reader.get_for_project(boundary=CONTEXT, project_id="unknown_project"))
    assert _files(tmp_path) == before


def test_readonly_preserves_existing_operation_integrity_validation(env, monkeypatch):
    reserved = _reserve(env, _decide(env, _save(env)))
    with _db(env) as conn:
        # B3의 기존 손상 주입과 같다. 보호 trigger 제거 없이 잘못된 최종 단계만 주입한다.
        conn.execute("UPDATE advisor_v2_bootstraps SET stage='COMPLETED' WHERE operation_id=?",
                     (reserved["operation_id"],))
    before = _files(env.root)
    reader = _reader(env, monkeypatch)
    assert reader.is_v2_project(reserved["project_id"]) is True
    _unavailable(lambda: reader.get_for_project(boundary=CONTEXT, project_id=reserved["project_id"]),
                 "ADVISOR_STORAGE_INTEGRITY")
    _unavailable(lambda: reader.get(boundary=CONTEXT, actor=AUTHOR, operation_id=reserved["operation_id"]),
                 "ADVISOR_STORAGE_INTEGRITY")
    assert _files(env.root) == before


def test_readonly_keeps_exact_boundary_and_operation_actor_checks(env, monkeypatch):
    reserved = _reserve(env, _decide(env, _save(env)))
    before = _files(env.root)
    reader = _reader(env, monkeypatch)
    _unavailable(lambda: reader.get_for_project(
        boundary={**CONTEXT, "scope_node_id": "other-dept"}, project_id=reserved["project_id"]),
        "ADVISOR_NOT_FOUND", 404)
    _unavailable(lambda: reader.get(boundary=CONTEXT, actor=OTHER, operation_id=reserved["operation_id"]),
                 "ADVISOR_NOT_FOUND", 404)
    assert _files(env.root) == before


def test_readonly_uri_opens_exact_special_character_path(tmp_path, monkeypatch):
    # Windows에서 '?' 파일명은 불가하다. 공백/#/% 실제 파일로 URI 인코딩을 검증한다.
    case = _case(tmp_path / "advisor # % space.db", tmp_path)
    approved = _decide(case, _save(case))
    reserved = _reserve(case, approved)
    before = _files(tmp_path, case.adapter.db_path)
    reader = _reader(case, monkeypatch)
    assert reader.is_v2_project(reserved["project_id"]) is True
    assert reader.get_for_project(boundary=CONTEXT, project_id=reserved["project_id"]) == reserved
    assert reader.get(boundary=CONTEXT, actor=REVIEWER,
                      approved_revision_id=approved["approved_revision_id"]) == approved
    assert _files(tmp_path, case.adapter.db_path) == before
