"""B2 불변 팩: 새 임시 DB·파일만 사용한다. 실제 자산을 쓰는 테스트가 아니다.

실행은 main의 격리 runner 담당이다. 전역 conftest를 사용하지 않는다.
"""
from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from core.data_preparation import process_pack_artifacts as artifacts


class ArtifactStore:
    """실제 데이터 저장소·싱글턴을 생성하지 않는 격리 연결 어댑터."""

    def __init__(self, path):
        self.path = path

    @contextlib.contextmanager
    def transaction(self):
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(tmp_path / "artifacts.db")


@pytest.fixture
def bundle():
    return artifacts.load_bundle(artifacts.CANDIDATE_MANIFEST)


@pytest.fixture
def package(tmp_path):
    """후보 다섯 JSON만 격리 경로에 복사한다(1.2.0 부터 데이터셋 계약 포함). 기존 Starter는 읽지도 쓰지도 않는다."""
    root = tmp_path / "package"
    root.mkdir()
    for name in ("manifest.json", "profile.json", "blueprints.json", "processes/l2-process-pack.json",
                 "dataset_contracts.json"):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((artifacts.CANDIDATE_MANIFEST.parent / name).read_bytes())
    return root / "manifest.json"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rehash(manifest_path, field):
    manifest = read_json(manifest_path)
    raw = (manifest_path.parent / manifest[field]["path"]).read_bytes()
    manifest[field]["sha256"] = hashlib.sha256(raw).hexdigest()
    write_json(manifest_path, manifest)


def changed_bundle(package):
    manifest = read_json(package)
    pack_path = package.parent / manifest["process_pack"]["path"]
    pack = read_json(pack_path)
    pack["templates"][0]["label"] += " 개정 후보"
    write_json(pack_path, pack)
    rehash(package, "process_pack")
    return artifacts.load_bundle(package)


def test_candidate_counts_and_bk01_boundaries(bundle):
    templates = bundle["pack"]["templates"]
    assert len([x for x in templates if x["level"] == "L1"]) == 8
    assert len([x for x in templates if x["level"] == "L2"]) == 29
    assert len({x["template_key"] for x in templates}) == 37
    assert {x["business_kit_id"] for x in templates} == {f"BK-{n:02d}" for n in range(1, 9)}
    bk01 = [x for x in templates if x["business_kit_id"] == "BK-01" and x["level"] == "L2"]
    assert len(bk01) == 4
    assert next(x for x in bk01 if x["template_key"] == "sourcing.supplier_selection")["default_selected"] is False
    sourcing = next(x for x in templates if x["template_key"] == "sourcing")
    assert sourcing["shortcut_refs"] == [
        {"target_template_key": "logistics.shipment", "target_business_kit_id": "BK-02"},
        {"target_template_key": "inventory.receipt", "target_business_kit_id": "BK-03"},
        {"target_template_key": "finance.settlement", "target_business_kit_id": "BK-07"},
    ]
    plan = next(x for x in bk01 if x["template_key"] == "sourcing.plan")
    missing = [x for x in plan["data_requirements"] if x["unresolved_requirement"]]
    assert len(missing) == 1 and missing[0]["candidate_dataset_keys"] == []
    assert missing[0]["mandatory"] is True


def test_candidate_contains_no_company_data_or_executable_approval(bundle):
    assert bundle["version"] == "1.2.0"
    assert bundle["pack"]["version"] == "1.0.1"
    assert bundle["profile"]["mode"] == "REAL"
    assert bundle["profile"]["data_class"] == "NO_DATA"
    assert bundle["profile"]["setup_only"] is True
    assert bundle["manifest"]["status"] == "DOMAIN_REVIEW_REQUIRED"
    assert len(bundle["profile"]["datasets"]) == 35
    assert len(bundle["blueprints"]["blueprints"]) == 7
    assert all(bp["reference_status"] == "REFERENCE_ONLY" for bp in bundle["blueprints"]["blueprints"])
    for doc in (bundle["manifest"], bundle["profile"], bundle["pack"], bundle["blueprints"], bundle["dataset_contracts"]):
        assert not {"company_profile_id", "company_name", "users", "signatures", "certifications", "raw_data", "credentials"} & doc.keys()


def test_exact_original_bytes_are_retained(bundle):
    assert artifacts.load_bundle(artifacts.CANDIDATE_MANIFEST) == bundle
    for name in ("manifest", "profile", "pack", "blueprints", "dataset_contracts"):
        raw = base64.b64decode(bundle["raw_documents"][name], validate=True)
        assert hashlib.sha256(raw).hexdigest() == bundle[f"{name}_digest"]
        assert json.loads(raw.decode("utf-8-sig")) == bundle[name]


