"""★★★ [BDR-201·202·203] 키트 레지스트리와 Kit Instance.

이 시험이 전제하는 것: **저장소는 conftest 가 `tmp_path` 로 격리한다.** 조직 경계를
보는 절만 `seeded_org`·`enforced_org` 를 붙인다.

⚠️ 이 파일이 지키는 두 가지 —
  ① **템플릿은 운영 Data Contract 가 아니다.** 키트를 등록했다고 데이터가 생기지 않는다.
  ② **명시 범위 없는 인스턴스는 0건.** 「비어 있으면 전사」 같은 기본값은 한 번 새면
     되돌릴 수 없다 — 그 자원이 어느 조직 것이었는지 아무도 모르게 되기 때문이다.
"""
import json
import os

import pytest

from core.data_preparation import kit_registry as kr
from core.data_preparation import models as m
from core.data_preparation.store import DataPreparationStore


@pytest.fixture
def store(tmp_path):
    return DataPreparationStore(db_path=str(tmp_path / "dp.db"))


def _profile(**kw):
    base = {"kit_id": "k1", "version": "1.0.0", "name": "키트", "mode": "DEMO/SYNTHETIC",
            "datasets": [{"dataset_contract_key": "arrivals", "label": "입고",
                          "fields": [{"name": "qty", "type": "number"}]}]}
    base.update(kw)
    return base


def _write(tmp_path, profile, name="k1.kit.json"):
    p = tmp_path / name
    p.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    return str(p)


# ── 저장소 ───────────────────────────────────────────────────────────────
def test_the_store_does_not_open_a_file_on_construction(tmp_path):
    """★★★ [2026-08-17 원장 사고의 교훈] **만드는 것만으로 파일을 열지 않는다.**

    ⚠️ `__init__` 이 DB 를 열면 import 만으로 운영 파일이 생기고, autouse fixture 는
      그보다 늦다. 새 저장소를 만들 때 이 습관을 처음부터 들인다."""
    target = tmp_path / "아직없음.db"
    s = DataPreparationStore(db_path=str(target))
    assert s._prepared_for is None
    assert not target.exists()
    s.list_kit_versions()
    assert target.exists()


def test_the_schema_is_idempotent(tmp_path):
    """★ 마이그레이션을 다시 돌려도 같다 — Gate C 의 「재실행 멱등」."""
    p = str(tmp_path / "dp.db")
    a = DataPreparationStore(db_path=p)
    a.upsert_kit_version(kit_id="k1", version="1.0.0", name="n", mode="DEMO/SYNTHETIC",
                         source_path="k.json", fingerprint_value="f", profile={})
    b = DataPreparationStore(db_path=p)
    b._ready()
    b._ready()
    assert len(b.list_kit_versions()) == 1, "재실행이 자료를 지웠거나 두 배로 만들었다"


def test_a_blank_path_is_not_replaced_by_the_live_one():
    """⚠️ `db_path=""` 를 「지정 안 함」으로 읽으면 운영 파일이 열린다 — 원장과 같은 함정."""
    assert DataPreparationStore(db_path="").db_path == ""


# ── 키트 로더 ────────────────────────────────────────────────────────────
def test_a_valid_profile_loads_with_a_content_fingerprint(tmp_path):
    path = _write(tmp_path, _profile())
    kit = kr.load_profile(path)
    assert kit.kit_id == "k1" and kit.version == "1.0.0"
    assert len(kit.fingerprint) == 64


def test_the_fingerprint_follows_the_content_not_the_path(tmp_path):
    """★ 같은 문서가 옮겨 다녀도 같은 키트다 — 경로나 시각을 쓰면 그때마다 달라진다."""
    a = kr.load_profile(_write(tmp_path, _profile(), "a.kit.json"))
    b = kr.load_profile(_write(tmp_path, _profile(), "b.kit.json"))
    assert a.fingerprint == b.fingerprint

    changed = kr.load_profile(_write(tmp_path, _profile(name="다른 이름"), "c.kit.json"))
    assert changed.fingerprint != a.fingerprint, "문서가 바뀌었는데 지문이 그대로다"


