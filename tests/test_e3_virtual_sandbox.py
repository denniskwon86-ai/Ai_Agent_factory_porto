"""★★★ [ECM E3] 가상 기업 Sandbox — **복제본이지 운영계 우회 통로가 아니다.**

## 이 파일이 지키는 것

설계서 §7.1 은 가상 조직 생성 흐름을 "원본 선택 → 복제 범위·목적·유효기간 → 복사 정책 확인 →
가정값 → 격리 스냅샷 → 계산 → 비교/승인" 으로 규정한다. 그동안 `CREATABLE_ENTITY_MODES` 가
`REAL` 만 허용해 가상 생성을 막아 왔다(E3 선행 조건, §13 위험표).

E3 를 열면서 그 안전장치를 없애지 않았다 — **가상 엔터티는 직접 생성이 아니라 복제로만**
만들어진다. 이 파일은 그 문이 열리는 조건과, 문을 통과해도 **넘어오지 않는 것**을 검증한다.

⚠️ 가장 중요한 것은 "무엇이 복사되는가"가 아니라 **"무엇이 절대 복사되지 않는가"** 다:
  실거래·원장·개인정보와 외부 시스템 자격증명·MCP 쓰기 권한. 이것이 넘어오는 순간
  "안전한 복제본"이라는 전제가 사라지고, 가상 실험이 운영계 우회 통로가 된다(비협상 4).
"""
import pytest

from core.enterprise_context.clone_service import (COPY_POLICY, NEVER_COPIED, CloneService,
                                                   SandboxError, assert_external_allowed)
from core.enterprise_context.models import (EnterpriseEntity, EnterpriseProfile,
                                            OrganizationEdge, OrganizationNode)
from core.enterprise_context.repository import EcmRepository

TOMORROW = "2099-12-31"
TODAY = "2026-07-31"


@pytest.fixture
def repo(tmp_path):
    return EcmRepository(db_path=str(tmp_path / "ecm.db"))


@pytest.fixture
def svc(repo):
    return CloneService(repository=repo)


@pytest.fixture
def real_org(repo):
    """실제 법인 1개 + 사업부 2개 + 프로필 1개. 복제 원본."""
    ent = repo.upsert_entity(EnterpriseEntity(
        entity_type="legal_entity", entity_mode="REAL", name_ko="LS MnM",
        legal_name="LS MnM Co., Ltd.", industry_code="C24"))
    # ★ `status="ACTIVE"` 를 명시한다 — 모델 기본값은 DRAFT 이고, `find_node_by_code` 는
    #   ACTIVE 만 찾는다. 실제 조직도는 승인된 상태이므로 그쪽을 흉내낸다.
    top = repo.upsert_node(OrganizationNode(
        entity_id=ent.entity_id, node_type="legal_entity", code="LS_MNM",
        name_ko="LS MnM", dept_id="hq", status="ACTIVE"))
    div = repo.upsert_node(OrganizationNode(
        entity_id=ent.entity_id, node_type="business_division", code="MNM_BATTERY",
        name_ko="배터리소재 사업부", dept_id="production_battery", status="ACTIVE"))
    repo.add_edge(OrganizationEdge(from_node_id=top.node_id, to_node_id=div.node_id,
                                   relation_type="OPERATING_PARENT"))
    repo.upsert_profile(EnterpriseProfile(
        scope_node_id=div.node_id, industry_code="C24", profile_kind="business_profile",
        payload={"주요공정": ["소성", "코팅"]}, status="ACTIVE",
        approved_by="hikwon", approved_at="2026-07-01T00:00:00"))
    return {"entity": ent, "top": top, "div": div}


