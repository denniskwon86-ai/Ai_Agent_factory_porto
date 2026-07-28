# ==========================================
# 기준정보 조직 범위 바인딩 (R-001 / DECISIONS.md D-009)
# — Antigravity 감사 Finding 1 + Codex 교차검토 보완
#
# ## 왜 필요한가
#
# 감사 Finding 1: M1~M4 기준정보에 "어느 법인·사업부·공장의 것인가"가 없어 전역 고립 데이터가
# 되고 부서별 권한 제어가 불가능하다. 실측으로 확인: `_load_cache()` 는 전체 활성 레코드를 담고
# `get_master_context()` 는 `domains` 필터만 써서 **A 법인 기준정보가 B 법인 프롬프트에 섞인다.**
#
# ## 검증하는 계약 여섯
#  ① ★ **원본 1 : 적용범위 N** — 동일 자재·공통 설비·환율 기준을 여러 법인·공장이 함께 참조한다.
#     `master_records` 에 컬럼을 추가하는 방식(내 초안)은 1:1 이 되어 이걸 표현할 수 없었다.
#  ② **본문은 MDM 에만 있다** — `enterprise_profiles` 로 복사하지 않는다(진실원본 모호 방지).
#  ③ **점진 도입** — 바인딩이 없는 레코드는 전사 공통으로 통과. 전부 막으면 바인딩 전 기능이 멈춘다.
#     바인딩을 하나 넣는 순간 그 레코드는 즉시 통제 대상이 된다(fail-closed 전환).
#  ④ **상속은 운영 계층만** — `inherit_descendants` 로 하위에 적용. 공유서비스·연결집계 관계는
#     적용 범위를 만들지 않는다(D-003 유지).
#  ⑤ ★ **캐시 오염이 없다** — 캐시는 '전체 레코드'를 담고 필터는 요청마다 적용되므로 A 법인
#     요청이 B 법인 결과를 오염시킬 수 없다.
#  ⑥ **적용 가능성 ≠ 열람 권한** — 바인딩은 "이 조직에 쓰이는가"이고 사용자 권한은 ECM 이 판정한다.
# ==========================================
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.master_data import MasterData, MasterDataError


@pytest.fixture
def md(tmp_path):
    m = MasterData(db_path=str(tmp_path / "master.db"))
    m.create_type("material", "자재")
    m.create_type("equipment", "설비")
    return m


def _rec(md, code, name, type_id="material", domains=None, is_core=True, aliases=None):
    md.create_or_revise_record(code, type_id, name, attributes={},
                               domains=domains or ["manufacturing"], is_core=is_core)
    if aliases:
        md.add_aliases(code, list(aliases))
    return code


# ── ① 원본 1 : 적용범위 N ────────────────────────────────────────────────
def test_one_record_many_scopes(md):
    """★★ 동일 자재를 여러 공장이 함께 참조한다 — 컬럼 방식으로는 불가능한 구조."""
    _rec(md, "MAT-CU", "전기동")
    md.bind_master_to_scope("MAT-CU", "node_plant_1")
    md.bind_master_to_scope("MAT-CU", "node_plant_2")
    md.bind_master_to_scope("MAT-CU", "node_plant_3")
    bindings = md.list_scope_bindings(master_code="MAT-CU")
    assert len(bindings) == 3
    assert {b["scope_node_id"] for b in bindings} == {"node_plant_1", "node_plant_2", "node_plant_3"}


def test_binding_is_idempotent(md):
    _rec(md, "MAT-CU", "전기동")
    md.bind_master_to_scope("MAT-CU", "node_plant_1")
    md.bind_master_to_scope("MAT-CU", "node_plant_1")
    assert len(md.list_scope_bindings(master_code="MAT-CU")) == 1


def test_unknown_master_code_rejected(md):
    with pytest.raises(MasterDataError):
        md.bind_master_to_scope("MAT-GHOST", "node_plant_1")


def test_missing_args_rejected(md):
    _rec(md, "MAT-CU", "전기동")
    with pytest.raises(MasterDataError):
        md.bind_master_to_scope("", "node_plant_1")
    with pytest.raises(MasterDataError):
        md.bind_master_to_scope("MAT-CU", "")


def test_virtual_mode_binding_blocked(md):
    """가상·경쟁사 문맥의 기준정보 적용은 격리 스냅샷(E3) 이후다(D-007)."""
    _rec(md, "MAT-CU", "전기동")
    with pytest.raises(MasterDataError):
        md.bind_master_to_scope("MAT-CU", "node_plant_1", entity_mode="VIRTUAL")


