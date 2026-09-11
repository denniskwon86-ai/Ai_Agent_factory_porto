"""선행자료 및 기존 RAW/가격/물류 회귀를 DB 연결 없이 실행한다."""
from pathlib import Path
import json
import os
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
run = Path(tempfile.mkdtemp(prefix="foundation-tests-", dir=root / "output"))
blocked = []
def guard(event, args):
    if event == "sqlite3.connect":
        blocked.append(str(args[0]))
        raise PermissionError("순수 회귀검사는 DB에 연결할 수 없습니다")
sys.addaudithook(guard)
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
import pytest
files = ["foundation_alignment", "logistics_batch", "integration_plan", "raw_rehearsal", "raw_quality",
         "price_basis", "price_candidate", "price_impact", "financial_candidate"]
code = pytest.main(["--noconftest", "-p", "no:cacheprovider", "-o", "addopts=", "-q",
    "--basetemp", str(run / "pytest"), "--junitxml", str(run / "tests.xml"),
    *[str(root / f"tests/test_kit_{name}.py") for name in files]])
report = {"exit_code": int(code), "blocked_sqlite": blocked,
          "repository_conftest_loaded": any(k.endswith("conftest") for k in sys.modules), "output": str(run)}
(run / "test-isolation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report), flush=True)
raise SystemExit(int(code) or (1 if blocked or report["repository_conftest_loaded"] else 0))
