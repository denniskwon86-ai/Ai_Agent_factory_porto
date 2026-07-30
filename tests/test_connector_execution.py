"""[§7.1 / §7.2] 커넥터 실행 — 계약을 **응답에도** 적용하는가.

`connector_registry` 는 요청만 검사한다. 요청만 검사하면 최소 권한이 절반만 지켜진다:
원천이 요청보다 더 준 것을 그대로 흘리면 계약서는 종이 조각이다.

이 파일이 잠그는 것:
  · 계약에 없는 컬럼을 원천이 줘도 **버리고, 버렸다고 말한다**
  · 상한을 넘겨 줘도 **자르고, 잘랐다고 말한다**
  · 어댑터가 없으면 **빈 결과가 아니라 실패**다
  · 목적(purpose) 없는 조회는 실행되지 않는다
  · 거부된 조회도 감사로그에 남는다
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import connector_execution as cx
from core.connector_registry import ConnectorRegistry


@pytest.fixture()
def reg(tmp_path):
    r = ConnectorRegistry(db_path=str(tmp_path / "connectors.db"))
    r.register("erp", "그룹 ERP", "db", endpoint="postgres://erp",
               auth_ref="ERP_DB_PASSWORD")
    # 계약 먼저, 활성화 나중 — 무엇을 물어볼 수 있는지 정하지 않은 커넥터는 활성화되지 않는다.
    r.add_contract("erp", "wo_status", ["wo_no", "qty", "unit_cost"],
                   required_params=["plant"], max_rows=5,
                   sensitive_fields=["unit_cost"], approved_by="it-admin")
    r.activate("erp", "it-admin")
    return r


@pytest.fixture(autouse=True)
def _clean_adapters():
    for cid in cx.registered_adapters():
        cx.unregister_adapter(cid)
    yield
    for cid in cx.registered_adapters():
        cx.unregister_adapter(cid)


def _adapter(rows, source="erp:view_wo"):
    return lambda q, f, p, lim: {"rows": rows, "source": source}


P = {"plant": "P1"}


# ── 목적과 요청자는 필수다 ───────────────────────────────────────────────────
def test_purpose_is_mandatory(reg):
    """★ §7.2 는 목적을 감사 항목으로 규정한다.

    목적을 옵션으로 두면 아무도 적지 않고, 감사로그에서 "왜"가 영구히 빠진다."""
    cx.register_adapter("erp", _adapter([]))
    with pytest.raises(cx.ConnectorExecutionError, match="purpose"):
        cx.execute("erp", "wo_status", ["wo_no"], actor="u1", purpose="",
                   params=P, registry=reg)


def test_actor_is_mandatory(reg):
    cx.register_adapter("erp", _adapter([]))
    with pytest.raises(cx.ConnectorExecutionError, match="actor"):
        cx.execute("erp", "wo_status", ["wo_no"], actor="", purpose="원가검증",
                   params=P, registry=reg)


# ── 미설정 어댑터는 빈 결과가 아니라 실패다 ──────────────────────────────────
def test_missing_adapter_fails_loudly_not_empty(reg):
    """★★ 빈 결과를 돌려주면 "데이터가 없다"로 읽힌다.

    그건 "조회 자체를 못 했다"와 완전히 다른 사실이고, 그 혼동이 잘못된 계획을 만든다."""
    with pytest.raises(cx.ConnectorExecutionError, match="어댑터가 없습니다"):
        cx.execute("erp", "wo_status", ["wo_no"], actor="u1", purpose="원가검증",
                   params=P, registry=reg)


def test_adapter_exception_surfaces(reg):
    def boom(q, f, p, lim):
        raise RuntimeError("connection refused")
    cx.register_adapter("erp", boom)
    with pytest.raises(cx.ConnectorExecutionError, match="connection refused"):
        cx.execute("erp", "wo_status", ["wo_no"], actor="u1", purpose="원가검증",
                   params=P, registry=reg)


# ── 응답에도 계약을 적용한다 ─────────────────────────────────────────────────
def test_source_returning_extra_columns_is_stripped_and_reported(reg):
    """★★ 계약에 없는 컬럼을 원천이 주는 일은 실제로 일어난다(SELECT * 뷰).

    조용히 지우면 원천 결함이 영원히 안 고쳐지고, 다음 컬럼이 또 샌다."""
    cx.register_adapter("erp", _adapter([
        {"wo_no": "W1", "qty": 10, "operator_ssn": "800101-1", "cost_center": "CC1"},
    ]))
    out = cx.execute("erp", "wo_status", ["wo_no", "qty"], actor="u1",
                     purpose="진도확인", params=P, registry=reg)
    assert out["rows"] == [{"wo_no": "W1", "qty": 10}]
    e = out["enforcement"]
    assert e["dropped_columns"] == ["cost_center", "operator_ssn"]
    assert e["contract_violations_by_source"], "원천 계약 위반을 보고해야 한다"


def test_over_limit_rows_are_truncated_and_reported(reg):
    cx.register_adapter("erp", _adapter([{"wo_no": f"W{i}"} for i in range(12)]))
    out = cx.execute("erp", "wo_status", ["wo_no"], actor="u1", purpose="진도확인",
                     params=P, limit=3, registry=reg)
    e = out["enforcement"]
    assert len(out["rows"]) == 3
    assert e["rows_from_source"] == 12 and e["rows_truncated"] == 9
    assert any("상한 초과" in m for m in e["contract_violations_by_source"])


def test_non_dict_rows_are_refused_not_passed_through(reg):
    """행이 dict 가 아니면 필드 단위 통제가 불가능하다 — 통과시키면 계약이 무의미해진다."""
    cx.register_adapter("erp", _adapter([["W1", 10], {"wo_no": "W2"}]))
    out = cx.execute("erp", "wo_status", ["wo_no"], actor="u1", purpose="진도확인",
                     params=P, registry=reg)
    assert out["rows"] == [{"wo_no": "W2"}]
    assert "<non-dict row>" in out["enforcement"]["dropped_columns"]


def test_clean_source_reports_no_violation(reg):
    cx.register_adapter("erp", _adapter([{"wo_no": "W1"}]))
    out = cx.execute("erp", "wo_status", ["wo_no"], actor="u1", purpose="진도확인",
                     params=P, registry=reg)
    assert out["enforcement"]["contract_violations_by_source"] == []
    assert out["source"] == "erp:view_wo"


# ── 계약 위반 요청은 실행하지 않는다 ─────────────────────────────────────────
def test_contract_violation_does_not_reach_adapter(reg):
    """★ 검증 실패 시 어댑터가 호출되면 최소 권한 통제가 우회된다."""
    called = []
    cx.register_adapter("erp", lambda q, f, p, lim: called.append(1) or {"rows": []})
    out = cx.execute("erp", "wo_status", ["wo_no", "supplier_price"], actor="u1",
                     purpose="원가검증", params=P, registry=reg)
    assert out["executed"] is False and called == []
    assert any("허용되지 않은 필드" in e for e in out["errors"])


def test_missing_required_param_blocks_execution(reg):
    cx.register_adapter("erp", _adapter([{"wo_no": "W1"}]))
    out = cx.execute("erp", "wo_status", ["wo_no"], actor="u1", purpose="진도확인",
                     params={}, registry=reg)
    assert out["executed"] is False
    assert any("필수 파라미터" in e for e in out["errors"])


# ── 프롬프트 주입 경로는 민감 필드를 뺀다 ────────────────────────────────────
def test_for_prompt_removes_sensitive_field_and_says_so(reg):
    cx.register_adapter("erp", _adapter([{"wo_no": "W1", "unit_cost": 1234}]))
    out = cx.fetch_for_prompt("erp", "wo_status", ["wo_no", "unit_cost"], actor="u1",
                              purpose="원가분석", params=P, registry=reg)
    assert out["rows"] == [{"wo_no": "W1"}], "민감 필드가 프롬프트로 흘러선 안 된다"
    assert out["enforcement"]["removed_sensitive"] == ["unit_cost"]
    assert "추정하지 마십시오" in out["prompt_note"]


def test_all_fields_sensitive_fails_instead_of_returning_empty_rows(reg):
    """★★ 필드가 전부 제거되면 `[{}, {}]` 가 된다 — 행은 있는데 값이 없는 결과다.

    그건 데이터 부재로 오독되므로 실행 전에 막는다."""
    cx.register_adapter("erp", _adapter([{"unit_cost": 1234}]))
    with pytest.raises(cx.ConnectorExecutionError, match="민감 필드로 제거"):
        cx.fetch_for_prompt("erp", "wo_status", ["unit_cost"], actor="u1",
                            purpose="원가분석", params=P, registry=reg)


def test_empty_fields_is_refused(reg):
    cx.register_adapter("erp", _adapter([{"wo_no": "W1"}]))
    with pytest.raises(cx.ConnectorExecutionError, match="조회할 필드가 없습니다"):
        cx.execute("erp", "wo_status", [], actor="u1", purpose="진도확인",
                   params=P, registry=reg)


# ── 감사 ─────────────────────────────────────────────────────────────────────
def _audit_lines():
    # conftest 가 감사로그를 tmp 로 격리한다 — 고정 경로를 읽으면 남의 기록을 보고 통과한다.
    from core.enterprise_context import audit
    p = audit._LOG_PATH
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def test_executed_query_is_audited_with_purpose(reg):
    """★ §7.2: 요청자·목적·시각·결과 요약을 남긴다."""
    cx.register_adapter("erp", _adapter([{"wo_no": "W1"}]))
    cx.execute("erp", "wo_status", ["wo_no"], actor="alice", purpose="납기지연 원인분석",
               params=P, registry=reg)
    hits = [l for l in _audit_lines()
            if l.get("event") == "CONNECTOR_QUERY_EXECUTED" and l.get("actor") == "alice"]
    assert hits, "실행된 조회가 감사로그에 없다"
    assert "납기지연 원인분석" in hits[-1].get("detail", "")


def test_denied_query_is_audited(reg):
    """★ 거부된 시도가 침해 시도의 신호다 — 남기지 않으면 탐지할 수 없다."""
    cx.register_adapter("erp", _adapter([]))
    cx.execute("erp", "wo_status", ["secret_col"], actor="bob", purpose="탐색",
               params=P, registry=reg)
    hits = [l for l in _audit_lines()
            if l.get("event") == "CONNECTOR_QUERY_DENIED" and l.get("actor") == "bob"]
    assert hits, "거부된 조회가 감사로그에 없다"


def test_audit_event_types_are_registered_not_degraded(reg):
    """★ 이벤트를 등록하지 않으면 `record()` 가 `UNKNOWN:` 으로 격하해 집계에서 빠진다."""
    from core.enterprise_context import audit
    assert audit.CONNECTOR_QUERY_EXECUTED in audit.EVENTS
    assert audit.CONNECTOR_QUERY_DENIED in audit.EVENTS
