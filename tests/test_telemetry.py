"""운영 계기판 텔레메트리 집계 단위 테스트 — LLM 0콜, 서버 무기동(모킹 jsonl)."""
import json
import importlib

import api.routes.telemetry_control as tc


def _write_log(tmp_path, records, monkeypatch, partial_last=False):
    p = tmp_path / "llm_call_log.jsonl"
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    text = "\n".join(lines) + "\n"
    if partial_last:
        text += '{"ts": "2026-07-20", "used": "grok'  # 일부러 깨진(닫히지 않은) 부분 기록 줄
    p.write_text(text, encoding="utf-8")
    monkeypatch.setattr(tc, "_LOG_PATH", str(p))
    return p


def _rec(**kw):
    base = dict(ts="2026-07-20T10:00:00", project="P1", stage="PLANNING",
                tier="flash_router", requested_tier="flash_router", downgraded=False,
                output_mode="json", retry_count=0, attempts=["gemini-2.5-flash"],
                used="gemini-2.5-flash", ok=True, duration_s=1.0)
    base.update(kw)
    return base


def test_aggregate_by_model_is_primary_axis():
    recs = [
        _rec(used="gemini-2.5-pro", attempts=["gemini-2.5-pro"]),
        _rec(used="llama-3.3-70b-versatile", attempts=["gemini-2.5-pro", "grok-2-latest", "llama-3.3-70b-versatile"]),
        _rec(used="gemini-2.5-flash"),
    ]
    agg = tc.aggregate(recs)
    # 비Gemini 모델도 used 로 정확히 집계 (이분법에 안 묻힘)
    assert agg["by_model"]["gemini-2.5-pro"] == 1
    assert agg["by_model"]["llama-3.3-70b-versatile"] == 1
    assert agg["by_model"]["gemini-2.5-flash"] == 1
    assert agg["totals"]["calls"] == 3


def test_fallback_and_downgrade_counted():
    recs = [
        _rec(attempts=["gemini-2.5-pro", "grok-2-latest"]),          # 폴백(2회 시도)
        _rec(requested_tier="pro_router", downgraded=True),          # 브레이커 강등
        _rec(),                                                      # 정상 1회
    ]
    agg = tc.aggregate(recs)
    assert agg["totals"]["fallback_calls"] == 1
    assert agg["totals"]["downgraded_calls"] == 1
    assert agg["by_requested_tier"]["pro_router"]["downgraded"] == 1


def test_by_stage_avg_duration():
    recs = [_rec(stage="RFP", duration_s=2.0), _rec(stage="RFP", duration_s=4.0)]
    agg = tc.aggregate(recs)
    assert agg["by_stage"]["RFP"]["calls"] == 2
    assert agg["by_stage"]["RFP"]["avg_duration_s"] == 3.0


def test_read_records_tolerates_partial_last_line(tmp_path, monkeypatch):
    _write_log(tmp_path, [_rec(), _rec(used="grok-2-latest")], monkeypatch, partial_last=True)
    recs = tc._read_records()
    # 깨진 마지막 줄은 skip, 정상 2건만
    assert len(recs) == 2


def test_read_records_project_filter(tmp_path, monkeypatch):
    _write_log(tmp_path, [_rec(project="A"), _rec(project="B"), _rec(project="A")], monkeypatch)
    assert len(tc._read_records("A")) == 2
    assert len(tc._read_records()) == 3


def test_read_records_project_filter_accepts_internal_project_id(tmp_path, monkeypatch):
    """프로젝트 관리 화면은 표시명이 아니라 내부 ID로 실적을 조회한다."""
    _write_log(tmp_path, [
        _rec(project="월간 제조원가 분석 보고서", project_id="prj_cost"),
        _rec(project="전사 시뮬레이션", project_id="prj_sim"),
    ], monkeypatch)
    rows = tc._read_records("prj_cost")
    assert len(rows) == 1
    assert rows[0]["project"] == "월간 제조원가 분석 보고서"


def test_missing_log_file_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(tc, "_LOG_PATH", str(tmp_path / "nope.jsonl"))
    agg = tc.aggregate(tc._read_records())
    assert agg["totals"]["calls"] == 0 and agg["by_model"] == {}