# ── ③ 점진 도입: 바인딩 없으면 통과, 있으면 지킨다 ────────────────────────
def test_unbound_record_passes_everywhere(md):
    """★ 전부 막으면 바인딩을 넣기 전에 기능이 통째로 멈춘다(Phase 3·5 와 같은 판단)."""
    _rec(md, "MAT-FREE", "공통자재", aliases=["공통자재"])
    got = md.select_for_injection("공통자재 사용", ["manufacturing"],
                                  tenant_id="t1", scope_node_id="node_any")
    assert [r["master_code"] for r in got] == ["MAT-FREE"]


def test_bound_record_is_scoped(md):
    """★★ 바인딩을 하나 넣는 순간 그 레코드는 통제 대상이 된다."""
    _rec(md, "MAT-A", "A법인자재", aliases=["A법인자재"])
    md.bind_master_to_scope("MAT-A", "node_a", tenant_id="t1")

    inside = md.select_for_injection("A법인자재 검토", ["manufacturing"],
                                     tenant_id="t1", scope_node_id="node_a")
    assert [r["master_code"] for r in inside] == ["MAT-A"]

    outside = md.select_for_injection("A법인자재 검토", ["manufacturing"],
                                      tenant_id="t1", scope_node_id="node_b")
    assert outside == [], "다른 조직 범위에서는 주입되지 않는다"


def test_no_scope_means_no_filter(md):
    """범위 미지정(ECM 미도입 흐름)은 종전대로 전량 — 하위호환."""
    _rec(md, "MAT-A", "A법인자재", aliases=["A법인자재"])
    md.bind_master_to_scope("MAT-A", "node_a")
    got = md.select_for_injection("A법인자재 검토", ["manufacturing"])
    assert [r["master_code"] for r in got] == ["MAT-A"]


def test_tenant_isolation(md):
    """★ 같은 노드 id 라도 테넌트가 다르면 적용되지 않는다."""
    _rec(md, "MAT-A", "테넌트자재", aliases=["테넌트자재"])
    md.bind_master_to_scope("MAT-A", "node_x", tenant_id="t_a")
    assert md.select_for_injection("테넌트자재", ["manufacturing"],
                                   tenant_id="t_a", scope_node_id="node_x")
    assert md.select_for_injection("테넌트자재", ["manufacturing"],
                                   tenant_id="t_b", scope_node_id="node_x") == []


# ── ⑤ 캐시 오염 없음 ─────────────────────────────────────────────────────
def test_cache_is_not_poisoned_across_scopes(md):
    """★★ 캐시는 '전체 레코드'를 담고 필터는 요청마다 적용된다 — A 법인 요청이 B 를 오염시킬 수 없다."""
    _rec(md, "MAT-A", "가자재", aliases=["가자재"])
    _rec(md, "MAT-B", "나자재", aliases=["나자재"])
    md.bind_master_to_scope("MAT-A", "node_a")
    md.bind_master_to_scope("MAT-B", "node_b")

    # A 범위로 먼저 조회해 캐시를 채운다
    a1 = md.select_for_injection("가자재 나자재", ["manufacturing"],
                                 tenant_id="tenant_default", scope_node_id="node_a")
    assert [r["master_code"] for r in a1] == ["MAT-A"]
    # 이어서 B 범위 — 캐시가 오염됐다면 MAT-A 가 섞여 나온다
    b1 = md.select_for_injection("가자재 나자재", ["manufacturing"],
                                 tenant_id="tenant_default", scope_node_id="node_b")
    assert [r["master_code"] for r in b1] == ["MAT-B"]
    # 다시 A — 여전히 A 만
    a2 = md.select_for_injection("가자재 나자재", ["manufacturing"],
                                 tenant_id="tenant_default", scope_node_id="node_a")
    assert [r["master_code"] for r in a2] == ["MAT-A"]


def test_binding_change_invalidates(md):
    """바인딩이 바뀌면 주입 결과가 바뀌어야 한다(캐시가 낡으면 통제가 늦게 걸린다)."""
    _rec(md, "MAT-A", "가자재", aliases=["가자재"])
    before = md.select_for_injection("가자재", ["manufacturing"],
                                     tenant_id="tenant_default", scope_node_id="node_b")
    assert [r["master_code"] for r in before] == ["MAT-A"], "바인딩 전엔 전사 공통"
    md.bind_master_to_scope("MAT-A", "node_a")
    after = md.select_for_injection("가자재", ["manufacturing"],
                                    tenant_id="tenant_default", scope_node_id="node_b")
    assert after == [], "바인딩 후에는 범위 밖에서 사라진다"


# ── ④ 상속 ───────────────────────────────────────────────────────────────
def test_inheritance_uses_operating_ancestors(md, monkeypatch):
    """상위 조직에 걸린 상속 바인딩이 하위 노드에 적용된다."""
    _rec(md, "MAT-CORP", "전사표준자재", aliases=["전사표준자재"])
    md.bind_master_to_scope("MAT-CORP", "node_corp", inherit_descendants=True)

    import core.enterprise_context.resolver as res_mod

    class _Stub:
        def ancestors(self, node_id, relation_type=None):
            return ["node_corp"] if node_id == "node_plant" else []
    monkeypatch.setattr(res_mod, "ecm_resolver", _Stub())

    got = md.select_for_injection("전사표준자재", ["manufacturing"],
                                  tenant_id="tenant_default", scope_node_id="node_plant")
    assert [r["master_code"] for r in got] == ["MAT-CORP"]


