"""★★★ [BDR-204] Source Binding — 후보는 여럿, **활성은 하나**.

이 시험이 전제하는 것: **저장소는 `tmp_path` 로 격리한다.** 조직 경계는 API 절에서
`enforced_org` 로 본다.

## 이 파일이 지키는 것 하나

★★★ 한 (Kit Instance, Dataset Contract) 당 ACTIVE 는 하나뿐이다.

⚠️⚠️ 둘이 되는 순간 「이 데이터셋은 어디서 오는가」에 답이 두 개가 되고, 그 상태는
  **오류를 내지 않는다** — 조회하는 쪽이 아무거나 하나를 집을 뿐이다. 그래서 코드
  판정과 **DB 부분 유일 인덱스** 두 겹으로 막는다. 코드만 있으면 경쟁 상태에서
  뚫리고, DB 만 있으면 사용자가 이유를 모른다.
"""
import sqlite3
import threading

import pytest

from core.data_preparation import models as m
from core.data_preparation import source_binding as sb
from core.data_preparation.store import DataPreparationStore

FILE_CFG = {"file_name": "arrivals.csv", "column_map": {"arrived_at": "A", "qty": "B"}}


@pytest.fixture
def store(tmp_path):
    return DataPreparationStore(db_path=str(tmp_path / "dp.db"))


@pytest.fixture
def instance(store):
    return store.create_instance(kit_id="k1", version="1.0.0", kit_fingerprint="f",
                                 tenant_id="t1", scope_node_id="n1", entity_mode="REAL")


def _binding(store, instance, key="arrivals", provider=m.PROVIDER_FILE_SNAPSHOT,
             config=None):
    return store.create_binding(
        instance_id=instance["instance_id"], dataset_contract_key=key,
        provider=provider, config=FILE_CFG if config is None else config,
        tenant_id="t1", scope_node_id="n1", entity_mode="REAL")


def _to_active(store, row):
    row = sb.validate(store, row["binding_id"])
    row = sb.approve(store, row["binding_id"])
    return sb.activate(store, row["binding_id"])


# ── 상태 전이표 ──────────────────────────────────────────────────────────
def test_the_transition_table_is_pinned_literally():
    """★★★ 표를 **글자 그대로** 고정한다 — 표를 넓혀도 초록으로 남는 시험은 동어반복이다."""
    assert m.BINDING_TRANSITIONS == {
        "DRAFT": ("VALIDATED", "BLOCKED"),
        "VALIDATED": ("APPROVED", "BLOCKED", "DRAFT"),
        "APPROVED": ("ACTIVE", "BLOCKED", "DRAFT"),
        "ACTIVE": ("RETIRED",),
        "BLOCKED": ("DRAFT",),
        "RETIRED": (),
    }


@pytest.mark.parametrize("cur,tgt", [
    ("DRAFT", "APPROVED"), ("DRAFT", "ACTIVE"), ("VALIDATED", "ACTIVE"),
    ("ACTIVE", "APPROVED"), ("RETIRED", "ACTIVE"), ("RETIRED", "DRAFT"),
    ("모르는상태", "ACTIVE"), ("DRAFT", "모르는상태"),
])
def test_forbidden_transitions_say_where_you_can_go(cur, tgt):
    """⚠️ 막기만 하고 갈 곳을 안 알려 주면 사용자는 아무 버튼이나 누른다."""
    with pytest.raises(m.StateConflict) as e:
        m.assert_transition(cur, tgt)
    assert "가능한 다음 상태" in str(e.value) or "알 수 없는" in str(e.value)


def test_a_blocked_candidate_can_be_fixed_and_resubmitted():
    """★ 돌아갈 길이 없으면 사람들은 새 후보를 만들고, 그러면 「무엇이 왜 막혔는가」의
    이력이 끊긴다."""
    m.assert_transition("BLOCKED", "DRAFT")


def test_retired_is_terminal():
    """⚠️ 되살린 결속은 「언제부터 다시 쓰였나」가 흐려진다 — 새 후보를 만든다."""
    assert m.BINDING_TRANSITIONS["RETIRED"] == ()


# ── 검증 ─────────────────────────────────────────────────────────────────
def test_a_file_snapshot_without_a_column_map_is_blocked(store, instance):
    """⚠️ 어느 열이 어느 필드인지 **사람이 정해야 한다** — 추측하지 않는다."""
    row = _binding(store, instance, config={"file_name": "a.csv"})
    row = sb.validate(store, row["binding_id"])
    assert row["state"] == m.BLOCKED
    assert "column_map" in row["blocked_reason"]


def test_a_file_snapshot_without_a_file_name_is_blocked(store, instance):
    row = _binding(store, instance, config={"column_map": {"a": "A"}})
    assert sb.validate(store, row["binding_id"])["state"] == m.BLOCKED


