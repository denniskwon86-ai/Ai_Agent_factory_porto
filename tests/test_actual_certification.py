"""[M0] 회사 실적 인증 — 서명은 «종류» 이고 병렬이다. 2026-09-12.

이 파일이 지키는 것 여섯.

  ① **서명이 대사를 대신하지 않는다** — `RECONCILED` 를 마친 판에만 서명한다
  ② **소유 부서는 «찾는다»** — 받지 않는다. 결속이 없으면 서명이 서지 않는다
  ③ ★★★ **필요한 종류가 다 모여야 인증이 선다** — 하나만 눌러도 «인증» 이 아니다
  ④ **용도 선언이 쓰임을 제약한다** — OPERATIONAL 로 인증하면 경영 보고에 못 쓴다
  ⑤ **대사 증거가 없으면 서명이 안 선다**
  ⑥ **시연 자료에는 실적 인증을 붙이지 않는다**

## ⚠️ 조직 층은 «격리» 한다, 없애지 않는다

`_require_approval_authority()` 는 조직 정본을 읽고 네 관문을 지난다 — 그 층에는
자기 시험이 있다. 여기서 그것을 **다시 시험하지 않되**, 「부르는가」는 시험한다
(monkeypatch 로 호출 여부를 센다). 안 그러면 관문을 빼먹어도 이 파일은 초록이다.
"""
import os
import tempfile

import pytest

from core import actual_certification_policy as acp
from core.data_preparation import models as m
from core.data_preparation import ownership_binding as ob
from core.data_preparation import snapshot_service as svc
from core.data_preparation.store import DataPreparationStore

OWNER_DEPT = "demo_smelting"
ACTOR_OWNER = "owner@test.invalid"
ACTOR_EXEC = "exec@test.invalid"
EVIDENCE = "SAP FI 2026/08 마감(2026-09-05 확정) · 계정 4000 100,000 / 5000 90,000 대사 일치"
ROWS = [{"a": "1"}]


@pytest.fixture()
def store(tmp_path):
    s = DataPreparationStore(db_path=str(tmp_path / "dp.db"))
    assert "WorkSpace" not in s.db_path, "운영 저장소를 열었다"
    return s


@pytest.fixture()
def authority(monkeypatch):
    """조직 층을 격리하되 **불렸는지는 센다.**

    ⚠️ 그냥 no-op 로 덮으면 「승인권을 안 봐도」 시험이 통과한다 — 관문을 빼먹은 것을
      못 잡는다. 호출을 세어 ③ 관문이 실제로 지나갔음을 확인한다."""
    calls = []
    monkeypatch.setattr(ob, "_require_approval_authority", lambda actor: calls.append(actor))
    monkeypatch.setattr(ob, "resolve", lambda conn, **kw: {"owner_dept_id": OWNER_DEPT})
    return calls


def _reconciled(store, tmp_path, *, data_kind=m.DATA_KIND_REAL, contract="FIN-03"):
    store.upsert_kit_version(kit_id="k", version="1.0.0", name="t", mode="DEMO/SYNTHETIC",
                             source_path="k.json", fingerprint_value="fp",
                             profile={"datasets": []})
    fp = store.get_kit_version("k", "1.0.0")["fingerprint"]
    inst = store.create_instance(kit_id="k", version="1.0.0", kit_fingerprint=fp,
                                 tenant_id="T", scope_node_id="S", entity_mode="REAL")
    binding = store.create_binding(instance_id=inst["instance_id"],
                                   dataset_contract_key=contract,
                                   provider=m.PROVIDER_FILE_SNAPSHOT, config={},
                                   tenant_id="T", scope_node_id="S", entity_mode="REAL")
    snap = svc.ingest(store, binding=binding, payload=b"a\n1\n", file_name="f.csv",
                      workspace_root=str(tmp_path), created_by="t", data_kind=data_kind)
    sid = snap["snapshot_id"]
    svc.profile(store, sid, ROWS, ["a"])
    svc.standardize(store, sid, ROWS)
    svc.reconcile(store, sid, ROWS, {"row_count": 1})
    return sid


