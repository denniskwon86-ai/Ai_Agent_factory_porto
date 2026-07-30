# ==========================================
# Enterprise Context Master E1 — 조직 그래프·범위 전개·권한 가시성
# (`docs/design_enterprise_context_master.md` §3·§4·§6.1·§9)
#
# 검증하는 계약 여섯:
#  ① **단일 트리로 표현할 수 없는 것을 표현한다**(§2.1-2) — 법적소유·운영보고·공유서비스·연결집계가
#     서로 다른 관계로 공존한다. 시드가 실제로 네 관계를 모두 갖는다.
#  ② ★ **권한 상속은 OPERATING_PARENT 만 따른다**(§6.1) — 공유서비스·연결집계 관계는 자동
#     전체열람을 만들지 않는다. 뭉개면 "전사 권한이 모든 상세 데이터 권한으로 비화"(§13)한다.
#  ③ **순환 관계는 거부한다** — 사이클이 생기면 범위 전개가 무한 재귀에 빠져 서버가 멈춘다.
#  ④ **가상·경쟁사는 근거·원본을 강제한다**(§2.1-4, §7.3) — 가상은 base_entity_id,
#     경쟁사는 evidence_ref 없이 만들 수 없다.
#  ⑤ **문맥이 섞이지 않는다** — 실제/가상/경쟁사가 한 트리에 나오지 않고, 다른 테넌트는 404.
#  ⑥ **부서 id 와 ECM node_id 를 모두 해석한다** — ECM-lite 로 저장된 기존 범위를
#     마이그레이션 없이 살린다.
#
# ⚠️ 프로필 **상속 병합은 E2** 다. 여기서는 저장·조회와 `is_effective`(승인된 것만 상속 참여)만.
# ==========================================
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.routes.enterprise_context_control as ecc
import config
from api.deps import Principal, current_principal
from core.enterprise_context import (REL_CONSOLIDATION_SCOPE, REL_LEGAL_OWNERSHIP,
                                     REL_OPERATING_PARENT, REL_SHARED_SERVICE, STATUS_ACTIVE,
                                     STATUS_DRAFT, EcmError, EcmRepository, EcmResolver,
                                     EnterpriseEntity, EnterpriseProfile, OrganizationEdge,
                                     OrganizationNode)
from core.enterprise_context.seed import seed_example_organization
from core.org_directory import AccessScope


@pytest.fixture
def repo(tmp_path):
    return EcmRepository(db_path=str(tmp_path / "ecm.db"))


@pytest.fixture
def seeded(repo):
    res = seed_example_organization(repo)
    assert res["status"] == "seeded"
    return repo, res["node_ids"], EcmResolver(repo)


def _p(user_id="bob", dept="", readable=None, unrestricted=False):
    return Principal(user_id=user_id, scope=AccessScope(
        user_id=user_id, primary_dept_id=dept, unrestricted=unrestricted,
        readable_dept_ids=frozenset(readable if readable is not None else ({dept} if dept else set())),
        writable_dept_ids=frozenset({dept} if dept else set())))


# ── ① 그래프가 네 관계를 동시에 표현하는가 ────────────────────────────────
def test_seed_creates_all_four_relation_types(seeded):
    """★ 단일 트리로는 전사공통 조직의 서비스·집계 관계를 표현할 수 없다."""
    repo, ids, _ = seeded
    kinds = {e.relation_type for e in repo.list_edges()}
    assert {REL_LEGAL_OWNERSHIP, REL_OPERATING_PARENT, REL_SHARED_SERVICE,
            REL_CONSOLIDATION_SCOPE} == kinds


def test_seed_is_idempotent(repo):
    first = seed_example_organization(repo)
    second = seed_example_organization(repo)
    assert first["status"] == "seeded" and second["status"] == "skipped"
    assert second["node_ids"], "건너뛰어도 기존 노드 id 는 돌려줘야 한다"


def test_seed_marks_itself_as_example(seeded):
    """실제 조직과 구분되어야 한다 — 나중에 실제 조직을 넣을 때 이것을 걸러야 한다."""
    repo, _, _ = seeded
    assert all(e.source_ref == "design_doc_example" for e in repo.list_entities())


def test_shared_service_serves_two_divisions(seeded):
    """§3.3 — 전사공통 재무회계가 여러 사업부를 집계한다(트리로는 불가능한 구조)."""
    repo, ids, res = seeded
    consumers = set(res.shared_service_consumers(ids["MNM_SHARED"]))
    assert consumers == {ids["MNM_COPPER"], ids["MNM_BATTERY"]}
    consolidated = set(res.consolidation_scope(ids["MNM_SHARED"]))
    assert consolidated == {ids["MNM_COPPER"], ids["MNM_BATTERY"]}


