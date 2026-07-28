# ==========================================
# ECM E2 — 프로필 상속 병합 + 템플릿↔마스터 바인딩
# (`docs/design_enterprise_context_master.md` §4.4·§5.2 / 감사 ENTERPRISE-01 Action 3)
#
# 검증하는 계약 여섯:
#  ① **가장 하위의 승인된 프로필이 이긴다**(§4.4) — 두 단어가 다 중요하다.
#     '가장 하위' = 현장이 본사보다 자기 공정을 잘 안다(§13 "업종 템플릿이 현장 예외를 삭제" 방지).
#     '승인된' = 미승인(DRAFT) 값이 프롬프트에 들어가면 안 된다.
#  ② **리스트는 병합하지 않고 교체한다** — 이어붙이면 그 공장에 없는 공정이 프롬프트에 들어가
#     환각의 근거가 된다.
#  ③ **`replace` 모드는 상위를 버린다** — 병합으로 표현할 수 없는 완전 대체가 필요한 경우가 있다.
#  ④ **근거를 함께 돌려준다**(`sources`/`skipped`) — "이 값이 어디서 왔나"에 답할 수 없으면
#     프로필 기반 추천을 신뢰할 수 없다(§5.2).
#  ⑤ ★ **템플릿 바인딩이 환각을 차단한다**(감사 Action 3) — 기준정보를 주입하는 것만으로는 부족하고
#     "이 수치는 계산 결과이니 지어내지 말라"는 규칙이 함께 프롬프트에 들어가야 한다.
#  ⑥ **조직 프로필이 플레이북의 필수를 지울 수 없다** — 조용히 지우면 준비도가 부풀려지고 결손
#     안내도 안 뜬다(M0-a 에서 같은 유형의 결함을 겪었다).
# ==========================================
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.routes.enterprise_context_control as ecc
from api.deps import Principal, current_principal
from core.advisor_playbook import load_playbook
from core.enterprise_context import (STATUS_ACTIVE, EcmRepository, EcmResolver,
                                     EnterpriseProfile)
from core.enterprise_context.profile_resolver import (TEMPLATE_MASTER_BINDINGS, ProfileResolver,
                                                      apply_org_profile_to_requirements,
                                                      binding_for_template,
                                                      playbook_industry_base,
                                                      render_binding_block)
from core.enterprise_context.seed import seed_example_organization
from core.org_directory import AccessScope

PB_ID = "business_planning"


@pytest.fixture
def stack(tmp_path):
    repo = EcmRepository(db_path=str(tmp_path / "ecm.db"))
    ids = seed_example_organization(repo)["node_ids"]
    return repo, ids, ProfileResolver(repo, EcmResolver(repo))


def _prof(repo, node_id, payload, kind="data_profile", approved=True, mode="merge"):
    return repo.upsert_profile(EnterpriseProfile(
        scope_node_id=node_id, profile_kind=kind, payload=payload, inheritance_mode=mode,
        status=STATUS_ACTIVE if approved else "DRAFT",
        approved_by="admin" if approved else "",
        approved_at="2026-07-28T00:00:00Z" if approved else ""))


# ── ① 하위 우선 · 승인된 것만 ──────────────────────────────────────────────
def test_inheritance_chain_is_top_down(stack):
    repo, ids, pr = stack
    chain = pr.inheritance_chain(ids["BATT_PLANT_1"])
    assert chain[-1] == ids["BATT_PLANT_1"], "마지막이 자기 자신"
    assert chain.index(ids["LS_MNM"]) < chain.index(ids["MNM_BATTERY"]), "상위 → 하위 순서"


def test_lower_node_wins(stack):
    """★ 현장이 본사보다 자기 공정을 잘 안다."""
    repo, ids, pr = stack
    _prof(repo, ids["LS_MNM"], {"freshness_days": 30, "owner": "본사"})
    _prof(repo, ids["MNM_BATTERY"], {"freshness_days": 7})
    _prof(repo, ids["BATT_PLANT_1"], {"freshness_days": 1})
    out = pr.resolve(ids["BATT_PLANT_1"], "data_profile")
    assert out["payload"]["freshness_days"] == 1, "가장 하위가 이긴다"
    assert out["payload"]["owner"] == "본사", "하위가 언급하지 않은 키는 상위 값이 살아남는다"


