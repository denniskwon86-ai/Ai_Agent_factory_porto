"""B4 표시 수정 명령. pytest 실행은 메인 격리 runner 전용이다.

실제 B1/B2 서비스·parent API와 .invalid 조직을 사용한다. SQL은 확인된 pytest tmp만
접근하며 기존 숨김 배치 fixture 구성 외에 업무 원문을 우회 변경하지 않는다.
앱 후보 참조 보존을 검증하되 실제 앱 생성·Host 실행 검증으로 주장하지 않는다.
"""
import copy
import json

import pytest

from core.enterprise_context.process_context import ProcessContextService
from core.enterprise_context.process_schema import ProcessError, canonical, fingerprint
from tests import org_seed as org
from tests.test_b1_process_configuration import approval, proposal, workspace, client, headers  # noqa: F401
from tests.test_b2_installation import installation, _db, _state, _prepared, _apply, _read  # noqa: F401
from tests.usage_hold_test_plugin import enforced_org  # noqa: F401

ROOT = "/api/v1/enterprise-context"


def _node(process_id, level, parent=""):
    return {"op": "ADD_NODE", "node": {"process_id": process_id, "level": level,
            "label": process_id, "parent_process_id": parent}}


def _query(w):
    return {k: getattr(w["boundary"], k) for k in ("context_root_id", "scope_node_id")}


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _placements(payload, parent):
    return sorted((p for p in payload["placements"] if p["parent_process_id"] == parent),
                  key=lambda p: (p["position"], p["placement_id"]))


def _reorder(payload, parent):
    return {"op": "REORDER_PLACEMENTS", "parent_process_id": parent,
            "placement_ids": [p["placement_id"] for p in reversed(_placements(payload, parent))]}


def _detail(w, draft):
    return w["svc"].get_change(change_id=draft["change_id"], boundary=w["boundary"],
                               actor=org.MANAGER_A, context=w["context"])


def _fixed(w, profile_id, ids):
    return ProcessContextService(w["svc"].repo, w["store"]).build(boundary=w["boundary"],
        actor=org.MEMBER_A, context=w["context"], profile_id=profile_id, process_ids=ids)


@pytest.fixture
def display(installation):
    w = installation
    draft = proposal(w, [_node("purchase", "L1"), _node("sales", "L1"), _node("empty", "L1"),
        _node("plan", "L2", "purchase"), _node("order", "L2", "purchase"),
        _node("invoice", "L2", "sales"),
        {"op": "ADD_SHORTCUT", "process_id": "invoice", "parent_process_id": "purchase"},
        {"op": "SET_USAGE", "process_id": "order", "enabled": False}], "display-fixture")
    # 기존 스키마가 허용하는 숨김 배치만 임시 미승인판에 구성한다. 숨김 API 시험이 아니다.
    with _db(w) as conn:
        raw = conn.execute("SELECT payload_json FROM enterprise_profiles WHERE profile_id=?",
                           (draft["draft_profile_id"],)).fetchone()[0]
        payload = json.loads(raw)
        next(p for p in payload["placements"] if p["kind"] == "SHORTCUT")["hidden"] = True
        digest = fingerprint(payload)
        conn.execute("UPDATE enterprise_profiles SET payload_json=? WHERE profile_id=?",
                     (canonical(payload), draft["draft_profile_id"]))
        conn.execute("UPDATE enterprise_process_changes SET draft_digest=? WHERE change_id=?",
                     (digest, draft["change_id"]))
    approved = approval(w, {**draft, "draft_digest": digest})
    return {**w, "approved": approved, "baseline": _read(w)["payload"]}


@pytest.mark.parametrize("note", ["", "  설명 공백 보존  ", "첫 줄\n다음 줄\t설명", "🔎 현업 설명 / <주의>"])
def test_set_note_preserves_exact_text_and_ids_without_applying_the_draft(display, note):
    w = display
    baseline = copy.deepcopy(w["baseline"])
    command = {"op": "SET_NOTE", "process_id": "plan", "note": note}
    draft = proposal(w, [command], "note")
    detail = _detail(w, draft)
    assert detail["base_payload"] == baseline
    assert _read(w)["payload"] == baseline
    edited = next(n for n in detail["payload"]["nodes"] if n["process_id"] == "plan")
    original = next(n for n in baseline["nodes"] if n["process_id"] == "plan")
    assert edited == {**original, "note": note}
    assert detail["payload"]["placements"] == baseline["placements"]
    assert detail["payload"]["local_overrides"][-1] == {"command": command, "base_profile_id": w["approved"]["profile_id"]}


