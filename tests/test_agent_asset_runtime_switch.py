"""★★★ [D-017 §9 P1-5] 기존 `/agents`·`/templates` 를 어댑터로 전환 — 응답 형태는 그대로.

## 이 파일이 지키는 것

1. **응답 형태 불변.** 기존 화면이 그대로 동작해야 한다 — 종전 키가 하나도 사라지지 않는다.
   새 정보는 **추가**만 한다(기존 화면은 모르는 키를 무시한다).
2. **승인된 것만 실행된다.** `resolve_workflow` 가 그 계약이 실제로 지켜지는 단일 지점이다.
   P1-1 이 «DRAFT 가 도는 순간 검토 단계는 형식이 된다» 를 계약으로 잡았고, 그것을 여기서 막는다.
3. **폴백하지 않는다.** 파일 로더는 깨진 파일을 `DEFAULT_REGISTRY` 로 대체하지만(부팅 안전),
   DB 자산에는 그 관대함을 주지 않는다 — 조직 워크플로우를 실행했는데 조용히 기본 파이프라인이
   도는 것은 «다른 것이 실행됐다» 이고 산출물을 보고도 알 수 없다.
4. **목록은 가시 범위만**(설계 §7.1). 초안은 기존 목록에 넣지 않는다.
"""
import pytest
from fastapi.testclient import TestClient

from core import agent_registry as reg
from core.agent_assets import (AgentAssetStore, AssetError, AssetNotFound, KIND_AGENT,
                               KIND_WORKFLOW, VIS_PERSONAL, VIS_SCOPE)

B = "/api/v1/factory"

ADMIN = "hikwon@lsmnm.com"
AI_ADMIN = "hikwon_4@lsmnm.com"     # LS_MNM·MNM_BATTERY·MNM_COPPER
MGR = "hikwon_7@lsmnm.com"          # 관리·읽기 = LS_MNM 만
MEMBER = "hikwon_2@lsmnm.com"       # 읽기 = MNM_BATTERY


def H(uid):
    return {"X-Factory-User": uid} if uid else {}


@pytest.fixture()
def store(monkeypatch, tmp_path):
    """격리된 자산 DB. ⚠️ 어댑터와 새 라우트가 각각 이름을 가져갔으므로 **두 곳** 갈아끼운다."""
    from core import agent_asset_adapter
    from api.routes import agent_governance
    s = AgentAssetStore(db_path=str(tmp_path / "a.db"))
    monkeypatch.setattr(agent_asset_adapter, "agent_assets", s)
    monkeypatch.setattr(agent_governance, "agent_assets", s)
    return s


@pytest.fixture()
def client(monkeypatch, store, ecm_org_seed):
    import config
    from core.org_directory import org_directory
    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    from main import app
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


def _wf(store, name="조직 워크플로우", scope="LS_MNM", approve=True, body=None):
    """조직 워크플로우 자산 하나. 기본은 승인까지 마친다."""
    base = reg.load_template(reg.DEFAULT_TEMPLATE_ID)
    a = store.create(KIND_WORKFLOW, name, body if body is not None else dict(base),
                     "hikwon_4@lsmnm.com", owner_scope_id=scope, visibility=VIS_SCOPE,
                     purpose="테스트용")
    if approve:
        store.submit(a["asset_id"], "hikwon_4@lsmnm.com")
        store.approve(a["asset_id"], "hikwon_4@lsmnm.com")
    return store.get(a["asset_id"])


# ── 런타임 입구: 승인된 것만 실행 ─────────────────────────────────────────
def test_file_template_still_resolves(store):
    """★★ 종전 경로가 그대로 동작한다 — 전환이 기존 실행을 깨뜨리면 안 된다."""
    from core.agent_asset_adapter import resolve_workflow
    assert resolve_workflow("default") == reg.load_template("default")
    assert resolve_workflow("") == reg.load_template(reg.DEFAULT_TEMPLATE_ID), \
        "빈 template_id 는 기본 파이프라인이다(종전 동작)"


