"""[I-4 3단계] **증명 발급 전 일치 게이트 + 두 지문 봉인.**

## 왜 봉인만으로는 부족한가

지문을 봉인하면 **발급 뒤의 변경**은 잡는다. 그러나 **처음부터 계약과 DB 결속이 다른
상태**에는 아무 말도 하지 않는다 — 그 상태에서 나간 증명은 어긋남을 정상으로 못박고,
이후 모든 대조가 그 어긋남을 기준으로 삼는다.

    봉인은 「그때와 같은가」에 답할 뿐 **「그때가 옳았는가」에는 답하지 않는다.**

⚠️ 이 파일은 **실제 라우터**를 태운다 — 게이트 함수만 부르면 「발급 경로에 안 걸렸다」를
  못 잡는다.
"""
import json

import pytest

from core import app_contract_gate as gate, app_manifest, app_runtime_contract as arc
from core.app_data import app_data_service

R = "/api/v1/appdata/runtime"
H_USER = {"X-Factory-User": "u@x", "X-Session-Token": "sess_raw_1",
          "X-Enterprise-Scope": "node_hq"}


def _schema():
    return {"fields": [{"name": "qty", "type": "number"}]}


def _contract(datasets, *, approved=True):
    c = {
        "schema_version": "1.0", "contract_id": "contract_000000000001", "revision": 1,
        "project_id": "proj_a", "runtime_contract_version": 1,
        "status": "APPROVED" if approved else "COMPILED",
        "app_class": "departmental", "capability_intents": [], "manifest": {},
        "datasets": datasets, "unsupported_requirements": [], "semantic_fingerprint": "",
        "approval": ({"status": "APPROVED", "approved_by": "hikwon@lsmnm.com",
                      "approved_at": "2026-08-15T00:00:00Z", "decision_ledger_id": "L1"}
                     if approved else {"status": "PENDING"}),
    }
    c["manifest"] = app_manifest.build(
        capabilities=[{"resource": d["name"], "actions": d["allowed_actions"]} for d in datasets],
        app_class="departmental")
    c["semantic_fingerprint"] = arc.semantic_fingerprint(c)
    return c


def _ds_decl(name="orders", actions=("read", "create"), role="NATIVE_SUPPLEMENT",
             intent="AFS_NATIVE", fields=None):
    return {
        "name": name, "dataset_key": name, "label": name, "purpose": "시험용",
        "allowed_actions": list(actions), "data_role": role, "source_intent": intent,
        "duplicate_entry_policy": "NO_DUPLICATE_CHECK_REQUIRED",
        "fields": fields or [{"name": "qty", "type": "number", "required": False,
                              "label": "qty", "classification": "INTERNAL"}],
    }


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """실제 앱 + 격리된 라이브러리·앱데이터·증명 저장소."""
    import config
    import core.app_data as ad
    import core.library_paths as library_paths
    from core.app_capability_token import app_capability_tokens
    from core.org_directory import org_directory
    from core.policy_shadow import policy_shadow

    lib = tmp_path / "library"
    lib.mkdir()

    def _mk(rid, contract=None):
        d = lib / rid
        d.mkdir(exist_ok=True)
        body = {
            "release_id": rid, "project_id": "proj_a", "tenant_id": "tenant_default",
            "entity_mode": "REAL", "enterprise_scope_id": "node_hq",
            "owner_user_id": "", "owner_dept_id": "hq", "visibility": "dept",
            "manifest": {"fingerprint": "fp_" + rid, "valid": True, "manifest": {
                "version": "1.0", "app_class": "departmental",
                "capabilities": ["orders.read", "orders.create", "orders.update",
                                 "orders.delete", "extra.read", "extra.create"],
                "required_capabilities": []}},
        }
        if contract is not None:
            body["runtime_contract"] = contract
        (d / "release.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(library_paths, "release_dir", lambda rid: str(lib / str(rid)),
                        raising=False)
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    monkeypatch.setattr(app_data_service._store, "db_path", str(tmp_path / "app_data.db"),
                        raising=False)
    monkeypatch.setattr(app_data_service._store, "_ready", "", raising=False)
    monkeypatch.setattr(ad, "release_identity",
                        lambda rid: ("tenant_default", "proj_a") if (lib / str(rid)).exists()
                        else None)

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
    c = TestClient(app)
    c.lib = lib
    c.mk = _mk
    return c


