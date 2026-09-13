"""실행하지 않는 B0~B3+B4 등록 회귀 검증 계획. ROOT는 호출자가 명시한다.

stdlib로 경로·Python AST만 읽는다. 앱 import, subprocess, DB, 파일 쓰기는 없다.
coverage는 선택 범위일 뿐 PASS/제품 완료 판정이 아니다. full도 이 runner의
B0~B3 기준선과 등록된 B4/verification 파일이며 저장소의 모든 시험이라는 뜻은 아니다.
브라우저·현업 수용이나 아직 작성되지 않은 B4 시험까지 검증했다고 주장하지 않는다.
"""
from __future__ import annotations

import ast
from pathlib import Path, PureWindowsPath
import re


_BASE_NAMES = (
    "data_usage_holds", "data_readiness", "dataset_snapshot", "object_scope_index",
    "kit_app_builder", "calc_canary",
    "b1_process_configuration", "b1_process_adversarial", "ecm_e1", "ecm_e2_profile", "admin_capability",
    "project_data_context", "b0_data_boundary", "actual_certification",
    "b0_certification_atomicity", "b0_snapshot_transaction", "b0_certification_subject",
    "b0_certification_races", "b0_certification_integrity", "b0_certification_review_regressions",
    "b0_certification_api_contract", "b2_pack_artifacts", "b2_installation", "b2_installation_api",
)
_HOST_NAMES = ("host_runtime_wire", "host_runtime_sdk", "contract_decision_api",
               "capability_decision_normalization", "tech_lead_contract_draft")
_ROUTE_NAMES = (
    "test_every_table_entry_matches_a_real_route", "test_every_exempt_entry_matches_a_real_route",
    "test_every_write_route_is_decided", "test_exempt_entries_carry_a_reason",
    "test_member_may_run_but_not_release",
)
_SELF_TEST = "tests/test_verification_plan.py"
_QUICK = (
    "tests/test_b3_runtime_contract_v2.py::test_v2_schema_is_separate_and_preserves_server_context",
    "tests/test_b3_runtime_contract_v2.py::test_v2_missing_or_malformed_context_cannot_compile",
    "tests/test_b3_hotl_context.py",
    "tests/test_b3_decision_round.py::test_pending_uses_persisted_identity_without_get_uuid_or_meta_write",
    "tests/test_b3_decision_round.py::test_same_content_new_save_has_new_uuid_and_stale_expected_409",
)

# 확인한 계약 경계만 좁힌다. B3와 process 계약의 B4 신규 소비자는 glob으로 포함한다.
# HOTL도 토큰 함수 시험만 골라서는 HTTP/실행 경계를 놓치므로 전체 B3를 포함한다.
_MODULE_CONTRACTS = {
    "core/studio_hotl_context.py": "runtime",
    "core/contract_decision.py": "runtime",
    "nodes/contract.py": "runtime",
    "core/app_runtime_contract.py": "runtime",
    "core/host_contract_compiler.py": "runtime",
    "core/project_contract_aggregator.py": "runtime",
    "core/kit_app_contract.py": "runtime",
    "core/kit_app_builder.py": "runtime",
    "core/enterprise_context/process_configuration.py": "process",
    "core/enterprise_context/process_installation.py": "process",
    "core/enterprise_context/process_references.py": "process",
    "core/enterprise_context/process_context.py": "process",
    "core/data_preparation/process_pack_artifacts.py": "process",
    "core/data_preparation/process_kit_instances.py": "process",
    "api/routes/process_configuration_control.py": "process",
    "api/routes/process_installation_control.py": "process",
    "api/routes/studio_kit_control.py": "runtime",
}
_COMMON = {
    "config.py", "main.py", "state_models.py", "pyproject.toml", "pytest.ini", "conftest.py",
    "api/deps.py", "core/paths.py", "core/library_paths.py", "core/scope_policy.py",
    "core/route_authority.py", "core/admin_capability.py", "core/decision_ledger.py",
    "core/project_data_context.py", "core/enterprise_context/process_schema.py",
    "core/enterprise_context/repository.py", "core/enterprise_context/models.py",
    "core/enterprise_context/context.py", "core/enterprise_context/resolver.py",
    "tests/org_seed.py", "tests/usage_hold_test_plugin.py", "tests/test_route_authority_table.py",
}
_SEGMENT = re.compile(r"[\w.-]+\Z")
_TEST_FILE = re.compile(r"test_[\w-]+\.py\Z")
_SELECTOR = re.compile(r"[^\W\d]\w*\Z")
_NOTICE = ("계획만 생성: PASS·완료 판정 없음. coverage는 B0~B3+B4 등록 회귀 중 선택 범위이며 제품 진척이 아닙니다. "
           "브라우저·현업 수용 및 아직 작성되지 않은 시험은 포함하지 않습니다.")