def test_approved_org_workflow_resolves_into_registry_shape(store):
    """★★ DB 자산이 **그래프 빌더가 받는 것과 같은 dict** 로 나온다(설계 §5.3)."""
    from core.agent_asset_adapter import resolve_workflow
    a = _wf(store)
    r = resolve_workflow(a["asset_id"])
    assert r["id"] == a["asset_id"], "로더와 같은 id 스탬프가 있어야 한다"
    assert r["agents"] and all("id" in x for x in r["agents"])
    # 파일 로더가 주는 키가 하나도 빠지지 않아야 한다 — 빠진 필드는 실행 중에야 드러난다.
    assert set(reg.load_template("default")) <= set(r)


@pytest.mark.parametrize("approve", [False])
def test_unapproved_workflow_is_refused_at_runtime(store, approve):
    """★★★ **초안은 실행되지 않는다.** 이것이 P1-1 계약이 실제로 지켜지는 지점이다."""
    from core.agent_asset_adapter import resolve_workflow
    a = _wf(store, approve=approve)
    with pytest.raises(AssetError) as e:
        resolve_workflow(a["asset_id"])
    assert "승인된 워크플로우만" in str(e.value)
    # 조회 목적으로는 읽을 수 있어야 한다 — 게시 경로가 이것을 쓴다.
    assert resolve_workflow(a["asset_id"], require_runnable=False)["id"] == a["asset_id"]


def test_retired_workflow_is_refused_at_runtime(store):
    """폐기된 워크플로우로 새 프로젝트를 시작할 수 없다."""
    from core.agent_asset_adapter import resolve_workflow
    a = _wf(store)
    store.retire(a["asset_id"], ADMIN)
    with pytest.raises(AssetError):
        resolve_workflow(a["asset_id"])


def test_empty_definition_does_not_fall_back_to_default(store):
    """★★★ **폴백하지 않는다.** 조직 워크플로우를 실행했는데 조용히 기본 파이프라인이 도는 것은
    «다른 것이 실행됐다» 이고, 산출물을 보고도 알 수 없다."""
    from core.agent_asset_adapter import resolve_workflow
    a = _wf(store, body={"pipeline_name": "빈 것", "agents": []})
    with pytest.raises(AssetError) as e:
        resolve_workflow(a["asset_id"])
    assert "대체하지 않습니다" in str(e.value)


def test_wrong_kind_is_refused(store):
    """에이전트 자산 id 로 워크플로우를 실행할 수 없다 — 종류를 확인한다."""
    from core.agent_asset_adapter import resolve_workflow
    a = store.create(KIND_AGENT, "에이전트", {"role": "x"}, ADMIN, visibility=VIS_PERSONAL)
    with pytest.raises(AssetError) as e:
        resolve_workflow(a["asset_id"])
    assert "워크플로우 자산이 아닙니다" in str(e.value)


def test_missing_db_asset_raises_not_found(store):
    from core.agent_asset_adapter import resolve_workflow
    with pytest.raises(AssetNotFound):
        resolve_workflow("as_deadbeef1234")


def test_runtime_graph_entry_uses_the_adapter():
    """★★ 실행 입구가 **어댑터를 부른다.** 여기가 `load_template` 로 되돌아가면 조직
    워크플로우가 실행되지 않고, 승인 검사도 사라진다."""
    import inspect
    from core import agent_graph
    src = inspect.getsource(agent_graph.get_runtime_app)
    assert "resolve_workflow" in src
    assert "load_template" not in src, "실행 입구가 파일 로더로 되돌아갔다"


# ── 기존 API: 형태 불변 ───────────────────────────────────────────────────
def test_get_agents_keeps_its_shape(client):
    """★★★ 종전 키가 하나도 사라지지 않는다. 새 정보만 추가된다."""
    r = client.get(f"{B}/agents", headers=H(ADMIN))
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "success"
    assert d["data"] == reg.load_registry(), "data 는 종전과 같은 registry dict 여야 한다"
    assert d["source"] in ("SYSTEM", "LEGACY") and d["needs_migration"] is True


def test_get_templates_keeps_legacy_keys(client, store):
    """★★★ 기존 화면이 읽는 키가 그대로 있어야 한다."""
    _wf(store)
    items = client.get(f"{B}/templates", headers=H(AI_ADMIN)).json()["data"]
    legacy_keys = {"id", "name", "description", "agent_count", "builtin"}
    assert items and all(legacy_keys <= set(i) for i in items)
    # 파일 템플릿이 종전과 같은 목록으로 들어 있다.
    file_ids = {t["id"] for t in reg.list_templates()}
    assert file_ids <= {i["id"] for i in items}