# ── 범위 전개 ────────────────────────────────────────────────────────────
def test_operating_descendants(seeded):
    repo, ids, res = seeded
    d = set(res.descendants(ids["MNM_BATTERY"]))
    assert d == {ids["MNM_BATTERY"], ids["BATT_PLANT_1"], ids["BATT_PLANT_2"]}
    legal = set(res.descendants(ids["LS_MNM"]))
    assert ids["MNM_COPPER"] in legal and ids["BATT_PLANT_1"] in legal, "다단 전개"
    assert ids["LS_CABLE"] not in legal, "형제 법인은 운영 하위가 아니다"


def test_ancestors_chain(seeded):
    """E2 프로필 상속 체인의 입력이 된다."""
    repo, ids, res = seeded
    a = res.ancestors(ids["BATT_PLANT_1"])
    assert ids["MNM_BATTERY"] in a and ids["LS_MNM"] in a
    assert ids["LS"] not in a, "LS→LS_MNM 은 LEGAL_OWNERSHIP 이라 운영 조상이 아니다"


def test_legal_ownership_is_separate_from_operating(seeded):
    """지주 → 법인은 소유 관계이고 운영 보고선이 아니다 — 섞으면 권한이 새어나간다."""
    repo, ids, res = seeded
    owned = set(res.descendants(ids["LS"], REL_LEGAL_OWNERSHIP, include_self=False))
    assert owned == {ids["LS_CABLE"], ids["LS_ELECTRIC"], ids["LS_MNM"]}
    assert res.descendants(ids["LS"], REL_OPERATING_PARENT, include_self=False) == []


# ── ② ★ 권한 상속은 OPERATING_PARENT 만 ───────────────────────────────────
def test_shared_service_grants_no_read_permission(seeded):
    """★★ 전사공통(hq)에만 권한이 있는 사용자가 사업부 운영 데이터를 볼 수 없어야 한다.

    시드에서 MNM_SHARED 는 두 사업부에 SHARED_SERVICE·CONSOLIDATION_SCOPE 로 연결돼 있다.
    이 관계로 열람 권한이 생기면 §13 위험표의 "전사 권한이 모든 상세 데이터 권한으로 비화"가
    실현된다."""
    repo, ids, res = seeded
    hq_only = _p(dept="hq", readable={"hq"})
    readable = res.readable_node_ids(hq_only)
    assert ids["MNM_SHARED"] in readable, "자기 조직은 보인다"
    assert ids["MNM_COPPER"] not in readable, "서비스/집계 대상의 운영 데이터는 못 본다"
    assert ids["MNM_BATTERY"] not in readable
    assert ids["BATT_PLANT_1"] not in readable


def test_operating_parent_does_inherit(seeded):
    """운영 보고선으로는 상속된다 — production 부서 권한이 매핑된 노드와 그 하위."""
    repo, ids, res = seeded
    prod = _p(dept="production", readable={"production"})
    readable = res.readable_node_ids(prod)
    assert ids["MNM_BATTERY"] in readable
    assert ids["BATT_PLANT_1"] in readable and ids["BATT_PLANT_2"] in readable
    assert ids["MNM_SHARED"] not in readable, "다른 부서에 매핑된 노드는 안 보인다"


def test_unmapped_nodes_grant_nothing(seeded):
    """부서 매핑이 없는 노드(기업집단·법인)는 그 자체로 열람 권한을 주지 않는다(fail-closed)."""
    repo, ids, res = seeded
    prod = _p(dept="production", readable={"production"})
    readable = res.readable_node_ids(prod)
    assert ids["LS"] not in readable and ids["LS_MNM"] not in readable


def test_unrestricted_sees_all(seeded):
    repo, ids, res = seeded
    assert res.readable_node_ids(_p(unrestricted=True)) is None, "None = 필터하지 말라"
    assert res.can_read_node(_p(unrestricted=True), ids["LS"]) is True


