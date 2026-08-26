"""[I-4 1단계] App Runtime Contract 와 HostContractCompiler 회귀.

지키는 것 넷:

1. **판정은 결정표가 한다** — LLM 이 적어 온 상태를 쓰지 않는다.
2. **모르는 요구를 자동 허용하지 않는다** — 결정표에 없으면 `NOT_YET_SUPPORTED`.
3. **금지 항목은 개발 요청이 되지 않는다** — `PROHIBITED` 에 `REQUEST_HOST_FEATURE` 불가.
4. **지문이 바뀌면 승인은 초기화된다** — 문구를 다듬은 것은 바뀐 것이 아니다.
"""
import json
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
            #: [BDR-1] 이 데이터가 무엇이고 어디서 오는가 — 없으면 계약이 성립하지 않는다.
            "data_role": "NATIVE_SUPPLEMENT",
            "source_intent": "AFS_NATIVE",
            "duplicate_entry_policy": "ALLOW_SUPPLEMENT_ONLY",
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
    """지원되는 요구에 붙은 결정은 **버려진다.**

    ## ⚠️⚠️ [2026-08-26] 「막는다」에서 「버리고 계속한다」로 바꿨다

    종전에는 이 잉여 칸 하나로 **프로젝트 전체가 CONTRACT_BLOCKED** 였다. 실측에서
    Tech Lead 가 `app_data.query`(CONDITIONAL)에 `WAIT` 을 붙였고 7개 태스크짜리
    프로젝트가 그 자리에서 멈췄다.

    ★ 컴파일러는 그 값을 **어차피 버린다** — 계약에는 아무 영향이 없다(권한도, 지문도,
      승인도). 지키는 것이 없는데 완주만 막는 거절은 통제가 아니라 마찰이다.
    ⚠️ 그래도 **조용히 넘기지는 않는다**(로그로 말한다). 그리고 아래 시험이 보듯
      **정본 검증기는 그대로 막는다** — 층마다 가정이 달라야 층이다."""
    d = _draft()
    d["capability_intents"][0]["user_decision"] = arc.WAIT
    r = compile_contract(d, project_id="P1")
    assert r.ok, f"잉여 결정 하나로 컴파일이 막혔다: {r.errors}"
    for i in r.contract.get("capability_intents") or []:
        assert not i.get("user_decision"), "버려야 할 결정이 계약에 실렸다"


def test_the_canonical_validator_still_rejects_a_surplus_decision():
    """★★★ **대조군.** 컴파일러가 놓아준다고 정본 검증기까지 놓아주면, 어떤 경로로든
    이 값이 계약에 실려 들어올 수 있다."""
    #: ⚠️ **완전한 계약**을 만들어 그 칸만 뒤집는다. 조각 dict 로 부르면 스키마 오류에서
    #:   먼저 끊겨 결정 규칙까지 가지도 않는다 — 그러면 「막았다」가 아니라 「다른 이유로
    #:   막았다」이고, 이 시험은 아무것도 증명하지 못한다(실제로 그렇게 한 번 틀렸다).
    good = compile_contract(_draft(), project_id="P1").contract
    assert not arc.validate(good), "전제가 깨졌다 — 기준 계약이 이미 유효하지 않다"

    bad = json.loads(json.dumps(good, ensure_ascii=False))
    for i in bad.get("capability_intents") or []:
        if arc.is_buildable(str(i.get("status", ""))):
            i["user_decision"] = arc.WAIT
            break
    else:                                   # pragma: no cover - 기준 초안이 바뀌면
        pytest.skip("기준 초안에 지원되는 능력이 없다")

    assert any("고를 것이 없습니다" in e for e in arc.validate(bad))


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
    #: ⚠️ 증명에 봉인되는 값이므로 축약하지 않는다(64비트는 권한 결속에 좁다).
    assert len(fp) == 64 and all(ch in "0123456789abcdef" for ch in fp)
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


# ── 9. [BDR-1 / I-4 2.2] 출처·역할·중복입력 ───────────────────────────────
#
# ★★★ 무엇을 막으려는가: 계약이 «이 데이터가 어디서 오는가» 를 말하지 않으면 생성기는
#   **모든 것을 입력 화면으로 만든다.** 그러면 현업은 ERP 에 이미 있는 값을 한 번 더 손으로
#   넣고, 두 값이 갈라진 뒤에야 그 사실이 드러난다.

