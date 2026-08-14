"""[I-4 1단계] App Runtime Contract 와 HostContractCompiler 회귀.

지키는 것 넷:

1. **판정은 결정표가 한다** — LLM 이 적어 온 상태를 쓰지 않는다.
2. **모르는 요구를 자동 허용하지 않는다** — 결정표에 없으면 `NOT_YET_SUPPORTED`.
3. **금지 항목은 개발 요청이 되지 않는다** — `PROHIBITED` 에 `REQUEST_HOST_FEATURE` 불가.
4. **지문이 바뀌면 승인은 초기화된다** — 문구를 다듬은 것은 바뀐 것이 아니다.
"""
import copy

import pytest

from core import app_manifest, app_runtime_contract as arc
from core.host_contract_compiler import compile_contract


def _draft(**over):
    d = {
        "app_class": "departmental",
        "capability_intents": [
            {"capability": "app_data.read", "requirement_ref": "R-1"},
            {"capability": "app_data.create", "requirement_ref": "R-2"},
        ],
        "datasets": [{
            "name": "arrivals", "label": "입고", "purpose": "자재 입고를 기록한다",
            "allowed_actions": ["read", "create"],
            "ontology_entity_type": "ArrivalEvent",
            "fields": [
                {"name": "qty", "type": "number", "required": True,
                 "classification": "INTERNAL", "semantic_role": "quantity", "unit": "ton"},
                {"name": "note", "type": "text", "required": False,
                 "classification": "INTERNAL"},
            ],
        }],
    }
    d.update(over)
    return d


def _compiled(**over):
    r = compile_contract(_draft(**over), project_id="P1", task_id="T1")
    assert r.ok, r.errors
    return r.contract


# ── 1. 결정표 ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("cap,want", [
    ("app_data.read", arc.SUPPORTED),
    ("app_data.delete", arc.SUPPORTED),
    ("app_data.aggregate", arc.CONDITIONAL),
    ("auth.local_login", arc.PROHIBITED),
    ("api.direct_call", arc.PROHIBITED),
    ("storage.credentials", arc.PROHIBITED),
    ("file.upload", arc.NOT_YET_SUPPORTED),
    ("network.external_api", arc.HOST_SERVICE_REQUIRED),
    ("compute.simulation", arc.HOST_SERVICE_REQUIRED),
])
def test_decision_table(cap, want):
    status, reason = arc.decide(cap)
    assert status == want
    assert reason  # 근거 없는 판정은 사용자에게 설명할 수 없다


@pytest.mark.parametrize("unknown", ["quantum.teleport", "", None, "app_data", "   "])
def test_unknown_capability_is_not_auto_allowed(unknown):
    """⚠️⚠️ 「모르니까 되겠지」가 곧 통제 없는 기능이다."""
    status, _ = arc.decide(unknown)
    assert status == arc.NOT_YET_SUPPORTED
    assert not arc.is_buildable(status)


def test_decision_is_deterministic():
    """★ 같은 요구에 어제와 오늘의 답이 다르면 그 차이는 릴리스가 나온 뒤에야 드러난다."""
    for cap in list(arc.CAPABILITY_DECISION) + ["모르는것"]:
        assert arc.decide(cap) == arc.decide(cap)


def test_llm_supplied_status_is_ignored():
    """LLM 이 `PROHIBITED` 를 `SUPPORTED` 라고 적어 와도 계약은 그것을 쓰지 않는다."""
    d = _draft(capability_intents=[
        {"capability": "auth.local_login", "requirement_ref": "R-9", "status": "SUPPORTED"}])
    r = compile_contract(d, project_id="P1")
    got = [i for i in r.contract["capability_intents"] if i["capability"] == "auth.local_login"]
    assert got and got[0]["status"] == arc.PROHIBITED


# ── 2. 상태별 사용자 결정 ─────────────────────────────────────────────────
def test_prohibited_cannot_become_a_feature_request():
    """★★★ 허용하면 금지 정책이 개발 요청으로 변질된다 —
    「요청해 뒀으니 언젠가 열리겠지」가 되고, 그 사이 사용자는 우회로를 쓴다."""
    assert arc.allowed_decisions(arc.PROHIBITED) == (arc.REDUCE,)
    assert arc.REQUEST_HOST_FEATURE not in arc.allowed_decisions(arc.PROHIBITED)
    assert arc.WAIT not in arc.allowed_decisions(arc.PROHIBITED)

    d = _draft(capability_intents=[{"capability": "auth.local_login", "requirement_ref": "R-9",
                                    "user_decision": arc.REQUEST_HOST_FEATURE}])
    r = compile_contract(d, project_id="P1")
    assert not r.ok
    assert any("REQUEST_HOST_FEATURE" in e for e in r.errors)
    assert r.status == "DRAFT" and r.fingerprint == ""   # 승인할 대상 자체가 없다