# ── 트리 ─────────────────────────────────────────────────────────────────
def test_tree_includes_ancestors_as_path_only(seeded):
    """★ 조상을 빼면 트리가 조각나고, 열람 가능으로 표시하면 권한이 부풀려진다 — 구분해서 담는다."""
    repo, ids, res = seeded
    roots = res.visible_tree(_p(dept="production", readable={"production"}))
    flat = {}

    def walk(n):
        flat[n.node_id] = n
        for c in n.children:
            walk(c)
    for r in roots:
        walk(r)

    assert ids["MNM_BATTERY"] in flat and flat[ids["MNM_BATTERY"]].__dict__["readable"] is True
    assert ids["LS_MNM"] in flat, "경로가 끊기면 자기 조직의 위치를 알 수 없다"
    assert flat[ids["LS_MNM"]].__dict__["readable"] is False, "경로용 노드는 열람 불가로 표시"
    assert ids["MNM_SHARED"] not in flat, "권한 없고 경로도 아닌 노드는 아예 안 나온다"


def test_tree_has_single_root_and_depth(seeded):
    repo, ids, res = seeded
    roots = res.visible_tree(_p(unrestricted=True))
    assert len(roots) == 1 and roots[0].code == "LS"
    assert roots[0].depth == 0
    mnm = next(c for c in roots[0].children if c.code == "LS_MNM")
    assert mnm.depth == 1


# ── ③ 순환 방지 ──────────────────────────────────────────────────────────
def test_cycle_is_rejected(seeded):
    """★ 사이클이 생기면 범위 전개가 무한 재귀에 빠진다."""
    repo, ids, _ = seeded
    with pytest.raises(EcmError):
        repo.add_edge(OrganizationEdge(from_node_id=ids["BATT_PLANT_1"],
                                       to_node_id=ids["MNM_BATTERY"],
                                       relation_type=REL_OPERATING_PARENT))


def test_self_edge_rejected(seeded):
    repo, ids, _ = seeded
    with pytest.raises(EcmError):
        repo.add_edge(OrganizationEdge(from_node_id=ids["LS"], to_node_id=ids["LS"],
                                       relation_type=REL_OPERATING_PARENT))


def test_self_parent_rejected(repo):
    e = repo.upsert_entity(EnterpriseEntity(name_ko="X", status=STATUS_ACTIVE))
    n = repo.upsert_node(OrganizationNode(entity_id=e.entity_id, name_ko="X"))
    n.default_parent_id = n.node_id
    with pytest.raises(EcmError):
        repo.upsert_node(n)


def test_unknown_node_edge_rejected(seeded):
    repo, ids, _ = seeded
    with pytest.raises(EcmError):
        repo.add_edge(OrganizationEdge(from_node_id=ids["LS"], to_node_id="node_ghost",
                                       relation_type=REL_OPERATING_PARENT))


# ── ④ 가상·경쟁사 근거 강제 ───────────────────────────────────────────────
def test_virtual_requires_base_entity(repo):
    """§2.1-4 — 가상 조직은 실제의 복제본이지 허공에서 나오지 않는다."""
    with pytest.raises(EcmError):
        repo.upsert_entity(EnterpriseEntity(name_ko="가상 제3공장", entity_mode="VIRTUAL"))
    base = repo.upsert_entity(EnterpriseEntity(name_ko="제2공장", status=STATUS_ACTIVE))
    ok = repo.upsert_entity(EnterpriseEntity(name_ko="가상 제3공장", entity_mode="VIRTUAL",
                                             base_entity_id=base.entity_id))
    assert ok.entity_id and ok.base_entity_id == base.entity_id


def test_competitor_requires_evidence(repo):
    """§7.3 — 경쟁사 모델은 공개·승인된 근거만 쓴다. 근거 없이 만들 수 없다."""
    with pytest.raises(EcmError):
        repo.upsert_entity(EnterpriseEntity(name_ko="경쟁사 A",
                                            entity_mode="COMPETITOR_REFERENCE"))
    ok = repo.upsert_entity(EnterpriseEntity(name_ko="경쟁사 A",
                                            entity_mode="COMPETITOR_REFERENCE",
                                            evidence_ref="2026 사업보고서 p.42"))
    assert ok.evidence_ref


def test_unknown_types_rejected(repo):
    with pytest.raises(EcmError):
        repo.upsert_entity(EnterpriseEntity(name_ko="X", entity_type="회사"))
    with pytest.raises(EcmError):
        repo.upsert_entity(EnterpriseEntity(name_ko="X", entity_mode="FAKE"))
    e = repo.upsert_entity(EnterpriseEntity(name_ko="X", status=STATUS_ACTIVE))
    with pytest.raises(EcmError):
        repo.upsert_node(OrganizationNode(entity_id=e.entity_id, name_ko="X", node_type="팀"))
    with pytest.raises(EcmError):
        repo.upsert_node(OrganizationNode(entity_id="ent_ghost", name_ko="X"))


