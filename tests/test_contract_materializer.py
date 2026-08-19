"""★★★ [Wave F-0] 승인된 계약 → 실제 데이터셋. **승인이 무언가를 만들게 한다.**

## 이 파일이 생긴 이유

I-4 는 계약을 쓰고·합산하고·검토하고·승인하고·봉인하는 길을 다 만들었는데,
승인 뒤 **실제로 데이터셋을 만드는 단계가 운영 코드에 없었다.** 승인 후 하는 일은
타입 어댑터 파일 쓰기 하나였다.

⚠️ 그 상태는 오류를 내지 않았다. 봉인은 「그때와 같은가」에 답할 뿐 「무언가
  생겼는가」에는 답하지 않는다. 그래서 계약 경로를 지난 릴리스가 **한 건도 없었고**
  (운영 `app_data.db` 에 결속 표조차 없다), 아무도 그것을 몰랐다.

## 이 파일이 막으려는 네 가지

★★★ ① **부분 물질화.** 다섯 중 셋만 만들어지면 앱은 둘을 「없는 것」으로 보고 화면에서
  지운다. 하나라도 못 만들면 아무것도 만들지 않는다.
★★★ ② **원천 해석의 임의성.** 후보가 둘일 때 하나를 고르면 그 선택은 조용하고,
  고른 쪽이 틀리면 남의 숫자를 보여 준다.
★★★ ③ **못 박지 않은 원천.** 매 요청 해석하면 앱이 보는 원천이 조용히 바뀐다.
★★★ ④ **시험만 아는 배선.** 여기서 초록이면 **사용자 경로도 초록**이어야 한다 —
  시험이 결속 표를 직접 UPDATE 하던 방식으로는 배선 누락을 잡지 못한다.
"""
from pathlib import Path

import pytest

from core import app_runtime_contract as arc
from core import contract_materializer as cm
from core.data_preparation import models as dpm
from core.data_preparation import snapshot_service as ss
from core.data_preparation import source_binding as sb
from core.data_preparation.store import DataPreparationStore

TENANT = "tenant_default"
SCOPE = "node_hq"
MODE = "REAL"

CSV = (
    "arrived_at,material_code,quantity\n"
    "2026-01-05,M1,10\n"
    "2026-01-06,M2,5\n"
).encode("utf-8")

ROWS = [{"arrived_at": "2026-01-05", "material_code": "M1", "quantity": "10"},
        {"arrived_at": "2026-01-06", "material_code": "M2", "quantity": "5"}]


@pytest.fixture
def dp(tmp_path):
    return DataPreparationStore(db_path=str(tmp_path / "dp.db"))


def _instance(dp, *, scope=SCOPE, tenant=TENANT, mode=MODE):
    return dp.create_instance(kit_id="k", version="1.0.0", kit_fingerprint="f",
                              tenant_id=tenant, scope_node_id=scope, entity_mode=mode)


def _serving(dp, key="purchase_orders", *, scope=SCOPE, tenant=TENANT, mode=MODE,
             activate=True, instance=None):
    """그 계약키를 실제로 제공하는 인스턴스 하나."""
    inst = instance or _instance(dp, scope=scope, tenant=tenant, mode=mode)
    b = dp.create_binding(instance_id=inst["instance_id"], dataset_contract_key=key,
                          provider=dpm.PROVIDER_FILE_SNAPSHOT,
                          config={"file_name": "a.csv", "column_map": {"a": "A"}},
                          tenant_id=tenant, scope_node_id=scope, entity_mode=mode)
    if activate:
        for step in ("validate", "approve", "activate"):
            getattr(sb, step)(dp, b["binding_id"])
    return inst, b


def _contract(datasets, *, status=arc.STATUS_APPROVED, revision=1):
    return {"schema_version": arc.SCHEMA_VERSION, "contract_id": "contract_aaaaaaaaaaaa",
            "revision": revision, "project_id": "P1", "task_id": "",
            "status": status, "datasets": datasets}