# ══════════════════════════════════════════════════════════════════════════
# 비용 산정 + 부서 스코프 (2026-07-28, P0 「비용 관측」 / 마스터 명세서 §10.1·§10.3)
#
# 가장 중요한 계약: **모르는 비용을 0 으로 두지 않는다.** 0 으로 두면 "이 프로젝트는
# 공짜였다"는 거짓이 되고, 임의 추정치를 넣으면 근거 없는 숫자가 경영 판단에 들어간다.
# ══════════════════════════════════════════════════════════════════════════
import pytest

import config
from api.deps import Principal
from core.llm_cost import estimate_cost_usd, is_paid_model, provider_of
from core.org_directory import AccessScope


def _p(**kw):
    return Principal(user_id=kw.pop("user_id", "u"), scope=AccessScope(**kw))


# ── 단가 판정 ────────────────────────────────────────────────────────────
def test_free_tier_direct_calls_cost_zero():
    """무료 티어 직접 호출은 과금 0 이 '사실'이다(추정이 아니다)."""
    for m in ("gemini-2.5-pro", "gemini-2.5-flash", "grok-2-latest",
              "llama-3.3-70b-versatile", "llama3.1-8b"):
        cost, basis = estimate_cost_usd(m, 1_000_000, 1_000_000)
        assert (cost, basis) == (0.0, "free_tier"), m
        assert not is_paid_model(m)


def test_cache_hit_is_free_because_no_call_happened():
    assert estimate_cost_usd("cache_hit", 0, 0) == (0.0, "cache_hit")


def test_unpriced_paid_model_returns_none_not_zero():
    """★ 핵심 계약 — 단가를 모르는 유료 모델은 None 이어야 한다."""
    cost, basis = estimate_cost_usd("openai/some-unregistered-model", 1000, 1000)
    assert cost is None, "0 으로 두면 '공짜였다'는 거짓이 된다"
    assert basis == "unpriced"


def test_free_slug_suffix_is_not_paid():
    """OpenRouter `:free` 슬러그는 유료 마커가 있어도 무료다."""
    assert not is_paid_model("google/gemini-2.5-flash:free")
    assert estimate_cost_usd("google/gemini-2.5-flash:free", 1000, 1000)[1] == "free_tier"


def test_registered_paid_model_computes_from_table():
    """입력 $0.30/1M × 100만 + 출력 $2.50/1M × 50만 = $1.55 (OpenRouter 공식 단가)."""
    cost, basis = estimate_cost_usd("google/gemini-2.5-flash", 1_000_000, 500_000)
    assert cost == pytest.approx(1.55)
    assert basis == "paid"


def test_partial_price_entry_is_marked_as_underestimate(monkeypatch):
    """★ 단가 일부만 아는 것을 완전한 산정으로 표시하면 안 된다(과소 추정임을 남긴다)."""
    monkeypatch.setitem(config.LLM_PRICE_PER_MTOK, "openai/half", {"in": None, "out": 2.0})
    cost, basis = estimate_cost_usd("openai/half", 1_000_000, 1_000_000)
    assert cost == pytest.approx(2.0), "아는 부분(출력)만 합산한다"
    assert basis == "paid_partial"


def test_full_price_table_entry_yields_paid(monkeypatch):
    monkeypatch.setitem(config.LLM_PRICE_PER_MTOK, "openai/x", {"in": 1.0, "out": 3.0})
    cost, basis = estimate_cost_usd("openai/x", 1_000_000, 1_000_000)
    assert cost == pytest.approx(4.0) and basis == "paid"


def test_provider_derived_from_engine_tiers():
    assert provider_of("gemini-2.5-pro") == "gemini"
    assert provider_of("llama-3.3-70b-versatile") == "groq"
    assert provider_of("llama-3.3-70b") == "cerebras"
    assert provider_of("grok-2-latest") == "xai"
    assert provider_of("google/gemini-2.5-flash") == "openrouter"
    assert provider_of("gemini-2.0-flash") == "gemini", "변종 풀은 ENGINE_TIERS 에 없어도 인식"
    assert provider_of("") == ""


