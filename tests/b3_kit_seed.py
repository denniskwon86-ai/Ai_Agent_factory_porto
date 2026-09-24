"""이번 pytest 실행에만 존재하는 합성 키트 seed. 운영 경로·정책 우회는 없다.

캐시는 검증된 파일 경로·해시·불변 JSON 문자열뿐이다. DB 연결이나 서비스는
보관하지 않는다. 모든 소비자는 SQLite backup으로 새 DB를 받고 실제 서비스를
새로 만든다. 기존 function-scoped 조직/설치 fixture와 cold 설치 경로는 유지한다.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3


_ROOT = Path(__file__).resolve().parents[1]
_CACHE = "_b3_verified_kit_seed_v1"
_REQUIRED = {
    "ecm": {"enterprise_profiles", "enterprise_process_heads", "enterprise_process_installations"},
    "dp": {"kit_process_artifacts", "kit_process_instances", "dataset_snapshots", "source_bindings"},
    "org": {"departments", "users", "user_dept_roles"},
    "ledger": {"decision_ledger_events"},
}


class SeedIntegrityError(AssertionError):
    """불완전·변조·다른 실행/소스의 seed는 자동 재생성 없이 실패한다."""


def _need(ok, message):
    if not ok:
        raise SeedIntegrityError(message)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=lambda v: {"sqlite_blob_hex": bytes(v).hex()})


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def source_digest():
    """실행 중 소스 교체도 거부한다. 경로/본문만 읽고 모듈을 실행하지 않는다."""
    paths = list((_ROOT / "core").rglob("*.py")) + list((_ROOT / "nodes").rglob("*.py"))
    paths += list((_ROOT / "process_packs").rglob("*.json"))
    #: [2026-09-25] 인증 판은 키트 정본 샘플에서 온다(`tests/kit_samples.py`).
    kit = _ROOT / "starter_kits" / "KIT-MFG-NONFERROUS-PROCUREMENT" / "1.0.0"
    paths += list((kit / "contracts").glob("*.json")) + list((kit / "samples" / "quick").glob("*.csv"))
    paths += [_ROOT / "config.py", _ROOT / "state_models.py"]
    paths += [_ROOT / "tests" / name for name in (
        "b3_kit_seed.py", "kit_samples.py", "test_b3_kit_contract_v2.py", "test_b3_seed_isolation.py",
        "test_b2_installation.py", "test_b1_process_configuration.py", "org_seed.py",
        "usage_hold_test_plugin.py", "test_b3_process_context.py")]
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        digest.update(path.relative_to(_ROOT).as_posix().encode())
        digest.update(b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _path(path, root, *, exists=True):
    path, root = Path(path).absolute(), Path(root).resolve()
    _need(path.resolve().is_relative_to(root) and path.resolve() != root, "seed 경로가 임시 루트 밖입니다.")
    _need(not any(p.is_symlink() for p in (path, *path.parents) if p != root.parent), "seed 링크 경로는 허용하지 않습니다.")
    _need(not exists or path.is_file(), "seed DB가 없습니다.")
    return path.resolve()


def _read(path):
    # runner의 일반 경로 감사 규칙을 그대로 따른다. URI/guard 예외를 사용하지 않는다.
    _need(Path(path).is_file(), "읽을 seed DB가 없습니다.")
    conn = sqlite3.connect(str(path), timeout=5)
    try:
        conn.execute("PRAGMA query_only=ON")
        return conn
    except BaseException:
        conn.close()
        raise


def _signature(path, kind, *, forbidden_root=None):
    """SQLite 구조·제약·인덱스·트리거·행 전체의 논리 지문. WAL/mtime에 의존하지 않는다."""
    with closing(_read(path)) as conn:
        conn.execute("BEGIN")
        _need(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite 무결성 오류")
        _need(not conn.execute("PRAGMA foreign_key_check").fetchall(), "SQLite 외래키 오류")
        schema = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                              "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
        names = {row[1] for row in schema if row[0] == "table"}
        _need(_REQUIRED[kind] <= names, "seed 필수 스키마가 없습니다.")
        tables = {}
        for name in sorted(names):
            quoted = '"' + name.replace('"', '""') + '"'
            tables[name] = sorted((_json(list(row)) for row in conn.execute(f"SELECT * FROM {quoted}")))
        material = _json({"schema": schema, "tables": tables})
        if forbidden_root is not None:
            normalized = material.replace("\\", "/")
            while "//" in normalized:
                normalized = normalized.replace("//", "/")
            _need(Path(forbidden_root).as_posix() not in normalized,
                  "seed 행이 최초 시험의 파일 경로를 참조합니다.")
        return _hash(material.encode())


def _backup(source, destination):
    _need(not destination.exists(), "기존 DB를 seed로 덮어쓰지 않습니다.")
    with closing(_read(source)) as src, closing(sqlite3.connect(str(destination), timeout=5)) as dst:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")
        dst.commit()


@dataclass(frozen=True)
class KitSeed:
    schema_version: int
    run_id: int
    source_hash: str
    root: str
    payload: str
    payload_hash: str
    databases: tuple[tuple[str, str, str, str], ...]


def validate_seed(seed, *, run_id):
    _need(isinstance(seed, KitSeed) and type(seed.schema_version) is int and seed.schema_version == 1,
          "알 수 없는 seed 스키마")
    _need(seed.run_id == run_id and seed.source_hash == source_digest(), "다른 실행/소스의 seed입니다.")
    _need(_hash(seed.payload.encode()) == seed.payload_hash, "seed 메타데이터 해시 오류")
    payload = json.loads(seed.payload)
    _need(set(payload) == {"boundary", "context", "approved", "instance_id", "ids", "data", "fixed",
                           "bundle", "nodes", "contract"}, "seed 메타데이터 스키마 오류")
    _need(len(seed.databases) == 4 and {d[0] for d in seed.databases} == set(_REQUIRED), "seed DB 집합 오류")
    _need(len({Path(d[1]).resolve() for d in seed.databases}) == 4, "seed DB 경로가 중복됩니다.")
    for kind, filename, file_hash, logical_hash in seed.databases:
        path = _path(filename, seed.root)
        _need(_hash(path.read_bytes()) == file_hash, "seed 원본 DB 해시 오류")
        _need(_signature(path, kind) == logical_hash, "seed 논리/스키마 해시 오류")
    return payload


def capture_seed(w, destination, *, run_id):
    """실제 cold 설치 결과만 복제한다. 호출 전에도 실제 생산자/PDP로 검증한다."""
    from tests import org_seed as org
    from tests.test_b3_kit_contract_v2 import producer
    _need(w["ledger"].verify_chain()["ok"], "cold 원장 체인 오류")
    payload = {key: w[key] for key in ("context", "approved", "instance_id", "ids", "data", "fixed", "bundle")}
    payload.update(boundary=w["boundary"].model_dump(), nodes=dict(org.NODES), contract=producer(w))
    raw = _json(payload)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    sources = {**w["paths"], "ledger": Path(w["ledger"].db_path)}
    databases = []
    for kind in sorted(_REQUIRED):
        source = _path(sources[kind], w["root"])
        before = _signature(source, kind, forbidden_root=w["root"])
        target = _path(destination / f"{kind}.db", destination, exists=False)
        _backup(source, target)
        _need(_signature(target, kind) == before, "SQLite backup이 원본 논리 상태와 다릅니다.")
        databases.append((kind, str(target), _hash(target.read_bytes()), before))
    seed = KitSeed(1, run_id, source_digest(), str(destination), raw, _hash(raw.encode()), tuple(databases))
    validate_seed(seed, run_id=run_id)
    return seed


def clone_seed(seed, destination, monkeypatch, *, run_id):
    """새 DB/서비스와 현재 시험의 singleton 별칭을 같은 복사본에 결속한다."""
    from tests import org_seed as org
    from core import scope_policy
    from core.enterprise_context.process_schema import ProcessBoundary
    from core.enterprise_context.process_configuration import ProcessConfigurationService
    from core.enterprise_context.process_context import ProcessContextService
    from core.enterprise_context.process_installation import ProcessInstallationService

    payload = validate_seed(seed, run_id=run_id)
    destination = Path(destination).resolve()
    _need(not destination.is_relative_to(Path(seed.root)), "seed 내부에 시험 복사본을 만들 수 없습니다.")
    destination.mkdir(parents=True, exist_ok=False)
    paths = {}
    for kind, filename, _, logical_hash in seed.databases:
        target = _path(destination / f"{kind}.db", destination, exists=False)
        _backup(_path(filename, seed.root), target)
        _need(_signature(target, kind) == logical_hash, "복사본의 스키마/행이 seed와 다릅니다.")
        paths[kind] = target

    specifications = (
        ("core.data_preparation.store", "data_preparation_store", "DataPreparationStore", "dp"),
        ("core.enterprise_context.repository", "ecm_repository", "EcmRepository", "ecm"),
        ("core.org_directory", "org_directory", "OrgDirectory", "org"),
        ("core.decision_ledger", "decision_ledger", "DecisionLedger", "ledger"),
    )
    objects = {}
    for module_name, attribute, class_name, kind in specifications:
        module = importlib.import_module(module_name)
        old = getattr(module, attribute)
        # 이미 import된 별칭도 현재 시험 DB만 보도록 경로와 캐시를 초기화한다.
        monkeypatch.setattr(old, "db_path", str(paths[kind]))
        if hasattr(old, "_prepared_for"):
            monkeypatch.setattr(old, "_prepared_for", None)
        if hasattr(old, "_scope_cache"):
            monkeypatch.setattr(old, "_scope_cache", {})
        fresh = getattr(module, class_name)(str(paths[kind]))
        monkeypatch.setattr(module, attribute, fresh)
        objects[kind] = fresh
    # NODES를 inplace 공유하지 않는다. teardown은 이전 function fixture의 사전을 복원한다.
    monkeypatch.setattr(org, "NODES", dict(payload["nodes"]))
    _need(scope_policy.org_enforce() is True, "조직 강제 정책이 꺼져 있습니다.")
    repo, store = objects["ecm"], objects["dp"]
    w = {key: payload[key] for key in ("context", "approved", "instance_id", "ids", "data", "fixed", "bundle")}
    w.update(root=destination, paths={k: v for k, v in paths.items() if k != "ledger"},
             boundary=ProcessBoundary(**payload["boundary"]), directory=objects["org"],
             ledger=objects["ledger"], store=store, svc=ProcessConfigurationService(repo, store),
             ctx=ProcessContextService(repo, store), install=ProcessInstallationService(repo, store))
    verify_clone(w, payload)
    return w


def verify_clone(w, payload):
    """원장·핀 원문·현재 조직/PDP·ID·고정 binding/snapshot을 실제 서비스로 대조한다."""
    from core.data_preparation.process_pack_artifacts import get_bundle
    from tests.test_b2_installation import _read
    from tests.test_b3_kit_contract_v2 import DATA_KEYS, TEMPLATES, process_build, producer
    chain = w["ledger"].verify_chain()
    _need(chain["ok"] and chain["checked"] > 0, "복제 원장 체인 검증 실패")
    _need(get_bundle(w["store"], w["bundle"]["artifact_digest"]) == w["bundle"], "핀 artifact 불일치")
    doc = _read(w)
    _need(doc["profile_id"] == w["approved"]["profile_id"], "승인 프로필 ID 불일치")
    _need({n["template_key"]: n["process_id"] for n in doc["payload"]["nodes"]} == w["ids"], "process ID 불일치")
    _need(set(w["data"]) == set(DATA_KEYS), "인증 데이터 집합 불일치")
    fixed = process_build(w, [w["ids"][key] for key in TEMPLATES])
    _need(fixed == w["fixed"], "실제 정책/조직/원장으로 재검증한 고정 문맥이 다릅니다.")
    refs = {ref["contract_key"]: ref for ref in fixed["verified_binding_refs"]}
    _need(set(refs) == set(DATA_KEYS), "고정 참조 집합 불일치")
    for key, value in w["data"].items():
        ref = refs[key]
        _need(ref["instance_id"] == w["instance_id"] and ref["snapshot_id"] == value["snapshot_id"]
              and ref["binding_id"] == value["binding"]["binding_id"], "복제 ID/binding/snapshot 불일치")
    _need(producer(w) == payload["contract"], "실제 cold 생산자와 복제 생산자 결과가 다릅니다.")


def cached_kit(request, installation, monkeypatch, tmp_path_factory, cold_builder):
    """session 객체 외 전역/디스크 검색 캐시가 없다. xdist도 worker별로 한 번 생성한다."""
    session = request.session
    seed = getattr(session, _CACHE, None)
    if seed is None:
        cold = cold_builder(installation, monkeypatch)
        parent = tmp_path_factory.mktemp("b3-kit-seed")
        seed = capture_seed(cold, parent / "sealed", run_id=id(session))
        setattr(session, _CACHE, seed)
    return clone_seed(seed, installation["root"] / "kit-clone", monkeypatch, run_id=id(session))


def session_seed(request):
    return getattr(request.session, _CACHE)
