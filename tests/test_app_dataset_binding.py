"""[I-4 2단계] 데이터셋 안정 식별자 · 릴리스 결속 · 데이터셋별 2차 판정.

지키는 것 셋:

1. **데이터셋은 앱에 속한다.** 릴리스가 바뀌어도 레코드가 승계된다 —
   종전에는 앱을 한 번 개정하면 현업 데이터가 «0건» 으로 보였다.
2. **권한은 데이터셋별이다.** 전역 합집합(`orders.read + secrets.update` → 전역 write)이
   `orders` 에 쓰기를 열어 주던 구멍을 닫는다.
3. **레거시와 «허용 없음» 은 다른 사실이다.** 뭉개면 계약이 잠근 데이터셋이 열리거나,
   계약 이전 앱이 통째로 멈춘다. 둘 다 조용하다.

⚠️ 런타임 시험은 **실제 라우터**를 태운다 — 판정 함수만 부르면 「배선을 안 탔다」를 못 잡는다.
"""
import json

import pytest

from core import app_policy as ap
from core.app_data import AppDataError, DATASET_ACTIONS, app_data_service, normalize_actions

R = "/api/v1/appdata/runtime"
H_USER = {"X-Factory-User": "u@x", "X-Session-Token": "sess_raw_1",
          "X-Enterprise-Scope": "node_hq"}


# ── 서비스 계층 ───────────────────────────────────────────────────────────
@pytest.fixture()
def svc(monkeypatch, tmp_path):
    """격리된 app_data DB 위의 서비스."""
    monkeypatch.setattr(app_data_service._store, "db_path", str(tmp_path / "app_data.db"),
                        raising=False)
    monkeypatch.setattr(app_data_service._store, "_ready", "", raising=False)
    return app_data_service


def _schema():
    return {"fields": [{"name": "qty", "type": "number"}]}


def test_actions_are_normalized_to_a_fixed_order(svc):
    """⚠️ 선언 순서를 보존하면 같은 권한이 다른 문자열로 저장되고,
    「바뀌었나」 비교가 거짓이 된다."""
    assert normalize_actions(["update", "read"]) == ("read", "update")
    assert normalize_actions(["read", "update"]) == normalize_actions(["update", "read"])
    assert normalize_actions([]) == ()
    assert normalize_actions(None) == ()


def test_unknown_action_is_not_silently_dropped(svc):
    """⚠️ 조용히 버리면 계약이 `purge` 를 선언해도 아무 일이 없고, 아무도 모른다."""
    with pytest.raises(AppDataError) as e:
        normalize_actions(["read", "purge"])
    assert "purge" in str(e.value)


def test_a_string_says_it_is_not_a_list(svc):
    """`"read"` 를 그냥 순회하면 `{'r','e','a','d'}` 가 되고, 나오는 말은
    「알 수 없는 행동: ['a','d','e','r']」이다.

    ⚠️ 막히기는 하지만 **무엇을 고쳐야 하는지 알려 주지 않는다.** 호출자는 행동 이름을
      의심하며 시간을 쓴다 — 진짜 문제는 목록이 아니라 문자열을 보냈다는 것이다."""
    with pytest.raises(AppDataError) as e:
        normalize_actions("read")
    assert "목록" in str(e.value), str(e.value)
    assert "'r'" not in str(e.value)   # 글자로 흩어진 흔적이 없다


def test_dataset_actions_match_the_contract_module():
    """⚠️ 두 목록이 갈라지면 계약이 허용한 행동을 런타임이 모르거나,
    런타임이 계약에 없는 행동을 허용한다."""
    from core import app_runtime_contract as arc
    assert DATASET_ACTIONS == arc.ACTIONS


def test_none_and_empty_actions_are_different_facts(svc):
    """★★★ 셋을 구분한다: 미결속(None) · «아무것도 허용 안 함»(()) · 목록."""
    legacy = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x")
    assert svc.allowed_actions("rel_1", legacy["dataset_id"]) is None

    locked = svc.create_dataset("rel_1", "secrets", _schema(), actor_id="u@x",
                                allowed_actions=[])
    assert svc.allowed_actions("rel_1", locked["dataset_id"]) == ()

    open_ = svc.create_dataset("rel_1", "notes", _schema(), actor_id="u@x",
                               allowed_actions=["read"])
    assert svc.allowed_actions("rel_1", open_["dataset_id"]) == ("read",)


