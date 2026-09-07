"""[DAO-12] 준비도 ↔ 수집 다리 — **「준비되지 않음」에서 끝내지 않되, 거짓말도 하지 않는다.**

이 파일이 지키는 것 넷.

  ① 준비도 **상태를 바꾸지 않는다** — 제안만 한다.
  ② 이미 수집한 것이 있어도 **「준비됨」이 아니다.** 남은 단계를 이름으로 적는다.
  ③ 「받아온 것이 틀렸다」(품질 실패)에는 새 원천을 권하지 않는다 — 원인을 덮는다.
  ④ 순수하다 — 넘겨받은 값만 본다.
"""
import json

import pytest

from core.external_intelligence import readiness_bridge as RB
from core.external_intelligence import providers as P
from core.external_intelligence.providers import ecos as _e  # noqa: F401  (등록)
from core.external_intelligence.providers import opendart as _o  # noqa: F401

DESC = P.provider_registry.descriptors()
ENV = {"AFS_ECOS_API_KEY": "e" * 24}


def _row(key, state):
    return {"dataset_contract_key": key, "state": state}


# ── ① 준비도를 조작하지 않는다 ──────────────────────────────────────────────
def test_ready_datasets_get_no_suggestion():
    """★ 「더 좋은 원천이 있습니다」는 이 자리의 질문이 아니다."""
    assert RB.suggest([_row("FIN-01", "READY")], descriptors=DESC) == []


@pytest.mark.parametrize("state", ["READY", "STALE", "APPROVAL_PENDING", "DATA_AVAILABLE"])
def test_states_past_source_selection_are_left_alone(state):
    assert RB.suggest([_row("EXT-01", state)], descriptors=DESC) == []


def test_the_suggestion_carries_the_readiness_state_unchanged():
    """상태를 덮지 않는다 — 화면이 둘을 나란히 보여 줘야 한다."""
    out = RB.suggest([_row("EXT-01", "NOT_CONFIGURED")], descriptors=DESC)
    assert out[0].readiness_state == "NOT_CONFIGURED"
    assert out[0].as_dict()["readiness_state"] == "NOT_CONFIGURED"


def test_no_module_level_state_names_are_invented():
    """새 준비도 상태를 만들지 않는다 — `readiness.DATASET_STATES` 가 정본이다."""
    from core.data_preparation import readiness as R
    for state in RB.SUGGESTIBLE_STATES:
        assert state in R.DATASET_STATES, state


# ── ② 수집했어도 「준비됨」이 아니다 ────────────────────────────────────────
def test_collected_rows_do_not_mean_ready():
    """★★★ 받아 온 것과 인증되어 결속된 것은 다르다 — 그 차이가 이 시스템의 전부다."""
    out = RB.suggest([_row("PUB-01", "NOT_CONFIGURED")], descriptors=DESC,
                     collected_by_contract={"PUB-01": 40})
    s = out[0]
    assert s.gap == RB.GAP_COLLECTED_NOT_BOUND
    assert s.collected_rows == 40
    assert s.readiness_state == "NOT_CONFIGURED"      # 여전히 준비 안 됨
    assert "준비도는 아직 오르지 않았습니다" in RB.GAP_LABELS[s.gap]


def test_remaining_steps_are_named_not_summarised():
    """⚠️ 「거의 다 됐습니다」로 줄이면 사람은 기다리기만 한다."""
    out = RB.suggest([_row("PUB-01", "NOT_CONFIGURED")], descriptors=DESC,
                     collected_by_contract={"PUB-01": 40})
    steps = out[0].remaining_steps
    assert len(steps) == 4
    joined = " ".join(steps)
    assert "인증" in joined and "결속" in joined and "준비도 재평가" in joined


def test_the_summary_says_collection_does_not_raise_readiness():
    out = RB.suggest([_row("PUB-01", "NOT_CONFIGURED")], descriptors=DESC,
                     collected_by_contract={"PUB-01": 40})
    summary = RB.summarise(out)
    assert summary["collected_but_not_bound"] == 1
    assert "자동으로 올리지 않습니다" in summary["notice"]


def test_zero_collected_rows_is_not_collected():
    """0행을 「수집됨」으로 세면 빈 결과가 진척으로 보인다."""
    out = RB.suggest([_row("PUB-01", "NOT_CONFIGURED")], descriptors=DESC,
                     collected_by_contract={"PUB-01": 0})
    assert out[0].gap == RB.GAP_NO_SOURCE


# ── ③ 품질 실패에는 새 원천을 권하지 않는다 ─────────────────────────────────
@pytest.mark.parametrize("state", ["QUALITY_FAILED", "RECONCILIATION_FAILED",
                                   "UNAVAILABLE", "LEGACY_OWNERSHIP_QUARANTINED"])
