"""★★★ [ECM E2 잔여] 에이전트팩 바인딩 — **어떤 조직에서 어떤 에이전트가 도는가.**

## 왜 필요했나

에이전트 구성이 `departments.domain_agents` 라는 **부서별 평면 목록**이었다. 전사 표준 에이전트
하나를 추가하려면 모든 부서의 목록을 각각 고쳐야 하고, 한 곳을 빠뜨리면 그 부서만 조용히 다른
구성으로 돈다 — 이 저장소가 하드코딩 맵 3개에서 겪은 문제와 같은 형태다
(`org_seed`: "세 맵이 서로 어긋나도 아무도 알아채지 못했다").

그리고 "이 에이전트가 왜 도는가"에 답할 수 없었다. 목록에 이름이 있다는 사실 외에 근거가 없다.

## 이 파일이 지키는 계약

1. 승인된 팩만 바인딩·해석에 쓴다.
2. 상속은 `OPERATING_PARENT` 조상 체인만 따라간다(`CONSOLIDATION_SCOPE` 금지 — 다른 법인의
   구성이 넘어온다).
3. 만료·비상속 바인딩은 해석에서 빠지고 **왜 빠졌는지** 남는다.
4. 해석 결과가 비면 "바인딩이 없다"고 말한다(에이전트가 없는 것과 구분한다).
5. **실행 경로에 실제로 배선돼 있다** — 판정 함수만 만들고 부르지 않으면 장식이다.
"""
import pytest

from core.enterprise_context.agent_pack_binding import AgentPackError, AgentPackStore
from core.enterprise_context.clone_service import CloneService
from core.enterprise_context.models import EnterpriseEntity, OrganizationEdge, OrganizationNode
from core.enterprise_context.repository import EcmRepository
from core.enterprise_context.resolver import EcmResolver

TODAY = "2026-08-03"


@pytest.fixture
def repo(tmp_path):
    return EcmRepository(db_path=str(tmp_path / "ecm.db"))


@pytest.fixture
def store(repo):
    return AgentPackStore(repository=repo, resolver=EcmResolver(repo),
                          clone=CloneService(repository=repo))


@pytest.fixture
def org(repo):
    """전사 → 사업부 → 공장(운영 계층) + 다른 법인(집계 관계)."""
    def _n(name, code, ntype="business_division"):
        e = repo.upsert_entity(EnterpriseEntity(entity_type=ntype, entity_mode="REAL",
                                                name_ko=name))
        return repo.upsert_node(OrganizationNode(entity_id=e.entity_id, node_type=ntype,
                                                 code=code, name_ko=name, status="ACTIVE"))
    top = _n("LS MnM", "LS_MNM", "legal_entity")
    div = _n("배터리소재 사업부", "MNM_BATTERY")
    plant = _n("제1공장", "BATT_PLANT_1", "site_plant")
    other = _n("LS전선", "LS_CABLE", "legal_entity")
    repo.add_edge(OrganizationEdge(from_node_id=top.node_id, to_node_id=div.node_id,
                                   relation_type="OPERATING_PARENT"))
    repo.add_edge(OrganizationEdge(from_node_id=div.node_id, to_node_id=plant.node_id,
                                   relation_type="OPERATING_PARENT"))
    repo.add_edge(OrganizationEdge(from_node_id=top.node_id, to_node_id=other.node_id,
                                   relation_type="CONSOLIDATION_SCOPE"))
    return {"top": top, "div": div, "plant": plant, "other": other}


def _approved(store, name, agents, actor="hikwon"):
    p = store.create_pack(name, f"{name} 목적", agents, actor=actor)
    return store.approve_pack(p["pack_id"], actor)


# ── 팩 ────────────────────────────────────────────────────────────────────
def test_pack_requires_name_purpose_agents(store):
    """★ 목적 없는 구성은 나중에 누구도 손대지 못한다."""
    with pytest.raises(AgentPackError):
        store.create_pack("", "목적", ["a"])
    with pytest.raises(AgentPackError, match="목적"):
        store.create_pack("팩", "", ["a"])
    with pytest.raises(AgentPackError, match="비어"):
        store.create_pack("팩", "목적", [])


