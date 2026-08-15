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
    assert cov["bound"] == 1 and cov["legacy"] == 1 and cov["materialized"] == 2


def test_coverage_denominator_is_the_declaration(svc):
    """★★★ 결속 행만 세면 **계약이 열 개를 선언했는데 하나만 물질화된 상태**가
    「1/1 = 100%」로 보인다 — 가장 위험한 거짓 초록이다."""
    svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x", allowed_actions=["read"])
    cov = svc.contract_coverage("rel_1", declared=["orders", "arrivals", "invoices"])
    assert cov["declared"] == 3
    assert cov["materialized"] == 1
    assert cov["missing"] == ["arrivals", "invoices"]     # 선언됐는데 없는 것
    assert cov["undeclared"] == []


def test_coverage_reports_bindings_outside_the_contract(svc):
    """계약에 없는데 결속돼 있는 것도 드러낸다 — §4 의 「계약 밖 데이터셋」 이 그것이다."""
    svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x", allowed_actions=["read"])
    svc.create_dataset("rel_1", "shadow", _schema(), actor_id="u@x")
    cov = svc.contract_coverage("rel_1", declared=["orders"])
    assert cov["undeclared"] == ["shadow"]


def test_unknown_declaration_is_not_reported_as_zero(svc):
    """⚠️ 모르는 값을 0 으로 적지 않는다. 「선언이 없다」와 「선언을 모른다」는 다르다."""
    svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x", allowed_actions=["read"])
    cov = svc.contract_coverage("rel_1")
    assert cov["declared"] is None and cov["missing"] is None


def test_list_datasets_follows_bindings(svc):
    ds = svc.create_dataset("rel_v1", "orders", _schema(), actor_id="u@x",
                            app_id="app_o", dataset_key="ds_o", allowed_actions=["read"])
    assert [d["dataset_id"] for d in svc.list_datasets("rel_v2")] == []
    svc.adopt_dataset("app_o", "ds_o", "rel_v2", allowed_actions=["read"])
    assert [d["dataset_id"] for d in svc.list_datasets("rel_v2")] == [ds["dataset_id"]]


# ── [2.1 보정] 결속된 스키마 판이 실제로 쓰인다 ───────────────────────────
def _schema_v2():
    return {"fields": [{"name": "qty", "type": "number"},
                       {"name": "memo", "type": "string"}]}


def test_two_releases_validate_with_their_own_schema(svc):
    """★★★ **2.1 보정의 이유 전부.**

    ⚠️ 종전에는 `version_id` 를 저장만 하고 검증은 데이터셋 마스터의 단일 `schema_json`
      으로 했다. 그래서 v1·v2 가 서로 다른 판을 가리켜도 **둘 다 마지막에 저장된 스키마
      하나**를 썼다 — 판을 기록만 하고 쓰지 않는 상태이고, 그것은 판이 없는 것과 같다."""
    ds = svc.create_dataset("rel_v1", "orders", _schema(), actor_id="u@x",
                            app_id="app_o", dataset_key="ds_o", allowed_actions=["read", "create"],
                            contract_revision=1)
    svc.adopt_dataset("app_o", "ds_o", "rel_v2", allowed_actions=["read", "create"],
                      schema=_schema_v2(), contract_revision=2)

    #: v2 에만 있는 필드 — v2 로는 되고 v1 로는 거부된다.
    ok = svc.create_record(ds["dataset_id"], {"qty": 1, "memo": "메모"},
                           actor_id="u@x", release_id="rel_v2")
    assert ok["payload"]["memo"] == "메모"
    with pytest.raises(AppDataError) as e:
        svc.create_record(ds["dataset_id"], {"qty": 1, "memo": "메모"},
                          actor_id="u@x", release_id="rel_v1")
    assert "memo" in str(e.value)

    #: 두 릴리스의 스키마 조회 결과가 실제로 다르다.
    v1 = svc.find_dataset("rel_v1", "orders")
    v2 = svc.find_dataset("rel_v2", "orders")
    assert {f["name"] for f in v1["schema"]["fields"]} == {"qty"}
    assert {f["name"] for f in v2["schema"]["fields"]} == {"qty", "memo"}
    assert v1["contract_revision"] == 1 and v2["contract_revision"] == 2
    assert v1["schema_fingerprint"] != v2["schema_fingerprint"]


