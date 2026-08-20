"""★★★ [BDR-5] 결정론적 준비도 — 「지금 무엇까지 믿고 만들 수 있는가」.

## 이 파일이 막으려는 세 가지

★★★ ① **부족한 값이 0으로 채워지는 것.** 준비되지 않은 데이터는 「0건」이 아니라
  「아직 아니다」다. 0으로 채우면 보고서가 «완성» 되고, 그 순간 아무도 그것이
  미완이라고 생각하지 않는다.
★★★ ② **같은 입력에 다른 답이 나오는 것.** 두 사람이 같은 화면을 보면서 다른
  결론을 내리고, 그 차이를 아무도 재현하지 못한다.
★★★ ③ **없음·못 읽음·승인 전·만료가 한 덩어리가 되는 것.** 「원천을 고르세요」와
  「승인을 받으세요」와 「다시 올리세요」는 **다른 사람이 하는 다른 일**이다.
"""
import pytest

from core.data_preparation import models as m
from core.data_preparation import readiness as r

NOW = "2026-08-18T00:00:00+00:00"


def _binding(state=m.ACTIVE, **kw):
    base = {"binding_id": "b1", "state": state, "tenant_id": "t1",
            "scope_node_id": "n1", "entity_mode": "REAL"}
    base.update(kw)
    return base


def _snap(state, *, sid="ds_1", certified_at="", created_at="2026-08-01T00:00:00+00:00",
          **kw):
    base = {"snapshot_id": sid, "state": state, "certified_at": certified_at,
            "created_at": created_at, "data_kind": m.DATA_KIND_DEMO}
    base.update(kw)
    return base


def _ready_snap(certified_at="2026-08-17T00:00:00+00:00"):
    return _snap(m.DEMO_CERTIFIED, certified_at=certified_at)


def _eval(binding=None, snapshots=(), **kw):
    return r.evaluate_dataset("arrivals", binding=binding, snapshots=list(snapshots),
                              now=kw.pop("now", NOW), **kw)


# ── 어휘 ─────────────────────────────────────────────────────────────────
def test_the_state_vocabulary_is_pinned_literally():
    """★ 어휘가 흔들리면 화면·API·판정이 서로 다른 말을 하게 된다.

    ⚠️ 정본이 둘로 갈렸던 자리다(설계서 §10.1 vs 솔로 인수인계 §9.1) — 그래서 여기에
      **하나만** 못 박는다."""
    assert r.DATASET_STATES == (
        "NOT_CONFIGURED", "SOURCE_CONFIGURED", "DATA_AVAILABLE", "QUALITY_FAILED",
        "RECONCILIATION_FAILED", "APPROVAL_PENDING", "READY", "STALE", "UNAVAILABLE")


def test_every_state_says_what_to_do_next_and_who_does_it():
    """★★★ 상태만 주고 다음 행동을 안 주면 사용자는 화면 앞에서 멈춘다.

    ⚠️ `READY` 만 예외다 — 할 일이 없다."""
    for state in r.DATASET_STATES:
        action, role = r._NEXT_ACTION[state]
        if state == r.READY:
            assert action == "" and role == ""
        else:
            assert action and role, f"{state} 에 다음 행동·책임자가 없다"


def test_only_ready_counts_as_official():
    """★★★ **만료된 판은 공식이 아니다.** 오래된 판으로 만든 숫자는 「틀렸다」가
    아니라 「언제 것인지 모른다」가 되고, 그쪽이 더 고치기 어렵다."""
    assert r.OFFICIAL_STATES == (r.READY,)
    assert r.STALE not in r.OFFICIAL_STATES


# ── ③ 넷은 서로 다르다 ───────────────────────────────────────────────────
def test_the_four_situations_stay_four_different_states():
    """★★★ 없음 · 못 읽음 · 승인 전 · 만료."""
    없음 = _eval(binding=None)
    못읽음 = _eval(binding=_binding(scope_node_id="n_다른곳"),
                   scope={"tenant_id": "t1", "scope_node_id": "n1", "entity_mode": "REAL"})
    승인전 = _eval(binding=_binding(), snapshots=[_snap(m.RECONCILED)])
    만료 = _eval(binding=_binding(),
                 snapshots=[_ready_snap("2026-01-01T00:00:00+00:00")], max_age_days=30)

    states = [없음["state"], 못읽음["state"], 승인전["state"], 만료["state"]]
    assert states == [r.NOT_CONFIGURED, r.UNAVAILABLE, r.APPROVAL_PENDING, r.STALE]
    assert len(set(states)) == 4, "넷이 한 덩어리가 됐다"
    #: 다음 행동도 넷 다 달라야 한다 — 같으면 상태를 나눈 의미가 없다
    assert len({x["next_action"] for x in (없음, 못읽음, 승인전, 만료)}) == 4


