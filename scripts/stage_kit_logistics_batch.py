"""6종·13,900행을 새 사본에 일괄 RAW 적재. 기존 판·권한·운영 DB는 변경하지 않는다."""
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from core.data_preparation.kit_logistics_revision import fingerprint, inspect_logistics
from core.data_preparation.kit_procurement_reference_revision import IDENTITIES, inspect_procurement
from core.data_preparation.kit_sample_audit import read_package
from core.data_preparation import snapshot_service as ss
from scripts.prepare_kit_purchase_rehearsal import KIT, RUN, verified
from scripts.rehearse_kit_factory_connection import REVIEW, backup, digest, ro, tables
from scripts.inspect_kit_raw_quality import STAGE
from scripts.inspect_kit_integration_plan import LOG_KEYS, overlay, reviewed_context
from scripts.stage_kit_raw_rehearsal import payload_for, sqlite_guard

COUNTS = {"PRC-01": 100, "PRC-02": 1800, "LOG-02": 1200, "LOG-03": 7200, "LOG-04": 1200, "LOG-05": 2400}
KEYS = {**IDENTITIES, **LOG_KEYS}


def grouped_batch(candidate, plan, tenant, scopes):
    """고정된 전체 모집단·업무키·두 공장·계획 지문을 전수 대조한다."""
    if {k: len(v) for k, v in candidate.items()} != COUNTS or len(scopes) != 2:
        raise ValueError("6종·13,900행/두 공장 범위 불일치")
    planned = {r["dataset"]: r for r in plan["next_single_batch"]}
    if len(planned) != 6 or set(planned) != set(COUNTS) or len(plan["next_single_batch"]) != 6:
        raise ValueError("계획의 6종 자료 집합 불일치")
    groups = defaultdict(list)
    for dataset, rows in candidate.items():
        seen = set()
        for row in rows:
            identity = row[KEYS[dataset]]
            if not identity or identity in seen:
                raise ValueError("누락/중복 업무키")
            seen.add(identity)
            if row["tenant_id"] != tenant or row["scope_node_id"] not in scopes:
                raise ValueError("회사/공장 범위 이탈")
            if (row["data_class"], row["data_origin"], row["quality_status"], row["certification_status"]) != (
                "SYNTHETIC", "SYNTHETIC", "PENDING_VALIDATION", "UNVERIFIED_CANDIDATE"):
                raise ValueError("합성 미검증 후보만 RAW로 저장합니다")
            groups[dataset, row["scope_node_id"]].append(row)
        item = planned[dataset]
        if item["rows"] != len(rows) or item["row_fingerprint"] != fingerprint(rows) or item["scope_counts"] != dict(Counter(r["scope_node_id"] for r in rows)):
            raise ValueError("통합 계획 이후 업무값/범위/순서 변경")
    if len(groups) != 12:
        raise ValueError("공장별 12개 RAW 그룹 불일치")
    for rows in groups.values():
        payload_for(rows)
    return dict(groups)


def verify_additions(before, after, added):
    """기존 모든 테이블 행은 그대로 두고 지정한 두 테이블의 추가만 허용한다."""
    if set(before) != set(after):
        raise ValueError("예상 밖 테이블 변경")
    for name, rows in before.items():
        if not Counter(rows) <= Counter(after[name]) or len(after[name]) - len(rows) != added.get(name, 0):
            raise ValueError("기존 행 변경 또는 허용 밖 추가: " + name)


def table_schema(path):
    with closing(ro(path)) as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: list(conn.execute('PRAGMA table_info("' + name.replace('"', '""') + '")')) for name in names}


def verify_initialization(before, after, old_schema, new_schema):
    """기존 열/값 전수 보존 + 제품의 빈 certified_by 열 추가만 허용한다."""
    if not (set(before) == set(after) == set(old_schema) == set(new_schema)):
        raise ValueError("초기화 테이블 집합 변경")
    additions = []
    for name, rows in before.items():
        old, new = old_schema[name], new_schema[name]
        if old == new:
            if Counter(rows) != Counter(after[name]):
                raise ValueError("초기화 중 기존 행 변경: " + name)
            continue
        expected = (len(old), "certified_by", "TEXT", 1, "''", 0)
        if name != "dataset_snapshots" or any(c[1] == "certified_by" for c in old) or new != [*old, expected]:
            raise ValueError("허용하지 않은 스키마 변경: " + name)
        if any(len(r) != len(new) or r[-1] != "" for r in after[name]):
            raise ValueError("신규 인증자 열은 빈 값이어야 합니다")
        if Counter(rows) != Counter(tuple(r[:-1]) for r in after[name]):
            raise ValueError("인증자 열 추가 과정에서 기존 값 변경")
        additions.append({"table": name, "column": "certified_by", "definition": "TEXT NOT NULL DEFAULT ''",
            "old_column_names": [c[1] for c in old], "preserved_rows": len(rows), "all_new_values_empty": True,
            "old_values_fingerprint": digest(sorted(rows, key=repr))})
    return {"old_columns_and_values_preserved": True, "additive_schema_changes": additions,
        "approval_values_added": False, "source_schema_fingerprint": digest(old_schema),
        "initialized_schema_fingerprint": digest(new_schema)}