def _sign(store, sid, kind, actor, **kw):
    args = dict(review_kind=kind, actor=actor, reconciliation_evidence=EVIDENCE,
                use_kind=acp.USE_OPERATIONAL)
    args.update(kw)
    return svc.sign_actual_certification(store, sid, **args)


# ── ① 서명이 대사를 대신하지 않는다 ────────────────────────────────────────
@pytest.mark.parametrize("stop_at", [m.RAW, m.PROFILED, m.STANDARDIZED])
def test_a_snapshot_must_be_reconciled_before_anyone_signs(store, tmp_path, authority, stop_at):
    """★★★ 대사도 안 한 판에 서명받으면 그 서명은 «안 잘렸나» 조차 모르는 판에 대한 것이다."""
    store.upsert_kit_version(kit_id="k", version="1.0.0", name="t", mode="DEMO/SYNTHETIC",
                             source_path="k.json", fingerprint_value="fp", profile={})
    fp = store.get_kit_version("k", "1.0.0")["fingerprint"]
    inst = store.create_instance(kit_id="k", version="1.0.0", kit_fingerprint=fp,
                                 tenant_id="T", scope_node_id="S", entity_mode="REAL")
    binding = store.create_binding(instance_id=inst["instance_id"], dataset_contract_key="FIN-03",
                                   provider=m.PROVIDER_FILE_SNAPSHOT, config={},
                                   tenant_id="T", scope_node_id="S", entity_mode="REAL")
    snap = svc.ingest(store, binding=binding, payload=b"a\n1\n", file_name="f.csv",
                      workspace_root=str(tmp_path), created_by="t",
                      data_kind=m.DATA_KIND_REAL)
    sid = snap["snapshot_id"]
    if stop_at in (m.PROFILED, m.STANDARDIZED):
        svc.profile(store, sid, ROWS, ["a"])
    if stop_at == m.STANDARDIZED:
        svc.standardize(store, sid, ROWS)
    with pytest.raises(m.StateConflict) as e:
        _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER)
    assert "서명이 대사를 대신하지 않습니다" in str(e.value)


def test_demo_data_gets_no_actual_certification(store, tmp_path, authority):
    """⑥ 시연 자료에 실적 인증을 붙이면 시연이 실적으로 읽힌다."""
    sid = _reconciled(store, tmp_path, data_kind=m.DATA_KIND_DEMO)
    with pytest.raises(m.StateConflict) as e:
        _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER)
    assert "REAL» 전용" in str(e.value)


# ── ② 소유 부서는 «찾는다» ─────────────────────────────────────────────────
def test_an_unbound_dataset_cannot_be_signed(store, tmp_path, monkeypatch):
    """★★★ 「누구 데이터인지 모르는 실적」에 서명을 받으면 그 서명은 무엇에 대한 것인가."""
    monkeypatch.setattr(ob, "_require_approval_authority", lambda actor: None)
    monkeypatch.setattr(ob, "resolve", lambda conn, **kw: None)
    sid = _reconciled(store, tmp_path)
    with pytest.raises(m.DataPreparationError) as e:
        _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER)
    assert "소유 부서가 결속돼 있지 않습니다" in str(e.value)


def test_the_owner_department_is_recorded_from_the_binding(store, tmp_path, authority):
    """★ 서명자가 «자기 부서를 적는» 것이 아니라 결속에서 온다."""
    sid = _reconciled(store, tmp_path)
    out = _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER)
    assert out["owner_dept_id"] == OWNER_DEPT
    assert svc.actual_certifications(store, sid)[0]["owner_dept_id"] == OWNER_DEPT


def test_the_approval_authority_check_actually_runs(store, tmp_path, authority):
    """⚠️ 「관문이 있다」와 「관문이 걸린다」는 다르다 — 불렸는지를 «센다»."""
    sid = _reconciled(store, tmp_path)
    _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER)
    assert authority == [ACTOR_OWNER], "승인권 확인이 호출되지 않았다"


