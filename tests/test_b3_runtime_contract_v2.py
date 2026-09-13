"""B3 문서 2.0 회귀. main의 감사·격리 runner에서만 실행한다.

1.0 원문은 2026-09-13 B3 편집 전에 파일 읽기로 확보했다.
아래 frozen 함수·schema 원문 SHA를 현재 구현으로 다시 생성하지 않는다.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from core import app_runtime_contract as arc
from core import host_contract_compiler as compiler
from core import project_contract_aggregator as aggregator


_LEGACY_CANONICAL_SOURCE = "def canonical_json(obj: Any) -> str:\n    \"\"\"정렬된 canonical JSON — 지문의 입력.\n\n    ⚠️ 키 순서가 다르면 같은 내용이 다른 지문을 갖는다. 그러면 「계약이 바뀌었다」는 판정이\n      거짓이 되고, 아무도 그 판정을 믿지 않게 된다.\"\"\"\n    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(\",\", \":\"))"
_LEGACY_MATERIAL_SOURCE = "def semantic_material(contract: Dict[str, Any]) -> Dict[str, Any]:\n    \"\"\"지문에 **들어가는 것만** 추린다.\n\n    ★ `label`·`purpose`·`reason` 같은 설명 문구는 **들어가지 않는다.** 문구를 다듬었다고\n      재승인을 요구하면 사람이 게이트를 습관으로 통과시킨다 — 그러면 게이트가 아니다.\"\"\"\n    c = contract if isinstance(contract, dict) else {}\n    datasets = []\n    for ds in (c.get(\"datasets\") or []):\n        d = ds if isinstance(ds, dict) else {}\n        datasets.append({\n            \"name\": str(d.get(\"name\", \"\")),\n            #: 정체가 바뀌면 그것은 다른 데이터셋이다 — 지문이 움직여야 한다.\n            \"dataset_key\": str(d.get(\"dataset_key\", \"\") or d.get(\"name\", \"\")),\n            \"allowed_actions\": sorted({str(a) for a in (d.get(\"allowed_actions\") or [])}),\n            \"ontology_entity_type\": str(d.get(\"ontology_entity_type\", \"\")),\n            #: ★★★ [BDR-1] 출처·역할·중복입력은 **의미**다. 이것이 바뀌면 앱이 다루는 것이\n            #:   달라진다 — 「기존 시스템에서 읽는다」가 「화면에서 받는다」로 바뀌는 것은\n            #:   설명 문구가 아니라 업무 자체의 변경이고, **재승인 대상**이다.\n            \"data_role\": str(d.get(\"data_role\", \"\")),\n            \"source_intent\": str(d.get(\"source_intent\", \"\")),\n            \"duplicate_entry_policy\": str(d.get(\"duplicate_entry_policy\", \"\")),\n            \"enterprise_contract_key\": str(d.get(\"enterprise_contract_key\", \"\")),\n            \"required_freshness\": str(d.get(\"required_freshness\", \"\")),\n            \"fields\": sorted(\n                ({\"name\": str(f.get(\"name\", \"\")), \"type\": str(f.get(\"type\", \"\")),\n                  \"required\": bool(f.get(\"required\", False)), \"unit\": str(f.get(\"unit\", \"\")),\n                  \"classification\": str(f.get(\"classification\", \"\")),\n                  \"semantic_role\": str(f.get(\"semantic_role\", \"\"))}\n                 for f in (d.get(\"fields\") or []) if isinstance(f, dict)),\n                key=lambda x: x[\"name\"]),\n        })\n    #: ★★★ 능력은 **집합**이다 — 같은 것이 몇 번 적혔는지는 권한이 아니다.\n    #:\n    #: ⚠️⚠️ [2026-08-26 실측] 종전에는 중복째 실었다. 그런데 이 재료에는\n    #:   `requirement_ref` 가 **빠져 있다**(설명이므로 옳다). 그 결과 「같은 `app_data.read`\n    #:   를 몇 개의 FR 이 인용했는가」만으로 지문이 바뀌었다 — 권한은 한 글자도 안 달라졌는데.\n    #:   실측: Tech Lead 가 매 실행마다 FR 인용 수를 달리 적어 지문이\n    #:   `56ac83 → 906969 → 56ac83 → 2fcd71` 로 오갔고, **승인이 영영 수렴하지 않았다.**\n    #:   사용자는 승인을 눌러도 계속 재승인을 요구받는다.\n    #: ★ 머리말이 「문구를 다듬었다고 재승인을 요구하면 사람이 게이트를 습관으로 통과시킨다」\n    #:   고 적어 둔 것과 **같은 이유**다. 인용 횟수도 문구다.\n    #: ⚠️ 「같음」의 기준은 (능력·상태·사용자결정) 셋이다. 하나라도 다르면 **남는다** —\n    #:   예: `network.external_api` 를 FR-1 은 `REDUCE`, FR-2 는 `WAIT` 로 정했다면 둘 다\n    #:   실린다. 그것은 실제로 다른 결정이고, 합치면 하나가 조용히 사라진다.\n    _seen_intents: set = set()\n    intents = []\n    for i in (c.get(\"capability_intents\") or []):\n        if not isinstance(i, dict):\n            continue\n        item = {\"capability\": str(i.get(\"capability\", \"\")),\n                \"status\": str(i.get(\"status\", \"\")),\n                \"user_decision\": str(i.get(\"user_decision\", \"\"))}\n        key = (item[\"capability\"], item[\"status\"], item[\"user_decision\"])\n        if key in _seen_intents:\n            continue\n        _seen_intents.add(key)\n        intents.append(item)\n    intents.sort(key=lambda x: (x[\"capability\"], x[\"status\"], x[\"user_decision\"]))\n    return {\n        \"app_class\": str(c.get(\"app_class\", \"\")),\n        \"datasets\": sorted(datasets, key=lambda x: x[\"name\"]),\n        \"capability_intents\": intents,\n    }"
_LEGACY_SCHEMA_SOURCE_SHA256 = {
    "_DATASET_SCHEMA": "7d04d8ae56b8559edd17e31ba729b4c3625aec691cd7625450e698ec6fd5aa16",
    "_INTENT_SCHEMA": "06f4803093c5fc12dfc3bfe53d02e4fe9566e6bb59b0efac592d6fc3b3297100",
    "_UNSUPPORTED_SCHEMA": "0666c489aa4a620242823ea0ce5e2b754bcbf757f944c46cb190e9cabf5e8b20",
    "_FIELD_SCHEMA": "fda7b7125374ccce1ffdc018ed957ee454c2a158671952fa0d093770547f7098",
    "CONTRACT_SCHEMA": "ef136c8d481f5263e41a0f5875a19a0c959740f23c9c7907951e7b6dd872211d"
}
_PRE_EDIT_SOURCE_SHA256 = {
    "core/app_runtime_contract.py": "289a43d161aac060f0c53e3dd248f0e1e6f40d418940c59c04b943eeb401573a",
    "core/host_contract_compiler.py": "3874e938585a9c24edfe9fb98fa34de844c827c293f90bcb2a47d41581dc5770",
    "core/project_contract_aggregator.py": "8ac997fdbb78f45a3291cc622579c32145d984cd02aec2183a9db4f9cf23d78b",
    "nodes/contract.py": "7eac3dd985c15de69072290157dcf4e23263ce660615f24ab96ff0bf195a51d0",
}


def _frozen_v1_functions():
    namespace = {"json": json, "Any": Any, "Dict": Dict}
    # 현재 코드로 기대값을 재생성하지 않고 고정한 이전 순수 함수만 사용한다.
    exec(_LEGACY_CANONICAL_SOURCE + "\n\n" + _LEGACY_MATERIAL_SOURCE, namespace)
    return namespace["canonical_json"], namespace["semantic_material"]


# 변경 전 1.0 함수에서 읽어 확정한 무데이터·무능력 계약의 canonical 원문.
_V1_COMPILED_CANONICAL = "{\"app_class\":\"departmental\",\"approval\":{\"status\":\"PENDING\"},\"capability_intents\":[],\"contract_id\":\"contract_bcd77aad50f2\",\"datasets\":[],\"manifest\":{\"app_class\":\"departmental\",\"audit_mode\":\"PLATFORM_LEDGER\",\"auth_mode\":\"PLATFORM_INHERITED\",\"capabilities\":[],\"enterprise_scope_mode\":\"HOST_CONTEXT\",\"entrypoints\":[],\"forbidden_features\":[\"jwt_issuer\",\"local_login\",\"local_user_store\"],\"host_auth_required\":true,\"required_capabilities\":[],\"required_data_scopes\":[],\"standalone_auth\":false,\"version\":\"1.0\"},\"project_id\":\"B3-GOLDEN\",\"revision\":1,\"runtime_contract_version\":1,\"schema_version\":\"1.0\",\"semantic_fingerprint\":\"0c481788facfb3e2ecf2018b12b5eeb59860be2bb2b467a68dbd39ffebe82dd7\",\"status\":\"COMPILED\",\"task_id\":\"\",\"unsupported_requirements\":[]}"
_V1_SEMANTIC_BYTES = b'{"app_class":"departmental","capability_intents":[],"datasets":[]}'
_V1_EXPECTED_FINGERPRINT = "0c481788facfb3e2ecf2018b12b5eeb59860be2bb2b467a68dbd39ffebe82dd7"


def _draft():
    return {
        "app_class": "departmental",
        "capability_intents": [],
        "datasets": [{
            "name": "arrivals", "label": "입고 검토", "purpose": "입고 메모를 조회한다",
            "allowed_actions": ["read"],
            "data_role": "NATIVE_SUPPLEMENT", "source_intent": "AFS_NATIVE",
            "duplicate_entry_policy": "NO_DUPLICATE_CHECK_REQUIRED",
            "fields": [
                {"name": "qty", "type": "number", "required": True,
                 "classification": "INTERNAL", "semantic_role": "quantity", "unit": "ton"},
                {"name": "note", "type": "text", "required": False, "classification": "INTERNAL"},
            ],
        }],
    }


def _context():
    return {
        "schema_version": 1, "configuration_id": "configuration_b3", "profile_id": "profile_b3",
        "process_ids": ["process_b3_contract", "process_b3_plan"],
        "process_semantic_fingerprint": "a" * 64, "configuration_fingerprint": "b" * 64,
        "context_key": {"tenant_id": "tenant_b3", "context_root_id": "root_b3",
                        "entity_mode": "REAL", "scope_node_id": ""},
        "data_requirements": [], "verified_binding_refs": [], "blockers": [],
        "permitted_actions": ["DRAFT"],
        "sources": [{"kind": "PROCESS_PROFILE", "configuration_id": "configuration_b3",
                     "profile_id": "profile_b3", "fingerprint": "b" * 64}],
    }


def _compile2(context=None, previous=None):
    return compiler.compile_contract(_draft(), project_id="B3-P", document_version="2.0",
                                     process_context=_context() if context is None else context,
                                     previous=previous)


def _binding(process_id="process_b3_contract", requirement_key="need_arrivals"):
    return {
        "process_id": process_id, "requirement_key": requirement_key,
        "instance_id": "instance_b3", "contract_key": "purchase_orders",
        "artifact_digest": "c" * 64, "binding_id": "binding_b3",
        "binding_fingerprint": "d" * 64, "snapshot_id": "snapshot_b3",
        "snapshot_fingerprint": "e" * 64, "checksum": "f" * 64,
        "ownership_binding_id": "owner_b3", "ownership_fingerprint": "1" * 64,
        "certification_state": "SOURCE_CERTIFIED", "certification_subject_id": None,
        "certification_subject_digest": None, "signing_policy_id": None,
        "signing_policy_digest": None, "certified_use_kind": None,
        "usage_policy_fingerprint": "2" * 64,
    }


def _bound_context():
    context = _context()
    refs = [_binding(pid) for pid in context["process_ids"]]
    context["verified_binding_refs"] = refs
    context["data_requirements"] = [
        {"process_id": ref["process_id"], "requirement_key": ref["requirement_key"],
         "logical_requirement": "입고 실적", "mandatory": True,
         "candidate_contract_keys": [ref["contract_key"]], "unresolved_requirement": False}
        for ref in refs]
    context["sources"].append({"kind": "PROCESS_PACK", "artifact_digest": "c" * 64,
        "pack_id": "pack_b3", "pack_version": "1.1.0", "pack_digest": "3" * 64,
        "instance_id": "instance_b3", "template_keys": ["BK-01.arrivals"]})
    return context


def _approved(contract):
    result = copy.deepcopy(contract)
    result["status"] = "APPROVED"
    result["approval"] = {"status": "APPROVED", "approved_by": "reviewer@test.invalid",
                          "approved_at": "2026-09-13T00:00:00Z",
                          "decision_ledger_id": "fixture_b3_approval"}
    assert not arc.validate(result)
    return result


def test_legacy_schema_assignment_source_is_unchanged():
    source = Path(arc.__file__).read_text(encoding="utf-8").replace("\r\n", "\n")
    tree = ast.parse(source)
    found = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            if name in _LEGACY_SCHEMA_SOURCE_SHA256:
                raw = ast.get_source_segment(source, node).encode("utf-8")
                found[name] = hashlib.sha256(raw).hexdigest()
    assert found == _LEGACY_SCHEMA_SOURCE_SHA256


def test_legacy_function_bodies_are_frozen_not_regenerated():
    source = Path(arc.__file__).read_text(encoding="utf-8").replace("\r\n", "\n")
    functions = {node.name: ast.get_source_segment(source, node)
                 for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}
    assert functions["canonical_json"] == _LEGACY_CANONICAL_SOURCE
    old_name = functions["_semantic_material_v1"].replace("def _semantic_material_v1(", "def semantic_material(", 1)
    assert old_name == _LEGACY_MATERIAL_SOURCE


def test_legacy_compiled_canonical_bytes_and_hash_are_fixed():
    draft = {"app_class": "departmental", "datasets": [], "capability_intents": []}
    result = compiler.compile_contract(draft, project_id="B3-GOLDEN")
    assert result.ok, result.errors
    assert arc.canonical_json(result.contract) == _V1_COMPILED_CANONICAL
    assert arc.canonical_json(arc.semantic_material(result.contract)).encode("utf-8") == _V1_SEMANTIC_BYTES
    assert result.fingerprint == _V1_EXPECTED_FINGERPRINT
    assert hashlib.sha256(_V1_SEMANTIC_BYTES).hexdigest() == _V1_EXPECTED_FINGERPRINT


@pytest.mark.parametrize("case", ["partial", "normal", "display", "duplicate_intents", "empty"])
def test_v1_material_and_canonical_match_frozen_original(case):
    canonical, material = _frozen_v1_functions()
    value = _draft()
    if case == "normal": value["schema_version"] = "1.0"
    elif case == "display":
        value["datasets"][0].update(label="다른 표시", purpose="설명만 변경")
    elif case == "duplicate_intents":
        value["capability_intents"] = [
            {"capability": "app_data.read", "status": "SUPPORTED", "requirement_ref": "R1"},
            {"capability": "app_data.read", "status": "SUPPORTED", "requirement_ref": "R2"},
        ]
    elif case == "empty": value = {}
    expected = canonical(material(value)).encode("utf-8")
    assert arc.semantic_material(value) == material(value)
    assert arc.canonical_json(arc.semantic_material(value)).encode("utf-8") == expected
    assert arc.semantic_fingerprint(value) == hashlib.sha256(expected).hexdigest()


def test_legacy_approval_and_wire_version_survive_recompile():
    previous = _approved(compiler.compile_contract(_draft(), project_id="B3-P").contract)
    frozen_bytes = arc.canonical_json(previous)
    result = compiler.compile_contract(_draft(), project_id="B3-P", previous=previous)
    assert result.ok
    assert arc.canonical_json(result.contract) == frozen_bytes
    assert arc.canonical_json(previous) == frozen_bytes
    assert arc.SCHEMA_VERSION == "1.0"
    assert arc.RUNTIME_CONTRACT_VERSION == 1
    from core import host_runtime_wire
    from state_models import PROJECT_STATE_SCHEMA_VERSION
    assert host_runtime_wire.WIRE_VERSION == 1
    assert PROJECT_STATE_SCHEMA_VERSION == "5.3.0"


def test_v2_schema_is_separate_and_preserves_server_context():
    result = _compile2()
    assert result.ok, result.errors
    assert result.contract["schema_version"] == "2.0"
    assert result.contract["runtime_contract_version"] == 1
    assert result.contract["process_context"] == _context()
    assert not arc.validate(result.contract)
    assert "process_context" not in arc.CONTRACT_SCHEMA["properties"]
    assert "process_context" not in arc.CONTRACT_SCHEMA["required"]
    assert arc.CONTRACT_SCHEMA["properties"]["schema_version"] == {"const": "1.0"}
    assert arc.CONTRACT_SCHEMA_V2["properties"]["schema_version"] == {"const": "2.0"}



def _node_workspace(tmp_path, *, require_metadata=False):
    from nodes.utils.wbs_manager import WBSManager
    root = tmp_path / "b3-node"
    root.mkdir()
    WBSManager(str(root)).initialize_wbs(
        "B3-P", [{"task_id": "A", "title": "입고 검토 앱", "artifact_kind": "APP"}],
        runtime_contract_profile="v1")
    if require_metadata:
        # 2.0 정상 경로는 실제 producer처럼 서버 판 메타데이터와 초안을 함께 저장한다.
        from nodes import contract as node
        node.save_draft(str(root), "A", _draft(), require_metadata=True)
    else:
        # 기존 부정 시험의 메타데이터 없는 초안은 의도적으로 그대로 둔다.
        drafts = root / "contracts" / "drafts"
        drafts.mkdir(parents=True, exist_ok=True)
        (drafts / "A.json").write_text(json.dumps(_draft(), ensure_ascii=False), encoding="utf-8")
    return root


def _node_state(root, context=None):
    return {"project_name": "B3-P", "workspace_root": str(root),
            "current_sprint_task_id": "A", "runtime_contract_profile": "v1",
            "runtime_document_version": "2.0",
            "process_context": _context() if context is None else context}


def test_node_passes_server_state_context_to_canonical_file(tmp_path):
    import asyncio
    from nodes import contract as node
    root = _node_workspace(tmp_path, require_metadata=True)
    context = _context()
    out = asyncio.run(node.run_host_contract_compiler(_node_state(root, context)))
    assert out["app_runtime_contract_status"] == "COMPILED"
    saved = json.loads(Path(node.contract_path(str(root))).read_text(encoding="utf-8"))
    assert saved["schema_version"] == "2.0"
    assert saved["process_context"] == context
    assert saved["semantic_fingerprint"] == out["app_runtime_contract_fingerprint"]
    assert not arc.validate(saved)


def test_node_missing_v2_context_preserves_previous_contract_bytes(tmp_path):
    import asyncio
    from nodes import contract as node
    root = _node_workspace(tmp_path)
    output = Path(node.contract_path(str(root)))
    previous = _approved(compiler.compile_contract(_draft(), project_id="B3-P").contract)
    raw = arc.canonical_json(previous).encode("utf-8")
    output.write_bytes(raw)
    out = asyncio.run(node.run_host_contract_compiler(_node_state(root, {})))
    assert out["terminal_status"] == "CONTRACT_BLOCKED"
    assert out["app_runtime_contract_fingerprint"] == ""
    assert output.read_bytes() == raw


def test_node_cannot_downgrade_previous_v2_file(tmp_path):
    import asyncio
    from nodes import contract as node
    root = _node_workspace(tmp_path)
    output = Path(node.contract_path(str(root)))
    raw = arc.canonical_json(_approved(_compile2().contract)).encode("utf-8")
    output.write_bytes(raw)
    state = _node_state(root, {})
    state["runtime_document_version"] = "1.0"
    out = asyncio.run(node.run_host_contract_compiler(state))
    assert out["terminal_status"] == "CONTRACT_BLOCKED"
    assert output.read_bytes() == raw


@pytest.mark.parametrize("mismatch", ["missing", "legacy", "semantic", "malformed"])
def test_v2_review_gate_cannot_use_missing_legacy_or_stale_context_contract(tmp_path, mismatch):
    import asyncio
    from nodes import contract as node
    root = _node_workspace(tmp_path)
    context = _context()
    contract = _approved(_compile2().contract)
    if mismatch == "legacy":
        contract = _approved(compiler.compile_contract(_draft(), project_id="B3-P").contract)
    elif mismatch == "semantic":
        context["process_semantic_fingerprint"] = "f" * 64
    elif mismatch == "malformed":
        contract["process_context"].pop("context_key")
    if mismatch != "missing":
        Path(node.contract_path(str(root))).write_text(arc.canonical_json(contract), encoding="utf-8")
    state = _node_state(root, context)
    state.update(app_runtime_contract_fingerprint=contract["semantic_fingerprint"],
                 approved_contract_fingerprint=contract["semantic_fingerprint"],
                 app_runtime_contract_status="APPROVED")
    out = asyncio.run(node.run_contract_review_gate(state))
    assert out["terminal_status"] == "CONTRACT_BLOCKED"
    assert out["contract_review_request_event_id"] == ""


def test_v2_review_gate_display_only_revision_keeps_approved_semantics(tmp_path):
    import asyncio
    from nodes import contract as node
    root = _node_workspace(tmp_path, require_metadata=True)
    contract = _approved(_compile2().contract)
    output = Path(node.contract_path(str(root)))
    raw = arc.canonical_json(contract).encode("utf-8")
    output.write_bytes(raw)
    context = _context()
    context["profile_id"] = "profile_display_revision"
    context["configuration_fingerprint"] = "d" * 64
    context["sources"] = [{"kind": "PROCESS_PROFILE", "configuration_id": "configuration_b3",
                           "profile_id": "profile_display_revision", "fingerprint": "d" * 64}]
    state = _node_state(root, context)
    state.update(app_runtime_contract_fingerprint=contract["semantic_fingerprint"],
                 approved_contract_fingerprint=contract["semantic_fingerprint"],
                 app_runtime_contract_status="APPROVED")
    out = asyncio.run(node.run_contract_review_gate(state))
    assert out == {"contract_review_request_event_id": ""}
    assert output.read_bytes() == raw


@pytest.mark.parametrize("context", [None, {}, [], "untrusted"])
def test_v2_missing_or_malformed_context_cannot_compile(context):
    result = compiler.compile_contract(_draft(), project_id="B3-P", document_version="2.0",
                                       process_context=context)
    assert not result.ok and result.status == "DRAFT" and not result.fingerprint
    assert result.contract["schema_version"] == "2.0"


@pytest.mark.parametrize("field", list(_context()))
def test_each_context_field_is_required(field):
    context = _context()
    context.pop(field)
    result = _compile2(context)
    assert not result.ok and not result.fingerprint


@pytest.mark.parametrize("mutation", ["extra_context_key", "missing_context_key", "mode", "schema_bool",
    "duplicate_ids", "empty_ids", "bad_digest", "unknown_field", "nan", "bad_source"])
def test_context_contract_rejects_unknown_and_noncanonical_values(mutation):
    context = _context()
    if mutation == "extra_context_key": context["context_key"]["configuration_kind"] = "business_process"
    elif mutation == "missing_context_key": context["context_key"].pop("scope_node_id")
    elif mutation == "mode": context["context_key"]["entity_mode"] = "SYNTHETIC_TEST"
    elif mutation == "schema_bool": context["schema_version"] = True
    elif mutation == "duplicate_ids": context["process_ids"] *= 2
    elif mutation == "empty_ids": context["process_ids"] = []
    elif mutation == "bad_digest": context["process_semantic_fingerprint"] = "short"
    elif mutation == "unknown_field": context["approved_by"] = "attacker@test.invalid"
    elif mutation == "nan": context["sources"][0]["untrusted_number"] = float("nan")
    elif mutation == "bad_source": context["sources"][0]["kind"] = "UNVERIFIED"
    assert arc.process_context_errors(context)
    assert not _compile2(context).ok


@pytest.mark.parametrize("version", ["", "3.0", "2", "v2", None, 2, True])
def test_unknown_document_version_does_not_fallback(version):
    result = compiler.compile_contract(_draft(), project_id="B3-P", document_version=version)
    assert not result.ok and not result.fingerprint
    assert result.status == "DRAFT"


def test_llm_draft_cannot_select_version_or_context():
    draft = _draft()
    draft.update(schema_version="2.0", document_version="2.0", process_context={"forged": True})
    legacy = compiler.compile_contract(draft, project_id="B3-P")
    assert legacy.ok and legacy.contract["schema_version"] == "1.0"
    assert "process_context" not in legacy.contract
    current = compiler.compile_contract(draft, project_id="B3-P", document_version="2.0", process_context=_context())
    assert current.ok and current.contract["process_context"] == _context()


def test_explicit_context_is_not_silently_dropped_from_v1():
    result = compiler.compile_contract(_draft(), project_id="B3-P", process_context=_context())
    assert not result.ok and not result.fingerprint


def test_v2_validator_and_hash_reject_lost_context_and_unknown_version():
    contract = _compile2().contract
    contract.pop("process_context")
    assert arc.validate(contract)
    with pytest.raises(arc.ContractError):
        arc.semantic_fingerprint(contract)
    contract["schema_version"] = "unsupported"
    assert arc.validate(contract)
    with pytest.raises(arc.ContractError):
        arc.semantic_fingerprint(contract)


@pytest.mark.parametrize("changed", ["tenant_id", "context_root_id", "entity_mode", "scope_node_id",
                                    "process_ids", "process_semantic_fingerprint", "verified_binding_refs"])
def test_v2_semantic_changes_require_new_fingerprint(changed):
    before = _compile2()
    context = _context()
    if changed in context["context_key"]:
        context["context_key"][changed] = "VIRTUAL" if changed == "entity_mode" else "changed_b3"
    elif changed == "process_ids":
        context[changed] = ["process_b3_other"]
    elif changed == "process_semantic_fingerprint":
        context[changed] = "c" * 64
    else:
        context = _bound_context()
    after = _compile2(context)
    assert after.ok, after.errors
    assert before.fingerprint != after.fingerprint


def test_display_tracking_changes_preserve_fingerprint_and_approval():
    before = _approved(_compile2().contract)
    context = _context()
    context["profile_id"] = "profile_b3_renamed"
    context["configuration_fingerprint"] = "e" * 64
    context["sources"] = [{"kind": "PROCESS_PROFILE", "configuration_id": "configuration_b3",
                           "profile_id": "profile_b3_renamed", "fingerprint": "e" * 64}]
    after = _compile2(context, previous=before)
    assert after.ok, after.errors
    assert after.fingerprint == before["semantic_fingerprint"]
    assert after.contract["approval"] == before["approval"]
    assert after.status == "APPROVED"
    assert after.contract["process_context"]["profile_id"] == "profile_b3_renamed"


@pytest.mark.parametrize("field", ["process_ids", "verified_binding_refs"])
def test_noncanonical_process_or_verified_ref_order_is_rejected_like_dto(field):
    context = _bound_context()
    before = _compile2(context)
    context[field].reverse()
    after = _compile2(context)
    assert before.ok, before.errors
    assert not after.ok and not after.fingerprint


def test_migration_requires_new_approval_and_downgrade_is_blocked():
    legacy = _approved(compiler.compile_contract(_draft(), project_id="B3-P").contract)
    current = _compile2(previous=legacy)
    assert current.ok and current.fingerprint_changed
    assert current.fingerprint != legacy["semantic_fingerprint"]
    assert current.status == "COMPILED"
    assert current.contract["approval"]["status"] == "PENDING"
    assert current.contract["approval"]["supersedes_fingerprint"] == legacy["semantic_fingerprint"]
    downgrade = compiler.compile_contract(_draft(), project_id="B3-P", previous=_approved(current.contract))
    assert not downgrade.ok and not downgrade.fingerprint


def test_invalid_previous_v2_approval_is_not_inherited():
    previous = _approved(_compile2().contract)
    previous["process_context"]["process_semantic_fingerprint"] = "f" * 64
    after = _compile2(previous=previous)
    assert not after.ok and not after.fingerprint
    assert after.contract["approval"] == {"status": "PENDING"}


@pytest.mark.parametrize("previous", ["not_a_contract", ["not_a_contract"],
    {"schema_version": "3.0", "revision": 1},
    {"schema_version": "2.0", "revision": "not_a_revision"}])
def test_v2_unknown_or_malformed_history_cannot_inherit_approval(previous):
    result = _compile2(previous=previous)
    assert not result.ok and not result.fingerprint
    assert result.status == "DRAFT"


def test_producers_copy_inputs_and_do_not_mutate_approved_history():
    context, draft = _context(), _draft()
    previous = _approved(_compile2().contract)
    originals = copy.deepcopy((context, draft, previous))
    result = compiler.compile_contract(draft, project_id="B3-P", document_version="2.0",
                                       process_context=context, previous=previous)
    assert (context, draft, previous) == originals
    assert result.contract["process_context"] is not context
    context["process_ids"].append("after_return")
    assert "after_return" not in result.contract["process_context"]["process_ids"]


def test_aggregator_preserves_explicit_context_and_ignores_task_forgery():
    context = _context()
    draft = _draft()
    draft["schema_version"], draft["process_context"] = "99.0", {"forged": True}
    tasks = [{"task_id": "A", "artifact_kind": "APP"}]
    aggregate = aggregator.aggregate(tasks, {"A": draft}, document_version="2.0", process_context=context)
    assert not aggregate.blocked
    assert aggregate.draft["process_context"] == context
    result, _ = aggregator.compile_project_contract(tasks, {"A": draft}, project_id="B3-P",
                                                     document_version="2.0", process_context=context)
    assert result.ok and result.contract["process_context"] == context
    legacy, _ = aggregator.compile_project_contract(tasks, {"A": draft}, project_id="B3-P")
    assert legacy.ok and legacy.contract["schema_version"] == "1.0"
    assert "process_context" not in legacy.contract


@pytest.mark.parametrize("drafts", [{}, {"A": {"app_class": "departmental", "datasets": [], "capability_intents": []}}])
def test_aggregate_failure_keeps_v2_and_never_drops_missing_context(drafts):
    result, aggregate = aggregator.compile_project_contract(
        [{"task_id": "A", "artifact_kind": "APP"}], drafts, project_id="B3-P", document_version="2.0")
    assert aggregate.blocked and not result.ok and not result.fingerprint
    assert result.contract["schema_version"] == "2.0"


@pytest.mark.parametrize("field", list(_binding()))
def test_every_verified_binding_field_is_required(field):
    context = _bound_context()
    context["verified_binding_refs"][0].pop(field)
    assert arc.process_context_errors(context)
    assert not _compile2(context).ok


@pytest.mark.parametrize("field", list(_bound_context()["data_requirements"][0]))
def test_every_data_requirement_field_is_required(field):
    context = _bound_context()
    context["data_requirements"][0].pop(field)
    assert arc.process_context_errors(context)


@pytest.mark.parametrize("field", ["binding_fingerprint", "snapshot_fingerprint", "checksum",
    "ownership_fingerprint", "usage_policy_fingerprint", "artifact_digest"])
def test_each_verified_evidence_digest_changes_runtime_semantics(field):
    context = _bound_context()
    before = _compile2(context)
    context["verified_binding_refs"][0][field] = "9" * 64
    after = _compile2(context)
    assert before.ok and after.ok
    assert before.fingerprint != after.fingerprint


def _dto_parity_cases():
    cases = [(_context(), True), (_bound_context(), True)]
    empty_sources = _context()
    empty_sources["sources"] = []  # DTO는 이를 허용한다. 실제 출처/권한은 서비스가 재검증한다.
    cases.append((empty_sources, True))
    long_id = _context()
    long_id["configuration_id"] = "x" * 200
    cases.append((long_id, True))
    for state in ("OWNER_CERTIFIED", "DEMO_CERTIFIED"):
        context = _bound_context()
        for ref in context["verified_binding_refs"]:
            ref["certification_state"] = state
            if state == "OWNER_CERTIFIED":
                ref.update(certification_subject_id="subject_b3", certification_subject_digest="4" * 64,
                           signing_policy_id="policy_b3", signing_policy_digest="5" * 64,
                           certified_use_kind="OPERATIONAL")
        cases.append((context, True))
    blocked = _bound_context()
    blocked["blockers"] = [{"reason_code": "DATA_USAGE_HOLD", "process_id": None,
        "requirement_key": None, "blocking_actions": ["GENERATE", "RUN", "RELEASE"],
        "next_action": "담당자에게 확인"}]
    cases.append((blocked, True))  # 형식 성공은 RUN 권한이 아니다.
    for mutation in ("float_version", "bool_version", "too_many_ids", "long_id", "duplicate_requirement",
                     "foreign_process", "orphan_binding", "duplicate_binding", "unsorted_binding",
                     "missing_owner_proof", "forged_source_proof", "unknown_action", "duplicate_action",
                     "binding_extra", "requirement_extra", "profile_extra", "pack_extra", "blocker_extra",
                     "bool_coercion", "wrong_digest", "digest_newline", "wrong_certification", "wrong_source_kind"):
        context = copy.deepcopy(blocked)
        ref = context["verified_binding_refs"][0]
        req = context["data_requirements"][0]
        if mutation == "float_version": context["schema_version"] = 1.0
        elif mutation == "bool_version": context["schema_version"] = True
        elif mutation == "too_many_ids": context["process_ids"] = [f"p{i:03}" for i in range(201)]
        elif mutation == "long_id": context["configuration_id"] = "x" * 201
        elif mutation == "duplicate_requirement": context["data_requirements"].append(copy.deepcopy(req))
        elif mutation == "foreign_process": req["process_id"] = "not_selected"
        elif mutation == "orphan_binding": ref["requirement_key"] = "no_requirement"
        elif mutation == "duplicate_binding": context["verified_binding_refs"].append(copy.deepcopy(ref))
        elif mutation == "unsorted_binding": context["verified_binding_refs"].reverse()
        elif mutation == "missing_owner_proof": ref["certification_state"] = "OWNER_CERTIFIED"
        elif mutation == "forged_source_proof": ref["signing_policy_id"] = "forged_policy"
        elif mutation == "unknown_action": context["permitted_actions"] = ["ADMIN"]
        elif mutation == "duplicate_action": context["permitted_actions"] *= 2
        elif mutation == "binding_extra": ref["approved"] = True
        elif mutation == "requirement_extra": req["approved"] = True
        elif mutation == "profile_extra": context["sources"][0]["approved"] = True
        elif mutation == "pack_extra": context["sources"][1]["approved"] = True
        elif mutation == "blocker_extra": context["blockers"][0]["approved"] = True
        elif mutation == "bool_coercion": req["mandatory"] = "true"
        elif mutation == "wrong_digest": ref["checksum"] = "g" * 64
        elif mutation == "digest_newline": ref["checksum"] = "a" * 64 + "\n"
        elif mutation == "wrong_certification": ref["certification_state"] = "CERTIFIED"
        elif mutation == "wrong_source_kind": context["sources"][0]["kind"] = "USER"
        cases.append((context, False))
    return cases


@pytest.mark.parametrize("context,valid", _dto_parity_cases())
def test_runtime_format_matches_james_strict_dto(context, valid):
    # 이 import는 main의 격리 회귀 실행에서만 한다. runtime 모듈은 ECM을 import하지 않는다.
    from core.enterprise_context.process_context import ProcessContextDTO
    from pydantic import ValidationError
    try:
        ProcessContextDTO.model_validate(context)
        accepted = True
    except ValidationError:
        accepted = False
    assert accepted is valid
    assert (not arc.process_context_errors(context)) is valid


def test_runtime_format_validation_does_not_import_ecm(monkeypatch):
    import builtins
    original = builtins.__import__
    def checked(name, *args, **kwargs):
        if name.startswith("core.enterprise_context"):
            raise AssertionError("runtime format validation must be IO-free")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", checked)
    assert not arc.process_context_errors(_bound_context())