# ── 문이 열리는 조건 ──────────────────────────────────────────────────────
def test_clone_creates_isolated_virtual_entity(svc, repo, real_org):
    """★★ 복제하면 가상 엔터티가 생기고 **계보(base_entity_id)** 가 남는다."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상 제3공장 시나리오",
                             purpose="증설 타당성 검토", valid_until=TOMORROW,
                             actor="hikwon", today=TODAY)
    virt = repo.get_entity(s["entity_id"])
    assert virt.entity_mode == "VIRTUAL"
    assert virt.base_entity_id == real_org["entity"].entity_id, "복제 계보가 없으면 근거를 잃는다"
    assert virt.status == "DRAFT", "승인 전에는 초안이어야 한다(§4.1)"
    assert s["clone_source_id"] == real_org["entity"].entity_id
    assert s["status"] == "ACTIVE" and s["expired"] is False


@pytest.mark.parametrize("missing,kw", [
    ("이름", {"name_ko": ""}),
    ("목적", {"purpose": ""}),
    ("유효기간", {"valid_until": ""}),
])
def test_clone_requires_name_purpose_and_expiry(svc, real_org, missing, kw):
    """★★★ 셋 중 하나라도 없으면 만들지 않는다.

    ⚠️ 만료 없는 가상 조직은 **영구 조직**이 된다 — 이 저장소는 같은 실패를 이미 봤다
      ('한시 예외'가 만료를 갖지 않아 상시 규칙이 됐다). 목적 없는 가상 조직은 나중에 아무도
      정리하지 못한다."""
    args = {"name_ko": "가상", "purpose": "검토", "valid_until": TOMORROW}
    args.update(kw)
    with pytest.raises(SandboxError):
        svc.clone_to_virtual(real_org["entity"].entity_id, today=TODAY, **args)


def test_expired_valid_until_is_refused(svc, real_org):
    """★★ 이미 지난 만료일은 거부한다 — 만들자마자 만료된 시나리오는 혼란만 남긴다."""
    with pytest.raises(SandboxError, match="지났"):
        svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until="2026-01-01", today=TODAY)


def test_cannot_clone_a_virtual_entity(svc, real_org):
    """★★★ **가상의 가상은 만들 수 없다.** 계보를 추적할 수 없으면 "어떤 실제 조직에서 나온
    가정인가"에 답할 수 없고, 가정 위의 가정이 실제처럼 보이기 시작한다."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "1차 가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    with pytest.raises(SandboxError, match="실제 운영 문맥이어야"):
        svc.clone_to_virtual(s["entity_id"], "2차 가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)


def test_missing_source_is_refused(svc):
    """★ 없는 원본으로는 만들 수 없다(조용히 빈 가상 조직을 만들지 않는다)."""
    with pytest.raises(SandboxError, match="원본을 찾을 수 없"):
        svc.clone_to_virtual("ent_nope", "가상", purpose="검토", valid_until=TOMORROW,
                             today=TODAY)


# ── 문을 통과해도 넘어오지 않는 것 ─────────────────────────────────────────
def test_forbidden_items_cannot_be_requested(svc, real_org):
    """★★★ **이 파일의 핵심.** 실거래·원장·개인정보와 자격증명·쓰기 권한은 호출자가 요청해도
    거부한다. 선택 항목이 아니다(§7.1 복사 금지 행).

    ⚠️ 이것을 "기본값 False" 로만 두면 언젠가 누가 True 로 켠다. 정책은 기본값이 아니라
      **거부**로 표현해야 한다."""
    for forbidden in NEVER_COPIED:
        with pytest.raises(SandboxError, match="복사할 수 없"):
            svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                                 valid_until=TOMORROW, copy={forbidden: True}, today=TODAY)


def test_unknown_copy_item_is_refused(svc, real_org):
    """★ 알 수 없는 복사 항목은 조용히 무시하지 않는다 — 오타가 "복사 안 함"으로 흘러가면
    사용자는 복사됐다고 믿는다."""
    with pytest.raises(SandboxError, match="알 수 없는 복사 항목"):
        svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, copy={"ledger": True}, today=TODAY)