def test_update_record_also_uses_the_bound_schema(svc):
    ds = svc.create_dataset("rel_v1", "orders", _schema(), actor_id="u@x",
                            app_id="app_o", dataset_key="ds_o", allowed_actions=["read", "create"],
                            contract_revision=1)
    svc.adopt_dataset("app_o", "ds_o", "rel_v2", allowed_actions=["read", "create"],
                      schema=_schema_v2(), contract_revision=2)
    rec = svc.create_record(ds["dataset_id"], {"qty": 1}, actor_id="u@x", release_id="rel_v1")
    with pytest.raises(AppDataError):
        svc.update_record(rec["record_id"], {"memo": "x"}, actor_id="u@x", release_id="rel_v1")
    out = svc.update_record(rec["record_id"], {"memo": "x"}, actor_id="u@x", release_id="rel_v2")
    assert out["payload"]["memo"] == "x"


def test_console_cannot_edit_a_contracted_schema(svc):
    """⚠️ 관리 API 의 전역 스키마 변경과 릴리스별 계약 판은 **다른 경로**다.
    섞으면 승인된 revision 의 내용이 콘솔에서 바뀌고, 승인 원장은 그것을 모른다."""
    bound = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                               allowed_actions=["read"], contract_revision=1)
    with pytest.raises(AppDataError) as e:
        svc.update_schema(bound["dataset_id"], _schema_v2(), actor_id="u@x")
    assert "계약" in str(e.value)

    #: 레거시(계약 이전) 데이터셋은 종전대로 콘솔에서 바꿀 수 있다 — 대조군.
    legacy = svc.create_dataset("rel_1", "notes", _schema(), actor_id="u@x")
    out = svc.update_schema(legacy["dataset_id"], _schema_v2(), actor_id="u@x")
    assert out["added_fields"] == ["memo"]


# ── [2.1 보정] 계약 판은 불변이다 ─────────────────────────────────────────
def test_same_revision_with_a_different_schema_is_refused(svc):
    """★★★ 덮어쓰게 두면 **이미 승인된 revision 의 의미가 나중에 바뀐다** —
    승인 원장은 「revision 1 을 승인했다」고 하는데 그 내용이 달라져 있고,
    3단계에서 봉인할 계약 지문의 역사도 함께 변조된다."""
    ds = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                            allowed_actions=["read"], contract_revision=1)
    with pytest.raises(AppDataError) as e:
        svc.bind_release("rel_2", ds["dataset_id"], allowed_actions=["read"],
                         schema=_schema_v2(), contract_revision=1)
    assert "revision" in str(e.value) and "새 revision" in str(e.value)


def test_same_revision_with_the_same_schema_is_idempotent(svc):
    ds = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                            allowed_actions=["read"], contract_revision=1)
    first = svc.binding_for("rel_1", ds["dataset_id"])["version_id"]
    #: 같은 내용을 다시 결속해도 판이 늘지 않는다 — 재실행이 가능해야 한다.
    again = svc.bind_release("rel_3", ds["dataset_id"], allowed_actions=["read"],
                             schema=_schema(), contract_revision=1)
    assert again["version_id"] == first
    n = svc._store.scalar("SELECT COUNT(*) FROM app_dataset_versions WHERE dataset_id=?",
                          (ds["dataset_id"],))
    assert n == 1


def test_a_new_revision_is_the_way_to_change_a_schema(svc):
    ds = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                            allowed_actions=["read"], contract_revision=1)
    svc.bind_release("rel_2", ds["dataset_id"], allowed_actions=["read"],
                     schema=_schema_v2(), contract_revision=2)
    revs = [r["contract_revision"] for r in svc._store.query(
        "SELECT contract_revision FROM app_dataset_versions WHERE dataset_id=? "
        "ORDER BY contract_revision", (ds["dataset_id"],))]
    assert revs == [1, 2]


