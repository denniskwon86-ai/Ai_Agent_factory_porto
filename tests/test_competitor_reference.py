"""★★★ [ECM E3 §7.3] 경쟁사 참조 — **추정치를 공식 수치처럼 쓰지 않게 한다.**

설계서 §7.3 의 다섯 줄을 코드로 지킨다. 그중 3번("LLM 은 빈 칸을 사실처럼 채우지 않고
'확인 불가'로 제시한다")이 가장 어렵다:

⚠️ 지침만으로는 지켜지지 않는다. 값을 넣을 자리가 하나뿐이면, 모르는 값을 만난 사람(또는 모델)은
  결국 **그럴듯한 숫자**를 넣는다. 그래서 "확인 불가"를 1급 상태로 둔다 — 모른다고 말할 자리가
  있어야 지어내지 않는다.

그리고 근거 5종(`source`·`published_at`·`as_of_date`·`confidence`·`evidence_level`)을 선택이
아니라 **필수**로 둔다. 출처가 붙어 있지 않은 경쟁사 숫자는 몇 달 뒤에 내부 실적과 구분되지
않고, 그 순간 "경쟁사는 우리보다 원가가 낮다"가 근거 없는 사실로 굳는다.
"""
import pytest

from core.enterprise_context.competitor_reference import (CONFIDENCE, EVIDENCE_LEVELS,
                                                          UNVERIFIABLE, CompetitorError,
                                                          CompetitorReferenceStore)
from core.enterprise_context.models import EnterpriseEntity
from core.enterprise_context.repository import EcmRepository

TODAY = "2026-08-03"
OK = dict(source="2025 사업보고서 p.42", published_at="2026-03-20", as_of_date="2025-12-31",
          confidence="HIGH", evidence_level="PUBLIC_FILING")


@pytest.fixture
def repo(tmp_path):
    return EcmRepository(db_path=str(tmp_path / "ecm.db"))


@pytest.fixture
def store(repo):
    return CompetitorReferenceStore(repository=repo)


@pytest.fixture
def comp(store):
    return store.create_competitor("경쟁사 A", evidence_ref="DART 공시 2026-03-20",
                                   industry_code="C24", actor="hikwon")


# ── 생성: 근거 없는 경쟁사 모델은 만들 수 없다 ─────────────────────────────
def test_competitor_needs_evidence_ref(store):
    """★★★ 근거 없는 경쟁사 모델은 추측의 집합이고, 그것이 시장 판단의 기준이 되면 되돌릴 수 없다."""
    with pytest.raises(CompetitorError, match="근거"):
        store.create_competitor("경쟁사", evidence_ref="")


def test_competitor_is_created_as_draft_and_says_what_it_is(store, comp):
    """★★ 만들면 초안이고, **회계·경영의 공식 수치가 아니라는 사실을 응답이 말한다**(§7.3-5)."""
    assert comp["entity_mode"] == "COMPETITOR_REFERENCE" and comp["status"] == "DRAFT"
    assert "공식 수치가 아닙니다" in comp["note"]


def test_general_entity_route_still_refuses_competitor(repo):
    """★★★ **이 모듈이 유일한 문이다.** 일반 생성 경로는 여전히 REAL 만 받는다 —
    VIRTUAL 이 복제로만 만들어지는 것과 같은 구조다."""
    from core.enterprise_context.context import CREATABLE_ENTITY_MODES
    assert CREATABLE_ENTITY_MODES == ("REAL",)


# ── 근거 5종 필수 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("drop", ["source", "published_at", "as_of_date", "confidence",
                                  "evidence_level"])
def test_all_five_evidence_fields_are_required(store, comp, drop):
    """★★★ 하나라도 선택 항목이면 그 필드는 비어 있게 된다(§7.3-2)."""
    kw = dict(OK); kw[drop] = ""
    with pytest.raises(CompetitorError, match="근거|형식"):
        store.record_metric(comp["entity_id"], "단위원가", 2800, **kw)


def test_only_allowed_evidence_kinds(store, comp):
    """★★★ "인터넷 검색"·"업계 소문" 을 받기 시작하면 근거 필드는 장식이 된다.

    §7.3-1 은 공개 공시·공식 발표·계약상 허용 산업데이터·검증된 조사자료만 허용한다."""
    kw = dict(OK); kw["evidence_level"] = "INTERNET_SEARCH"
    with pytest.raises(CompetitorError, match="허용된 근거 종류가 아닙니다"):
        store.record_metric(comp["entity_id"], "단위원가", 2800, **kw)
    assert set(EVIDENCE_LEVELS) == {"PUBLIC_FILING", "OFFICIAL_ANNOUNCEMENT",
                                    "LICENSED_INDUSTRY_DATA", "VERIFIED_RESEARCH"}