@pytest.mark.parametrize("profile,why", [
    ({"version": "1.0.0", "name": "n", "datasets": [{"dataset_contract_key": "a"}]}, "kit_id"),
    (_profile(version="latest"), "version"),
    (_profile(version="1.0"), "version"),
    (_profile(mode="아무거나"), "mode"),
    (_profile(datasets=[]), "datasets"),
    (_profile(datasets=[{"label": "이름 없음"}]), "dataset_contract_key"),
])
def test_a_broken_kit_is_refused_not_partially_loaded(tmp_path, profile, why):
    """★★★ 「일단 읽고 되는 만큼 쓰자」로 두면 필드 절반이 빠진 키트가 등록되고,
    그것을 적용한 조직은 «왜 이 항목이 없지» 를 **데이터를 넣은 뒤에** 발견한다."""
    with pytest.raises(kr.KitLoadError) as e:
        kr.load_profile(_write(tmp_path, profile))
    assert why in str(e.value)


def test_unreadable_json_is_refused(tmp_path):
    p = tmp_path / "bad.kit.json"
    p.write_text("{깨진", encoding="utf-8")
    with pytest.raises(kr.KitLoadError):
        kr.load_profile(str(p))


def test_discover_raises_instead_of_skipping_a_broken_kit(tmp_path):
    """⚠️ 조용히 건너뛰면 「키트가 없다」와 「키트가 깨졌다」가 같은 화면이 된다."""
    _write(tmp_path, _profile(), "good.kit.json")
    (tmp_path / "bad.kit.json").write_text("{", encoding="utf-8")
    with pytest.raises(kr.KitLoadError):
        kr.discover(str(tmp_path))


def test_the_demo_kit_in_the_repo_loads():
    """★ 시연 키트가 실제로 읽혀야 한다 — 문서만 있고 안 읽히면 시연이 멈춘다."""
    kits = {k.kit_id: k for k in kr.discover()}
    assert kr.DEMO_KIT_ID in kits, f"시연 키트를 찾지 못했다: {sorted(kits)}"
    demo = kits[kr.DEMO_KIT_ID]
    assert demo.name == kr.DEMO_KIT_NAME
    assert demo.mode == m.KIT_MODE_DEMO, "시연 키트가 실제 업무 데이터로 표시돼 있다"
    #: ★★★ [2026-08-20 §4.4] 시연 키트가 **첫 수직 경로 전체**를 덮는다. 종전에는 셋뿐이라
    #:   영향 경로가 영영 「근거 없음」이었다.
    #: ⚠️ 이름은 `core/ontology_path.CHAIN` 과 **글자 그대로** 같아야 한다 —
    #:   `tests/test_baseline_and_calc.py` 가 그 정렬을 따로 못박는다.
    assert kr.dataset_keys(demo.profile) == [
        "external_indicators", "financials", "material_arrivals", "materials",
        "production_plans", "products", "purchase_orders", "shipments",
        "supplier_master"]


# ── 등록 ─────────────────────────────────────────────────────────────────
def test_registering_is_idempotent_and_follows_the_document(store, tmp_path):
    path = _write(tmp_path, _profile())
    kr.register_all(store, str(tmp_path))
    kr.register_all(store, str(tmp_path))
    rows = store.list_kit_versions()
    assert len(rows) == 1, "같은 판본이 두 번 등록됐다"
    first_fp = rows[0]["fingerprint"]

    #: 문서가 바뀌면 **지문이 따라 바뀐다** — 그 사실이 보여야 한다
    _write(tmp_path, _profile(name="이름을 고쳤다"))
    kr.register_all(store, str(tmp_path))
    rows = store.list_kit_versions()
    assert len(rows) == 1 and rows[0]["fingerprint"] != first_fp


def test_an_unknown_version_is_not_resolved_to_the_latest(store, tmp_path):
    """⚠️ 「없으면 최신으로」는 편해 보이지만, 고른 것과 적용된 것이 달라지고 그 차이는
    데이터가 들어간 뒤에야 드러난다."""
    kr.register_all(store, str(tmp_path)) if False else None
    _write(tmp_path, _profile())
    kr.register_all(store, str(tmp_path))
    assert kr.resolve(store, "k1", "1.0.0") is not None
    assert kr.resolve(store, "k1", "9.9.9") is None
    assert kr.resolve(store, "없는키트", "1.0.0") is None