def test_schema_fingerprint_covers_the_stored_artifact_exactly(svc):
    """★ 이 지문은 «의미» 지문이 아니라 **판 지문**이다 — 「저장된 판이 승인된 그것과
    같은가」에 답한다. 그래서 **필드 순서까지** 들어간다.

    ⚠️ 순서를 빼면 「승인된 판과 저장된 판이 다른데 지문은 같은」 구간이 생기고, 그 구간이
      바로 불변성이 지켜지지 않는 곳이다. 화면 순서를 바꾸려면 새 revision 을 낸다.
    (요구가 바뀐 것인지 판단하는 «의미» 지문은 `app_runtime_contract.semantic_fingerprint`
     이고 그쪽은 설명 문구를 뺀다 — 두 지문은 서로 다른 질문에 답한다.)"""
    from core.app_data import schema_fingerprint
    a = {"fields": [{"name": "qty", "type": "number"}, {"name": "memo", "type": "string"}]}
    b = {"fields": [{"name": "memo", "type": "string"}, {"name": "qty", "type": "number"}]}
    assert schema_fingerprint(a) != schema_fingerprint(b)
    assert schema_fingerprint(a) == schema_fingerprint(dict(a))   # 같은 내용은 같은 지문
    assert schema_fingerprint(a) != schema_fingerprint(_schema())


def test_reordering_fields_needs_a_new_revision(svc):
    ds = svc.create_dataset("rel_1", "orders", _schema_v2(), actor_id="u@x",
                            allowed_actions=["read"], contract_revision=1)
    flipped = {"fields": list(reversed(_schema_v2()["fields"]))}
    with pytest.raises(AppDataError):
        svc.bind_release("rel_2", ds["dataset_id"], allowed_actions=["read"],
                         schema=flipped, contract_revision=1)
    svc.bind_release("rel_2", ds["dataset_id"], allowed_actions=["read"],
                     schema=flipped, contract_revision=2)   # 새 판이면 된다
    assert svc.find_dataset("rel_2", "orders")["contract_revision"] == 2


# ── [2.1 보정] 유일성은 DB 가 지킨다 ──────────────────────────────────────
def test_duplicate_dataset_key_in_one_app_is_blocked_by_the_db(svc):
    """⚠️ 응용 계층의 「조회 후 INSERT」 는 워커가 둘이면 깨진다 — DB 가 막아야 한다."""
    import sqlite3
    svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                       app_id="app_o", dataset_key="ds_o")
    assert svc._store.integrity_problems() == []
    with pytest.raises(sqlite3.IntegrityError):
        svc._store.execute(
            "INSERT INTO app_datasets (dataset_id, tenant_id, release_id, name, app_id, "
            "dataset_key, created_by, created_at, updated_at, retired_at) "
            "VALUES ('ds_dup','tenant_default','rel_9','orders2','app_o','ds_o','u','','','')")


def test_legacy_empty_app_id_does_not_collide(svc):
    """★ 레거시(`app_id=''`)는 유일성 대상에서 뺀다 —
    ⚠️ 넣으면 앱 식별자가 없는 옛 데이터셋들이 서로 충돌해 마이그레이션이 통째로 멈춘다."""
    a = svc.create_dataset("rel_a", "orders", _schema(), actor_id="u@x")
    b = svc.create_dataset("rel_b", "orders", _schema(), actor_id="u@x")
    assert a["app_id"] == b["app_id"] == "" and a["dataset_key"] == b["dataset_key"] == "orders"
    assert svc._store.integrity_problems() == []
    #: 그리고 그 둘은 자동으로 합쳐지지 않는다.
    assert svc.adopt_dataset("", "orders", "rel_c") is None