def test_confidence_is_a_level_not_a_number(store, comp):
    """★★ 신뢰도를 숫자로 두면 계산에 쓰이기 시작하고, 그러면 추정 불확실성이 확정 계산의
    입력이 된다. 단계로만 둔다."""
    kw = dict(OK); kw["confidence"] = "0.7"
    with pytest.raises(CompetitorError, match="confidence"):
        store.record_metric(comp["entity_id"], "단위원가", 2800, **kw)
    assert CONFIDENCE == ("HIGH", "MEDIUM", "LOW")


def test_bad_date_format_is_refused(store, comp):
    """★ 날짜 형식이 깨지면 나이·신선도 판정이 조용히 무의미해진다."""
    kw = dict(OK); kw["as_of_date"] = "2025년 12월"
    with pytest.raises(CompetitorError, match="YYYY-MM-DD"):
        store.record_metric(comp["entity_id"], "단위원가", 2800, **kw)


def test_metrics_cannot_be_recorded_on_real_entities(store, repo):
    """★★★ 실제 엔터티에 이 표를 쓰기 시작하면 **추정치가 실제 문맥에 섞인다** — §8.1 이
    물리적/논리적으로 분리하라고 한 그 경계다."""
    real = repo.upsert_entity(EnterpriseEntity(entity_mode="REAL", name_ko="LS MnM"))
    with pytest.raises(CompetitorError, match="경쟁사 참조 엔터티에만"):
        store.record_metric(real.entity_id, "단위원가", 2800, **OK)


# ── 확인 불가: 지어내지 않게 하는 장치 ─────────────────────────────────────
def test_empty_value_points_to_unverifiable(store, comp):
    """★★★ 빈 값을 지표로 저장하면 나중에 누군가 그 칸을 채운다 — 명시적 '확인 불가'로 보낸다."""
    with pytest.raises(CompetitorError, match="확인 불가"):
        store.record_metric(comp["entity_id"], "단위원가", None, **OK)


def test_unverifiable_is_a_first_class_state(store, comp):
    """★★★ **§7.3-3 을 코드로 만든 부분.** 모른다고 말할 자리가 있어야 지어내지 않는다."""
    m = store.mark_unverifiable(comp["entity_id"], "단위원가", as_of_date="2025-12-31",
                                note="공시에 원가 분해 없음 · IR 자료에도 미공개", actor="hikwon")
    assert m["state"] == UNVERIFIABLE and m["value"] is None
    assert m["display"] == "확인 불가"


def test_unverifiable_requires_a_reason(store, comp):
    """★★ 사유가 없으면 다음 사람이 같은 조사를 반복한다."""
    with pytest.raises(CompetitorError, match="사유"):
        store.mark_unverifiable(comp["entity_id"], "단위원가", "2025-12-31", note="")


# ── 신선도 ────────────────────────────────────────────────────────────────
def test_old_estimates_are_marked_stale(store, comp):
    """★★★ 오래된 추정치를 최신 실적 옆에 조용히 두면, 읽는 사람은 그것을 현재값으로 본다.

    공시는 보통 연 1회 갱신된다 → 1년이 넘으면 최신 공시가 이미 나왔을 가능성이 크다."""
    store.record_metric(comp["entity_id"], "매출", 1200, **OK)     # as_of 2025-12-31
    fresh = store.list_metrics(comp["entity_id"], today="2026-03-01")[0]
    assert fresh["stale"] is False
    old = store.list_metrics(comp["entity_id"], today="2027-06-01")[0]
    assert old["stale"] is True and "갱신 필요" in old["display"]
    assert old["age_days"] > 365


def test_values_are_never_official(store, comp):
    """★★ 모든 경쟁사 값은 `official=False` 다(§7.3-5). 화면이 그것을 근거로 다르게 그릴 수 있다."""
    store.record_metric(comp["entity_id"], "매출", 1200, **OK)
    assert store.list_metrics(comp["entity_id"])[0]["official"] is False


def test_same_key_and_date_is_a_correction_not_a_duplicate(store, comp):
    """★ 같은 지표·같은 기준일을 다시 넣으면 **정정**이다(중복 행이 쌓이면 어느 것이 맞는지 모른다)."""
    store.record_metric(comp["entity_id"], "매출", 1200, **OK)
    kw = dict(OK); kw["confidence"] = "MEDIUM"
    store.record_metric(comp["entity_id"], "매출", 1250, **kw)
    rows = store.list_metrics(comp["entity_id"], metric_key="매출")
    assert len(rows) == 1 and rows[0]["value"] == 1250 and rows[0]["confidence"] == "MEDIUM"


