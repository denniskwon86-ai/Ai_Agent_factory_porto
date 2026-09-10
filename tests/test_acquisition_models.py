"""[DAO-0] 수집 작업 어휘가 **자기 자신과, 그리고 이미 있는 것들과** 어긋나지 않는지.

이 파일이 막는 것은 「닫힌 목록을 만들었는데 아무도 안 보는」 상태다. 목록은 두 방향으로
묶여 있어야 쓸모가 있다 — 안으로는 전이표가 목록 밖을 가리키지 않아야 하고, 밖으로는
**이미 그 값을 쓰고 있던 파일들**과 같은 어휘여야 한다.
"""
import glob
import json

import pytest

from core.external_intelligence import acquisition_models as am
from core.data_preparation import models as dpm


# ── 목록 자체의 정합 ──────────────────────────────────────────────────────────
def test_transition_table_covers_every_state():
    """전이표에 빠진 상태가 있으면 그 상태에 들어간 작업은 **영원히 못 나온다**."""
    assert set(am.ACQUISITION_TRANSITIONS) == set(am.ACQUISITION_STATES)


def test_transition_targets_are_known_states():
    for src, targets in am.ACQUISITION_TRANSITIONS.items():
        for t in targets:
            assert t in am.ACQUISITION_STATES, f"{src} -> {t} 가 목록 밖을 가리킨다"


def test_every_state_is_reachable_from_draft():
    """도달할 수 없는 상태는 선언만 있고 없는 것과 같다."""
    seen, frontier = {am.DRAFT}, [am.DRAFT]
    while frontier:
        cur = frontier.pop()
        for t in am.ACQUISITION_TRANSITIONS.get(cur, ()):
            if t not in seen:
                seen.add(t)
                frontier.append(t)
    assert seen == set(am.ACQUISITION_STATES), f"도달 불가: {set(am.ACQUISITION_STATES) - seen}"


# ── 사람 관문 ────────────────────────────────────────────────────────────────
def test_active_is_reachable_only_from_applying():
    """★★★ ACTIVE 로 들어오는 문이 둘이 되면 그중 하나는 검토를 건너뛴다."""
    doors = [s for s, t in am.ACQUISITION_TRANSITIONS.items() if am.ACTIVE in t]
    assert doors == [am.APPLYING]


def test_dry_run_cannot_skip_human_review():
    with pytest.raises(am.AcquisitionStateError):
        am.assert_transition(am.DRY_RUN, am.ACTIVE)
    am.assert_transition(am.DRY_RUN, am.REVIEW_REQUIRED)


def test_review_required_is_not_auto_advanced_from_discovery():
    """탐색 결과만으로 사람 관문에 도달할 수 없다 — 반드시 dry-run 을 거친다."""
    assert am.REVIEW_REQUIRED not in am.ACQUISITION_TRANSITIONS[am.DISCOVERING]
    assert am.REVIEW_REQUIRED not in am.ACQUISITION_TRANSITIONS[am.PLAN_READY]


def test_scheduler_touches_only_active():
    """지시 9 — ACTIVE 아닌 작업을 스케줄러가 움직이면 사람 관문이 무력해진다."""
    assert am.SCHEDULABLE_STATES == (am.ACTIVE,)
    assert am.DRAFT not in am.SCHEDULABLE_STATES
    assert am.REVIEW_REQUIRED not in am.SCHEDULABLE_STATES


def test_disabled_cannot_jump_back_into_the_middle():
    """꺼 둔 작업이 곧바로 APPLYING·ACTIVE 로 돌아오면 «껐다» 가 의미를 잃는다."""
    assert am.ACQUISITION_TRANSITIONS[am.DISABLED] == (am.DRAFT,)


# ── 장애와 자료 없음 ─────────────────────────────────────────────────────────
def test_no_data_is_a_distinct_state_from_failed():
    """지시 2 — 둘을 접으면 스케줄러가 없는 자료를 영원히 재시도한다."""
    assert am.NO_DATA != am.FAILED
    assert am.NO_DATA in am.ACQUISITION_STATES
    assert am.NO_DATA in am.ACQUISITION_TRANSITIONS[am.DISCOVERING]