def _ds(name="arrivals", *, intent=arc.ENTERPRISE_READ, key="purchase_orders",
        role=arc.ENTERPRISE_ACTUAL, actions=("read",)):
    out = {"name": name, "allowed_actions": list(actions), "data_role": role,
           "source_intent": intent,
           "fields": [{"name": "quantity", "type": "number", "required": True,
                       "classification": "INTERNAL"}]}
    if key:
        out["enterprise_contract_key"] = key
    return out


# ── 승인 전에는 만들지 않는다 ────────────────────────────────────────────
@pytest.mark.parametrize("status", [arc.STATUS_DRAFT, arc.STATUS_COMPILED, "", "아무거나"])
def test_an_unapproved_contract_materializes_nothing(dp, status):
    """★★★ 승인 전 계약을 물질화하면 **검토를 지나지 않은 권한이 DB 에 들어간다.**

    ⚠️ 그리고 그 결속은 3단계에서 «정상» 으로 봉인된다."""
    _serving(dp)
    with pytest.raises(cm.MaterializeError) as e:
        cm.plan(_contract([_ds()], status=status), store=dp, tenant_id=TENANT,
                scope_node_id=SCOPE, entity_mode=MODE)
    assert "승인" in str(e.value)


def test_a_contract_without_datasets_is_refused(dp):
    """⚠️ 표가 없는 계약을 물질화하면 앱은 **빈 화면을 정상으로** 그린다."""
    with pytest.raises(cm.MaterializeError):
        cm.plan(_contract([]), store=dp, tenant_id=TENANT, scope_node_id=SCOPE,
                entity_mode=MODE)


# ── ② 원천 해석은 애매하면 멈춘다 ────────────────────────────────────────
def test_the_kit_instance_is_resolved_from_the_scope(dp):
    inst, _ = _serving(dp)
    got = cm.resolve_kit_instance(dp, contract_key="purchase_orders", tenant_id=TENANT,
                                  scope_node_id=SCOPE, entity_mode=MODE)
    assert got == inst["instance_id"]


def test_no_serving_instance_is_refused_not_left_for_later(dp):
    """★★★ 「나중에 생기겠지」로 넘기면 그 앱은 **만들어진 첫날부터** 읽을 수 없고,
    사용자는 자기가 무엇을 안 했는지 모른다."""
    with pytest.raises(cm.MaterializeError) as e:
        cm.resolve_kit_instance(dp, contract_key="purchase_orders", tenant_id=TENANT,
                                scope_node_id=SCOPE, entity_mode=MODE)
    assert "활성 원천이" in str(e.value)


def test_a_binding_that_is_not_active_does_not_count_as_serving(dp):
    """⚠️ 결속이 있다는 것과 그것이 **지금 데이터를 준다**는 것은 다르다."""
    _serving(dp, activate=False)
    with pytest.raises(cm.MaterializeError):
        cm.resolve_kit_instance(dp, contract_key="purchase_orders", tenant_id=TENANT,
                                scope_node_id=SCOPE, entity_mode=MODE)


def test_two_serving_instances_are_refused_instead_of_picking_one(dp):
    """★★★ 「첫 번째를 고른다」는 임의이고 **조용하다** — 고른 쪽이 틀리면 남의 숫자다."""
    _serving(dp)
    _serving(dp)
    with pytest.raises(cm.MaterializeError) as e:
        cm.resolve_kit_instance(dp, contract_key="purchase_orders", tenant_id=TENANT,
                                scope_node_id=SCOPE, entity_mode=MODE)
    assert "2개" in str(e.value)