def test_non_inheritable_binding_does_not_reach_children(md, monkeypatch):
    """`inherit_descendants=False` 면 그 조직만 — 본사 전용 기준이 공장에 흘러가지 않는다."""
    _rec(md, "MAT-HQ", "본사전용자재", aliases=["본사전용자재"])
    md.bind_master_to_scope("MAT-HQ", "node_corp", inherit_descendants=False)

    import core.enterprise_context.resolver as res_mod

    class _Stub:
        def ancestors(self, node_id, relation_type=None):
            return ["node_corp"] if node_id == "node_plant" else []
    monkeypatch.setattr(res_mod, "ecm_resolver", _Stub())

    assert md.select_for_injection("본사전용자재", ["manufacturing"],
                                   tenant_id="tenant_default", scope_node_id="node_plant") == []
    assert md.select_for_injection("본사전용자재", ["manufacturing"],
                                   tenant_id="tenant_default", scope_node_id="node_corp")


def test_resolver_failure_does_not_block_injection(md, monkeypatch):
    """범위 해석이 죽어도 주입은 계속된다(다만 필터가 걸리지 않으므로 자기 노드만 적용)."""
    _rec(md, "MAT-A", "가자재", aliases=["가자재"])
    md.bind_master_to_scope("MAT-A", "node_a")

    import core.enterprise_context.resolver as res_mod

    class _Broken:
        def ancestors(self, *a, **kw):
            raise RuntimeError("resolver 장애")
    monkeypatch.setattr(res_mod, "ecm_resolver", _Broken())

    assert md.select_for_injection("가자재", ["manufacturing"],
                                   tenant_id="tenant_default", scope_node_id="node_a")


# ── ② 본문은 MDM 에만 ────────────────────────────────────────────────────
def test_binding_stores_no_master_body(md):
    """★ 바인딩 테이블에 기준정보 본문이 들어가면 진실원본이 둘이 된다(ECM §8.2)."""
    import sqlite3
    _rec(md, "MAT-CU", "전기동")
    md.bind_master_to_scope("MAT-CU", "node_a")
    with sqlite3.connect(md.db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(master_scope_bindings)")}
    assert "payload" not in cols and "attributes" not in cols and "name" not in cols
    assert "master_code" in cols, "본문이 아니라 참조만 갖는다"


# ── 주입 경로 배선 (★ 이 세션에서 반복된 결함 유형) ────────────────────────
def test_get_master_context_passes_scope(md, monkeypatch):
    """★★ 상태의 문맥이 실제로 필터까지 전달되는가. 안 되면 필터가 조용히 무력화된다."""
    from state_models import ProjectState
    _rec(md, "MAT-A", "가자재", aliases=["가자재"])
    md.bind_master_to_scope("MAT-A", "node_a", tenant_id="tenant_default")

    import core.enterprise_context.resolver as res_mod

    class _Stub:
        def resolve_scope_ref(self, ref):
            return {"node_id": ref, "kind": "ecm_node"}

        def ancestors(self, *a, **kw):
            return []
    monkeypatch.setattr(res_mod, "ecm_resolver", _Stub())

    inside = ProjectState.model_validate({
        "project_name": "P", "initial_idea": "가자재 검토", "master_domains": ["manufacturing"],
        "tenant_id": "tenant_default", "enterprise_scope_id": "node_a"})
    assert "MAT-A" in md.get_master_context(inside)

    outside = ProjectState.model_validate({
        "project_name": "P", "initial_idea": "가자재 검토", "master_domains": ["manufacturing"],
        "tenant_id": "tenant_default", "enterprise_scope_id": "node_b"})
    assert md.get_master_context(outside) == "", "다른 범위에는 주입되지 않는다"


def test_state_model_accepts_context_fields():
    """ProjectState 는 extra='forbid' 라 선언이 없으면 ValidationError 로 즉사한다."""
    from state_models import ProjectState
    s = ProjectState.model_validate({"project_name": "P", "tenant_id": "t1",
                                     "enterprise_scope_id": "node_1", "entity_mode": "REAL"})
    assert s.tenant_id == "t1" and s.enterprise_scope_id == "node_1"


def test_context_fields_are_accumulated():
    """문맥이 스프린트 사이에 유실되면 범위 필터가 풀린다(다시 채워줄 곳이 없다)."""
    import api.routes.factory_control as fc
    for f in ("tenant_id", "enterprise_scope_id", "entity_mode"):
        assert f in fc._ACCUMULATED_FIELDS