def test_the_three_meaning_fields_are_required():
    """⚠️ 선택으로 두면 빠진 계약이 「모르니까 입력 화면」으로 처리된다."""
    for missing in ("data_role", "source_intent", "duplicate_entry_policy"):
        d = _draft()
        d["datasets"][0].pop(missing)
        r = compile_contract(d, project_id="P1")
        assert not r.ok, missing
        assert any(missing in e for e in r.errors), (missing, r.errors)


@pytest.mark.parametrize("intent,want", [
    (arc.AFS_NATIVE, arc.SUPPORTED),
    #: ★ [Wave F-0] `HOST_SERVICE_REQUIRED` → `SUPPORTED`. **그 Host 서비스를 실제로
    #:   만들었기 때문이다**(BDR-6 `core/host_runtime_provider.py`).
    (arc.ENTERPRISE_READ, arc.SUPPORTED),
    #: ⚠️ 아래 둘은 그대로다 — 「곧 될 것」을 열면 앱이 빈 응답을 정상으로 받는다.
    (arc.EXTERNAL_REFERENCE, arc.HOST_SERVICE_REQUIRED),
    (arc.DERIVED_READ, arc.HOST_SERVICE_REQUIRED),
])
def test_source_intent_decision_table(intent, want):
    status, why = arc.decide_source_intent(intent)
    assert status == want and why
    assert arc.materializable(intent) is (want == arc.SUPPORTED)


@pytest.mark.parametrize("unknown", ["", None, "MAGIC_SOURCE", "afs_native", "  "])
def test_unknown_source_intent_does_not_fall_back_to_native(unknown):
    """★★★ ⚠️⚠️ **모르는 출처를 `AFS_NATIVE` 로 떨어뜨리지 않는다.**
    그 폴백 하나가 곧 이중 입력 앱을 만든다."""
    status, _ = arc.decide_source_intent(unknown)
    assert status == arc.NOT_YET_SUPPORTED
    assert not arc.materializable(unknown)


def test_only_sources_with_a_real_host_service_are_materializable():
    """★★★ 물질화 가능 목록은 **실제로 읽어 줄 수 있는 것**과 정확히 같아야 한다.

    ⚠️ 「곧 될 것」을 여기 넣는 순간 앱이 빈 응답을 정상으로 받고, 그 화면은 오류를
      내지 않는다. 이 목록이 늘어날 때는 **그것을 읽어 주는 코드가 먼저** 있어야 한다.
    ★ [Wave F-0] `ENTERPRISE_READ` 가 늘었다 — 승인된 파일 Snapshot 을 Host Runtime 이
      읽어 준다(`core/host_runtime_provider.SERVING_PROVIDERS`)."""
    from core import host_runtime_provider as hrp

    materializable = [i for i in arc.SOURCE_INTENTS if arc.materializable(i)]
    assert materializable == [arc.AFS_NATIVE, arc.ENTERPRISE_READ]
    #: ★★★ 계약 계층과 런타임 계층이 **같은 것**을 말해야 한다 — 갈라지면 계약은
    #:   허용하는데 런타임이 못 읽거나, 그 반대가 된다.
    assert {hrp.provider_for_intent(i) for i in materializable} \
        == set(hrp.SERVING_PROVIDERS)


@pytest.mark.parametrize("intent", [arc.EXTERNAL_REFERENCE, arc.DERIVED_READ])
def test_sources_without_a_host_service_still_cannot_be_compiled(intent):
    """읽어 줄 코드가 없는 출처는 계약에서 막는다 — **만들어져도 읽히지 않기 때문이다.**"""
    d = _draft()
    d["datasets"][0].update({"source_intent": intent, "allowed_actions": ["read"],
                             "data_role": (arc.DERIVED_RESULT if intent == arc.DERIVED_READ
                                           else arc.OPERATIONAL_FORECAST),
                             "duplicate_entry_policy": arc.DENY_IF_AUTHORITATIVE_SOURCE_EXISTS})
    r = compile_contract(d, project_id="P1")
    assert not r.ok
    assert any("Host 기능 필요" in e for e in r.errors), r.errors