def test_stored_contract_with_forbidden_decision_is_invalid():
    """★ 컴파일러만 믿지 않는다.

    ⚠️ 계약은 파일로도 오고(`release.json` 스냅샷·workspace 원문) 손으로 고쳐질 수도 있다.
      검사가 컴파일 경로에만 있으면 그 경로를 지나지 않은 계약은 아무것도 통과하지 못한 채
      통과한다."""
    c = _compiled()
    c["capability_intents"].append({
        "intent_id": "intent_x", "requirement_ref": "R-9", "capability": "auth.local_login",
        "status": arc.PROHIBITED, "reason": "회사 권한 체계 밖", "user_decision": arc.REQUEST_HOST_FEATURE})
    c["semantic_fingerprint"] = arc.semantic_fingerprint(c)   # 지문은 맞춰 둔다
    errs = arc.validate(c)
    assert any("REQUEST_HOST_FEATURE" in e for e in errs), errs

    # 미지원 목록 쪽도 같은 규칙이 걸린다.
    c2 = _compiled()
    c2["unsupported_requirements"] = [{"requirement_ref": "R-9", "status": arc.PROHIBITED,
                                       "user_decision": arc.WAIT}]
    assert any("WAIT" in e for e in arc.validate(c2))


def test_stored_contract_with_decision_on_supported_is_invalid():
    c = _compiled()
    c["capability_intents"][0]["user_decision"] = arc.REDUCE
    c["semantic_fingerprint"] = arc.semantic_fingerprint(c)
    assert any("고를 것이 없습니다" in e for e in arc.validate(c))


def test_not_yet_supported_may_wait_but_not_request():
    assert set(arc.allowed_decisions(arc.NOT_YET_SUPPORTED)) == {arc.REDUCE, arc.WAIT}


def test_host_service_required_may_request():
    assert set(arc.allowed_decisions(arc.HOST_SERVICE_REQUIRED)) == {
        arc.REDUCE, arc.WAIT, arc.REQUEST_HOST_FEATURE}


def test_supported_requirement_has_nothing_to_choose():
    d = _draft()
    d["capability_intents"][0]["user_decision"] = arc.WAIT
    r = compile_contract(d, project_id="P1")
    assert not r.ok and any("고를 것이 없습니다" in e for e in r.errors)


def test_undecided_requirement_blocks_compilation():
    """⚠️ 결정이 없는 것을 계약에 실으면 「사용자가 대기를 골랐다」와 「아직 아무도 안 봤다」가
    같은 모양이 된다."""
    d = _draft(capability_intents=[{"capability": "file.upload", "requirement_ref": "R-5"}])
    r = compile_contract(d, project_id="P1")
    assert not r.ok
    assert r.pending_decisions and r.pending_decisions[0]["capability"] == "file.upload"
    assert r.pending_decisions[0]["choices"] == [arc.REDUCE, arc.WAIT]
    assert r.contract["unsupported_requirements"] == []


def test_decided_requirement_lands_in_unsupported_list():
    d = _draft(capability_intents=[
        {"capability": "app_data.read", "requirement_ref": "R-1"},
        {"capability": "file.upload", "requirement_ref": "R-5", "user_decision": arc.WAIT},
    ])
    r = compile_contract(d, project_id="P1")
    assert r.ok, r.errors
    assert r.contract["unsupported_requirements"] == [
        {"requirement_ref": "R-5", "status": arc.NOT_YET_SUPPORTED,
         "reason": arc.CAPABILITY_DECISION["file.upload"][1], "user_decision": arc.WAIT}]


def test_one_requirement_may_hit_several_walls():
    """⚠️ 하나의 요구가 여러 이유로 막힐 수 있다 — 「외부에서 파일을 받아 저장한다」는
    `file.upload`(지원 대기)와 `network.external_api`(Host 기능 필요) 둘 다에 걸린다.

    요구 번호로만 묶어 버리면 그중 하나가 사라지고, 사용자는 **하나만 해결하면 되는 줄 안다.**"""
    d = _draft(capability_intents=[
        {"capability": "app_data.read", "requirement_ref": "R-1"},
        {"capability": "file.upload", "requirement_ref": "R-7", "user_decision": arc.WAIT},
        {"capability": "network.external_api", "requirement_ref": "R-7",
         "user_decision": arc.REQUEST_HOST_FEATURE},
    ])
    r = compile_contract(d, project_id="P1")
    assert r.ok, r.errors
    got = {(u["status"], u["user_decision"]) for u in r.contract["unsupported_requirements"]}
    assert got == {(arc.NOT_YET_SUPPORTED, arc.WAIT),
                   (arc.HOST_SERVICE_REQUIRED, arc.REQUEST_HOST_FEATURE)}


