"""K1-c7c: 새 사본에만 합성 후보를 DRAFT 결속 / RAW 판으로 저장한다."""
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

from scripts.prepare_kit_purchase_rehearsal import KIT, RUN, verified
from scripts.prepare_kit_reference_context import remap
from scripts.rehearse_kit_factory_connection import ROOT, REVIEW, backup, digest, ro, tables
from core.data_preparation.kit_logistics_revision import fingerprint
from core.data_preparation.kit_procurement_reference_revision import plan_reference_revision, inspect_procurement, IDENTITIES
from core.data_preparation.kit_sample_audit import read_package
from core.data_preparation import snapshot_service as ss

COUNTS = {"MDM-01": 220, "MDM-02": 40, "PRC-01": 100, "PRC-02": 1800}


def payload_for(rows):
    """후보 문자열을 변경하지 않는 CSV. 파싱 왕복도 적재 전에 확인한다."""
    if not rows:
        raise ValueError("빈 후보")
    columns = list(rows[0])
    if any(set(row) != set(columns) or any(not isinstance(v, str) for v in row.values()) for row in rows):
        raise ValueError("열 또는 자료형이 달라졌습니다")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    payload = stream.getvalue().encode("utf-8-sig")
    if ss.parse_csv(payload, file_name="candidate.csv").rows != rows:
        raise ValueError("CSV 왕복 변환 손실")
    return payload


def grouped_candidates(candidate, tenant, allowed):
    """회사·범위·업무키·합성 표시를 확인하고 범위별로 손실 없이 나눈다."""
    if {k: len(v) for k, v in candidate.items()} != COUNTS:
        raise ValueError("후보 모수 변경")
    groups = defaultdict(list)
    for key, rows in candidate.items():
        seen = set()
        for row in rows:
            identity = row[IDENTITIES[key]]
            if not identity or identity in seen:
                raise ValueError("누락/중복 업무키")
            seen.add(identity)
            if row["tenant_id"] != tenant or row["scope_node_id"] not in allowed[key]:
                raise ValueError("후보 회사/범위 불일치")
            if (row["data_origin"], row["data_class"], row["certification_status"], row["quality_status"]) != (
                    "SYNTHETIC", "SYNTHETIC", "UNVERIFIED_CANDIDATE", "PENDING_VALIDATION"):
                raise ValueError("합성 미검증 후보가 아닙니다")
            groups[(key, row["scope_node_id"])].append(row)
    if len(groups) != 7:
        raise ValueError("예상한 7개 범위별 판이 아닙니다")
    for rows in groups.values():
        payload_for(rows)
    return dict(groups)


def sqlite_guard(target, read_paths):
    """쓰기 가능한 DB는 새 사본 단 하나. 원본은 정확한 RO URI만 허용."""
    read_uris = {p.resolve().as_uri() + "?mode=ro" for p in read_paths}
    def guard(event, args):
        if event != "sqlite3.connect":
            return
        value = str(args[0])
        if value in read_uris:
            return
        if value.startswith("file:") or Path(value).resolve() != target:
            raise PermissionError("새 RAW 사본 밖의 SQLite 쓰기는 금지합니다")
    return guard