def _proof(c, rid="rel_a"):
    return c.post(f"{R}/proof", json={"release_id": rid}, headers=H_USER)


def _h(c, rid="rel_a"):
    r = _proof(c, rid)
    assert r.status_code == 200, r.text
    out = dict(H_USER)
    out["X-App-Proof"] = r.json()["data"]["token"]
    return out


def _materialize(rid="rel_a", name="orders", actions=("read", "create"),
                 role="NATIVE_SUPPLEMENT", intent="AFS_NATIVE", schema=None):
    return app_data_service.create_dataset(
        rid, name, schema or _schema(), actor_id="u@x", dataset_key=name,
        allowed_actions=list(actions), contract_revision=1,
        data_role=role, source_intent=intent)


# ── ① 처음부터 어긋난 상태에는 증명이 나가지 않는다 ────────────────────────
def test_a_mismatch_present_from_the_start_blocks_issuance(client):
    """★★★ **이 시험이 3단계의 이유 전부다.**

    ⚠️ 두 지문을 봉인만 하면 이 상태는 **정상으로 봉인된다** — 그 뒤로는 어긋남이 기준이
      되고, 아무 대조도 그것을 되돌리지 못한다."""
    client.mk("rel_a", _contract([_ds_decl(actions=("read",))]))
    _materialize(actions=("read", "create"))          # 계약은 read 만, DB 는 create 까지
    assert _proof(client).status_code == 404


def test_a_dataset_the_contract_declares_but_is_missing_blocks(client):
    client.mk("rel_a", _contract([_ds_decl(), _ds_decl(name="extra")]))
    _materialize()                                     # extra 를 만들지 않았다
    assert _proof(client).status_code == 404


def test_a_binding_the_contract_never_declared_blocks(client):
    """계약에 없는 결속은 **아무도 승인하지 않은 권한**이다."""
    client.mk("rel_a", _contract([_ds_decl()]))
    _materialize()
    _materialize(name="extra")
    assert _proof(client).status_code == 404


@pytest.mark.parametrize("drift", [
    {"actions": ("read",)},                            # 행동만 다름
    {"role": "SCENARIO_INPUT"},                        # 역할만 다름
    {"intent": "AFS_NATIVE", "role": "OPERATIONAL_FORECAST"},   # 역할만 다름(다른 값)
    {"schema": {"fields": [{"name": "qty", "type": "number"},
                           {"name": "memo", "type": "string"}]}},  # 스키마만 다름
])
def test_each_axis_alone_blocks_issuance(client, drift):
    """★ **한 축씩** 어긋뜨린다. 여러 축을 함께 바꾸면 하나가 안 걸려도 초록이다."""
    client.mk("rel_a", _contract([_ds_decl()]))
    _materialize(**drift)
    assert _proof(client).status_code == 404


def test_a_legacy_binding_left_in_a_contract_release_blocks(client):
    """★★★ 계약이 있는 릴리스에 **계약 이전 결속**이 남아 있으면 발급하지 않는다.

    ⚠️⚠️ 그 데이터셋에는 2차 판정이 걸리지 않는다(레거시 = 계약이 말한 적 없음) — 즉
      앱이 **아무 제한 없이** 만진다. 계약을 도입해 놓고 뒷문을 열어 둔 상태다."""
    client.mk("rel_a", _contract([_ds_decl()]))
    _materialize()
    app_data_service.create_dataset("rel_a", "extra", _schema(), actor_id="u@x")  # 레거시 결속
    r = _proof(client)
    assert r.status_code == 404
    v = gate.evaluate(json.loads((client.lib / "rel_a" / "release.json").read_text("utf-8")),
                      "rel_a")
    assert any("계약 이전 결속" in x for x in v.reasons), v.reasons