def test_an_enterprise_source_compiles_once_it_names_which_table_it_comes_from():
    """★★★ [Wave F-0] 대조군 — 위 시험이 「전부 막힘」으로도 통과하지 않게 한다.

    ⚠️ 계약키가 없으면 여전히 막힌다. 그것이 없으면 그 데이터셋은 **런타임에서 영원히
      읽을 수 없고**, 실패가 만드는 자리가 아니라 쓰는 자리에서 드러난다."""
    d = _draft()
    d["datasets"][0].update({
        "source_intent": arc.ENTERPRISE_READ, "data_role": arc.ENTERPRISE_ACTUAL,
        "duplicate_entry_policy": arc.DENY_IF_AUTHORITATIVE_SOURCE_EXISTS,
        "allowed_actions": ["read"]})

    without = compile_contract(d, project_id="P1")
    assert not without.ok
    assert any("enterprise_contract_key" in e for e in without.errors), without.errors

    d["datasets"][0]["enterprise_contract_key"] = "purchase_orders"
    with_key = compile_contract(d, project_id="P1")
    assert with_key.ok, with_key.errors
    assert with_key.contract["datasets"][0]["enterprise_contract_key"] == "purchase_orders"


def test_enterprise_read_cannot_have_input_actions():
    """★★★ ①번 게이트 — 기존 시스템에서 읽는 데이터에 **입력 화면을 만들지 않는다.**

    ⚠️⚠️ [Wave F-0 실측] 이 시험은 **잘못된 이유로 통과하고 있었다.** 컴파일러가
      `ENTERPRISE_READ` 를 「아직 물질화 불가」로 먼저 막았고, 그 안내문에 마침
      「입력 화면」이라는 말이 들어 있었다 — 게이트가 아니라 **문구가** 통과시켰다.
      출처를 열자 그 우연한 방벽이 사라졌고, 그제서야 컴파일러에 이 게이트가 실제로
      없다는 사실이 드러났다(`role_source_errors` 를 부르지 않고 있었다).
    ★ 그래서 여기서는 **계약키를 채운다** — 다른 오류가 이 게이트를 다시 가리지 않게."""
    for write in ("create", "update", "delete"):
        d = _draft()
        d["datasets"][0].update({
            "source_intent": arc.ENTERPRISE_READ, "data_role": arc.ENTERPRISE_ACTUAL,
            "duplicate_entry_policy": arc.DENY_IF_AUTHORITATIVE_SOURCE_EXISTS,
            "enterprise_contract_key": "purchase_orders",
            "allowed_actions": ["read", write]})
        r = compile_contract(d, project_id="P1")
        assert not r.ok, write
        assert any("입력 화면" in e for e in r.errors), (write, r.errors)


def test_stored_contract_with_enterprise_read_writes_is_invalid():
    """★★★ **컴파일 경로에만 두면 잡히지 않는다.**

    ⚠️ Compiler 는 `ENTERPRISE_READ` 를 「아직 물질화 불가」로 먼저 막으므로, 이중 입력
      게이트 ①은 그 경로에서 **한 번도 실행되지 않는다.** 계약은 파일로도 들어오고
      (릴리스 스냅샷·workspace 원문) 그때는 Compiler 를 지나지 않는다."""
    c = _compiled()
    c["datasets"][0].update({"source_intent": arc.ENTERPRISE_READ,
                             "data_role": arc.ENTERPRISE_ACTUAL,
                             "duplicate_entry_policy": arc.NO_DUPLICATE_CHECK_REQUIRED,
                             "allowed_actions": ["read", "create"]})
    c["semantic_fingerprint"] = arc.semantic_fingerprint(c)   # 지문은 맞춰 둔다
    errs = arc.validate(c)
    assert any(arc.DUPLICATE_ENTRY_MESSAGE in e for e in errs), errs
    #: 읽기만이면 이 규칙은 걸리지 않는다 — 전부 거부하는 검사는 통제를 증명하지 않는다.
    #: (매니페스트도 함께 좁혀야 한다: 계약이 read 만 주면 매니페스트도 read 만 가진다.)
    c["datasets"][0]["allowed_actions"] = ["read"]
    c["manifest"] = app_manifest.build(capabilities=["arrivals.read"],
                                       app_class="departmental")
    c["semantic_fingerprint"] = arc.semantic_fingerprint(c)
    assert arc.validate(c) == []


