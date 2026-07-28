# ==========================================
# M1~M4 문서 시드 · 조직 바인딩 · 데이터 품질 점검
# (감사 ENTERPRISE-01 Action 1 종결 / R-001·D-009)
#
# ## 이 테스트의 관점 — 값이 아니라 구조를 검증한다
#
# 사용자 지시(2026-07-29): "데이터 수치가 맞냐, 정확도가 얼마냐는 구현 단계에서 확인할 수 없다.
# 구현 완료 이후 실제 사용을 위한 사전 작업 또는 실제 사용 과정에서 보정되어야 한다."
# → 그래서 여기서는 **특정 수치가 옳은지 판정하지 않는다.** 대신:
#    ① 문서 값이 **변형 없이** 적재되는가(변형하면 문서를 고쳐도 반영되지 않는다)
#    ② 문서가 **올바른 조직 범위**에 바인딩되는가(배터리소재가 동제련에 새면 안 된다)
#    ③ 모순이 **자동으로 드러나는가**(사람이 기억해서 챙기지 않아도 되게)
#    ④ 시드가 **멱등**하고 사용자 개정을 되돌리지 않는가
# ==========================================
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.enterprise_context import EcmRepository, EcmResolver
from core.enterprise_context.seed import seed_example_organization
from core.master_data import MasterData
from core.master_data_seed import (DOCUMENT_SCOPES, ENTITY_TYPES, SEED_SOURCE,
                                   inspect_data_quality, load_documents,
                                   seed_master_documents)


@pytest.fixture
def stack(tmp_path, monkeypatch):
    repo = EcmRepository(db_path=str(tmp_path / "ecm.db"))
    ids = seed_example_organization(repo)["node_ids"]
    import core.enterprise_context.resolver as res_mod
    monkeypatch.setattr(res_mod, "ecm_resolver", EcmResolver(repo))
    md = MasterData(db_path=str(tmp_path / "master.db"))
    return md, repo, ids


# ── ① 문서 값이 변형 없이 적재되는가 ──────────────────────────────────────
def test_documents_load(tmp_path):
    docs = load_documents()
    assert len(docs) == 4, "M1~M4 네 문서가 있어야 한다"
    assert set(docs) == set(DOCUMENT_SCOPES), "모든 문서에 조직 매핑이 정의돼야 한다"


def test_seed_creates_records_and_types(stack):
    md, repo, ids = stack
    r = seed_master_documents(md=md, ecm_repo=repo)
    assert r["status"] == "seeded"
    assert r["summary"]["records_created"] > 30, "M1~M4 의 실체 데이터가 충분히 적재돼야 한다"
    assert r["summary"]["records_failed"] == 0, f"적재 실패: {r['records_failed']}"
    types = {t["type_id"] for t in md.list_types()}
    assert {tid for tid, _ in ENTITY_TYPES} <= types


def test_values_are_stored_verbatim(stack):
    """★ 값을 변형하면 문서를 고쳐도 반영되지 않고 무엇이 원본인지 알 수 없다."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    src = json.load(open("docs/master_data/battery_material_m1.json", encoding="utf-8"))
    mhp = next(m for m in src["material_master"] if m["material_id"] == "RM-MHP-001")

    rec = md.get_record("RM-MHP-001")
    assert rec is not None
    assert rec["attributes"]["base_price_usd"] == mhp["base_price_usd"]
    assert rec["attributes"]["uom"] == mhp["uom"]
    assert rec["attributes"]["lead_time_days"] == mhp["lead_time_days"]
    assert rec["source"] == SEED_SOURCE, "시드 출처가 표시되어 사용자 입력과 구분된다"


def test_calculation_formulas_are_loaded(stack):
    """M3 의 ERP 산식·ISO22400 KPI 가 적재되어야 한다 — LLM 이 산식을 지어내지 않게 하는 근거."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    kpi = md.get_record("ISO-KPI-01")
    assert kpi and "formula" in kpi["attributes"]
    cost = md.get_record("M3-ERP-COST-MANAGEMENT")
    assert cost and "standard_costing_formula" in cost["attributes"]