def test_semantically_equal_raw_bytes_have_distinct_digest(package, bundle):
    profile_path = package.parent / "profile.json"
    profile = read_json(profile_path)
    raw = b"\xef\xbb\xbf" + (json.dumps(profile, ensure_ascii=False) + "\r\n").encode("utf-8")
    profile_path.write_bytes(raw)
    rehash(package, "profile")
    changed = artifacts.load_bundle(package)
    assert changed["profile"] == bundle["profile"]
    assert changed["profile_digest"] != bundle["profile_digest"]
    assert changed["artifact_digest"] != bundle["artifact_digest"]
    assert base64.b64decode(changed["raw_documents"]["profile"]) == raw


@pytest.mark.parametrize("path", ["../outside.json", "https://example.invalid/a.json", "/tmp/a.json",
    "C:/secret.json", "C:\\secret.json", "processes/../../a.json", "./profile.json", "processes//a.json",
    "processes\\a.json", "%2e%2e/a.json", "NUL", "CON.json", "a.json:stream", "a./b.json"])
def test_unsafe_component_paths_fail_before_read(package, path):
    manifest = read_json(package)
    manifest["process_pack"]["path"] = path
    write_json(package, manifest)
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.load_bundle(package)
    assert error.value.reason_code == "PROCESS_PACK_PATH_INVALID"