def test_a_native_binding_needs_a_dataset_name(store, instance):
    row = _binding(store, instance, provider=m.PROVIDER_AFS_NATIVE, config={})
    assert sb.validate(store, row["binding_id"])["state"] == m.BLOCKED
    ok = _binding(store, instance, provider=m.PROVIDER_AFS_NATIVE,
                  config={"dataset_name": "arrivals"})
    assert sb.validate(store, ok["binding_id"])["state"] == m.VALIDATED


def test_connector_query_says_it_is_not_supported_yet(store, instance):
    """★★★ 목록에는 있지만 **아직 되지 않는다.**

    ⚠️ 「선택은 되는데 아무 일도 안 일어나는」 화면을 만들지 않으려면 여기서 분명히
      말해야 한다 — 조용히 통과시키면 사용자는 원천을 붙였다고 믿는다."""
    row = _binding(store, instance, provider=m.PROVIDER_CONNECTOR_QUERY, config={})
    row = sb.validate(store, row["binding_id"])
    assert row["state"] == m.BLOCKED
    assert "아직 지원하지 않습니다" in row["blocked_reason"]


def test_a_failed_validation_is_recorded_not_just_raised(store, instance):
    """★ 검증 실패를 `BLOCKED` 로 **남긴다** — 그냥 오류로 돌려주면 이력이 없고,
    다음 사람이 같은 설정을 다시 낸다."""
    row = sb.validate(store, _binding(store, instance, config={})["binding_id"])
    assert row["state"] == m.BLOCKED and row["blocked_reason"]
    again = store.get_binding(row["binding_id"])
    assert again["blocked_reason"] == row["blocked_reason"], "사유가 저장되지 않았다"


def test_blocking_without_a_reason_is_refused(store, instance):
    """⚠️ 사유 없는 차단은 나중에 「왜 막혔지?」에 답할 수 없고, 아무도 되돌리지 못한다."""
    row = _binding(store, instance)
    with pytest.raises(m.DataPreparationError):
        store.transition(row["binding_id"], m.BLOCKED, blocked_reason="")


# ── 후보는 여럿 ──────────────────────────────────────────────────────────
def test_many_candidates_may_exist_for_one_dataset(store, instance):
    """★ 비교해 고르는 일이 가능하려면 후보가 여럿이어야 한다."""
    a = _binding(store, instance)
    b = _binding(store, instance, config={"file_name": "b.csv", "column_map": {"x": "X"}})
    rows = store.list_bindings(instance["instance_id"], "arrivals")
    assert {r["binding_id"] for r in rows} == {a["binding_id"], b["binding_id"]}
    assert all(r["state"] == m.DRAFT for r in rows)


# ── 활성은 하나 ──────────────────────────────────────────────────────────
def test_the_full_path_reaches_active(store, instance):
    """★ 키트 적용 → 결속 후보 → 검증 → 승인 → 활성(Gate C)."""
    row = _to_active(store, _binding(store, instance))
    assert row["state"] == m.ACTIVE
    assert store.active_binding(instance["instance_id"], "arrivals")["binding_id"] \
        == row["binding_id"]


def test_activating_a_second_one_retires_the_first(store, instance):
    """★★★ 활성 교체는 **한 트랜잭션**이다 — 나누면 그 사이에 「활성이 하나도 없는」
    순간이 생기고, 그때 들어온 요청은 「원천이 없다」를 본다."""
    first = _to_active(store, _binding(store, instance))
    second = _to_active(store, _binding(
        store, instance, config={"file_name": "b.csv", "column_map": {"x": "X"}}))

    assert store.get_binding(first["binding_id"])["state"] == m.RETIRED
    assert store.get_binding(second["binding_id"])["state"] == m.ACTIVE
    actives = [r for r in store.list_bindings(instance["instance_id"], "arrivals")
               if r["state"] == m.ACTIVE]
    assert len(actives) == 1


def test_the_database_itself_refuses_a_second_active(store, instance):
    """★★★ **DB 부분 유일 인덱스**가 두 번째 방어선이다.

    ⚠️ 애플리케이션 코드로만 막으면 「먼저 종료하고 새로 활성화」 사이의 틈에서 둘이
      된다. 여기서는 코드를 **건너뛰고** DB 에 직접 써서 그 방어선을 확인한다."""
    first = _to_active(store, _binding(store, instance))
    other = _binding(store, instance, config={"file_name": "c.csv",
                                              "column_map": {"x": "X"}})
    with store.transaction() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE source_bindings SET state=? WHERE binding_id=?",
                         (m.ACTIVE, other["binding_id"]))
    assert store.get_binding(first["binding_id"])["state"] == m.ACTIVE


def test_different_datasets_may_each_have_an_active(store, instance):
    """⚠️ 유일성은 **(인스턴스, 데이터셋)** 단위다 — 전체 유일로 만들면 데이터셋 하나만
    붙일 수 있게 된다."""
    a = _to_active(store, _binding(store, instance, key="arrivals"))
    b = _to_active(store, _binding(store, instance, key="orders"))
    assert a["state"] == b["state"] == m.ACTIVE


