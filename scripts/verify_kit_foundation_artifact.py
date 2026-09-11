"""저장 실행기와 분리된 읽기 전용 검산. 운영 DB/이전 RAW 파일을 열지 않는다."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys

parser = argparse.ArgumentParser()
parser.add_argument("report", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
report_path = args.report.resolve(strict=True)
base = root / "output/kit-logistics-review-2026-09-10/factory-rehearsal-7h8jvgww"
if not report_path.is_relative_to(base.resolve()) or report_path.parent == base.resolve():
    parser.error("정렬 실행의 명시된 output 폴더만 허용합니다")
report = json.loads(report_path.read_text(encoding="utf-8"))
parent = base / "logistics-raw-batch-eweopj4t/data_preparation.db"
target = Path(report["copy_path"]).resolve(strict=True)
if target.parent != report_path.parent or target == parent:
    raise ValueError("검증 대상 사본 경로 불일치")
allowed = {path.resolve().as_uri() + "?mode=ro" for path in (parent, target)}
opened = set()
def guard(event, args):
    if event == "sqlite3.connect":
        if str(args[0]) not in allowed:
            raise PermissionError("검산은 부모/결과 사본의 정확한 RO URI만 허용합니다")
        opened.add(str(args[0]))
sys.addaudithook(guard)
sys.path.insert(0, str(root))
from core.data_preparation.kit_logistics_revision import fingerprint
assert report["report_fingerprint"] == fingerprint({k: v for k, v in report.items() if k != "report_fingerprint"})
assert not report["installed"] and not report["executable"] and not report["certified"]
assert report["candidate_rows_fingerprint"] == fingerprint(report["candidate_rows"])

def read_tables(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        rows = {name: Counter(conn.execute('SELECT * FROM "' + name.replace('"', '""') + '"')) for name in names}
        schema = {name: list(conn.execute('PRAGMA table_info("' + name.replace('"', '""') + '")')) for name in names}
        return rows, schema

before, before_schema = read_tables(parent)
after, after_schema = read_tables(target)
assert before_schema == after_schema and set(before) == set(after)
for name, rows in before.items():
    assert rows <= after[name], name
    assert sum(after[name].values()) - sum(rows.values()) == (6 if name in {"source_bindings", "dataset_snapshots"} else 0), name
assert sum(before["dataset_snapshots"].values()) == 55
assert sum(after["dataset_snapshots"].values()) == 61
loaded = defaultdict(list)
with closing(sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)) as conn:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    for info in report["snapshots"]:
        snap = dict(conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id=?", (info["snapshot_id"],)).fetchone())
        binding = dict(conn.execute("SELECT * FROM source_bindings WHERE binding_id=?", (snap["binding_id"],)).fetchone())
        instance = dict(conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (snap["instance_id"],)).fetchone())
        for field in ("tenant_id", "scope_node_id", "entity_mode", "instance_id"):
            assert snap[field] == binding[field] == instance[field]
        assert binding["state"] == "DRAFT" and snap["state"] == "RAW"
        assert not snap["certified_at"] and not snap["certified_by"]
        assert snap["data_kind"] == "DEMO/SYNTHETIC"
        assert json.loads(binding["config_json"])["usage_holds"] == report["checks"]["usage_holds"]
        path = Path(snap["raw_path"]).resolve(strict=True)
        assert path.is_relative_to(report_path.parent)
        payload = path.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == snap["checksum"] == info["checksum"]
        rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
        assert len(payload) == snap["byte_size"] and len(rows) == snap["row_count"]
        assert all(r["tenant_id"] == snap["tenant_id"] and r["scope_node_id"] == snap["scope_node_id"] for r in rows)
        loaded[snap["dataset_contract_key"]].extend(rows)
for key, rows in loaded.items():
    assert sorted(rows, key=lambda r: r["record_id"]) == sorted(report["candidate_rows"][key], key=lambda r: r["record_id"])
assert sum(map(len, loaded.values())) == 1397
for path, sha in report["input_hashes_before_and_after"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha, path
assert len(report["held_source_rows"]) == 1
assert report["held_source_rows"][0]["source_row"]["location_id"] == "LOC-P3-SIM"
assert not report["checks"]["structural_issues"]
assert report["checks"]["reference_counts"] == {"TRANSPORT_LOCATION": 2400,
    "REFERENCE_INCOTERM": 100, "REFERENCE_PAYMENT_TERM": 100, "BENCHMARK_CODE": 100, "ORDER_CALENDAR": 1800}
result = {"passed": True, "parent_snapshots_preserved": 55, "result_snapshots": 61,
    "new_raw_snapshots": 6, "new_rows": 1397, "held_rows": 1, "report_fingerprint": report["report_fingerprint"],
    "sqlite_readonly_uris": sorted(opened), "operational_sqlite_connections": 0,
    "certification_performed": False, "runtime_hold_enforcement_verified": False}
with (report_path.parent / "independent-verification.json").open("x", encoding="utf-8") as stream:
    json.dump(result, stream, indent=2)
print(json.dumps(result), flush=True)