def test_two_datasets_cannot_share_a_runtime_name_in_one_release(svc):
    """앱은 이름으로만 부른다 — 한 릴리스에 같은 이름이 둘이면 답할 수 없다."""
    other = svc.create_dataset("rel_x", "orders", _schema(), actor_id="u@x",
                               app_id="app_x", dataset_key="ds_x")
    svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                       app_id="app_o", dataset_key="ds_o")
    with pytest.raises(AppDataError) as e:
        svc.bind_release("rel_1", other["dataset_id"], runtime_name="orders")
    assert "orders" in str(e.value)


def test_ambiguous_adoption_refuses_instead_of_picking_one(svc, monkeypatch):
    """★★★ **첫 행을 고르지 않는다.** 그 선택은 임의이고 조용하며,
    고른 쪽이 틀렸다면 현업 레코드가 통째로 다른 데이터셋에 붙는다."""
    svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                       app_id="app_o", dataset_key="ds_o")
    #: 유일성 인덱스를 우회해 중복을 심는다(과거 데이터에 이미 중복이 있는 상황을 흉내).
    svc._store.execute("DROP INDEX IF EXISTS idx_app_datasets_app_key")
    svc._store.execute(
        "INSERT INTO app_datasets (dataset_id, tenant_id, release_id, name, app_id, "
        "dataset_key, created_by, created_at, updated_at, retired_at) "
        "VALUES ('ds_dup','tenant_default','rel_2','orders','app_o','ds_o','u','','','')")
    with pytest.raises(AppDataError) as e:
        svc.adopt_dataset("app_o", "ds_o", "rel_3")
    assert "고를 수 없습니다" in str(e.value)


# ── [2.1 보정] 생성·판·결속은 하나의 트랜잭션 ────────────────────────────
def test_a_failed_binding_rolls_back_the_dataset(svc, monkeypatch):
    """⚠️ 나뉘어 있으면 **고아 데이터셋**이 남는다 — 아무 릴리스도 가리키지 않으므로
    이름으로 찾히지 않고, 다음 요청이 **또 만든다.**"""
    import core.app_data as ad
    real = ad.AppDataService._bind_in_tx

    def _boom(self, conn, *a, **kw):
        raise RuntimeError("결속 실패")

    monkeypatch.setattr(ad.AppDataService, "_bind_in_tx", _boom)
    with pytest.raises(RuntimeError):
        svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                           allowed_actions=["read"])
    monkeypatch.setattr(ad.AppDataService, "_bind_in_tx", real)

    assert svc._store.scalar("SELECT COUNT(*) FROM app_datasets") == 0
    assert svc._store.scalar("SELECT COUNT(*) FROM app_release_dataset_bindings") == 0
    assert svc._store.scalar("SELECT COUNT(*) FROM app_dataset_versions") == 0
    #: 그리고 같은 이름으로 다시 만들 수 있다(고아가 막고 있지 않다).
    assert svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x")["name"] == "orders"


def test_a_failed_version_rolls_back_the_binding(svc):
    """revision 충돌로 결속이 실패하면 **그 결속도 남지 않는다.**"""
    ds = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                            allowed_actions=["read"], contract_revision=1)
    before = svc._store.scalar("SELECT COUNT(*) FROM app_release_dataset_bindings")
    with pytest.raises(AppDataError):
        svc.bind_release("rel_2", ds["dataset_id"], allowed_actions=["read"],
                         schema=_schema_v2(), contract_revision=1)   # 같은 revision, 다른 스키마
    assert svc._store.scalar("SELECT COUNT(*) FROM app_release_dataset_bindings") == before
    assert svc.binding_for("rel_2", ds["dataset_id"]) is None


# ── [2.1 보정] 물질화 지문 ────────────────────────────────────────────────
def test_materialization_fingerprint_moves_when_bindings_move(svc):
    """★★★ 계약 원문 지문과 **다른 사실**이다 — 계약서가 승인된 것과 DB 가 그대로
    물질화된 것은 별개다. 원문만 봉인하면 「계약서는 승인됐지만 결속이 다른 상태」를
    잡을 수 없다."""
    ds = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                            allowed_actions=["read", "create"], contract_revision=1)
    base = svc.materialization_fingerprint("rel_1")
    assert len(base) == 16

    svc.bind_release("rel_1", ds["dataset_id"], allowed_actions=["read"])   # 권한 축소
    narrowed = svc.materialization_fingerprint("rel_1")
    assert narrowed != base

    svc.bind_release("rel_1", ds["dataset_id"], allowed_actions=["read"],
                     schema=_schema_v2(), contract_revision=2)              # 판 교체
    reschemed = svc.materialization_fingerprint("rel_1")
    assert reschemed != narrowed

    svc.create_dataset("rel_1", "extra", _schema(), actor_id="u@x", allowed_actions=["read"])
    assert svc.materialization_fingerprint("rel_1") != reschemed


