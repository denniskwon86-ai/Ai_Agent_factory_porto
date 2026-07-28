# ==========================================
# [§14 M1 「MDM 확장 — 중복 후보」] 같은 대상이 두 벌로 존재하는 것을 찾아낸다
#
# 왜 필요한가: 실제 개발 DB 에서 같은 대상이 두 벌 있었다
#   BOM-FG-CATHODE-001 ↔ M2-BOM-FG-CATHODE-001 / QC-FG-NISO4-001 ↔ M1-QS-FG-NISO4-001
# 둘 다 활성이면 **둘 다 주입되어 LLM 이 서로 다른 두 기준값을 동시에 본다.**
# 기준정보의 존재 이유를 정면으로 깨는 상태인데 아무도 탐지하지 못하고 있었다.
#
# 이 탐지기의 원칙(품질 점검과 동일):
#   ① 자동 병합하지 않는다 — 정본 판단은 현업 몫이고 시스템이 지우면 되돌릴 수 없다
#   ② LLM 0콜 — 코드·명칭·별칭의 문자열 비교뿐
#   ③ **오탐에 다른 조치를 안내한다** — 틀린 조치를 유도하면 안 하느니만 못하다
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.enterprise_context import EcmRepository, EcmResolver
from core.enterprise_context.seed import seed_example_organization
from core.master_data import MasterData


@pytest.fixture
def md(tmp_path, monkeypatch):
    repo = EcmRepository(db_path=str(tmp_path / "ecm.db"))
    ids = seed_example_organization(repo)["node_ids"]
    import core.enterprise_context.resolver as res_mod
    monkeypatch.setattr(res_mod, "ecm_resolver", EcmResolver(repo))
    m = MasterData(db_path=str(tmp_path / "master.db"))
    for t in ("material", "bom", "quality-spec", "finance-param"):
        m.create_type(t, t)
    return m, ids


def _pair(rows, a, b):
    want = sorted((a, b))
    return next((r for r in rows if r["codes"] == want), None)


# ── 탐지 ──────────────────────────────────────────────────────────────────
def test_prefix_only_difference_is_high_confidence(md):
    """★★ 실제로 있었던 사례 — 문서 출처 접두사만 다른 같은 대상."""
    m, ids = md
    m.create_or_revise_record("BOM-FG-NISO4-001", "bom", "황산니켈 BOM", attributes={"qty": 1})
    m.create_or_revise_record("M1-BOM-FG-NISO4-001", "bom", "FG-NiSO4-001 BOM",
                              attributes={"qty": 1})
    hit = _pair(m.find_duplicate_candidates(), "BOM-FG-NISO4-001", "M1-BOM-FG-NISO4-001")
    assert hit and hit["confidence"] == "high"
    assert hit["kind"] == "same_normalized_code"
    assert "폐기" in hit["suggested_action"]


def test_qs_and_qc_are_recognised_as_the_same(md):
    """`QS`/`QC` 처럼 같은 뜻의 약어가 갈리면 사람 눈에도 잘 안 띈다."""
    m, ids = md
    m.create_or_revise_record("QC-FG-NISO4-001", "quality-spec", "품질 A", attributes={"cpk": 1.3})
    m.create_or_revise_record("M1-QS-FG-NISO4-001", "quality-spec", "품질 B", attributes={"cpk": 1.3})
    assert _pair(m.find_duplicate_candidates(), "QC-FG-NISO4-001", "M1-QS-FG-NISO4-001")


def test_same_name_different_code_is_detected(md):
    """코드가 전혀 달라도 정규화 명칭이 같으면 후보다."""
    m, ids = md
    m.create_or_revise_record("EF-ELEC", "material", "Electricity (Grid)", attributes={})
    m.create_or_revise_record("M3-EMIS-01", "material", "Electricity", attributes={})
    hit = _pair(m.find_duplicate_candidates(), "EF-ELEC", "M3-EMIS-01")
    assert hit and hit["kind"] == "same_name" and hit["confidence"] == "high"


def test_findings_carry_evidence_and_action(md):
    m, ids = md
    m.create_or_revise_record("BOM-X", "bom", "X BOM", attributes={})
    m.create_or_revise_record("M1-BOM-X", "bom", "X 소요량", attributes={})
    for f in m.find_duplicate_candidates():
        assert f["why"] and f["suggested_action"] and f["names"] and f["codes"]
        assert f["confidence"] in ("high", "medium", "low")