@pytest.mark.parametrize("snap_state,expected", [
    (m.RAW, r.DATA_AVAILABLE),
    (m.PROFILED, r.DATA_AVAILABLE),
    (m.STANDARDIZED, r.DATA_AVAILABLE),
    (m.RECONCILED, r.APPROVAL_PENDING),
    (m.DEMO_CERTIFIED, r.READY),
])
def test_each_pipeline_stage_maps_to_its_own_readiness(snap_state, expected):
    snap = (_ready_snap() if snap_state == m.DEMO_CERTIFIED else _snap(snap_state))
    assert _eval(binding=_binding(), snapshots=[snap])["state"] == expected


def test_a_quarantine_is_split_by_its_machine_code_not_its_prose():
    """★★★ 격리 사유를 **코드**로 나눈다.

    ⚠️ 사람이 읽는 문장으로 분기하면 문구를 다듬는 순간 판정이 조용히 바뀌고,
      시험은 그대로 통과한다."""
    quality = _eval(binding=_binding(), snapshots=[
        _snap(m.QUARANTINED, quarantine={"kind": m.QUARANTINE_QUALITY, "reason": "단위"})])
    recon = _eval(binding=_binding(), snapshots=[
        _snap(m.QUARANTINED, quarantine={"kind": m.QUARANTINE_RECONCILIATION,
                                         "reason": "합계"})])
    assert quality["state"] == r.QUALITY_FAILED
    assert recon["state"] == r.RECONCILIATION_FAILED
    assert quality["next_action"] != recon["next_action"], "고칠 사람이 같아졌다"


def test_a_quarantine_of_unknown_kind_is_unreadable_not_a_quality_failure():
    """⚠️ 「품질 실패」로 접으면 사용자가 파일을 고치러 가는데, 원인은 다른 곳일 수 있다."""
    out = _eval(binding=_binding(),
                snapshots=[_snap(m.QUARANTINED, quarantine={"reason": "무언가"})])
    assert out["state"] == r.UNAVAILABLE


def test_an_unknown_snapshot_state_is_unavailable_not_ready():
    """★★★ 모르는 것을 준비됨으로 떨어뜨리면 통제가 통째로 무의미해진다."""
    assert _eval(binding=_binding(),
                 snapshots=[_snap("아무거나")])["state"] == r.UNAVAILABLE


def test_an_inactive_binding_is_not_configured_yet():
    for state in (m.DRAFT, m.VALIDATED, m.APPROVED, m.RETIRED, m.BLOCKED):
        assert _eval(binding=_binding(state=state))["state"] == r.NOT_CONFIGURED


# ── 인증판 선택 ──────────────────────────────────────────────────────────
def test_an_uncertified_newer_snapshot_does_not_hide_the_certified_one():
    """★★★ 「가장 최근 판」이 아니라 「가장 최근 **인증된** 판」이다.

    ⚠️ 반대로 두면 승인 전 데이터가 공식 화면에 오른다."""
    out = _eval(binding=_binding(), snapshots=[
        _ready_snap(), _snap(m.RAW, sid="ds_2", created_at="2026-08-18T00:00:00+00:00")])
    assert out["state"] == r.READY
    assert out["snapshot_id"] == "ds_1"


def test_the_certified_snapshot_is_chosen_by_time_not_by_list_position():
    """★★★ 인증판이 **여럿일 때** 어느 것을 쓰는가.

    ⚠️ 목록의 마지막을 집으면 조회 순서 하나로 «오늘 판» 과 «지난달 판» 이 뒤바뀐다 —
      그리고 그 화면은 오류를 내지 않는다. 변이 검사가 실제로 이 자리를 뚫었다."""
    old = _snap(m.DEMO_CERTIFIED, sid="ds_old", certified_at="2026-01-01T00:00:00+00:00")
    new = _snap(m.DEMO_CERTIFIED, sid="ds_new", certified_at="2026-08-17T00:00:00+00:00")
    #: 새 판을 **앞에** 두고 옛 판을 뒤에 둔다 — 위치로 고르면 옛 판이 이긴다
    out = _eval(binding=_binding(), snapshots=[new, old])
    assert out["snapshot_id"] == "ds_new", "목록 위치로 골랐다"
    assert out["as_of"] == "2026-08-17T00:00:00+00:00"