def test_a_kit_mode_outside_the_list_is_refused(store):
    with pytest.raises(m.DataPreparationError):
        store.upsert_kit_version(kit_id="k", version="1.0.0", name="n", mode="아무거나",
                                 source_path="p", fingerprint_value="f", profile={})


# ── Kit Instance ─────────────────────────────────────────────────────────
def _instance(store, **kw):
    base = dict(kit_id="k1", version="1.0.0", kit_fingerprint="f",
                tenant_id="t1", scope_node_id="n1", entity_mode="REAL")
    base.update(kw)
    return store.create_instance(**base)


@pytest.mark.parametrize("missing", ["tenant_id", "scope_node_id", "entity_mode"])
def test_an_instance_without_explicit_context_is_refused(store, missing):
    """★★★ **명시 범위 없는 인스턴스 0건**(Gate C).

    ⚠️ 「비어 있으면 전사」 같은 공용 기본값은 한 번 새면 되돌릴 수 없다 — 그 자원이
      어느 조직 것이었는지 아무도 모르게 되기 때문이다."""
    with pytest.raises(m.DataPreparationError):
        _instance(store, **{missing: ""})


def test_an_unknown_entity_mode_is_refused(store):
    """⚠️ 실제 데이터와 가상 시나리오를 섞으면 둘 다 못 쓴다."""
    with pytest.raises(m.DataPreparationError):
        _instance(store, entity_mode="아무거나")


def test_listing_shows_only_the_visible_scopes(store):
    a = _instance(store, scope_node_id="n1")
    b = _instance(store, scope_node_id="n2")
    seen = store.list_instances(tenant_id="t1", entity_mode="REAL", scope_node_ids=["n1"])
    assert [r["instance_id"] for r in seen] == [a["instance_id"]]
    assert b["instance_id"] not in {r["instance_id"] for r in seen}


def test_an_empty_scope_list_shows_nothing_not_everything(store):
    """★★★ 「비었으니 전부」로 읽는 순간 타 조직 자원이 목록에 뜬다 — **개수조차 누설**이다."""
    _instance(store)
    assert store.list_instances(tenant_id="t1", entity_mode="REAL",
                                scope_node_ids=[]) == []


def test_another_tenant_or_mode_is_not_listed(store):
    _instance(store, tenant_id="t1", entity_mode="REAL")
    assert store.list_instances(tenant_id="t2", entity_mode="REAL",
                                scope_node_ids=["n1"]) == []
    assert store.list_instances(tenant_id="t1", entity_mode="VIRTUAL",
                                scope_node_ids=["n1"]) == []


def test_registering_a_kit_does_not_create_any_data(store, tmp_path):
    """★★★ **템플릿은 운영 Data Contract 가 아니다.**

    ⚠️ 등록만으로 데이터가 있는 것처럼 보이면, 그 위에서 계산이 돌아 **없는 숫자로
      경영 판단**을 하게 된다."""
    _write(tmp_path, _profile())
    kr.register_all(store, str(tmp_path))
    inst = _instance(store)
    assert store.list_bindings(inst["instance_id"]) == []
    assert store.active_binding(inst["instance_id"], "arrivals") is None


# ── [BDR-203] API 경계 ───────────────────────────────────────────────────
#
# 이 절이 전제하는 것: **`enforced_org`**(합성 조직 + 강제 ON). 여기서 보는 것이
# 「누가 무엇을 볼 수 있는가」이므로 조직 경계가 필요하다.
import unittest.mock as _mock                                        # noqa: E402

from fastapi import FastAPI                                          # noqa: E402
from fastapi.testclient import TestClient                            # noqa: E402

import api.routes.data_preparation_control as dp                     # noqa: E402
from tests import org_seed                                           # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch, enforced_org):
    """⚠️ `ORG_TRUST_HEADER` 를 켠다 — 꺼져 있으면 서버가 헤더를 무시하고 전부 401 이
    되어, 「권한이 막았다」와 「신원을 못 읽었다」가 같은 모양이 된다."""
    import config

    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    app = FastAPI()
    app.include_router(dp.router)
    return TestClient(app)