# ── 집계: 무료 0 과 '모름' 을 섞지 않는다 ────────────────────────────────
def test_cost_aggregate_separates_unpriced_from_free():
    recs = [
        _rec(used="gemini-2.5-pro", cost_estimate_usd=0.0, cost_basis="free_tier", provider="gemini"),
        _rec(used="google/gemini-2.5-flash", cost_estimate_usd=1.25,
             cost_basis="paid_partial", provider="openrouter"),
        _rec(used="openai/ghost", cost_estimate_usd=None, cost_basis="unpriced", provider="openrouter"),
    ]
    agg = tc.aggregate(recs)
    t = agg["totals"]
    assert t["cost_usd"] == pytest.approx(1.25)
    assert t["priced_calls"] == 2 and t["unpriced_calls"] == 1
    assert t["cost_complete"] is False, "미산정이 있으면 총액은 하한이라고 표시해야 한다"
    assert t["cost_partial_calls"] == 1
    assert agg["by_cost_basis"]["free_tier"]["calls"] == 1
    assert agg["by_cost_basis"]["unpriced"]["cost_usd"] == 0.0
    assert agg["by_provider"]["openrouter"]["calls"] == 2


def test_cost_complete_when_all_priced():
    recs = [_rec(cost_estimate_usd=0.0, cost_basis="free_tier")]
    assert tc.aggregate(recs)["totals"]["cost_complete"] is True


# ── 소급 산정: 단가표를 채우면 과거 로그도 살아난다 ──────────────────────
def test_legacy_records_are_backfilled_on_read(tmp_path, monkeypatch):
    """★ 구 로그엔 cost 필드가 없다. used/토큰이 남아 있으므로 읽는 시점에 산정한다."""
    _write_log(tmp_path, [
        _rec(used="gemini-2.5-pro", input_tokens=100, output_tokens=200),
        _rec(used="google/gemini-2.5-flash", input_tokens=0, output_tokens=1_000_000),
    ], monkeypatch)
    recs = tc._read_records()
    assert recs[0]["cost_basis"] == "free_tier" and recs[0]["backfilled"] is True
    assert recs[0]["provider"] == "gemini"
    assert recs[1]["cost_estimate_usd"] == pytest.approx(2.50)


def test_backfill_does_not_overwrite_recorded_cost(tmp_path, monkeypatch):
    """게이트웨이가 이미 산정한 값은 건드리지 않는다(단가표가 바뀌어도 기록이 진실)."""
    _write_log(tmp_path, [_rec(used="google/gemini-2.5-flash", output_tokens=1_000_000,
                               cost_estimate_usd=9.99, cost_basis="paid")], monkeypatch)
    r = tc._read_records()[0]
    assert r["cost_estimate_usd"] == 9.99 and r["cost_basis"] == "paid"
    assert "backfilled" not in r


# ── 부서 스코프 (Phase 4 단기 게이트의 정상화) ───────────────────────────
def test_unrestricted_sees_everything():
    """조직 미도입(기본 ORG_ENFORCE=False)에서는 종전과 동일하게 전량."""
    recs = [_rec(owner_dept_id="sales"), _rec(owner_dept_id=""), _rec(owner_dept_id="quality")]
    s = tc.apply_scope(recs, _p(unrestricted=True))
    assert len(s["records"]) == 3 and s["scope"] == "enterprise"


def test_executive_sees_everything():
    recs = [_rec(owner_dept_id="sales"), _rec(owner_dept_id="quality")]
    s = tc.apply_scope(recs, _p(unrestricted=False, can_run_enterprise=True))
    assert len(s["records"]) == 2


def test_dept_member_sees_only_own_dept():
    recs = [_rec(owner_dept_id="sales"), _rec(owner_dept_id="quality")]
    s = tc.apply_scope(recs, _p(unrestricted=False, readable_dept_ids=frozenset({"quality"})))
    assert [r["owner_dept_id"] for r in s["records"]] == ["quality"]
    assert s["excluded_other_dept"] == 1


def test_unattributed_records_excluded_but_counted():
    """★ 귀속 불가는 남의 부서일 수 있으니 제외하되, 조용히 빼지 않고 건수를 밝힌다."""
    recs = [_rec(owner_dept_id=""), _rec(owner_dept_id="quality")]
    s = tc.apply_scope(recs, _p(unrestricted=False, readable_dept_ids=frozenset({"quality"})))
    assert len(s["records"]) == 1
    assert s["excluded_unattributed"] == 1, "집계가 왜 작아졌는지 사용자가 알 수 있어야 한다"