# ── 커버리지: 확인 불가와 미조사를 구분한다 ────────────────────────────────
def test_coverage_separates_unverifiable_from_not_researched(store, comp):
    """★★★ 앞은 **찾아봤고 없는 것**, 뒤는 **아직 안 본 것**이다. 같게 세면 조사 진척을 알 수 없다."""
    store.record_metric(comp["entity_id"], "매출", 1200, **OK)
    store.mark_unverifiable(comp["entity_id"], "단위원가", "2025-12-31", note="공시 미포함")
    c = store.coverage(comp["entity_id"], expected_keys=["매출", "단위원가", "설비능력"],
                       today=TODAY)
    assert c["estimated"] == ["매출"]
    assert c["unverifiable"] == ["단위원가"]
    assert c["not_researched"] == ["설비능력"]
    assert "둘을 같게 세면" in c["note"]


# ── 내부 실적과 나란히 보기 (§7.3-4) ──────────────────────────────────────
def test_side_by_side_keeps_state_and_evidence(store, comp):
    """★★★ 같은 차트에 둘 수 있으나 **상태를 분리한다**(§7.3-4).

    각 셀에 상태·신뢰도·근거·`official` 이 붙어 나오지 않으면 화면은 두 값을 같게 그린다."""
    store.record_metric(comp["entity_id"], "단위원가", 2800, **OK)
    out = store.compare_with_internal(comp["entity_id"], {"단위원가": 3000},
                                      internal_as_of="2026-06-30", today=TODAY)
    row = out["rows"][0]
    assert row["internal"]["mode_ko"] == "확정 실적" and row["internal"]["official"] is True
    assert row["competitor"]["mode_ko"] == "경쟁사 추정" and row["competitor"]["official"] is False
    assert row["competitor"]["evidence_level_ko"].startswith("공개 공시")
    assert row["competitor"]["confidence_ko"]


def test_side_by_side_does_not_compute_delta(store, comp):
    """★★★ 확정 실적과 추정치의 차이는 **숫자로 보이는 순간 사실처럼 읽힌다** — 그리고 그 차이의
    대부분은 추정 오차일 수 있다. 계산하지 않고, 왜 안 하는지를 행마다 남긴다."""
    store.record_metric(comp["entity_id"], "단위원가", 2800, **OK)
    row = store.compare_with_internal(comp["entity_id"], {"단위원가": 3000})["rows"][0]
    assert row["delta"] is None and "계산하지 않습니다" in row["delta_note"]


def test_side_by_side_warns_about_stale_and_unverifiable(store, comp):
    """★★ 오래된 값·확인 불가 항목이 섞이면 표가 그것을 말해야 한다."""
    store.record_metric(comp["entity_id"], "매출", 1200, **OK)          # as_of 2025-12-31
    store.mark_unverifiable(comp["entity_id"], "단위원가", "2025-12-31", note="미공개")
    out = store.compare_with_internal(comp["entity_id"], {"매출": 1500}, today="2027-06-01")
    joined = " ".join(out["notes"])
    assert "1년을 넘은" in joined and "확인 불가" in joined
    assert "공식 수치가 아닙니다" in joined


def test_missing_internal_value_blocks_superiority_claims(store, comp):
    """★★ 내부 값이 없으면 우열을 말할 수 없다 — 표가 그 사실을 말한다."""
    store.record_metric(comp["entity_id"], "매출", 1200, **OK)
    out = store.compare_with_internal(comp["entity_id"], {}, today=TODAY)
    assert out["rows"][0]["internal"] is None
    assert any("우열을 말할 수 없" in n for n in out["notes"])


# ── 감사 ──────────────────────────────────────────────────────────────────
def test_records_and_unverifiable_are_audited(store, comp, tmp_path, monkeypatch):
    """★★★ 추정치는 시간이 지나면 내부 실적과 구분되지 않으므로 **누가 어떤 근거로 넣었는지**가
    남아야 한다. '확인 불가' 도 남긴다 — 무엇을 찾아봤는지가 조사 진척의 유일한 근거다."""
    import json

    from core.enterprise_context import audit
    log = tmp_path / "a.jsonl"
    monkeypatch.setattr(audit, "_LOG_PATH", str(log), raising=False)
    store.record_metric(comp["entity_id"], "매출", 1200, actor="hikwon", **OK)
    store.mark_unverifiable(comp["entity_id"], "원가", "2025-12-31", note="미공개", actor="hikwon")
    rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    reasons = [r["reason"] for r in rows if r["event"] == "COMPETITOR_REFERENCE_CHANGED"]
    assert "경쟁사 지표 기록" in reasons and "경쟁사 지표 확인 불가 기록" in reasons