def test_materialization_fingerprint_is_stable_and_per_release(svc):
    svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x", allowed_actions=["read"])
    a = svc.materialization_fingerprint("rel_1")
    assert a == svc.materialization_fingerprint("rel_1")     # 부작용 없음
    assert a != svc.materialization_fingerprint("rel_2")     # 릴리스마다 다르다


def test_materialization_fingerprint_ignores_creation_order(svc, monkeypatch, tmp_path):
    """⚠️ 행 순서에 흔들리면 **같은 상태가 다른 지문**을 갖는다 — 그러면
    「물질화가 바뀌었다」는 판정이 거짓 경보를 내고, 곧 아무도 그것을 믿지 않는다."""
    svc.create_dataset("rel_1", "aaa", _schema(), actor_id="u@x", allowed_actions=["read"])
    svc.create_dataset("rel_1", "zzz", _schema(), actor_id="u@x", allowed_actions=["create"])
    forward = svc.materialization_fingerprint("rel_1")

    #: 같은 상태를 **반대 순서로** 만든 다른 DB.
    monkeypatch.setattr(svc._store, "db_path", str(tmp_path / "other.db"), raising=False)
    monkeypatch.setattr(svc._store, "_ready", "", raising=False)
    svc.create_dataset("rel_1", "zzz", _schema(), actor_id="u@x", allowed_actions=["create"])
    svc.create_dataset("rel_1", "aaa", _schema(), actor_id="u@x", allowed_actions=["read"])
    assert svc.materialization_fingerprint("rel_1") == forward