@pytest.mark.parametrize("field,value", [
    ("scope", "node_다른곳"), ("tenant", "tenant_other"), ("mode", "VIRTUAL"),
])
def test_an_instance_in_another_scope_does_not_serve_this_app(dp, field, value):
    """★★★ 범위 세 필드를 **하나씩** 어긋내 본다.

    ⚠️ 셋을 한꺼번에만 시험하면 판정이 그중 하나만 봐도 통과한다(Wave E 실측)."""
    kw = {"scope": SCOPE, "tenant": TENANT, "mode": MODE}
    kw[field] = value
    _serving(dp, **kw)
    with pytest.raises(cm.MaterializeError):
        cm.resolve_kit_instance(dp, contract_key="purchase_orders", tenant_id=TENANT,
                                scope_node_id=SCOPE, entity_mode=MODE)


def test_a_different_contract_key_does_not_serve(dp):
    """⚠️ 「이 조직에 키트가 적용돼 있다」가 「이 표를 준다」는 뜻은 아니다."""
    _serving(dp, key="shipments")
    with pytest.raises(cm.MaterializeError):
        cm.resolve_kit_instance(dp, contract_key="purchase_orders", tenant_id=TENANT,
                                scope_node_id=SCOPE, entity_mode=MODE)


def test_a_store_failure_is_not_reported_as_an_absent_source(dp, monkeypatch):
    """★★★ 장애와 부재는 다른 사실이다.

    ⚠️ 부재로 접으면 운영자가 저장소를 고치러 가지 않는다."""
    def _boom(**kw):
        raise RuntimeError("디스크가 응답하지 않습니다")

    monkeypatch.setattr(dp, "list_instances", _boom, raising=False)
    with pytest.raises(cm.MaterializeError) as e:
        cm.resolve_kit_instance(dp, contract_key="purchase_orders", tenant_id=TENANT,
                                scope_node_id=SCOPE, entity_mode=MODE)
    assert "읽을 수 없습니다" in str(e.value)
    assert "활성 원천이" not in str(e.value), "장애가 «원천 없음» 으로 기록됐다"


# ── ① 전부 아니면 아무것도 ───────────────────────────────────────────────
def test_one_unresolvable_dataset_blocks_the_whole_contract(dp):
    """★★★ 다섯 중 셋만 만들어지면 앱은 둘을 「없는 것」으로 보고 화면에서 지운다."""
    _serving(dp, key="purchase_orders")
    with pytest.raises(cm.MaterializeError) as e:
        cm.plan(_contract([_ds("arrivals", key="purchase_orders"),
                           _ds("shipments", key="없는표")]),
                store=dp, tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=MODE)
    #: 두 번째만 문제인데 계획 전체가 멈춰야 한다
    assert "shipments" in str(e.value)


def test_every_problem_is_reported_at_once(dp):
    """⚠️ 한 건씩 고치게 하면 사용자가 같은 화면을 다섯 번 본다."""
    with pytest.raises(cm.MaterializeError) as e:
        cm.plan(_contract([_ds("a", key="없는표1"), _ds("b", key="없는표2")]),
                store=dp, tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=MODE)
    assert "a:" in str(e.value) and "b:" in str(e.value)


def test_a_native_dataset_needs_no_source_at_all(dp):
    """⚠️ 대조군 — 위 시험들이 「전부 막힘」으로도 통과하지 않게 한다."""
    out = cm.plan(_contract([_ds("memo", intent=arc.AFS_NATIVE, key="",
                                 role=arc.NATIVE_SUPPLEMENT,
                                 actions=("read", "create"))]),
                  store=dp, tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=MODE)
    assert len(out) == 1
    assert out[0].kit_instance_id == "", "우리 DB 인데 원천을 못 박았다"


def test_a_native_dataset_carrying_an_enterprise_key_is_refused(dp):
    """★★★ 둘 중 하나가 틀린 것이다.

    ⚠️ 조용히 무시하면 그 키는 «적혀 있으나 아무도 안 보는» 값이 되고, 다음 사람이
      그것을 근거로 읽는다."""
    with pytest.raises(cm.MaterializeError) as e:
        cm.plan(_contract([_ds("memo", intent=arc.AFS_NATIVE, key="purchase_orders",
                               role=arc.NATIVE_SUPPLEMENT, actions=("read", "create"))]),
                store=dp, tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=MODE)
    assert "틀렸습니다" in str(e.value)