def test_duplicate_agents_in_a_pack_are_refused(store):
    """★ 같은 에이전트가 팩 안에 두 번 있으면 실행 순서 해석이 흔들린다."""
    with pytest.raises(AgentPackError, match="중복"):
        store.create_pack("팩", "목적", ["a", "b", "a"])


def test_unapproved_pack_cannot_be_bound(store, org):
    """★★★ 승인되지 않은 팩을 바인딩하면 **검증되지 않은 에이전트가 산출물을 만든다.**"""
    p = store.create_pack("초안팩", "목적", ["planner"])
    with pytest.raises(AgentPackError, match="승인되지 않은 팩"):
        store.bind(p["pack_id"], org["div"].node_id)


# ── 상속 ──────────────────────────────────────────────────────────────────
def test_enterprise_pack_is_inherited_downward(store, org):
    """★★★ **이 모듈의 목적.** 전사에 한 번 바인딩하면 하위 조직이 상속한다 —
    부서마다 목록을 고치지 않아도 된다."""
    pk = _approved(store, "전사 표준", ["reviewer", "auditor"])
    store.bind(pk["pack_id"], org["top"].node_id, actor="hikwon")

    r = store.resolve_agents(org["plant"].node_id, today=TODAY)
    assert r["agents"] == ["reviewer", "auditor"]
    assert r["bound"] is True and r["note"] == ""
    assert r["provenance"]["reviewer"][0]["how"].startswith("상속")


def test_enterprise_then_own_order(store, org):
    """★★ 전사 표준이 먼저, 조직 고유 구성이 뒤 — 읽는 사람이 이해하는 순서다."""
    ent = _approved(store, "전사 표준", ["reviewer"])
    own = _approved(store, "배터리 전용", ["battery_specialist"])
    store.bind(ent["pack_id"], org["top"].node_id)
    store.bind(own["pack_id"], org["div"].node_id)

    r = store.resolve_agents(org["div"].node_id, today=TODAY)
    assert r["agents"] == ["reviewer", "battery_specialist"]
    assert r["provenance"]["battery_specialist"][0]["how"] == "직접"


def test_same_agent_from_two_packs_is_counted_once_but_both_recorded(store, org):
    """★★★ 중복은 한 번만 세지만 **어느 팩에서 왔는지는 전부 남긴다** — 구성을 고칠 때 어디를
    고쳐야 하는지 알아야 한다."""
    a = _approved(store, "전사 표준", ["reviewer"])
    b = _approved(store, "사업부 표준", ["reviewer", "planner"])
    store.bind(a["pack_id"], org["top"].node_id)
    store.bind(b["pack_id"], org["div"].node_id)

    r = store.resolve_agents(org["div"].node_id, today=TODAY)
    assert r["agents"] == ["reviewer", "planner"]
    assert len(r["provenance"]["reviewer"]) == 2, "두 팩에서 왔다는 사실이 사라졌다"


def test_consolidation_edges_do_not_carry_agents(store, org):
    """★★★ 지분 집계 관계를 따라가면 **다른 법인의 구성이 넘어온다.** 복제 범위에서와 같은 금지다."""
    pk = _approved(store, "LS MnM 표준", ["mnm_agent"])
    store.bind(pk["pack_id"], org["top"].node_id)
    r = store.resolve_agents(org["other"].node_id, today=TODAY)
    assert r["agents"] == [] and r["bound"] is False


def test_inherit_flag_false_stops_inheritance(store, org):
    """★★ 상속 안 함으로 바인딩하면 하위에 내려가지 않고, **왜 빠졌는지** 남는다."""
    pk = _approved(store, "본사 전용", ["hq_only"])
    store.bind(pk["pack_id"], org["top"].node_id, inherit_descendants=False)

    own = store.resolve_agents(org["top"].node_id, today=TODAY)
    assert own["agents"] == ["hq_only"], "자기 조직에는 적용돼야 한다"
    child = store.resolve_agents(org["div"].node_id, today=TODAY)
    assert child["agents"] == []
    assert any("상속 안 함" in s["why"] for s in child["skipped"])