def test_approval_moves_to_active(repo):
    e = repo.upsert_entity(EnterpriseEntity(name_ko="신규 법인"))
    assert e.status == STATUS_DRAFT and not e.approved_at
    ap = repo.approve_entity(e.entity_id, "admin")
    assert ap.status == STATUS_ACTIVE and ap.approved_by == "admin" and ap.approved_at


# ── ⑤ 문맥 격리 ──────────────────────────────────────────────────────────
def test_virtual_nodes_do_not_appear_in_real_tree(seeded):
    """★ 실제/가상이 한 트리에 섞이면 가정값과 실제값의 구분이 무너진다(비협상 3)."""
    repo, ids, res = seeded
    base = repo.get_entity(repo.get_node(ids["BATT_PLANT_2"]).entity_id)
    v = repo.upsert_entity(EnterpriseEntity(
        name_ko="가상 제3공장", entity_type="site_plant", entity_mode="VIRTUAL",
        base_entity_id=base.entity_id, status=STATUS_ACTIVE))
    repo.upsert_node(OrganizationNode(entity_id=v.entity_id, node_type="site_plant",
                                      name_ko="가상 제3공장", code="BATT_PLANT_3",
                                      dept_id="production", status=STATUS_ACTIVE))
    real = res.readable_node_ids(_p(dept="production", readable={"production"}),
                                 entity_mode="REAL")
    virt = res.readable_node_ids(_p(dept="production", readable={"production"}),
                                 entity_mode="VIRTUAL")
    assert ids["BATT_PLANT_1"] in real and ids["BATT_PLANT_1"] not in virt
    assert len(virt) == 1, "가상 문맥에서는 가상 노드만 보인다"


# ── ⑥ 문맥 해석 (ECM-lite 이행) ────────────────────────────────────────────
def test_resolve_scope_ref_handles_both_forms(seeded):
    """★ 기존 데이터에는 `enterprise_scope_id` 에 부서 id 가 들어 있다 — 깨뜨리면 안 된다."""
    repo, ids, res = seeded
    by_node = res.resolve_scope_ref(ids["MNM_BATTERY"])
    assert by_node["kind"] == "ecm_node" and by_node["resolved"] is True

    # ★★ [2026-07-30] `production` 은 **의도적으로 모호한** 부서다 — 레거시 부서는 하나인데
    #   생산 사업부는 둘(동제련·배터리소재)이다. 하나를 고르면 `LIMIT 1` 의 tie-break 가 조직
    #   권한을 결정하고, 시드는 같은 시각에 만들어지므로 그 승자가 **비결정적**이다.
    #   → 해석을 포기하고(상속 없음) 후보를 돌려준다. 결정은 사람이 한다.
    ambiguous = res.resolve_scope_ref("production")
    assert ambiguous["kind"] == "department_ambiguous"
    assert ambiguous["resolved"] is False and ambiguous["node_id"] == ""
    assert {c["code"] for c in ambiguous["candidates"]} == {"MNM_COPPER", "MNM_BATTERY"}

    # 1:1 로 매핑된 부서는 종전대로 노드로 승격된다(하위호환).
    by_dept = res.resolve_scope_ref("hq")
    assert by_dept["kind"] == "department_mapped" and by_dept["node_id"]
    assert by_dept["resolved"] is True, "노드로 승격 가능한 상태"

    # 충돌 목록이 **고쳐야 할 일감**으로 드러난다 — 코드 우회만 하면 그 부서는 영원히
    #   조직 상속을 못 받는다.
    conflicts = repo.dept_mapping_conflicts()
    assert [c["dept_id"] for c in conflicts] == ["production"]
    assert conflicts[0]["node_count"] == 2

    unknown = res.resolve_scope_ref("nonexistent_dept")
    assert unknown["kind"] == "department" and unknown["resolved"] is False
    assert unknown["dept_id"] == "nonexistent_dept", "ECM 에 없어도 부서 체계로 계속 동작"

    assert res.resolve_scope_ref("")["resolved"] is False


# ── 프로필 (E1: 저장·조회만) ───────────────────────────────────────────────
def test_profile_requires_scope_or_industry(seeded):
    repo, ids, _ = seeded
    with pytest.raises(EcmError):
        repo.upsert_profile(EnterpriseProfile(profile_kind="business_profile"))


