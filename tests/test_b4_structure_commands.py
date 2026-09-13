"""B4 구조 명령의 실제 parent FastAPI 회귀. 메인 격리 runner만 실행한다.

조직은 .invalid, ECM/DP는 기존 pytest tmp fixture다. 운영 DB/RAW/LLM/Host는 사용하지 않는다.
팩 시험의 설치 준비만 B2 서비스를 재사용하며 구조 제안·승인·조회는 실제 HTTP 경로다.
"""
import copy

import pytest

from core.enterprise_context.process_context import ProcessContextService
from core.enterprise_context.process_schema import ProcessError, fingerprint
from tests import org_seed as org
from tests.test_b1_process_configuration import client, headers, workspace  # noqa: F401
from tests.test_b2_installation import installation, _state, _prepared, _apply  # noqa: F401
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401

ROOT = "/api/v1/enterprise-context"


def _ok(response):
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
    return response.json()["data"]


def _error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["detail"]["reason_code"] == code
    assert "data" not in response.json()


def _query(w):
    return {k: getattr(w["boundary"], k) for k in ("context_root_id", "scope_node_id")}


def _node(pid, level, parent=""):
    return {"op": "ADD_NODE", "node": {"process_id": pid, "level": level, "label": pid,
            "parent_process_id": parent}}


def _resolved(w, profile_id=""):
    return _ok(w["client"].get(ROOT + "/process-configurations/resolved",
        params={**_query(w), "profile_id": profile_id}, headers=headers()))


def _body(w, commands, key="structure-edit"):
    base = _resolved(w)
    return {**_query(w), "commands": commands, "expected_head_version": base["head_version"],
            "base_profile_id": base["profile_id"], "base_fingerprint": base["digest"],
            "legacy_token": base["legacy_token"], "client_request_id": key, "reason": "구조 변경 검토"}


def _propose(w, commands, key="structure-edit", actor=org.MEMBER_A):
    return _ok(w["client"].post(ROOT + "/process-configurations/changes",
                                json=_body(w, commands, key), headers=headers(actor)))


def _review_body(draft):
    return {"expected_head_version": draft["base_head_version"], "draft_digest": draft["draft_digest"],
            "reason": "작성자와 다른 담당자의 구조 검토"}


def _approve(w, draft, actor=org.MANAGER_A):
    return _ok(w["client"].post(ROOT + "/process-changes/" + draft["change_id"] + "/approve",
                                json=_review_body(draft), headers=headers(actor)))


def _detail(w, draft):
    return _ok(w["client"].get(ROOT + "/process-changes/" + draft["change_id"],
                               params=_query(w), headers=headers(org.MANAGER_A)))


def _canonical(payload):
    return {p["process_id"]: p for p in payload["placements"] if p["kind"] == "CANONICAL"}


def _fixed(w, pid="plan"):
    return ProcessContextService(w["svc"].repo, w["store"]).build(boundary=w["boundary"],
        actor=org.MEMBER_A, context=w["context"], profile_id=_resolved(w)["profile_id"], process_ids=[pid])


def _revalidate(w, fixed):
    return ProcessContextService(w["svc"].repo, w["store"]).revalidate(fixed_context=fixed,
        actor=org.MEMBER_A, current_context=w["context"], for_action="DRAFT")


@pytest.fixture
def structure(client, installation):
    w = {**installation, "client": client}
    draft = _propose(w, [_node("purchase", "L1"), _node("sales", "L1"), _node("support", "L1"),
                        _node("plan", "L2", "purchase"), _node("order", "L2", "purchase")], "structure-base")
    approved = _approve(w, draft)
    return {**w, "approved": approved, "baseline": _resolved(w)["payload"]}