# ── 유효기간 ──────────────────────────────────────────────────────────────
def test_expired_binding_is_excluded_with_a_reason(store, org):
    """★★★ 기간을 두고 지키지 않으면 기간은 장식이다. 빠진 이유를 남긴다."""
    pk = _approved(store, "한시 구성", ["temp_agent"])
    store.bind(pk["pack_id"], org["div"].node_id,
               effective_from="2026-01-01", effective_to="2026-06-30")
    r = store.resolve_agents(org["div"].node_id, today=TODAY)
    assert r["agents"] == []
    assert any("유효기간 밖" in s["why"] for s in r["skipped"])


def test_future_binding_is_not_active_yet(store, org):
    """★ 시작 전 바인딩은 아직 적용되지 않는다."""
    pk = _approved(store, "예약 구성", ["future_agent"])
    store.bind(pk["pack_id"], org["div"].node_id, effective_from="2099-01-01")
    assert store.resolve_agents(org["div"].node_id, today=TODAY)["agents"] == []


def test_broken_period_does_not_apply(store, org):
    """★★ 형식이 깨진 기간은 **적용하지 않는다** — 해석 불가를 통과시키면 통제가 사라진다."""
    pk = _approved(store, "깨진 기간", ["x"])
    store.bind(pk["pack_id"], org["div"].node_id, effective_from="2026-13-99")
    r = store.resolve_agents(org["div"].node_id, today=TODAY)
    assert r["agents"] == [] and any("유효기간" in s["why"] for s in r["skipped"])


def test_reversed_period_is_refused_at_bind_time(store, org):
    """★ 거꾸로 된 기간은 저장 시점에 막는다(나중에 조용히 안 도는 것보다 낫다)."""
    pk = _approved(store, "역기간", ["x"])
    with pytest.raises(AgentPackError, match="거꾸로"):
        store.bind(pk["pack_id"], org["div"].node_id,
                   effective_from="2026-06-30", effective_to="2026-01-01")


# ── 해제·미바인딩 ─────────────────────────────────────────────────────────
def test_unbind_is_soft_and_removes_from_resolution(store, org):
    """★★ 해제는 소프트다 — "언제 무엇이 이 조직에서 돌았나"는 산출물의 근거다."""
    pk = _approved(store, "표준", ["a"])
    b = store.bind(pk["pack_id"], org["div"].node_id)
    assert store.resolve_agents(org["div"].node_id, today=TODAY)["agents"] == ["a"]
    assert store.unbind(b["binding_id"], actor="hikwon") is True
    assert store.resolve_agents(org["div"].node_id, today=TODAY)["agents"] == []
    assert store.list_bindings(scope_node_id=org["div"].node_id, include_revoked=True)


def test_empty_resolution_says_it_is_unbound(store, org):
    """★★★ 조용히 빈 목록을 주면 "에이전트가 없다"와 "바인딩이 안 됐다"가 같아진다."""
    r = store.resolve_agents(org["div"].node_id, today=TODAY)
    assert r["bound"] is False
    assert "바인딩이 없는" in r["note"] and "에이전트가 없는 것이 아니라" in r["note"]


def test_unapproved_pack_is_skipped_with_a_reason(store, org):
    """★★ 승인이 취소된 팩은 해석에서 빠지고 이유가 남는다(바인딩 시점에는 승인돼 있었다)."""
    pk = _approved(store, "표준", ["a"])
    store.bind(pk["pack_id"], org["div"].node_id)
    import sqlite3
    conn = sqlite3.connect(store._repo.db_path)
    conn.execute("UPDATE agent_packs SET status='DRAFT' WHERE pack_id=?", (pk["pack_id"],))
    conn.commit(); conn.close()
    r = store.resolve_agents(org["div"].node_id, today=TODAY)
    assert r["agents"] == [] and any("승인되지 않은 팩" in s["why"] for s in r["skipped"])


# ── 가상 문맥 ─────────────────────────────────────────────────────────────
def test_virtual_binding_needs_a_live_scenario(store, repo, org):
    """★★ 기준정보 바인딩과 **같은 규율** — 가상 문맥은 살아 있는 시나리오 안에서만."""
    pk = _approved(store, "표준", ["a"])
    with pytest.raises(AgentPackError, match="유효한 가상 시나리오가 없습니다"):
        store.bind(pk["pack_id"], org["div"].node_id, entity_mode="VIRTUAL")