def test_unapproved_profile_is_skipped_with_reason(stack):
    """★ 검토 전 값이 프롬프트에 들어가면 안 된다. 그리고 왜 제외됐는지 보여야 한다."""
    repo, ids, pr = stack
    _prof(repo, ids["MNM_BATTERY"], {"freshness_days": 7})
    _prof(repo, ids["BATT_PLANT_1"], {"freshness_days": 1}, approved=False)
    out = pr.resolve(ids["BATT_PLANT_1"], "data_profile")
    assert out["payload"]["freshness_days"] == 7, "미승인은 병합되지 않는다"
    assert out["skipped"] and "승인" in out["skipped"][0]["reason"]


def test_industry_base_is_the_bottom_layer(stack):
    """플레이북(산업 공통)이 최상위이고 조직이 그것을 덮는다(D-002)."""
    repo, ids, pr = stack
    _prof(repo, ids["MNM_BATTERY"], {"freshness_days": 7})
    out = pr.resolve(ids["MNM_BATTERY"], "data_profile",
                     industry_base={"freshness_days": 30, "industry": "제련"})
    assert out["payload"]["freshness_days"] == 7, "조직이 산업 공통을 덮는다"
    assert out["payload"]["industry"] == "제련", "조직이 안 건드린 것은 산업 공통이 남는다"
    assert out["sources"][0]["layer"] == "industry_common"


# ── ② 리스트 교체 ────────────────────────────────────────────────────────
def test_lists_are_replaced_not_concatenated(stack):
    """★ 이어붙이면 그 공장에 없는 공정이 프롬프트에 들어가 환각의 근거가 된다."""
    repo, ids, pr = stack
    _prof(repo, ids["LS_MNM"], {"processes": ["제련", "정련", "주조", "압연", "검사"]})
    _prof(repo, ids["BATT_PLANT_1"], {"processes": ["소성", "코팅", "검사"]})
    out = pr.resolve(ids["BATT_PLANT_1"], "data_profile")
    assert out["payload"]["processes"] == ["소성", "코팅", "검사"]
    assert "압연" not in out["payload"]["processes"], "없는 공정이 남으면 안 된다"


def test_nested_dicts_merge_deeply(stack):
    repo, ids, pr = stack
    _prof(repo, ids["LS_MNM"], {"kpi": {"수율": 0.9, "가동률": 0.8}})
    _prof(repo, ids["BATT_PLANT_1"], {"kpi": {"수율": 0.95}})
    out = pr.resolve(ids["BATT_PLANT_1"], "data_profile")
    assert out["payload"]["kpi"] == {"수율": 0.95, "가동률": 0.8}


# ── ③ replace 모드 ───────────────────────────────────────────────────────
def test_replace_mode_discards_upper(stack):
    """병합으로는 표현할 수 없는 '완전 대체'가 필요한 경우가 있다."""
    repo, ids, pr = stack
    _prof(repo, ids["LS_MNM"], {"processes": ["제련"], "legacy": True})
    _prof(repo, ids["BATT_PLANT_1"], {"processes": ["소성"]}, mode="replace")
    out = pr.resolve(ids["BATT_PLANT_1"], "data_profile")
    assert out["payload"] == {"processes": ["소성"]}, "상위를 통째로 버린다"
    assert out["sources"][0]["mode"] == "replace" and len(out["sources"]) == 1


# ── ④ 근거 표시 ──────────────────────────────────────────────────────────
def test_sources_record_application_order(stack):
    repo, ids, pr = stack
    _prof(repo, ids["LS_MNM"], {"a": 1})
    _prof(repo, ids["MNM_BATTERY"], {"b": 2})
    out = pr.resolve(ids["BATT_PLANT_1"], "data_profile",
                     industry_base={"z": 0}, overlay={"c": 3})
    layers = [s["layer"] for s in out["sources"]]
    assert layers[0] == "industry_common" and layers[-1] == "overlay"
    assert out["payload"] == {"z": 0, "a": 1, "b": 2, "c": 3}


def test_overlay_is_the_lowest_layer(stack):
    """프로젝트/시나리오 오버레이가 조직 프로필까지 덮는다(§4.4 체인 최하위)."""
    repo, ids, pr = stack
    _prof(repo, ids["BATT_PLANT_1"], {"freshness_days": 1})
    out = pr.resolve(ids["BATT_PLANT_1"], "data_profile", overlay={"freshness_days": 0})
    assert out["payload"]["freshness_days"] == 0


def test_unknown_profile_kind_rejected(stack):
    from core.enterprise_context.models import EcmError
    repo, ids, pr = stack
    with pytest.raises(EcmError):
        pr.resolve(ids["LS_MNM"], "무슨_프로필")


def test_empty_node_resolves_to_industry_base_only(stack):
    repo, ids, pr = stack
    out = pr.resolve("", "data_profile", industry_base={"x": 1})
    assert out["payload"] == {"x": 1} and out["chain"] == []


