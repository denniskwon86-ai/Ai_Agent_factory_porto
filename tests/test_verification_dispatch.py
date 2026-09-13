"""Pure dispatcher evidence tests: no subprocess, application import or DB.

Synthetic reports are unit test doubles, not proof of real isolation. The main
audit runner separately runs collection + actual parallel-worker smoke tests.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
import uuid

from scripts.run_verification import (
    EvidenceError, Invocation, _unique_object, _invalid_constant,
    aggregate_reports, build_command, canonical_targets, partition_targets,
    partition_with_baseline_hints, prepare_plan, sanitized_env, validate_partition, validate_report,
)


ROOT = Path(__file__).resolve().parents[1] / "synthetic-verification-root"
FILES = ["tests/test_alpha.py", "tests/test_beta.py"]
NODES = [FILES[0] + "::test_one", FILES[0] + "::test_two[x]", FILES[1] + "::test_three"]
HASH = "a" * 64


def invocation(number, targets, collect=False):
    return Invocation("collect" if collect else "worker-" + str(number), str(uuid.UUID(int=number)),
                      tuple(targets), collect, ROOT / "output" / "verification-synthetic" / (str(number) + ".json"))


def evidence(call, nodes):
    runtime = ROOT / "output" / ("usage-holds-" + call.invocation_id)
    return {
        "exit_code": 0, "wrapper_exit_code": 0, "invocation_id": call.invocation_id,
        "targets": list(call.targets), "strict_writes": True, "audit_hook_installed": True,
        "pytest_environment_sanitized": True,
        "collect_only": call.collect_only, "repository_conftest_loaded": False,
        "selection": "", "sources_unchanged": True, "protected_assets_unchanged": True,
        "source_hashes_before": {"core/example.py": HASH, "tests/test_alpha.py": HASH},
        "source_hashes_after": {"core/example.py": HASH, "tests/test_alpha.py": HASH},
        "asset_hashes_before": {"starter_kits/example.json": HASH},
        "asset_hashes_after": {"starter_kits/example.json": HASH},
        "run_root": str(runtime), "sqlite_paths": [str(runtime / "data" / "unit.sqlite3")],
        "write_paths": [str(runtime / "temp" / "artifact.json")],
        "blocked_sqlite_paths": [], "blocked_file_writes": [],
        "phase_seconds": {"startup": 0.1, "collection": 0.1, "pytest": 0.2}, "elapsed_seconds": 0.4,
        "collected_nodeids": list(nodes), "executed_nodeids": [] if call.collect_only else list(nodes),
        "subtest_outcomes": [],
        "phase_outcomes": [] if call.collect_only else [
            {"nodeid": node, "when": when, "outcome": "passed", "duration": 0.01}
            for node in nodes for when in ("setup", "call", "teardown")],
    }


def record(call, nodes):
    return {"invocation": call, "report": evidence(call, nodes), "returncode": 0}


def cohort():
    collection = record(invocation(1, FILES, True), NODES)
    workers = [record(invocation(2, [FILES[0]]), NODES[:2]), record(invocation(3, [FILES[1]]), NODES[2:])]
    return collection, workers


def aggregate(collection, workers):
    return aggregate_reports(collection, workers, root=ROOT, targets=FILES, partitions=[[FILES[0]], [FILES[1]]])


class PlanTests(unittest.TestCase):
    def test_child_environment_sanitization_is_a_pure_copy_without_pytest_injection(self):
        source = {"PYTEST_ADDOPTS": "--deselect=tests/test_synthetic.py::test_hidden",
                  "PYTEST_PLUGINS": "synthetic_plugin", "PATH": "synthetic-path",
                  "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "0"}
        before = dict(source)
        result = sanitized_env(source)
        self.assertEqual(source, before)
        self.assertIsNot(result, source)
        self.assertEqual(result, {"PATH": "synthetic-path", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                                  "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(sanitized_env(result), result)

    def test_child_environment_sanitization_handles_missing_keys_and_windows_aliases(self):
        self.assertEqual(sanitized_env({}), {"PYTHONDONTWRITEBYTECODE": "1"})
        source = {"pytest_addopts": "synthetic", "PyTest_Plugins": "synthetic",
                  "pythondontwritebytecode": "0", "Unrelated": "preserved"}
        self.assertEqual(sanitized_env(source), {"Unrelated": "preserved", "PYTHONDONTWRITEBYTECODE": "1"})

    def test_selected_scope_cannot_claim_full_even_if_planner_label_says_full(self):
        result = prepare_plan({"targets": FILES[:1], "coverage": "full", "reasons": []}, FILES, tier="quick")
        self.assertEqual(result["scope"], "SELECTED")
        self.assertIn("browser", result["separate_gates"])
        self.assertIn("full_execution_task_integration", result["separate_gates"])

    def test_full_tier_requires_exact_registry(self):
        with self.assertRaises(EvidenceError):
            prepare_plan({"targets": FILES[:1], "coverage": "full", "reasons": []}, FILES, tier="full")
        result = prepare_plan({"targets": FILES, "coverage": "full", "reasons": ["explicit"]}, FILES, tier="full")
        self.assertEqual(result["scope"], "FULL_REGISTERED")

    def test_feature_promotion_is_only_exact_registered_scope(self):
        result = prepare_plan({"targets": list(reversed(FILES)), "coverage": "affected", "reasons": []}, FILES, tier="feature")
        self.assertEqual(result["scope"], "FULL_REGISTERED")

    def test_invalid_plan_and_target_inputs_fail(self):
        bad = [[], ["--help"], ["../tests/test_a.py"], ["/tests/test_a.py"],
               ["tests/test_a.py::"], ["tests/test_a.py\n"], ["tests/../test_a.py"],
               ["C:/repo/tests/test_a.py"], [FILES[0], FILES[0]],
               [FILES[0], NODES[0]], [NODES[0], NODES[0] + "[x]"],
               [FILES[0], "tests/TEST_ALPHA.py::test_one"]]
        for values in bad:
            with self.subTest(values=values), self.assertRaises(EvidenceError):
                canonical_targets(values)
        for raw in ({}, {"targets": [], "coverage": "full", "reasons": []},
                    {"targets": FILES, "coverage": "full", "reasons": [float("nan")]}):
            with self.subTest(raw=raw), self.assertRaises(EvidenceError):
                prepare_plan(raw, FILES, tier="full")

    def test_baseline_is_deterministic_one_per_file_not_seconds(self):
        split = partition_targets(FILES, 2)
        self.assertEqual(split["partitions"], [[FILES[0]], [FILES[1]]])
        self.assertEqual(split["weights"], dict.fromkeys(FILES, 1.0))
        self.assertEqual(split["weight_source"], "baseline_equal_file")
        self.assertEqual(split["weight_unit"], "relative_cost_not_seconds")
        self.assertEqual(split, partition_targets(list(reversed(FILES)), 2))

    def test_same_file_selectors_are_never_split(self):
        targets = [NODES[0], NODES[1], FILES[1]]
        split = partition_targets(targets, 2)
        self.assertEqual(split["partitions"], [[NODES[0], NODES[1]], [FILES[1]]])
        self.assertEqual(len(partition_targets(NODES[:2], 2)["partitions"]), 1)
        with self.assertRaises(EvidenceError):
            validate_partition(NODES[:2], [[NODES[0]], [NODES[1]]])

    def test_fixed_weights_and_worker_limit(self):
        split = partition_targets(FILES, 2, {FILES[1]: 8})
        self.assertEqual(split["partitions"][0], [FILES[1]])
        self.assertEqual(split["weight_source"], "supplied_fixed")
        for jobs in (0, 3, True, "2"):
            with self.subTest(jobs=jobs), self.assertRaises(EvidenceError):
                partition_targets(FILES, jobs)
        for weights in ({FILES[0]: 0}, {FILES[0]: -1}, {FILES[0]: float("nan")},
                        {FILES[0]: float("inf")}, {FILES[0]: True}, {"unknown": 1}):
            with self.subTest(weights=weights), self.assertRaises(EvidenceError):
                partition_targets(FILES, 2, weights)

    def test_fixed_baseline_hints_filter_balance_and_preserve_unhinted_quick_plan(self):
        hints = {"tests/test_b3_kit_contract_v2.py": 751.102,
                 "tests/test_b3_release_readiness.py": 315.768,
                 "tests/test_b3_runtime_data.py": 287.756,
                 "tests/test_b3_kit_rejection.py": 267.612,
                 "tests/test_b3_kit_api.py": 156.785,
                 "tests/test_b3_process_context.py": 99.270}
        targets = [*hints, *FILES]
        split = partition_with_baseline_hints(targets, 2)
        self.assertEqual(split["weight_hints"], hints)
        self.assertEqual(split["weights"], {**hints, **dict.fromkeys(FILES, 1.0)})
        self.assertEqual(split["weight_source"], "baseline_fixed_serial_junit_hints")
        self.assertEqual(split["weight_provenance"], "output/usage-holds-6m4qchly")
        self.assertIs(split["weight_is_forecast"], False)
        self.assertEqual(split["weight_unit"], "relative_cost_not_seconds")
        validate_partition(targets, split["partitions"])
        equal = partition_targets(targets, 2)
        equal_costs = [sum(hints.get(path, 1) for path in group) for group in equal["partitions"]]
        self.assertLess(abs(split["worker_weights"][0] - split["worker_weights"][1]), abs(equal_costs[0] - equal_costs[1]))
        selected = ["tests/test_b3_kit_contract_v2.py::test_selected", FILES[0]]
        filtered = partition_with_baseline_hints(selected, 2)
        self.assertEqual(filtered["weight_hints"], {"tests/test_b3_kit_contract_v2.py": 751.102})
        self.assertEqual(set(filtered["weights"]), {"tests/test_b3_kit_contract_v2.py", FILES[0]})
        quick = ["tests/test_b3_hotl_context.py", "tests/test_b3_runtime_contract_v2.py::test_selected"]
        self.assertEqual(partition_with_baseline_hints(quick, 2), partition_targets(quick, 2))

    def test_partition_missing_extra_duplicate_empty_fail(self):
        for groups in ([], [[FILES[0]]], [[FILES[0]], [FILES[0]]], [FILES, []],
                       [[FILES[0]], [FILES[1]], ["tests/test_extra.py"]]):
            with self.subTest(groups=groups), self.assertRaises(EvidenceError):
                validate_partition(FILES, groups)

    def test_command_uses_fixed_python_entrypoint_and_exact_target_arguments(self):
        call = invocation(1, FILES, True)
        args = build_command(ROOT, call)
        self.assertEqual(args[0], sys.executable)
        self.assertEqual(args[1], "-B")
        self.assertEqual(Path(args[2]).name, "verify_data_usage_holds.py")
        self.assertEqual(args[3:7], ["--b0", "--b1", "--b2", "--b3"])
        self.assertEqual([args[i + 1] for i, value in enumerate(args) if value == "--target"], FILES)
        self.assertIn("--strict-writes", args)
        self.assertEqual(args[-1], "--collect-only")
        self.assertNotIn("--collect-only", build_command(ROOT, invocation(2, FILES)))
        for bad in (replace(call, report_file=ROOT / "output" / "old.json"),
                    replace(call, invocation_id="old"), replace(call, targets=("--help",))):
            with self.subTest(bad=bad), self.assertRaises(EvidenceError):
                build_command(ROOT, bad)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.call = invocation(2, [FILES[0]])
        self.report = evidence(self.call, NODES[:2])

    def validate(self, report=None, returncode=0):
        return validate_report(self.report if report is None else report, self.call, root=ROOT, returncode=returncode)

    def test_complete_evidence_and_setup_skip_are_allowed(self):
        self.validate()
        self.report["phase_outcomes"] = [row for row in self.report["phase_outcomes"]
                                           if not (row["nodeid"] == NODES[0] and row["when"] == "call")]
        self.report["phase_outcomes"][0]["outcome"] = "skipped"
        self.validate()

    def test_collect_only_allows_zero_execution_but_not_zero_collection(self):
        call = invocation(1, FILES, True)
        report = evidence(call, NODES)
        validate_report(report, call, root=ROOT, returncode=0)
        for key, value in (("collected_nodeids", []), ("executed_nodeids", NODES),
                           ("phase_outcomes", self.report["phase_outcomes"]),
                           ("subtest_outcomes", [{"nodeid": NODES[0], "when": "call", "outcome": "passed", "duration": 0.01}])):
            changed = {**report, key: value}
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                validate_report(changed, call, root=ROOT, returncode=0)

    def test_every_required_attestation_missing_or_false_fails(self):
        for key in self.report:
            candidate = deepcopy(self.report)
            del candidate[key]
            with self.subTest(missing=key), self.assertRaises(EvidenceError):
                self.validate(candidate)

    def test_exit_status_invocation_scope_and_attestation_tampering_fail(self):
        changes = {"exit_code": 1, "wrapper_exit_code": 1, "invocation_id": str(uuid.UUID(int=8)),
                   "targets": [FILES[1]], "strict_writes": 1, "audit_hook_installed": False,
                   "pytest_environment_sanitized": False,
                   "collect_only": True, "repository_conftest_loaded": True,
                   "sources_unchanged": False, "protected_assets_unchanged": False,
                   "selection": "hidden", "blocked_sqlite_paths": ["operating.sqlite3"],
                   "blocked_file_writes": [{"event": "subprocess.Popen"}],
                   "elapsed_seconds": float("nan"), "phase_seconds": {"pytest": -1}}
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                self.validate({**self.report, key: value})
        for status in (1, -15, None, True):
            with self.subTest(status=status), self.assertRaises(EvidenceError):
                self.validate(returncode=status)

    def test_each_test_phase_failure_error_or_missing_is_rejected(self):
        for when in ("setup", "call", "teardown"):
            for outcome in ("failed", "error", "interrupted"):
                candidate = deepcopy(self.report)
                next(row for row in candidate["phase_outcomes"] if row["when"] == when)["outcome"] = outcome
                with self.subTest(when=when, outcome=outcome), self.assertRaises(EvidenceError):
                    self.validate(candidate)
            candidate = deepcopy(self.report)
            candidate["phase_outcomes"] = [row for row in candidate["phase_outcomes"] if row["when"] != when]
            with self.subTest(missing=when), self.assertRaises(EvidenceError):
                self.validate(candidate)

    def test_duplicate_out_of_order_or_foreign_phases_fail(self):
        original = self.report["phase_outcomes"]
        variants = [original + [original[0]], list(reversed(original)),
                    [{**original[0], "nodeid": NODES[2]}, *original[1:]],
                    [{**original[0], "duration": float("inf")}, *original[1:]]]
        for phases in variants:
            with self.subTest(phases=phases), self.assertRaises(EvidenceError):
                self.validate({**self.report, "phase_outcomes": phases})

    def test_worker_zero_duplicate_missing_and_extra_nodes_fail(self):
        for key in ("collected_nodeids", "executed_nodeids"):
            for values in ([], NODES[:1], NODES, [NODES[0], NODES[0]]):
                with self.subTest(key=key, values=values), self.assertRaises(EvidenceError):
                    self.validate({**self.report, key: values})

    def test_repeated_subtests_pass_without_duplicate_main_phases_or_node_counts(self):
        collection, workers = cohort()
        row = {"nodeid": NODES[0], "when": "call", "outcome": "passed", "duration": 0.01}
        workers[0]["report"]["subtest_outcomes"] = [row, dict(row), {**row, "outcome": "skipped"}]
        result = aggregate(collection, workers)
        self.assertEqual(result["executed_node_count"], 3)

    def test_failed_subtest_overrides_zero_exit_and_successful_main_phases(self):
        for outcome in ("failed", "error", "interrupted", "unknown"):
            collection, workers = cohort()
            workers[0]["report"]["subtest_outcomes"] = [
                {"nodeid": NODES[0], "when": "call", "outcome": outcome, "duration": 0.01}]
            with self.subTest(outcome=outcome), self.assertRaises(EvidenceError):
                aggregate(collection, workers)

    def test_subtest_list_and_rows_are_required_structured_evidence(self):
        row = {"nodeid": NODES[0], "when": "call", "outcome": "passed", "duration": 0.01}
        candidates = [None, {}, "", [None], ["passed"]]
        candidates.extend([{key: value for key, value in row.items() if key != missing}] for missing in row)
        for values in candidates:
            with self.subTest(values=values), self.assertRaises(EvidenceError):
                self.validate({**self.report, "subtest_outcomes": values})

    def test_subtest_foreign_node_phase_and_invalid_duration_fail(self):
        row = {"nodeid": NODES[0], "when": "call", "outcome": "passed", "duration": 0.01}
        changes = [{"nodeid": NODES[2]}, {"nodeid": FILES[0]}, {"when": "collection"},
                   {"duration": -1}, {"duration": float("nan")}, {"duration": float("inf")},
                   {"duration": True}, {"duration": "0.01"}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(EvidenceError):
                self.validate({**self.report, "subtest_outcomes": [{**row, **change}]})

    def test_subtests_cannot_supply_a_missing_main_call_phase(self):
        self.report["phase_outcomes"] = [row for row in self.report["phase_outcomes"]
                                           if not (row["nodeid"] == NODES[0] and row["when"] == "call")]
        self.report["subtest_outcomes"] = [{"nodeid": NODES[0], "when": "call", "outcome": "passed", "duration": 0.01}]
        with self.assertRaises(EvidenceError):
            self.validate()
        self.report["phase_outcomes"][0]["outcome"] = "skipped"
        with self.assertRaises(EvidenceError):
            self.validate()

    def test_hash_mutation_missing_empty_or_bad_digest_fails(self):
        for key in ("source_hashes_before", "source_hashes_after", "asset_hashes_before", "asset_hashes_after"):
            for value in ({}, None, {"core/example.py": "bad"}, {"../escape": HASH},
                          {"core/example.py": "b" * 64}):
                with self.subTest(key=key, value=value), self.assertRaises(EvidenceError):
                    self.validate({**self.report, key: value})

    def test_hash_key_separator_normalization(self):
        self.report["source_hashes_before"] = {key.replace("/", "\\"): value for key, value in self.report["source_hashes_before"].items()}
        self.validate()

    def test_sqlite_and_write_paths_must_be_own_child_run(self):
        foreign = ROOT / "output" / "usage-holds-sibling" / "data.sqlite3"
        for key in ("sqlite_paths", "write_paths"):
            for path in (str(foreign), str(ROOT / "data" / "operating.sqlite3"), "relative.db",
                         "file:/tmp/test.sqlite3", str(ROOT / "output" / "verification-synthetic" / "2.json")):
                with self.subTest(key=key, path=path), self.assertRaises(EvidenceError):
                    self.validate({**self.report, key: [path]})

    def test_run_boundary_cannot_be_parent_nested_or_relative(self):
        for runtime in (str(ROOT / "output"), "usage-holds-relative",
                        str(ROOT / "output" / "usage-holds-a" / "nested"),
                        str(ROOT / "output" / "verification-synthetic")):
            with self.subTest(runtime=runtime), self.assertRaises(EvidenceError):
                self.validate({**self.report, "run_root": runtime})


class AggregateTests(unittest.TestCase):
    def test_collector_and_worker_require_exact_true_environment_sanitization_attestation(self):
        for target in ("collector", "worker"):
            for value in (None, False, 1, "true", "missing"):
                collection, workers = cohort()
                report = collection["report"] if target == "collector" else workers[0]["report"]
                if value == "missing":
                    del report["pytest_environment_sanitized"]
                else:
                    report["pytest_environment_sanitized"] = value
                with self.subTest(target=target, value=value), self.assertRaises(EvidenceError):
                    aggregate(collection, workers)

    def test_two_worker_exact_union_passes(self):
        result = aggregate(*cohort())
        self.assertEqual(result["expected_node_count"], 3)
        self.assertEqual(result["executed_node_count"], 3)
        self.assertEqual(result["executed_nodeids"], sorted(NODES))

    def test_one_worker_covers_manifest(self):
        collection, _ = cohort()
        result = aggregate_reports(collection, [record(invocation(2, FILES), NODES)],
                                   root=ROOT, targets=FILES, partitions=[FILES])
        self.assertEqual(result["executed_node_count"], 3)

    def test_missing_report_process_failure_or_worker_absence_fail(self):
        for mutation in ("missing", "exit", "absent", "invalid"):
            collection, workers = cohort()
            if mutation == "missing":
                workers[0]["report"] = None
            elif mutation == "exit":
                workers[0]["returncode"] = 1
            elif mutation == "absent":
                workers.pop()
            else:
                del workers[0]["report"]
            with self.subTest(mutation=mutation), self.assertRaises(EvidenceError):
                aggregate(collection, workers)

    def test_worker_internally_unchanged_but_different_snapshot_fails(self):
        for family in ("source", "asset"):
            for mutation in ("value", "extra_key"):
                collection, workers = cohort()
                for side in ("before", "after"):
                    hashes = workers[0]["report"][family + "_hashes_" + side]
                    key = next(iter(hashes)) if mutation == "value" else "new/file.py"
                    hashes[key] = "b" * 64
                with self.subTest(family=family, mutation=mutation), self.assertRaises(EvidenceError):
                    aggregate(collection, workers)

    def test_internally_consistent_worker_manifest_still_cannot_drop_expected_node(self):
        collection, workers = cohort()
        workers[0] = record(workers[0]["invocation"], NODES[:1])
        with self.assertRaises(EvidenceError):
            aggregate(collection, workers)

    def test_duplicate_execution_and_cross_worker_node_fail(self):
        collection, workers = cohort()
        workers[1]["report"]["executed_nodeids"].append(NODES[0])
        with self.assertRaises(EvidenceError):
            aggregate(collection, workers)

    def test_reused_run_id_or_invocation_id_fail(self):
        for same in ("run", "invocation"):
            collection, workers = cohort()
            if same == "run":
                for key in ("run_root", "sqlite_paths", "write_paths"):
                    workers[1]["report"][key] = deepcopy(workers[0]["report"][key])
            else:
                identity = workers[0]["invocation"].invocation_id
                workers[1]["invocation"] = replace(workers[1]["invocation"], invocation_id=identity)
                workers[1]["report"]["invocation_id"] = identity
            with self.subTest(same=same), self.assertRaises(EvidenceError):
                aggregate(collection, workers)

    def test_collector_failure_blocks_aggregation(self):
        collection, workers = cohort()
        collection["returncode"] = 2
        with self.assertRaises(EvidenceError):
            aggregate(collection, workers)

    def test_duplicate_json_keys_and_nonfinite_literals_fail(self):
        for value in ('{"exit_code": 1, "exit_code": 0}', '{"duration": NaN}', '{"duration": Infinity}'):
            with self.subTest(value=value), self.assertRaises(EvidenceError):
                json.loads(value, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