def test_simulation_distributions_are_loaded(stack):
    """M4 확률분포가 적재되어야 시뮬레이션이 결정론적으로 재현된다."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    codes = {r["master_code"] for r in md.list_records()}
    assert any(c.startswith("M4-DES-") for c in codes)


# ── ② 조직 범위 바인딩 — 격리가 실제로 되는가 ─────────────────────────────
def test_documents_bind_to_declared_scopes(stack):
    md, repo, ids = stack
    r = seed_master_documents(md=md, ecm_repo=repo)
    assert r["summary"]["bindings"] == (r["summary"]["records_created"]
                                        + r["summary"]["records_skipped"]), \
        "문서에서 나온 레코드는 모두 조직 범위를 가져야 한다(감사 Finding 1)"
    by_scope = {}
    for b in r["bindings"]:
        by_scope.setdefault(b["scope_code"], []).append(b["master_code"])
    assert set(by_scope) == {"MNM_BATTERY", "MNM_COPPER", "LS_MNM"}


def test_cross_division_isolation(stack):
    """★★ 배터리소재 마스터가 동제련 프롬프트에 섞이면 안 된다(감사 Finding 1 의 핵심)."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)

    batt = md.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"])
    copper = md.allowed_codes_for_scope("tenant_default", ids["MNM_COPPER"])
    assert "RM-MHP-001" in batt and "RM-MHP-001" not in copper, "배터리 원료가 동제련에 새면 안 된다"
    assert "RM-CUCON-001" in copper and "RM-CUCON-001" not in batt, "동정광이 배터리에 새면 안 된다"


def test_corporate_standard_inherits_to_all_divisions(stack):
    """M3 전사 표준은 법인 하위 모든 사업부에 상속된다."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    for code in ("MNM_BATTERY", "MNM_COPPER", "MNM_SHARED", "BATT_PLANT_1"):
        allowed = md.allowed_codes_for_scope("tenant_default", ids[code])
        assert "ISO-KPI-01" in allowed, f"{code} 에 전사 표준이 상속되지 않았다"


def test_other_legal_entity_gets_nothing(stack):
    """★ 다른 법인(LS전선)은 MnM 기준정보를 전혀 받지 않는다."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    assert md.allowed_codes_for_scope("tenant_default", ids["LS_CABLE"]) == set()


def test_plant_inherits_from_division(stack):
    """공장은 사업부 바인딩을 상속받는다(운영 계층)."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    div = md.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"])
    plant = md.allowed_codes_for_scope("tenant_default", ids["BATT_PLANT_1"])
    assert div <= plant, "사업부에 적용된 것은 하위 공장에도 적용된다"


def test_injection_respects_scope(stack):
    """실제 주입 경로까지 격리가 이어지는가(배선 확인)."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    text = "Mixed Hydroxide Precipitate 와 Copper Concentrate 검토"
    batt = {r["master_code"] for r in md.select_for_injection(
        text, ["manufacturing"], "tenant_default", ids["MNM_BATTERY"])}
    copper = {r["master_code"] for r in md.select_for_injection(
        text, ["manufacturing"], "tenant_default", ids["MNM_COPPER"])}
    assert "RM-MHP-001" in batt and "RM-MHP-001" not in copper


# ── ②-b 전수 주입 — 임의 절단 금지(2026-07-29 사용자 지시) ─────────────────
def test_all_applicable_records_are_injected(stack):
    """★★ 적용 가능한 기준정보는 **전부** 주입된다. 상한으로 임의 절단하지 않는다.

    종전 12건 상한에서는 배터리소재 30건 중 12건만 들어가고 표준원가 산식·MPS·라우팅이
    잘려나갔다 — M1 의 존재 이유(LLM 이 산식을 지어내지 못하게 확정 주입)가 무력화됐다."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    node = ids["MNM_BATTERY"]
    allowed = md.allowed_codes_for_scope("tenant_default", node)
    sel, stats = md.select_for_injection("생산 계획", ["manufacturing", "battery-materials",
                                                      "simulation"],
                                         "tenant_default", node, with_stats=True)
    assert stats["dropped"] == 0, "상한으로 잘린 건이 있어선 안 된다"
    assert {r["master_code"] for r in sel} == allowed, "적용 가능 전량이 주입돼야 한다"


def test_formulas_survive_injection(stack):
    """★ 산식이 사업부 자재에 밀려 잘리면 LLM 이 산식을 지어낸다."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    codes = {r["master_code"] for r in md.select_for_injection(
        "원가 계산", ["manufacturing"], "tenant_default", ids["MNM_BATTERY"])}
    for must in ("M3-ERP-COST-MANAGEMENT", "M3-ERP-PRODUCTION-PLANNING-MPS",
                 "M3-ROUTING", "ISO-KPI-01"):
        assert must in codes, f"{must} 이 주입되지 않았다"


