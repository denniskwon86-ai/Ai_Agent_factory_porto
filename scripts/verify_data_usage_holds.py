"""소비 경계 회귀: 전역 conftest 없이 새 출력 폴더의 SQLite만 허용한다."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import tempfile
import time

STARTED = time.perf_counter()
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
# pytest.ini addopts 무효화만으로 환경변수의 선택·플러그인 주입은 제거되지 않는다.
# 원값은 출력하지 않는다. 직접 실행과 부모 실행 모두 같은 고정 범위를 보장한다.
for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
    os.environ.pop(key, None)

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--focused", action="store_true", help="새 보류 회귀만 실행")
parser.add_argument("--b0", action="store_true", help="B0 읽기·프로젝트 HTTP 및 기존 인증 회귀 포함")
parser.add_argument("--b1", action="store_true", help="B1 업무 구성·기존 ECM/권한 회귀")
parser.add_argument("--b2", action="store_true", help="B2 불변 팩·설치·이관 및 원본 파일 쓰기 차단")
parser.add_argument("--b3", action="store_true", help="B3 초안·승격·양쪽 계약 및 Host 회귀, 프로젝트/라이브러리 쓰기 격리")
parser.add_argument("--select", default="", help="수정 확인용 pytest -k 선택식; 최종 전체 회귀와 구분")
parser.add_argument("--target", action="append", default=[], help="기존 tests/test_*.py[::nodeid] 반복 지정; B0~B3 보호는 유지")
parser.add_argument("--strict-writes", action="store_true", help="파일 쓰기도 현재 RUN 내부로만 제한")
parser.add_argument("--collect-only", action="store_true", help="정확한 예상 nodeid 수집만 수행")
parser.add_argument("--report-file", help="output 내부의 존재하지 않는 JSON 보고서")
parser.add_argument("--invocation-id", default="", help="부모 실행의 일회성 식별자")
args = parser.parse_args()
sys.path.insert(0, str(ROOT))
from scripts.verification_plan import normalize_targets
from scripts.verification_isolation import VerificationIsolation, VerificationTiming

if args.target:
    try:
        args.target = normalize_targets(ROOT, args.target)
    except ValueError as exc:
        parser.error(str(exc))
    args.b0 = args.b1 = args.b2 = args.b3 = True
report_file = None
if args.report_file:
    candidate = Path(args.report_file)
    report_file = candidate.resolve()
    if (not candidate.is_absolute() or not report_file.is_relative_to((ROOT / "output").resolve())
            or candidate.suffix != ".json" or not candidate.parent.is_dir() or candidate.exists()
            or any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                   for p in (candidate, *candidate.parents))):
        parser.error("보고서는 output 안의 새 절대 JSON 파일이어야 하며 링크/덮어쓰기는 금지합니다")
sources = [ROOT / path for path in (
    "core/data_preparation/usage_policy.py", "core/data_preparation/models.py",
    "core/data_preparation/store.py", "core/data_preparation/snapshot_service.py",
    "core/data_preparation/readiness.py", "core/data_preparation/scope_index.py",
    "core/calc_dataset_loader.py", "core/kit_app_builder.py",
    "api/routes/data_preparation_control.py", "tests/test_data_usage_holds.py",
    "tests/test_data_readiness.py", "tests/test_dataset_snapshot.py",
    "tests/test_object_scope_index.py", "tests/test_kit_app_builder.py",
    "tests/test_calc_canary.py", "tests/usage_hold_test_plugin.py",
    "core/project_data_context.py", "api/routes/factory_control.py",
    "tests/test_project_data_context.py", "tests/test_b0_data_boundary.py",
    "tests/test_actual_certification.py", "core/actual_certification_policy.py",
    "tests/test_b0_certification_atomicity.py", "tests/test_b0_snapshot_transaction.py",
    "core/data_preparation/certification_authority.py", "core/data_preparation/certification_subject.py",
    "tests/test_b0_certification_subject.py", "tests/test_b0_certification_races.py",
    "tests/test_b0_certification_integrity.py", "tests/test_b0_certification_review_regressions.py",
    "tests/test_b0_certification_api_contract.py", "core/route_authority.py",
    "core/decision_ledger.py", "core/org_directory.py")]
if args.b1:
    sources += [ROOT / path for path in (
        "core/enterprise_context/models.py", "core/enterprise_context/repository.py",
        "core/enterprise_context/process_schema.py", "core/enterprise_context/process_configuration.py",
        "core/enterprise_context/profile_resolver.py", "core/enterprise_context/clone_service.py",
        "core/admin_capability.py", "api/routes/enterprise_context_control.py",
        "api/routes/process_configuration_control.py", "tests/test_b1_process_configuration.py",
        "tests/test_b1_process_adversarial.py")]
if args.b2:
    sources += [ROOT / path for path in (
        "core/enterprise_context/process_schema.py", "core/enterprise_context/process_configuration.py",
        "core/enterprise_context/process_references.py", "core/enterprise_context/process_installation.py",
        "core/data_preparation/process_pack_artifacts.py", "core/data_preparation/process_kit_instances.py",
        "api/routes/process_installation_control.py", "tests/test_b2_pack_artifacts.py",
        "tests/test_b2_installation.py", "tests/test_b2_installation_api.py")]
    sources += list((ROOT / "process_packs").rglob("*.json"))
if args.b3:
    sources += [path for folder in ("core", "api", "nodes") for path in (ROOT / folder).rglob("*.py")]
    sources += list((ROOT / "tests").glob("test_b3_*.py"))
    sources += [ROOT / f"tests/test_{name}.py" for name in ("host_runtime_wire", "host_runtime_sdk",
        "contract_decision_api", "capability_decision_normalization", "tech_lead_contract_draft")]
    sources += [ROOT / "state_models.py", ROOT / "scripts/verify_data_usage_holds.py"]
# fixture/helper/선택기/실행기 판본과 새 파일·삭제도 확인한다.
def source_snapshot():
    paths = set(sources)
    paths.update(p for folder in ("core", "api", "nodes", "tests", "scripts")
                 for p in (ROOT / folder).rglob("*.py"))
    paths.update(ROOT / name for name in ("main.py", "state_models.py", "config.py", "pytest.ini")
                 if (ROOT / name).is_file())
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            if p.is_file() else None for p in sorted(paths)}


protected_roots = [ROOT / "starter_kits", ROOT / "docs/data-kits", ROOT / "process_packs"]
protected_files = [p for root in protected_roots for p in root.rglob("*") if p.is_file()] if args.b2 or args.b3 else []
write_guard_roots = protected_roots + ([ROOT / "projects", ROOT / "data", ROOT / "library", ROOT / "workspace"] if args.b3 else [])
asset_before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected_files}
before = source_snapshot()
RUN = Path(tempfile.mkdtemp(prefix="usage-holds-", dir=ROOT / "output")).resolve()
guard = VerificationIsolation(RUN, strict=args.strict_writes,
                              protected_roots=write_guard_roots if args.b2 or args.b3 else ())
sys.addaudithook(guard)
temp_root = RUN / "temp"
temp_root.mkdir()
tempfile.tempdir = str(temp_root)
for key in ("TEMP", "TMP", "TMPDIR"):
    os.environ[key] = str(temp_root)
import core.paths
core.paths.DATA_DIR = str(RUN / "data")
preload_mode = "not-b3"
if args.b3:
    core.paths.PROJECTS_DIR = str(RUN / "projects")
    import core.library_paths
    core.library_paths._LIBRARY_DIR = str(RUN / "library")
    # 전역 앱의 무관한 skill router import가 만드는 상대경로 디렉터리도 격리한다.
    # 실제 모듈을 그대로 초기화하며 main/라우트 대역이나 보호 guard 면제는 없다.
    light_files = {"tests/test_b3_hotl_context.py", "tests/test_b3_runtime_contract_v2.py",
                   "tests/test_b3_decision_round.py", "tests/test_b3_kit_contract_v2.py",
                   "tests/test_verification_plan.py", "tests/test_verification_dispatch.py",
                   "tests/test_verification_guard.py"}
    light = bool(args.target) and all(t.split("::", 1)[0] in light_files for t in args.target)
    preload_mode = "reviewed-light-targets" if light else "real-skill-before-pytest"
    if not light:
        previous_cwd = Path.cwd()
        try:
            os.chdir(RUN)
            import core.skill_evolution
        finally:
            os.chdir(previous_cwd)
        # 좁은 API nodeid에서는 다른 시험의 수집 import가 조직 singleton을 먼저 만들지 않는다.
        # 실제 빈 조직 저장소를 worker RUN에서 초기화한 뒤, enforced_org가 시험별 DB에 재결속한다.
        # 좁은 fixture의 SQLite guard 설치 후 최초 전역 생성이 끼어드는 수집 순서 의존을 제거한다.
        import core.org_directory
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
import pytest

names = ["data_usage_holds", "data_readiness", "dataset_snapshot", "object_scope_index", "kit_app_builder", "calc_canary"]
if args.focused:
    names = ["data_usage_holds"]
if args.b1:
    names = (names if args.b0 else []) + ["b1_process_configuration", "b1_process_adversarial", "ecm_e1", "ecm_e2_profile", "admin_capability"]
if args.b0:
    names += ["project_data_context", "b0_data_boundary", "actual_certification",
              "b0_certification_atomicity", "b0_snapshot_transaction", "b0_certification_subject", "b0_certification_races", "b0_certification_integrity", "b0_certification_review_regressions", "b0_certification_api_contract"]
if args.b2:
    names = (names if args.b0 or args.b1 else []) + ["b2_pack_artifacts", "b2_installation", "b2_installation_api"]
if args.b3:
    names = (names if args.b0 or args.b1 or args.b2 else []) + [p.stem.removeprefix("test_") for p in sorted((ROOT / "tests").glob("test_b3_*.py"))]
    names += ["host_runtime_wire", "host_runtime_sdk", "contract_decision_api",
              "capability_decision_normalization", "tech_lead_contract_draft"]
targets = [str(ROOT / f"tests/test_{name}.py") for name in names]
if args.b1:
    targets += [str(ROOT / "tests/test_route_authority_table.py") + "::" + name for name in (
        "test_every_table_entry_matches_a_real_route", "test_every_exempt_entry_matches_a_real_route",
        "test_every_write_route_is_decided", "test_exempt_entries_carry_a_reason", "test_member_may_run_but_not_release")]
if args.target:
    targets = [str(ROOT / t.split("::", 1)[0]) + ("::" + t.split("::", 1)[1] if "::" in t else "")
               for t in args.target]
elif args.b0 and args.b1 and args.b2 and args.b3:
    targets += [str(p) for p in sorted((ROOT / "tests").glob("test_verification*.py"))]
selected_targets = [Path(t.split("::", 1)[0]).relative_to(ROOT).as_posix()
                    + ("::" + t.split("::", 1)[1] if "::" in t else "") for t in targets]
timing = VerificationTiming()
startup_seconds = time.perf_counter() - STARTED
code = pytest.main(["--noconftest", "-p", "no:cacheprovider", "-p", "tests.usage_hold_test_plugin",
                   "-c", str(ROOT / "pytest.ini"), "--rootdir", str(ROOT),
                   "-o", "addopts=", "--log-file", str(RUN / "pytest.log"), "-q", "--tb=short", "--durations=10",
                   "--basetemp", str(RUN / "pytest"), "--junitxml", str(RUN / "tests.xml"),
                   *targets, *(["-k", args.select] if args.select else []),
                   *(["--collect-only"] if args.collect_only else [])], plugins=[timing])
timing.phase_seconds.update(startup=startup_seconds, pytest=time.perf_counter() - timing.started)
after = source_snapshot()
asset_after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for root in protected_roots for p in root.rglob("*") if p.is_file()} if args.b2 or args.b3 else {}
report = {"exit_code": int(code), "run_root": str(RUN), "selection": args.select, "sqlite_paths": sorted(guard.sqlite_paths),
          "invocation_id": args.invocation_id, "targets": selected_targets, "strict_writes": args.strict_writes,
          "collect_only": args.collect_only, "audit_hook_installed": True, "preload_mode": preload_mode,
          "pytest_environment_sanitized": True,
          "collected_nodeids": timing.collected_nodeids, "executed_nodeids": sorted(timing.executed_nodeids),
          "phase_outcomes": timing.phase_outcomes, "subtest_outcomes": timing.subtest_outcomes,
          "phase_seconds": timing.phase_seconds,
          "elapsed_seconds": time.perf_counter() - STARTED, "write_paths": sorted(guard.write_paths),
          "asset_hashes_before": asset_before, "asset_hashes_after": asset_after,
          "protected_assets_unchanged": asset_before == asset_after, "blocked_file_writes": guard.blocked_file_writes,
          "source_hashes_before": before, "source_hashes_after": after, "sources_unchanged": before == after,
          "blocked_sqlite_paths": guard.blocked_sqlite_paths,
          "repository_conftest_loaded": any(k.endswith("conftest") for k in sys.modules)}
invalid = (bool(guard.blocked_sqlite_paths) or bool(guard.blocked_file_writes)
           or asset_before != asset_after or report["repository_conftest_loaded"] or before != after
           or not timing.collected_nodeids or len(timing.collected_nodeids) != len(set(timing.collected_nodeids))
           or (not args.collect_only and set(timing.collected_nodeids) != timing.executed_nodeids)
           or any(r["outcome"] == "failed" for r in (*timing.phase_outcomes, *timing.subtest_outcomes)))
report["wrapper_exit_code"] = int(code) or int(invalid)
(RUN / "isolation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
if report_file:
    guard.final_report = report_file
    try:
        with report_file.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    finally:
        guard.final_report = None
summary = {key: value for key, value in report.items()
           if not key.startswith(("source_hashes_", "asset_hashes_"))
           and key not in {"sqlite_paths", "write_paths", "collected_nodeids", "executed_nodeids", "phase_outcomes", "subtest_outcomes"}}
print(json.dumps({**summary, "sqlite_paths": len(guard.sqlite_paths),
                  "collected": len(timing.collected_nodeids), "executed": len(timing.executed_nodeids)}, ensure_ascii=False), flush=True)
raise SystemExit(report["wrapper_exit_code"])