def test_a_contract_dataset_materialized_as_legacy_blocks(client):
    """계약이 정한 데이터셋인데 **레거시로** 물질화돼 있으면 발급하지 않는다.

    ⚠️ 이름과 스키마는 맞는데 계약 판정만 빠진 상태다 — 겉보기로는 정상이라 가장 놓치기 쉽다."""
    client.mk("rel_a", _contract([_ds_decl(actions=())]))
    app_data_service.create_dataset("rel_a", "orders", _schema(), actor_id="u@x",
                                    dataset_key="orders")   # allowed_actions 없음 → 레거시
    r = _proof(client)
    assert r.status_code == 404
    v = gate.evaluate(json.loads((client.lib / "rel_a" / "release.json").read_text("utf-8")),
                      "rel_a")
    assert any("contract_bound=0" in x for x in v.reasons), v.reasons


def test_a_dataset_key_drift_blocks(client):
    """★ 이름은 같은데 **안정 키가 다르다** — 계약이 승인한 그 데이터셋이 아니다.

    ⚠️ 키는 정체다. 이름만 보고 통과시키면 «이름이 같은 다른 것» 이 승인된 자리에 들어온다."""
    decl = _ds_decl()
    decl["dataset_key"] = "ds_orders_v2"
    client.mk("rel_a", _contract([decl]))
    _materialize()                                     # dataset_key = "orders"
    r = _proof(client)
    assert r.status_code == 404
    v = gate.evaluate(json.loads((client.lib / "rel_a" / "release.json").read_text("utf-8")),
                      "rel_a")
    assert any("안정 키" in x for x in v.reasons), v.reasons


def test_the_stable_key_is_part_of_the_contract_fingerprint():
    """정체가 바뀌면 그것은 **다른 데이터셋**이다 — 지문이 움직여야 한다."""
    a = _contract([_ds_decl()])
    b = _contract([dict(_ds_decl(), dataset_key="ds_orders_v2")])
    assert arc.semantic_fingerprint(a) != arc.semantic_fingerprint(b)


def test_an_invalid_contract_body_blocks_even_if_it_parses(client):
    """★ JSON 으로는 읽히지만 **계약으로는 성립하지 않는** 문서.

    ⚠️ 「읽혔으니 통과」로 두면 계약 검증을 우회한 문서가 승인된 계약 행세를 한다."""
    broken = _contract([_ds_decl()])
    broken["datasets"][0].pop("data_role")             # 필수 의미 필드가 없다
    client.mk("rel_a", broken)
    _materialize()
    r = _proof(client)
    assert r.status_code == 404
    v = gate.evaluate(json.loads((client.lib / "rel_a" / "release.json").read_text("utf-8")),
                      "rel_a")
    assert any("계약을 읽을 수 없습니다" in x for x in v.reasons), v.reasons


def test_an_unapproved_contract_blocks_issuance(client):
    """승인 전 계약으로는 앱을 열 수 없다 — 승인은 **사람이 하는 일**이다."""
    client.mk("rel_a", _contract([_ds_decl()], approved=False))
    _materialize()
    assert _proof(client).status_code == 404


def test_an_unreadable_contract_blocks_issuance(client):
    """⚠️ 판독 실패를 「없음」으로 접으면 계약이 깨진 앱이 **계약 없는 앱처럼** 열린다."""
    client.mk("rel_a", {"schema_version": "1.0", "datasets": "목록아님"})
    assert _proof(client).status_code == 404


def test_a_contractless_app_with_contract_bindings_is_fail_closed(client):
    """★★★ 계약 없는 신규 App-in-App — **물질화가 승인보다 앞선** 상태다.

    ⚠️ 그것은 「아무도 승인하지 않은 권한이 열려 있다」는 뜻이고, 열어 주면 계약 제도
      자체가 선택 사항이 된다."""
    client.mk("rel_a")                                 # 계약 없음
    _materialize()                                     # 그런데 계약 결속이 있다
    assert _proof(client).status_code == 404