def test_unapproved_profile_is_not_effective(seeded):
    """§4.4 — 충돌 시 가장 하위의 **승인된** 프로필이 이긴다. 미승인은 상속에 참여하지 않는다."""
    repo, ids, _ = seeded
    draft = repo.upsert_profile(EnterpriseProfile(
        scope_node_id=ids["MNM_BATTERY"], profile_kind="data_profile",
        payload={"required_masters": ["품목"]}))
    assert draft.is_effective is False, "미승인 프로필이 상속되면 검토 전 값이 적용된다"

    approved = repo.upsert_profile(EnterpriseProfile(
        profile_id=draft.profile_id, scope_node_id=ids["MNM_BATTERY"],
        profile_kind="data_profile", payload={"required_masters": ["품목"]},
        status=STATUS_ACTIVE, approved_by="admin", approved_at="2026-07-28T00:00:00Z"))
    assert approved.is_effective is True


def test_profile_payload_roundtrip(seeded):
    repo, ids, _ = seeded
    repo.upsert_profile(EnterpriseProfile(
        scope_node_id=ids["BATT_PLANT_1"], profile_kind="process_profile",
        payload={"공정": ["소성", "코팅"], "kpi": {"수율": 0.95}}))
    got = repo.list_profiles(scope_node_id=ids["BATT_PLANT_1"], profile_kind="process_profile")
    assert got[0].payload["공정"] == ["소성", "코팅"]
    assert got[0].payload["kpi"]["수율"] == 0.95


# ══════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def client(repo, monkeypatch):
    resolver = EcmResolver(repo)
    monkeypatch.setattr(ecc, "ecm_repository", repo)
    monkeypatch.setattr(ecc, "ecm_resolver", resolver)
    import core.enterprise_context.seed as seed_mod
    monkeypatch.setattr(seed_mod, "ecm_repository", repo)
    app = FastAPI()
    app.include_router(ecc.router)
    return app, TestClient(app), repo, resolver


def _as(app, user_id="bob", dept="production", readable=None, edit_org=False, unrestricted=False):
    scope = AccessScope(
        user_id=user_id, primary_dept_id=dept, unrestricted=unrestricted,
        readable_dept_ids=frozenset(readable if readable is not None else {dept}),
        writable_dept_ids=frozenset({dept}), can_edit_org=edit_org)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id=user_id, scope=scope)


def test_api_meta_states_inheritance_rule(client):
    """규칙을 API 가 스스로 알려줘야 클라이언트가 오해하지 않는다."""
    app, c, _, _ = client
    _as(app)
    d = c.get("/api/v1/enterprise-context/meta").json()["data"]
    assert d["inheritable_relations"] == ["OPERATING_PARENT"]
    assert "공유서비스" in d["note"]


def test_api_seed_requires_org_edit(client):
    app, c, _, _ = client
    _as(app, edit_org=False)
    assert c.post("/api/v1/enterprise-context/seed-example").status_code == 403
    _as(app, edit_org=True)
    r = c.post("/api/v1/enterprise-context/seed-example")
    assert r.status_code == 200 and r.json()["data"]["status"] == "seeded"
    assert "예시" in r.json()["data"]["note"]


def test_api_tree_is_permission_filtered(client):
    app, c, repo, _ = client
    _as(app, edit_org=True)
    c.post("/api/v1/enterprise-context/seed-example")

    _as(app, dept="production", readable={"production"})
    roots = c.get("/api/v1/enterprise-context/tree").json()["data"]
    assert len(roots) == 1
    flat = []

    def walk(n):
        flat.append(n)
        for ch in n["children"]:
            walk(ch)
    walk(roots[0])
    codes = {n["code"]: n["readable"] for n in flat}
    assert codes.get("MNM_BATTERY") is True
    assert codes.get("LS_MNM") is False, "경로용 노드는 readable=False"
    assert "MNM_SHARED" not in codes


def test_api_node_scope_separates_permission_from_aggregation(client):
    """★ 집계 범위를 권한으로 오해하지 않게 응답에서 분리하고 note 로 못 박는다."""
    app, c, repo, _ = client
    _as(app, edit_org=True)
    ids = c.post("/api/v1/enterprise-context/seed-example").json()["data"]["node_ids"]

    _as(app, dept="hq", readable={"hq"})
    d = c.get(f"/api/v1/enterprise-context/nodes/{ids['MNM_SHARED']}/scope").json()["data"]
    assert d["operating_scope"] == [ids["MNM_SHARED"]], "운영 하위가 없다"
    assert set(d["consolidation_scope"]) == {ids["MNM_COPPER"], ids["MNM_BATTERY"]}
    assert "열람 권한을 부여하지 않습니다" in d["note"]
    # 그리고 그 집계 대상의 상세는 실제로 막혀 있다
    assert c.get(f"/api/v1/enterprise-context/nodes/{ids['MNM_COPPER']}/scope").status_code == 403


