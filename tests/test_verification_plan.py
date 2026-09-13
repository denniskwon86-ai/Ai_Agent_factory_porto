"""계획 라이브러리 자체 시험. 제품 import/DB/하위 프로세스 없이 tmp repo만 만든다.

실행은 main runner 전용이다. 계획 targets는 실행하지 않으며 작성 중 pytest도 금지한다.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts import verification_plan as vp


# 기존 --b0 --b1 --b2 --b3 실행 목록의 독립 스냅샷. 구현 상수를 복사해 기대값으로 쓰지 않는다.
LEGACY_NAMES = (
    "data_usage_holds", "data_readiness", "dataset_snapshot", "object_scope_index", "kit_app_builder", "calc_canary",
    "b1_process_configuration", "b1_process_adversarial", "ecm_e1", "ecm_e2_profile", "admin_capability",
    "project_data_context", "b0_data_boundary", "actual_certification", "b0_certification_atomicity",
    "b0_snapshot_transaction", "b0_certification_subject", "b0_certification_races", "b0_certification_integrity",
    "b0_certification_review_regressions", "b0_certification_api_contract",
    "b2_pack_artifacts", "b2_installation", "b2_installation_api",
    "host_runtime_wire", "host_runtime_sdk", "contract_decision_api", "capability_decision_normalization",
    "tech_lead_contract_draft",
)
ROUTE_CASES = (
    "test_every_table_entry_matches_a_real_route", "test_every_exempt_entry_matches_a_real_route",
    "test_every_write_route_is_decided", "test_exempt_entries_carry_a_reason", "test_member_may_run_but_not_release",
)
B3_FILES = ("test_b3_runtime_contract_v2.py", "test_b3_hotl_context.py", "test_b3_decision_round.py",
            "test_b3_new_consumer.py")
B4_FILES = ("test_b4_installation_queries.py", "test_b4_new_consumer.py")


def put(root, relative, source="# 임시 정적 시험 원본\n"):
    path = root / relative
    assert path.absolute().is_relative_to(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path):
    root = (tmp_path / "repo").resolve()
    root.mkdir()
    for name in LEGACY_NAMES:
        put(root, f"tests/test_{name}.py")
    put(root, "tests/test_route_authority_table.py")
    for name in (*B3_FILES, *B4_FILES):
        put(root, "tests/" + name)
    put(root, "tests/test_verification_plan.py")
    put(root, "tests/test_verification_extra.py")
    for relative in ("core/studio_hotl_context.py", "core/enterprise_context/process_installation.py",
                     "core/contract_decision.py", "core/kit_app_contract.py"):
        put(root, relative)
    return root


def assert_full(result, repo, reason):
    assert result["coverage"] == "full"
    assert result["targets"] == vp.full_targets(repo)
    assert any(reason in r for r in result["reasons"]), result["reasons"]


def test_full_matches_existing_combined_runner_plus_dynamic_selftests(repo):
    # 기존 기준선은 유지하고 명시 target으로 실행하는 B4 등록 파일을 추가한다.
    expected = {f"tests/test_{name}.py" for name in LEGACY_NAMES}
    expected.update("tests/" + name for name in B3_FILES)
    expected.update("tests/" + name for name in B4_FILES)
    expected.update("tests/test_route_authority_table.py::" + name for name in ROUTE_CASES)
    expected.update({"tests/test_verification_plan.py", "tests/test_verification_extra.py"})
    result = vp.full_targets(repo)
    assert set(result) == expected and len(result) == len(expected)
    assert "tests/test_route_authority_table.py" not in result
    assert vp.normalize_targets(repo, result) == result
    assert vp.full_targets(repo) == result


def test_new_b3_and_verification_files_are_included_without_changing_mapping(repo):
    put(repo, "tests/test_b3_future_boundary.py")
    put(repo, "tests/test_verification_future.py")
    result = vp.full_targets(repo)
    assert "tests/test_b3_future_boundary.py" in result
    assert "tests/test_verification_future.py" in result
    assert "tests/test_verification_future.py" in vp.plan(repo, "quick")["targets"]


def test_new_b4_files_join_full_registry_without_changing_mapping(repo):
    before = vp.full_targets(repo)
    future = "tests/test_b4_future_installation_flow.py"
    put(repo, future, "raise AssertionError('B4 시험 import/수집 금지')\n")
    result = vp.plan(repo, "full")
    assert "tests/test_b4_installation_queries.py" in before
    assert future not in before
    assert set(result["targets"]) == set(before) | {future}
    assert result["targets"] == vp.full_targets(repo)
    assert len(result["targets"]) == len(set(result["targets"]))


@pytest.mark.parametrize("relative", [
    "core/enterprise_context/process_configuration.py",
    "core/enterprise_context/process_installation.py",
    "core/enterprise_context/process_references.py",
    "core/enterprise_context/process_context.py",
    "core/data_preparation/process_pack_artifacts.py",
    "core/data_preparation/process_kit_instances.py",
    "api/routes/process_configuration_control.py",
    "api/routes/process_installation_control.py",
])
@pytest.mark.parametrize("tier", ["feature", "quick"])
def test_process_contract_changes_include_every_registered_b4_consumer(repo, relative, tier):
    put(repo, relative)
    future = "tests/test_b4_future_process_consumer.py"
    put(repo, future)
    result = vp.plan(repo, tier, [relative])
    expected_b4 = {"tests/" + name for name in B4_FILES} | {future}
    assert result["coverage"] == "affected"
    assert expected_b4 <= set(result["targets"])
    assert "tests/test_b1_process_configuration.py" in result["targets"]
    assert "tests/test_b2_installation.py" in result["targets"]
    assert "tests/test_b2_installation_api.py" in result["targets"]
    assert "tests/test_b3_new_consumer.py" in result["targets"]
    assert any("CONTRACT_MAPPING" in reason and "B1/B2/B3/B4" in reason for reason in result["reasons"])
    assert vp.normalize_targets(repo, result["targets"]) == result["targets"]


@pytest.mark.parametrize("case,reason", [
    ("missing", "MISSING_OR_UNSAFE_CHANGE"), ("unknown", "UNKNOWN_CHANGE"),
    ("dynamic", "DYNAMIC_CHANGE"), ("common", "COMMON_CHANGE"),
    ("no_changes", "NO_CHANGED_PATHS"),
])
def test_b4_registry_remains_in_full_fallbacks(repo, case, reason):
    relative = "core/enterprise_context/process_installation.py"
    changed = [relative]
    if case == "missing":
        changed = ["core/missing_b4_source.py"]
    elif case == "unknown":
        relative = "core/new_b4_source.py"
        put(repo, relative)
        changed.append(relative)
    elif case == "dynamic":
        put(repo, relative, "import importlib\nimportlib.import_module(module_name)\n")
    elif case == "common":
        put(repo, "api/deps.py")
        changed.append("api/deps.py")
    else:
        changed = []
    result = vp.plan(repo, "feature", changed)
    assert_full(result, repo, reason)
    assert {"tests/" + name for name in B4_FILES} <= set(result["targets"])


def test_quick_without_changes_keeps_existing_selection_when_b4_is_registered(repo):
    expected = {
        "tests/test_b3_runtime_contract_v2.py::test_v2_schema_is_separate_and_preserves_server_context",
        "tests/test_b3_runtime_contract_v2.py::test_v2_missing_or_malformed_context_cannot_compile",
        "tests/test_b3_hotl_context.py",
        "tests/test_b3_decision_round.py::test_pending_uses_persisted_identity_without_get_uuid_or_meta_write",
        "tests/test_b3_decision_round.py::test_same_content_new_save_has_new_uuid_and_stale_expected_409",
        "tests/test_verification_plan.py", "tests/test_verification_extra.py",
    }
    result = vp.plan(repo, "quick")
    put(repo, "tests/test_b4_another_future_flow.py")
    assert vp.plan(repo, "quick") == result
    assert result["coverage"] == "quick"
    assert set(result["targets"]) == expected


@pytest.mark.parametrize("tier", ["quick", "feature", "full"])
def test_coverage_notice_identifies_b4_registered_scope_not_product_completion(repo, tier):
    result = vp.plan(repo, tier)
    assert any("B0~B3+B4" in reason and "등록 회귀 중 선택 범위" in reason for reason in result["reasons"])
    assert any("제품 진척이 아닙니다" in reason and "아직 작성되지 않은 시험은 포함하지 않습니다" in reason
               for reason in result["reasons"])


def test_deleted_b4_consumer_forces_full_instead_of_narrow_feature(repo):
    path = put(repo, "tests/test_b4_removed_consumer.py")
    path.unlink()
    result = vp.plan(repo, "feature", ["tests/test_b4_removed_consumer.py"])
    assert_full(result, repo, "MISSING_OR_UNSAFE_CHANGE")
    assert {"tests/" + name for name in B4_FILES} <= set(result["targets"])


def test_default_plan_is_full_and_reports_actual_targets_not_only_counts(repo):
    result = vp.plan(repo)
    assert_full(result, repo, "EXPLICIT_FULL")
    assert set(result) == {"targets", "coverage", "reasons"}
    assert result["targets"] and all(isinstance(t, str) and t.startswith("tests/") for t in result["targets"])
    assert result["reasons"]


def test_quick_is_only_partial_plan_never_a_completed_pass(repo):
    result = vp.plan(repo, "quick")
    assert result["coverage"] == "quick"
    assert result["targets"] != vp.full_targets(repo)
    assert "tests/test_b3_hotl_context.py" in result["targets"]
    assert any("test_b3_runtime_contract_v2.py::" in t for t in result["targets"])
    assert any("test_b3_decision_round.py::" in t for t in result["targets"])
    assert "tests/test_verification_plan.py" in result["targets"]
    assert not ({"status", "passed", "completed", "exit_code", "progress"} & result.keys())
    assert any("전체 회귀를 대체하지 않습니다" in r for r in result["reasons"])
    assert any("PASS·완료 판정 없음" in r for r in result["reasons"])


def test_feature_without_changes_promotes_instead_of_returning_empty_success(repo):
    assert_full(vp.plan(repo, "feature"), repo, "NO_CHANGED_PATHS")


@pytest.mark.parametrize("relative", [
    "core/org_directory.py", "core/admin_capability.py", "core/route_authority.py",
    "core/auth/session.py", "core/data_preparation/store.py", "core/enterprise_context/repository.py",
    "core/enterprise_context/process_schema.py", "api/deps.py", "state_models.py",
    "tests/conftest.py", "tests/org_seed.py", "tests/usage_hold_test_plugin.py",
    "scripts/verify_data_usage_holds.py", "scripts/verification_plan.py", "tests/test_verification_plan.py",
])
def test_common_changes_promote_to_full_even_when_quick_requested(repo, relative):
    put(repo, relative)
    assert_full(vp.plan(repo, "quick", [relative]), repo, "COMMON_CHANGE")


@pytest.mark.parametrize("relative", ["core/unmapped_new_module.py", "README.md", "frontend/new.tsx",
                                        "process_packs/new.json"])
def test_unknown_changes_are_full_not_silently_ignored(repo, relative):
    put(repo, relative)
    assert_full(vp.plan(repo, "feature", [relative]), repo, "UNKNOWN_CHANGE")


def test_deleted_known_source_and_missing_path_promote_to_full(repo):
    (repo / "core/studio_hotl_context.py").unlink()
    for changed in ("core/studio_hotl_context.py", "core/missing.py"):
        assert_full(vp.plan(repo, "feature", [changed]), repo, "MISSING_OR_UNSAFE_CHANGE")


def test_deleted_dynamic_test_is_reported_not_lost_by_glob(repo):
    path = put(repo, "tests/test_b3_removed.py")
    path.unlink()
    assert_full(vp.plan(repo, "feature", ["tests/test_b3_removed.py"]), repo, "MISSING_OR_UNSAFE_CHANGE")


def test_multiple_known_changes_union_contracts_and_keep_new_b3_consumers(repo):
    first = vp.plan(repo, "feature", ["core/studio_hotl_context.py"])
    second = vp.plan(repo, "feature", ["core/enterprise_context/process_installation.py"])
    combined = vp.plan(repo, "feature", ["core/studio_hotl_context.py", "core/enterprise_context/process_installation.py"])
    assert first["coverage"] == second["coverage"] == combined["coverage"] == "affected"
    assert set(combined["targets"]) == set(first["targets"]) | set(second["targets"])
    assert "tests/test_b3_new_consumer.py" in first["targets"]
    assert "tests/test_b2_installation.py" in second["targets"]
    assert any("studio_hotl_context.py" in r for r in combined["reasons"])
    assert any("process_installation.py" in r for r in combined["reasons"])
    assert vp.normalize_targets(repo, combined["targets"]) == combined["targets"]


def test_one_unknown_change_promotes_the_entire_union(repo):
    put(repo, "core/unknown.py")
    result = vp.plan(repo, "feature", ["core/studio_hotl_context.py", "core/unknown.py"])
    assert_full(result, repo, "UNKNOWN_CHANGE")
    assert any("CONTRACT_MAPPING" in r for r in result["reasons"])


def test_quick_with_known_changes_is_affected_and_coalesces_overlapping_targets(repo):
    result = vp.plan(repo, "quick", ["core/studio_hotl_context.py"])
    assert result["coverage"] == "affected"
    assert any("QUICK_EXPANDED" in r for r in result["reasons"])
    assert vp.normalize_targets(repo, result["targets"]) == result["targets"]
    assert "tests/test_b3_runtime_contract_v2.py" in result["targets"]
    assert not any(t.startswith("tests/test_b3_runtime_contract_v2.py::") for t in result["targets"])


def test_repeated_changed_paths_do_not_duplicate_tests_or_reasons(repo):
    once = vp.plan(repo, "feature", ["core/studio_hotl_context.py"])
    repeated = vp.plan(repo, "feature", ["core/studio_hotl_context.py", "core\\studio_hotl_context.py"])
    assert repeated == once


@pytest.mark.parametrize("source", [
    "__import__(module_name)\n", "import importlib\nimportlib.import_module(module_name)\n",
    "from importlib import import_module as load\nload(module_name)\n",
    "loader = __import__\nloader(module_name)\n",
    "request.getfixturevalue(fixture_name)\n", "import sys\nmodule = sys.modules[name]\n",
    "from core.something import *\n", "exec(payload)\n", "pytest_plugins = plugins\n",
])
def test_dynamic_or_wildcard_changed_module_promotes_to_full(repo, source):
    put(repo, "core/studio_hotl_context.py", source)
    assert_full(vp.plan(repo, "feature", ["core/studio_hotl_context.py"]), repo, "DYNAMIC_CHANGE")


def test_unparseable_changed_module_promotes_to_full(repo):
    put(repo, "core/studio_hotl_context.py", "def broken(:\n")
    assert_full(vp.plan(repo, "feature", ["core/studio_hotl_context.py"]), repo, "STATIC_ANALYSIS_UNAVAILABLE")


@pytest.mark.parametrize("statement", [
    "from tests.test_b3_hotl_context import shared_fixture\n",
    "import tests.test_b3_hotl_context as helper\n",
    "from tests import test_b3_hotl_context as helper\n",
    "from .test_b3_hotl_context import shared_fixture\n",
    "from . import test_b3_hotl_context\n",
])
def test_fixture_or_helper_import_consumer_forces_full_even_outside_baseline(repo, statement):
    put(repo, "tests/test_outside_baseline.py", statement)
    assert_full(vp.plan(repo, "feature", ["tests/test_b3_hotl_context.py"]), repo, "SHARED_TEST_IMPORT")


def test_indirect_fixture_helper_import_is_not_missed(repo):
    put(repo, "tests/shared_helper.py", "from tests.test_b3_hotl_context import shared_fixture\n")
    put(repo, "tests/test_outside_baseline.py", "from tests.shared_helper import shared_fixture\n")
    assert_full(vp.plan(repo, "feature", ["tests/test_b3_hotl_context.py"]), repo, "SHARED_TEST_IMPORT")


@pytest.mark.parametrize("source,reason", [
    ("import importlib\nimportlib.import_module(name)\n", "DYNAMIC_TEST_DEPENDENCY"),
    ("def invalid(:\n", "STATIC_ANALYSIS_UNAVAILABLE"),
])
def test_unknown_test_dependency_analysis_is_full(repo, source, reason):
    put(repo, "tests/test_unresolved_consumer.py", source)
    assert_full(vp.plan(repo, "feature", ["tests/test_b3_hotl_context.py"]), repo, reason)


def test_statically_isolated_test_selects_itself_and_planner_selftests(repo):
    result = vp.plan(repo, "feature", ["tests/test_b3_new_consumer.py"])
    assert result["coverage"] == "affected"
    assert set(result["targets"]) == {"tests/test_b3_new_consumer.py", "tests/test_verification_plan.py",
                                       "tests/test_verification_extra.py"}


@pytest.mark.parametrize("target", [
    "tests/test_b3_hotl_context.py", "tests\\test_b3_hotl_context.py",
    "tests/test_b3_hotl_context.py::test_round", "tests/test_b3_hotl_context.py::TestRound::test_round[a-1]",
])
def test_normalize_existing_relative_file_and_selector(repo, target):
    assert vp.normalize_target(repo, target) == target.replace("\\", "/")


@pytest.mark.parametrize("target", [
    "", " tests/test_b3_hotl_context.py", "tests/test_b3_hotl_context.py ",
    "/tests/test_b3_hotl_context.py", "C:/repo/tests/test_b3_hotl_context.py", "C:tests/test_b3_hotl_context.py",
    "\\\\server\\share\\test_case.py", "tests/../test_case.py", "tests/./test_b3_hotl_context.py",
    "tests//test_b3_hotl_context.py", "tests/test_missing.py", "core/test_case.py", "tests/conftest.py",
    "-k", "--pyargs", "tests/test_b3_hotl_context.py --help", "tests/test_b3_hotl_context.py::",
    "tests/test_b3_hotl_context.py::-k", "tests/test_b3_hotl_context.py::test_round;whoami",
    "tests/test_b3_hotl_context.py\n--help",
    "tests/test_b3_hotl_context.py::[hotl/resume-1]", "tests/test_b3_hotl_context.py::TestA::[param]",
    "tests/test_b3_hotl_context.py::test_round[unterminated",
    "tests/test_b3_hotl_context.py::test_round[x]::--override-ini", "tests/test_b3_hotl_context.py:stream",
])
def test_normalize_rejects_escape_missing_file_and_option_injection(repo, target):
    with pytest.raises(ValueError):
        vp.normalize_target(repo, target)


def test_existing_absolute_target_is_still_forbidden(repo):
    with pytest.raises(ValueError):
        vp.normalize_target(repo, str(repo / "tests/test_b3_hotl_context.py"))


@pytest.mark.parametrize("parameter", ["hotl/resume-1", "hotl/resume-2", "sprint/resume-quota-1"])
def test_actual_hotl_api_parameter_nodeid_is_preserved_without_collection(repo, parameter):
    # 원본 test_b3_hotl_api.py:107의 suffix/failed_read 조합. 원본 import/수집은 하지 않는다.
    relative = "tests/test_b3_hotl_api.py"
    put(repo, relative)
    target = relative + "::test_actual_preflight_and_contract_query_errors_keep_503[" + parameter + "]"
    assert vp.normalize_target(repo, target) == target


@pytest.mark.parametrize("parameter", [
    "hotl/resume-1", "공백 포함 ID", "../../outside", "--basetemp ../../escape",
    "C:\\outside path", "x::y[nested]", "",
])
def test_parameter_is_opaque_and_cannot_change_validated_file_path(repo, monkeypatch, parameter):
    original, paths = vp._file, []
    def capture(root, relative):
        paths.append(relative)
        return original(root, relative)
    monkeypatch.setattr(vp, "_file", capture)
    target = "tests\\test_b3_hotl_context.py::test_round[" + parameter + "]"
    expected = "tests/test_b3_hotl_context.py::test_round[" + parameter + "]"
    assert vp.normalize_target(repo, target) == expected
    assert paths == ["tests/test_b3_hotl_context.py"]


@pytest.mark.parametrize("control", ["\x00", "\n", "\r", "\t", "\x7f", "\x85", "\u2028"])
def test_parameter_control_characters_are_rejected(repo, control):
    with pytest.raises(ValueError):
        vp.normalize_target(repo, "tests/test_b3_hotl_context.py::test_round[hotl/" + control + "resume]")


def test_parameter_delimiters_do_not_confuse_duplicate_or_parent_overlap(repo):
    parent = "tests/test_b3_hotl_context.py::test_round"
    first, second = parent + "[hotl/resume::first ID]", parent + "[hotl/resume::second ID]"
    assert vp.normalize_targets(repo, [first, second]) == [first, second]
    for targets in ([first, first], [parent, first], [first, parent]):
        with pytest.raises(ValueError):
            vp.normalize_targets(repo, targets)


@pytest.mark.parametrize("suffixes", [
    ("", ""), ("", "::test_a"), ("::test_a", ""),
    ("::TestA", "::TestA::test_a"), ("::test_a", "::test_a[x]"),
    ("::test_a[x]", "::test_a"),
])
def test_duplicate_or_overlapping_explicit_targets_are_rejected(repo, suffixes):
    targets = ["tests/test_b3_hotl_context.py" + suffix for suffix in suffixes]
    with pytest.raises(ValueError, match="중복|겹치는"):
        vp.normalize_targets(repo, targets)


def test_distinct_selectors_are_not_false_overlap_and_backslash_duplicates_are(repo):
    targets = ["tests/test_b3_hotl_context.py::test_a[x]", "tests/test_b3_hotl_context.py::test_a[y]",
               "tests/test_b3_hotl_context.py::test_b"]
    assert vp.normalize_targets(repo, targets) == targets
    with pytest.raises(ValueError):
        vp.normalize_targets(repo, ["tests/test_b3_hotl_context.py", "tests\\test_b3_hotl_context.py"])


def test_symlink_target_or_tests_directory_is_rejected(repo, tmp_path):
    outside = put(tmp_path, "outside/test_link.py")
    link = repo / "tests/test_link.py"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"이 환경은 임시 symlink를 지원하지 않습니다: {exc}")
    with pytest.raises(ValueError, match="링크"):
        vp.normalize_target(repo, "tests/test_link.py")
    with pytest.raises(ValueError, match="링크"):
        vp.normalize_target(repo, "tests/test_link.py::test_a")


def test_missing_baseline_target_fails_closed_instead_of_shrinking_full(repo):
    (repo / "tests/test_data_usage_holds.py").unlink()
    with pytest.raises(ValueError):
        vp.full_targets(repo)


def test_root_is_explicit_and_independent_of_cwd(repo, tmp_path, monkeypatch):
    before = vp.full_targets(repo)
    monkeypatch.chdir(tmp_path)
    assert vp.full_targets(repo) == before
    with pytest.raises(ValueError):
        vp.full_targets("repo")


def test_invalid_tier_and_scalar_lists_are_not_silently_accepted(repo):
    with pytest.raises(ValueError):
        vp.plan(repo, "fast")
    with pytest.raises(ValueError):
        vp.plan(repo, "feature", "core/studio_hotl_context.py")
    with pytest.raises(ValueError):
        vp.normalize_targets(repo, "tests/test_b3_hotl_context.py")
    with pytest.raises(ValueError):
        vp.normalize_targets(repo, [])


def test_unsafe_changed_path_promotes_without_reading_outside_root(repo):
    assert_full(vp.plan(repo, "feature", ["../outside.py"]), repo, "MISSING_OR_UNSAFE_CHANGE")


def test_plan_does_not_execute_source_and_never_writes_files(repo):
    put(repo, "core/studio_hotl_context.py", "raise AssertionError('앱 import 금지')\n")
    before = {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    assert vp.plan(repo, "feature", ["core/studio_hotl_context.py"])["coverage"] == "affected"
    after = {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    assert after == before


def test_library_imports_only_explicit_stdlib_and_has_no_execution_or_write_calls():
    tree = ast.parse(Path(vp.__file__).read_text(encoding="utf-8"))
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    modules.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert modules <= {"__future__", "ast", "pathlib", "re"}
    forbidden = {"write_text", "write_bytes", "mkdir", "unlink", "rmdir", "Popen", "run", "system",
                 "connect", "import_module", "exec", "eval"}
    calls = {node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
             for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert not (calls & forbidden)
