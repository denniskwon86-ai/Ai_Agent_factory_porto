# ==========================================
# [R-001 잔여] 바인딩의 버전 고정 · 적용 기간 평가
#
# 종전에는 `master_version`·`effective_from`·`effective_to` 가 **저장만 되고 아무도 읽지 않았다.**
# 컬럼이 있으니 동작한다고 오해하기 딱 좋은 상태였고, 실제로는
#   · "2026-01-01 부터 이 단가" 로 등록해도 등록 즉시 적용됐고
#   · 종료일이 지나도 계속 적용됐으며
#   · 개정 후에는 "그때 그 값으로 재현"이 불가능했다.
# 이 파일은 그 세 가지가 실제로 동작하는지 본다.
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
    m.create_type("material", "자재")
    m.create_or_revise_record("RM-A", "material", "원료 A",
                              attributes={"price": 100}, domains=["mfg"], is_core=True)
    return m, ids


# ── 적용 기간 ─────────────────────────────────────────────────────────────
def test_binding_not_yet_effective_is_excluded(md):
    """★ 미래 시작일 바인딩이 등록 즉시 적용되면 안 된다."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"], effective_from="2030-01-01T00:00:00+00:00")
    assert m.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"],
                                     as_of="2026-07-29T00:00:00+00:00") == set()
    assert "RM-A" in m.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"],
                                               as_of="2030-06-01T00:00:00+00:00")


def test_binding_past_end_is_excluded(md):
    """★ 종료일이 지난 바인딩이 계속 적용되면 안 된다."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"], effective_to="2026-01-01T00:00:00+00:00")
    assert m.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"],
                                     as_of="2026-07-29T00:00:00+00:00") == set()
    assert "RM-A" in m.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"],
                                               as_of="2025-06-01T00:00:00+00:00")


def test_empty_period_means_unbounded(md):
    """기간 미지정은 '무제한' — 기존 바인딩 44건이 여기 해당하므로 회귀하면 전부 사라진다."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"])
    for t in ("2000-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"):
        assert "RM-A" in m.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"], as_of=t)


def test_end_boundary_is_exclusive(md):
    """경계 규칙: `from <= as_of < to`. 종료 시각 당일은 이미 만료다."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"],
                           effective_from="2026-01-01T00:00:00+00:00",
                           effective_to="2027-01-01T00:00:00+00:00")
    inside = m.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"],
                                       as_of="2026-12-31T23:59:59+00:00")
    edge = m.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"],
                                     as_of="2027-01-01T00:00:00+00:00")
    assert "RM-A" in inside and "RM-A" not in edge


def test_period_applies_to_injection_too(md):
    """★★ 배선 확인 — 판정만 맞고 주입 경로가 이를 무시하면 아무 의미가 없다."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"], effective_to="2026-01-01T00:00:00+00:00")
    sel = m.select_for_injection("원료 A 검토", ["mfg"], "tenant_default",
                                 ids["MNM_BATTERY"], as_of="2026-07-29T00:00:00+00:00")
    assert not any(r["master_code"] == "RM-A" for r in sel), "만료된 바인딩이 주입됐다"


# ── 버전 고정 ─────────────────────────────────────────────────────────────
def test_pinned_version_survives_revision(md):
    """★★ 개정 후에도 고정 버전의 값이 주입돼야 '그때 그 값으로 재현'이 가능하다."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"], master_version=1)
    m.create_or_revise_record("RM-A", "material", "원료 A",
                              attributes={"price": 999}, domains=["mfg"], is_core=True)
    assert m.get_record("RM-A")["attributes"]["price"] == 999      # 현행판은 개정됨

    sel = m.select_for_injection("원료 A", ["mfg"], "tenant_default", ids["MNM_BATTERY"])
    rec = next(r for r in sel if r["master_code"] == "RM-A")
    assert rec["attributes"]["price"] == 100, "고정 버전(v1)이 아니라 현행판이 주입됐다"
    assert rec["pinned_version"] == 1