def test_a_revoked_snapshot_is_not_certified():
    assert _eval(binding=_binding(),
                 snapshots=[_snap(m.REVOKED)])["state"] == r.UNAVAILABLE


def test_the_as_of_is_the_certification_time_not_the_evaluation_time():
    """⚠️ 판정 시각을 주면 화면이 매번 새로 보이고, 사용자는 데이터가 갱신됐다고 믿는다."""
    out = _eval(binding=_binding(), snapshots=[_ready_snap("2026-08-10T00:00:00+00:00")])
    assert out["as_of"] == "2026-08-10T00:00:00+00:00"
    assert NOW not in out["as_of"]


def test_an_unreadable_timestamp_is_unavailable_not_fresh():
    """★★★ 읽을 수 없는 시각을 0일로 두면 **만료된 판이 신선해 보인다.**"""
    out = _eval(binding=_binding(), snapshots=[_ready_snap("어제쯤")], max_age_days=30)
    assert out["state"] == r.UNAVAILABLE


def test_without_an_age_policy_nothing_goes_stale():
    """⚠️ 대조군 — 위 시험들이 「전부 STALE」로도 통과하지 않게 한다."""
    out = _eval(binding=_binding(), snapshots=[_ready_snap("2020-01-01T00:00:00+00:00")])
    assert out["state"] == r.READY


# ── ② 결정론 ─────────────────────────────────────────────────────────────
def test_the_same_input_gives_the_same_answer():
    """★★★ 같은 입력이면 같은 판정 — **판 순서가 바뀌어도.**"""
    snaps = [_ready_snap(), _snap(m.RAW, sid="ds_9")]
    a = _eval(binding=_binding(), snapshots=snaps)
    b = _eval(binding=_binding(), snapshots=list(reversed(snaps)))
    assert a == b


def test_the_fingerprints_follow_the_inputs_not_the_order():
    keys = ["arrivals", "orders"]
    bindings = {"arrivals": _binding(), "orders": _binding(binding_id="b2")}
    snaps = {"arrivals": [_ready_snap()], "orders": []}
    a = r.evaluate_instance(contract_keys=keys, bindings=bindings, snapshots=snaps, now=NOW)
    b = r.evaluate_instance(contract_keys=list(reversed(keys)), bindings=dict(
        reversed(list(bindings.items()))), snapshots=snaps, now=NOW)
    assert a["binding_set_fingerprint"] == b["binding_set_fingerprint"]
    assert a["snapshot_set_fingerprint"] == b["snapshot_set_fingerprint"]


def test_a_changed_binding_changes_the_fingerprint():
    """⚠️ 지문이 안 변하면 캐시된 옛 판정이 재사용되고, 바뀐 사실이 화면에 안 나온다."""
    base = dict(contract_keys=["arrivals"], snapshots={"arrivals": []}, now=NOW)
    a = r.evaluate_instance(bindings={"arrivals": _binding()}, **base)
    b = r.evaluate_instance(bindings={"arrivals": _binding(state=m.RETIRED)}, **base)
    assert a["binding_set_fingerprint"] != b["binding_set_fingerprint"]


# ── ① 0으로 채우지 않는다 ────────────────────────────────────────────────
def test_coverage_counts_are_not_padded():
    out = r.evaluate_instance(
        contract_keys=["a", "b", "c"],
        bindings={"a": _binding(), "b": _binding(), "c": None},
        snapshots={"a": [_ready_snap()], "b": [_snap(m.RECONCILED)]}, now=NOW)
    assert out["coverage"] == {"required": 3, "ready": 1, "stale": 0, "blocked": 2}
    assert out["status"] == r.INSTANCE_PARTIAL


def test_nothing_ready_is_blocked_not_ready():
    out = r.evaluate_instance(contract_keys=["a"], bindings={"a": None},
                              snapshots={}, now=NOW)
    assert out["status"] == r.INSTANCE_BLOCKED