@pytest.mark.parametrize("intent", [arc.EXTERNAL_REFERENCE, arc.DERIVED_READ])
def test_a_source_without_a_host_service_is_refused(dp, intent):
    with pytest.raises(cm.MaterializeError):
        cm.plan(_contract([_ds("x", intent=intent, key="")]),
                store=dp, tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=MODE)


# ── ③ 못 박는다 ─────────────────────────────────────────────────────────
def test_the_resolved_plan_pins_which_instance_serves_it(dp):
    """★★★ 매 요청 해석하면 앱이 보는 원천이 **조용히 바뀐다.**"""
    inst, _ = _serving(dp)
    out = cm.plan(_contract([_ds()]), store=dp, tenant_id=TENANT, scope_node_id=SCOPE,
                  entity_mode=MODE)
    assert out[0].kit_instance_id == inst["instance_id"]
    assert out[0].enterprise_contract_key == "purchase_orders"


# ── ④ 시험만 아는 배선이 없다 — 관통 ────────────────────────────────────
#
# ★★★ 여기서 초록이면 **사용자 경로도 초록**이어야 한다. 결속 표를 직접 UPDATE 하는
#   방식으로는 「계약이 그 값을 채우지 않는다」를 잡지 못한다 — 실제로 Wave E 는 그렇게
#   통과했고, 배선이 없다는 사실은 다음 세션에 가서야 드러났다.
import json                                                          # noqa: E402

from core.app_data import AppDataError, AppDataService                # noqa: E402
from core.app_data_store import AppDataStore                          # noqa: E402