def test_pinned_version_is_visible_in_the_block(md):
    """★ 고정 사실을 표시하지 않으면 왜 최신값과 다른지 아무도 모른다."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"], master_version=1)
    m.create_or_revise_record("RM-A", "material", "원료 A",
                              attributes={"price": 999}, domains=["mfg"], is_core=True)
    block = m.render_grounding("원료 A", ["mfg"], "tenant_default", ids["MNM_BATTERY"])
    assert "v1 고정" in block and "현행판 아님" in block
    assert "price=100" in block and "price=999" not in block


def test_unpinned_binding_follows_current_version(md):
    """고정하지 않은 바인딩(현재 44건 전부)은 현행판을 따른다 — 회귀 방지."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"])
    m.create_or_revise_record("RM-A", "material", "원료 A",
                              attributes={"price": 999}, domains=["mfg"], is_core=True)
    sel = m.select_for_injection("원료 A", ["mfg"], "tenant_default", ids["MNM_BATTERY"])
    rec = next(r for r in sel if r["master_code"] == "RM-A")
    assert rec["attributes"]["price"] == 999
    assert not rec.get("pinned_version")


def test_pin_does_not_leak_into_other_scopes(md):
    """★ 버전 고정은 그 조직의 바인딩이다. 캐시를 오염시켜 다른 조직까지 구판을 보면 안 된다."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"], master_version=1)
    m.bind_master_to_scope("RM-A", ids["MNM_COPPER"])          # 고정 없음
    m.create_or_revise_record("RM-A", "material", "원료 A",
                              attributes={"price": 999}, domains=["mfg"], is_core=True)

    batt = next(r for r in m.select_for_injection("원료 A", ["mfg"], "tenant_default",
                                                  ids["MNM_BATTERY"]) if r["master_code"] == "RM-A")
    copper = next(r for r in m.select_for_injection("원료 A", ["mfg"], "tenant_default",
                                                    ids["MNM_COPPER"]) if r["master_code"] == "RM-A")
    assert batt["attributes"]["price"] == 100
    assert copper["attributes"]["price"] == 999, "다른 조직이 고정 버전에 오염됐다"


# ── 상속과의 상호작용 ─────────────────────────────────────────────────────
def test_own_node_binding_overrides_inherited(md):
    """★ 하위 조직 바인딩이 상위 상속을 덮는다. 반대면 사업부 특화 값을 전사 값이 밀어낸다."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["LS_MNM"], master_version=1)          # 전사: v1 고정
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"])                       # 사업부: 현행
    m.create_or_revise_record("RM-A", "material", "원료 A",
                              attributes={"price": 999}, domains=["mfg"], is_core=True)

    binds = m.bindings_for_scope("tenant_default", ids["MNM_BATTERY"])
    assert binds["RM-A"] is None, "사업부의 미고정 바인딩이 전사의 v1 고정을 덮어야 한다"
    other = m.bindings_for_scope("tenant_default", ids["MNM_COPPER"])
    assert other["RM-A"] == 1, "동제련은 전사 상속을 그대로 받아 v1 고정"


# ── 격리 관측 ─────────────────────────────────────────────────────────────
def test_coverage_reports_unbound_exposure(md):
    """★★ 미바인딩 = 전 조직 노출. 조용한 노출이 위험한 것이지 규칙이 위험한 게 아니다."""
    m, ids = md
    cov = m.scope_coverage()
    assert cov["exposed_records"] == 1 and "RM-A" in cov["exposed_codes"]
    assert cov["coverage_ratio"] == 0.0

    b = m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"])
    cov = m.scope_coverage()
    assert cov["exposed_records"] == 0 and cov["coverage_ratio"] == 1.0
    assert cov["by_scope_node"][ids["MNM_BATTERY"]] == 1

    m.unbind_master_from_scope(b["binding_id"])
    assert m.scope_coverage()["exposed_records"] == 1, "해제하면 다시 노출로 잡혀야 한다"