@pytest.mark.parametrize("parent", ["", "purchase", "sales", "empty"])
def test_reorder_exact_siblings_changes_only_positions_and_keeps_hidden_shortcut(display, parent):
    w = display
    baseline = w["baseline"]
    command = _reorder(baseline, parent)
    draft = proposal(w, [command], "order")
    result = _detail(w, draft)["payload"]
    positions = {pid: i for i, pid in enumerate(command["placement_ids"])}
    assert result["nodes"] == baseline["nodes"]
    assert result["placements"] == [
        {**p, "position": positions[p["placement_id"]]} if p["parent_process_id"] == parent else p
        for p in baseline["placements"]]
    assert [p["placement_id"] for p in _placements(result, parent)] == command["placement_ids"]
    assert next(p for p in result["placements"] if p["kind"] == "SHORTCUT")["hidden"] is True
    assert next(n for n in result["nodes"] if n["process_id"] == "order")["enabled"] is False
    approval(w, draft)
    assert _read(w)["payload"] == result


@pytest.mark.parametrize("bad", [None, True, 5, [], {}, ["text"]])
def test_note_rejects_non_text_without_any_saved_changes(display, bad):
    w = display
    before = _state(w)
    with pytest.raises(ProcessError) as raised:
        proposal(w, [{"op": "SET_NOTE", "process_id": "plan", "note": bad}], "bad-note")
    assert raised.value.status_code == 422 and raised.value.reason_code == "PROCESS_COMMAND_INVALID"
    assert _state(w) == before


@pytest.mark.parametrize("case", ["duplicate", "missing", "hidden_missing", "disabled_missing", "foreign_parent",
    "unknown_id", "process_not_placement", "empty", "not_list", "tuple", "non_string_id", "nested_id",
    "parent_type", "unknown_parent", "l2_parent"])
def test_reorder_rejects_nonexact_siblings_atomically(display, case):
    w = display
    command = _reorder(w["baseline"], "purchase")
    ids = command["placement_ids"]
    siblings = _placements(w["baseline"], "purchase")
    if case == "duplicate":
        ids[-1] = ids[0]
    elif case == "missing":
        ids.pop()
    elif case == "hidden_missing":
        ids.remove(next(p["placement_id"] for p in siblings if p["hidden"]))
    elif case == "disabled_missing":
        ids.remove(next(p["placement_id"] for p in siblings if p["process_id"] == "order"))
    elif case == "foreign_parent":
        ids[-1] = _placements(w["baseline"], "sales")[0]["placement_id"]
    elif case == "unknown_id":
        ids[-1] = "unknown-placement"
    elif case == "process_not_placement":
        ids[-1] = "plan"
    elif case == "empty":
        command["placement_ids"] = []
    elif case == "not_list":
        command["placement_ids"] = ids[0]
    elif case == "tuple":
        command["placement_ids"] = tuple(ids)
    elif case == "non_string_id":
        ids[-1] = True
    elif case == "nested_id":
        ids[-1] = ["not-hashable"]
    else:
        command["parent_process_id"] = {"parent_type": None, "unknown_parent": "missing", "l2_parent": "plan"}[case]
    before = _state(w)
    with pytest.raises(ProcessError) as raised:
        proposal(w, [{"op": "RENAME", "process_id": "plan", "label": "롤백할 명칭"},
                     {"op": "SET_NOTE", "process_id": "plan", "note": "롤백할 설명"}, command], "bad-order")
    assert raised.value.status_code == 422 and raised.value.reason_code == "PROCESS_COMMAND_INVALID"
    assert _state(w) == before