def test_api_context_select_validates_permission(client):
    app, c, repo, _ = client
    _as(app, edit_org=True)
    ids = c.post("/api/v1/enterprise-context/seed-example").json()["data"]["node_ids"]

    _as(app, dept="production", readable={"production"})
    ok = c.post("/api/v1/enterprise-context/contexts/select",
                json={"enterprise_scope_id": ids["MNM_BATTERY"]})
    assert ok.status_code == 200
    assert ok.json()["data"]["headers"]["X-Enterprise-Scope"] == ids["MNM_BATTERY"]

    denied = c.post("/api/v1/enterprise-context/contexts/select",
                    json={"enterprise_scope_id": ids["MNM_SHARED"]})
    assert denied.status_code == 403

    # ECM 에 없는 부서 id 도 받아들인다(하위호환) — 부서 권한으로 판정
    legacy = c.post("/api/v1/enterprise-context/contexts/select",
                    json={"enterprise_scope_id": "production"})
    assert legacy.status_code == 200


def test_api_entity_crud_and_context_isolation(client):
    app, c, _, _ = client
    _as(app, edit_org=True, unrestricted=True)
    ent = c.post("/api/v1/enterprise-context/entities",
                 json={"name_ko": "신규 법인", "entity_type": "legal_entity"}).json()["data"]
    assert ent["status"] == "DRAFT"
    got = c.get(f"/api/v1/enterprise-context/entities/{ent['entity_id']}")
    assert got.status_code == 200
    # 다른 테넌트 문맥에서는 없는 것으로 답한다
    other = c.get(f"/api/v1/enterprise-context/entities/{ent['entity_id']}",
                  headers={config.ECM_TENANT_HEADER: "tenant_other"})
    assert other.status_code == 404
    ap = c.post(f"/api/v1/enterprise-context/entities/{ent['entity_id']}/approve")
    assert ap.json()["data"]["status"] == "ACTIVE"


def test_api_virtual_entity_needs_base(client):
    app, c, _, _ = client
    _as(app, edit_org=True, unrestricted=True)
    r = c.post("/api/v1/enterprise-context/entities",
               json={"name_ko": "가상 공장", "entity_mode": "VIRTUAL"})
    assert r.status_code == 400 and "base_entity_id" in r.json()["detail"]


def test_api_cycle_rejected(client):
    app, c, _, _ = client
    _as(app, edit_org=True, unrestricted=True)
    ids = c.post("/api/v1/enterprise-context/seed-example").json()["data"]["node_ids"]
    r = c.post("/api/v1/enterprise-context/edges",
               json={"from_node_id": ids["BATT_PLANT_1"], "to_node_id": ids["MNM_BATTERY"],
                     "relation_type": "OPERATING_PARENT"})
    assert r.status_code == 400 and "순환" in r.json()["detail"]


def test_api_profiles_do_not_merge_in_e1(client):
    """E1 은 상속 병합을 하지 않는다 — 그 사실을 응답에 명시해 오해를 막는다."""
    app, c, _, _ = client
    _as(app, edit_org=True, unrestricted=True)
    ids = c.post("/api/v1/enterprise-context/seed-example").json()["data"]["node_ids"]
    c.post("/api/v1/enterprise-context/profiles",
           json={"scope_node_id": ids["MNM_BATTERY"], "profile_kind": "data_profile",
                 "payload": {"required_masters": ["품목"]}})
    r = c.get(f"/api/v1/enterprise-context/profiles?scope_node_id={ids['MNM_BATTERY']}")
    body = r.json()
    assert body["data"][0]["is_effective"] is False, "미승인은 상속 참여 불가"
    assert "E2" in body["note"]


def test_api_node_creation_requires_org_edit(client):
    app, c, _, _ = client
    _as(app, edit_org=True, unrestricted=True)
    ent = c.post("/api/v1/enterprise-context/entities", json={"name_ko": "법인"}).json()["data"]
    _as(app, edit_org=False)
    r = c.post("/api/v1/enterprise-context/nodes",
               json={"entity_id": ent["entity_id"], "name_ko": "사업부"})
    assert r.status_code == 403