def main():
    parents = {"plan": (STAGE / "integration-batch-plan.json", "report_fingerprint"),
        "price": (STAGE / "price-candidate.json", "proposal_fingerprint"),
        "finance": (STAGE / "financial-candidate.json", "proposal_fingerprint"),
        "raw": (STAGE / "raw-result.json", "report_fingerprint"),
        "logistics": (REVIEW / "candidate.json", "proposal_fingerprint"),
        "connection": (RUN / "result.json", "report_fingerprint")}
    reports = {k: verified(*v) for k, v in parents.items()}
    plan, price, finance, raw, logistics, connection = (reports[k] for k in parents)
    if plan["installed"] or plan["executable"] or plan["certification_or_ownership_approval"]:
        raise ValueError("비설치 통합 계획 상태가 아닙니다")
    for k in ("price", "finance", "raw", "logistics", "connection"):
        if plan["parent_fingerprints"][k] != reports[k][parents[k][1]]:
            raise ValueError("통합 계획 부모 연결 불일치")
    runtime_paths = [Path(__file__).resolve(), *(Path(__file__).resolve().parents[1] / p for p in (
        "core/data_preparation/store.py", "core/data_preparation/snapshot_service.py", "core/data_preparation/ownership_binding.py"))]
    watched = {**plan["input_hashes_before_and_after"], **{str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p, _ in parents.values()},
        **{str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime_paths}}
    def unchanged_files():
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != value for p, value in watched.items()):
            raise ValueError("부모 보고서/RAW 원문 변경")
    unchanged_files()
    candidate = {}
    for snap in raw["snapshots"]:
        path = Path(snap["raw_path"]).resolve()
        if not path.is_relative_to(STAGE.resolve()):
            raise ValueError("부모 RAW 경로 이탈")
        parsed = ss.parse_csv(path.read_bytes(), file_name=path.name)
        if parsed.checksum != snap["checksum"] or len(parsed.rows) != snap["row_count"]:
            raise ValueError("부모 RAW 지문/모수 불일치")
        candidate.setdefault(snap["dataset_contract_key"], []).extend(parsed.rows)
    manifest, source, contracts, files, errors = read_package(KIT, "full")
    if errors or files != plan["source_files_before_and_after"]:
        raise ValueError("검토한 원천 파일 변경")
    mapping = {m["source_scope_node_id"]: m["target_scope_node_id"] for m in connection["mapping"]}
    if mapping != plan["context_mapping_applied_only_in_memory"]:
        raise ValueError("공장 연결 계획 변경")
    target_tenants = {r["tenant_id"] for r in candidate["PRC-02"]}
    source_tenants = {r["tenant_id"] for r in logistics["candidate_rows"]["PRC-02"]}
    if len(target_tenants) != 1 or len(source_tenants) != 1:
        raise ValueError("복수 회사 문맥")
    tenant, source_tenant = next(iter(target_tenants)), next(iter(source_tenants))
    for key in ("PRC-01", "PRC-02"):
        candidate[key] = overlay(candidate[key], price["candidate_rows"][key], IDENTITIES[key])
    for key, identity in LOG_KEYS.items():
        rows = logistics["candidate_rows"][key]
        if key == "LOG-04":
            rows = overlay(rows, finance["candidate_rows"][key], identity)
        candidate[key] = reviewed_context(rows, mapping, source_tenant, tenant)
    groups = grouped_batch({k: candidate[k] for k in COUNTS}, plan, tenant, set(mapping.values()))
    procurement, _ = inspect_procurement(candidate)
    log_check = inspect_logistics(candidate, contracts)
    if any(procurement.values()) or log_check["issues"]:
        raise ValueError("적재 전 참조/수량/날짜 대사 실패")

    run = Path(tempfile.mkdtemp(prefix="logistics-raw-batch-", dir=RUN)).resolve()
    target = run / "data_preparation.db"
    source_db = (STAGE / "data_preparation.db").resolve()
    org_copies = {k: Path(p).resolve() for k, p in connection["copy_paths"].items()}
    if not run.is_relative_to(RUN.resolve()) or run == STAGE.resolve() or target.exists():
        raise ValueError("새 격리 사본 경로 불일치")
    # 원본 운영 DB/공유 원장은 읽기도 허용하지 않는다. 쓰기는 새 사본 하나뿐이다.
    sys.addaudithook(sqlite_guard(target, [source_db, target, *org_copies.values()]))
    print(json.dumps({"phase": "ISOLATED_COPY_START", "directory": str(run)}, ensure_ascii=True), flush=True)
    before = tables(source_db)
    source_schema = table_schema(source_db)
    if digest(before) != raw["copy_table_fingerprint"]:
        raise ValueError("부모 사본이 RAW 증적 이후 변경됐습니다")
    for key, path in org_copies.items():
        if digest(tables(path)) != connection["copy_table_fingerprints"][key]:
            raise ValueError("기존 조직 사본 변경")
    backup(source_db, target)
    if tables(target) != before or table_schema(target) != source_schema:
        raise ValueError("SQLite 백업 대조 실패")
    import core.paths
    core.paths.DATA_DIR = str(run)
    from core.data_preparation.store import DataPreparationStore, data_preparation_store
    if Path(data_preparation_store.db_path).resolve() != target:
        raise ValueError("기본 저장소 격리 실패")
    store = DataPreparationStore(db_path=str(target))
    kit = store.get_kit_version(manifest["kit_id"], manifest["version"])
    manifest_sha = hashlib.sha256((KIT / "manifest.json").read_bytes()).hexdigest()
    if not kit or kit["fingerprint"] != manifest_sha or kit["mode"] != "DEMO/SYNTHETIC" or kit["status"] != "active":
        raise ValueError("등록 키트 지문/상태 불일치")
    initialized_before, initialized_schema = tables(target), table_schema(target)
    initialization = verify_initialization(before, initialized_before, source_schema, initialized_schema)
    print(json.dumps({"phase": "SCHEMA_COMPATIBILITY_VERIFIED", **initialization}, ensure_ascii=True), flush=True)
    instances = {}
    for scope in mapping.values():
        ids = {s["instance_id"] for s in raw["snapshots"] if s["scope_node_id"] == scope}
        if len(ids) != 1:
            raise ValueError("기존 공장 인스턴스가 유일하지 않습니다")
        instance = store.get_instance(next(iter(ids)))
        if not instance or any(instance[k] != v for k, v in {"tenant_id": tenant, "scope_node_id": scope,
                "entity_mode": "REAL", "kit_id": manifest["kit_id"], "version": manifest["version"],
                "kit_fingerprint": manifest_sha, "status": "active"}.items()):
            raise ValueError("기존 인스턴스 문맥/키트 불일치")
        instances[scope] = instance["instance_id"]
    snapshots, reread = [], defaultdict(list)
    for (key, scope), rows in sorted(groups.items()):
        payload = payload_for(rows)
        file_name = f"{key}__{scope}__synthetic_candidate.csv"
        previous = [s["snapshot_id"] for s in raw["snapshots"] if s["dataset_contract_key"] == key and s["scope_node_id"] == scope]
        config = {"file_name": file_name, "column_map": {c: c for c in rows[0]}, "expected_row_count": len(rows),
            "payload_sha256": ss.checksum_bytes(payload), "integration_plan_fingerprint": plan["report_fingerprint"],
            "price_candidate_fingerprint": price["proposal_fingerprint"], "financial_candidate_fingerprint": finance["proposal_fingerprint"],
            "preserved_previous_raw_ids": previous, "rehearsal_only": True, "price_hold_runtime_enforcement_installed": False}
        binding = store.create_binding(instance_id=instances[scope], dataset_contract_key=key, provider="FILE_SNAPSHOT",
            config=config, tenant_id=tenant, scope_node_id=scope, entity_mode="REAL", created_by="codex-rehearsal-batch")
        snap = ss.ingest(store, binding=binding, payload=payload, file_name=file_name, workspace_root=str(run),
            created_by="codex-rehearsal-batch", data_kind="DEMO/SYNTHETIC")
        stored = Path(snap["raw_path"]).resolve()
        if not stored.is_relative_to(run) or stored.read_bytes() != payload:
            raise ValueError("새 RAW 경로/바이트 불일치")
        parsed = ss.parse_csv(stored.read_bytes(), file_name=file_name)
        if parsed.rows != rows or parsed.checksum != snap["checksum"] or snap["row_count"] != len(rows) or snap["byte_size"] != len(payload):
            raise ValueError("RAW 13,900행 왕복 또는 메타데이터 손실")
        if snap["state"] != "RAW" or snap["certified_at"] or snap.get("certified_by") or snap["data_kind"] != "DEMO/SYNTHETIC" or store.get_binding(binding["binding_id"])["state"] != "DRAFT":
            raise ValueError("RAW/DRAFT 밖 상태 변경")
        reread[key].extend(parsed.rows)
        snapshots.append({**{k: snap[k] for k in ("snapshot_id", "binding_id", "instance_id", "dataset_contract_key", "tenant_id",
            "scope_node_id", "entity_mode", "state", "data_kind", "row_count", "byte_size", "checksum", "raw_path")},
            "preserved_previous_raw_ids": previous})
        print(json.dumps({"phase": "RAW_GROUP_VERIFIED", "group": len(snapshots), "of": 12, "dataset": key, "rows": len(rows)}, ensure_ascii=True), flush=True)
    loaded = {**candidate, **reread}
    after_procurement, _ = inspect_procurement(loaded)
    after_logistics = inspect_logistics(loaded, contracts)
    if any(after_procurement.values()) or after_logistics["issues"]:
        raise ValueError("저장 후 참조/수량/날짜 대사 실패")
    for key, rows in reread.items():
        if sorted(rows, key=lambda r: r[KEYS[key]]) != sorted(candidate[key], key=lambda r: r[KEYS[key]]):
            raise ValueError("자료 전체 재조회 불일치")
    after = tables(target)
    added = {"source_bindings": 12, "dataset_snapshots": 12}
    verify_additions(initialized_before, after, added)
    if table_schema(target) != initialized_schema or table_schema(source_db) != source_schema:
        raise ValueError("적재 중 스키마 변경")
    if tables(source_db) != before or any(digest(tables(p)) != connection["copy_table_fingerprints"][k] for k, p in org_copies.items()):
        raise ValueError("기존 사본 보존 실패")
    unchanged_files()
    _, _, _, after_files, after_errors = read_package(KIT, "full")
    if after_errors or after_files != files:
        raise ValueError("적재 중 원천 변경")
    with closing(ro(target)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("새 사본 무결성 실패")
    report = {"status": "COPY_BATCH_RAW_VERIFIED_NOT_INSTALLED", "installed": False, "executable": False, "certified": False,
        "created_at": datetime.now(timezone.utc).isoformat(), "copy_path": str(target), "source_copy_path": str(source_db),
        "parent_plan_fingerprint": plan["report_fingerprint"], "parent_raw_fingerprint": raw["report_fingerprint"],
        "snapshots": snapshots, "row_counts": COUNTS, "added_rows": added, "reused_factory_instances": instances,
        "source_copy_fingerprint_before_and_after": digest(before), "copy_table_fingerprint": digest(after),
        "initialization": initialization, "initialized_copy_table_fingerprint": digest(initialized_before),
        "input_hashes_before_and_after": watched, "source_files_before_and_after": files,
        "procurement_reconciliation": after_procurement, "logistics_reconciliation": after_logistics,
        "checks": {"all_13900_rows_round_tripped": True, "all_12_raw_checksums": True, "old_rows_and_7_RAW_preserved": True,
            "existing_organization_copies_unchanged": True, "only_12_DRAFT_bindings_and_12_RAW_snapshots_added": True,
            "no_instances_or_approval_rows_added": True, "integrity_check": True},
        "selected_core_snapshot_ids": [s["snapshot_id"] for s in raw["snapshots"] if s["dataset_contract_key"] in ("MDM-01", "MDM-02")] + [s["snapshot_id"] for s in snapshots],
        "core_RAW_datasets": {"before": 4, "after": 8, "target": 8}, "batch_datasets": {"completed": 6, "target": 6},
        "core_selected_rows": 14160, "historical_RAW_paths_still_external": True,
        "deferred": plan["deferred"], "target_reference_datasets": plan["target_reference_datasets"],
        "not_verified": ["foundation alignment/certification", "runtime hold enforcement", "ownership approval",
            "operational installation", "HTTP/browser/T3", "previous full regression ledger sentinel error"],
        "next": "선행 5종 FND-01/03·MDM-04/08·EXT-02 문맥/품질/참조를 한 묶음으로 정렬; 실제 인증/승인은 별도"}
    report["report_fingerprint"] = fingerprint(report)
    with (run / "batch-result.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": report["status"], "report": str(run / "batch-result.json"), "row_counts": COUNTS,
        "checks": report["checks"], "report_fingerprint": report["report_fingerprint"]}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