# ── [2.1 보정] 유일성 실패를 드러낸다 ─────────────────────────────────────
def test_preexisting_duplicates_are_reported_not_swallowed(monkeypatch, tmp_path):
    """★ 인덱스가 **없는 채로 도는 것**과 **없다는 사실을 모르는 채 도는 것**은 다르다.

    ⚠️ 후자에서는 중복이 계속 생겨도 아무도 모르고, `adopt_dataset` 이 「둘 중 하나」를
      임의로 고르는 상태가 굳어진다."""
    import sqlite3
    db = tmp_path / "dup.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE app_datasets (
            dataset_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL DEFAULT 'tenant_default',
            release_id TEXT NOT NULL, name TEXT NOT NULL, label TEXT NOT NULL DEFAULT '',
            schema_json TEXT NOT NULL DEFAULT '{}', app_class TEXT NOT NULL DEFAULT '',
            owner_dept_id TEXT NOT NULL DEFAULT '', scope_node_id TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '', retired_at TEXT NOT NULL DEFAULT '',
            app_id TEXT NOT NULL DEFAULT '', dataset_key TEXT NOT NULL DEFAULT '');
        CREATE TABLE app_records (
            record_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}', created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT '', updated_by TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '', deleted_by TEXT NOT NULL DEFAULT '',
            deleted_at TEXT NOT NULL DEFAULT '');
        INSERT INTO app_datasets (dataset_id, release_id, name, app_id, dataset_key)
             VALUES ('ds_1', 'rel_a', 'orders', 'app_o', 'ds_o'),
                    ('ds_2', 'rel_b', 'orders', 'app_o', 'ds_o');
    """)
    conn.commit()
    conn.close()

    monkeypatch.setattr(app_data_service._store, "db_path", str(db), raising=False)
    monkeypatch.setattr(app_data_service._store, "_ready", "", raising=False)
    problems = app_data_service._store.integrity_problems()
    assert problems, "중복이 있는데 유일성 실패가 보고되지 않았다"
    assert any("idx_app_datasets_app_key" in p for p in problems), problems
    #: 그리고 그 상태에서 승계는 **거부**된다 — 임의로 하나를 고르지 않는다.
    with pytest.raises(AppDataError):
        app_data_service.adopt_dataset("app_o", "ds_o", "rel_c")


def test_duplicate_runtime_name_in_a_release_is_blocked_by_the_db(svc):
    """응용 계층의 `clash` 검사를 **우회해도** DB 가 막는다 —
    ⚠️ 워커가 둘이면 「없다」를 동시에 보고 둘 다 INSERT 한다."""
    import sqlite3
    a = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                           app_id="app_a", dataset_key="ds_a")
    b = svc.create_dataset("rel_2", "orders", _schema(), actor_id="u@x",
                           app_id="app_b", dataset_key="ds_b")
    assert svc._store.integrity_problems() == []
    with pytest.raises(sqlite3.IntegrityError):
        svc._store.execute(
            "INSERT INTO app_release_dataset_bindings (binding_id, release_id, dataset_id, "
            "version_id, runtime_name, allowed_actions, contract_bound, created_at) "
            "VALUES ('bind_dup','rel_1',?,'','orders','',0,'')", (b["dataset_id"],))
    assert a["dataset_id"] != b["dataset_id"]


def test_the_binding_name_is_what_the_app_calls(svc):
    """★ 런타임 이름은 **결속에 봉인**된다 — 데이터셋 마스터의 `name` 이 아니다.

    ⚠️ 마스터를 따라가게 두면, 이름을 고치는 경로가 하나라도 생기는 날 **이미 결속된
      릴리스의 호출 이름이 함께 바뀐다.** 그 앱은 어제까지 되던 호출이 오늘 404 가 된다."""
    ds = svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                            app_id="app_o", dataset_key="ds_o", allowed_actions=["read"])
    svc.bind_release("rel_2", ds["dataset_id"], allowed_actions=["read"],
                     runtime_name="purchase_orders")
    assert svc.find_dataset("rel_2", "purchase_orders")["dataset_id"] == ds["dataset_id"]
    #: 마스터 이름으로는 그 릴리스에서 찾히지 않는다 — 결속이 정본이다.
    assert svc.find_dataset("rel_2", "orders") is None
    assert svc.find_dataset("rel_1", "orders")["dataset_id"] == ds["dataset_id"]


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


def test_legacy_identity_report_separates_the_five_cases(svc):
    """★★★ 「앱을 개정해도 데이터가 유지된다」는 **신규 계약 데이터셋에만** 참이다.

    ⚠️⚠️ 이름이 같다는 이유로 자동 연결하지 않는다 — 서로 다른 앱이 `orders` 를 쓰는 것은
      흔하고, 잘못 이으면 **남의 앱 레코드가 이 앱에 보인다.** 보고만 하고 고치지 않는다."""
    #: ① 앱 식별자가 있는 것 — 이미 승계 가능
    svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                       app_id="app_o", dataset_key="ds_o", allowed_actions=["read"])
    #: ② 레거시인데 이름이 유일 — 앱을 특정할 수 있다
    svc.create_dataset("rel_2", "invoices", _schema(), actor_id="u@x")
    #: ③ 레거시이고 같은 이름이 여럿 — 후보가 여럿이라 모호하다
    svc.create_dataset("rel_3", "notes", _schema(), actor_id="u@x")
    svc.create_dataset("rel_4", "notes", _schema(), actor_id="u@x")
    #: ④ 결속이 없는 고아
    svc._store.execute(
        "INSERT INTO app_datasets (dataset_id, tenant_id, release_id, name, dataset_key, "
        "created_by, created_at, updated_at, retired_at) "
        "VALUES ('ds_orphan','tenant_default','','stray','stray','u','','','')")

    rep = svc.legacy_identity_report()
    names = {k: {i["name"] for i in v["items"]} for k, v in rep.items()}
    assert names["succeeded"] == {"orders"}
    assert names["recoverable"] == {"invoices"}
    assert names["ambiguous"] == {"notes"}
    assert names["unbindable"] == {"stray"}
    assert rep["ambiguous"]["count"] == 2
    assert rep["quarantined"]["count"] == 0
    #: 보고가 무엇도 고치지 않았다.
    assert svc.find_dataset("rel_3", "notes")["dataset_id"] != \
        svc.find_dataset("rel_4", "notes")["dataset_id"]


def test_legacy_report_quarantines_duplicate_keys(svc):
    svc.create_dataset("rel_1", "orders", _schema(), actor_id="u@x",
                       app_id="app_o", dataset_key="ds_o")
    svc._store.execute("DROP INDEX IF EXISTS idx_app_datasets_app_key")
    svc._store.execute(
        "INSERT INTO app_datasets (dataset_id, tenant_id, release_id, name, app_id, "
        "dataset_key, created_by, created_at, updated_at, retired_at) "
        "VALUES ('ds_dup','tenant_default','rel_2','orders','app_o','ds_o','u','','','')")
    rep = svc.legacy_identity_report()
    assert rep["quarantined"]["count"] == 2 and rep["succeeded"]["count"] == 0


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
    #: 같은 앱의 두 판 — 서로 다른 스키마를 결속한다.
    _mk("rel_v1", caps=["orders.read", "orders.create", "orders.update"])
    _mk("rel_v2", caps=["orders.read", "orders.create", "orders.update"])

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


def test_runtime_writes_use_the_bound_schema_not_the_master(client):
    """★★★ **2.1 보정 ①의 종단 회귀.**

    ⚠️ 서비스 계층만 시험하면 「라우트가 릴리스를 안 넘긴다」를 못 잡는다. 그 상태에서는
      v1 과 v2 가 서로 다른 판을 가리켜도 **둘 다 마지막에 저장된 스키마 하나**로 검증된다.
      실제 배선을 타지 않은 초록은 거짓이다."""
    ds = app_data_service.create_dataset(
        "rel_v1", "orders", _schema(), actor_id="u@x", app_id="app_o", dataset_key="ds_o",
        allowed_actions=["read", "create", "update"], contract_revision=1)
    app_data_service.adopt_dataset(
        "app_o", "ds_o", "rel_v2", allowed_actions=["read", "create", "update"],
        schema={"fields": [{"name": "qty", "type": "number"},
                           {"name": "memo", "type": "string"}]}, contract_revision=2)

    h1, h2 = _h(client, "rel_v1"), _h(client, "rel_v2")
    body = {"payload": {"qty": 1, "memo": "메모"}}
    #: v2 는 `memo` 를 안다.
    r2 = client.post(f"{R}/datasets/orders/records", headers=h2, json=body)
    assert r2.status_code == 200, r2.text
    #: v1 은 모른다 — 같은 데이터셋인데 판이 다르다.
    assert client.post(f"{R}/datasets/orders/records", headers=h1, json=body).status_code == 400

    #: 수정도 같은 규칙이다.
    rid = r2.json()["data"]["record_id"]
    assert client.put(f"{R}/datasets/orders/records/{rid}", headers=h1,
                      json={"payload": {"memo": "바꿈"}}).status_code == 400
    assert client.put(f"{R}/datasets/orders/records/{rid}", headers=h2,
                      json={"payload": {"memo": "바꿈"}}).status_code == 200

    #: 스키마 조회도 판을 따라간다.
    f1 = client.get(f"{R}/datasets/orders/schema", headers=h1).json()["data"]
    f2 = client.get(f"{R}/datasets/orders/schema", headers=h2).json()["data"]
    assert {f["name"] for f in f1["schema"]["fields"]} == {"qty"}
    assert {f["name"] for f in f2["schema"]["fields"]} == {"qty", "memo"}
    #: ★ 그리고 레코드는 하나의 데이터셋에 쌓인다 — 판이 갈려도 데이터는 승계된다.
    assert app_data_service.count_records(ds["dataset_id"]) == 1


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