# ── ③ ★★★ 필요한 종류가 다 모여야 인증이 선다 ─────────────────────────────
def test_one_signature_is_enough_for_operational(store, tmp_path, authority):
    sid = _reconciled(store, tmp_path)
    out = _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER)
    assert out["certified"] is True
    assert out["state"] == m.OWNER_CERTIFIED
    assert store.get_snapshot(sid)["certified_by"] == ACTOR_OWNER


def test_management_needs_both_and_one_is_not_enough(store, tmp_path, authority):
    """★★★ 하나만 눌러도 «인증» 이 아니다 — 그러면 임원 서명이 장식이 된다."""
    sid = _reconciled(store, tmp_path)
    first = _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER,
                  use_kind=acp.USE_MANAGEMENT)
    assert first["certified"] is False
    assert first["missing"] == [acp.REVIEW_EXECUTIVE]
    assert store.get_snapshot(sid)["state"] == m.RECONCILED, "아직 인증되면 안 된다"

    second = _sign(store, sid, acp.REVIEW_EXECUTIVE, ACTOR_EXEC,
                   use_kind=acp.USE_MANAGEMENT)
    assert second["certified"] is True
    assert second["state"] == m.OWNER_CERTIFIED
    assert sorted(second["signed"]) == [acp.REVIEW_DATA_OWNER, acp.REVIEW_EXECUTIVE]


def test_the_missing_signature_says_who_should_press_it(store, tmp_path, authority):
    """★ 「아직 안 됐다」가 아니라 «누가 안 눌렀는지» 를 말한다 — 그래야 사람이 누른다."""
    sid = _reconciled(store, tmp_path)
    out = _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, use_kind=acp.USE_MANAGEMENT)
    assert acp.reviewer_title(acp.REVIEW_EXECUTIVE) in out["next_action"]


def test_signatures_are_parallel_not_sequential(store, tmp_path, authority):
    """★★★ 순차로 만들면 부서장이 휴가 갈 때 «전체가 멈춘다» — 임원이 먼저 눌러도 된다."""
    sid = _reconciled(store, tmp_path)
    first = _sign(store, sid, acp.REVIEW_EXECUTIVE, ACTOR_EXEC, use_kind=acp.USE_MANAGEMENT)
    assert first["certified"] is False
    assert first["missing"] == [acp.REVIEW_DATA_OWNER]
    second = _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, use_kind=acp.USE_MANAGEMENT)
    assert second["certified"] is True


def test_an_unneeded_signature_kind_is_refused(store, tmp_path, authority):
    """필요 없는 서명을 받으면 「무엇이 갖춰졌나」를 셀 수 없다."""
    sid = _reconciled(store, tmp_path)
    with pytest.raises(m.DataPreparationError) as e:
        _sign(store, sid, acp.REVIEW_EXECUTIVE, ACTOR_EXEC, use_kind=acp.USE_OPERATIONAL)
    assert "필요하지 않습니다" in str(e.value)


def test_an_unknown_signature_kind_is_refused(store, tmp_path, authority):
    sid = _reconciled(store, tmp_path)
    with pytest.raises(m.DataPreparationError):
        _sign(store, sid, "AUDITOR", ACTOR_OWNER)


# ── ④ 용도 선언이 쓰임을 제약한다 ──────────────────────────────────────────
def test_the_declared_use_kind_is_stored(store, tmp_path, authority):
    sid = _reconciled(store, tmp_path)
    _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, use_kind=acp.USE_OPERATIONAL)
    assert store.get_snapshot(sid)["certified_use_kind"] == acp.USE_OPERATIONAL


def test_the_use_kind_cannot_be_switched_midway(store, tmp_path, authority):
    """★★★ 용도가 섞이면 「이 판이 무엇으로 인증됐나」에 답할 수 없다."""
    sid = _reconciled(store, tmp_path)
    _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, use_kind=acp.USE_MANAGEMENT)
    with pytest.raises(m.DataPreparationError) as e:
        _sign(store, sid, acp.REVIEW_EXECUTIVE, ACTOR_EXEC, use_kind=acp.USE_OPERATIONAL)
    assert "용도가 섞이면" in str(e.value)