def main():
    purchase = verified(RUN / "purchase-preparation.json", "proposal_fingerprint")
    reference = verified(RUN / "reference-context-preparation.json", "proposal_fingerprint")
    connection = verified(RUN / "result.json", "report_fingerprint")
    plan = verified(REVIEW / "department-alignment-plan.json", "plan_fingerprint")
    refs = verified(REVIEW / "reference-candidate.json", "proposal_fingerprint")
    logistics = verified(REVIEW / "candidate.json", "proposal_fingerprint")
    if (reference["parent_purchase_fingerprint"] != purchase["proposal_fingerprint"] or
            reference["parent_connection_fingerprint"] != connection["report_fingerprint"] or
            purchase["parent_connection_fingerprint"] != connection["report_fingerprint"] or
            reference["parent_reference_fingerprint"] != refs["proposal_fingerprint"] or
            purchase["parent_reference_fingerprint"] != refs["proposal_fingerprint"] or
            purchase["parent_logistics_fingerprint"] != logistics["proposal_fingerprint"] or
            connection["plan_fingerprint"] != plan["plan_fingerprint"]):
        raise ValueError("부모 보고서 연결 변경")
    if refs != plan_reference_revision(KIT, REVIEW / "candidate.json"):
        raise ValueError("현재 원천에서 재생성한 참조 후보 불일치")
    manifest, raw, _, files, errors = read_package(KIT, "full")
    if errors or any(files[k] != reference["source_files"][k] for k in reference["source_files"]):
        raise ValueError("키트 원천 변경")
    factories = {m["source_scope_node_id"]: m["target_scope_node_id"] for m in connection["mapping"]}
    expected_refs, changes = remap({k: refs["candidate_rows"].get(k, raw[k]) for k in COUNTS if k != "PRC-02"},
        tenant=plan["target_tenant_id"], company=plan["target_company_node_id"], factories=factories,
        source_tenant=plan["source_tenant_id"])
    expected_purchase = [{**r, "tenant_id": plan["target_tenant_id"], "scope_node_id": factories[r["scope_node_id"]]}
                         for r in logistics["candidate_rows"]["PRC-02"]]
    if expected_refs != reference["candidate_rows"] or changes != reference["changes"] or expected_purchase != purchase["candidate_rows"]["PRC-02"]:
        raise ValueError("후보를 원천에서 재현할 수 없습니다")
    candidate = {**expected_refs, "PRC-02": expected_purchase}
    groups = grouped_candidates(candidate, plan["target_tenant_id"],
        {k: {plan["target_company_node_id"]} if k == "MDM-02" else set(factories.values()) for k in COUNTS})
    reconciliation, _ = inspect_procurement(candidate)
    if any(reconciliation.values()):
        raise ValueError("한정 참조 대사 실패")

    originals = {"preparation": ROOT / "data/data_preparation.db", "master": ROOT / "data/master/master.db",
                 "ecm": ROOT / "data/enterprise_context.db", "ledger": ROOT / "data/decision_ledger.db"}
    old_copies = {k: Path(v) for k, v in connection["copy_paths"].items()}
    for k, p in old_copies.items():
        if digest(tables(p)) != connection["copy_table_fingerprints"][k]:
            raise ValueError("기존 조직 사본 변경")
    before = {k: tables(p) for k, p in originals.items()}
    file_before = {p: p.read_bytes() for p in (ROOT / "data/instance.json", ROOT / "data/scope_policy.json")}
    manifest_checksum = hashlib.sha256((KIT / "manifest.json").read_bytes()).hexdigest()
    run = Path(tempfile.mkdtemp(prefix="raw-stage-", dir=RUN)).resolve()
    target = run / "data_preparation.db"
    if not run.is_relative_to(RUN.resolve()) or target.exists():
        raise ValueError("새 사본 경로가 아닙니다")
    sys.addaudithook(sqlite_guard(target, [*originals.values(), *old_copies.values(), target]))
    backup(originals["preparation"], target)
    if tables(target) != before["preparation"]:
        raise ValueError("백업 중 원본 변경")
    # 전역 저장소도 원본을 가리키지 않도록 import 전에 사본으로 바꾼다.
    import core.paths
    core.paths.DATA_DIR = str(run)
    from core.data_preparation.store import DataPreparationStore, data_preparation_store
    if Path(data_preparation_store.db_path).resolve() != target:
        raise ValueError("기본 저장소가 사본을 가리키지 않습니다")
    store = DataPreparationStore(db_path=str(target))
    kit = store.get_kit_version(manifest["kit_id"], manifest["version"])
    if not kit or kit["fingerprint"] != manifest_checksum or kit["mode"] != "DEMO/SYNTHETIC" or kit["status"] != "active":
        raise ValueError("등록 키트와 원문 지문 불일치")
    # 초기화의 마이그레이션도 기존 행을 건드렸다면 적재하지 않는다.
    if tables(target) != before["preparation"]:
        raise ValueError("저장소 초기화가 기존 행/테이블을 변경했습니다")
    instances, snapshots = {}, []
    for (key, scope), rows in sorted(groups.items()):
        context = dict(tenant_id=plan["target_tenant_id"], scope_node_id=scope, entity_mode="REAL")
        if scope not in instances:
            instances[scope] = store.create_instance(kit_id=kit["kit_id"], version=kit["version"],
                kit_fingerprint=kit["fingerprint"], **context, label="K1-c7c · 사본 RAW 리허설 · 합성 미인증",
                created_by="codex-rehearsal")
        payload = payload_for(rows)
        file_name = f"{key}__{scope}__synthetic_candidate.csv"
        parent = purchase if key == "PRC-02" else reference
        config = {"file_name": file_name, "column_map": {c: c for c in rows[0]},
                  "candidate_fingerprint": parent["proposal_fingerprint"], "payload_sha256": ss.checksum_bytes(payload),
                  "candidate_artifact": str(RUN / ("purchase-preparation.json" if key == "PRC-02" else "reference-context-preparation.json")),
                  "rehearsal_only": True, "expected_row_count": len(rows)}
        binding = store.create_binding(instance_id=instances[scope]["instance_id"], dataset_contract_key=key,
            provider="FILE_SNAPSHOT", config=config, **context, created_by="codex-rehearsal")
        snap = ss.ingest(store, binding=binding, payload=payload, file_name=file_name,
                         workspace_root=str(run), created_by="codex-rehearsal", data_kind="DEMO/SYNTHETIC")
        stored = Path(snap["raw_path"])
        if not stored.resolve().is_relative_to(run) or stored.read_bytes() != payload or not ss.verify_raw(str(stored), snap["checksum"]):
            raise ValueError("RAW 바이트 또는 저장 경계 불일치")
        if ss.parse_csv(stored.read_bytes(), file_name=file_name).rows != rows:
            raise ValueError("저장 후 전체 행 불일치")
        if snap["state"] != "RAW" or snap["certified_at"] or store.get_binding(binding["binding_id"])["state"] != "DRAFT":
            raise ValueError("RAW/DRAFT 밖의 상태 변경")
        if snap["row_count"] != len(rows) or snap["byte_size"] != len(payload) or snap["data_kind"] != "DEMO/SYNTHETIC":
            raise ValueError("저장 메타데이터 불일치")
        snapshots.append({k: snap[k] for k in ("snapshot_id", "binding_id", "instance_id", "dataset_contract_key",
            "tenant_id", "scope_node_id", "entity_mode", "state", "data_kind", "row_count", "byte_size", "checksum", "raw_path")})

    after = tables(target)
    allowed_added = {"kit_instances": 3, "source_bindings": 7, "dataset_snapshots": 7}
    if set(after) != set(before["preparation"]):
        raise ValueError("예상 밖 테이블 변경")
    for name, rows in before["preparation"].items():
        if not set(rows).issubset(after[name]) or len(after[name]) - len(rows) != allowed_added.get(name, 0):
            raise ValueError("허용 범위 밖 사본 행 변경: " + name)
    for k, path in originals.items():
        if tables(path) != before[k]:
            raise ValueError("검증 중 원본 DB 행 변경: " + k)
    if any(digest(tables(p)) != connection["copy_table_fingerprints"][k] for k, p in old_copies.items()):
        raise ValueError("기존 조직 사본 변경")
    if any(p.read_bytes() != b for p, b in file_before.items()):
        raise ValueError("설치 설정/정책 변경")
    with closing(ro(target)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("사본 무결성 검사 실패")
    report = {"status": "COPY_RAW_VERIFIED", "installed": False, "executable": False,
        "created_at": datetime.now(timezone.utc).isoformat(), "copy_path": str(target),
        "parent_reference_fingerprint": reference["proposal_fingerprint"], "parent_purchase_fingerprint": purchase["proposal_fingerprint"],
        "parent_connection_fingerprint": connection["report_fingerprint"], "snapshots": snapshots,
        "row_counts": dict(Counter({k: sum(s["row_count"] for s in snapshots if s["dataset_contract_key"] == k) for k in COUNTS})),
        "added_rows": allowed_added, "source_table_fingerprints": {k: digest(v) for k, v in before.items()},
        "copy_table_fingerprint": digest(after), "checks": {"all_2160_rows_round_tripped": True, "all_7_raw_checksums": True,
        "old_rows_preserved": True, "installation_rows_unchanged": True, "organization_copies_unchanged": True,
        "settings_policy_unchanged": True, "integrity_check": True},
        "state_note": "status=active is record lifecycle, NOT binding ACTIVE or certification",
        "not_verified": ["ownership approval", "remaining declared dependencies", "certification", "HTTP/browser", "calculation readiness"],
        "next": "Read-only profile and dependency inventory on these RAW files; no automatic approvals"}
    report["report_fingerprint"] = fingerprint(report)
    with (run / "raw-result.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": report["status"], "report": str(run / "raw-result.json"),
        "row_counts": report["row_counts"], "added_rows": allowed_added, "checks": report["checks"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