def test_symlink_escape_is_rejected(package, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_bytes((package.parent / "processes/l2-process-pack.json").read_bytes())
    link = package.parent / "linked.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("이 호스트는 심볼릭 링크 생성 권한이 없어 별도 환경 검증 필요")
    manifest = read_json(package)
    manifest["process_pack"]["path"] = "linked.json"
    write_json(package, manifest)
    with pytest.raises(artifacts.ProcessPackError, match="패키지 밖"):
        artifacts.load_bundle(package)


def test_missing_pack_is_not_data_only_success(package):
    manifest = read_json(package)
    manifest["process_pack"]["path"] = "missing.json"
    write_json(package, manifest)
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.load_bundle(package)
    assert error.value.reason_code == "PROCESS_PACK_FILE_UNAVAILABLE"
    assert error.value.status_code == 503


def test_hash_corruption_rejected(package):
    path = package.parent / "processes/l2-process-pack.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.load_bundle(package)
    assert error.value.reason_code == "PROCESS_PACK_DIGEST_MISMATCH"


#: [2026-09-25] schema 2(데이터셋 계약 포함)가 정식 판이 되었다 — 지원 밖 값은 3·"2" 등으로 본다.
@pytest.mark.parametrize("schema", [0, 3, "2", True, None])
def test_manifest_schema_is_explicit(package, schema):
    manifest = read_json(package)
    manifest["schema_version"] = schema
    write_json(package, manifest)
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.load_bundle(package)
    assert error.value.reason_code == "PROCESS_PACK_SCHEMA_UNSUPPORTED"


@pytest.mark.parametrize("raw", [b'{"schema_version":1,"schema_version":1}', b'{"x":NaN}',
                               b'{"x":Infinity}', b'\xff\x00', b'{broken'])
def test_ambiguous_or_malformed_json_is_rejected(package, raw):
    package.write_bytes(raw)
    with pytest.raises(artifacts.ProcessPackError):
        artifacts.load_bundle(package)


@pytest.mark.parametrize("mutation", ["duplicate", "missing_field", "l1_parent", "l2_parent", "cycle",
    "cross_kit_parent", "unknown_data", "unknown_app", "wrong_app_version", "unknown_relation",
    "unknown_shortcut", "wrong_shortcut_kit", "shortcut_own_child", "unresolved_false", "numeric_default",
    "approved_status", "credentials", "malformed_level", "malformed_parent", "malformed_requirement"])
def test_pack_structure_and_reference_fail_closed(bundle, mutation):
    pack = copy.deepcopy(bundle["pack"])
    node = next(x for x in pack["templates"] if x["template_key"] == "sourcing.plan")
    root = next(x for x in pack["templates"] if x["template_key"] == "sourcing")
    if mutation == "duplicate": pack["templates"].append(copy.deepcopy(node))
    elif mutation == "missing_field": node.pop("purpose")
    elif mutation == "l1_parent": root["parent_template_key"] = "logistics"
    elif mutation == "l2_parent": node["parent_template_key"] = "missing"
    elif mutation == "cycle": node["parent_template_key"] = "sourcing.plan"
    elif mutation == "cross_kit_parent": node["parent_template_key"] = "logistics"
    elif mutation == "unknown_data": node["data_requirements"][0]["candidate_dataset_keys"] = ["MISSING"]
    elif mutation == "unknown_app": node["suggested_blueprint_refs"][0]["app_id"] = "APP-99"
    elif mutation == "wrong_app_version": node["suggested_blueprint_refs"][0]["version"] = "1.0.0"
    elif mutation == "unknown_relation": node["relations"] = [{"kind": "informs", "target_template_key": "missing"}]
    elif mutation == "unknown_shortcut": root["shortcut_refs"][0]["target_template_key"] = "missing"
    elif mutation == "wrong_shortcut_kit": root["shortcut_refs"][0]["target_business_kit_id"] = "BK-01"
    elif mutation == "shortcut_own_child": root["shortcut_refs"] = [{"target_template_key": "sourcing.plan", "target_business_kit_id": "BK-01"}]
    elif mutation == "unresolved_false": node["data_requirements"][1]["unresolved_requirement"] = False
    elif mutation == "numeric_default": node["default_selected"] = 1
    elif mutation == "approved_status": pack["review_status"] = "APPROVED"
    elif mutation == "credentials": node["credentials"] = "not-a-real-secret"
    elif mutation == "malformed_level": node["level"] = []
    elif mutation == "malformed_parent": node["parent_template_key"] = {}
    elif mutation == "malformed_requirement": node["data_requirements"][0] = []
    with pytest.raises(artifacts.ProcessPackError):
        artifacts.validate_pack(pack, bundle["profile"], bundle["blueprints"])


def test_profile_and_blueprint_set_must_match(bundle):
    profile = copy.deepcopy(bundle["profile"])
    profile["outputs"][0]["requires"] = ["PRC-01"]
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.validate_pack(bundle["pack"], profile, bundle["blueprints"])
    assert error.value.reason_code == "PROCESS_PACK_REFERENCE_INVALID"


def test_pin_idempotent_and_reads_independent_of_registry(store, bundle):
    with store.transaction() as conn:
        conn.execute("CREATE TABLE kit_registry_versions (kit_id TEXT, version TEXT, marker TEXT)")
        conn.execute("INSERT INTO kit_registry_versions VALUES (?, '1.0.0', 'legacy-unchanged')", (bundle["kit_id"],))
    first = artifacts.pin_bundle(store, bundle)
    second = artifacts.pin_bundle(store, copy.deepcopy(bundle))
    assert first == second == artifacts.get_bundle(store, bundle["artifact_digest"])
    with store.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM kit_process_artifacts").fetchone()[0] == 1
        assert conn.execute("SELECT marker FROM kit_registry_versions").fetchone()[0] == "legacy-unchanged"
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='kit_instances'").fetchone()


@pytest.mark.parametrize("already_pinned", [False, True])
def test_legacy_same_version_blocks_initial_pin_and_identical_retry(store, bundle, already_pinned):
    if already_pinned:
        artifacts.pin_bundle(store, bundle)
    with store.transaction() as conn:
        conn.execute("CREATE TABLE kit_registry_versions (kit_id TEXT, version TEXT, marker TEXT)")
        conn.execute("INSERT INTO kit_registry_versions VALUES (?, ?, 'legacy-unchanged')",
                     (bundle["kit_id"], bundle["version"]))
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.pin_bundle(store, copy.deepcopy(bundle))
    assert error.value.reason_code == "IMMUTABLE_VERSION_CONFLICT"
    assert error.value.status_code == 409
    with store.transaction() as conn:
        assert conn.execute("SELECT marker FROM kit_registry_versions").fetchone()[0] == "legacy-unchanged"
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='kit_process_artifacts'").fetchone()
        assert bool(exists) is already_pinned
        if already_pinned:
            assert conn.execute("SELECT COUNT(*) FROM kit_process_artifacts").fetchone()[0] == 1
    if already_pinned:
        assert artifacts.get_bundle(store, bundle["artifact_digest"]) == bundle


def test_same_version_different_bytes_conflicts(store, bundle, package):
    artifacts.pin_bundle(store, bundle)
    other = changed_bundle(package)
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.pin_bundle(store, other)
    assert error.value.reason_code == "IMMUTABLE_VERSION_CONFLICT"
    assert error.value.status_code == 409
    assert artifacts.get_bundle(store, bundle["artifact_digest"]) == bundle


@pytest.mark.parametrize("part", ["pack", "profile", "blueprints", "manifest", "artifact_digest", "raw_documents",
                                  "dataset_contracts"])
def test_caller_cannot_pin_relabelled_or_mutated_bundle(store, bundle, part):
    value = copy.deepcopy(bundle)
    if part == "artifact_digest": value[part] = "a" * 64
    elif part == "raw_documents": value[part]["pack"] = "invalid"
    elif part == "pack": value[part]["templates"][0]["label"] = "변조"
    elif part == "dataset_contracts": value[part]["contracts"][0]["business_keys"] = ["record_id"]
    else: value[part]["name"] = "변조"
    with pytest.raises(artifacts.ProcessPackError):
        artifacts.pin_bundle(store, value)
    with store.transaction() as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='kit_process_artifacts'").fetchone()


@pytest.mark.parametrize("statement", [
    "UPDATE kit_process_artifacts SET created_at='changed'",
    "DELETE FROM kit_process_artifacts",
    "INSERT OR REPLACE INTO kit_process_artifacts SELECT * FROM kit_process_artifacts",
])
def test_db_rejects_direct_update_delete_and_replace(store, bundle, statement):
    artifacts.pin_bundle(store, bundle)
    with pytest.raises(sqlite3.IntegrityError, match="PROCESS_ARTIFACT_IMMUTABLE"):
        with store.transaction() as conn:
            conn.execute(statement)
    assert artifacts.get_bundle(store, bundle["artifact_digest"]) == bundle


@pytest.mark.parametrize("damage", ["body", "index", "raw"])
def test_get_revalidates_stored_integrity_without_file_fallback(store, bundle, damage):
    artifacts.pin_bundle(store, bundle)
    with store.transaction() as conn:
        conn.execute("DROP TRIGGER kit_process_artifacts_no_update")
        if damage == "index":
            conn.execute("UPDATE kit_process_artifacts SET kit_id='another-kit'")
        else:
            value = copy.deepcopy(bundle)
            if damage == "body": value["pack"]["templates"][0]["label"] = "tampered"
            else: value["raw_documents"]["pack"] = base64.b64encode(b"{}").decode()
            conn.execute("UPDATE kit_process_artifacts SET bundle_json=?", (json.dumps(value),))
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.get_bundle(store, bundle["artifact_digest"])
    assert error.value.reason_code == "PROCESS_ARTIFACT_CORRUPT"
    assert error.value.status_code == 503


def test_missing_artifact_does_not_create_table_or_fallback(store):
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.get_bundle(store, "0" * 64)
    assert error.value.reason_code == "PROCESS_ARTIFACT_NOT_FOUND"
    assert error.value.status_code == 404
    with store.transaction() as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='kit_process_artifacts'").fetchone()


def test_read_survives_removed_candidate_files(store, package, monkeypatch):
    pinned = artifacts.pin_bundle(store, changed_bundle(package))
    for name in ("manifest.json", "profile.json", "blueprints.json", "processes/l2-process-pack.json"):
        (package.parent / name).unlink()  # 삭제 대상은 fixture의 신규 임시 JSON 네 개뿐이다.

    def forbid_load(_path):
        pytest.fail("고정 아티팩트를 현재 파일로 대체하면 안 됩니다.")

    monkeypatch.setattr(artifacts, "load_bundle", forbid_load)
    assert artifacts.get_bundle(store, pinned["artifact_digest"]) == pinned


def test_failed_pin_rolls_back_table_creation(store, bundle, monkeypatch):
    ensure = artifacts._ensure_table

    def fail_after_ddl(conn):
        ensure(conn)
        raise sqlite3.OperationalError("injected scoped test failure")

    monkeypatch.setattr(artifacts, "_ensure_table", fail_after_ddl)
    with pytest.raises(artifacts.ProcessPackError) as error:
        artifacts.pin_bundle(store, bundle)
    assert error.value.status_code == 503
    with store.transaction() as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='kit_process_artifacts'").fetchone()


@pytest.mark.parametrize("conflicting", [False, True])
def test_independent_connection_pin_race_keeps_one_immutable_version(store, bundle, package, conflicting):
    barrier = Barrier(2)
    other = changed_bundle(package) if conflicting else copy.deepcopy(bundle)

    def pin(value):
        barrier.wait(timeout=10)
        try:
            return artifacts.pin_bundle(ArtifactStore(store.path), value)["artifact_digest"]
        except artifacts.ProcessPackError as error:
            return error.reason_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(pin, bundle)
        second = executor.submit(pin, other)
        results = [first.result(timeout=20), second.result(timeout=20)]
    if conflicting:
        assert results.count("IMMUTABLE_VERSION_CONFLICT") == 1
        assert len(set(results) & {bundle["artifact_digest"], other["artifact_digest"]}) == 1
    else:
        assert results == [bundle["artifact_digest"]] * 2
    with store.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM kit_process_artifacts").fetchone()[0] == 1