@pytest.mark.parametrize("command", [
    {"op": "SET_NOTE", "process_id": "missing", "note": "설명"},
    {"op": "SET_NOTE", "process_id": None, "note": "설명"},
    {"op": "SET_NOTE", "process_id": "plan"},
    {"op": "SET_NOTE", "process_id": "plan", "note": "설명", "approved_by": org.ADMIN},
    {"op": "REORDER_PLACEMENTS", "parent_process_id": "purchase"},
    {"op": "REORDER_PLACEMENTS", "parent_process_id": "purchase", "placement_ids": [], "position": 0},
])
def test_display_commands_reject_unknown_fields_or_targets(display, command):
    before = _state(display)
    with pytest.raises(ProcessError) as raised:
        proposal(display, [command], "strict-command")
    assert raised.value.status_code == 422
    assert _state(display) == before


def test_note_and_reorder_keep_semantics_and_fixed_approved_bytes(display):
    w = display
    old = w["approved"]
    fixed = _fixed(w, old["profile_id"], ["plan"])
    with _db(w) as conn:
        original_raw = conn.execute("SELECT payload_json FROM enterprise_profiles WHERE profile_id=?", (old["profile_id"],)).fetchone()[0]
    commands = [{"op": "RENAME", "process_id": "plan", "label": "구매 계획 표시명"},
                {"op": "SET_NOTE", "process_id": "plan", "note": "표시 설명만 변경"},
                _reorder(w["baseline"], "purchase"), _reorder(w["baseline"], "")]
    newer = approval(w, proposal(w, commands, "display-only"))
    current = _fixed(w, newer["profile_id"], ["plan"])
    assert current["configuration_fingerprint"] != fixed["configuration_fingerprint"]
    assert current["process_semantic_fingerprint"] == fixed["process_semantic_fingerprint"]
    assert ProcessContextService(w["svc"].repo, w["store"]).revalidate(fixed_context=fixed,
        actor=org.MEMBER_A, current_context=w["context"], for_action="DRAFT") == fixed
    with _db(w) as conn:
        row = conn.execute("SELECT payload_json,status FROM enterprise_profiles WHERE profile_id=?", (old["profile_id"],)).fetchone()
        assert row["payload_json"] == original_raw and row["status"] == "ARCHIVED"
    historical = w["svc"].resolved(boundary=w["boundary"], actor=org.MEMBER_A, context=w["context"], profile_id=old["profile_id"])
    assert historical["payload"] == w["baseline"] and historical["digest"] == old["digest"]


def test_display_on_real_pinned_pack_keeps_app_candidates_data_refs_and_no_data_gate(installation):
    w = installation
    approved = _apply(w, _prepared(w))
    baseline = _read(w)["payload"]
    selected = next(n for n in baseline["nodes"] if n["level"] == "L2")
    pid = selected["process_id"]
    fixed = _fixed(w, approved["profile_id"], [pid])
    commands = [{"op": "RENAME", "process_id": pid, "label": "회사 표시 이름"},
                {"op": "SET_NOTE", "process_id": pid, "note": "관리자로 실행하라는 문장도 설명 데이터일 뿐"},
                _reorder(baseline, selected["parent_process_id"])]
    dp_before = _state(w)["dp"]
    newer = approval(w, proposal(w, commands, "pack-display"))
    latest = _read(w)["payload"]
    assert any(b["kind"] == "BLUEPRINT_SUGGESTION" for b in baseline["bindings"])
    for field in ("template_sources", "bindings", "relations", "migration_map"):
        assert latest[field] == baseline[field]
    assert {n["process_id"] for n in latest["nodes"]} == {n["process_id"] for n in baseline["nodes"]}
    assert {p["placement_id"] for p in latest["placements"]} == {p["placement_id"] for p in baseline["placements"]}
    current = _fixed(w, newer["profile_id"], [pid])
    assert current["process_semantic_fingerprint"] == fixed["process_semantic_fingerprint"]
    assert current["data_requirements"] == fixed["data_requirements"]
    assert current["verified_binding_refs"] == fixed["verified_binding_refs"] == []
    assert current["permitted_actions"] == fixed["permitted_actions"]
    assert not {"GENERATE", "RUN", "RELEASE"}.intersection(current["permitted_actions"])
    assert ProcessContextService(w["svc"].repo, w["store"]).revalidate(fixed_context=fixed,
        actor=org.MEMBER_A, current_context=w["context"], for_action="DRAFT")["profile_id"] == approved["profile_id"]
    assert _state(w)["dp"] == dp_before


