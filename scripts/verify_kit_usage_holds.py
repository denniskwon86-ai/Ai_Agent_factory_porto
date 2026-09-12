"""기존 선행 5종 사본의 보류를 RO 트랜잭션으로 검산한다. 인증·RAW 변경 없음."""
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "output/kit-logistics-review-2026-09-10/factory-rehearsal-7h8jvgww/foundation-raw-0yag5clt"
REPORT = BASE / "foundation-result.json"
report = json.loads(REPORT.read_text(encoding="utf-8"))
target = Path(report["copy_path"]).resolve(strict=True)
assert target.parent == BASE.resolve()
allowed = target.as_uri() + "?mode=ro"
opened = []


def guard(event, args):
    if event == "sqlite3.connect":
        if str(args[0]) != allowed:
            raise PermissionError("명시된 선행자료 사본의 RO URI 외 SQLite 접근 금지")
        opened.append(str(args[0]))


sys.addaudithook(guard)
sys.path.insert(0, str(ROOT))
from core.data_preparation import usage_policy, readiness

before = hashlib.sha256(target.read_bytes()).hexdigest()
checks = []
with closing(sqlite3.connect(allowed, uri=True)) as conn:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    snapshots = [dict(row) for row in conn.execute("SELECT * FROM dataset_snapshots ORDER BY snapshot_id")]
    assert len(snapshots) == 61
    for snapshot in snapshots:
        holds = usage_policy.snapshot_holds(conn, snapshot)
        if not holds:
            continue
        try:
            usage_policy.require_usable_conn(conn, snapshot)
        except usage_policy.UsageHoldError:
            pass
        else:
            raise AssertionError("보류 판이 소비 관문을 통과했습니다")
        binding = dict(conn.execute("SELECT * FROM source_bindings WHERE binding_id=?",
                                    (snapshot["binding_id"],)).fetchone())
        result = readiness.evaluate_dataset(snapshot["dataset_contract_key"], binding=binding,
                                             snapshots=[snapshot], now="2026-09-12T00:00:00Z")
        assert result["reason_code"] == "DATA_USAGE_HOLD" and result["state"] == readiness.UNAVAILABLE
        checks.append({"snapshot_id": snapshot["snapshot_id"], "key": snapshot["dataset_contract_key"],
                       "holds": list(holds), "state_preserved": snapshot["state"], "readiness": result["state"]})
    foundation_ids = {row["snapshot_id"] for row in report["snapshots"]}
    assert len(foundation_ids) == 6 and foundation_ids <= {row["snapshot_id"] for row in checks}
    assert all(set(report["checks"]["usage_holds"]) <= set(row["holds"])
               for row in checks if row["snapshot_id"] in foundation_ids)
after = hashlib.sha256(target.read_bytes()).hexdigest()
assert before == after
run = Path(tempfile.mkdtemp(prefix="usage-holds-artifact-", dir=ROOT / "output"))
result = {"passed": True, "source_report": str(REPORT), "database_sha256_before_after": before,
          "total_snapshots_preserved": len(snapshots), "held_snapshots": len(checks),
          "foundation_held_snapshots": len(foundation_ids),
          "held_by_contract": dict(sorted(Counter(row["key"] for row in checks).items())),
          "checks": checks, "sqlite_readonly_uris": opened, "operational_db_connections": 0,
          "certification_performed": False, "raw_modified": False,
          "code_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in (ROOT / "core/data_preparation/usage_policy.py",
                                       ROOT / "core/data_preparation/readiness.py", Path(__file__))}}
path = run / "verification.json"
path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in result.items() if key not in ("checks", "code_sha256")},
                 ensure_ascii=False))
print(path)