def test_competitor_binding_is_refused(store, org):
    """★ 경쟁사 참조 문맥에는 에이전트를 바인딩하지 않는다."""
    pk = _approved(store, "표준", ["a"])
    with pytest.raises(AgentPackError, match="경쟁사"):
        store.bind(pk["pack_id"], org["div"].node_id, entity_mode="COMPETITOR_REFERENCE")


# ── 실행 경로 배선 ────────────────────────────────────────────────────────
def test_department_config_uses_the_binding(tmp_path, monkeypatch, repo, store, org):
    """★★★ **배선 검증.** 판정 함수만 만들어 두고 실행 경로에서 부르지 않으면 장식이다 —
    오늘 아침 목록 API 에서 정확히 그 실패를 겪었다.

    부서에 `scope_node_id` 가 있으면 `resolve_department_config` 가 팩 해석을 쓰고, 부서 고유
    목록은 그 뒤에 얹힌다(둘 다 의도된 값이다)."""
    import core.enterprise_context.agent_pack_binding as apb
    from core.org_directory import OrgDirectory

    od = OrgDirectory(db_path=str(tmp_path / "org.db"))
    od.create_department("battery", "배터리소재", domain_agents=["legacy_agent"],
                         scope_node_id=org["div"].node_id, actor="t")
    pk = _approved(store, "전사 표준", ["reviewer"])
    store.bind(pk["pack_id"], org["top"].node_id)

    monkeypatch.setattr(apb, "agent_packs", store, raising=False)
    import core.org_seed as seed
    monkeypatch.setattr(seed, "org_directory", od, raising=False)

    cfg = seed.resolve_department_config("battery")
    assert cfg["agents"] == ["reviewer", "legacy_agent"], "팩 해석이 실행 경로에 반영되지 않았다"
    assert "에이전트팩 바인딩" in cfg["agent_source"]


def test_department_config_falls_back_when_unbound(tmp_path, monkeypatch, repo, store, org):
    """★★★ 바인딩이 없으면 **기존 목록을 그대로 쓴다.**

    ⚠️ 하위호환이 핵심이다 — 조직 미도입·ECM 미배선 환경에서 에이전트가 사라지면 프로젝트 생성
      자체가 망가진다. 새 기능이 기존 흐름을 끊으면 그 기능은 꺼진다."""
    import core.enterprise_context.agent_pack_binding as apb
    from core.org_directory import OrgDirectory

    od = OrgDirectory(db_path=str(tmp_path / "org.db"))
    od.create_department("qa", "품질", domain_agents=["qa_agent"], actor="t")  # scope 미지정
    monkeypatch.setattr(apb, "agent_packs", store, raising=False)
    import core.org_seed as seed
    monkeypatch.setattr(seed, "org_directory", od, raising=False)

    cfg = seed.resolve_department_config("qa")
    assert cfg["agents"] == ["qa_agent"]
    assert cfg["agent_source"] == "부서 목록(domain_agents)"


# ── 감사 ──────────────────────────────────────────────────────────────────
def test_pack_and_binding_changes_are_audited(store, org, tmp_path, monkeypatch):
    """★★★ 구성 변경이 남지 않으면 과거 산출물을 재현할 수도 반박할 수도 없다."""
    import json

    from core.enterprise_context import audit
    log = tmp_path / "a.jsonl"
    monkeypatch.setattr(audit, "_LOG_PATH", str(log), raising=False)

    pk = _approved(store, "표준", ["a"], actor="hikwon")
    b = store.bind(pk["pack_id"], org["div"].node_id, actor="hikwon")
    store.unbind(b["binding_id"], actor="hikwon")

    rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    reasons = [r["reason"] for r in rows if r["event"] == "AGENT_PACK_CHANGED"]
    assert "에이전트팩 생성" in reasons and "에이전트팩 승인" in reasons
    assert "에이전트팩 바인딩" in reasons and "에이전트팩 바인딩 해제" in reasons
