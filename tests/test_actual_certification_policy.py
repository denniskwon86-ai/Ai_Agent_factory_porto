"""[실적 인증 정책] 「우선은 경영관리팀장, 나중에 화면에서 바꾼다」 — 2026-09-11.

이 파일이 지키는 것 다섯.

  ① **코드 기본값이 남는다** — 저장소가 없거나 깨져도 동작이 멈추지 않는다
  ② **부분 저장이 코드의 새 항목을 지우지 않는다** — 통째로 갈아치우지 않는다
  ③ ★★★ **소유 부서 서명은 뺄 수 없다** — 실적 인증의 바닥이다
  ④ **대사 증거는 «있는가» 만 본다** — 형식을 강제하면 그 ERP 전용이 된다
  ⑤ **바꾼 사람과 이유가 이력에 남는다** — 책임자를 바꾸는 일이다

## ⚠️ 운영 파일을 쓰지 않는다

`_PATH` 를 tmp 로 돌린다. 안 돌리면 시험이 운영 정책을 바꾼다.
"""
import json

import pytest

from core import actual_certification_policy as acp


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """★ 운영 정책 파일을 만지지 않는다."""
    path = tmp_path / "policy.json"
    monkeypatch.setattr(acp, "_PATH", str(path))
    assert "WorkSpace" not in str(path), "운영 경로다"
    return path


# ── ① 코드 기본값 ───────────────────────────────────────────────────────────
def test_defaults_work_without_any_stored_file():
    """저장소가 «없어도» 돈다 — 그것이 코드 기본값을 남기는 이유다."""
    eff = acp.effective()
    assert eff["required_reviews"][acp.USE_OPERATIONAL] == [acp.REVIEW_DATA_OWNER]
    assert eff["required_reviews"][acp.USE_MANAGEMENT] == [acp.REVIEW_DATA_OWNER,
                                                           acp.REVIEW_EXECUTIVE]
    assert eff["sources"]["required_reviews"] == acp.SOURCE_CODE


def test_the_initial_executive_title_is_the_requested_one():
    """사용자 지시(2026-09-11): 「우선은 경영관리팀장 승인으로 해 놓고」."""
    assert acp.reviewer_title(acp.REVIEW_EXECUTIVE) == "경영관리팀장"
    assert acp.reviewer_title(acp.REVIEW_DATA_OWNER) == "데이터 소유 부서장"


def test_the_initial_reconciliation_is_sap_based():
    """사용자 지시: 「대사 증거도 SAP ERP 기준 추천안으로 초기 설정」."""
    rec = acp.effective()["reconciliation"]
    assert rec["source_system"] == "SAP ERP"
    assert rec["recommended_fields"], "무엇을 적으면 좋은지 화면이 안내할 수 있어야 한다"
    assert "2026/08" in rec["example"], "회계연도·전기기간이 예시에 있어야 한다"


def test_a_broken_store_falls_back_to_code(isolated):
    """⚠️ 파일이 깨져도 멈추지 않는다 — 정책이 못 읽힌다고 인증이 막히면 안 된다."""
    isolated.write_text("{ 깨진 json", encoding="utf-8")
    assert acp.effective()["required_reviews"][acp.USE_MANAGEMENT] == [
        acp.REVIEW_DATA_OWNER, acp.REVIEW_EXECUTIVE]


# ── ② 부분 저장이 새 항목을 지우지 않는다 ──────────────────────────────────
def test_a_partial_save_does_not_erase_code_additions(isolated):
    """★★★ 저장소 값으로 «통째로 갈아치우면» 코드에 새 항목이 생겼을 때
    저장소를 쓴 회사에서만 그 항목이 사라진다 — 그리고 아무도 모른다."""
    acp.update("reviewer_titles", {acp.REVIEW_EXECUTIVE: "담당임원"},
               actor="a@test.invalid", reason="조직 개편")
    titles = acp.effective()["reviewer_titles"]
    assert titles[acp.REVIEW_EXECUTIVE] == "담당임원", "바꾼 값이 이긴다"
    assert titles[acp.REVIEW_DATA_OWNER] == "데이터 소유 부서장", "안 바꾼 항목은 남는다"