def test_records_survive_a_new_release(svc):
    """★★★ 이것이 「앱을 개정하면 현업 데이터가 안 보인다」의 회귀다."""
    ds = svc.create_dataset("rel_v1", "orders", _schema(), actor_id="u@x",
                            app_id="app_orders", dataset_key="ds_orders",
                            allowed_actions=["read", "create"])
    svc.create_record(ds["dataset_id"], {"qty": 7}, actor_id="u@x")

    # 새 릴리스가 같은 앱의 데이터셋을 이어받는다.
    adopted = svc.adopt_dataset("app_orders", "ds_orders", "rel_v2",
                                allowed_actions=["read"], schema=_schema(),
                                contract_revision=2)
    assert adopted is not None
    assert adopted["dataset_id"] == ds["dataset_id"]      # ★ 같은 id — 레코드가 그대로다

    found = svc.find_dataset("rel_v2", "orders")
    assert found and found["dataset_id"] == ds["dataset_id"]
    rows, total = svc.list_records(ds["dataset_id"])
    assert total == 1 and rows[0]["payload"]["qty"] == 7

    # 판이 바뀌면서 권한은 좁아졌다 — 좁아진 쪽이 즉시 반영돼야 한다.
    assert svc.allowed_actions("rel_v2", ds["dataset_id"]) == ("read",)
    assert svc.allowed_actions("rel_v1", ds["dataset_id"]) == ("read", "create")


def test_adopt_refuses_to_match_on_empty_identity(svc):
    """★★★ ⚠️ 빈 값으로 맞추면 **앱 식별자가 없는 레거시 데이터셋이 전부 하나로 묶인다.**

    아래 두 데이터셋은 `app_id` 가 비어 있고 `dataset_key` 는 이름에서 왔다. 빈 식별자를
    조회 조건으로 허용하면 `adopt_dataset("", "orders", …)` 가 **남의 앱 데이터셋**을
    이어받는다 — 그 순간 다른 앱의 레코드가 이 앱에 보인다."""
    legacy_a = svc.create_dataset("rel_a", "orders", _schema(), actor_id="u@x")  # app_id 없음
    assert legacy_a["app_id"] == "" and legacy_a["dataset_key"] == "orders"

    assert svc.adopt_dataset("", "orders", "rel_b") is None      # ← 빈 app_id 로 낚아채기
    assert svc.adopt_dataset("app_x", "", "rel_b") is None       # ← 빈 key 로 낚아채기
    assert svc.adopt_dataset("app_x", "ds_orders", "rel_b") is None   # 없는 앱
    assert svc.find_dataset("rel_b", "orders") is None           # 아무것도 새로 묶이지 않았다


def test_rebinding_narrows_immediately(svc):
    """계약 개정으로 행동이 줄면 **즉시** 좁아진다 —
    ⚠️ 늘어난 것만 반영하고 줄어든 것을 무시하면 회수되지 않는 권한이 남는다."""
    ds = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                            allowed_actions=["read", "create", "update", "delete"])
    svc.bind_release("rel_1", ds["dataset_id"], allowed_actions=["read"])
    assert svc.allowed_actions("rel_1", ds["dataset_id"]) == ("read",)


def test_binding_is_scoped_to_its_release(svc):
    ds = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                            allowed_actions=["read"])
    assert svc.find_dataset("rel_other", "orders") is None
    assert svc.allowed_actions("rel_other", ds["dataset_id"]) is None


def test_duplicate_name_within_a_release_is_refused(svc):
    svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x")
    with pytest.raises(AppDataError):
        svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x")


def test_same_name_in_two_apps_stays_separate(svc):
    a = svc.create_dataset("rel_a", "orders", _schema(), actor_id="u@x", app_id="app_a",
                           dataset_key="ds_orders")
    b = svc.create_dataset("rel_b", "orders", _schema(), actor_id="u@x", app_id="app_b",
                           dataset_key="ds_orders")
    assert a["dataset_id"] != b["dataset_id"]
    assert svc.adopt_dataset("app_a", "ds_orders", "rel_a2")["dataset_id"] == a["dataset_id"]