def test_identical_requirements_are_deduplicated():
    # 같은 요구·같은 상태·같은 결정이 두 번 오면 한 줄이다(화면에 같은 말이 두 번 뜨지 않는다).
    d = _draft(capability_intents=[
        {"capability": "app_data.read", "requirement_ref": "R-1"},
        {"capability": "file.upload", "requirement_ref": "R-7", "user_decision": arc.WAIT},
        {"capability": "job.background", "requirement_ref": "R-7", "user_decision": arc.WAIT},
    ])
    r = compile_contract(d, project_id="P1")
    assert r.ok, r.errors
    assert len(r.contract["unsupported_requirements"]) == 1


# ── 3. 의미 지문 ──────────────────────────────────────────────────────────
def test_fingerprint_is_stable_and_16_hex():
    c = _compiled()
    fp = c["semantic_fingerprint"]
    assert len(fp) == 16 and all(ch in "0123456789abcdef" for ch in fp)
    assert arc.semantic_fingerprint(c) == fp


def test_wording_changes_do_not_move_the_fingerprint():
    """⚠️ 문구를 다듬었다고 재승인을 요구하면 사람이 게이트를 습관으로 통과시킨다."""
    base = _compiled()
    d = _draft()
    d["datasets"][0]["label"] = "입고 기록"
    d["datasets"][0]["purpose"] = "표현만 바꾼 설명"
    assert compile_contract(d, project_id="P1", task_id="T1").fingerprint == \
        base["semantic_fingerprint"]


@pytest.mark.parametrize("mutate", [
    lambda d: d["datasets"][0]["allowed_actions"].append("delete"),
    lambda d: d["datasets"][0].__setitem__("name", "arrivals2"),
    lambda d: d["datasets"][0]["fields"][0].__setitem__("unit", "kg"),
    lambda d: d["datasets"][0]["fields"][0].__setitem__("classification", "CONFIDENTIAL"),
    lambda d: d["datasets"][0]["fields"][0].__setitem__("required", False),
    lambda d: d["datasets"][0].__setitem__("ontology_entity_type", "Other"),
    lambda d: d.__setitem__("app_class", "enterprise"),
    lambda d: d["datasets"][0]["fields"].append(
        {"name": "extra", "type": "string", "required": False, "classification": "PUBLIC"}),
])
def test_meaning_changes_move_the_fingerprint(mutate):
    base = _compiled()["semantic_fingerprint"]
    d = _draft()
    mutate(d)
    r = compile_contract(d, project_id="P1", task_id="T1")
    assert r.fingerprint != base, "의미가 바뀌었는데 지문이 그대로다 — 게이트가 열리지 않는다"


def test_fingerprint_ignores_key_order():
    c = _compiled()
    shuffled = {k: c[k] for k in reversed(list(c))}
    assert arc.semantic_fingerprint(shuffled) == c["semantic_fingerprint"]


def test_tampered_fingerprint_is_caught():
    """지문이 내용을 따라가지 않으면 재승인 판정 자체가 거짓이 된다."""
    c = _compiled()
    c["semantic_fingerprint"] = "0" * 16
    errs = arc.validate(c)
    assert any("semantic_fingerprint" in e for e in errs)


def test_contract_id_is_deterministic():
    a = arc.contract_id_for("P1", "T1")
    assert a == arc.contract_id_for("P1", "T1") != arc.contract_id_for("P1", "T2")
    import re
    assert re.match(arc.CONTRACT_ID_PATTERN, a)


# ── 4. 승인 승계와 초기화 ─────────────────────────────────────────────────
def _approved_previous():
    c = _compiled()
    c["approval"] = {"status": "APPROVED", "approved_by": "hikwon@lsmnm.com",
                     "approved_at": "2026-08-15T00:00:00Z", "decision_ledger_id": "L1"}
    c["status"] = "APPROVED"
    return c


def test_same_fingerprint_keeps_approval_and_revision():
    prev = _approved_previous()
    r = compile_contract(_draft(), project_id="P1", task_id="T1", previous=prev)
    assert r.ok and not r.fingerprint_changed
    assert r.contract["approval"]["status"] == "APPROVED"
    assert r.contract["revision"] == prev["revision"]