def test_the_source_flips_to_store_after_a_change(isolated):
    """화면이 「내가 바꾼 값이 적용되고 있나」를 볼 수 있어야 한다."""
    assert acp.effective()["sources"]["reviewer_titles"] == acp.SOURCE_CODE
    acp.update("reviewer_titles", {acp.REVIEW_EXECUTIVE: "담당임원"}, actor="a@test.invalid")
    assert acp.effective()["sources"]["reviewer_titles"] == acp.SOURCE_STORE


def test_code_defaults_are_always_returned_for_comparison(isolated):
    """★ 바꾼 뒤에도 «원래 값» 을 함께 준다 — 되돌릴 수 있어야 한다."""
    acp.update("reviewer_titles", {acp.REVIEW_EXECUTIVE: "담당임원"}, actor="a@test.invalid")
    assert acp.effective()["code_defaults"]["reviewer_titles"][acp.REVIEW_EXECUTIVE] == "경영관리팀장"


# ── ③ ★★★ 소유 부서 서명은 뺄 수 없다 ────────────────────────────────────
def test_the_data_owner_signature_cannot_be_removed(isolated):
    """「이 숫자가 우리 부서 것이 맞다」가 없으면 임원은 무엇을 근거로 누르는가."""
    with pytest.raises(acp.ActualCertificationPolicyError) as e:
        acp.update("required_reviews", {acp.USE_MANAGEMENT: [acp.REVIEW_EXECUTIVE]},
                   actor="a@test.invalid")
    assert "실적 인증의 바닥" in str(e.value)


def test_an_empty_review_list_is_refused(isolated):
    """서명이 하나도 없는 인증은 인증이 아니다."""
    with pytest.raises(acp.ActualCertificationPolicyError) as e:
        acp.update("required_reviews", {acp.USE_OPERATIONAL: []}, actor="a@test.invalid")
    assert "인증이 아닙니다" in str(e.value)


def test_an_unknown_review_kind_is_refused(isolated):
    with pytest.raises(acp.ActualCertificationPolicyError):
        acp.update("required_reviews", {acp.USE_MANAGEMENT: ["DATA_OWNER", "AUDITOR"]},
                   actor="a@test.invalid")


def test_an_unknown_use_kind_is_refused(isolated):
    with pytest.raises(acp.ActualCertificationPolicyError):
        acp.update("required_reviews", {"WHATEVER": ["DATA_OWNER"]}, actor="a@test.invalid")


def test_required_reviews_refuses_an_unknown_use_kind():
    with pytest.raises(acp.ActualCertificationPolicyError) as e:
        acp.required_reviews("WHATEVER")
    assert "어디에 쓰는 실적인가" in str(e.value)


def test_adding_the_executive_to_operational_is_allowed(isolated):
    """★ 반대편 — 회사가 더 빡빡하게 가고 싶으면 «막지 않는다»."""
    acp.update("required_reviews",
               {acp.USE_OPERATIONAL: [acp.REVIEW_DATA_OWNER, acp.REVIEW_EXECUTIVE]},
               actor="a@test.invalid")
    assert acp.required_reviews(acp.USE_OPERATIONAL) == [acp.REVIEW_DATA_OWNER,
                                                         acp.REVIEW_EXECUTIVE]


# ── ④ 대사 증거는 «있는가» 만 본다 ─────────────────────────────────────────
def test_empty_reconciliation_evidence_is_refused():
    with pytest.raises(acp.ActualCertificationPolicyError) as e:
        acp.assert_reconciliation_evidence("   ")
    assert "무엇과 맞춰 봤는가" in str(e.value)
    assert "SAP" in str(e.value), "무엇을 적어야 하는지 예시를 줘야 한다"


def test_a_too_short_evidence_is_refused():
    with pytest.raises(acp.ActualCertificationPolicyError) as e:
        acp.assert_reconciliation_evidence("SAP")
    assert "권장 항목" in str(e.value)


def test_the_format_is_not_enforced():
    """★★★ ERP 마다 마감본을 특정하는 방법이 다르다. 형식을 강제하면 그 ERP 전용이 되고,
    안 맞는 회사에서는 «아무 말이나» 적게 된다 — 그러면 검사가 있으나 마나다."""
    for text in ("SAP FI 2026/08 마감 · 계정 4000 대사 일치",
                 "Oracle GL AUG-2026 close batch #8812, AP/AR tie-out ok",
                 "자체 원가시스템 2026년 8월 마감본 · 총계 일치 확인(김OO)"):
        assert acp.assert_reconciliation_evidence(text) == text