def test_refused_items_are_recorded_on_the_scenario(svc, real_org):
    """★★ 무엇을 복사하지 **않았는지**가 시나리오에 남는다 — 가상 결과의 한계를 설명하는 근거다."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    assert set(s["refused"]) == set(NEVER_COPIED), "복사 금지 항목 기록이 빠졌다"
    assert set(s["copied"]) >= set(COPY_POLICY), "무엇을 복사했는지 기록이 빠졌다"


def test_dept_id_is_not_copied(svc, repo, real_org):
    """★★★ 복제된 노드는 **실제 부서(dept_id)를 가리키지 않는다.**

    ⚠️ 여기가 조용한 권한 유출 경로다: 가상 노드가 `production_battery` 를 그대로 들고 있으면
      그 부서 사람의 권한 해석이 가상 문맥까지 닿는다. 실제 사용자는 자기가 가상 자료를 보고
      있는지도 모른 채 가정값을 실제로 읽는다."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    virt_nodes = [n for n in repo.list_nodes() if n.entity_id == s["entity_id"]]
    assert virt_nodes, "노드가 복제되지 않았다"
    assert all(n.dept_id == "" for n in virt_nodes), "실제 부서가 가상 노드로 복사됐다"


def test_codes_are_prefixed_so_trees_do_not_collide(svc, repo, real_org):
    """★★★ 같은 code 가 두 문맥에 존재하면 `find_node_by_code` 가 **정렬 순서로** 어느 쪽인지
    결정한다 — 이 저장소는 부서 1:N 매핑에서 정확히 그 사고를 겪었다."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    virt = [n for n in repo.list_nodes() if n.entity_id == s["entity_id"]]
    assert all(n.code.startswith("V") and n.code != "LS_MNM" for n in virt)
    # 실제 코드로 찾으면 여전히 실제 노드가 나온다
    assert repo.find_node_by_code("LS_MNM").entity_id == real_org["entity"].entity_id


def test_profile_approval_is_not_copied(svc, repo, real_org):
    """★★ 원본 프로필의 **승인이 복사되면 안 된다** — 실제 조직의 승인이 가상 가정의 승인이
    될 수 없다. §4.4 는 "가장 하위의 승인된 프로필이 이긴다"고 하므로, 승인된 채 복사되면
    가상 가정이 상속 경쟁에서 실제 프로필을 이긴다."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    virt_nodes = [n for n in repo.list_nodes() if n.entity_id == s["entity_id"]]
    copied = [pr for n in virt_nodes for pr in repo.list_profiles(scope_node_id=n.node_id)]
    assert copied, "프로필이 복제되지 않았다"
    assert all(pr.status == "DRAFT" and not pr.approved_by for pr in copied)


