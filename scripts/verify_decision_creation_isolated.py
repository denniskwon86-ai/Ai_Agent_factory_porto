"""Run focused decision tests without repository conftest or operational SQLite access."""
from pathlib import Path
import argparse
import json
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--browser-report", type=Path)
args = parser.parse_args()
extra_tests = []
if args.browser_report:
    browser_report = args.browser_report.resolve(strict=True)
    if not browser_report.is_relative_to(ROOT / "output"):
        parser.error("browser report must be a local output artifact")
    os.environ["DECISION_BROWSER_REPORT"] = str(browser_report)
    extra_tests.append(str(ROOT / "tests/decision_browser_contract_checks.py"))
sys.path.insert(0, str(ROOT))
RUN = Path(tempfile.mkdtemp(prefix="decision-create-", dir=ROOT / "output")).resolve()
connections = set()
blocked = []


def guard(event, args):
    if event != "sqlite3.connect":
        return
    raw = str(args[0])
    target = Path(raw).resolve()
    if raw.startswith("file:") or not target.is_relative_to(RUN):
        blocked.append(raw)
        raise RuntimeError("Decision verification refused non-isolated SQLite access")
    connections.add(str(target))


sys.addaudithook(guard)
import core.paths
core.paths.DATA_DIR = str(RUN / "data")
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
import pytest

print(f"ISOLATED_RUN={RUN}", flush=True)
code = pytest.main([
    "--noconftest", "-p", "no:cacheprovider", "-o", "addopts=", "-q",
    "--basetemp", str(RUN / "pytest"),
    str(ROOT / "tests/test_decision_source_binding.py"),
    str(ROOT / "tests/test_decision_creation_contract.py"),
    str(ROOT / "tests/test_decision_case.py"),
    str(ROOT / "tests/test_publication_control.py"),
    *extra_tests,
    "--junitxml", str(RUN / "tests.xml"),
])
report = {"exit_code": int(code), "run_root": str(RUN),
          "sqlite_paths": sorted(connections), "blocked_sqlite_paths": blocked,
          "repository_conftest_loaded": any(k.endswith("conftest") for k in sys.modules)}
(RUN / "isolation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({**report, "sqlite_paths": len(connections)}, ensure_ascii=False), flush=True)
raise SystemExit(int(code) or (1 if blocked or report["repository_conftest_loaded"] else 0))
