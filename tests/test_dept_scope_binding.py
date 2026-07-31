"""★★★ 부서 → ECM 조직 노드 매핑 — **권한 모델의 마지막 조각.**

## 왜 부서에 두는가

자료(지식팩·참고문서·기준정보)의 소유자는 부서(`production_battery`)가 아니라 **ECM 조직
노드**(`MNM_BATTERY`)로 적혀 있다. 두 이름 사이에 다리가 없으면 "이 사용자가 이 자료를
볼 수 있는가"에 답할 수 없다 — 그래서 강제를 켠 첫날의 통제는 "열어도 되는가"까지만 판단하고
"무엇까지 보이는가"는 판단하지 못했다.

다리를 **사용자**에 놓으면 같은 부서의 두 사람이 다른 조직 범위를 갖게 되고, 그 차이는 아무도
의도하지 않은 채 생긴다(어제 `production` 부서가 두 사업부에 걸쳐 정렬 순서가 권한을 정한
사고와 같은 유형이다). 부서는 기준정보이므로 **부서가 들고 사용자는 상속한다.**

## 이 파일이 지키는 계약

1. 미지정은 **미지정으로 남는다** — 상위 노드로 추측하지 않는다.
2. 미지정 부서 소속은 조직 소유 자료를 못 본다(관문 A: 미지정 = 비노출).
3. 소유 조직이 비어 있는 자료도 보이지 않는다 — 미기재를 공개로 읽으면 전부 공개가 된다.
4. 범위 변경은 **새 버전**으로 남는다("언제부터 이 부서가 이 범위였나"에 답해야 한다).
5. 다른 조직을 `scope_node_id` 로 지정해 넘겨다볼 수 없다.
"""
import pytest

from core.org_directory import OrgDirectory


@pytest.fixture
def org(tmp_path):
    return OrgDirectory(db_path=str(tmp_path / "org.db"))


# ── 저장·개정 ────────────────────────────────────────────────────────────
def test_dept_carries_scope_node(org):
    """★ 부서에 조직 노드를 적을 수 있고, 조회 시 그대로 돌아온다."""
    d = org.create_department("battery", "배터리소재", scope_node_id="MNM_BATTERY")
    assert d["scope_node_id"] == "MNM_BATTERY"
    assert org.get_department("battery")["scope_node_id"] == "MNM_BATTERY"


def test_unset_scope_node_stays_unset(org):
    """★★ 적지 않으면 **빈 값으로 남는다.** 상위 노드로 추측하지 않는다 —
    추측이 한 번 맞으면 아무도 다시 검증하지 않고, 틀리면 다른 사업부 자료가 열린다."""
    org.create_department("hq", "본사", scope_node_id="LS_MNM")
    org.create_department("sub", "하위", parent_id="hq")
    assert org.get_department("sub")["scope_node_id"] == ""


def test_changing_scope_node_creates_new_version(org):
    """★★ 범위 변경은 조용히 덮지 않는다 — 구판이 이력으로 남아야 과거 산출물을 설명할 수 있다."""
    org.create_department("plant", "공장", scope_node_id="MNM_COPPER")
    org.update_department("plant", scope_node_id="MNM_BATTERY")
    cur = org.get_department("plant")
    assert cur["scope_node_id"] == "MNM_BATTERY" and int(cur["version"]) == 2
    hist = org.get_department_history("plant")
    assert any(h["scope_node_id"] == "MNM_COPPER" for h in hist), "구판이 사라졌다"


def test_other_fields_survive_scope_update(org):
    """★ 범위만 바꿀 때 나머지 필드가 초기화되면 안 된다(개정은 전체 재삽입이므로 실수하기 쉽다)."""
    org.create_department("qa", "품질", master_domains=["quality"], legacy_domain="q",
                          scope_node_id="LS_MNM")
    org.update_department("qa", scope_node_id="MNM_COPPER")
    d = org.get_department("qa")
    assert d["master_domains"] == ["quality"] and d["legacy_domain"] == "q"


# ── 판정: 열려도 되는 것과 안 되는 것 ─────────────────────────────────────
def test_viewer_nodes_are_inherited_from_departments(org, monkeypatch):
    """★★★ 사용자는 부서를 통해 조직 노드를 **상속**한다 — 사용자 표에 범위를 적지 않는다."""
    import config
    import core.org_directory as od
    monkeypatch.setattr(od, "_org_enforce_effective", lambda: True)
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    monkeypatch.setattr(od, "org_directory", org, raising=False)

    org.create_department("battery", "배터리소재", scope_node_id="MNM_BATTERY")
    org.create_department("copper", "제련", scope_node_id="MNM_COPPER")
    org.upsert_user("kim", "김", primary_dept_id="battery")

    scope = org.resolve_scope("kim")
    assert scope.readable_scope_nodes == frozenset({"MNM_BATTERY"})
    assert "MNM_COPPER" not in scope.readable_scope_nodes, "다른 사업부가 섞였다"


def test_unassigned_dept_yields_no_nodes(org, monkeypatch):
    """★★ 부서에 범위가 없으면 노드도 없다 — 호출자는 이것을 '전부'가 아니라 '아무것도'로 다뤄야
    한다. 빈 집합을 전면 통과로 읽는 실수가 바로 관문 A 가 막으려는 것이다."""
    import core.org_directory as od
    monkeypatch.setattr(od, "_org_enforce_effective", lambda: True)
    org.create_department("plain", "무범위")
    org.upsert_user("lee", "이", primary_dept_id="plain")
    assert org.resolve_scope("lee").readable_scope_nodes == frozenset()