def test_enterprise_actual_cannot_be_afs_native():
    """★★★ **기업 Actual 의 AFS Native 폴백 차단** — 가장 위험한 조합이다.

    ⚠️ 회사의 확정 실적을 AFS 화면에서 받겠다는 선언은 곧 이중 입력이고,
      두 값이 갈라진 뒤에야 드러난다."""
    d = _draft()
    d["datasets"][0].update({"data_role": arc.ENTERPRISE_ACTUAL,
                             "source_intent": arc.AFS_NATIVE,
                             "allowed_actions": ["read"]})
    r = compile_contract(d, project_id="P1")
    assert not r.ok
    assert any("이중 입력" in e for e in r.errors), r.errors
    assert arc.AFS_NATIVE not in arc.ROLE_SOURCE_MATRIX[arc.ENTERPRISE_ACTUAL]


def test_deny_if_authoritative_source_exists_blocks_writes():
    """②번 게이트 — 정책이 «권위 원천이 있으면 금지» 인데 입력이 생기면 그 정책은 글자다."""
    d = _draft()
    d["datasets"][0].update({
        "duplicate_entry_policy": arc.DENY_IF_AUTHORITATIVE_SOURCE_EXISTS,
        "allowed_actions": ["read", "create"]})
    r = compile_contract(d, project_id="P1")
    assert not r.ok and any("중복입력 정책" in e for e in r.errors)


def test_role_and_source_must_say_the_same_thing():
    """⑤번 게이트 — 역할과 출처가 서로 다른 말을 하면 안 된다.

    ★ 여기서는 **물질화 가능한 출처끼리** 어긋뜨린다. `ENTERPRISE_READ` 를 쓰면 Compiler 의
      출처 결정표가 먼저 막아 이 규칙을 시험하지 못한다."""
    d = _draft()
    #: 계산 결과(`DERIVED_RESULT`)를 사람이 입력하겠다는 선언 — 결정론이 깨진다.
    d["datasets"][0].update({"data_role": arc.DERIVED_RESULT,
                             "source_intent": arc.AFS_NATIVE,
                             "duplicate_entry_policy": arc.NO_DUPLICATE_CHECK_REQUIRED,
                             "allowed_actions": ["read", "create"]})
    r = compile_contract(d, project_id="P1")
    assert not r.ok
    assert any("역할" in e and "DERIVED_RESULT" in e for e in r.errors), r.errors


def test_supplement_only_policy_belongs_to_supplement_data():
    d = _draft()
    d["datasets"][0].update({"data_role": arc.SCENARIO_INPUT,
                             "duplicate_entry_policy": arc.ALLOW_SUPPLEMENT_ONLY})
    r = compile_contract(d, project_id="P1")
    assert not r.ok and any("보완만 허용" in e for e in r.errors)


@pytest.mark.parametrize("mutate", [
    lambda d: d["datasets"][0].update({"data_role": arc.SCENARIO_INPUT,
                                       "duplicate_entry_policy": arc.NO_DUPLICATE_CHECK_REQUIRED}),
    lambda d: d["datasets"][0].__setitem__("duplicate_entry_policy",
                                           arc.NO_DUPLICATE_CHECK_REQUIRED),
    lambda d: d["datasets"][0].__setitem__("enterprise_contract_key", "PRC-02"),
    lambda d: d["datasets"][0].__setitem__("required_freshness", "P1D"),
])
def test_meaning_changes_move_the_fingerprint(mutate):
    """★★★ 「기존 시스템에서 읽는다」가 「화면에서 받는다」로 바뀌는 것은 설명 문구가
    아니라 **업무 자체의 변경**이다 — 재승인 대상이어야 한다."""
    base = _compiled()["semantic_fingerprint"]
    d = _draft()
    mutate(d)
    r = compile_contract(d, project_id="P1", task_id="T1")
    assert r.ok, r.errors
    assert r.fingerprint != base