def _root(root) -> Path:
    path = Path(root)
    if not path.is_absolute():
        raise ValueError("ROOT는 명시적인 절대 디렉터리여야 합니다.")
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("ROOT 디렉터리가 없습니다.")
    return path


def _relative(text: str) -> str:
    if not isinstance(text, str) or not text or text != text.strip():
        raise ValueError("비어 있거나 공백으로 감싼 경로는 허용하지 않습니다.")
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ValueError("경로에 제어 문자를 넣을 수 없습니다.")
    value = text.replace("\\", "/")
    if value.startswith("/") or PureWindowsPath(value).drive:
        raise ValueError("상대 경로만 허용합니다.")
    parts = value.split("/")
    if any(p in ("", ".", "..") or p.startswith("-") or not _SEGMENT.fullmatch(p) for p in parts):
        raise ValueError("경로 이탈·옵션·지원하지 않는 경로 문자는 허용하지 않습니다.")
    return value


def _file(root: Path, relative: str) -> Path:
    path = root
    for part in relative.split("/"):
        path /= part
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise ValueError("링크 경로는 검증 대상으로 사용하지 않습니다.")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("ROOT 안의 기존 파일만 허용합니다.")
    return resolved


def _nodeid_parts(target: str) -> list[str]:
    # pytest와 같이 첫 '[' 이후는 마지막 selector의 불투명한 parameter ID다.
    # ID 안의 /, 공백, ::, 옵션처럼 보이는 문자열을 파일 경로/별도 argv로 해석하지 않는다.
    head, bracket, tail = target.partition("[")
    parts = head.split("::")
    if bracket:
        if len(parts) < 2 or not tail.endswith("]"):
            raise ValueError("parameter ID는 selector 뒤의 닫힌 [param] 형식이어야 합니다.")
        parts[-1] += bracket + tail
    return parts


def normalize_target(root, target: str) -> str:
    """기존 tests/**/test_*.py[::Class][::test[param]]만 허용한다.

    selector 식별자와 [param]을 분리한다. parameter ID는 제어문자 없이 원형 보존한다.
    호출자는 반환값을 shell=False의 단일 argv로 전달해야 하며 문자열 명령을 만들지 않는다.
    selector는 구문만 검사하며 pytest 수집/import로 존재 여부를 확인하지 않는다.
    여러 대상 사이의 중복/포함 관계는 normalize_targets가 검사한다.
    """
    root = _root(root)
    if not isinstance(target, str):
        raise ValueError("대상은 문자열이어야 합니다.")
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 or c in "\u2028\u2029" for c in target):
        raise ValueError("대상에 제어 문자·줄바꿈을 넣을 수 없습니다.")
    bits = _nodeid_parts(target)
    relative = _relative(bits[0])
    if not relative.startswith("tests/") or not _TEST_FILE.fullmatch(relative.rsplit("/", 1)[-1]):
        raise ValueError("tests 아래 test_*.py만 실행 대상으로 허용합니다.")
    if any(not _SELECTOR.fullmatch(bit.partition("[")[0]) for bit in bits[1:]):
        raise ValueError("지원하지 않는 pytest selector입니다.")
    try:
        _file(root, relative)
    except OSError as exc:
        raise ValueError(f"검증 대상 파일을 확인할 수 없습니다: {relative}") from exc
    return "::".join([relative, *bits[1:]])


def _covers(parent: str, child: str) -> bool:
    left, right = _nodeid_parts(parent), _nodeid_parts(child)
    if left[0].casefold() != right[0].casefold() or len(left) > len(right):
        return False
    return all(a == b or ("[" not in a and b.startswith(a + "["))
               for a, b in zip(left[1:], right[1:]))