# ── 오탐 방지 — 여기가 이 탐지기의 값어치를 정한다 ─────────────────────────
def test_division_specific_records_are_not_flagged_as_duplicates(md):
    """★★ `M1-FIN-COST-STRUCTURE`(배터리소재)와 `M2-FIN-COST-STRUCTURE`(동제련)는
    **중복이 아니라 의도된 사업부별 분리**다. 접두사를 무조건 벗기면 두 사업부를 뭉갠다.
    "정본을 정해 하나를 폐기하라"는 조치가 여기서는 **데이터 손실을 유도한다.**"""
    m, ids = md
    m.create_or_revise_record("M1-FIN-COST-STRUCTURE", "finance-param", "원가구조", attributes={"a": 1})
    m.create_or_revise_record("M2-FIN-COST-STRUCTURE", "finance-param", "원가구조", attributes={"a": 2})
    m.bind_master_to_scope("M1-FIN-COST-STRUCTURE", ids["MNM_BATTERY"])
    m.bind_master_to_scope("M2-FIN-COST-STRUCTURE", ids["MNM_COPPER"])

    hit = _pair(m.find_duplicate_candidates(), "M1-FIN-COST-STRUCTURE", "M2-FIN-COST-STRUCTURE")
    assert hit and hit["kind"] == "same_code_different_scope" and hit["confidence"] == "low"
    assert "병합하지 마십시오" in hit["suggested_action"]


def test_same_scope_duplicates_stay_high(md):
    """같은 조직에 둘 다 적용 중이면 진짜 문제다 — 두 기준값이 함께 주입된다."""
    m, ids = md
    m.create_or_revise_record("M1-FIN-X", "finance-param", "X", attributes={"a": 1})
    m.create_or_revise_record("M2-FIN-X", "finance-param", "X", attributes={"a": 2})
    m.bind_master_to_scope("M1-FIN-X", ids["MNM_BATTERY"])
    m.bind_master_to_scope("M2-FIN-X", ids["MNM_BATTERY"])
    hit = _pair(m.find_duplicate_candidates(), "M1-FIN-X", "M2-FIN-X")
    assert hit["confidence"] == "high" and "폐기" in hit["suggested_action"]


def test_shared_alias_across_types_is_not_called_a_duplicate(md):
    """★ 같은 제품의 BOM 과 품질규격이 제품ID 를 별칭으로 공유하는 것은 정상이다.
    여기에 '하나를 폐기하라'고 안내하면 **틀린 조치를 유도한다.**"""
    m, ids = md
    m.create_or_revise_record("M1-BOM-FG-A", "bom", "A BOM", attributes={},
                              aliases=["FG-A-001"])
    m.create_or_revise_record("M1-QS-FG-A", "quality-spec", "A 품질규격", attributes={},
                              aliases=["FG-A-001"])
    hit = _pair(m.find_duplicate_candidates(), "M1-BOM-FG-A", "M1-QS-FG-A")
    assert hit and hit["kind"] == "shared_alias" and hit["confidence"] == "low"
    assert "폐기" not in hit["suggested_action"]
    assert "별칭" in hit["suggested_action"]


def test_no_false_positive_on_distinct_records(md):
    """서로 무관한 레코드는 후보로 올리지 않는다 — 노이즈가 많으면 아무도 안 본다."""
    m, ids = md
    m.create_or_revise_record("RM-MHP-001", "material", "Mixed Hydroxide Precipitate",
                              attributes={}, aliases=["MHP"])
    m.create_or_revise_record("RM-CUCON-001", "material", "Copper Concentrate",
                              attributes={}, aliases=["정광"])
    assert m.find_duplicate_candidates() == []


def test_retired_records_are_not_candidates(md):
    """폐기로 이미 해결한 중복이 계속 뜨면 목록을 신뢰하지 않게 된다."""
    m, ids = md
    m.create_or_revise_record("BOM-Y", "bom", "Y", attributes={})
    m.create_or_revise_record("M1-BOM-Y", "bom", "Y", attributes={})
    assert m.find_duplicate_candidates()
    m.retire_record("BOM-Y")
    assert m.find_duplicate_candidates() == []


def test_detection_does_not_mutate_anything(md):
    """★ 자동 병합·자동 폐기 금지 — 정본 판단은 현업 몫이다."""
    m, ids = md
    m.create_or_revise_record("BOM-Z", "bom", "Z", attributes={"v": 1})
    m.create_or_revise_record("M1-BOM-Z", "bom", "Z", attributes={"v": 2})
    before = {r["master_code"]: r["attributes"] for r in m.list_records()}
    m.find_duplicate_candidates()
    after = {r["master_code"]: r["attributes"] for r in m.list_records()}
    assert before == after and len(after) == 2