@pytest.fixture
def app_data(tmp_path, monkeypatch):
    """격리된 앱 데이터 저장소. ⚠️ 격리하지 않으면 운영 DB 에 쓴다."""
    from core import library_paths

    lib = tmp_path / "library"
    (lib / "rel_1").mkdir(parents=True)
    (lib / "rel_1" / "release.json").write_text(json.dumps({
        "release_id": "rel_1", "project_id": "P1", "tenant_id": TENANT,
        "entity_mode": MODE, "enterprise_scope_id": SCOPE,
        "owner_dept_id": "hq", "visibility": "dept", "app_id": "app_1",
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(library_paths, "release_dir",
                        lambda rid: str(lib / str(rid)), raising=False)
    return AppDataService(AppDataStore(db_path=str(tmp_path / "app.db")))


def _materialize(dp, app_data, datasets):
    return cm.materialize(_contract(datasets), release_id="rel_1", actor_id="u@x",
                          store=dp, app_data=app_data, tenant_id=TENANT,
                          scope_node_id=SCOPE, entity_mode=MODE)


def test_materializing_writes_the_source_into_the_binding(dp, app_data):
    """★★★ 계약이 «어느 표에서 오는가» 를 말했으면 그것이 **결속 표에 적혀야** 한다.

    ⚠️ 이 값이 비면 Dispatch 는 갈 곳을 모르고, 그때 우리 DB 로 폴백하지 않으므로
      그 데이터셋은 만들어진 첫날부터 읽히지 않는다."""
    inst, _ = _serving(dp)
    out = _materialize(dp, app_data, [_ds()])

    assert len(out.datasets) == 1
    binding = app_data.binding_for("rel_1", out.datasets[0]["dataset_id"])
    assert binding["enterprise_contract_key"] == "purchase_orders"
    assert binding["kit_instance_id"] == inst["instance_id"]
    assert binding["source_intent"] == arc.ENTERPRISE_READ
    assert binding["contract_bound"] is True
    assert binding["allowed_actions"] == ("read",)


def test_a_native_dataset_leaves_the_source_columns_empty(dp, app_data):
    """⚠️ 대조군 — 위 시험이 「늘 채워진다」로도 통과하지 않게 한다."""
    out = _materialize(dp, app_data, [_ds("memo", intent=arc.AFS_NATIVE, key="",
                                          role=arc.NATIVE_SUPPLEMENT,
                                          actions=("read", "create"))])
    binding = app_data.binding_for("rel_1", out.datasets[0]["dataset_id"])
    assert binding["enterprise_contract_key"] == ""
    assert binding["kit_instance_id"] == ""


def test_the_provider_resolves_from_what_materialization_wrote(dp, app_data):
    """★★★ **관통** — 계약이 적은 값으로 Dispatch 가 실제 판을 찾아낸다.

    ⚠️ 이 시험이 없으면 「물질화는 적고 Dispatch 는 다른 데를 본다」가 조용히 성립한다."""
    from core import host_runtime_provider as prov

    inst, b = _serving(dp)
    #: 그 원천에 인증된 판을 하나 올린다
    snap = ss.ingest(dp, binding=dp.get_binding(b["binding_id"]), payload=CSV,
                     file_name="a.csv", workspace_root=str(app_data._store.db_path) + "_raw")
    done = ss.run_pipeline(dp, snap["snapshot_id"], ROWS,
                           ["arrived_at", "material_code", "quantity"],
                           control={"row_count": 2, "sums": {"quantity": 15}})
    assert done["state"] == dpm.DEMO_CERTIFIED, done

    out = _materialize(dp, app_data, [_ds()])
    binding = app_data.binding_for("rel_1", out.datasets[0]["dataset_id"])

    #: Dispatch 가 «결속 표가 말한 곳» 을 보고 판을 찾는다
    key = binding["enterprise_contract_key"]
    dp_binding = dp.active_binding(binding["kit_instance_id"], key)
    snapshots = [r for r in dp.list_snapshots(binding["kit_instance_id"])
                 if str(r.get("dataset_contract_key")) == key]
    res = prov.resolve(source_intent=binding["source_intent"], dataset_contract_key=key,
                       binding=dp_binding, snapshots=snapshots,
                       now="2026-08-18T00:00:00+00:00",
                       scope={"tenant_id": TENANT, "scope_node_id": SCOPE,
                              "entity_mode": MODE})
    assert res.provider == prov.FILE_SNAPSHOT
    assert res.snapshot and res.snapshot["snapshot_id"] == snap["snapshot_id"]
    assert res.stale is False


def test_a_half_resolvable_contract_leaves_no_dataset_behind(dp, app_data):
    """★★★ ① 부분 물질화 금지 — **실행 경로에서도** 확인한다.

    ⚠️ `plan()` 단위 시험만으로는 「계획은 막았는데 실행이 절반 썼다」를 못 잡는다."""
    _serving(dp, key="purchase_orders")
    with pytest.raises(cm.MaterializeError):
        _materialize(dp, app_data, [_ds("arrivals", key="purchase_orders"),
                                    _ds("shipments", key="없는표")])
    assert app_data.list_datasets("rel_1") == [], "실패했는데 데이터셋이 남았다"


def test_a_write_action_on_an_enterprise_source_is_refused_at_the_db(dp, app_data):
    """★★★ 계약이 막아도 **DB 가 다시 막는다** — 물질화는 계약을 지나지 않고도 일어난다."""
    _serving(dp)
    with pytest.raises(AppDataError) as e:
        _materialize(dp, app_data, [_ds(actions=("read", "create"))])
    assert "입력 화면" in str(e.value)


def test_rerunning_materialization_adopts_instead_of_duplicating(dp, app_data):
    """★★★ 앱을 개정해도 현업이 쌓은 레코드가 **승계돼야** 한다.

    ⚠️ 새로 만들면 같은 이름의 데이터셋이 둘이 되고, 그때 「이 데이터는 어디 있나」에
      답이 두 개가 된다."""
    _serving(dp)
    first = _materialize(dp, app_data, [_ds()])
    again = _materialize(dp, app_data, [_ds()])
    assert first.datasets[0]["dataset_id"] == again.datasets[0]["dataset_id"]
    assert len(app_data.list_datasets("rel_1")) == 1


# ── 게시 경로가 실제로 물질화기를 부르는가 ──────────────────────────────
#
# ★★★ 이 절이 없으면 **아무도 부르지 않는 물질화기**가 남는다 — 단위 시험은 전부
#   초록인데 사용자 경로에서는 아무 일도 일어나지 않는 상태. 그것이 바로 이 Wave 가
#   고치러 온 결함이다(승인은 되는데 아무것도 생기지 않았다).
import api.routes.factory_control as fc                              # noqa: E402


def test_the_release_path_calls_the_materializer():
    """★★★ 게시 라우트가 물질화 헬퍼를 **부른다.**

    ⚠️ 헬퍼가 있다는 것과 그것이 불린다는 것은 다르다."""
    import inspect

    src = inspect.getsource(fc.create_release)
    assert "_materialize_contract_for_release" in src, "게시가 물질화를 부르지 않는다"
    assert "contract_materialization" in src, "결과를 릴리스에 남기지 않는다"


def test_a_legacy_release_is_not_materialized(tmp_path, monkeypatch):
    """★★★ **소급하지 않는다.** 계약 이전 판의 결속을 다시 쓰면 이미 도는 앱이 바뀐다."""
    out = fc._materialize_contract_for_release(
        "P1", "rel_1", actor_id="u@x", profile="",
        ctx={"tenant_id": TENANT, "scope_node_id": SCOPE, "entity_mode": MODE})
    assert out["state"] == "SKIPPED_LEGACY"
    assert out["datasets"] == []


def test_a_contract_profile_release_without_a_contract_file_is_reported_not_skipped(
        tmp_path, monkeypatch):
    """★★★ 「프로필은 켜졌는데 계약 파일이 없다」는 정상이 아니다.

    ⚠️ 조용히 건너뛰면 그 앱은 데이터 없이 게시되고, 화면은 빈 표를 정상으로 그린다."""
    monkeypatch.setattr(fc, "workspace_path", lambda *a: str(tmp_path / "없는곳"),
                        raising=False)
    out = fc._materialize_contract_for_release(
        "P1", "rel_1", actor_id="u@x", profile="v1",
        ctx={"tenant_id": TENANT, "scope_node_id": SCOPE, "entity_mode": MODE})
    assert out["state"] == "FAILED"
    assert out["state"] != "SKIPPED_LEGACY"


def test_a_materialization_failure_is_recorded_not_swallowed(tmp_path, monkeypatch):
    """★★★ 실패를 삼키지 않는다 — **조용한 성공이 가장 나쁘다.**

    ⚠️ 다만 게시 자체를 막지도 않는다. 산출물은 이미 만들어져 있고, 못 꺼내게 하는
      것이 더 큰 손해다."""
    import json as _json

    ws = tmp_path / "ws"
    (ws / "05_app_contract").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(fc, "workspace_path", lambda *a: str(ws), raising=False)
    from nodes.contract import contract_path

    canon = Path(contract_path(str(ws)))
    canon.parent.mkdir(parents=True, exist_ok=True)
    #: 제공하는 원천이 없는 계약 — 물질화는 실패해야 한다
    canon.write_text(_json.dumps(_contract([_ds()]), ensure_ascii=False),
                     encoding="utf-8")

    out = fc._materialize_contract_for_release(
        "P1", "rel_1", actor_id="u@x", profile="v1",
        ctx={"tenant_id": TENANT, "scope_node_id": SCOPE, "entity_mode": MODE})
    assert out["state"] == "FAILED"
    assert out["detail"], "무엇이 안 됐는지가 비어 있다"
    assert "활성 원천이" in out["detail"]