def test_structure_is_preserved(svc, repo, real_org):
    """★★ 노드만 복사하고 엣지를 빼면 상하관계가 사라져 **상속이 끊긴다** — 어제 실제로
    조직 코드가 해석되지 않아 상속이 조용히 끊긴 사고와 같은 결과가 된다."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    assert s["copied"]["edges"] >= 1, "구조(엣지)가 복제되지 않았다"


def test_operating_subtree_is_cloned_even_across_entities(svc, repo, real_org):
    """★★★ [2026-07-31 실측] **하위 조직이 따라와야 한다.**

    실서버에서 사업부를 복제해 보니 `org_nodes: 1, edges: 0` 이었다 — 이 저장소의 조직도는
    노드마다 엔터티가 1:1 이고 계층은 **엔터티 사이의 엣지**에 있다(LS → LS MnM → 사업부 → 공장).
    엔터티의 노드만 복사하면 복제본이 노드 하나짜리 껍데기가 된다: 기능은 있는데 쓸 수 없다.
    → `OPERATING_PARENT` 하위 트리를 따라간다."""
    plant_ent = repo.upsert_entity(EnterpriseEntity(
        entity_type="site_plant", entity_mode="REAL", name_ko="제1공장"))
    plant = repo.upsert_node(OrganizationNode(
        entity_id=plant_ent.entity_id, node_type="site_plant", code="BATT_PLANT_1",
        name_ko="제1공장", status="ACTIVE"))
    repo.add_edge(OrganizationEdge(from_node_id=real_org["div"].node_id,
                                   to_node_id=plant.node_id,
                                   relation_type="OPERATING_PARENT"))

    s = svc.clone_to_virtual(real_org["div"].entity_id, "가상 증설", purpose="증설 검토",
                             valid_until=TOMORROW, today=TODAY)
    virt = [n for n in repo.list_nodes() if n.entity_id == s["entity_id"]]
    names = {n.name_ko for n in virt}
    assert "배터리소재 사업부" in names and "제1공장" in names, "하위 공장이 복제되지 않았다"
    assert s["copied"]["edges"] >= 1, "복제된 노드 사이의 구조가 남지 않았다"


def test_consolidation_edges_are_not_followed(svc, repo, real_org):
    """★★★ 지분 집계(`CONSOLIDATION_SCOPE`)는 따라가지 않는다 — 따라가면 **법인 경계를 넘어**
    다른 회사가 복제된다. 경영진 드릴다운에서 이미 같은 이유로 금지한 경로다."""
    other = repo.upsert_entity(EnterpriseEntity(
        entity_type="legal_entity", entity_mode="REAL", name_ko="LS전선"))
    other_node = repo.upsert_node(OrganizationNode(
        entity_id=other.entity_id, node_type="legal_entity", code="LS_CABLE",
        name_ko="LS전선", status="ACTIVE"))
    repo.add_edge(OrganizationEdge(from_node_id=real_org["top"].node_id,
                                   to_node_id=other_node.node_id,
                                   relation_type="CONSOLIDATION_SCOPE"))

    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    virt = {n.name_ko for n in repo.list_nodes() if n.entity_id == s["entity_id"]}
    assert "LS전선" not in virt, "집계 관계를 따라가 다른 법인이 복제됐다"


def test_profiles_can_be_skipped(svc, repo, real_org):
    """★ 선택 복사는 실제로 선택된다(정책이 장식이 아니다)."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, copy={"profiles": False}, today=TODAY)
    virt_nodes = [n for n in repo.list_nodes() if n.entity_id == s["entity_id"]]
    assert not [pr for n in virt_nodes for pr in repo.list_profiles(scope_node_id=n.node_id)]


# ── 외부 연계 차단 (§8.3) ─────────────────────────────────────────────────
@pytest.mark.parametrize("mode", ["VIRTUAL", "COMPETITOR_REFERENCE"])
def test_external_calls_are_blocked_in_non_real_contexts(mode):
    """★★★ 가상·경쟁사 문맥에서 외부 운영 시스템을 부르면 그 결과는 더 이상 가정이 아니다 —
    실제와 섞인 값이 된다. "가상 조직은 운영계의 우회 통로가 아니다"(비협상 4)의 실질."""
    with pytest.raises(SandboxError, match="가상·경쟁사 문맥"):
        assert_external_allowed(mode, "ERP 조회")


@pytest.mark.parametrize("mode", ["REAL", ""])
def test_real_context_is_not_blocked(mode):
    """★ 실제 문맥은 막지 않는다(빈 값도 실제로 본다 — 기존 흐름을 깨지 않는다)."""
    assert_external_allowed(mode) is None


def test_mcp_broker_refuses_virtual_context(tmp_path, monkeypatch):
    """★★★ 차단이 **실제 조회 경로에 배선돼 있는지** 확인한다.

    ⚠️ 판정 함수만 만들어 두고 부르지 않으면 통제가 없다 — 오늘 아침 목록 API 에서 정확히
      그 일이 있었다(필터를 부르지 않으면 통제가 없었다). 그래서 브로커를 직접 부른다.
    ★ 범위 판정보다 **먼저** 막혀야 한다: 범위가 맞는 가상 노드가 운영 ERP 를 읽으면
      결과가 실제와 섞인다."""
    from core.mcp_broker import MCPBroker, MCPError

    broker = MCPBroker()
    monkeypatch.setattr(broker.cw, "get_system",
                        lambda sid: {"system_id": sid, "status": "active", "scope": "read"},
                        raising=False)
    with pytest.raises(MCPError, match="가상·경쟁사 문맥"):
        broker.resolve("MAT-001", "ERP_PROD", entity_mode="VIRTUAL",
                       scope_node_id="V_NODE", tenant_id="tenant_default")