def test_a_legacy_release_without_any_contract_binding_still_opens(client):
    """★ 대조군 — 계약 이전 릴리스는 그대로 열린다.
    ⚠️ 「없다」와 「어긋난다」는 다른 사실이다. 뭉개면 돌던 앱이 통째로 멈춘다."""
    client.mk("rel_a")
    app_data_service.create_dataset("rel_a", "orders", _schema(), actor_id="u@x")
    h = _h(client)
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 200


def test_a_zero_dataset_app_is_normal(client):
    """★★★ **데이터셋 0개는 정상이다** — 계약 0개 + 결속 0개.

    ⚠️ 0을 오류로 만들면 화면만 있는 앱을 만들 수 없다."""
    client.mk("rel_a", _contract([]))
    r = _proof(client)
    assert r.status_code == 200, r.text
    v = gate.evaluate(json.loads((client.lib / "rel_a" / "release.json").read_text("utf-8")),
                      "rel_a")
    assert v.ok and not v.legacy


def test_a_matching_state_issues_and_works(client):
    """대조군 — 계약과 물질화가 맞으면 발급되고 실제로 동작한다."""
    client.mk("rel_a", _contract([_ds_decl()]))
    _materialize()
    h = _h(client)
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 200
    assert client.post(f"{R}/datasets/orders/records", headers=h,
                       json={"payload": {"qty": 1}}).status_code == 200


# ── ② 발급 뒤의 변경은 410 이다 ────────────────────────────────────────────
def test_a_contract_revision_after_issuance_is_410(client):
    """계약 원문만 바뀐 경우 — 결속은 그대로다."""
    client.mk("rel_a", _contract([_ds_decl()]))
    _materialize()
    h = _h(client)
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 200

    #: 정책 문구만 바꿔도 **의미**가 달라진다(중복입력 정책은 지문에 들어간다).
    changed = _ds_decl()
    changed["duplicate_entry_policy"] = "ALLOW_SUPPLEMENT_ONLY"
    client.mk("rel_a", _contract([changed]))
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 410


def test_a_freshness_change_after_issuance_is_410(client):
    client.mk("rel_a", _contract([_ds_decl()]))
    _materialize()
    h = _h(client)
    changed = _ds_decl()
    changed["required_freshness"] = "P1D"
    client.mk("rel_a", _contract([changed]))
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 410


def test_a_materialization_change_after_issuance_is_410(client):
    """★★★ **계약 원문은 그대로인데 결속만 달라진** 경우 — 원문 지문만 봉인하면 못 잡는다."""
    client.mk("rel_a", _contract([_ds_decl()]))
    ds = _materialize()
    h = _h(client)
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 200

    app_data_service.bind_release("rel_a", ds["dataset_id"], allowed_actions=["read"],
                                  data_role="NATIVE_SUPPLEMENT", source_intent="AFS_NATIVE")
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 410


def test_a_contract_appearing_later_kills_a_running_legacy_app(client):
    """★★★ 계약이 **나중에 생기면** 이미 도는 레거시 앱도 폐기된다.

    ⚠️ 계약 없음을 빈 지문으로 두면 판정이 「양쪽 다 비었으니 같다」로 통과하고, 그 앱은
      승인 없는 상태로 계속 돈다. 그래서 표식(`no-contract`)을 봉인한다."""
    client.mk("rel_a")
    app_data_service.create_dataset("rel_a", "orders", _schema(), actor_id="u@x")
    h = _h(client)
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 200

    client.mk("rel_a", _contract([]))                  # 계약이 생겼다
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 410


def test_an_approval_revocation_after_issuance_is_410(client):
    client.mk("rel_a", _contract([_ds_decl()]))
    _materialize()
    h = _h(client)
    client.mk("rel_a", _contract([_ds_decl()], approved=False))
    assert client.get(f"{R}/datasets/orders/records", headers=h).status_code == 410