# ── ⑤ ★ 템플릿 바인딩 — 환각 차단 ─────────────────────────────────────────
def test_audit_binding_table_matches_master_root_keys():
    """감사 Action 3 표가 실제 마스터 JSON 루트 키와 맞아야 한다(안 맞으면 바인딩이 무의미)."""
    import glob
    import json
    roots = set()
    for f in glob.glob("docs/master_data/*.json"):
        with open(f, encoding="utf-8") as fh:
            roots.update(json.load(fh).keys())
    for tid, b in TEMPLATE_MASTER_BINDINGS.items():
        for section in b["required_master_sections"]:
            assert section in roots, f"{tid} 가 요구한 '{section}' 이 마스터 JSON 에 없다"


def test_deterministic_templates_are_marked():
    """계산이 필요한 템플릿은 deterministic=True 여야 한다(감사표와 일치)."""
    for tid in ("manufacturing-cost-analysis", "manufacturing-production",
                "manufacturing-qc", "mfg_sim"):
        assert TEMPLATE_MASTER_BINDINGS[tid]["deterministic"] is True
    assert TEMPLATE_MASTER_BINDINGS["manufacturing-market-forecast"]["deterministic"] is False


def test_binding_prompt_block_forbids_fabrication():
    """★★ 감사 지적의 핵심 — 기준정보를 주입하는 것만으로는 환각을 막지 못한다."""
    block = render_binding_block("manufacturing-cost-analysis")
    assert "material_master" in block and "bill_of_materials" in block
    assert "지어내지" in block, "'지어내지 말라'는 지시가 없으면 규칙이 아니다"
    assert "계산할 수 없음" in block, "없을 때 무엇을 하라는 지시가 있어야 한다"


def test_non_deterministic_binding_is_softer():
    block = render_binding_block("manufacturing-market-forecast")
    assert "siop_finance_master" in block
    assert "지어내지" not in block, "통계 모델링 영역에 계산 강제를 걸면 오차단이 된다"


def test_unknown_template_has_no_binding():
    assert binding_for_template("default") is None
    assert render_binding_block("default") == ""
    assert render_binding_block("") == ""


def test_binding_block_is_injected_into_prompt_context(monkeypatch):
    """★ 배선 확인 — 규칙이 실제로 프롬프트 문맥에 들어가는가(이 세션에서 반복된 결함 유형)."""
    from core.context_engine import ContextEngine
    from state_models import ProjectState

    st = ProjectState.model_validate({"project_name": "P", "template_id": "manufacturing-qc"})
    ctx = ContextEngine.build_core_context(st)
    assert "기준정보 바인딩 규칙" in ctx
    assert "quality_master" in ctx

    st2 = ProjectState.model_validate({"project_name": "P", "template_id": "default"})
    assert "기준정보 바인딩 규칙" not in ContextEngine.build_core_context(st2), \
        "바인딩 없는 템플릿에 규칙이 붙으면 안 된다"


# ── ⑥ 조직 프로필이 요구사항을 바꾸는 범위 ────────────────────────────────
def test_org_profile_can_raise_necessity():
    pb = load_playbook(PB_ID)
    out = apply_org_profile_to_requirements(pb, {
        "requirement_overrides": {"master_product": {"necessity": "required"}}})
    assert out["overrides"]["master_product"]["necessity"] == "required"
    assert out["blocked"] == []


def test_org_profile_cannot_delete_playbook_required():
    """★★ 플레이북이 '이것 없으면 성립 안 됨'이라 한 것을 조직 설정으로 조용히 지우면
    준비도가 부풀려지고 결손 안내도 뜨지 않는다."""
    pb = load_playbook(PB_ID)
    required = next(r.key for r in pb.data_requirements if r.necessity == "required")
    out = apply_org_profile_to_requirements(pb, {"excluded_requirements": [required]})
    assert out["excluded"] == []
    assert out["blocked"] and "필수" in out["blocked"][0]["reason"]

    out2 = apply_org_profile_to_requirements(pb, {
        "requirement_overrides": {required: {"necessity": "optional"}}})
    assert required not in out2["overrides"]
    assert out2["blocked"], "필수를 선택으로 내리는 것도 막는다"


def test_org_profile_can_exclude_non_required():
    pb = load_playbook(PB_ID)
    optional_key = next(r.key for r in pb.data_requirements if r.necessity == "optional")
    out = apply_org_profile_to_requirements(pb, {"excluded_requirements": [optional_key]})
    assert out["excluded"] == [optional_key] and out["blocked"] == []