def test_ordered_add_usage_shortcut_batch_preserves_old_ids_and_base(structure):
    w = structure
    commands = [_node("new-parent", "L1"), _node("new-child", "L2", "new-parent"),
                {"op": "SET_USAGE", "process_id": "new-child", "enabled": False},
                {"op": "ADD_SHORTCUT", "process_id": "new-child", "parent_process_id": "sales"}]
    draft = _propose(w, commands)
    detail = _detail(w, draft)
    payload = detail["payload"]
    assert detail["base_payload"] == w["baseline"] == _resolved(w)["payload"]
    assert [v["command"] for v in payload["local_overrides"][-4:]] == commands
    prior, current = _canonical(w["baseline"]), _canonical(payload)
    assert {pid: current[pid] for pid in prior} == prior
    assert current["new-child"]["placement_id"] not in {p["placement_id"] for p in w["baseline"]["placements"]}
    assert current["new-child"]["placement_id"].startswith("placement_")
    assert len({p["placement_id"] for p in payload["placements"]}) == len(payload["placements"])
    new_node = next(n for n in payload["nodes"] if n["process_id"] == "new-child")
    assert new_node["enabled"] is False and new_node["origin"] == "CUSTOM"
    assert len([p for p in payload["placements"] if p["process_id"] == "new-child"]) == 2
    _approve(w, draft)
    assert _resolved(w)["payload"] == payload
    historical = _resolved(w, w["approved"]["profile_id"])
    assert historical["payload"] == w["baseline"] and historical["digest"] == w["approved"]["digest"]


def test_remove_shortcut_move_and_add_reverse_shortcut_preserves_canonical_id(structure):
    w = structure
    _approve(w, _propose(w, [{"op": "ADD_SHORTCUT", "process_id": "plan", "parent_process_id": "sales"}], "shortcut"))
    before = _resolved(w)["payload"]
    shortcut = next(p for p in before["placements"] if p["kind"] == "SHORTCUT")
    commands = [{"op": "REMOVE_SHORTCUT", "placement_id": shortcut["placement_id"]},
                {"op": "MOVE_NODE", "process_id": "plan", "parent_process_id": "sales"},
                {"op": "ADD_SHORTCUT", "process_id": "plan", "parent_process_id": "purchase"}]
    _approve(w, _propose(w, commands, "move-with-cleanup"))
    after = _resolved(w)["payload"]
    assert _canonical(after)["plan"] == {**_canonical(before)["plan"], "parent_process_id": "sales"}
    assert {n["process_id"] for n in before["nodes"]} == {n["process_id"] for n in after["nodes"]}
    assert shortcut["placement_id"] not in {p["placement_id"] for p in after["placements"]}
    assert next(p for p in after["placements"] if p["kind"] == "SHORTCUT")["parent_process_id"] == "purchase"


def test_batch_process_reference_requires_the_add_to_precede_usage(structure):
    w = structure
    add = _node("new-child", "L2", "purchase")
    usage = {"op": "SET_USAGE", "process_id": "new-child", "enabled": False}
    before = _state(w)
    response = w["client"].post(ROOT + "/process-configurations/changes", json=_body(w, [usage, add]), headers=headers())
    _error(response, 422, "PROCESS_COMMAND_INVALID")
    assert _state(w) == before
    draft = _propose(w, [add, usage])
    assert next(n for n in _detail(w, draft)["payload"]["nodes"] if n["process_id"] == "new-child")["enabled"] is False


@pytest.mark.parametrize("target", ["plan", "purchase"])
def test_usage_disabled_keeps_ids_but_blocks_selected_or_ancestor_context(structure, target):
    w = structure
    fixed = _fixed(w)
    _approve(w, _propose(w, [{"op": "SET_USAGE", "process_id": target, "enabled": False}]))
    after = _resolved(w)["payload"]
    assert _canonical(after) == _canonical(w["baseline"])
    assert {n["process_id"] for n in after["nodes"]} == {n["process_id"] for n in w["baseline"]["nodes"]}
    with pytest.raises(ProcessError) as raised:
        _revalidate(w, fixed)
    assert raised.value.status_code == 409 and raised.value.reason_code == "PROCESS_DISABLED"
    _approve(w, _propose(w, [{"op": "SET_USAGE", "process_id": target, "enabled": True}], "reenable"))
    assert _revalidate(w, fixed) == fixed