def test_coverage_ignores_retired_records(md):
    """폐기된 레코드는 주입되지 않으므로 노출로 세면 안 된다(허위 경보)."""
    m, ids = md
    m.retire_record("RM-A")
    assert m.scope_coverage()["exposed_records"] == 0


# ── 해제 ──────────────────────────────────────────────────────────────────
def test_unbind_is_soft_and_removes_from_scope(md):
    """해제는 소프트 삭제다 — "언제 무엇이 적용됐었나"는 감사 대상이라 지우지 않는다."""
    m, ids = md
    b = m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"])
    assert "RM-A" in m.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"])

    assert m.unbind_master_from_scope(b["binding_id"]) is True
    assert m.unbind_master_from_scope(b["binding_id"]) is False, "이미 해제된 것은 False"
    assert "RM-A" not in m.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"])
    rows = m.list_scope_bindings(master_code="RM-A")
    assert not rows, "활성 목록에서는 사라진다"


def test_unbind_last_binding_hides_record_everywhere(md):
    """★★ [관문 A · 2026-07-30] 마지막 바인딩을 풀면 그 레코드는 **어디에서도 주입되지 않는다.**

    종전에는 정반대였다 — 해제하면 "미바인딩 = 전사 공통"이 되어 **전 조직에 노출**됐고,
    그래서 "해제했으니 안전하다"는 직관이 실제로는 유출이었다. 관문 A 로 그 함정이 사라졌다.
    이제 해제는 차단과 같은 방향으로 작동하므로 운영자의 직관과 시스템 동작이 일치한다.

    ⚠️ 반대편 위험이 새로 생긴다 — 실수로 해제하면 그 기준정보가 조용히 프롬프트에서
      사라진다. 그래서 `select_for_injection` 이 `excluded_unbound` 로 건수를 보고하고
      `render_grounding` 이 그 사실을 블록에 적는다(여기서 함께 잠근다)."""
    m, ids = md
    b = m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"])
    assert not any(r["master_code"] == "RM-A" for r in
                   m.select_for_injection("원료", ["mfg"], "tenant_default", ids["MNM_COPPER"]))

    m.unbind_master_from_scope(b["binding_id"])
    got, stats = m.select_for_injection("원료", ["mfg"], "tenant_default",
                                        ids["MNM_BATTERY"], with_stats=True)
    assert not any(r["master_code"] == "RM-A" for r in got), \
        "해제된 레코드가 여전히 주입된다 — 해제가 통제로 작동하지 않는다"
    assert stats["excluded_unbound"] >= 1, \
        "해제로 빠진 건수가 보고되지 않는다 — 실수로 해제하면 조용히 사라진다"


def test_overlapping_periods_resolve_deterministically(md):
    """★ 같은 노드에 기간이 겹치는 바인딩이 둘이면 **늦게 시작한 것이 이긴다**.
    순회 순서에 맡기면 같은 입력에 다른 결과가 나온다."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"], master_version=1,
                           effective_from="2026-01-01T00:00:00+00:00")
    m.bind_master_to_scope("RM-A", ids["MNM_BATTERY"], master_version=2,
                           effective_from="2026-06-01T00:00:00+00:00")
    at = "2026-07-29T00:00:00+00:00"
    for _ in range(3):                                   # 같은 입력 → 같은 결과
        assert m.bindings_for_scope("tenant_default", ids["MNM_BATTERY"], as_of=at)["RM-A"] == 2
    assert m.bindings_for_scope("tenant_default", ids["MNM_BATTERY"],
                                as_of="2026-03-01T00:00:00+00:00")["RM-A"] == 1


def test_expired_inherited_binding_does_not_reach_child(md):
    """만료된 상위 바인딩이 하위로 상속되면 안 된다."""
    m, ids = md
    m.bind_master_to_scope("RM-A", ids["LS_MNM"], effective_to="2026-01-01T00:00:00+00:00")
    assert m.allowed_codes_for_scope("tenant_default", ids["MNM_BATTERY"],
                                     as_of="2026-07-29T00:00:00+00:00") == set()