def test_an_instance_with_no_datasets_is_not_ready():
    """★★★ 요구가 0건인데 「전부 준비됨」이면, 키트를 못 읽은 것이 «완벽» 으로 보인다."""
    out = r.evaluate_instance(contract_keys=[], bindings={}, snapshots={}, now=NOW)
    assert out["status"] == r.INSTANCE_BLOCKED


def test_the_instance_as_of_is_the_oldest_ready_snapshot():
    """★ 가장 최신을 주면 화면이 실제보다 신선해 보인다."""
    out = r.evaluate_instance(
        contract_keys=["a", "b"], bindings={"a": _binding(), "b": _binding()},
        snapshots={"a": [_ready_snap("2026-08-01T00:00:00+00:00")],
                   "b": [_ready_snap("2026-08-17T00:00:00+00:00")]}, now=NOW)
    assert out["as_of"] == "2026-08-01T00:00:00+00:00"


# ── 산출물 ───────────────────────────────────────────────────────────────
OUTPUTS = [{"output": "입고 보고", "requires": ["a"]},
           {"output": "이행 현황", "requires": ["a", "b"]}]


def _instance(states):
    """상태를 직접 만들어 산출물 판정만 본다."""
    return r.evaluate_outputs(
        [{"dataset_contract_key": k, "state": v, "next_action": f"do {k}",
          "responsible_role": "담당자"} for k, v in states.items()], OUTPUTS)


def test_one_missing_dataset_blocks_the_whole_output():
    """★★★ 부분 계산을 하지 않는다 — 화면에서 완성된 숫자와 구별되지 않고, 그 숫자가
    회의에 올라간다."""
    out = {o["output"]: o for o in _instance({"a": r.READY, "b": r.APPROVAL_PENDING})}
    assert out["입고 보고"]["state"] == r.AVAILABLE
    assert out["이행 현황"]["state"] == r.BLOCKED_OUTPUT
    assert out["이행 현황"]["reason_code"] == "REQUIRED_DATA_APPROVAL_PENDING"
    assert out["이행 현황"]["blocking_datasets"] == ["b"]


def test_a_stale_dataset_makes_the_output_a_warning_not_a_pass():
    out = {o["output"]: o for o in _instance({"a": r.STALE, "b": r.READY})}
    assert out["입고 보고"]["state"] == r.AVAILABLE_WITH_WARNING
    assert "기준시점" in out["입고 보고"]["user_message"]


def test_an_output_requiring_an_unknown_dataset_is_blocked_not_skipped():
    """★★★ 요구사항 오타 하나가 산출물을 통과시키면, **데이터 없이도 «가능»** 이 된다."""
    out = r.evaluate_outputs([{"dataset_contract_key": "a", "state": r.READY,
                               "next_action": "", "responsible_role": ""}],
                             [{"output": "x", "requires": ["없는것"]}])
    assert out[0]["state"] == r.BLOCKED_OUTPUT
    assert out[0]["blocking_datasets"] == ["없는것"]


def test_a_blocked_output_says_who_does_what():
    out = _instance({"a": r.READY, "b": r.NOT_CONFIGURED})[0]
    assert out["next_action"] and out["responsible_role"]


# ── 권한 밖은 세지 않는다 ────────────────────────────────────────────────
def test_the_response_never_counts_things_outside_my_permission():
    """★★★ 「권한 밖 3건」을 세어 주면 그 3이 곧 「그 조직에 3건이 있다」가 된다.

    표현할 수 있는 유일한 «빠진 수» 는 `context_omitted` — **권한은 있으나 지금 고른
    문맥에서 빠진 수**다."""
    out = r.evaluate_instance(contract_keys=["a"], bindings={"a": _binding()},
                              snapshots={"a": []}, now=NOW, context_omitted=2)
    assert out["context_omitted"] == 2
    body = repr(out)
    for forbidden in ("denied", "forbidden", "hidden", "out_of_scope", "권한"):
        assert forbidden not in body


def test_a_negative_omitted_count_is_clamped_not_echoed():
    out = r.evaluate_instance(contract_keys=[], bindings={}, snapshots={}, now=NOW,
                              context_omitted=-5)
    assert out["context_omitted"] == 0


def test_an_empty_contract_key_is_refused():
    with pytest.raises(r.ReadinessError):
        r.evaluate_dataset("  ", binding=None, snapshots=[], now=NOW)