def test_the_minimum_length_cannot_be_zero(isolated):
    """0 으로 두면 빈 값이 통과한다 — 그러면 요구하는 의미가 사라진다."""
    with pytest.raises(acp.ActualCertificationPolicyError) as e:
        acp.update("reconciliation", {"min_length": 0}, actor="a@test.invalid")
    assert "요구하는 의미가 사라집니다" in str(e.value)


def test_the_minimum_length_can_be_tightened(isolated):
    acp.update("reconciliation", {"min_length": 40}, actor="a@test.invalid")
    with pytest.raises(acp.ActualCertificationPolicyError):
        acp.assert_reconciliation_evidence("SAP FI 2026/08 마감")


# ── ⑤ 바꾼 사람과 이유가 남는다 ────────────────────────────────────────────
def test_a_change_without_an_actor_is_refused(isolated):
    """「경영관리팀장」을 「담당임원」으로 바꾸는 것은 **책임자를 바꾸는 일**이다."""
    with pytest.raises(acp.ActualCertificationPolicyError) as e:
        acp.update("reviewer_titles", {acp.REVIEW_EXECUTIVE: "담당임원"}, actor="")
    assert "되돌릴 근거가 없습니다" in str(e.value)


def test_the_history_keeps_the_previous_value(isolated):
    """★ 되돌릴 수 있어야 한다 — 이전 값이 없으면 무엇으로 되돌리는가."""
    acp.update("reviewer_titles", {acp.REVIEW_EXECUTIVE: "담당임원"},
               actor="a@test.invalid", reason="조직 개편으로 경영관리팀이 없어짐")
    rows = acp.history()
    assert rows[0]["actor"] == "a@test.invalid"
    assert rows[0]["reason"] == "조직 개편으로 경영관리팀이 없어짐"
    assert rows[0]["after"][acp.REVIEW_EXECUTIVE] == "담당임원"
    assert rows[0]["before"] is None, "첫 변경 전에는 저장소 값이 없었다"


def test_the_history_accumulates(isolated):
    acp.update("reviewer_titles", {acp.REVIEW_EXECUTIVE: "담당임원"}, actor="a@test.invalid")
    acp.update("reviewer_titles", {acp.REVIEW_EXECUTIVE: "CFO"}, actor="b@test.invalid")
    rows = acp.history()
    assert len(rows) == 2
    assert rows[0]["actor"] == "b@test.invalid", "최신이 앞에 온다"
    assert rows[0]["before"][acp.REVIEW_EXECUTIVE] == "담당임원"


def test_an_unknown_key_is_refused(isolated):
    with pytest.raises(acp.ActualCertificationPolicyError):
        acp.update("whatever", {"a": 1}, actor="a@test.invalid")


def test_an_empty_value_is_refused(isolated):
    with pytest.raises(acp.ActualCertificationPolicyError):
        acp.update("reviewer_titles", {}, actor="a@test.invalid")


def test_an_empty_title_is_refused(isolated):
    """자리 이름이 비면 화면이 「누구에게 요청하나」를 그릴 수 없다."""
    with pytest.raises(acp.ActualCertificationPolicyError) as e:
        acp.update("reviewer_titles", {acp.REVIEW_EXECUTIVE: "  "}, actor="a@test.invalid")
    assert "누구에게 요청하나" in str(e.value)


# ── 어휘가 publication 과 «같은가» ─────────────────────────────────────────
def test_the_review_vocabulary_matches_publication():
    """★★★ 두 벌로 만들면 한쪽만 늘어나는 날이 온다."""
    from core import publication as pub

    assert acp.REVIEW_DATA_OWNER == pub.REVIEW_DATA_OWNER
    assert acp.REVIEW_EXECUTIVE == pub.REVIEW_EXECUTIVE
    assert set(acp.REVIEW_KINDS) <= set(pub.REVIEW_TYPES)


def test_policy_is_read_at_call_time(isolated):
    """⚠️ 캐시하면 화면에서 바꿔도 재시작해야 한다."""
    assert acp.required_reviews(acp.USE_OPERATIONAL) == [acp.REVIEW_DATA_OWNER]
    acp.update("required_reviews",
               {acp.USE_OPERATIONAL: [acp.REVIEW_DATA_OWNER, acp.REVIEW_EXECUTIVE]},
               actor="a@test.invalid")
    assert acp.required_reviews(acp.USE_OPERATIONAL) == [acp.REVIEW_DATA_OWNER,
                                                         acp.REVIEW_EXECUTIVE]
