"""B3 kit release cohort. main의 감사·격리 runner에서만 실행한다.

테스트의 저장소 연산은 임시 SQLite 어댑터에 한정한다. ECM import 초기화도
main runner의 격리 환경에서만 허용하며 이 작업자는 테스트를 실행하지 않는다.
artifact는 B2 reference 후보를 읽으며 실제 데이터·서명·승인·릴리스는 만들지 않는다.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from core import studio_release_cohort as cohort
from core.data_preparation import process_pack_artifacts as artifacts
from core.enterprise_context.process_schema import ProcessError


CONTEXT = {"tenant_id": "b3_cohort_tenant", "context_root_id": "b3_cohort_root",
           "entity_mode": "REAL", "scope_node_id": ""}
INSTANCE = "ki_b3_cohort"
APP = "APP-01"
RELEASE = "kitapp_ki_b3_cohort_APP-01"


class Store:
    def __init__(self, path):
        self.path = path
        self.calls = 0
        self.statements = []

    @contextlib.contextmanager
    def transaction(self):
        self.calls += 1
        conn = sqlite3.connect(str(self.path), timeout=15)
        conn.row_factory = sqlite3.Row
        conn.set_trace_callback(self.statements.append)
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def bundle():
    return artifacts.load_bundle(artifacts.CANDIDATE_MANIFEST)


@pytest.fixture
def store(tmp_path, bundle):
    store = Store(tmp_path / "release-cohort.db")
    artifacts.pin_bundle(store, bundle)
    with store.transaction() as conn:
        conn.execute("""CREATE TABLE kit_instances (
            instance_id TEXT PRIMARY KEY, kit_id TEXT, version TEXT, kit_fingerprint TEXT,
            tenant_id TEXT, scope_node_id TEXT, entity_mode TEXT, status TEXT)""")
        conn.execute("""CREATE TABLE kit_process_instances (
            operation_id TEXT PRIMARY KEY, instance_id TEXT UNIQUE, context_root_id TEXT,
            artifact_digest TEXT, identity_json TEXT, identity_digest TEXT)""")
    _instance(store, bundle)
    store.calls = 0
    store.statements.clear()
    return store


def _instance(store, bundle, instance_id=INSTANCE, context=None):
    key = CONTEXT if context is None else context
    identity = {"kit_id": bundle["kit_id"], "version": bundle["version"],
        "kit_fingerprint": bundle["artifact_digest"], "tenant_id": key["tenant_id"],
        "scope_node_id": key["scope_node_id"] or key["context_root_id"], "entity_mode": key["entity_mode"]}
    with store.transaction() as conn:
        conn.execute("INSERT INTO kit_instances VALUES(?,?,?,?,?,?,?,?)", (instance_id,
            identity["kit_id"], identity["version"], identity["kit_fingerprint"],
            identity["tenant_id"], identity["scope_node_id"], identity["entity_mode"], "active"))
        conn.execute("INSERT INTO kit_process_instances VALUES(?,?,?,?,?,?)", (
            "op_" + instance_id, instance_id, key["context_root_id"], bundle["artifact_digest"],
            _json(identity), _digest(identity)))


def _pin(store, **changes):
    args = dict(release_id=RELEASE, instance_id=INSTANCE, app_id=APP, context_key=copy.deepcopy(CONTEXT))
    args.update(changes)
    return cohort.pin_release_cohort(store, **args)


def _schema(store):
    with store.transaction() as conn:
        return [tuple(row) for row in conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name")]


def _contents(store, table):
    # table은 이 테스트가 지정하는 상수뿐이다.
    with store.transaction() as conn:
        return [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]


def test_empty_store_get_returns_none_without_ddl(tmp_path):
    store = Store(tmp_path / "empty.db")
    before = _schema(store)
    store.statements.clear()
    assert cohort.get_release_cohort(store, RELEASE) is None
    statements = list(store.statements)
    assert _schema(store) == before == []
    assert not any(s.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE", "ALTER", "DROP"))
                   for s in statements)


def test_pin_shape_is_stable_and_revision_independent(store, bundle):
    context = copy.deepcopy(CONTEXT)
    identity = dict(release_id=RELEASE, instance_id=INSTANCE, app_id=APP,
                    context_key=CONTEXT, runtime_document_version="2.0")
    result = cohort.pin_release_cohort(store, release_id=RELEASE, instance_id=INSTANCE,
                                       app_id=APP, context_key=context)
    expected = {**identity, "artifact_digest": bundle["artifact_digest"], "identity_digest": _digest(identity)}
    assert result == expected
    assert _pin(store) == expected
    assert cohort.get_release_cohort(store, RELEASE) == expected
    assert not {"revision", "contract_revision", "semantic_fingerprint", "approved_by", "created_at"} & result.keys()
    result["context_key"]["tenant_id"] = "caller_mutation"
    assert context == CONTEXT
    assert cohort.get_release_cohort(store, RELEASE) == expected
    assert len(_contents(store, cohort.TABLE)) == 1


def test_pin_and_artifact_verification_use_one_immediate_transaction(store):
    _pin(store)
    assert store.calls == 1  # get_bundle가 새 연결/transaction을 열지 않는다.
    statements = [s.strip().upper() for s in store.statements]
    assert statements[0] == "BEGIN IMMEDIATE"
    assert statements[-1] == "COMMIT"
    assert statements.count("BEGIN IMMEDIATE") == 1
    assert statements.count("COMMIT") == 1


def test_server_contract_revision_changes_do_not_redefine_stable_cohort(store):
    with store.transaction() as conn:
        conn.execute("CREATE TABLE kit_app_contracts (revision INTEGER, semantic_fingerprint TEXT)")
        conn.execute("INSERT INTO kit_app_contracts VALUES(1,?)", ("1" * 64,))
    expected = _pin(store)
    with store.transaction() as conn:
        conn.execute("UPDATE kit_app_contracts SET revision=2, semantic_fingerprint=?", ("2" * 64,))
    assert _pin(store) == expected
    assert cohort.get_release_cohort(store, RELEASE) == expected


def test_get_is_one_read_snapshot_and_does_not_repair_or_write(store):
    expected = _pin(store)
    before_schema, before_rows = _schema(store), _contents(store, cohort.TABLE)
    store.calls = 0
    store.statements.clear()
    assert cohort.get_release_cohort(store, RELEASE) == expected
    assert store.calls == 1
    assert not any(s.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE", "ALTER", "DROP"))
                   for s in store.statements)
    assert _schema(store) == before_schema
    assert _contents(store, cohort.TABLE) == before_rows
    assert cohort.get_release_cohort(store, "not_registered") is None


def test_existing_b2_tables_and_rows_are_unchanged(store):
    before = {table: _contents(store, table) for table in ("kit_instances", "kit_process_instances", "kit_process_artifacts")}
    original_schema = _schema(store)
    _pin(store)
    for table, rows in before.items():
        assert _contents(store, table) == rows
    assert all(row in _schema(store) for row in original_schema)
    added = [row for row in _schema(store) if row not in original_schema]
    assert all("kit_process_release_cohorts" in row[1] for row in added)


@pytest.mark.parametrize("changed", ["instance_id", "app_id", "tenant_id", "context_root_id", "entity_mode", "scope_node_id"])
def test_same_release_with_different_identity_is_409_before_reference_lookup(store, changed):
    expected = _pin(store)
    changes = {}
    if changed in ("instance_id", "app_id"):
        changes[changed] = "another_valid_identifier"
    else:
        changes["context_key"] = {**CONTEXT, changed: "VIRTUAL" if changed == "entity_mode" else "another_scope"}
    with pytest.raises(cohort.ReleaseCohortError) as error:
        _pin(store, **changes)
    assert error.value.status_code == 409
    assert error.value.reason_code == "STUDIO_RELEASE_COHORT_CONFLICT"
    assert cohort.get_release_cohort(store, RELEASE) == expected


@pytest.mark.parametrize("mutation", ["missing_key", "fifth_key", "mode", "list", "none", "numeric_scope",
                                      "whitespace", "control", "too_long", "surrogate"])
def test_invalid_context_is_422_and_does_not_open_store(store, mutation):
    key = copy.deepcopy(CONTEXT)
    if mutation == "missing_key": key.pop("scope_node_id")
    elif mutation == "fifth_key": key["configuration_kind"] = "business_process"
    elif mutation == "mode": key["entity_mode"] = "UNKNOWN"
    elif mutation == "list": key = list(key)
    elif mutation == "none": key = None
    elif mutation == "numeric_scope": key["scope_node_id"] = 0
    elif mutation == "whitespace": key["tenant_id"] = " padded "
    elif mutation == "control": key["tenant_id"] = "bad\nvalue"
    elif mutation == "too_long": key["tenant_id"] = "x" * 201
    elif mutation == "surrogate": key["tenant_id"] = "\ud800"
    with pytest.raises(cohort.ReleaseCohortError) as error:
        _pin(store, context_key=key)
    assert error.value.status_code == 422
    assert store.calls == 0


@pytest.mark.parametrize("field,value", [("release_id", ""), ("release_id", "x" * 513),
    ("release_id", None), ("instance_id", True), ("app_id", ""), ("app_id", "x" * 201)])
def test_invalid_id_is_422_before_io(store, field, value):
    with pytest.raises(cohort.ReleaseCohortError) as error:
        _pin(store, **{field: value})
    assert error.value.status_code == 422 and store.calls == 0


@pytest.mark.parametrize("recursive", [0, 1])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "REPLACE", "INSERT OR REPLACE"])
def test_database_guards_block_all_existing_identity_mutations(store, recursive, operation):
    expected = _pin(store)
    with store.transaction() as conn:
        conn.execute(f"PRAGMA recursive_triggers={recursive}")
        with pytest.raises(sqlite3.IntegrityError, match="STUDIO_RELEASE_COHORT_IMMUTABLE"):
            if operation == "UPDATE":
                conn.execute("UPDATE kit_process_release_cohorts SET app_id=app_id WHERE release_id=?", (RELEASE,))
            elif operation == "DELETE":
                conn.execute("DELETE FROM kit_process_release_cohorts WHERE release_id=?", (RELEASE,))
            else:
                conn.execute(f"{operation} INTO kit_process_release_cohorts SELECT * FROM kit_process_release_cohorts")
    assert cohort.get_release_cohort(store, RELEASE) == expected


@pytest.mark.parametrize("column,value", [("identity_digest", "0" * 64), ("identity_json", "{}"),
    ("identity_json", '{"release_id":"a","release_id":"b"}'), ("app_id", "other_app"),
    ("artifact_digest", "0" * 64)])
def test_corrupt_existing_row_is_503_not_none_and_pin_does_not_overwrite(store, column, value):
    _pin(store)
    with store.transaction() as conn:
        conn.execute("DROP TRIGGER kit_process_release_cohorts_no_update")
        conn.execute(f"UPDATE kit_process_release_cohorts SET {column}=? WHERE release_id=?", (value, RELEASE))
    before = _contents(store, cohort.TABLE)
    for action in (lambda: cohort.get_release_cohort(store, RELEASE), lambda: _pin(store)):
        with pytest.raises(cohort.ReleaseCohortError) as error:
            action()
        assert error.value.status_code == 503
        assert "CORRUPT" in error.value.reason_code
    assert _contents(store, cohort.TABLE) == before


@pytest.mark.parametrize("table", ["kit_instances", "kit_process_instances", "kit_process_artifacts"])
def test_missing_dependency_after_pin_is_503_not_legacy_none(store, table):
    _pin(store)
    with store.transaction() as conn:
        # 손상 시뮬레이션은 이 테스트 전용 임시 DB 안에서만 한다.
        if table == "kit_process_artifacts":
            conn.execute("DROP TRIGGER kit_process_artifacts_no_delete")
        conn.execute(f"DELETE FROM {table}")
    with pytest.raises(cohort.ReleaseCohortError) as error:
        cohort.get_release_cohort(store, RELEASE)
    assert error.value.status_code == 503
    assert error.value.reason_code == "STUDIO_RELEASE_COHORT_REFERENCE_MISSING"


@pytest.mark.parametrize("table,column,value", [
    ("kit_instances", "kit_fingerprint", "0" * 64), ("kit_instances", "tenant_id", "forged"),
    ("kit_process_instances", "identity_json", "{}"), ("kit_process_instances", "identity_digest", "0" * 64),
    ("kit_process_instances", "artifact_digest", "0" * 64),
])
def test_corrupt_b2_reference_is_not_misclassified_as_absent(store, table, column, value):
    _pin(store)
    with store.transaction() as conn:
        conn.execute(f"UPDATE {table} SET {column}=?", (value,))
    with pytest.raises(cohort.ReleaseCohortError) as error:
        cohort.get_release_cohort(store, RELEASE)
    assert error.value.status_code == 503
    assert error.value.reason_code == "STUDIO_RELEASE_COHORT_REFERENCE_CORRUPT"


def test_corrupt_artifact_content_is_503(store):
    _pin(store)
    with store.transaction() as conn:
        conn.execute("DROP TRIGGER kit_process_artifacts_no_update")
        conn.execute("UPDATE kit_process_artifacts SET bundle_json='{}'")
    with pytest.raises(cohort.ReleaseCohortError) as error:
        cohort.get_release_cohort(store, RELEASE)
    assert error.value.reason_code == "STUDIO_RELEASE_COHORT_REFERENCE_CORRUPT"
    assert error.value.status_code == 503


@pytest.mark.parametrize("change", ["root", "scope", "mode", "app", "inactive"])
def test_unmatched_new_reference_fails_409_without_creating_cohort_table(store, change):
    key, args = copy.deepcopy(CONTEXT), {}
    if change == "root": key["context_root_id"] = "other_root"
    elif change == "scope": key["scope_node_id"] = "other_scope"
    elif change == "mode": key["entity_mode"] = "VIRTUAL"
    elif change == "app": args["app_id"] = "APP-NOT-IN-PACK"
    elif change == "inactive":
        with store.transaction() as conn:
            conn.execute("UPDATE kit_instances SET status='inactive'")
    with pytest.raises(cohort.ReleaseCohortError) as error:
        _pin(store, context_key=key, **args)
    assert error.value.status_code == 409
    assert not any(row[1] == cohort.TABLE for row in _schema(store))


def test_root_and_scoped_pins_keep_exact_four_keys(store, bundle):
    scoped = {**CONTEXT, "scope_node_id": "b3_department"}
    _instance(store, bundle, "ki_scoped", scoped)
    root = _pin(store)
    department = _pin(store, release_id="kitapp_ki_scoped_APP-01", instance_id="ki_scoped", context_key=scoped)
    assert root["context_key"] == CONTEXT
    assert department["context_key"] == scoped
    assert root["identity_digest"] != department["identity_digest"]


def test_same_pin_race_is_idempotent(store):
    barrier = Barrier(2)
    def work(_):
        barrier.wait(timeout=10)
        return _pin(store)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(work, range(2)))
    assert results[0] == results[1]
    assert len(_contents(store, cohort.TABLE)) == 1


def test_different_identity_race_has_one_winner_and_one_409(store):
    barrier = Barrier(2)
    def work(app_id):
        barrier.wait(timeout=10)
        try:
            return _pin(store, app_id=app_id)
        except cohort.ReleaseCohortError as exc:
            return (exc.status_code, exc.reason_code)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(work, ("APP-01", "APP-02")))
    assert len([r for r in results if isinstance(r, dict)]) == 1
    assert (409, "STUDIO_RELEASE_COHORT_CONFLICT") in results
    assert len(_contents(store, cohort.TABLE)) == 1


def test_wrong_cohort_table_shape_is_503_and_get_does_not_repair(store):
    with store.transaction() as conn:
        conn.execute("CREATE TABLE kit_process_release_cohorts (release_id TEXT PRIMARY KEY)")
    before = _schema(store)
    with pytest.raises(cohort.ReleaseCohortError) as error:
        cohort.get_release_cohort(store, RELEASE)
    assert error.value.reason_code == "STUDIO_RELEASE_COHORT_CORRUPT"
    assert _schema(store) == before


@pytest.mark.parametrize("failure", [sqlite3.OperationalError("unavailable"), OSError("unavailable")])
def test_storage_error_is_503_not_legacy_none(failure):
    class BrokenStore:
        @contextlib.contextmanager
        def transaction(self):
            raise failure
            yield
    for action in (lambda: _pin(BrokenStore()), lambda: cohort.get_release_cohort(BrokenStore(), RELEASE)):
        with pytest.raises(cohort.ReleaseCohortError) as error:
            action()
        assert error.value.status_code == 503
        assert error.value.reason_code == "STUDIO_RELEASE_COHORT_STORAGE_UNAVAILABLE"
        assert isinstance(error.value, ProcessError)


def test_nested_pin_does_not_commit_callers_transaction(store):
    with store.transaction() as conn:
        conn.execute("BEGIN")
        class AttachedStore:
            @contextlib.contextmanager
            def transaction(self):
                yield conn
        with pytest.raises(cohort.ReleaseCohortError) as error:
            _pin(AttachedStore())
        assert error.value.reason_code == "STUDIO_RELEASE_COHORT_TRANSACTION_REQUIRED"
        assert conn.in_transaction
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (cohort.TABLE,)).fetchone() is None