def test_each_meaning_field_moves_the_fingerprint_on_its_own():
    """★★★ 한 필드씩 따로 확인한다.

    ⚠️ 두 필드를 함께 바꾸는 시험만 있으면 **하나가 지문에서 빠져도 초록**이다 — 다른
      하나가 지문을 움직여 주기 때문이다(변이 검사에서 실제로 그 구멍이 잡혔다).
    ★ `source_intent` 는 `AFS_NATIVE` 말고는 컴파일되지 않으므로 **지문 함수를 직접** 부른다."""
    base = _compiled()
    ds = base["datasets"][0]
    for field, other in (("data_role", arc.OPERATIONAL_FORECAST),
                         ("source_intent", arc.ENTERPRISE_READ),
                         ("duplicate_entry_policy", arc.NO_DUPLICATE_CHECK_REQUIRED),
                         ("enterprise_contract_key", "PRC-02"),
                         ("required_freshness", "P1D")):
        moved = copy.deepcopy(base)
        moved["datasets"][0][field] = other
        assert arc.semantic_fingerprint(moved) != arc.semantic_fingerprint(base), field
    assert ds["data_role"] == arc.NATIVE_SUPPLEMENT     # 기준값이 바뀌지 않았다


def test_changing_the_source_intent_resets_approval():
    """출처가 바뀌면 이전 승인은 그대로 이어지지 않는다."""
    prev = _approved_previous()
    d = _draft()
    d["datasets"][0].update({"data_role": arc.OPERATIONAL_FORECAST,
                             "source_intent": arc.AFS_NATIVE,
                             "duplicate_entry_policy": arc.NO_DUPLICATE_CHECK_REQUIRED})
    r = compile_contract(d, project_id="P1", task_id="T1", previous=prev)
    assert r.ok and r.fingerprint_changed
    assert r.contract["approval"] == {"status": "PENDING"}


def test_unclassified_is_never_declared_enterprise_actual():
    """★★★ **미분류 레거시의 자동 Actual 승격 금지.**

    ⚠️⚠️ 「역할이 안 적혀 있으니 실적이겠지」는 추측이고, 그 추측 위에서 경영 보고가
      만들어진다."""
    f = arc.is_declared_enterprise_actual_dataset
    assert f({"name": "x"}) is False
    assert f({"name": "x", "data_role": ""}) is False
    assert f({"name": "x", "data_role": arc.NATIVE_SUPPLEMENT}) is False
    assert f(None) is False
    assert f({"name": "x", "data_role": arc.ENTERPRISE_ACTUAL}) is True


def test_the_name_stops_at_declared():
    """★★★ 이름이 «선언» 에서 멈춘다.

    정본 설계상 **공식 실적**은 선언 + 승인된 Source Binding + 대사 완료 + Data Owner
    인증 + 유효한 CERTIFIED Snapshot 을 모두 요구하고, 뒤의 넷은 **아직 없다**(BDR-2~3).
    ⚠️⚠️ 지금 `is_official_actual` 이라고 부르면 선언 하나가 공식 실적처럼 읽히고,
      다음 사람은 코드를 읽지 않고 **이름을 믿는다.**"""
    assert not hasattr(arc, "is_official_actual")
    from core import app_data, business_data_semantics
    assert not hasattr(app_data.app_data_service, "is_official_actual")
    assert hasattr(business_data_semantics, "is_declared_enterprise_actual")


def test_freshness_must_be_comparable():
    """⚠️ 신선도 요구를 자유 문장으로 두면 비교할 수 없다 — 「하루」와 「1일」이 다른 값이 된다."""
    #: ⚠️⚠️ 월·년은 **고정 길이가 아니다** — `P1M` 은 28~31일, `P1Y` 는 365 또는 366일이다.
    #:   그 값으로 최신성을 비교하면 같은 데이터가 기준일에 따라 신선하기도, 낡기도 한다.
    #:   그리고 그 차이는 월말·윤년에만 드러난다.
    for bad in ("하루", "1D", "P", "1일", "P1X", "P1M", "P1Y", "P1Y6M"):
        d = _draft()
        d["datasets"][0]["required_freshness"] = bad
        assert not compile_contract(d, project_id="P1").ok, bad
    for good in ("P1D", "PT6H", "P1DT12H", "P2W", "PT30M", "P7D"):
        d = _draft()
        d["datasets"][0]["required_freshness"] = good
        assert compile_contract(d, project_id="P1").ok, good