def test_default_has_no_cap(stack):
    from core.master_data import _INJECT_MAX_CHARS, _INJECT_MAX_ITEMS
    assert _INJECT_MAX_ITEMS is None and _INJECT_MAX_CHARS is None, \
        "기본값은 상한 없음이다. 상한을 되살리려면 근거를 문서에 남기고 이 테스트를 함께 고쳐라."


def test_explicit_cap_drops_do_not_kill_the_rest(stack):
    """상한을 명시했을 때도 `break` 로 뒤를 전부 잘라내지 않는다(F4)."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    sel, stats = md.select_for_injection("생산", ["manufacturing"], "tenant_default",
                                         ids["MNM_BATTERY"], max_chars=1200, with_stats=True)
    assert stats["dropped"] > 0 and len(sel) > 0
    assert stats["chars"] <= 1200


def test_truncation_is_visible_in_the_block(stack):
    """★ 조용히 잘리면 사람도 LLM 도 무엇이 없는지 모른다."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    import core.master_data as mdm
    orig = mdm._INJECT_MAX_ITEMS
    mdm._INJECT_MAX_ITEMS = 5
    try:
        block = md.render_grounding("생산", ["manufacturing"], "tenant_default",
                                    ids["MNM_BATTERY"])
    finally:
        mdm._INJECT_MAX_ITEMS = orig
    assert "[주의]" in block and "추정하지 말 것" in block


def test_aliases_are_matchable(stack):
    """★★ 문서의 `"Mixed Hydroxide Precipitate (MHP)"` 를 그대로 별칭으로 쓰면 단어경계 매칭에
    영원히 걸리지 않아 **별칭 히트 경로 전체가 죽는다**(실측 결함)."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    aliases = set(md.get_record("RM-MHP-001")["aliases"])
    assert "MHP" in aliases and "Mixed Hydroxide Precipitate" in aliases
    h2so4 = set(md.get_record("RM-H2SO4-001")["aliases"])
    assert "H2SO4" in h2so4 and "Sulfuric Acid" in h2so4
    assert not any(a.strip() == "98%" for a in h2so4), "순수 수치 토큰은 오탐을 부른다"


def test_alias_hit_outranks_domain_core(stack):
    """텍스트에 실제로 등장한 자재가 먼저 온다(잘리지 않아도 순서는 의미가 있다)."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    sel = md.select_for_injection("MHP 투입량 검토", ["manufacturing"],
                                  "tenant_default", ids["MNM_BATTERY"])
    assert sel[0]["master_code"] == "RM-MHP-001"


def test_seed_without_ecm_still_loads(stack):
    """ECM 미도입 환경에서도 적재는 되어야 한다(바인딩만 건너뛴다)."""
    md, repo, ids = stack
    r = seed_master_documents(md=md, ecm_repo=repo, bind_scopes=False)
    assert r["summary"]["records_created"] > 30
    assert r["summary"]["bindings"] == 0