def test_changed_fingerprint_resets_approval_and_bumps_revision():
    """★★★ 이전 승인을 새 지문에 끌어다 쓰면 게이트는 아무것도 지키지 않는다."""
    prev = _approved_previous()
    d = _draft()
    d["datasets"][0]["allowed_actions"].append("delete")
    r = compile_contract(d, project_id="P1", task_id="T1", previous=prev)
    assert r.ok and r.fingerprint_changed
    assert r.contract["approval"] == {"status": "PENDING"}
    assert r.contract["status"] == "COMPILED"
    assert r.contract["revision"] == prev["revision"] + 1


def test_approval_without_evidence_is_rejected():
    c = _compiled()
    c["approval"] = {"status": "APPROVED"}
    errs = arc.validate(c)
    assert any("approved_by" in e for e in errs)
    assert any("decision_ledger_id" in e for e in errs)


# ── 5. 조건부 규칙 (스키마만으로는 못 잡는 것) ────────────────────────────
def test_quantity_without_unit_is_rejected():
    """⚠️ 단위 없는 수량은 나중에 합산될 때 조용히 틀린다(톤과 개를 더한다)."""
    d = _draft()
    d["datasets"][0]["fields"][0].pop("unit")
    r = compile_contract(d, project_id="P1")
    assert not r.ok and any("unit" in e for e in r.errors)


def test_amount_role_also_requires_unit():
    d = _draft()
    d["datasets"][0]["fields"][0]["semantic_role"] = "amount"
    d["datasets"][0]["fields"][0].pop("unit")
    assert not compile_contract(d, project_id="P1").ok


def test_non_quantity_roles_do_not_require_unit():
    d = _draft()
    d["datasets"][0]["fields"][0]["semantic_role"] = "status"
    d["datasets"][0]["fields"][0]["type"] = "string"
    d["datasets"][0]["fields"][0].pop("unit")
    assert compile_contract(d, project_id="P1").ok


def test_classification_is_not_invented():
    """⚠️ 등급을 지어내면 없느니만 못하다 — 그 값으로 공유 판단을 하게 된다."""
    d = _draft()
    d["datasets"][0]["fields"][0].pop("classification")
    r = compile_contract(d, project_id="P1")
    assert not r.ok
    assert any("classification" in e for e in r.errors)
    assert r.contract["datasets"][0]["fields"][0]["classification"] == ""
    # ★ 실패한 계약은 **지문을 갖지 않는다** — 지문이 남으면 DRAFT 가 승인 가능한 것처럼 보인다.
    assert r.contract["semantic_fingerprint"] == ""
    assert r.contract["status"] == "DRAFT"


def test_optional_semantic_fields_may_stay_empty():
    """★ 전부 필수로 하면 Tech Lead 가 값을 지어낸다."""
    d = _draft()
    d["datasets"][0].pop("ontology_entity_type")
    d["datasets"][0]["fields"][0].pop("unit")
    d["datasets"][0]["fields"][0].pop("semantic_role")
    assert compile_contract(d, project_id="P1").ok


def test_duplicate_dataset_names_are_rejected():
    d = _draft()
    d["datasets"].append(copy.deepcopy(d["datasets"][0]))
    r = compile_contract(d, project_id="P1")
    assert not r.ok and any("중복" in e for e in r.errors)


def test_app_class_must_be_decided():
    for bad in ("", "unknown", None):
        d = _draft(app_class=bad)
        assert not compile_contract(d, project_id="P1").ok


# ── 6. 매니페스트 ↔ 계약 일치 ─────────────────────────────────────────────
def test_manifest_is_derived_from_the_contract():
    c = _compiled()
    assert app_manifest.validate(c["manifest"]) == []
    assert set(c["manifest"]["capabilities"]) == {"arrivals.read", "arrivals.create"}


def test_manifest_beyond_the_contract_is_reported_not_dropped():
    """⚠️ 말없이 지우면 사용자가 요구한 것이 사라지고, 아무도 그 사실을 모른다."""
    d = _draft()
    d["manifest"] = app_manifest.build(
        capabilities=["arrivals.read", "arrivals.create", "secrets.update"],
        app_class="departmental")
    r = compile_contract(d, project_id="P1")
    assert not r.ok and any("secrets.update" in e for e in r.errors)