def test_block_message_speaks_to_the_business_not_the_machine():
    """차단 문구는 현업이 **다음에 무엇을 할지** 알 수 있어야 한다.
    ⚠️ 「ENTERPRISE_READ 이므로 create 가 금지됩니다」는 아무것도 알려 주지 않는다."""
    msg = arc.DUPLICATE_ENTRY_MESSAGE
    assert "데이터 연결" in msg and "입력 화면을 만들지 않습니다" in msg
    for jargon in ("ENTERPRISE_READ", "AFS_NATIVE", "allowed_actions", "create"):
        assert jargon not in msg


def test_a_clean_native_supplement_contract_still_compiles():
    """★ 대조군 — 막기만 하는 게이트는 통제를 증명하지 않는다."""
    r = compile_contract(_draft(), project_id="P1")
    assert r.ok, r.errors
    ds = r.contract["datasets"][0]
    assert ds["source_intent"] == arc.AFS_NATIVE
    assert ds["data_role"] == arc.NATIVE_SUPPLEMENT
    assert "create" in ds["allowed_actions"]


# ── 8. 버전 계약 ──────────────────────────────────────────────────────────
def test_three_versions_are_distinct_contracts():
    """⚠️ 셋을 한 숫자로 묶으면 이후 한쪽만 올릴 수 없게 된다."""
    from state_models import PROJECT_STATE_SCHEMA_VERSION
    assert arc.SCHEMA_VERSION == "1.0"                  # 계약 문서 형식
    assert arc.RUNTIME_CONTRACT_VERSION == 1            # 앱↔Host 런타임 계약 세대
    assert PROJECT_STATE_SCHEMA_VERSION == "5.3.0"      # 파이프라인 상태(4c-2 에서 승격)
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


# ══════════════════════════════════════════════════════════════════════════
# 지문은 **인용 횟수**에 흔들리지 않는다 (2026-08-26 실측)
# ══════════════════════════════════════════════════════════════════════════

def _fp(intents):
    from core import app_runtime_contract as _arc
    return _arc.semantic_fingerprint(
        {"app_class": "departmental", "datasets": [], "capability_intents": intents})


def test_같은_능력을_여러_FR_이_인용해도_지문이_같다():
    """★★★ **실측: 승인이 영영 수렴하지 않았다.**

    지문 재료에는 `requirement_ref` 가 빠져 있다(설명이므로 옳다). 그런데 능력을
    **중복째** 실었더니, 「같은 `app_data.read` 를 몇 개의 FR 이 인용했는가」만으로 지문이
    바뀌었다 — 권한은 한 글자도 안 달라졌는데.

    실측에서 Tech Lead 가 매 실행마다 인용 수를 달리 적어 지문이
    `56ac83 → 906969 → 56ac83 → 2fcd71 → d0efff` 로 오갔고, 사용자는 승인을 눌러도
    **계속 재승인을 요구받았다.**

    ★ 머리말이 「문구를 다듬었다고 재승인을 요구하면 사람이 게이트를 습관으로
      통과시킨다」고 적어 둔 것과 같은 이유다 — **인용 횟수도 문구다.**"""
    one = [{"capability": "app_data.read", "status": "SUPPORTED",
            "requirement_ref": "FR-1", "user_decision": ""}]
    many = [{"capability": "app_data.read", "status": "SUPPORTED",
             "requirement_ref": f"FR-{n}", "user_decision": ""} for n in (1, 2, 3)]
    assert _fp(one) == _fp(many), "인용 횟수만으로 지문이 바뀐다 — 승인이 수렴하지 않는다"


def test_순서가_달라도_지문이_같다():
    """⚠️ 모델이 같은 것을 다른 순서로 적는 것도 문구다."""
    a = [{"capability": "app_data.read", "status": "SUPPORTED", "user_decision": ""},
         {"capability": "app_data.create", "status": "SUPPORTED", "user_decision": ""}]
    assert _fp(a) == _fp(list(reversed(a)))


def test_결정이_다르면_지문이_달라진다():
    """★★★ **대조군.** 합치기가 실제 차이를 지우면 안 된다.

    같은 능력이라도 FR-1 은 `REDUCE`, FR-2 는 `WAIT` 로 정했다면 그것은 **다른 결정**이다.
    합쳐 버리면 하나가 조용히 사라지고, 사라진 결정은 아무도 다시 묻지 않는다."""
    one = [{"capability": "network.external_api", "status": "HOST_SERVICE_REQUIRED",
            "user_decision": "REDUCE"}]
    two = one + [{"capability": "network.external_api", "status": "HOST_SERVICE_REQUIRED",
                  "user_decision": "WAIT"}]
    assert _fp(one) != _fp(two), "서로 다른 결정을 하나로 합쳤다"