def test_no_readable_dept_sees_nothing():
    recs = [_rec(owner_dept_id="sales")]
    s = tc.apply_scope(recs, _p(unrestricted=False, readable_dept_ids=frozenset()))
    assert s["records"] == [] and s["excluded_other_dept"] == 1


# ══════════════════════════════════════════════════════════════════════════
# ★ 배선 — 게이트웨이가 실제로 표준 필드를 남기는가 (회귀 방지)
#
# Phase 5 에서 "필터는 만들었는데 채워주는 쪽이 없었다"에 당했다. 같은 유형을 잠근다:
# 집계가 `owner_dept_id`/`cost_basis` 를 읽는데 기록부가 안 실으면, 오류 없이 부서 스코프가
# 전부 '귀속 불가'가 되고 비용이 영원히 미산정으로 남는다.
# ══════════════════════════════════════════════════════════════════════════
def test_gateway_logs_identity_and_cost_fields(tmp_path, monkeypatch):
    import core.llm_gateway as gw

    monkeypatch.chdir(tmp_path)
    # ★ [2026-08-05] 작업공간 경로가 절대경로로 고정됐다(`core/paths.py`). cwd 만 옮기면
    #   더 이상 격리되지 않으므로 **격리 지점을 함께 돌린다.** 이 한 줄이 없으면 테스트가
    #   제품 `projects/` 에 프로젝트를 만든다.
    import core.paths as _paths
    monkeypatch.setattr(_paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(gw, "_LLM_CALL_LOG_PATH", str(tmp_path / "log.jsonl"))

    class _S:
        project_name = "품질관리 시스템"
        workspace_root = "./projects/QUAL_APP"
        owner_dept_id = "quality"
        current_stage = "BACKEND"

    gw._log_llm_call(_S(), "pro_router", "code", 0, ["gemini-2.5-pro", "google/gemini-2.5-flash"],
                     True, 3.2, input_tokens=1000, output_tokens=1_000_000)

    rec = json.loads((tmp_path / "log.jsonl").read_text(encoding="utf-8").strip())
    # 식별 — 부서 스코프의 근거. 상태 모델 변경 없이 workspace_root 에서 유도된다.
    assert rec["project_id"] == "QUAL_APP", "부서/프로젝트 귀속의 기반이 비면 스코프가 전부 막힌다"
    assert rec["owner_dept_id"] == "quality"
    assert rec["project"] == "품질관리 시스템", "기존 집계 축(project_name)은 유지"
    # 비용 — 실제 응답 모델(체인의 마지막)로 산정한다. 1순위가 아니라 착지한 모델이 과금된다.
    assert rec["used"] == "google/gemini-2.5-flash"
    assert rec["provider"] == "openrouter"
    # 입력 1,000 × $0.30/1M + 출력 1,000,000 × $2.50/1M
    assert rec["cost_estimate_usd"] == pytest.approx(2.5003)
    assert rec["cost_basis"] == "paid"


def test_gateway_log_survives_stateless_call(tmp_path, monkeypatch):
    """workspace_root/owner_dept_id 가 없는 상태(vision_router 등)에서도 죽지 않는다."""
    import core.llm_gateway as gw

    monkeypatch.chdir(tmp_path)
    # ★ [2026-08-05] 작업공간 경로가 절대경로로 고정됐다(`core/paths.py`). cwd 만 옮기면
    #   더 이상 격리되지 않으므로 **격리 지점을 함께 돌린다.** 이 한 줄이 없으면 테스트가
    #   제품 `projects/` 에 프로젝트를 만든다.
    import core.paths as _paths
    monkeypatch.setattr(_paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(gw, "_LLM_CALL_LOG_PATH", str(tmp_path / "log.jsonl"))
    gw._log_llm_call(object(), "vision_router", "json", 0, ["cache_hit"], True, 0.0)
    rec = json.loads((tmp_path / "log.jsonl").read_text(encoding="utf-8").strip())
    assert rec["project_id"] == "" and rec["owner_dept_id"] == ""
    assert rec["cost_basis"] == "cache_hit" and rec["cost_estimate_usd"] == 0.0