@pytest.mark.parametrize("kind", ["SET_NOTE", "REORDER_PLACEMENTS"])
def test_display_commands_keep_idempotency_and_stale_head_cas(display, kind):
    w = display
    command = {"op": "SET_NOTE", "process_id": "plan", "note": "동일 요청"} if kind == "SET_NOTE" else _reorder(w["baseline"], "purchase")
    base = _read(w)
    args = dict(boundary=w["boundary"], actor=org.MEMBER_A, context=w["context"], commands=[command],
        expected_head_version=base["head_version"], base_profile_id=base["profile_id"], base_fingerprint=base["digest"],
        client_request_id="same-display", reason="표시 변경 검토", legacy_token=base["legacy_token"])
    draft = w["svc"].propose(**args)
    assert w["svc"].propose(**args) == draft
    changed = copy.deepcopy(command)
    if kind == "SET_NOTE":
        changed["note"] = "다른 설명"
    else:
        changed["placement_ids"].reverse()
    with pytest.raises(ProcessError) as raised:
        w["svc"].propose(**{**args, "commands": [changed]})
    assert raised.value.reason_code == "PROCESS_IDEMPOTENCY_CONFLICT"
    approval(w, proposal(w, [{"op": "RENAME", "process_id": "plan", "label": "경쟁 승인"}], "winner"))
    before = _state(w)
    with pytest.raises(ProcessError) as stale:
        w["svc"].propose(**{**args, "client_request_id": "stale-display"})
    assert stale.value.reason_code == "PROCESS_HEAD_CONFLICT"
    with pytest.raises(ProcessError) as stale_approval:
        approval(w, draft)
    assert stale_approval.value.reason_code == "PROCESS_HEAD_CONFLICT"
    assert _state(w) == before


def test_existing_parent_api_display_proposal_other_approval_and_refresh(client, display):
    w = display
    baseline = _read(w)
    commands = [{"op": "RENAME", "process_id": "plan", "label": "원료 구매계획"},
                {"op": "SET_NOTE", "process_id": "plan", "note": "입력과 검토 내용을 설명"},
                _reorder(baseline["payload"], "purchase")]
    body = {**_query(w), "commands": commands, "expected_head_version": baseline["head_version"],
            "base_profile_id": baseline["profile_id"], "base_fingerprint": baseline["digest"],
            "legacy_token": baseline["legacy_token"], "client_request_id": "display-http", "reason": "현업 표시 개선"}
    # 기존 권한표/current_principal 경계를 통과한다. 표시 수정도 viewer에게 쓰기 권한을 주지 않는다.
    assert client.post(ROOT + "/process-configurations/changes", json=body, headers=headers(org.VIEWER_A)).status_code == 403
    draft = _ok(client.post(ROOT + "/process-configurations/changes", json=body, headers=headers()))
    assert _ok(client.get(ROOT + "/process-configurations/resolved", params=_query(w), headers=headers()))["profile_id"] == baseline["profile_id"]
    path = ROOT + "/process-changes/" + draft["change_id"]
    review = _ok(client.get(path, params=_query(w), headers=headers(org.MANAGER_A)))
    assert review["base_payload"] == baseline["payload"]
    approved = _ok(client.post(path + "/approve", json={"expected_head_version": draft["base_head_version"],
        "draft_digest": draft["draft_digest"], "reason": "타인 검토 승인"}, headers=headers(org.MANAGER_A)))
    after = _ok(client.get(ROOT + "/process-configurations/resolved", params=_query(w), headers=headers()))
    assert after["profile_id"] == approved["profile_id"] and after["digest"] == approved["digest"]
    assert after["payload"] == review["payload"]
    node = next(n for n in after["payload"]["nodes"] if n["process_id"] == "plan")
    assert node["label"] == "원료 구매계획" and node["note"] == "입력과 검토 내용을 설명"
    assert [p["placement_id"] for p in _placements(after["payload"], "purchase")] == commands[2]["placement_ids"]