def test_parent_move_changes_meaning_not_identity_or_historical_payload(structure):
    w = structure
    fixed = _fixed(w)
    _approve(w, _propose(w, [{"op": "MOVE_NODE", "process_id": "plan", "parent_process_id": "sales"}]))
    current = _fixed(w)
    assert current["process_ids"] == fixed["process_ids"]
    assert current["process_semantic_fingerprint"] != fixed["process_semantic_fingerprint"]
    with pytest.raises(ProcessError) as raised:
        _revalidate(w, fixed)
    assert raised.value.status_code == 409 and raised.value.reason_code == "PROCESS_SEMANTIC_CONFLICT"
    assert _resolved(w, w["approved"]["profile_id"])["payload"] == w["baseline"]


def test_add_and_remove_shortcut_are_display_only_and_keep_canonical(structure):
    w = structure
    fixed = _fixed(w)
    _approve(w, _propose(w, [{"op": "ADD_SHORTCUT", "process_id": "plan", "parent_process_id": "sales"}]))
    added = _resolved(w)["payload"]
    assert _canonical(added) == _canonical(w["baseline"])
    assert _fixed(w)["process_semantic_fingerprint"] == fixed["process_semantic_fingerprint"]
    assert _revalidate(w, fixed) == fixed
    shortcut = next(p for p in added["placements"] if p["kind"] == "SHORTCUT")
    _approve(w, _propose(w, [{"op": "REMOVE_SHORTCUT", "placement_id": shortcut["placement_id"]}], "remove"))
    removed = _resolved(w)["payload"]
    assert removed["nodes"] == w["baseline"]["nodes"] and removed["placements"] == w["baseline"]["placements"]
    assert _revalidate(w, fixed) == fixed


@pytest.mark.parametrize("kind", ["SET_USAGE", "MOVE_NODE", "ADD_SHORTCUT"])
def test_real_pack_structure_commands_preserve_app_candidate_and_data_refs(client, installation, kind):
    w = {**installation, "client": client}
    original = _apply(w, _prepared(w))
    _approve(w, _propose(w, [_node("custom-parent", "L1")], "add-target"))
    before = _resolved(w)["payload"]
    pid = next(n["process_id"] for n in before["nodes"] if n["level"] == "L2")
    command = {"op": kind, "process_id": pid}
    command.update({"enabled": False} if kind == "SET_USAGE" else {"parent_process_id": "custom-parent"})
    dp = _state(w)["dp"]
    _approve(w, _propose(w, [command]))
    after = _resolved(w)["payload"]
    assert any(ref["kind"] == "BLUEPRINT_SUGGESTION" for ref in before["bindings"])
    for field in ("bindings", "relations", "template_sources", "migration_map"):
        assert after[field] == before[field]
    assert {p: v["placement_id"] for p, v in _canonical(after).items()} == {p: v["placement_id"] for p, v in _canonical(before).items()}
    assert _resolved(w, original["profile_id"])["digest"] == original["digest"]
    assert _state(w)["dp"] == dp