# ── [BDR-5] API 경계 ─────────────────────────────────────────────────────
import api.routes.data_preparation_control as dp                     # noqa: E402
from fastapi import FastAPI                                          # noqa: E402
from fastapi.testclient import TestClient                            # noqa: E402

from core.data_preparation import kit_registry as kr                 # noqa: E402
from core.data_preparation import snapshot_service as ss             # noqa: E402
from tests import org_seed                                           # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch, enforced_org):
    import config

    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    monkeypatch.setattr(dp, "_raw_root", lambda: str(tmp_path / "raw"))
    monkeypatch.setattr(dp, "_ctx", lambda p: {"tenant_id": "tenant_default",
                                               "entity_mode": "REAL"})
    monkeypatch.setattr(dp, "_visible_scopes", lambda p: ["n_mine"])
    app = FastAPI()
    app.include_router(dp.router)
    c = TestClient(app)
    #: 키트를 등록해 둔다 — 등록 전에는 인스턴스가 판본을 못 찾는다.
    c.get("/api/v1/data-preparation/kits", headers={"X-Factory-User": org_seed.ADMIN})
    return c


def _instance_of_demo_kit(scope_node_id="n_mine"):
    kit = kr.resolve(dp.store, kr.DEMO_KIT_ID, "1.0.0")
    assert kit, "데모 키트가 등록되지 않았다"
    return dp.store.create_instance(
        kit_id=kr.DEMO_KIT_ID, version="1.0.0",
        kit_fingerprint=str(kit["fingerprint"]), tenant_id="tenant_default",
        scope_node_id=scope_node_id, entity_mode="REAL")


def _readiness(client, instance_id, user=org_seed.ADMIN):
    return client.get(
        "/api/v1/data-preparation/instances/" + instance_id + "/readiness",
        headers={"X-Factory-User": user})


def test_a_fresh_instance_is_blocked_not_ready(client):
    """★★★ 아무 데이터도 없는데 「준비됨」이면, 그 화면이 곧 «시작해도 된다» 가 된다."""
    r = _readiness(client, _instance_of_demo_kit()["instance_id"])
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "BLOCKED"
    #: ⚠️ 요구 수를 **숫자로 박지 않는다** — 키트가 넓어질 때마다 시험이 깨지고,
    #:   그때 「3을 9로 고치는」 일이 반복되면 이 시험이 무엇을 지키는지 흐려진다.
    #:   지키려는 것은 「데이터가 없으면 준비 안 됨」이지 「요구가 몇 개인가」가 아니다.
    from core.data_preparation import kit_registry as _kr
    from core.data_preparation.store import data_preparation_store as _store
    _kit = _kr.resolve(_store, _kr.DEMO_KIT_ID, "1.0.0")
    assert data["coverage"]["required"] == len(_kr.dataset_keys((_kit or {}).get("profile")))
    assert data["coverage"]["required"] > 0, "요구가 0건이면 이 시험은 아무것도 안 지킨다"
    assert data["coverage"]["ready"] == 0
    assert all(d["state"] == "NOT_CONFIGURED" for d in data["datasets"])


def test_every_output_is_blocked_with_a_next_action(client):
    """⚠️ 「막혔다」만 말하고 무엇을 하라고 안 하면 사용자는 화면 앞에서 멈춘다."""
    data = _readiness(client, _instance_of_demo_kit()["instance_id"]).json()["data"]
    assert data["available_outputs"] == []
    assert data["blocked_outputs"], "산출물 판정이 비어 있다"
    for o in data["blocked_outputs"]:
        assert o["next_action"] and o["responsible_role"] and o["user_message"]


def test_the_answer_is_the_same_when_asked_twice(client):
    """★★★ Gate E — **준비도 동일 입력 동일 결과.**

    ⚠️ 판정 시각만 흐르는데 답이 달라지면, 두 사람이 같은 화면에서 다른 결론을 낸다."""
    iid = _instance_of_demo_kit()["instance_id"]
    a = _readiness(client, iid).json()["data"]
    b = _readiness(client, iid).json()["data"]
    assert a == b


