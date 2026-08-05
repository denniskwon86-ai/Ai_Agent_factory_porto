"""★★★ [D-018 ⑥] **신규 쓰기는 정본 `node_id` 로 저장한다.**

## 왜 이것이 필요한가

백필(⑤)로 저장분을 정리해도, 저장 경로가 요청 값을 **그대로** 넣으면 코드가 다시 들어온다.
그러면 백필은 «한 번 청소하고 다시 더러워지는» 작업이 되고, 정본 통일은 영구히 끝나지 않는다.

실측(2026-08-05): `_scope()` 는 이미 요청 값을 정본으로 해석해 돌려주는데, 라우트가 그 결과를
**판정에만 쓰고 저장은 원본으로** 하고 있었다. `plan_facts` 에서 `org_id='MNM_BATTERY'`(코드)와
`owner_organization_id='node_36c1…'`(정본)이 갈라져 있던 것이 그 증거다.

## 무엇을 정규화하고 무엇을 두는가

- **정규화한다**: 소유·권한 판정에 쓰이는 컬럼 — `owner_scope_id`(자산) ·
  `owner_organization_id`(계획·시나리오).
- **두는 것**: `plan_facts.org_id` 는 **`fact_id` 의 구성 요소**이고(`org_id|account|period|…`)
  인덱스 3개와 화면 조회 파라미터가 그 값을 쓴다. 바꾸면 기본키가 달라져 기존 행과 이어지지
  않는다. 권한 판정은 `owner_organization_id`(정본)로 하므로 통제는 정본을 탄다.

## 거절하지 않고 정규화하는 이유

D-005 입력 호환 계약이 코드·부서 id 를 계속 받기로 했다. 저장 시점에 거절하면 이행이 끝나기
전에 화면이 멈춘다. 그래서 «받아서 정본으로 저장» 한다. 해석 못 한 값은 **원본을 유지**한다 —
빈 값으로 만들면 «소유 미지정» 이 되어 그 자산이 아무에게도 보이지 않는다.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from core.agent_assets import AgentAssetStore, VIS_PERSONAL, VIS_SCOPE

ADMIN = "hikwon@lsmnm.com"
AI_ADMIN = "hikwon_4@lsmnm.com"
MGR = "hikwon_7@lsmnm.com"        # 관리·읽기 = LS_MNM


def H(uid: str):
    return {"X-Factory-User": uid} if uid else {}


@pytest.fixture()
def client(monkeypatch, tmp_path, ecm_org_seed):
    import config
    from core.org_directory import org_directory
    from api.routes import agent_governance
    from core import agent_asset_adapter

    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    store = AgentAssetStore(db_path=str(tmp_path / "assets.db"))
    monkeypatch.setattr(agent_governance, "agent_assets", store)
    monkeypatch.setattr(agent_asset_adapter, "agent_assets", store)
    from main import app
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


# ── 자산: 소유 조직 ───────────────────────────────────────────────────────
def test_asset_owner_is_stored_canonically(client, ecm_org_seed):
    """★★★ 코드로 보내도 **정본으로 저장된다.**"""
    r = client.post("/api/v1/agent-governance/agents",
                    json={"name_ko": "원가 분석가", "visibility": VIS_SCOPE,
                          "owner_scope_id": "LS_MNM", "body": {"role": "원가"}},
                    headers=H(MGR))
    assert r.status_code == 200
    assert r.json()["owner_scope_id"] == ecm_org_seed["LS_MNM"], \
        f"코드가 그대로 저장됐다: {r.json()['owner_scope_id']}"


def test_asset_owner_accepts_dept_id_too(client, ecm_org_seed):
    """부서 id 로 보내도 정본이 된다(D-005 입력 호환 계약)."""
    r = client.post("/api/v1/agent-governance/agents",
                    json={"name_ko": "배터리 전용", "visibility": VIS_SCOPE,
                          "owner_scope_id": "production_battery", "body": {}},
                    headers=H(AI_ADMIN))
    assert r.status_code == 200
    assert r.json()["owner_scope_id"] == ecm_org_seed["MNM_BATTERY"]


def test_canonical_owner_when_already_canonical(client, ecm_org_seed):
    """이미 정본이면 그대로 — 두 번 해석해 엉뚱한 값이 되지 않는다."""
    node = ecm_org_seed["LS_MNM"]
    r = client.post("/api/v1/agent-governance/agents",
                    json={"name_ko": "정본 입력", "visibility": VIS_SCOPE,
                          "owner_scope_id": node, "body": {}}, headers=H(MGR))
    assert r.status_code == 200 and r.json()["owner_scope_id"] == node


def test_copy_also_stores_canonical_owner(client, ecm_org_seed):
    """복사도 **생성**이므로 같은 규칙이다 — 파일 자산 복사가 주 경로다."""
    r = client.post("/api/v1/agent-governance/agents/file:agent:RFP_Analyst/copy",
                    json={"visibility": VIS_SCOPE, "owner_scope_id": "LS_MNM"},
                    headers=H(MGR))
    assert r.status_code == 200
    assert r.json()["owner_scope_id"] == ecm_org_seed["LS_MNM"]


def test_unresolvable_owner_keeps_the_original(client):
    """★★★ 해석 못 한 값을 **비우지 않는다.**

    빈 값은 «소유 미지정» 이고, 저장소 계약상 그 자산은 **아무에게도 보이지 않는다**
    («모르니까 보여 준다» 금지) — 만든 사람이 자기 자산을 잃는다."""
    from api.routes.agent_governance import _canonical_owner
    assert _canonical_owner("__no_such_scope__") == "__no_such_scope__"
    assert _canonical_owner("") == ""
    assert _canonical_owner("   ") == ""


def test_personal_asset_has_no_owner_to_normalize(client):
    """개인 자산은 소유 조직이 없다 — 정규화할 것도 없고, 빈 값이 그대로 유지된다."""
    r = client.post("/api/v1/agent-governance/agents",
                    json={"name_ko": "내 초안", "visibility": VIS_PERSONAL},
                    headers=H(MGR))
    assert r.status_code == 200 and r.json()["owner_scope_id"] == ""


# ── 오류 메시지는 사람이 읽는 이름 (D-018 ③) ─────────────────────────────
def test_error_message_never_leaks_the_canonical_hash(client):
    """★★★ 정본 해시를 사용자에게 보여주지 않는다.

    `node_41402723bc90` 만 보면 **무슨 조직 때문에 막혔는지 알 수 없고** 관리자에게 무엇을
    요청해야 하는지도 모른다. 백필 후 실제로 그런 메시지가 나가고 있었다."""
    r = client.post("/api/v1/agent-governance/agents",
                    json={"name_ko": "x", "visibility": VIS_SCOPE,
                          "owner_scope_id": "MNM_COPPER"}, headers=H(MGR))
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert "node_" not in detail, f"정본 해시가 노출됐다: {detail}"
    assert "MNM_COPPER" in detail or "동제련" in detail, f"조직을 식별할 수 없다: {detail}"


# ── 계획: 소유 조직 ───────────────────────────────────────────────────────
def _planning_db():
    from core.planning_model import planning_store
    return planning_store.db_path


def test_plan_fact_owner_is_stored_canonically(client, ecm_org_seed):
    """★★★ `put_fact` 는 `owner_organization_id` 가 비면 `org_id`(코드)로 채운다 — 그래서
    **정규화된 값을 항상 채워 넘겨야** 코드가 다시 들어오지 않는다."""
    from core.planning_model import planning_store
    planning_store.upsert_account("4000", "매출", "revenue", 1, "")
    r = client.post("/api/v1/planning/facts",
                    json={"org_id": "LS_MNM", "account_code": "4000", "period": "2099",
                          "value_kind": "PLAN", "amount": 1.0},
                    headers=H(MGR))
    assert r.status_code == 200, r.json()
    con = sqlite3.connect(_planning_db())
    try:
        rows = list(con.execute(
            "SELECT org_id, owner_organization_id FROM plan_facts WHERE period='2099'"))
    finally:
        con.close()
    assert rows, "행이 저장되지 않았다"
    org_id, owner = rows[0]
    assert owner == ecm_org_seed["LS_MNM"], f"소유가 코드로 저장됐다: {owner}"
    # ⚠️ `org_id` 는 `fact_id` 의 구성 요소이므로 **그대로 둔다**(위 모듈 주석).
    assert org_id == "LS_MNM"


def test_scenario_owner_is_stored_canonically(client, ecm_org_seed):
    r = client.post("/api/v1/planning/scenarios",
                    json={"scenario_id": "__canon_test__", "name": "정본 확인",
                          "org_id": "LS_MNM"}, headers=H(MGR))
    assert r.status_code == 200, r.json()
    con = sqlite3.connect(_planning_db())
    try:
        rows = list(con.execute("SELECT org_id, owner_organization_id FROM scenarios "
                                "WHERE scenario_id='__canon_test__'"))
    finally:
        con.close()
    assert rows and rows[0][1] == ecm_org_seed["LS_MNM"], \
        f"시나리오 소유가 정본이 아니다: {rows}"
    assert rows[0][0] == "LS_MNM", "조회 키(org_id)는 그대로여야 한다"


# ── 백필과의 관계 ─────────────────────────────────────────────────────────
def test_new_writes_do_not_create_backfill_debt(client, ecm_org_seed):
    """★★★ 신규 쓰기가 **백필 대상을 새로 만들지 않는다.**

    이것이 ⑥의 목적이다 — 그러지 않으면 백필은 «청소하고 다시 더러워지는» 작업이 되고 정본
    통일이 영구히 끝나지 않는다. 백필 스크립트의 계획 함수로 직접 확인한다."""
    import scripts.backfill_scope_node_ids as bf
    from core.planning_model import planning_store

    planning_store.upsert_account("5000", "매출원가", "COGS", 1, "")
    client.post("/api/v1/planning/facts",
                json={"org_id": "LS_MNM", "account_code": "5000", "period": "2098",
                      "value_kind": "PLAN", "amount": 2.0}, headers=H(MGR))
    client.post("/api/v1/planning/scenarios",
                json={"scenario_id": "__debt_test__", "name": "t", "org_id": "LS_MNM"},
                headers=H(MGR))

    # 격리 DB 를 향해 계획을 세운다(운영 DB 를 보지 않는다).
    import os
    monkey_dir = os.path.dirname(planning_store.db_path)
    orig = bf.DATA_DIR
    try:
        bf.DATA_DIR = monkey_dir
        for table, col in (("plan_facts", "owner_organization_id"),
                           ("scenarios", "owner_organization_id")):
            item, err = bf._plan_for("planning.db", table, col)
            assert not err, err
            assert item["plan"] == [], \
                f"{table}.{col} 에 백필 대상이 새로 생겼다: {item['plan']}"
    finally:
        bf.DATA_DIR = orig