def test_stored_contract_with_over_broad_manifest_is_invalid():
    """저장된 계약에도 같은 규칙이 걸린다 — 컴파일러만 믿지 않는다."""
    c = _compiled()
    c["manifest"]["capabilities"].append("secrets.update")
    c["manifest"]["required_capabilities"].append({"resource": "secrets", "actions": ["update"]})
    errs = arc.validate(c)
    assert any("secrets.update" in e for e in errs)


def test_manifest_fixed_values_cannot_be_loosened():
    c = _compiled()
    c["manifest"]["auth_mode"] = "SELF"
    assert any("auth_mode" in e for e in arc.validate(c))


# ── 7. 컴파일러는 던지지 않는다 ───────────────────────────────────────────
@pytest.mark.parametrize("junk", [None, "문자열", 42, [], {"datasets": "목록아님"},
                                  {"capability_intents": [None, 7]},
                                  {"datasets": [{"name": "x", "fields": "목록아님"}]}])
def test_compiler_never_raises(junk):
    """⚠️ 초안 형태가 어긋났다고 예외를 던지면 스프린트 루프가 통째로 죽는다
    (2026-07-26 에 ADR 검증이 정확히 그렇게 죽였다)."""
    r = compile_contract(junk, project_id="P1")
    assert not r.ok
    assert r.status == "DRAFT" and r.fingerprint == ""


def test_compilation_is_deterministic():
    a = compile_contract(_draft(), project_id="P1", task_id="T1").contract
    b = compile_contract(_draft(), project_id="P1", task_id="T1").contract
    assert a == b


def test_action_order_does_not_matter():
    d = _draft()
    d["datasets"][0]["allowed_actions"] = ["create", "read"]
    assert compile_contract(d, project_id="P1", task_id="T1").fingerprint == \
        _compiled()["semantic_fingerprint"]


def test_unknown_action_is_rejected():
    d = _draft()
    d["datasets"][0]["allowed_actions"] = ["read", "purge"]
    r = compile_contract(d, project_id="P1")
    assert not r.ok and any("purge" in e for e in r.errors)


def test_compiled_contract_passes_the_validator():
    assert arc.validate(_compiled()) == []
    assert arc.assert_valid(_compiled())


def test_summary_carries_no_secret_and_names_the_datasets():
    s = arc.summarize(_compiled())
    assert "arrivals" in s and "데이터셋 1개" in s


# ── 8. 버전 계약 ──────────────────────────────────────────────────────────
def test_three_versions_are_distinct_contracts():
    """⚠️ 셋을 한 숫자로 묶으면 이후 한쪽만 올릴 수 없게 된다."""
    from state_models import PROJECT_STATE_SCHEMA_VERSION
    assert arc.SCHEMA_VERSION == "1.0"                  # 계약 문서 형식
    assert arc.RUNTIME_CONTRACT_VERSION == 1            # 앱↔Host 런타임 계약 세대
    assert PROJECT_STATE_SCHEMA_VERSION == "5.2.0"      # 파이프라인 상태
    assert arc.SCHEMA_VERSION != PROJECT_STATE_SCHEMA_VERSION


def test_runtime_contract_version_matches_the_wire():
    from core import host_runtime_wire
    assert arc.RUNTIME_CONTRACT_VERSION == host_runtime_wire.WIRE_VERSION


def test_conditional_limit_is_the_one_the_runtime_enforces():
    """§1-2 의 「조건부 지원」 경계는 **런타임이 실제로 강제하는 상한**이어야 한다.

    ⚠️ 계약이 상한을 더 크게 말하면 화면은 「전수 집계가 된다」고 믿고 만든다. 그러면
      데이터가 늘어난 날 **조용히 틀린 합계**를 보여주고, 그때 화면은 오류를 내지 않는다."""
    import inspect
    from core import host_runtime_wire
    from api.routes import app_data_runtime

    assert arc.CONDITIONAL_LIMITS["max_page_size"] == host_runtime_wire.MAX_PAGE_LIMIT
    # 목록 경로가 그 상수로 자르는가 — 여기에 숫자를 다시 적으면 둘이 갈라진다.
    src = "\n".join(l.split("#")[0] for l in inspect.getsource(app_data_runtime).splitlines())
    assert "wire.MAX_PAGE_LIMIT" in src


def test_status_labels_cover_every_status():
    for st in arc.CAPABILITY_STATUSES:
        assert arc.STATUS_LABEL.get(st)
    assert arc.STATUS_LABEL[arc.PROHIBITED] != arc.STATUS_LABEL[arc.NOT_YET_SUPPORTED], \
        "「지원 대기」와 「허용되지 않음」이 같은 문구면 사용자는 언젠가 열린다고 읽는다"