# ── ③ 폐기된 프레임은 재발급으로 되살아나지 않는다 ────────────────────────
def test_a_discarded_frame_is_not_revived_by_a_new_proof(client):
    """★★★ ⚠️⚠️ 새 증명을 받아 **옛 코드가 계속 도는** 것이 이 통제가 막으려는 전부다.

    부모가 재발급 한 번으로 낡은 프레임을 되살릴 수 있으면, 계약 변경은 아무것도 바꾸지
    못한다 — 앱은 어제의 계약 위에서 오늘의 권한으로 돈다."""
    client.mk("rel_a", _contract([_ds_decl()]))
    ds = _materialize()
    old = _h(client)
    assert client.get(f"{R}/datasets/orders/records", headers=old).status_code == 200

    #: 계약과 물질화를 **함께** 좁힌다(정상적인 개정).
    client.mk("rel_a", _contract([_ds_decl(actions=("read",))]))
    app_data_service.bind_release("rel_a", ds["dataset_id"], allowed_actions=["read"],
                                  data_role="NATIVE_SUPPLEMENT", source_intent="AFS_NATIVE")
    assert client.get(f"{R}/datasets/orders/records", headers=old).status_code == 410

    new = _h(client)                                   # 새 증명은 나간다(상태가 일치하므로)
    assert client.get(f"{R}/datasets/orders/records", headers=new).status_code == 200
    #: ★ 그런데 **옛 증명은 여전히 410** 이다 — 되살아나지 않는다.
    assert client.get(f"{R}/datasets/orders/records", headers=old).status_code == 410
    #: 그리고 새 증명으로도 좁아진 권한은 그대로다.
    assert client.post(f"{R}/datasets/orders/records", headers=new,
                       json={"payload": {"qty": 1}}).status_code == 403


def test_stale_is_410_not_401(client):
    """⚠️ 만료(401)와 나누는 이유: 만료는 새 증명을 받아 **같은 프레임**을 계속 쓴다.
    여기는 지금 도는 코드가 **낡은 코드**이므로 프레임을 버려야 한다."""
    from core import host_runtime_wire as wire
    client.mk("rel_a", _contract([_ds_decl()]))
    _materialize()
    h = _h(client)
    client.mk("rel_a", _contract([_ds_decl(actions=("read",))]))
    r = client.get(f"{R}/datasets/orders/records", headers=h)
    assert r.status_code == wire.STATUS_STALE_APP == 410


# ── ④ 봉인된 값 자체 ──────────────────────────────────────────────────────
def test_both_fingerprints_are_sealed_and_full_width(client):
    from core.app_capability_token import app_capability_tokens
    client.mk("rel_a", _contract([_ds_decl()]))
    _materialize()
    r = _proof(client)
    rec = app_capability_tokens.resolve(r.json()["data"]["token"], quiet=True)
    assert len(rec["contract_fingerprint"]) == 64          # 계약 원문(전체 sha256)
    assert len(rec["materialization_fingerprint"]) == 64   # DB 결속
    assert rec["contract_fingerprint"] != rec["materialization_fingerprint"]


def test_a_legacy_release_seals_the_no_contract_marker(client):
    from core.app_capability_token import app_capability_tokens
    client.mk("rel_a")
    r = _proof(client)
    rec = app_capability_tokens.resolve(r.json()["data"]["token"], quiet=True)
    #: ⚠️ 빈 문자열이 아니다 — 빈 값은 「양쪽 다 비었으니 같다」로 통과한다.
    assert rec["contract_fingerprint"] == gate.NO_CONTRACT != ""


def test_a_token_cannot_be_issued_without_the_pair():
    """발급 계약 자체가 빈 지문을 거부한다 — 막을 곳은 **만드는 자리**다."""
    from core.app_capability_token import AppCapabilityTokenStore, AppTokenError
    store = AppCapabilityTokenStore()
    with pytest.raises(AppTokenError) as e:
        store.issue(actor="u@x", session_id="s", app_id="a", release_id="r",
                    capabilities=("read",), tenant_id="t", entity_mode="REAL",
                    scope_node_id="n", manifest_fingerprint="fp", manifest_version="1.0")
    assert "contract_fingerprint" in str(e.value)