def test_a_certified_snapshot_moves_one_dataset_to_ready(client, tmp_path):
    """⚠️ 대조군 — 위 시험들이 「전부 BLOCKED」로도 통과하지 않게 한다."""
    from core.data_preparation import source_binding as sb

    inst = _instance_of_demo_kit()
    b = dp.store.create_binding(
        instance_id=inst["instance_id"], dataset_contract_key="material_arrivals",
        provider=m.PROVIDER_FILE_SNAPSHOT,
        config={"file_name": "a.csv", "column_map": {"a": "A"}},
        tenant_id="tenant_default", scope_node_id="n_mine", entity_mode="REAL")
    for step in ("validate", "approve", "activate"):
        getattr(sb, step)(dp.store, b["binding_id"])

    payload = ("arrived_at,material_code,quantity\n"
               "2026-08-17,M1,10\n").encode("utf-8")
    snap = ss.ingest(dp.store, binding=dp.store.get_binding(b["binding_id"]),
                     payload=payload, file_name="a.csv",
                     workspace_root=str(tmp_path / "raw2"))
    rows = [{"arrived_at": "2026-08-17", "material_code": "M1", "quantity": "10"}]
    out = ss.run_pipeline(dp.store, snap["snapshot_id"], rows,
                          ["arrived_at", "material_code", "quantity"],
                          control={"row_count": 1, "sums": {"quantity": 10}})
    assert out["state"] == m.DEMO_CERTIFIED

    data = _readiness(client, inst["instance_id"]).json()["data"]
    states = {d["dataset_contract_key"]: d["state"] for d in data["datasets"]}
    assert states["material_arrivals"] == "READY", states
    assert data["status"] == "PARTIAL"
    assert data["coverage"]["ready"] == 1
    #: 「입고 현황 보고」는 이 데이터 하나만 요구한다 — 이제 가능해야 한다
    assert "입고 현황 보고" in data["available_outputs"], data["available_outputs"]


def test_readiness_of_another_scope_is_404(client):
    """★★★ 없는 것과 못 보는 것을 같은 404 로 돌려준다."""
    theirs = _instance_of_demo_kit(scope_node_id="n_theirs")
    missing = _readiness(client, "ki_없는것", user=org_seed.MEMBER_A)
    out_of_scope = _readiness(client, theirs["instance_id"], user=org_seed.MEMBER_A)
    assert missing.status_code == out_of_scope.status_code == 404
    assert missing.json()["detail"] == out_of_scope.json()["detail"]


def test_an_unreadable_kit_refuses_to_judge_instead_of_saying_ready(client):
    """★★★ 키트를 못 읽으면 **판정하지 않는다.**

    ⚠️ 빈 요구사항으로 판정하면 아무 데이터도 없는 인스턴스가 「전부 준비됨」으로
      나온다 — 0/0 은 100% 가 아니다."""
    orphan = dp.store.create_instance(
        kit_id="없는키트", version="9.9.9", kit_fingerprint="f",
        tenant_id="tenant_default", scope_node_id="n_mine", entity_mode="REAL")
    r = _readiness(client, orphan["instance_id"])
    assert r.status_code == 503, r.text


def test_the_response_says_it_is_demo_data(client):
    """⚠️ 「시연용」이 빠지면 그 숫자는 실적으로 읽힌다."""
    data = _readiness(client, _instance_of_demo_kit()["instance_id"]).json()["data"]
    assert data["data_kind"] == m.KIT_MODE_DEMO


def test_the_kit_refuses_an_output_requiring_a_dataset_it_does_not_have(tmp_path):
    """★★★ 오타 하나가 요구사항을 지우면 그 산출물은 **늘 «가능»** 이 된다."""
    import json as _json

    bad = tmp_path / "x.kit.json"
    bad.write_text(_json.dumps({
        "kit_id": "k", "version": "1.0.0", "name": "n",
        "datasets": [{"dataset_contract_key": "a"}],
        "outputs": [{"output": "보고", "requires": ["없는것"]}]}, ensure_ascii=False),
        encoding="utf-8")
    with pytest.raises(kr.KitLoadError):
        kr.load_profile(str(bad))


def test_the_kit_refuses_an_output_that_requires_nothing(tmp_path):
    """⚠️ 아무것도 요구하지 않는 산출물은 데이터가 하나도 없어도 «가능» 으로 보인다."""
    import json as _json

    bad = tmp_path / "y.kit.json"
    bad.write_text(_json.dumps({
        "kit_id": "k", "version": "1.0.0", "name": "n",
        "datasets": [{"dataset_contract_key": "a"}],
        "outputs": [{"output": "보고", "requires": []}]}, ensure_ascii=False),
        encoding="utf-8")
    with pytest.raises(kr.KitLoadError):
        kr.load_profile(str(bad))