def test_different_instances_do_not_collide(store):
    i1 = store.create_instance(kit_id="k", version="1.0.0", kit_fingerprint="f",
                               tenant_id="t1", scope_node_id="n1", entity_mode="REAL")
    i2 = store.create_instance(kit_id="k", version="1.0.0", kit_fingerprint="f",
                               tenant_id="t1", scope_node_id="n2", entity_mode="REAL")
    assert _to_active(store, _binding(store, i1))["state"] == m.ACTIVE
    assert _to_active(store, _binding(store, i2))["state"] == m.ACTIVE


def test_a_non_materializable_provider_is_not_activated(store, instance):
    """★★★ 활성인데 데이터가 안 흐르면 사용자는 「원천을 붙였다」고 믿고 **빈 화면**을
    본다. 그 오해가 가장 비싸다."""
    row = _binding(store, instance, provider=m.PROVIDER_CONNECTOR_QUERY, config={})
    #: 검증을 건너뛰고 상태만 밀어 올린다 — 활성화 문턱이 따로 있는지 본다
    store.transition(row["binding_id"], m.VALIDATED)
    store.transition(row["binding_id"], m.APPROVED)
    with pytest.raises(m.StateConflict) as e:
        sb.activate(store, row["binding_id"])
    assert "데이터가 흐르지 않습니다" in str(e.value)


def test_concurrent_activation_leaves_exactly_one_active(store, instance):
    """★★★ 동시에 눌러도 활성은 하나다."""
    rows = [_to_active(store, _binding(store, instance))]
    candidates = [_binding(store, instance,
                           config={"file_name": f"{i}.csv", "column_map": {"x": "X"}})
                  for i in range(4)]
    for c in candidates:
        sb.validate(store, c["binding_id"])
        sb.approve(store, c["binding_id"])

    errors = []
    barrier = threading.Barrier(len(candidates))

    def _go(c):
        barrier.wait()
        try:
            sb.activate(store, c["binding_id"])
        except Exception as e:          # 경쟁에서 진 쪽은 실패해도 된다 — 둘이 되면 안 된다
            errors.append(e)

    threads = [threading.Thread(target=_go, args=(c,)) for c in candidates]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    actives = [r for r in store.list_bindings(instance["instance_id"], "arrivals")
               if r["state"] == m.ACTIVE]
    assert len(actives) == 1, f"활성이 {len(actives)} 건이다 (오류 {len(errors)}건)"


# ── 커버리지 ─────────────────────────────────────────────────────────────
def test_coverage_separates_candidates_from_actives(store, instance):
    """★ 「후보가 있다」와 「활성이다」를 섞으면 준비도가 실제보다 높게 보이고, 그
    숫자로 시연 준비가 끝났다고 판단하게 된다."""
    _to_active(store, _binding(store, instance, key="arrivals"))
    _binding(store, instance, key="orders")                       # 후보만
    blocked = _binding(store, instance, key="suppliers", config={})
    sb.validate(store, blocked["binding_id"])                     # → BLOCKED

    cov = sb.coverage(store, instance["instance_id"],
                      ["arrivals", "orders", "suppliers", "prices"])
    assert cov["active"] == ["arrivals"]
    assert cov["candidate"] == ["orders"]
    assert cov["blocked"] == ["suppliers"]
    assert cov["missing"] == ["prices"]
    assert cov["ready"] is False


def test_coverage_is_ready_only_when_every_key_is_active(store, instance):
    for key in ("a", "b"):
        _to_active(store, _binding(store, instance, key=key))
    assert sb.coverage(store, instance["instance_id"], ["a", "b"])["ready"] is True
    assert sb.coverage(store, instance["instance_id"], ["a", "b", "c"])["ready"] is False


def test_coverage_of_nothing_is_not_ready(store, instance):
    """⚠️ 요구가 0개일 때 「전부 준비됐다」로 읽으면, 키트를 못 읽은 상태가 **완료**로
    보인다."""
    assert sb.coverage(store, instance["instance_id"], [])["ready"] is False


def test_coverage_does_not_count_an_approved_candidate_as_active(store, instance):
    """★★★ **승인은 활성이 아니다.**

    ⚠️ 앞 시험은 이것을 못 잡는다 — 후보를 `DRAFT` 로만 두면 「APPROVED 도 활성으로
      센다」는 변이가 관찰되지 않는다(변이 검사 실측). 승인까지 올린 후보를 따로 둔다.
    ★ 승인은 「써도 된다」이고 활성은 「지금 쓰고 있다」다. 섞으면 준비도가 실제보다
      높게 보이고, 그 숫자로 시연 준비가 끝났다고 판단하게 된다."""
    approved = _binding(store, instance, key="orders")
    sb.validate(store, approved["binding_id"])
    sb.approve(store, approved["binding_id"])
    assert store.get_binding(approved["binding_id"])["state"] == m.APPROVED

    cov = sb.coverage(store, instance["instance_id"], ["orders"])
    assert cov["active"] == [], "승인만 된 후보를 활성으로 셌다"
    assert cov["candidate"] == ["orders"]
    assert cov["ready"] is False