def test_scope_allows_owner_is_closed_by_default(org):
    """★★★ `scope_allows_owner` 의 실패 방향 — 모르면 **닫는다.**"""
    from api.deps import scope_allows_owner
    assert scope_allows_owner(None, "LS_MNM") is True, "unrestricted 는 전면 통과"
    assert scope_allows_owner(frozenset(), "LS_MNM") is False, "노드를 모르면 비노출"
    assert scope_allows_owner(frozenset({"MNM_BATTERY"}), "") is False, \
        "소유 조직 미기재를 공개로 읽으면 이행 기간의 모든 자료가 전사 공개가 된다"


def test_only_executives_drill_down(monkeypatch):
    """★★★ 하위 조직 열람은 **경영진만**(사용자 결정 2026-07-30 ③).

    ⚠️ 일반 직원에게 하향 열람이 열리면 전사 노드에 매인 스태프 부서(회계·재무 등) 사람이
      **전 사업부 자료를 보게 된다.** 상향 상속(사업부 → 전사 표준)은 그대로 두어야 하므로,
      "펼치는가"와 "어디까지 펼치는가"를 구분해 검증한다."""
    import api.deps as deps
    import core.enterprise_context.scoping as sc
    from api.deps import Principal, viewer_visible_scopes
    from core.org_directory import AccessScope

    monkeypatch.setattr(deps, "_enforced", lambda: True)
    monkeypatch.setattr(sc, "visible_scopes",
                        lambda n, include_descendants=False, **kw: (
                            {n, "LS_MNM"} | ({"MNM_COPPER", "MNM_BATTERY"}
                                             if include_descendants else set())))

    def _p(**kw):
        return Principal(user_id="u", scope=AccessScope(
            user_id="u", unrestricted=False,
            readable_scope_nodes=frozenset({"LS_MNM"}), **kw))

    staff = viewer_visible_scopes(_p())
    assert "LS_MNM" in staff
    assert "MNM_COPPER" not in staff, "일반 직원에게 하위 사업부가 열렸다"

    exec_ = viewer_visible_scopes(_p(is_executive=True, can_run_enterprise=True))
    assert {"MNM_COPPER", "MNM_BATTERY"} <= exec_, "경영진은 하위 조직을 봐야 한다"


def test_reference_assets_reject_peeking_at_other_org(monkeypatch):
    """★★★ 자기 범위 밖 조직을 `scope_node_id` 로 지정해 **넘겨다볼 수 없다.**

    통제를 요청 파라미터로 여는 것이 바로 오늘 아침 실측한 구멍이었다 — 파라미터는 통제의
    입력이지 통제의 해제 수단이 아니다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api.routes.reference_control as rc
    import core.org_directory as od
    from api.deps import Principal, current_principal
    from core.org_directory import AccessScope

    monkeypatch.setattr(od, "_org_enforce_effective", lambda: True)
    monkeypatch.setattr(od.org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"})

    app = FastAPI()
    app.include_router(rc.router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="kim", scope=AccessScope(
            user_id="kim", unrestricted=False,
            readable_dept_ids=frozenset({"battery"}),
            readable_scope_nodes=frozenset({"MNM_BATTERY"})))
    c = TestClient(app)

    r = c.get("/api/v1/reference/assets?scope_node_id=MNM_COPPER").json()
    assert r["data"] == []
    assert "소속 조직 범위가 아닙니다" in r.get("blocked_reason", "")

    # 자기 범위는 통과한다 — 통제가 업무를 막으면 통제가 꺼진다.
    # 대역은 실물과 같은 모양을 받아야 한다 — 실물은 (범위, 등급, 경로, 하향열람)을 받는다.
    monkeypatch.setattr(rc, "visible_assets",
                        lambda node, clearance, path=None, drill=False: [{"asset_id": "a1"}])
    r2 = c.get("/api/v1/reference/assets?scope_node_id=MNM_BATTERY").json()
    assert [a["asset_id"] for a in r2["data"]] == ["a1"]


def test_packs_are_filtered_by_owner_org(monkeypatch):
    """★★★ 지식팩은 **소유 조직**으로 걸러진다. 전사(LS_MNM) 자료는 상속으로 보이고,
    다른 사업부(MNM_COPPER) 자료는 보이지 않는다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api.routes.knowledge_control as kc
    import core.knowledge_base as kb
    import core.org_directory as od
    from api.deps import Principal, current_principal
    from core.org_directory import AccessScope

    monkeypatch.setattr(od, "_org_enforce_effective", lambda: True)
    monkeypatch.setattr(od.org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"})
    monkeypatch.setattr(kb.knowledge_base, "list_packs", lambda: [
        {"pack_id": "batt", "owner_org_id": "MNM_BATTERY"},
        {"pack_id": "cu", "owner_org_id": "MNM_COPPER"},
        {"pack_id": "none", "owner_org_id": ""},
    ])
    # 상속 판정은 `scoping` 이 단일 지점이다 — 여기서 다시 구현하지 않고 대역으로 고정한다.
    import core.enterprise_context.scoping as sc
    monkeypatch.setattr(sc, "visible_scopes",
                        lambda n, **kw: {n, "LS_MNM"} if n == "MNM_BATTERY" else {n})

    app = FastAPI()
    app.include_router(kc.router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="kim", scope=AccessScope(
            user_id="kim", unrestricted=False,
            readable_dept_ids=frozenset({"battery"}),
            readable_scope_nodes=frozenset({"MNM_BATTERY"})))
    r = TestClient(app).get("/api/v1/knowledge/packs").json()

    assert [k["pack_id"] for k in r["data"]] == ["batt"]
    assert r["hidden_count"] == 2, "가려진 건수를 말해야 '이게 전부인가'를 판단할 수 있다"