def test_an_unknown_use_kind_is_refused(store, tmp_path, authority):
    sid = _reconciled(store, tmp_path)
    with pytest.raises(acp.ActualCertificationPolicyError):
        _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, use_kind="WHATEVER")


def test_the_result_says_the_declaration_constrains_use(store, tmp_path, authority):
    """⚠️ 「인증됐다」만 돌려주면 사용자는 어디에나 쓸 수 있다고 믿는다."""
    sid = _reconciled(store, tmp_path)
    out = _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, use_kind=acp.USE_OPERATIONAL)
    assert "경영 보고에 쓸 수 없습니다" in out["note"]


# ── ⑤ 대사 증거 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["", "   ", "SAP"])
def test_a_missing_or_thin_reconciliation_is_refused(store, tmp_path, authority, bad):
    sid = _reconciled(store, tmp_path)
    with pytest.raises(acp.ActualCertificationPolicyError):
        _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, reconciliation_evidence=bad)


def test_the_reconciliation_evidence_is_stored_per_signature(store, tmp_path, authority):
    """★ 서명마다 «무엇과 맞췄나» 가 다를 수 있다 — 부서장과 임원이 본 것이 다르다."""
    sid = _reconciled(store, tmp_path)
    _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, use_kind=acp.USE_MANAGEMENT)
    _sign(store, sid, acp.REVIEW_EXECUTIVE, ACTOR_EXEC, use_kind=acp.USE_MANAGEMENT,
          reconciliation_evidence="경영관리 검토 2026-09-06 · 부서 제출본과 총계 일치")
    rows = {r["review_kind"]: r["reconciliation_evidence"]
            for r in svc.actual_certifications(store, sid)}
    assert "SAP FI" in rows[acp.REVIEW_DATA_OWNER]
    assert "경영관리 검토" in rows[acp.REVIEW_EXECUTIVE]


# ── 귀속 기간 — 「어느 8월을 인증했나」 ─────────────────────────────────────
def test_the_period_is_recorded(store, tmp_path, authority):
    sid = _reconciled(store, tmp_path)
    _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER,
          period_from="2026-08-01", period_to="2026-08-31")
    row = store.get_snapshot(sid)
    assert row["period_from"] == "2026-08-01"
    assert row["period_to"] == "2026-08-31"


def test_the_period_does_not_move_after_the_first_signature(store, tmp_path, authority):
    """★★★ 기간이 바뀌면 「어느 8월을 인증했나」가 흔들린다 — 정정은 새 판이다."""
    sid = _reconciled(store, tmp_path)
    _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, use_kind=acp.USE_MANAGEMENT,
          period_from="2026-08-01", period_to="2026-08-31")
    _sign(store, sid, acp.REVIEW_EXECUTIVE, ACTOR_EXEC, use_kind=acp.USE_MANAGEMENT,
          period_from="2026-09-01", period_to="2026-09-30")
    row = store.get_snapshot(sid)
    assert row["period_from"] == "2026-08-01", "첫 서명의 기간이 남아야 한다"


# ── 정정은 «새 판» 이다 ────────────────────────────────────────────────────
def test_a_certified_snapshot_only_goes_to_revoked(store, tmp_path, authority):
    """조정분개가 오면 철회하고 새 판을 만든다 — 인증 뒤엔 앞으로 못 간다."""
    sid = _reconciled(store, tmp_path)
    _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER)
    assert m.SNAPSHOT_TRANSITIONS[m.OWNER_CERTIFIED] == (m.REVOKED,)
    with pytest.raises(m.StateConflict):
        store.advance_snapshot(sid, m.DEMO_CERTIFIED, certified_by="x@test.invalid")


def test_owner_certified_counts_as_certified():
    """★ 인증판만 읽는 기준선·계산·색인이 실적을 «본다»."""
    assert m.is_certified(m.OWNER_CERTIFIED) is True
    assert m.OWNER_CERTIFIED in m.CERTIFIED_STATES
    assert m.CERTIFICATION_DATA_KIND[m.OWNER_CERTIFIED] == m.DATA_KIND_REAL