# ── 만료·종료·승격 ────────────────────────────────────────────────────────
def test_expiry_is_reported_not_hidden(svc, real_org, tmp_path):
    """★★ 만료된 시나리오는 **만료라고 말한다.** 조용히 살아 있으면 만료된 가정으로 판단한다."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until="2026-08-01", today=TODAY)
    later = svc.get_scenario(s["scenario_id"])
    assert later is not None
    fresh = svc.list_scenarios(today="2026-09-01")[0]
    assert fresh["expired"] is True and "만료" in fresh["visibility"]


def test_active_scenario_lookup_ignores_expired(svc, repo, real_org):
    """★★★ 만료된 시나리오는 "살아 있는 시나리오" 조회에 나오지 않는다 — 이 판정이
    가상 문맥 기준정보 바인딩의 열쇠다(만료되면 바인딩도 막힌다)."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until="2026-08-01", today=TODAY)
    node = [n for n in repo.list_nodes() if n.entity_id == s["entity_id"]][0]
    assert svc.active_scenario_of_node(node.node_id, today=TODAY) is not None
    assert svc.active_scenario_of_node(node.node_id, today="2026-09-01") is None


def test_close_does_not_delete(svc, real_org):
    """★★ 종료는 삭제가 아니다 — 어떤 가정으로 무엇을 판단했는지가 감사 대상이다."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    closed = svc.close_scenario(s["scenario_id"], actor="hikwon", reason="검토 종료")
    assert closed["status"] == "CLOSED"
    assert svc.get_scenario(s["scenario_id"]) is not None, "기록이 사라지면 안 된다"


def test_promotion_is_a_request_not_an_apply(svc, repo, real_org):
    """★★★ 승격은 **요청**까지다. 실제 조직은 바뀌지 않는다(§8.3).

    ⚠️ 여기서 자동 반영을 허용하면 가정값이 실제 조직 정의가 된다 — 되돌릴 방법이 없다."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    before = len([n for n in repo.list_nodes() if n.entity_id == real_org["entity"].entity_id])
    out = svc.request_promotion(s["scenario_id"], actor="hikwon", rationale="타당성 확인됨")
    assert out["status"] == "PROMOTION_REQUESTED"
    assert "실제 조직은 바뀌지 않았습니다" in out["note"]
    after = len([n for n in repo.list_nodes() if n.entity_id == real_org["entity"].entity_id])
    assert before == after, "승격 요청이 실제 조직을 건드렸다"


def test_promotion_requires_rationale(svc, real_org):
    """★ 근거 없는 승격 요청은 승인할 수 없다 — 요청 단계에서 막는다."""
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    with pytest.raises(SandboxError, match="승격 사유"):
        svc.request_promotion(s["scenario_id"], rationale="")