def normalize_targets(root, targets) -> list[str]:
    """명시 --target 목록용: 중복·파일/함수·클래스/함수 겹침은 거절한다."""
    if isinstance(targets, (str, bytes)):
        raise ValueError("대상 목록이 필요합니다.")
    result = []
    for raw in targets:
        target = normalize_target(root, raw)
        if any(_covers(old, target) or _covers(target, old) for old in result):
            raise ValueError(f"중복 또는 겹치는 검증 대상: {target}")
        result.append(target)
    if not result:
        raise ValueError("빈 검증 대상은 허용하지 않습니다.")
    return result


def _union(root, targets) -> list[str]:
    # 내부 계약군 합집합은 넓은 파일 대상이 좁은 nodeid를 흡수한다.
    result = []
    for raw in targets:
        target = normalize_target(root, raw)
        if any(_covers(old, target) for old in result):
            continue
        result = [old for old in result if not _covers(target, old)]
        result.append(target)
    return normalize_targets(root, result)


def full_targets(root) -> list[str]:
    """기존 B0~B3 대상 + 현재 존재하는 B4/verification 시험 파일.

    B4는 dispatcher의 명시 --target 전달로 실행한다. 구 runner 기본 목록과 구분한다.
    필수 기준선 파일 부재는 빈 성공/축소로 바꾸지 않고 ValueError로 중단한다.
    """
    root = _root(root)
    targets = [f"tests/test_{name}.py" for name in _BASE_NAMES]
    targets += [p.relative_to(root).as_posix() for p in sorted((root / "tests").glob("test_b3_*.py"))]
    targets += [p.relative_to(root).as_posix() for p in sorted((root / "tests").glob("test_b4_*.py"))]
    targets += [f"tests/test_{name}.py" for name in _HOST_NAMES]
    targets += ["tests/test_route_authority_table.py::" + name for name in _ROUTE_NAMES]
    targets += [_SELF_TEST]
    targets += [p.relative_to(root).as_posix() for p in sorted((root / "tests").glob("test_verification*.py"))]
    return _union(root, targets)


def _dynamic(tree) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] in {"importlib", "runpy"} for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in {"importlib", "runpy"}:
            return True
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            return True
        if isinstance(node, ast.Name) and node.id in {"__import__", "exec", "eval"}:
            return True
        if isinstance(node, ast.Attribute) and node.attr in {"import_module", "getfixturevalue", "modules"}:
            return True
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name in {"__import__", "import_module", "spec_from_file_location", "module_from_spec", "exec", "eval"}:
                return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = [x.id for x in ast.walk(node) if isinstance(x, ast.Name)]
            if "pytest_plugins" in names:
                return True
    return False


def _tree(root, relative):
    return ast.parse(_file(root, relative).read_text(encoding="utf-8-sig"), filename=relative)