def test_org_profile_can_add_requirements():
    pb = load_playbook(PB_ID)
    out = apply_org_profile_to_requirements(pb, {"additional_requirements": [
        {"key": "org_specific_permit", "canonical_term": "환경 배출 허가", "necessity": "required"}]})
    assert out["additional"][0]["key"] == "org_specific_permit"


def test_org_profile_key_collision_is_blocked():
    pb = load_playbook(PB_ID)
    existing = pb.data_requirements[0].key
    out = apply_org_profile_to_requirements(pb, {"additional_requirements": [{"key": existing}]})
    assert out["additional"] == [] and "충돌" in out["blocked"][0]["reason"]


def test_unknown_keys_are_reported_not_ignored():
    """조용히 무시하면 저작자가 오타를 모른다."""
    pb = load_playbook(PB_ID)
    out = apply_org_profile_to_requirements(pb, {
        "excluded_requirements": ["없는키"],
        "requirement_overrides": {"또없는키": {"necessity": "required"}}})
    assert len(out["blocked"]) == 2


def test_playbook_industry_base_carries_keys_not_bodies():
    """본문(질문 문구·결손 안내)은 플레이북이 진실원본이라 복사하지 않는다(두 곳이 어긋난다)."""
    pb = load_playbook(PB_ID)
    base = playbook_industry_base(pb)
    assert base["playbook_id"] == PB_ID
    assert base["recommended_template_id"] == pb.recommended_template_id
    assert len(base["requirements"]) == len(pb.data_requirements)
    sample = base["requirements"][pb.data_requirements[0].key]
    assert set(sample) == {"necessity", "requirement_type", "owner_department"}
    assert "gap_impact" not in sample and "purpose" not in sample


# ══════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def client(stack, monkeypatch):
    repo, ids, pr = stack
    monkeypatch.setattr(ecc, "ecm_repository", repo)
    monkeypatch.setattr(ecc, "ecm_resolver", EcmResolver(repo))
    import core.enterprise_context.profile_resolver as prm
    monkeypatch.setattr(prm, "profile_resolver", pr)
    app = FastAPI()
    app.include_router(ecc.router)
    return app, TestClient(app), repo, ids


def _as(app, dept="production", readable=None, unrestricted=False):
    scope = AccessScope(user_id="bob", primary_dept_id=dept, unrestricted=unrestricted,
                        readable_dept_ids=frozenset(readable if readable is not None else {dept}),
                        writable_dept_ids=frozenset({dept}))
    app.dependency_overrides[current_principal] = lambda: Principal(user_id="bob", scope=scope)


def test_api_resolved_profile_with_playbook_base(client):
    app, c, repo, ids = client
    _as(app, unrestricted=True)
    _prof(repo, ids["MNM_BATTERY"], {"freshness_days": 7})
    r = c.get(f"/api/v1/enterprise-context/contexts/{ids['MNM_BATTERY']}/resolved-profile"
              f"?profile_kind=data_profile&playbook_id={PB_ID}")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["payload"]["freshness_days"] == 7
    assert d["payload"]["playbook_id"] == PB_ID, "산업 공통 층이 들어갔다"
    assert d["sources"][0]["layer"] == "industry_common"
    assert d["scope_ref"]["kind"] == "ecm_node"


def test_api_resolved_profile_permission(client):
    app, c, repo, ids = client
    _as(app, dept="production", readable={"production"})
    ok = c.get(f"/api/v1/enterprise-context/contexts/{ids['MNM_BATTERY']}/resolved-profile")
    assert ok.status_code == 200
    denied = c.get(f"/api/v1/enterprise-context/contexts/{ids['MNM_SHARED']}/resolved-profile")
    assert denied.status_code == 403


def test_api_resolved_profile_unknown_playbook(client):
    app, c, repo, ids = client
    _as(app, unrestricted=True)
    r = c.get(f"/api/v1/enterprise-context/contexts/{ids['LS']}/resolved-profile"
              f"?playbook_id=ghost_pb")
    assert r.status_code == 404


def test_api_template_binding_exposes_prompt_block(client):
    app, c, _, _ = client
    _as(app, unrestricted=True)
    d = c.get("/api/v1/enterprise-context/templates/mfg_sim/binding").json()["data"]
    assert d["bound"] is True and d["deterministic"] is True
    assert len(d["required_master_sections"]) == 5
    assert "지어내지" in d["prompt_block"]


def test_api_template_binding_unknown_is_not_error(client):
    app, c, _, _ = client
    _as(app, unrestricted=True)
    d = c.get("/api/v1/enterprise-context/templates/default/binding").json()["data"]
    assert d["bound"] is False and d["known_templates"]