def _as(user):
    return {"X-Factory-User": user}


def _ctx_stub(tenant="tenant_default", mode="REAL"):
    return lambda p: {"tenant_id": tenant, "entity_mode": mode}


def test_the_kit_list_is_served(client):
    r = client.get("/api/v1/data-preparation/kits", headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    kits = {k["kit_id"] for k in r.json()["data"]["kits"]}
    assert kr.DEMO_KIT_ID in kits


def test_an_unknown_kit_version_is_404(client):
    r = client.get(f"/api/v1/data-preparation/kits/{kr.DEMO_KIT_ID}/versions/9.9.9",
                   headers=_as(org_seed.ADMIN))
    assert r.status_code == 404


def test_the_request_model_does_not_accept_a_tenant():
    """★★★ `tenant_id` 를 받으면 **남의 tenant 를 적어 보내는 경로**가 열린다.
    막는 것은 라우트의 검사가 아니라 **모델에 그 필드가 없는 것**이다."""
    assert set(dp.InstanceCreateRequest.model_fields) == {
        "kit_id", "version", "scope_node_id", "entity_mode", "label"}


def test_creating_an_instance_derives_the_tenant_from_the_context(client, monkeypatch):
    monkeypatch.setattr(dp, "_ctx", _ctx_stub(tenant="t_derived"))
    client.get("/api/v1/data-preparation/kits", headers=_as(org_seed.ADMIN))
    r = client.post("/api/v1/data-preparation/instances",
                    json={"kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
                          "scope_node_id": "n_any", "entity_mode": "REAL"},
                    headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["tenant_id"] == "t_derived"


@pytest.mark.parametrize("bad", ["", "   "])
def test_an_instance_without_a_scope_is_refused_by_the_api(client, monkeypatch, bad):
    monkeypatch.setattr(dp, "_ctx", _ctx_stub())
    client.get("/api/v1/data-preparation/kits", headers=_as(org_seed.ADMIN))
    r = client.post("/api/v1/data-preparation/instances",
                    json={"kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
                          "scope_node_id": bad, "entity_mode": "REAL"},
                    headers=_as(org_seed.ADMIN))
    assert r.status_code in (404, 422), r.text


def test_another_scope_is_hidden_as_404(client, monkeypatch):
    """★★★ 없는 것과 못 보는 것을 **같은 404** 로 돌려준다 — 다르게 답하면 그 응답이
    「그 조직에 그런 자원이 있다」를 알려 주는 신호가 된다."""
    monkeypatch.setattr(dp, "_ctx", _ctx_stub())
    monkeypatch.setattr(dp, "_visible_scopes", lambda p: ["n_mine"])
    made = dp.store.create_instance(kit_id="k", version="1.0.0", kit_fingerprint="f",
                                    tenant_id="tenant_default", scope_node_id="n_theirs",
                                    entity_mode="REAL")
    missing = client.get("/api/v1/data-preparation/instances/ki_없는것",
                         headers=_as(org_seed.MEMBER_A))
    theirs = client.get(f"/api/v1/data-preparation/instances/{made['instance_id']}",
                        headers=_as(org_seed.MEMBER_A))
    assert missing.status_code == theirs.status_code == 404
    assert missing.json()["detail"] == theirs.json()["detail"], "두 답이 다르면 그 차이가 신호다"


def test_a_state_conflict_is_409(client, monkeypatch):
    """⚠️ 지금 상태에서 할 수 없는 일은 **409** 다 — 422 로 주면 사용자가 요청을
    고쳐 보려 한다."""
    monkeypatch.setattr(dp, "_ctx", _ctx_stub())
    monkeypatch.setattr(dp, "_visible_scopes", lambda p: ["n1"])
    inst = dp.store.create_instance(kit_id="k", version="1.0.0", kit_fingerprint="f",
                                    tenant_id="tenant_default", scope_node_id="n1",
                                    entity_mode="REAL")
    b = dp.store.create_binding(
        instance_id=inst["instance_id"], dataset_contract_key="arrivals",
        provider="FILE_SNAPSHOT", config={"file_name": "a.csv", "column_map": {"a": "A"}},
        tenant_id="tenant_default", scope_node_id="n1", entity_mode="REAL")
    #: DRAFT 에서 곧바로 활성화 — 표가 허용하지 않는다
    r = client.post(f"/api/v1/data-preparation/bindings/{b['binding_id']}/decision",
                    json={"action": "ACTIVATE"}, headers=_as(org_seed.ADMIN))
    assert r.status_code == 409, r.text
    assert "가능한 다음 상태" in r.json()["detail"]


def test_an_unknown_action_is_422(client, monkeypatch):
    monkeypatch.setattr(dp, "_ctx", _ctx_stub())
    monkeypatch.setattr(dp, "_visible_scopes", lambda p: ["n1"])
    inst = dp.store.create_instance(kit_id="k", version="1.0.0", kit_fingerprint="f",
                                    tenant_id="tenant_default", scope_node_id="n1",
                                    entity_mode="REAL")
    b = dp.store.create_binding(
        instance_id=inst["instance_id"], dataset_contract_key="a", provider="AFS_NATIVE",
        config={"dataset_name": "a"}, tenant_id="tenant_default", scope_node_id="n1",
        entity_mode="REAL")
    r = client.post(f"/api/v1/data-preparation/bindings/{b['binding_id']}/decision",
                    json={"action": "지우기"}, headers=_as(org_seed.ADMIN))
    assert r.status_code == 422


def test_a_context_that_cannot_be_resolved_is_503(client, monkeypatch):
    """⚠️ 빈 문맥으로 넘어가면 전부 막히고 사용자에게는 「고장」으로 보인다 —
    확정하지 못했다고 말하는 편이 낫다."""
    from fastapi import HTTPException

    def _boom(p):
        raise HTTPException(status_code=503, detail="실행 문맥을 확정하지 못했습니다")

    monkeypatch.setattr(dp, "_ctx", _boom)
    r = client.post("/api/v1/data-preparation/instances",
                    json={"kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
                          "scope_node_id": "n1", "entity_mode": "REAL"},
                    headers=_as(org_seed.ADMIN))
    assert r.status_code == 503


def test_creating_an_instance_in_an_invisible_scope_is_404(client, monkeypatch):
    """★★★ 보이지 않는 범위에 자원을 **만들 수 없다.**

    ⚠️ 앞 시험은 이것을 못 잡는다 — 빈 범위는 `assert_context` 가 422 로 먼저
      막아서, 「범위 가시성 검사를 지운다」는 변이가 관찰되지 않는다(변이 검사 실측).
      **보이지 않는 «실재하는» 범위**를 써야 그 검사가 유일한 방어선이 된다."""
    monkeypatch.setattr(dp, "_ctx", _ctx_stub())
    monkeypatch.setattr(dp, "_visible_scopes", lambda p: ["n_mine"])
    client.get("/api/v1/data-preparation/kits", headers=_as(org_seed.ADMIN))
    r = client.post("/api/v1/data-preparation/instances",
                    json={"kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
                          "scope_node_id": "n_theirs", "entity_mode": "REAL"},
                    headers=_as(org_seed.MEMBER_A))
    assert r.status_code == 404, r.text
    assert "조직 범위를 찾을 수 없습니다" in r.json()["detail"]


def test_a_broken_kit_makes_the_list_fail_loudly(client, monkeypatch):
    """★★★ 깨진 키트를 200 으로 넘기면 화면은 **아무것도 없는 것처럼** 보인다.

    ⚠️ 그러면 「키트가 없다」와 「키트가 깨졌다」가 같은 화면이 되고, 사람은 등록이
      안 됐다고 생각해 문서를 다시 만든다."""
    def _boom(*_a, **_k):
        raise kr.KitLoadError("k.kit.json: 판독 실패")

    monkeypatch.setattr(dp.kit_registry, "register_all", _boom)
    r = client.get("/api/v1/data-preparation/kits", headers=_as(org_seed.ADMIN))
    assert r.status_code == 503, r.text
    assert "키트를 읽을 수 없습니다" in r.json()["detail"]