def test_dataset_versions_are_kept_per_revision(svc):
    ds = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                            allowed_actions=["read"], contract_revision=1)
    svc.bind_release("rel_2", ds["dataset_id"], allowed_actions=["read"],
                     schema={"fields": [{"name": "qty", "type": "number"},
                                        {"name": "memo", "type": "string"}]},
                     contract_revision=2)
    rows = svc._store.query(
        "SELECT contract_revision FROM app_dataset_versions WHERE dataset_id=? "
        "ORDER BY contract_revision", (ds["dataset_id"],))
    assert [r["contract_revision"] for r in rows] == [1, 2]


def test_coverage_counts_bound_and_legacy(svc):
    svc.create_dataset("rel_1", "a", _schema(), actor_id="u@x", allowed_actions=["read"])
    svc.create_dataset("rel_1", "b", _schema(), actor_id="u@x")
    cov = svc.contract_coverage("rel_1")
    assert cov == {"bound": 1, "legacy": 1, "total": 2}


def test_list_datasets_follows_bindings(svc):
    ds = svc.create_dataset("rel_v1", "orders", _schema(), actor_id="u@x",
                            app_id="app_o", dataset_key="ds_o", allowed_actions=["read"])
    assert [d["dataset_id"] for d in svc.list_datasets("rel_v2")] == []
    svc.adopt_dataset("app_o", "ds_o", "rel_v2", allowed_actions=["read"])
    assert [d["dataset_id"] for d in svc.list_datasets("rel_v2")] == [ds["dataset_id"]]