def test_document_scopes_match_ecm_org_codes():
    """★★ `DOCUMENT_SCOPES` 는 조직 코드를 **문자열로** 참조한다. 조직 시드가 코드를 바꾸면
    바인딩이 조용히 건너뛰어지고 → 미바인딩 → 「전사 공통 통과」 규칙을 타고 **모든 조직에
    노출**된다. 실행 시점이 아니라 여기서 먼저 깨지게 한다.

    (배경: 외부 세션 산출물이 같은 조직에 다른 코드 체계 `BU_SMELTING`/`PLANT_ONSAN_1` 을 쓴다.
     D-012 로 `core/enterprise_context/seed.py` 를 조직 SSOT 로 확정했다.)"""
    from core.enterprise_context import seed as ecm_seed
    org_codes = {row[0] for row in ecm_seed._NODES}
    declared = {s["scope_code"] for s in DOCUMENT_SCOPES.values() if s.get("scope_code")}
    missing = declared - org_codes
    assert not missing, (
        f"문서가 참조하는 조직 코드가 ECM 시드에 없다: {sorted(missing)}. "
        f"이대로 두면 해당 기준정보가 미바인딩으로 남아 모든 조직에 노출된다. "
        f"ECM 시드 코드: {sorted(org_codes)}")


def test_scope_code_mismatch_is_reported_as_misconfig(stack, monkeypatch):
    """조직은 있는데 코드만 없는 경우를 'ECM 미도입'과 구분해 크게 남기는가."""
    md, repo, ids = stack
    monkeypatch.setitem(DOCUMENT_SCOPES, "global_standard_m3.json",
                        {**DOCUMENT_SCOPES["global_standard_m3.json"],
                         "scope_code": "NO_SUCH_ORG"})
    r = seed_master_documents(md=md, ecm_repo=repo)
    assert r["status"] == "seeded_with_scope_misconfig"
    assert r["summary"]["unbound_exposed"] > 0
    bad = [x for x in r["binding_skipped"] if x.get("kind") == "scope_code_not_found"]
    assert bad and "모든 조직에 노출" in bad[0]["reason"]


def test_missing_ecm_nodes_are_reported_not_silent(tmp_path, monkeypatch):
    """조직이 없으면 조용히 넘어가지 말고 왜 못 붙였는지 남겨야 한다."""
    md = MasterData(db_path=str(tmp_path / "m.db"))
    empty = EcmRepository(db_path=str(tmp_path / "empty_ecm.db"))
    import core.enterprise_context.resolver as res_mod
    monkeypatch.setattr(res_mod, "ecm_resolver", EcmResolver(empty))
    r = seed_master_documents(md=md, ecm_repo=empty)
    assert r["summary"]["records_created"] > 0
    assert r["binding_skipped"], "바인딩 실패 이유가 리포트에 남아야 한다"
    assert any("ECM 노드가 없습니다" in str(x.get("reason", "")) for x in r["binding_skipped"])


# ── ③ 품질 점검 — 모순이 자동으로 드러나는가 ──────────────────────────────
def test_quality_inspection_finds_known_contradictions():
    """★★ 이 두 모순은 합성·계산을 해보지 않으면 발견되지 않는다. 시스템이 스스로 찾아야 한다."""
    findings = inspect_data_quality()
    kinds = {f["kind"] for f in findings}
    assert "cost_exceeds_price" in kinds, "재료비 > 판가(구조적 적자)를 탐지해야 한다"
    assert "cpk_unreachable" in kinds, "공차·분포·목표 Cpk 모순을 탐지해야 한다"
    assert all(f["severity"] in ("high", "medium", "low") for f in findings)


def test_findings_carry_evidence_and_action():
    """§4.3 F-DA-05 와 같은 원칙 — 문제만 알려주고 조치를 못 알려주면 방치된다."""
    for f in inspect_data_quality():
        assert f["evidence"], f"{f['kind']}: 계산 근거가 없다"
        assert f["suggested_action"], f"{f['kind']}: 다음 조치가 없다"
        assert f["document"] and f["subject"]


def test_cpk_finding_computes_required_sigma():
    """보정 목표를 수치로 줘야 실사용 전 작업이 가능하다."""
    cpk = [f for f in inspect_data_quality() if f["kind"] == "cpk_unreachable"]
    assert cpk
    for f in cpk:
        ev = f["evidence"]
        assert ev["computed_cpk"] < ev["target_cpk"]
        assert ev["std_dev_required"] < ev["std_dev"], "필요한 σ 가 현재보다 작아야 한다"