def test_broken_data_is_not_answered_with_a_new_source(state):
    """★★★ 「받아온 것이 틀렸다」에 새 원천을 권하면 **원인을 덮는다.**"""
    assert RB.suggest([_row("EXT-01", state)], descriptors=DESC) == []
    assert state not in RB.SUGGESTIBLE_STATES


# ── 원천 후보 ───────────────────────────────────────────────────────────────
def test_only_providers_that_target_the_contract_are_offered():
    ext = RB.suggest([_row("EXT-01", "NOT_CONFIGURED")], descriptors=DESC)[0]
    pub = RB.suggest([_row("PUB-01", "NOT_CONFIGURED")], descriptors=DESC)[0]
    assert [o.provider_id for o in ext.options] == ["ECOS"]
    assert [o.provider_id for o in pub.options] == ["OPENDART"]


def test_a_contract_with_no_provider_says_so():
    """빈 목록만 주면 화면이 「왜 아무것도 없나」에 답할 수 없다."""
    out = RB.suggest([_row("MFG-02", "NOT_CONFIGURED")], descriptors=DESC)[0]
    assert out.gap == RB.GAP_NO_PROVIDER
    assert out.options == ()
    assert "등록되지 않았습니다" in RB.GAP_LABELS[out.gap]
    assert out.actionable is False


def test_known_limits_travel_with_the_option():
    """★★★ 제안에서 한계를 떼면 고르는 순간 사라진다."""
    out = RB.suggest([_row("PUB-01", "NOT_CONFIGURED")], descriptors=DESC)[0]
    limits = out.options[0].known_limits
    assert limits
    assert any("대체하지 않습니다" in x for x in limits)
    assert out.as_dict()["options"][0]["known_limits"] == list(limits)


def test_missing_credentials_are_visible_not_hidden():
    """자격증명이 없는 원천을 숨기면 「왜 못 쓰나」에 답할 수 없다."""
    out = RB.suggest([_row("EXT-01", "NOT_CONFIGURED"), _row("PUB-01", "NOT_CONFIGURED")],
                     descriptors=DESC, env=ENV)
    by_key = {s.dataset_contract_key: s for s in out}
    assert by_key["EXT-01"].options[0].credential_configured is True
    assert by_key["PUB-01"].options[0].credential_configured is False
    #: 숨기지 않는다 — 목록에는 있고 표시만 다르다.
    assert by_key["PUB-01"].options


def test_actionable_items_come_first():
    rows = [_row("MFG-02", "NOT_CONFIGURED"), _row("EXT-01", "NOT_CONFIGURED")]
    out = RB.suggest(rows, descriptors=DESC, env=ENV)
    assert out[0].dataset_contract_key == "EXT-01"      # 손댈 수 있는 것이 앞
    assert out[0].actionable is True and out[-1].actionable is False


def test_collected_but_unbound_is_actionable():
    """할 일이 있다 — 편입·인증·결속이다."""
    out = RB.suggest([_row("PUB-01", "NOT_CONFIGURED")], descriptors=DESC,
                     collected_by_contract={"PUB-01": 40})
    assert out[0].actionable is True


# ── ④ 순수성 ────────────────────────────────────────────────────────────────
def test_the_module_touches_no_storage():
    """`readiness.py` 가 저장소를 모르는 것과 같은 이유다 — 같은 입력이면 같은 제안."""
    import inspect
    source = inspect.getsource(RB)
    for banned in ("sqlite3", "acquisition_store", "staged_rows", "import requests",
                   "datetime.now"):
        assert banned not in source, banned


def test_same_input_gives_the_same_suggestion():
    rows = [_row("EXT-01", "NOT_CONFIGURED"), _row("PUB-01", "NOT_CONFIGURED")]
    first = [s.as_dict() for s in RB.suggest(rows, descriptors=DESC, env=ENV)]
    second = [s.as_dict() for s in RB.suggest(rows, descriptors=DESC, env=ENV)]
    assert first == second


def test_output_is_json_serialisable():
    out = RB.suggest([_row("PUB-01", "NOT_CONFIGURED")], descriptors=DESC,
                     collected_by_contract={"PUB-01": 40}, env=ENV)
    json.dumps([s.as_dict() for s in out], ensure_ascii=False)
    json.dumps(RB.summarise(out), ensure_ascii=False)


def test_empty_input_is_empty_output_not_an_error():
    assert RB.suggest([], descriptors=DESC) == []
    assert RB.summarise([])["total"] == 0


def test_rows_without_a_contract_key_are_skipped():
    assert RB.suggest([{"state": "NOT_CONFIGURED"}], descriptors=DESC) == []


# ── 어휘 ────────────────────────────────────────────────────────────────────
def test_gap_codes_are_a_closed_list_with_labels():
    codes = {RB.GAP_NO_SOURCE, RB.GAP_COLLECTED_NOT_BOUND, RB.GAP_NO_PROVIDER}
    assert set(RB.GAP_LABELS) == codes
    assert all(RB.GAP_LABELS[c] for c in codes)