# ── ⑦ 사용 보류 · 서명/인증 원자성 [2026-09-12, Codex 인계분] ──────────────
#
# Codex 가 보드([DATA-USAGE-HOLD-20260912])에서 넘긴 두 가지를 여기서 지킨다.
#   ㉠ 보류 검사는 **서명을 받기 전에** 지나간다
#   ㉡ 마지막 서명과 상태 전환은 **한 트랜잭션**이다 — 반쪽이 남지 않는다

def _hold(store, sid, *codes):
    """인증된 구버전 결속에 사용 보류를 심는다(시험 전용 SQL). 제품에 해제 경로는 없다."""
    import json

    binding_id = store.get_snapshot(sid)["binding_id"]
    with store.transaction() as conn:
        conn.execute("UPDATE source_bindings SET config_json=? WHERE binding_id=?",
                     (json.dumps({"usage_holds": list(codes)}), binding_id))


def test_a_hold_blocks_the_first_signature_and_leaves_no_trace(store, tmp_path, authority):
    """⚠️ 보류는 **첫 서명부터** 막는다.

    나중에 보면 부서장은 서명하고 퇴근하고 막판에 임원이 벽을 만난다 — 차단이
    틀린 사람에게 틀린 시점에 도착한다. 그리고 막혔으면 **서명이 남지 않아야** 한다."""
    from core.data_preparation import usage_policy

    sid = _reconciled(store, tmp_path)
    _hold(store, sid, "PRICE_VINTAGE_AND_CONVERSION_POLICY_REQUIRED")
    with pytest.raises(usage_policy.UsageHoldError):
        _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER,
              use_kind=acp.USE_MANAGEMENT)
    assert svc.actual_certifications(store, sid) == [], "막힌 서명이 남았다"


def test_a_hold_blocks_the_last_signature_without_half_committing(store, tmp_path,
                                                                  authority):
    """★★★ **반쪽이 남지 않는다** — 이 시험이 원자성의 증거다.

    나눠 쓰면 「서명은 다 모였는데 인증은 안 선」 판이 남고, 그것을 본 사람은 누가
    무엇을 빠뜨렸는지 알 수 없다. 마지막 서명이 막히면 **그 서명 자체가 없어야** 한다."""
    from core.data_preparation import usage_policy

    sid = _reconciled(store, tmp_path)
    first = _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER,
                  use_kind=acp.USE_MANAGEMENT)
    assert first["certified"] is False and first["missing"] == [acp.REVIEW_EXECUTIVE]

    _hold(store, sid, "PRICE_VINTAGE_AND_CONVERSION_POLICY_REQUIRED")
    with pytest.raises(usage_policy.UsageHoldError):
        _sign(store, sid, acp.REVIEW_EXECUTIVE, ACTOR_EXEC, use_kind=acp.USE_MANAGEMENT)

    assert store.get_snapshot(sid)["state"] == m.RECONCILED, "막혔는데 인증이 섰다"
    kinds = [r["review_kind"] for r in svc.actual_certifications(store, sid)]
    assert kinds == [acp.REVIEW_DATA_OWNER], f"막힌 서명이 남았다: {kinds}"


def test_the_last_signature_and_the_certification_land_together(store, tmp_path, authority):
    """반대 방향 — 보류가 없으면 서명과 인증이 **함께** 선다."""
    sid = _reconciled(store, tmp_path)
    _sign(store, sid, acp.REVIEW_DATA_OWNER, ACTOR_OWNER, use_kind=acp.USE_MANAGEMENT)
    out = _sign(store, sid, acp.REVIEW_EXECUTIVE, ACTOR_EXEC, use_kind=acp.USE_MANAGEMENT)

    assert out["certified"] is True
    assert store.get_snapshot(sid)["state"] == m.OWNER_CERTIFIED
    assert sorted(r["review_kind"] for r in svc.actual_certifications(store, sid)) == \
        sorted([acp.REVIEW_DATA_OWNER, acp.REVIEW_EXECUTIVE])
