"""초기 선행 5종을 새 RAW 사본에 정렬·저장. 기존 판·원문·원장·권한은 불변."""
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUN = ROOT / "output/kit-logistics-review-2026-09-10/factory-rehearsal-7h8jvgww"
PARENT = RUN / "logistics-raw-batch-eweopj4t"


def main():
    # 제품 모듈보다 먼저 경계를 고정한다. SQLite 쓰기는 새 파일 하나에만 허용한다.
    run = Path(tempfile.mkdtemp(prefix="foundation-raw-", dir=RUN)).resolve()
    target = run / "data_preparation.db"
    source_db = PARENT / "data_preparation.db"
    org_paths = {"master": RUN / "master/master.db", "ecm": RUN / "enterprise_context.db"}
    ro_uris = {p.resolve().as_uri() + "?mode=ro" for p in (source_db, target, *org_paths.values())}
    opened, blocked = set(), []
    def guard(event, args):
        if event != "sqlite3.connect":
            return
        raw = str(args[0])
        if raw not in ro_uris and (raw.startswith("file:") or Path(raw).resolve() != target):
            blocked.append(raw)
            raise PermissionError("새 선행자료 사본 밖 SQLite 접근 거부")
        opened.add(raw)
    sys.addaudithook(guard)
    import core.paths
    core.paths.DATA_DIR = str(run)
    from core.data_preparation.kit_foundation_alignment import FOUNDATION, prepare_foundation, inspect_foundation_links
    from core.data_preparation.kit_sample_audit import read_package
    from core.data_preparation.kit_department_alignment import read_organization
    from core.data_preparation.kit_logistics_revision import fingerprint, inspect_logistics
    from core.data_preparation.kit_procurement_reference_revision import inspect_procurement
    from core.data_preparation import snapshot_service as ss
    from scripts.prepare_kit_purchase_rehearsal import KIT, verified
    from scripts.rehearse_kit_factory_connection import REVIEW, backup, digest, tables, ro
    from scripts.stage_kit_raw_rehearsal import payload_for
    from scripts.stage_kit_logistics_batch import table_schema, verify_initialization, verify_additions
    from scripts.inspect_kit_raw_quality import STAGE, field_profile
    from scripts.inspect_kit_integration_plan import dependency_layers, CORE_KEYS

    parent_paths = {"batch": (PARENT / "batch-result.json", "report_fingerprint"),
        "raw": (STAGE / "raw-result.json", "report_fingerprint"),
        "connection": (RUN / "result.json", "report_fingerprint"),
        "alignment": (REVIEW / "department-alignment-plan.json", "plan_fingerprint"),
        "integration": (STAGE / "integration-batch-plan.json", "report_fingerprint")}
    reports = {k: verified(*v) for k, v in parent_paths.items()}
    batch, raw, connection, alignment, integration = (reports[k] for k in parent_paths)
    if (batch["installed"] or batch["executable"] or batch["certified"]
        or batch["parent_raw_fingerprint"] != raw["report_fingerprint"]
        or batch["parent_plan_fingerprint"] != integration["report_fingerprint"]
        or connection["plan_fingerprint"] != alignment["plan_fingerprint"]
        or raw["parent_connection_fingerprint"] != connection["report_fingerprint"]):
        raise ValueError("부모 증적/비설치 경계 불일치")
    before, schema = tables(source_db), table_schema(source_db)
    if digest(before) != batch["copy_table_fingerprint"]:
        raise ValueError("부모 RAW 사본 변경")
    for key, path in org_paths.items():
        if digest(tables(path)) != connection["copy_table_fingerprints"][key]:
            raise ValueError("조직 사본 변경")
    manifest, source, contracts, files, errors = read_package(KIT, "full")
    if errors or files != batch["source_files_before_and_after"]:
        raise ValueError("원천 키트 변경")
    organization = read_organization(org_paths["master"], org_paths["ecm"])
    prepared = prepare_foundation(source, contracts, organization,
        source_tenant=alignment["source_tenant_id"], tenant=alignment["target_tenant_id"],
        company=alignment["target_company_node_id"],
        factories={r["source_scope_node_id"]: r["target_scope_node_id"] for r in connection["mapping"]},
        as_of=connection["created_at"])
    candidate = prepared["candidate_rows"]
    if {k: len(v) for k, v in candidate.items()} != {"FND-01": 6, "FND-03": 1101, "MDM-04": 7, "MDM-08": 43, "EXT-02": 240}:
        raise ValueError("검토한 선행자료 1,397행 모수 변경")
    if len(prepared["held_source_rows"]) != 1:
        raise ValueError("미매핑 증설창고 1행 보존 경계 변경")
    watched = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path, _ in parent_paths.values()}
    for path in [KIT / "manifest.json", *[KIT / "contracts" / (key + ".contract.json") for key in contracts]]:
        watched[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    for relative in ("core/data_preparation/kit_foundation_alignment.py", "core/data_preparation/store.py",
                     "core/data_preparation/snapshot_service.py", "scripts/stage_kit_foundation_batch.py"):
        path = ROOT / relative
        watched[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    core_rows, selected = defaultdict(list), []
    catalog = {s["snapshot_id"]: s for s in [*raw["snapshots"], *batch["snapshots"]]}
    with closing(ro(source_db)) as conn:
        import sqlite3
        conn.row_factory = sqlite3.Row
        for sid in batch["selected_core_snapshot_ids"]:
            snap = dict(conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id=?", (sid,)).fetchone())
            info = catalog[sid]
            path = Path(snap["raw_path"]).resolve()
            if not path.is_relative_to(RUN.resolve()):
                raise ValueError("부모 RAW 경로 이탈")
            payload = path.read_bytes()
            parsed = ss.parse_csv(payload, file_name=path.name)
            if parsed.checksum != info["checksum"] or parsed.checksum != snap["checksum"] or len(parsed.rows) != snap["row_count"]:
                raise ValueError("부모 RAW 메타데이터/행 불일치")
            if snap["state"] != "RAW" or snap["data_kind"] != "DEMO/SYNTHETIC" or snap["certified_at"] or snap.get("certified_by"):
                raise ValueError("부모 RAW 상태 변경")
            if any(r["tenant_id"] != snap["tenant_id"] or r["scope_node_id"] != snap["scope_node_id"] for r in parsed.rows):
                raise ValueError("부모 행 문맥 혼입")
            core_rows[snap["dataset_contract_key"]].extend(parsed.rows)
            selected.append(snap)
            watched[str(path)] = hashlib.sha256(payload).hexdigest()
    if len(core_rows) != 8 or sum(map(len, core_rows.values())) != 14160:
        raise ValueError("핵심 8종·14,160행 모수 변경")
    combined = {**core_rows, **candidate}
    checks = inspect_foundation_links(combined, contracts)
    procurement, _ = inspect_procurement(combined)
    logistics = inspect_logistics(combined, contracts)
    profiles = {key: field_profile(rows, contracts[key]) for key, rows in candidate.items()}
    closure = {key for layer in dependency_layers(contracts, CORE_KEYS) for key in layer}
    if (checks["structural_issues"] or any(procurement.values()) or logistics["issues"]
            or closure != set(combined) or any(p["missing_required"] or p["invalid_values"] for p in profiles.values())):
        raise ValueError("선행자료 구조·필수값·자료형·13종 참조 검사 실패")
    print(json.dumps({"phase": "FOUNDATION_CHECKED", "datasets": 5, "rows": 1397,
        "held_warehouse_rows": 1, "references": checks["reference_counts"]}), flush=True)
    backup(source_db, target)
    if tables(target) != before or table_schema(target) != schema:
        raise ValueError("사본 백업 대사 실패")
    from core.data_preparation.store import DataPreparationStore, data_preparation_store
    if Path(data_preparation_store.db_path).resolve() != target:
        raise ValueError("기본 저장소 격리 실패")
    store = DataPreparationStore(db_path=str(target))
    registered = store.get_kit_version(manifest["kit_id"], manifest["version"])
    manifest_sha = hashlib.sha256((KIT / "manifest.json").read_bytes()).hexdigest()
    if not registered or registered["fingerprint"] != manifest_sha or registered["status"] != "active" or registered["mode"] != "DEMO/SYNTHETIC":
        raise ValueError("등록 키트 지문/상태 불일치")
    initialized, initialized_schema = tables(target), table_schema(target)
    initialization = verify_initialization(before, initialized, schema, initialized_schema)
    instances = {}
    for snap in selected:
        instance = store.get_instance(snap["instance_id"])
        if not instance or any(instance[k] != value for k, value in {
            "tenant_id": alignment["target_tenant_id"], "scope_node_id": snap["scope_node_id"],
            "entity_mode": "REAL", "kit_id": manifest["kit_id"], "version": manifest["version"],
            "kit_fingerprint": manifest_sha, "status": "active"}.items()):
            raise ValueError("기존 인스턴스 불일치")
        scope = snap["scope_node_id"]
        if scope in instances and instances[scope] != snap["instance_id"]:
            raise ValueError("범위별 인스턴스가 모호합니다")
        instances[scope] = snap["instance_id"]
    groups = defaultdict(list)
    for key, rows in candidate.items():
        for row in rows:
            groups[key, row["scope_node_id"]].append(row)
    if len(groups) != 6:
        raise ValueError("회사/두 공장의 6개 RAW 그룹 불일치")
    snapshots, reread = [], defaultdict(list)
    for (key, scope), rows in sorted(groups.items()):
        payload = payload_for(rows)
        filename = key + "__foundation_candidate.csv"
        binding = store.create_binding(instance_id=instances[scope], dataset_contract_key=key,
            provider="FILE_SNAPSHOT", tenant_id=alignment["target_tenant_id"], scope_node_id=scope,
            entity_mode="REAL", created_by="codex-foundation-rehearsal", config={
                "file_name": filename, "column_map": {c: c for c in rows[0]}, "rehearsal_only": True,
                "payload_sha256": ss.checksum_bytes(payload), "expected_row_count": len(rows),
                "foundation_fingerprint": prepared["candidate_rows_fingerprint"],
                "parent_batch_fingerprint": batch["report_fingerprint"], "usage_holds": checks["usage_holds"]})
        snap = ss.ingest(store, binding=binding, payload=payload, file_name=filename,
            workspace_root=str(run), created_by="codex-foundation-rehearsal", data_kind="DEMO/SYNTHETIC")
        path = Path(snap["raw_path"]).resolve()
        if not path.is_relative_to(run) or path.read_bytes() != payload:
            raise ValueError("새 RAW 경로/바이트 불일치")
        parsed = ss.parse_csv(path.read_bytes(), file_name=filename)
        if parsed.rows != rows or snap["row_count"] != len(rows) or snap["byte_size"] != len(payload) or snap["checksum"] != parsed.checksum:
            raise ValueError("RAW 왕복/메타데이터 손실")
        if snap["state"] != "RAW" or snap["certified_at"] or snap.get("certified_by") or store.get_binding(binding["binding_id"])["state"] != "DRAFT":
            raise ValueError("사용 승인 상태로 변환 금지")
        snapshots.append(snap)
        reread[key].extend(parsed.rows)
        print(json.dumps({"phase": "FOUNDATION_RAW_VERIFIED", "group": len(snapshots), "of": 6,
                          "dataset": key, "rows": len(rows)}), flush=True)
    if inspect_foundation_links({**core_rows, **reread}, contracts) != checks:
        raise ValueError("저장 후 13종 참조 대사 변경")
    after = tables(target)
    verify_additions(initialized, after, {"source_bindings": 6, "dataset_snapshots": 6})
    if tables(source_db) != before or table_schema(target) != initialized_schema or table_schema(source_db) != schema:
        raise ValueError("기존 판/스키마 보존 실패")
    if any(digest(tables(p)) != connection["copy_table_fingerprints"][key] for key, p in org_paths.items()):
        raise ValueError("조직 사본 변경")
    if any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha for path, sha in watched.items()):
        raise ValueError("실행 중 원문/부모/구현 변경")
    _, _, _, after_files, after_errors = read_package(KIT, "full")
    if after_errors or after_files != files or blocked:
        raise ValueError("원천/격리 검증 실패")
    with closing(ro(target)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("사본 무결성 실패")
    result = {**prepared, "status": "FOUNDATION_COPY_RAW_VERIFIED_WITH_USAGE_HOLDS", "created_at": datetime.now(timezone.utc).isoformat(),
        "copy_path": str(target), "parent_batch_fingerprint": batch["report_fingerprint"],
        "parent_reports": {k: r[parent_paths[k][1]] for k, r in reports.items()},
        "snapshots": snapshots, "reused_instances": instances, "new_instances": 0,
        "added_bindings": 6, "added_snapshots": 6, "row_counts": {k: len(v) for k, v in candidate.items()},
        "added_rows": 1397, "selected_dataset_count": 13, "selected_rows": 15557,
        "source_snapshots_preserved": len(before["dataset_snapshots"]),
        "copy_table_fingerprint": digest(after), "parent_table_fingerprint_before_and_after": digest(before),
        "initialization": initialization, "checks": checks, "field_profiles": profiles,
        "procurement": procurement, "logistics": logistics, "source_files_before_and_after": files,
        "input_hashes_before_and_after": watched, "sqlite_connections": sorted(opened), "blocked_sqlite": blocked,
        "runtime_price_hold_enforcement_installed": False,
        "next": "가격/과거 조직 유효성 보류의 사용 경계 강제. 소유권·인증·실사용은 별도 승인."}
    result["report_fingerprint"] = fingerprint(result)
    with (run / "foundation-result.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ("status", "copy_path", "added_rows", "selected_dataset_count",
        "source_snapshots_preserved", "report_fingerprint")}), flush=True)


if __name__ == "__main__":
    main()