def test_get_templates_includes_approved_org_workflow(client, store):
    """★★ P1-4 로 만든 조직 워크플로우가 **기존 화면에도 보인다** — 안 보이면 만들어도 쓸 수 없다."""
    a = _wf(store, scope="LS_MNM")
    items = client.get(f"{B}/templates", headers=H(MGR)).json()["data"]
    row = next((i for i in items if i["id"] == a["asset_id"]), None)
    assert row is not None
    assert row["source"] == "ORG" and row["builtin"] is False
    assert row["agent_count"] > 0 and row["owner_scope_id"] == "LS_MNM"


def test_get_templates_excludes_unapproved_org_workflow(client, store):
    """★★★ 초안은 기존 목록에 넣지 않는다.

    기존 화면은 `status` 를 모르므로 «목록에 있으면 쓸 수 있다» 고 판단하고, 초안으로
    프로젝트를 만들려 한다."""
    a = _wf(store, approve=False)
    ids = [i["id"] for i in client.get(f"{B}/templates", headers=H(AI_ADMIN)).json()["data"]]
    assert a["asset_id"] not in ids


def test_get_templates_is_scoped(client, store):
    """★★★ 목록은 가시 범위만 반환한다(설계 §7.1).

    `hikwon_7` 의 읽기 범위는 `LS_MNM` 하나이고 하향 열람은 경영진에게만 준다 — 그래서
    `MNM_BATTERY` 조직 워크플로우는 목록에 없다."""
    other = _wf(store, name="배터리 전용", scope="MNM_BATTERY")
    mine = _wf(store, name="본부 것", scope="LS_MNM")
    ids = [i["id"] for i in client.get(f"{B}/templates", headers=H(MGR)).json()["data"]]
    assert mine["asset_id"] in ids
    assert other["asset_id"] not in ids, "다른 조직 워크플로우가 목록에 새어 나왔다"


def test_org_workflow_detail_is_readable_by_its_scope(client, store):
    a = _wf(store, scope="LS_MNM")
    r = client.get(f"{B}/templates/{a['asset_id']}", headers=H(MGR))
    assert r.status_code == 200
    d = r.json()
    assert d["data"]["agents"], "정의 본문이 나와야 한다"
    assert d["asset_status"] and d["runnable"] is True, \
        "status 없이 body 만 주면 화면이 초안을 실행 가능한 것으로 본다"


def test_org_workflow_detail_is_404_outside_scope(client, store):
    """★★★ 가시 범위 밖은 **404** 다 — 403 은 «그 조직에 그런 워크플로우가 있다» 를 알려 준다."""
    a = _wf(store, scope="MNM_BATTERY")
    assert client.get(f"{B}/templates/{a['asset_id']}", headers=H(MGR)).status_code == 404


def test_org_workflow_detail_404_for_missing_id(client):
    assert client.get(f"{B}/templates/as_deadbeef1234", headers=H(ADMIN)).status_code == 404


def test_new_and_old_api_agree_on_visibility(client, store):
    """★★★ 두 API 가 **같은 판정 함수**를 본다. 갈라지면 한쪽에 없는 것이 다른 쪽에서 열린다."""
    a = _wf(store, scope="MNM_BATTERY")
    old = client.get(f"{B}/templates/{a['asset_id']}", headers=H(MGR)).status_code
    new = client.get(f"/api/v1/agent-governance/workflows/{a['asset_id']}",
                     headers=H(MGR)).status_code
    assert old == new == 404

    old2 = client.get(f"{B}/templates/{a['asset_id']}", headers=H(MEMBER)).status_code
    new2 = client.get(f"/api/v1/agent-governance/workflows/{a['asset_id']}",
                      headers=H(MEMBER)).status_code
    assert old2 == new2 == 200, "member 의 읽기 범위는 MNM_BATTERY 다 — 양쪽 다 보여야 한다"


def test_legacy_template_id_validation_still_applies(client):
    """★ 경로 이탈 검증이 사라지지 않았다 — `template_id` 는 파일 경로가 된다."""
    for bad in ("../../etc/passwd", "a/b", "with space"):
        r = client.get(f"{B}/templates/{bad}", headers=H(ADMIN))
        assert r.status_code in (400, 404), f"«{bad}» 가 통과했다"