def test_closed_and_expired_cannot_be_promoted(svc, real_org):
    """★★ 종료·만료된 시나리오로 실제 조직을 바꿀 수 없다."""
    a = svc.clone_to_virtual(real_org["entity"].entity_id, "가상A", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    svc.close_scenario(a["scenario_id"])
    with pytest.raises(SandboxError, match="종료된"):
        svc.request_promotion(a["scenario_id"], rationale="근거")


# ── 가상 문맥 기준정보 바인딩 (E3 로 열린 문) ──────────────────────────────
def _master(tmp_path, svc, monkeypatch):
    """가상 바인딩을 시도할 기준정보 저장소. `clone_service` 싱글턴을 이 테스트의 것으로 바꾼다."""
    import core.enterprise_context.clone_service as cs
    from core.master_data import MasterData
    monkeypatch.setattr(cs, "clone_service", svc, raising=False)
    md = MasterData(db_path=str(tmp_path / "m.db"))
    md.create_type("material", "자재")
    md.create_or_revise_record(master_code="MAT-001", type_id="material", name="황산니켈")
    return md


def test_virtual_binding_needs_a_live_scenario(tmp_path, svc, repo, real_org, monkeypatch):
    """★★★ **E3 가 연 문이 여기다.** 가상 문맥 바인딩은 살아 있는 시나리오 안에서만 가능하다.

    ⚠️ 시나리오 없이 가상 노드에 바인딩하면 목적도 만료도 없는 가정값이 쌓인다 — 그것이 E3 를
      선행 조건으로 걸어 둔 이유 그대로다. 그래서 문을 열되 **조건을 구조로 확인**한다."""
    from core.master_data import MasterDataError
    md = _master(tmp_path, svc, monkeypatch)

    # ① 시나리오 없는 가상 노드 → 거부
    orphan = repo.upsert_entity(EnterpriseEntity(
        entity_mode="VIRTUAL", name_ko="떠도는 가상", base_entity_id=real_org["entity"].entity_id))
    orphan_node = repo.upsert_node(OrganizationNode(
        entity_id=orphan.entity_id, code="V_ORPHAN", name_ko="가상노드", status="ACTIVE"))
    with pytest.raises(MasterDataError, match="유효한 가상 시나리오가 없습니다"):
        md.bind_master_to_scope("MAT-001", orphan_node.node_id, entity_mode="VIRTUAL")

    # ② 살아 있는 시나리오의 가상 노드 → 허용
    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="검토",
                             valid_until=TOMORROW, today=TODAY)
    node = [n for n in repo.list_nodes() if n.entity_id == s["entity_id"]][0]
    out = md.bind_master_to_scope("MAT-001", node.node_id, entity_mode="VIRTUAL")
    assert out["scope_node_id"] == node.node_id

    # ③ 시나리오를 닫으면 다시 거부된다 — 종료된 실험에 가정값을 더 쌓을 수 없다
    svc.close_scenario(s["scenario_id"])
    with pytest.raises(MasterDataError, match="유효한 가상 시나리오가 없습니다"):
        md.bind_master_to_scope("MAT-001", node.node_id, entity_mode="VIRTUAL")


def test_competitor_binding_stays_closed(tmp_path, svc, repo, real_org, monkeypatch):
    """★★ 경쟁사 참조에는 자사 기준정보를 바인딩하지 않는다 — 공개 추정치와 자사 확정값이
    섞이면 어느 쪽이 사실인지 알 수 없다(비협상 3). E3 로도 열리지 않는다."""
    from core.master_data import MasterDataError
    md = _master(tmp_path, svc, monkeypatch)
    with pytest.raises(MasterDataError, match="경쟁사 참조 문맥"):
        md.bind_master_to_scope("MAT-001", "node_any", entity_mode="COMPETITOR_REFERENCE")


def test_real_binding_is_unchanged(tmp_path, svc, repo, real_org, monkeypatch):
    """★ 실제 문맥 바인딩은 종전과 같다 — E3 를 열면서 기존 흐름을 건드리지 않았다."""
    md = _master(tmp_path, svc, monkeypatch)
    out = md.bind_master_to_scope("MAT-001", real_org["div"].node_id)
    assert out["scope_node_id"] == real_org["div"].node_id


# ── 감사 ──────────────────────────────────────────────────────────────────
def test_scenario_lifecycle_is_audited(svc, real_org, tmp_path, monkeypatch):
    """★★★ 누가 무엇을 복제해 어떤 가정으로 판단했는지가 남는다.

    남지 않으면 "이 숫자가 실제인가 가정인가"에 답할 수 없다(비협상 3). 오늘 조직 변경에서
    겪은 것과 같은 공백이다."""
    import json

    from core.enterprise_context import audit
    log = tmp_path / "a.jsonl"
    monkeypatch.setattr(audit, "_LOG_PATH", str(log), raising=False)

    s = svc.clone_to_virtual(real_org["entity"].entity_id, "가상", purpose="증설 검토",
                             valid_until=TOMORROW, actor="hikwon", today=TODAY)
    svc.request_promotion(s["scenario_id"], actor="hikwon", rationale="타당")
    svc.close_scenario(s["scenario_id"], actor="hikwon", reason="완료")

    rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    ev = [r for r in rows if r["event"] == "VIRTUAL_SCENARIO_CHANGED"]
    assert len(ev) == 3, "생성·승격요청·종료가 모두 남아야 한다"
    assert all(r["actor"] == "hikwon" for r in ev)
    assert "증설 검토" in ev[0]["detail"] and real_org["entity"].entity_id in ev[0]["detail"]
