"""[§12.3] 외부 인텔리전스 수집기 — 파일(CSV) · 네트워크(API).

이 파일이 잠그는 것 — 전부 "값을 지어낼 수 없는 구조"에 관한 것이다:
  · **승인된 원천 없이는 아무것도 적재되지 않는다**(등록만으로는 안 된다)
  · **등급은 원천에서 온다** — 호출자가 올려 보낼 수 없다
  · **vintage 없는 행은 건너뛴다** — 오늘 날짜를 자동으로 넣지 않는다(§12.5 재현성)
  · **파싱 실패는 0 이 아니다** — 건너뛰고 이유를 보고한다
  · `dry_run` 이 기본 — 적재 전에 무엇이 빠지는지 먼저 본다
  · **임의 URL 을 호출하지 않는다** — 등록된 `base_url` 만(§12.4 범용 크롤러 금지)
  · **RSS 는 수치로 적재하지 않는다** — 기사에서 숫자를 뽑아 지표로 쓰는 것이 §12.1 금지 경로
  · 호출 실패를 빈 결과로 처리하지 않는다(빈 결과는 "값이 없다"로 읽힌다)
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.external_collector import CollectorError, ExternalCollector
from core.external_intelligence import ExternalIntelligence

CSV_OK = ("indicator,observed_at,value,vintage,unit\n"
          "LME_CU,2026-07-01,9450.5,2026-07-02,USD/t\n"
          "LME_CU,2026-07-02,9502.0,2026-07-03,USD/t\n")


@pytest.fixture()
def env(tmp_path):
    intel = ExternalIntelligence(db_path=str(tmp_path / "ei.db"))
    intel.upsert_indicator("LME_CU", name="LME 전기동 현물", unit="USD/t",
                           required_grade="gold")
    src = intel.register_source("LME 공시", "API", base_url="https://example.invalid/lme",
                                trust_grade="gold")
    return ExternalCollector(intel=intel), intel, src["source_id"]


# ── 원천 없이는 적재되지 않는다 ─────────────────────────────────────────────
def test_unapproved_source_cannot_load_anything(env):
    """★★ 등록만으로는 쓰이지 않는다 — 승인은 "이 출처의 값을 회사 계획에 쓴다"는 결정이다."""
    col, intel, sid = env
    with pytest.raises(CollectorError, match="승인되지 않은 원천"):
        col.collect_csv(CSV_OK, sid, dry_run=False)


def test_missing_source_id_is_refused(env):
    """★ 출처 없는 값은 적재하지 않는다(§12.4)."""
    col, _, _ = env
    with pytest.raises(CollectorError, match="source_id 는 필수"):
        col.collect_csv(CSV_OK, "", dry_run=True)
    with pytest.raises(CollectorError, match="존재하지 않는 원천"):
        col.collect_csv(CSV_OK, "src_nope", dry_run=True)


# ── CSV 적재 ────────────────────────────────────────────────────────────────
def test_dry_run_is_the_default_and_loads_nothing(env):
    """★★ 적재 전에 "무엇이 들어가고 무엇이 왜 빠지는지"를 먼저 본다."""
    col, intel, sid = env
    intel.approve_source(sid, approved_by="cdo@ls")
    out = col.collect_csv(CSV_OK, sid)          # dry_run 기본값

    assert out["dry_run"] is True and out["loaded"] == 2
    assert "[예행]" in out["note"]
    assert intel.list_observations("LME_CU") == [], "예행인데 실제로 적재됐다"


def test_real_run_loads_with_source_grade(env):
    """★★ 등급은 **원천에서** 온다 — 출처보다 값이 더 신뢰될 수는 없다."""
    col, intel, sid = env
    intel.approve_source(sid, approved_by="cdo@ls")
    out = col.collect_csv(CSV_OK, sid, dry_run=False)

    assert out["loaded"] == 2 and out["skipped"] == 0
    obs = intel.list_observations("LME_CU")
    assert len(obs) == 2
    assert all(o["grade"] == "gold" for o in obs), "원천 등급이 반영되지 않았다"
    assert all(o["source_id"] == sid for o in obs)
    # 등급이 gold 이므로 기준계획 용도로 실제 사용 가능해야 한다(§12.2).
    assert intel.resolve_value("LME_CU", purpose="baseline_plan")["allowed"] is True


def test_column_aliases_are_absorbed(env):
    """★ 현업 파일의 머리글은 통일돼 있지 않다 — 매핑을 강요하면 사람들이 시스템 밖으로 나간다."""
    col, intel, sid = env
    intel.approve_source(sid, approved_by="cdo@ls")
    korean = ("지표,기준일,값,발표일,단위\n"
              "LME_CU,2026-07-05,9600,2026-07-06,USD/t\n")
    out = col.collect_csv(korean, sid, dry_run=False)
    assert out["loaded"] == 1, out["skipped_items"]


def test_row_without_vintage_is_skipped_not_backfilled(env):
    """★★ vintage 를 오늘 날짜로 자동 채우면 §12.5 재현성이 **조용히** 깨진다.

    "그 계획이 당시 어떤 발표값을 썼는가"에 영원히 답할 수 없게 된다."""
    col, intel, sid = env
    intel.approve_source(sid, approved_by="cdo@ls")
    out = col.collect_csv("indicator,observed_at,value\nLME_CU,2026-07-01,9450\n",
                          sid, dry_run=False)

    assert out["loaded"] == 0 and out["skipped"] == 1
    assert "vintage" in out["skipped_items"][0]["reason"]
    assert intel.list_observations("LME_CU") == []


def test_unparseable_value_is_skipped_not_zeroed(env):
    """★★ 0 으로 채우면 결손이 계산에 섞여 아무도 눈치채지 못한다 — 결손보다 나쁘다."""
    col, intel, sid = env
    intel.approve_source(sid, approved_by="cdo@ls")
    out = col.collect_csv(
        "indicator,observed_at,value,vintage\n"
        "LME_CU,2026-07-01,,2026-07-02\n"
        "LME_CU,2026-07-02,미정,2026-07-03\n", sid, dry_run=False)

    assert out["loaded"] == 0 and out["skipped"] == 2
    assert all("0 으로 채우지 않습니다" in s["reason"] for s in out["skipped_items"])


def test_partial_failure_does_not_kill_the_batch(env):
    """★ 한 행의 실패가 전체를 죽이지 않는다. 단 **조용히 넘기지도 않는다.**"""
    col, intel, sid = env
    intel.approve_source(sid, approved_by="cdo@ls")
    out = col.collect_csv(
        "indicator,observed_at,value,vintage\n"
        "LME_CU,2026-07-01,9450,2026-07-02\n"
        "NO_SUCH_INDICATOR,2026-07-01,1,2026-07-02\n", sid, dry_run=False)

    assert out["loaded"] == 1 and out["skipped"] == 1
    assert "등록되지 않은 지표" in out["skipped_items"][0]["reason"]
    assert out["skipped_items"][0]["raw"], "건너뛴 원본이 없으면 사람이 고칠 수 없다"


def test_empty_file_is_refused(env):
    col, intel, sid = env
    intel.approve_source(sid, approved_by="cdo@ls")
    with pytest.raises(CollectorError, match="빈 파일"):
        col.collect_csv("", sid)
    with pytest.raises(CollectorError, match="데이터 행이 없습니다"):
        col.collect_csv("indicator,observed_at,value,vintage\n", sid)


# ── 네트워크 수집 ───────────────────────────────────────────────────────────
def test_json_api_is_collected_with_explicit_mapping(env):
    """★ 필드명은 원천마다 다르다 — 추측해서 맞추면 조용히 엉뚱한 열을 값으로 읽는다."""
    col, intel, sid = env
    intel.approve_source(sid, approved_by="cdo@ls")
    body = json.dumps({"data": [
        {"sym": "LME_CU", "d": "2026-07-10", "px": 9700.25, "pub": "2026-07-11"},
    ]})
    out = col.collect_source(sid, dry_run=False, fetcher=lambda url: body,
                             indicator_map={"sym": "indicator", "d": "observed_at",
                                            "px": "value", "pub": "vintage"})
    assert out["loaded"] == 1
    assert intel.list_observations("LME_CU")[0]["value"] == pytest.approx(9700.25)


def test_arbitrary_url_is_refused(env):
    """★★ 임의 URL 호출은 **범용 웹 크롤러**이고 §12.4 가 금지한다."""
    col, intel, sid = env
    intel.approve_source(sid, approved_by="cdo@ls")
    with pytest.raises(CollectorError, match="절대 URL"):
        col.collect_source(sid, path="https://evil.example/steal", fetcher=lambda u: "{}")
    with pytest.raises(CollectorError, match="'\\.\\.'"):
        col.collect_source(sid, path="../../etc/passwd", fetcher=lambda u: "{}")


def test_registered_base_url_is_the_only_target(env):
    """★ 수집기는 등록된 주소만 호출한다 — 상대 경로는 그 아래로만 붙는다."""
    col, intel, sid = env
    intel.approve_source(sid, approved_by="cdo@ls")
    seen = {}

    def _f(url):
        seen["url"] = url
        return "[]"
    col.collect_source(sid, path="daily.json", fetcher=_f)
    assert seen["url"] == "https://example.invalid/lme/daily.json"


def test_rss_is_never_loaded_as_a_number(env):
    """★★ 기사에서 숫자를 뽑아 지표로 쓰는 것이 §12.1 이 금지한 경로다."""
    col, intel, _ = env
    rss = intel.register_source("업계 뉴스", "RSS", base_url="https://example.invalid/rss",
                                trust_grade="bronze")
    intel.approve_source(rss["source_id"], approved_by="cdo@ls")
    with pytest.raises(CollectorError, match="RSS 원천은 관측값으로 적재하지 않습니다"):
        col.collect_source(rss["source_id"], fetcher=lambda u: "<rss/>")


def test_report_source_requires_a_human(env):
    """★ REPORT·WEB 은 사람이 확인해 CSV 로 올린다(§12.4)."""
    col, intel, _ = env
    rep = intel.register_source("증권사 리포트", "REPORT", base_url="https://x.invalid",
                                trust_grade="silver")
    intel.approve_source(rep["source_id"], approved_by="cdo@ls")
    with pytest.raises(CollectorError, match="자동 수집을 지원하지 않습니다"):
        col.collect_source(rep["source_id"], fetcher=lambda u: "x")


def test_fetch_failure_is_not_an_empty_result(env):
    """★★ 호출 실패를 빈 결과로 처리하면 "값이 없다"로 읽힌다 — 완전히 다른 사실이다."""
    col, intel, sid = env
    intel.approve_source(sid, approved_by="cdo@ls")

    def _boom(url):
        raise OSError("connection refused")
    with pytest.raises(CollectorError, match="원천을 호출할 수 없습니다"):
        col.collect_source(sid, fetcher=_boom)


def test_missing_base_url_is_refused(env):
    col, intel, _ = env
    s = intel.register_source("주소 없음", "API", trust_grade="silver")
    intel.approve_source(s["source_id"], approved_by="cdo@ls")
    with pytest.raises(CollectorError, match="base_url 이 없습니다"):
        col.collect_source(s["source_id"], fetcher=lambda u: "{}")


# ── 진단 ────────────────────────────────────────────────────────────────────
def test_collectable_says_when_there_is_nothing_to_collect(env):
    """★★ 2026-07-29 에 수집기를 안 만든 이유("승인 원천 0")를 숨기지 않고 답한다.

    수집기가 있는데 아무것도 안 들어오는 이유를 추측하게 두면, 다음 사람은 "수집기가
    고장났다"로 결론짓는다."""
    col, intel, sid = env
    out = col.collectable()
    assert out["ready"] is False and out["approved_total"] == 0
    assert "승인된 외부 원천이 없습니다" in out["note"]

    intel.approve_source(sid, approved_by="cdo@ls")
    out2 = col.collectable()
    assert out2["ready"] is True and out2["auto_collectable"] == 1
    assert out2["sources"][0]["auto"] is True