@pytest.mark.parametrize("command", [
    {"op": "MOVE_NODE", "process_id": "plan", "parent_process_id": "missing"},
    {"op": "MOVE_NODE", "process_id": "plan", "parent_process_id": "order"},
    {"op": "MOVE_NODE", "process_id": "purchase", "parent_process_id": "sales"},
    {"op": "ADD_SHORTCUT", "process_id": "plan", "parent_process_id": "purchase"},
    {"op": "ADD_SHORTCUT", "process_id": "purchase", "parent_process_id": "sales"},
    {"op": "ADD_SHORTCUT", "process_id": "plan", "parent_process_id": "missing"},
    {"op": "SET_USAGE", "process_id": "plan", "enabled": "false"},
    {"op": "SET_USAGE", "process_id": "plan", "enabled": 1},
    {"op": "ADD_NODE", "node": {"process_id": "orphan", "level": "L2", "label": "잘못된 부모", "parent_process_id": "missing"}},
])
def test_invalid_parent_shortcut_or_usage_returns_422_and_rolls_back_batch(structure, command):
    w = structure
    before = _state(w)
    body = _body(w, [{"op": "SET_NOTE", "process_id": "plan", "note": "실패하면 저장 금지"}, command])
    response = w["client"].post(ROOT + "/process-configurations/changes", json=body, headers=headers())
    _error(response, 422, "PROCESS_DOCUMENT_INVALID")
    assert _state(w) == before


@pytest.mark.parametrize("case", ["missing_process", "remove_canonical", "temporary_placement", "source_spoof"])
def test_client_cannot_inject_placement_or_source_refs_or_remove_canonical(structure, case):
    w = structure
    if case == "missing_process":
        command = {"op": "SET_USAGE", "process_id": "missing", "enabled": False}
    elif case == "remove_canonical":
        command = {"op": "REMOVE_SHORTCUT", "placement_id": _canonical(w["baseline"])["plan"]["placement_id"]}
    else:
        command = _node("new-child", "L2", "purchase")
        command["node"].update({"placement_id": "ui-temp-placement"} if case == "temporary_placement"
                               else {"source_ref": "client-artifact", "origin": "STANDARD"})
    before = _state(w)
    _error(w["client"].post(ROOT + "/process-configurations/changes", json=_body(w, [command]), headers=headers()),
           422, "PROCESS_COMMAND_INVALID")
    assert _state(w) == before


def test_structural_change_still_requires_a_distinct_qualified_approver(structure):
    w = structure
    draft = _propose(w, [{"op": "SET_USAGE", "process_id": "plan", "enabled": False}], actor=org.MANAGER_A)
    path = ROOT + "/process-changes/" + draft["change_id"] + "/approve"
    _error(w["client"].post(path, json=_review_body(draft), headers=headers(org.MANAGER_A)),
           403, "PROCESS_DISTINCT_REVIEWER_REQUIRED")
    assert _resolved(w)["profile_id"] == w["approved"]["profile_id"]
    result = _approve(w, draft, org.MANAGER_ROOT)
    assert _resolved(w)["profile_id"] == result["profile_id"]


@pytest.mark.parametrize("case", ["head", "digest", "idempotency"])
def test_structure_conflicts_preserve_original_draft_and_approved_head(structure, case):
    w = structure
    body = _body(w, [{"op": "MOVE_NODE", "process_id": "plan", "parent_process_id": "sales"}])
    draft = _ok(w["client"].post(ROOT + "/process-configurations/changes", json=body, headers=headers()))
    original = _detail(w, draft)
    if case == "head":
        _approve(w, _propose(w, [{"op": "SET_USAGE", "process_id": "order", "enabled": False}], "winner"))
    before = _state(w)
    if case == "idempotency":
        changed = copy.deepcopy(body)
        changed["commands"][0]["parent_process_id"] = "support"
        response = w["client"].post(ROOT + "/process-configurations/changes", json=changed, headers=headers())
        code = "PROCESS_IDEMPOTENCY_CONFLICT"
    else:
        review = _review_body(draft)
        if case == "digest":
            review["draft_digest"] = "0" * 64
        response = w["client"].post(ROOT + "/process-changes/" + draft["change_id"] + "/approve", json=review, headers=headers(org.MANAGER_A))
        code = "PROCESS_HEAD_CONFLICT" if case == "head" else "PROCESS_DIGEST_CONFLICT"
    _error(response, 409, code)
    assert _detail(w, draft)["payload"] == original["payload"]
    assert fingerprint(original["payload"]) == draft["draft_digest"]
    assert _state(w) == before