def test_no_data_is_not_a_success_state():
    """0건을 «적용 완료» 로 읽히게 두지 않는다(readiness 의 「0으로 채우지 않는다」와 같은 규칙)."""
    assert am.ACTIVE not in am.ACQUISITION_TRANSITIONS[am.NO_DATA]


def test_failure_kind_routes_to_the_right_state():
    for kind in am.QUARANTINE_FAILURES:
        assert am.state_for_failure(kind) == am.QUARANTINED
    for kind in set(am.FAILURE_KINDS) - set(am.QUARANTINE_FAILURES):
        assert am.state_for_failure(kind) == am.FAILED


def test_unknown_failure_kind_is_rejected():
    with pytest.raises(am.AcquisitionStateError):
        am.state_for_failure("WHATEVER")


# ── 이미 있는 어휘와의 결속 ──────────────────────────────────────────────────
def test_quarantine_kinds_match_data_preparation():
    """★★★ 격리 사유가 두 곳에서 갈리면 「무엇 때문에 격리됐나」에 답이 둘이 된다."""
    assert set(am.QUARANTINE_FAILURES) == set(dpm.QUARANTINE_KINDS)


def test_public_disclosed_is_not_internal_actual():
    """공개 재무자료가 내부 실적 자리에 앉으면 상세 계산의 근거가 조용히 바뀐다."""
    assert am.ORIGIN_PUBLIC_DISCLOSED in am.DATA_ORIGINS
    assert am.ORIGIN_PUBLIC_DISCLOSED not in am.ORIGINS_FOR_INTERNAL_ACTUAL
    assert am.ORIGINS_FOR_INTERNAL_ACTUAL == (am.ORIGIN_REAL,)


def test_existing_kit_contracts_use_known_origins():
    """★★★ 새 닫힌 목록이 **이미 그 값을 쓰던 파일들**을 설명하지 못하면 목록이 틀린 것이다.

    ⚠️ 이 시험이 없으면 나는 계약 35개가 쓰는 값을 모른 채 목록을 정할 수 있고,
      그러면 「검사하는 곳」과 「값이 있는 곳」의 출처가 갈린다."""
    paths = glob.glob("starter_kits/*/*/contracts/*.contract.json")
    assert paths, "계약 파일을 하나도 찾지 못했다 — 경로가 바뀌었다면 이 시험부터 고칠 것"
    for p in paths:
        with open(p, encoding="utf-8") as f:
            cl = json.load(f).get("classification", {})
        for field in ("data_class", "data_origin"):
            value = cl.get(field)
            if value is None:
                continue
            assert value in am.DATA_ORIGINS, f"{p} 의 {field}={value!r} 를 목록이 모른다"


def test_assert_origin_rejects_free_text():
    am.assert_origin(am.ORIGIN_PUBLIC_DISCLOSED)
    with pytest.raises(am.AcquisitionStateError):
        am.assert_origin("공개자료")
    with pytest.raises(am.AcquisitionStateError):
        am.assert_origin("")


def test_ledger_subject_type_is_reused_not_invented():
    """새 주체 이름을 만들기 전에 있는 것부터 본다 — `external_connection` 이 이미 있었다."""
    from core import decision_ledger
    assert "external_connection" in decision_ledger.SUBJECT_TYPES


def test_state_names_do_not_collide_with_snapshot_states():
    """겹치는 이름이 있으면 로그 한 줄만 보고는 어느 상태기계인지 알 수 없다.

    ⚠️ RAW·QUARANTINED 처럼 **의도적으로 같은 뜻인 것**만 겹쳐야 한다."""
    overlap = set(am.ACQUISITION_STATES) & set(dpm.SNAPSHOT_STATES)
    assert overlap == {"QUARANTINED"}, f"예상 밖의 이름 겹침: {overlap}"