def _fixture_risk(root, changed: str) -> str:
    """시험 모듈의 fixture/helper를 import하는 소비자를 좁은 선택에서 놓치지 않는다."""
    module = changed[:-3].replace("/", ".")
    short = module.rsplit(".", 1)[-1]
    for path in sorted((root / "tests").rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == changed:
            continue
        tree = _tree(root, relative)
        if _dynamic(tree):
            return f"DYNAMIC_TEST_DEPENDENCY: {relative}의 동적 시험 의존성을 확정할 수 없습니다."
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                imported = [base, *[base + "." + a.name for a in node.names]]
                if node.level and any(a.name == short for a in node.names):
                    return f"SHARED_TEST_IMPORT: {relative}가 {changed}의 fixture/helper를 참조합니다."
            else:
                continue
            if any(value in (module, short) or value.startswith(module + ".") for value in imported):
                return f"SHARED_TEST_IMPORT: {relative}가 {changed}의 fixture/helper를 참조합니다."
    return ""


def _contract_targets(full, contract):
    extras = {f"tests/test_{name}.py" for name in _HOST_NAMES}
    extras.update({"tests/test_kit_app_builder.py", "tests/test_project_data_context.py",
                   "tests/test_b0_data_boundary.py"})
    prefixes = ["tests/test_b3_", "tests/test_route_authority_table.py::"]
    if contract == "process":
        prefixes += ["tests/test_b1_", "tests/test_b2_", "tests/test_b4_"]
        extras.update({"tests/test_ecm_e1.py", "tests/test_ecm_e2_profile.py", "tests/test_admin_capability.py"})
    return [t for t in full if t in extras or any(t.startswith(p) for p in prefixes)]


def plan(root, tier: str = "full", changed=()) -> dict:
    """quick은 명시 빠른 부분, feature는 보수적 계약군, 불명확하면 full.

    quick + changed도 변경 영향 검사를 생략하지 않는다. 관련 계약군을 합치면
    coverage=affected, 공통/알 수 없는 변경이면 coverage=full로 승격한다.
    """
    root = _root(root)
    if tier not in ("quick", "feature", "full"):
        raise ValueError("tier는 quick/feature/full이어야 합니다.")
    if isinstance(changed, (str, bytes)):
        raise ValueError("changed는 반복 경로 목록이어야 합니다.")
    changes = list(changed)
    full = full_targets(root)
    selftests = [t for t in full if t.startswith("tests/test_verification")]
    reasons = [_NOTICE]
    if tier == "full":
        return {"targets": full, "coverage": "full", "reasons": reasons + ["EXPLICIT_FULL: 전체 기준선과 selftest를 선택했습니다."]}
    if not changes:
        if tier == "feature":
            return {"targets": full, "coverage": "full", "reasons": reasons + ["NO_CHANGED_PATHS: 영향 범위가 없어 full로 승격했습니다."]}
        return {"targets": _union(root, [*_QUICK, *selftests]), "coverage": "quick",
                "reasons": reasons + ["EXPLICIT_QUICK: 순수 schema/HOTL 및 임시 저장소 round identity 일부만 확인합니다. 전체 회귀를 대체하지 않습니다."]}
    selected = list(selftests)
    promote = False
    seen = set()
    for raw in changes:
        try:
            relative = _relative(raw)
            if relative in seen:
                continue
            seen.add(relative)
            _file(root, relative)
        except (OSError, ValueError, TypeError) as exc:
            reasons.append(f"MISSING_OR_UNSAFE_CHANGE: {raw!r}: {exc}; full로 승격합니다.")
            promote = True
            continue
        common = (relative in _COMMON or relative.startswith(("scripts/", "core/org", "core/auth", "core/admin"))
                  or relative.endswith(("/conftest.py", "/store.py", "/__init__.py"))
                  or relative.startswith("tests/test_verification") or "auth" in Path(relative).stem)
        if common:
            reasons.append(f"COMMON_CHANGE: {relative}; 공유 권한/저장소/검증 기반 변경은 full입니다.")
            promote = True
            continue
        try:
            if relative.endswith(".py") and _dynamic(_tree(root, relative)):
                reasons.append(f"DYNAMIC_CHANGE: {relative}; 정적 의존성 확정 불가로 full입니다.")
                promote = True
                continue
            if relative in _MODULE_CONTRACTS:
                contract = _MODULE_CONTRACTS[relative]
                selected += _contract_targets(full, contract)
                consumers = "등록된 B1/B2/B3/B4 소비자" if contract == "process" else "등록된 B3 소비자"
                reasons.append(f"CONTRACT_MAPPING: {relative} -> {contract} 계약군({consumers} 포함).")
            elif relative.startswith("tests/") and relative in full:
                risk = _fixture_risk(root, relative)
                if risk:
                    promote = True
                    reasons.append(risk + " full로 승격합니다.")
                else:
                    selected.append(relative)
                    reasons.append(f"ISOLATED_TEST_CHANGE: {relative}; 정적 시험 import 소비자가 없습니다.")
            else:
                promote = True
                reasons.append(f"UNKNOWN_CHANGE: {relative}; 승인된 계약 매핑이 없어 full입니다.")
        except (OSError, UnicodeError, SyntaxError, ValueError, RecursionError) as exc:
            promote = True
            reasons.append(f"STATIC_ANALYSIS_UNAVAILABLE: {relative}: {type(exc).__name__}; full입니다.")
    if promote:
        return {"targets": full, "coverage": "full", "reasons": reasons}
    if tier == "quick":
        selected += _QUICK
        reasons.append("QUICK_EXPANDED: 변경 계약군을 더했으므로 quick 단독이 아닌 affected입니다.")
    targets = _union(root, selected)
    coverage = "full" if set(targets) == set(full) else "affected"
    return {"targets": targets, "coverage": coverage, "reasons": reasons}