# ── 마이그레이션 ──────────────────────────────────────────────────────────
def test_legacy_rows_are_linked_not_rewritten(monkeypatch, tmp_path):
    """★ 기존 행을 다시 쓰지 않는다 — `release_id` 는 그대로 두고 결속을 만들어 준다.

    ⚠️⚠️ 만들어지는 결속은 **`contract_bound=0`** 이다. `1` 로 채우면 「계약이 이 행동만
      허용했다」는 거짓 사실이 생기고, 그 뒤 판정은 그 거짓을 근거로 삼는다."""
    import sqlite3

    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE app_datasets (
            dataset_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL DEFAULT 'tenant_default',
            release_id TEXT NOT NULL, name TEXT NOT NULL, label TEXT NOT NULL DEFAULT '',
            schema_json TEXT NOT NULL DEFAULT '{}', app_class TEXT NOT NULL DEFAULT '',
            owner_dept_id TEXT NOT NULL DEFAULT '', scope_node_id TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '', retired_at TEXT NOT NULL DEFAULT '');
        CREATE TABLE app_records (
            record_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}', created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT '', updated_by TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '', deleted_by TEXT NOT NULL DEFAULT '',
            deleted_at TEXT NOT NULL DEFAULT '');
        INSERT INTO app_datasets (dataset_id, release_id, name, schema_json, created_at)
             VALUES ('ds_old', 'rel_old', 'orders',
                     '{"fields":[{"name":"qty","type":"number"}]}', '2026-01-01T00:00:00Z');
        INSERT INTO app_records (record_id, dataset_id, payload_json, created_by)
             VALUES ('rec_old', 'ds_old', '{"qty": 3}', 'u@x');
    """)
    conn.commit()
    conn.close()

    monkeypatch.setattr(app_data_service._store, "db_path", str(db), raising=False)
    monkeypatch.setattr(app_data_service._store, "_ready", "", raising=False)

    ds = app_data_service.find_dataset("rel_old", "orders")
    assert ds and ds["dataset_id"] == "ds_old"            # 이름으로 계속 찾힌다
    assert ds["dataset_key"] == "orders"                  # 안정 키가 채워졌다
    rows, total = app_data_service.list_records("ds_old")
    assert total == 1 and rows[0]["payload"] == {"qty": 3}   # ★ 레코드가 보존됐다

    b = app_data_service.binding_for("rel_old", "ds_old")
    assert b and b["contract_bound"] is False             # ⚠️ 레거시는 레거시라고 적는다
    assert app_data_service.allowed_actions("rel_old", "ds_old") is None
    # 원본 열을 지우지 않았다 — 마이그레이션이 실패해도 되돌릴 수 있어야 한다.
    assert app_data_service._store.one(
        "SELECT release_id FROM app_datasets WHERE dataset_id='ds_old'")["release_id"] == "rel_old"


def test_migration_is_rerunnable(monkeypatch, tmp_path):
    """`ensure_schema()` 를 두 번 돌려도 결속이 두 벌 생기지 않는다."""
    monkeypatch.setattr(app_data_service._store, "db_path", str(tmp_path / "x.db"),
                        raising=False)
    monkeypatch.setattr(app_data_service._store, "_ready", "", raising=False)
    ds = app_data_service.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                                         allowed_actions=["read"])
    for _ in range(3):
        app_data_service._store._ready = ""
        app_data_service._store.ensure_schema()
    n = app_data_service._store.scalar(
        "SELECT COUNT(*) FROM app_release_dataset_bindings WHERE dataset_id=?",
        (ds["dataset_id"],))
    assert n == 1
    # 재실행이 계약 결속을 레거시로 되돌리지 않는다.
    assert app_data_service.allowed_actions("rel_1", ds["dataset_id"]) == ("read",)


def test_stable_identity_has_no_update_path():
    """⚠️ `dataset_key`·`name` 을 바꿀 수 있게 하면 「이름이 같은 다른 것」과
    「이름이 다른 같은 것」을 구분할 방법이 사라진다(설계 §18 — v1 은 변경 불가).

    주석은 빼고 본다 — 「바꾸지 않는다」는 **주석**이 검사를 통과시킨 적이 있다."""
    import inspect
    import re
    from core import app_data
    src = "\n".join(l.split("#")[0] for l in inspect.getsource(app_data).splitlines())
    assert not re.search(r"UPDATE\s+app_datasets\s+SET[^\"']*\bdataset_key\s*=", src, re.I)
    assert not re.search(r"UPDATE\s+app_datasets\s+SET[^\"']*\bname\s*=", src, re.I)


# ── 런타임 2차 판정 (실제 라우터) ─────────────────────────────────────────
@pytest.fixture()
def client(monkeypatch, tmp_path):
    import config
    import core.library_paths as library_paths
    from core.app_capability_token import app_capability_tokens
    from core.org_directory import org_directory
    from core.policy_shadow import policy_shadow

    lib = tmp_path / "library"
    lib.mkdir()

    def _mk(rid, *, caps):
        d = lib / rid
        d.mkdir()
        (d / "release.json").write_text(json.dumps({
            "release_id": rid, "project_id": "proj_a", "tenant_id": "tenant_default",
            "entity_mode": "REAL", "enterprise_scope_id": "node_hq",
            "owner_user_id": "", "owner_dept_id": "hq", "visibility": "dept",
            "manifest": {"fingerprint": "fp_" + rid, "valid": True, "manifest": {
                "version": "1.0", "app_class": "departmental",
                "capabilities": caps, "required_capabilities": []}},
        }, ensure_ascii=False), encoding="utf-8")

    #: ★★★ 대조군의 핵심: 매니페스트는 **전역으로** 쓰기·삭제를 준다.
    #:   그래도 계약이 `orders` 에 주지 않았으면 `orders` 는 못 쓴다.
    _mk("rel_wide", caps=["orders.read", "secrets.create", "secrets.update", "secrets.delete"])
    _mk("rel_legacy", caps=["orders.read", "orders.create", "orders.update", "orders.delete"])

    monkeypatch.setattr(library_paths, "release_dir", lambda rid: str(lib / str(rid)),
                        raising=False)
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)

    class _Scope:
        readable_dept_ids = frozenset({"hq"})
        writable_dept_ids = frozenset({"hq"})
        unrestricted = False
        can_manage_standard = False
        primary_dept_id = "hq"
        readable_scope_nodes = frozenset({"node_hq"})

        def can_read(self, d):
            return d in self.readable_dept_ids

        def can_write(self, d):
            return d in self.writable_dept_ids

    monkeypatch.setattr(org_directory, "resolve_scope", lambda uid="": _Scope())
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: False)
    monkeypatch.setattr(org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"} if uid else None)
    monkeypatch.setattr(org_directory, "get_ownership",
                        lambda kind, rid: {"dept_id": "hq", "owner_user_id": "",
                                           "visibility": "dept"})
    app_capability_tokens._tokens.clear()
    policy_shadow.reset()

    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def _h(c, release_id):
    r = c.post(f"{R}/proof", json={"release_id": release_id}, headers=H_USER)
    assert r.status_code == 200, r.text
    out = dict(H_USER)
    out["X-App-Proof"] = r.json()["data"]["token"]
    return out


def test_contract_beats_the_global_union(client):
    """★★★ **이 시험이 2단계의 이유 전부다.**

    매니페스트는 `secrets.create/update/delete` 때문에 **전역 write·delete** 를 갖는다.
    종전 구조에서는 그 전역 권한이 `orders` 에도 그대로 열렸다.
    계약이 `orders` 에 `read` 만 줬다면 `orders` 쓰기는 막혀야 한다."""
    ds = app_data_service.create_dataset(
        "rel_wide", "orders", _schema(), actor_id="u@x", allowed_actions=["read"])
    h = _h(client, "rel_wide")

    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 200
    #: ⚠️ 403 이다(404 가 아니다) — 그 앱 **자신의 계약**에 대한 사실이므로 숨기지 않는다.
    #:   숨기면 개발자는 계약 대신 이름을 의심한다.
    assert client.post(f"{R}/datasets/orders/records", headers=h,
                       json={"payload": {"qty": 1}}).status_code == 403

    rec = app_data_service.create_record(ds["dataset_id"], {"qty": 1}, actor_id="u@x")
    assert client.put(f"{R}/datasets/orders/records/{rec['record_id']}", headers=h,
                      json={"payload": {"qty": 2}}).status_code == 403
    assert client.delete(f"{R}/datasets/orders/records/{rec['record_id']}",
                         headers=h).status_code == 403
    #: 읽기는 여전히 된다 — 「전부 거부」로 초록이 되는 시험이 아니다.
    assert client.get(f"{R}/datasets/orders/records/{rec['record_id']}",
                      headers=h).status_code == 200


def test_create_and_update_are_separate_grants(client):
    """계약의 행동은 넷이다. `create` 만 준 데이터셋에 `update` 가 열리면 안 된다 —
    ⚠️ 정책 축(WRITE)에서 유도하면 이 둘이 한 덩어리가 된다."""
    ds = app_data_service.create_dataset(
        "rel_wide", "orders", _schema(), actor_id="u@x", allowed_actions=["read", "create"])
    h = _h(client, "rel_wide")
    r = client.post(f"{R}/datasets/orders/records", headers=h, json={"payload": {"qty": 1}})
    assert r.status_code == 200, r.text
    rid = r.json()["data"]["record_id"]
    assert client.put(f"{R}/datasets/orders/records/{rid}", headers=h,
                      json={"payload": {"qty": 2}}).status_code == 403
    assert client.delete(f"{R}/datasets/orders/records/{rid}", headers=h).status_code == 403


def test_schema_read_needs_read_specifically(client):
    """스키마 조회는 `read` 다. ⚠️ 다른 행동으로 대신할 수 없다 —
    「쓸 수 있으니 볼 수도 있겠지」는 계약이 말한 적 없는 추론이다."""
    #: 쓰기만 준 데이터셋 — 스키마도 못 본다.
    app_data_service.create_dataset("rel_wide", "secrets", _schema(), actor_id="u@x",
                                    allowed_actions=["create"])
    #: 읽기만 준 데이터셋 — 스키마가 보인다(대조군).
    app_data_service.create_dataset("rel_wide", "orders", _schema(), actor_id="u@x",
                                    allowed_actions=["read"])
    h = _h(client, "rel_wide")
    assert client.get(f"{R}/datasets/secrets/schema", headers=h).status_code == 403
    assert client.get(f"{R}/datasets/orders/schema", headers=h).status_code == 200


def test_unknown_dataset_name_is_not_found_not_forbidden(client):
    """⚠️ 계약에 **없는 이름**은 404 다 — 존재를 알리지 않는다.
    (계약에 있으나 행동이 없는 것은 403. 그 둘은 다른 사실이다.)"""
    app_data_service.create_dataset("rel_wide", "orders", _schema(), actor_id="u@x",
                                    allowed_actions=["read"])
    h = _h(client, "rel_wide")
    assert client.get(f"{R}/datasets/nosuch/records", headers=h).status_code == 404
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 200


@pytest.mark.parametrize("crafted", [
    "orders/../secrets", "orders%2F..%2Fsecrets", "ORDERS", "orders ", " orders",
    "orders;secrets", "orders,secrets",
])
def test_crafted_names_cannot_reach_another_dataset(client, crafted):
    """동적으로 조립한 이름으로 계약을 우회할 수 없다."""
    app_data_service.create_dataset("rel_wide", "orders", _schema(), actor_id="u@x",
                                    allowed_actions=["read"])
    app_data_service.create_dataset("rel_wide", "secrets", _schema(), actor_id="u@x",
                                    allowed_actions=[])
    h = _h(client, "rel_wide")
    r = client.post(f"{R}/datasets/{crafted}/records", headers=h, json={"payload": {"qty": 1}})
    assert r.status_code in (403, 404, 405), (crafted, r.status_code)


def test_narrowing_the_contract_blocks_an_existing_proof(client):
    """★ 계약 개정으로 행동이 줄면 **이미 발급된 증명이 즉시 막힌다.**

    ⚠️ 증명 수명이 남았다고 옛 권한을 계속 주면, 권한 회수가 최대 TTL 만큼 늦는다."""
    ds = app_data_service.create_dataset(
        "rel_wide", "orders", _schema(), actor_id="u@x", allowed_actions=["read", "create"])
    h = _h(client, "rel_wide")
    assert client.post(f"{R}/datasets/orders/records", headers=h,
                       json={"payload": {"qty": 1}}).status_code == 200

    app_data_service.bind_release("rel_wide", ds["dataset_id"], allowed_actions=["read"])
    assert client.post(f"{R}/datasets/orders/records", headers=h,
                       json={"payload": {"qty": 2}}).status_code == 403
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 200


def test_legacy_release_keeps_working(client):
    """⚠️ 계약 이전 릴리스를 2차 판정으로 막으면 **돌던 앱이 통째로 멈춘다.**
    「계약이 말한 적 없음」과 「계약이 금지함」은 다른 사실이다."""
    app_data_service.create_dataset("rel_legacy", "orders", _schema(), actor_id="u@x")
    h = _h(client, "rel_legacy")
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 200
    r = client.post(f"{R}/datasets/orders/records", headers=h, json={"payload": {"qty": 1}})
    assert r.status_code == 200, r.text
    assert app_data_service.contract_coverage("rel_legacy")["bound"] == 0


def test_second_stage_runs_after_the_first(client):
    """★★★ 순서를 바꾸지 않는다.

    ⚠️ 1차(증명)를 데이터셋 뒤로 옮기면 **증명이 없어도 이름의 존재 여부가 새어 나간다.**
      증명 없이 부른 «있는 이름» 과 «없는 이름» 의 답이 같아야 한다."""
    app_data_service.create_dataset("rel_wide", "orders", _schema(), actor_id="u@x",
                                    allowed_actions=["read"])
    a = client.get(f"{R}/datasets/orders/records", headers=H_USER)
    b = client.get(f"{R}/datasets/nosuch/records", headers=H_USER)
    assert a.status_code == b.status_code == 403
    assert a.json() == b.json()


def test_denial_reason_is_audited_not_returned(client):
    """정확한 사유는 감사에만 남고 앱에는 고정 문구가 간다."""
    app_data_service.create_dataset("rel_wide", "orders", _schema(), actor_id="u@x",
                                    allowed_actions=["read"])
    h = _h(client, "rel_wide")
    seen = []
    from core.enterprise_context import audit
    real = audit.record

    def _spy(event, *a, **kw):
        seen.append(kw.get("detail", ""))
        return real(event, *a, **kw)

    audit.record = _spy
    try:
        r = client.post(f"{R}/datasets/orders/records", headers=h, json={"payload": {"qty": 1}})
    finally:
        audit.record = real
    assert r.status_code == 403
    assert ap.DENY_DATASET_ACTION not in json.dumps(r.json(), ensure_ascii=False)
    assert any(ap.DENY_DATASET_ACTION in d for d in seen), seen
