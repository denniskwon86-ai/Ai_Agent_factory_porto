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


def test_missing_log_file_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(tc, "_LOG_PATH", str(tmp_path / "nope.jsonl"))
    agg = tc.aggregate(tc._read_records())
    assert agg["totals"]["calls"] == 0 and agg["by_model"] == {}
