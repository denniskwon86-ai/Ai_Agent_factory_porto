"""소비 경계 회귀: 전역 conftest 없이 새 출력 폴더의 SQLite만 허용한다."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--focused", action="store_true", help="새 보류 회귀만 실행")
args = parser.parse_args()
sources = [ROOT / path for path in (
    "core/data_preparation/usage_policy.py", "core/data_preparation/models.py",
    "core/data_preparation/store.py", "core/data_preparation/snapshot_service.py",
    "core/data_preparation/readiness.py", "core/data_preparation/scope_index.py",
    "core/calc_dataset_loader.py", "core/kit_app_builder.py",
    "api/routes/data_preparation_control.py", "tests/test_data_usage_holds.py",
    "tests/test_data_readiness.py", "tests/test_dataset_snapshot.py",
    "tests/test_object_scope_index.py", "tests/test_kit_app_builder.py",
    "tests/test_calc_canary.py", "tests/usage_hold_test_plugin.py")]
before = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
sys.path.insert(0, str(ROOT))
RUN = Path(tempfile.mkdtemp(prefix="usage-holds-", dir=ROOT / "output")).resolve()
connections, blocked = set(), []


def guard(event, args):
    if event != "sqlite3.connect":
        return
    raw = str(args[0])
    if raw.startswith("file:") or not Path(raw).resolve().is_relative_to(RUN):
        blocked.append(raw)
        raise PermissionError("사용 보류 검증은 신규 임시 SQLite에만 연결할 수 있습니다")
    connections.add(str(Path(raw).resolve()))


sys.addaudithook(guard)
import core.paths
core.paths.DATA_DIR = str(RUN / "data")
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
import pytest

names = ["data_usage_holds", "data_readiness", "dataset_snapshot", "object_scope_index", "kit_app_builder", "calc_canary"]
if args.focused:
    names = ["data_usage_holds"]
code = pytest.main(["--noconftest", "-p", "no:cacheprovider", "-p", "tests.usage_hold_test_plugin",
                   "-o", "addopts=", "-q", "--tb=short",
                   "--basetemp", str(RUN / "pytest"), "--junitxml", str(RUN / "tests.xml"),
                   *[str(ROOT / f"tests/test_{name}.py") for name in names]])
after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
report = {"exit_code": int(code), "run_root": str(RUN), "sqlite_paths": sorted(connections),
          "source_hashes_before": before, "source_hashes_after": after, "sources_unchanged": before == after,
          "blocked_sqlite_paths": blocked,
          "repository_conftest_loaded": any(k.endswith("conftest") for k in sys.modules)}
(RUN / "isolation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
summary = {key: value for key, value in report.items() if not key.startswith("source_hashes_")}
print(json.dumps({**summary, "sqlite_paths": len(connections)}, ensure_ascii=False), flush=True)
raise SystemExit(int(code) or int(bool(blocked) or report["repository_conftest_loaded"] or before != after))