def test_능력이_늘면_지문이_달라진다():
    """★ 대조군 둘 — **권한이 실제로 늘면** 반드시 재승인을 지나야 한다."""
    a = [{"capability": "app_data.read", "status": "SUPPORTED", "user_decision": ""}]
    b = a + [{"capability": "app_data.delete", "status": "SUPPORTED", "user_decision": ""}]
    assert _fp(a) != _fp(b), "권한이 늘었는데 지문이 그대로다"


def test_상태가_다르면_지문이_달라진다():
    """⚠️ 같은 이름이라도 판정이 달라지면 다른 계약이다."""
    a = [{"capability": "file.upload", "status": "NOT_YET_SUPPORTED", "user_decision": "WAIT"}]
    b = [{"capability": "file.upload", "status": "SUPPORTED", "user_decision": ""}]
    assert _fp(a) != _fp(b)


# ══════════════════════════════════════════════════════════════════════════
# 예약 필드 이름은 **계약 단계에서** 잡힌다 (2026-08-26 실측)
# ══════════════════════════════════════════════════════════════════════════

def test_예약된_필드_이름은_계약에서_막힌다():
    """★★★ **실측: 이것 때문에 「완주한 앱」이 못 돌았다.**

    `created_at` 을 필드로 넣었더니 **계약 컴파일·승인·코드 생성·태스크 완료·릴리스까지
    전부 통과**한 뒤 물질화에서 실패했다. 그 결과:

        물질화 FAILED → 릴리스 매니페스트의 능력이 **빈 배열**
          → 증명 발급 거절(「매니페스트 미선언」)
          → 앱이 데이터를 못 읽고 「초기화 중 오류」로 멈춤

    사람이 **화면에서** 그것을 처음 알았다. 규칙은 이미 스킬에 적혀 있었는데 **아무 관문도
    잡지 않았다** — 잡는 자리를 계약 단계로 당긴다."""
    from core.app_data import RESERVED_FIELD_NAMES

    for reserved in sorted(RESERVED_FIELD_NAMES):
        d = _draft()
        d["datasets"][0]["fields"].append(
            {"name": reserved, "type": "date", "required": False,
             "classification": "INTERNAL"})
        r = compile_contract(d, project_id="P1")
        assert not r.ok, f"예약 이름 «{reserved}» 이 계약을 통과했다"
        assert any(reserved in e for e in r.errors), r.errors


def test_예약이_아닌_이름은_통과한다():
    """⚠️ **대조군.** 「_at 으로 끝나면 막는다」처럼 넓히면 멀쩡한 이름이 막힌다 —
    `registered_at`·`ordered_at` 은 정상이다."""
    d = _draft()
    d["datasets"][0]["fields"].append(
        {"name": "registered_at", "type": "date", "required": False,
         "classification": "INTERNAL"})
    r = compile_contract(d, project_id="P1")
    assert r.ok, f"멀쩡한 이름을 막았다: {r.errors}"


def test_예약_목록을_두_곳에_적지_않는다():
    """⚠️ 목록이 갈라지면 **한쪽만 통과하는 계약**이 생긴다 — 계약은 통과하는데 물질화가
    막는, 방금 겪은 그 상태가 다시 만들어진다."""
    import inspect

    from core import app_runtime_contract as _arc

    src = inspect.getsource(_arc.conditional_errors)
    assert "RESERVED_FIELD_NAMES" in src, "예약 목록을 직접 적고 있다"
    assert "from core.app_data import" in src, "정본에서 읽지 않는다"


def test_스킬이_예약_이름을_전부_알려_준다():
    """★ 규칙만 적고 목록을 안 주면 모델은 **어떤 이름이 예약인지 모른다.** 실제로
    `created_at` 을 썼다."""
    import os

    from core.app_data import RESERVED_FIELD_NAMES

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "skills", "tech_lead_skill.md"), encoding="utf-8") as f:
        text = f.read()
    missing = [n for n in RESERVED_FIELD_NAMES if n not in text]
    assert not missing, "스킬에 없는 예약 이름: " + ", ".join(sorted(missing))