def test_precious_metal_is_not_false_flagged():
    """★ 금 온스당 고가는 정상이다 — 문서 내 시세(LBMA $2,350/oz)와 교차검증해 오탐을 막는다."""
    subjects = {f["subject"] for f in inspect_data_quality()}
    assert "BP-GOLD-001" not in subjects


def test_quality_inspection_does_not_mutate_documents():
    """★ 값을 자동 보정하지 않는다 — 근거 없는 숫자를 만들면 안 된다(§16)."""
    before = json.load(open("docs/master_data/battery_material_m1.json", encoding="utf-8"))
    inspect_data_quality()
    after = json.load(open("docs/master_data/battery_material_m1.json", encoding="utf-8"))
    assert before == after


def test_seed_report_includes_quality_findings(stack):
    """적재 리포트에 보정 목록이 함께 실려야 사람이 놓치지 않는다."""
    md, repo, ids = stack
    r = seed_master_documents(md=md, ecm_repo=repo)
    assert r["summary"]["high_severity_findings"] >= 1
    assert "보정" in r["note"]


# ── ④ 멱등성 · 사용자 개정 보호 ───────────────────────────────────────────
def test_seed_is_idempotent(stack):
    md, repo, ids = stack
    first = seed_master_documents(md=md, ecm_repo=repo)
    second = seed_master_documents(md=md, ecm_repo=repo)
    assert second["summary"]["records_created"] == 0
    assert second["summary"]["records_skipped"] == first["summary"]["records_created"]
    assert second["status"] == "already_seeded"


def test_seed_does_not_overwrite_user_revision(stack):
    """★★ 시드는 초기 공급이지 진실원본이 아니다 — 운영 중 개정한 값을 되돌리면 안 된다."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    md.create_or_revise_record("RM-MHP-001", "material", "MHP(현업 개정)",
                               attributes={"base_price_usd": 16200, "uom": "Ton"},
                               domains=["manufacturing"], source="user")
    seed_master_documents(md=md, ecm_repo=repo)          # 재실행
    rec = md.get_record("RM-MHP-001")
    assert rec["attributes"]["base_price_usd"] == 16200, "사용자 개정이 시드로 덮여선 안 된다"
    assert rec["source"] == "user"


def test_reseed_binds_preexisting_records(stack):
    """★★ 재시드가 격리를 무너뜨리지 않는가 — 실측으로 발견한 누출.

    바인딩이 없는 코드는 「전사 공통」으로 통과하는 규칙(점진 도입 하위호환)이다. 그래서 기존
    레코드를 건너뛸 때 바인딩 확인까지 건너뛰면, 그 레코드는 **모든 조직에 노출**된다.
    ECM 조직이 아직 없는 상태로 먼저 적재된 실제 DB 에서 이 상황이 재현됐다."""
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo, bind_scopes=False)     # 바인딩 없이 먼저 적재
    assert "RM-MHP-001" in md.allowed_codes_for_scope("tenant_default", ids["LS_CABLE"]) or \
        md.allowed_codes_for_scope("tenant_default", ids["LS_CABLE"]) == set(), \
        "미바인딩 상태의 노출 여부는 통과 규칙에 따른다"

    again = seed_master_documents(md=md, ecm_repo=repo)                # 조직 붙여 재시드
    assert again["summary"]["records_created"] == 0, "값은 다시 쓰지 않는다"
    assert again["summary"]["bindings"] == again["summary"]["records_skipped"] > 0, \
        "건너뛴 레코드도 바인딩돼야 한다"
    assert md.allowed_codes_for_scope("tenant_default", ids["LS_CABLE"]) == set(), \
        "재시드 후에는 다른 법인에 노출되지 않는다"


def test_force_reseeds(stack):
    md, repo, ids = stack
    seed_master_documents(md=md, ecm_repo=repo)
    forced = seed_master_documents(md=md, ecm_repo=repo, force=True)
    assert forced["summary"]["records_created"] > 0, "force 면 개정본으로 다시 적재한다"
