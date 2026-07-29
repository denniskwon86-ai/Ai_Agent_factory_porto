"""[M4] 실적·계획 파일 등록 — **조용히 틀리기 가장 쉬운 경로.**

엑셀 한 장의 오타 하나가 그대로 경영 보고서에 들어가고, 아무 오류도 나지 않는다.
그래서 이 모듈이 지키는 것은 "얼마나 잘 읽는가"가 아니라 **"틀린 것을 들여보내지 않는가"** 다.

핵심 계약: **한 행이라도 문제가 있으면 전부 거부한다.** 부분 저장은
"127행 중 119행 저장됨"이라는 **맞는 것도 틀린 것도 아닌 상태**를 남긴다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import planning_import as imp
from core.planning_model import ACTUAL, PLAN, PlanningError, PlanningStore


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = PlanningStore(db_path=str(tmp_path / "planning.db"))
    monkeypatch.setattr("core.planning_model.planning_store", s)
    monkeypatch.setattr(imp, "planning_store", s)
    s.upsert_account("4000", "매출", "REVENUE", sign=1)
    s.upsert_account("5000", "원가", "COGS", sign=-1)
    return s


def _row(**kw):
    base = {"org_id": "MNM_BATTERY", "account_code": "4000", "period": "2027",
            "value_kind": "PLAN", "amount": "1000"}
    base.update(kw)
    return base


# ── all-or-nothing ───────────────────────────────────────────────────────────
def test_one_bad_row_rejects_everything(store):
    """★★ 부분 저장은 '맞는 것도 틀린 것도 아닌' 데이터를 남긴다."""
    rows = [_row(), _row(account_code="9999")]        # 두 번째는 미등록 계정
    r = imp.import_rows(rows, commit=True)
    assert r["ok"] is False and r["committed"] is False
    assert store.list_facts(org_id="MNM_BATTERY") == [], "일부라도 저장되면 안 된다"


def test_dry_run_is_the_default(store):
    """★ 무엇이 들어갈지 먼저 보여준다 — '일단 넣고 고치자'는 원본을 알 수 없게 만든다."""
    r = imp.import_rows([_row()])
    assert r["ok"] is True and r["committed"] is False
    assert store.list_facts(org_id="MNM_BATTERY") == []
    assert "미리보기" in r["note"]


def test_commit_writes(store):
    r = imp.import_rows([_row(), _row(account_code="5000", amount="600")], commit=True)
    assert r["committed"] is True and r["written"] == 2
    assert len(store.list_facts(org_id="MNM_BATTERY")) == 2


# ── 검증 규칙 ────────────────────────────────────────────────────────────────
def test_unknown_account_is_not_auto_created(store):
    """★★ 오타가 새 계정이 되면 손익이 **조용히 갈라진다**."""
    r = imp.validate_rows([_row(account_code="4OOO")])   # 0 대신 O
    assert r["ok"] is False
    assert "등록되지 않은 계정" in r["errors"][0]["why"]


def test_missing_value_kind_is_an_error_not_a_default(store):
    """§11.3 — 빈 칸을 PLAN 으로 채우면 '실적처럼 보이는 계획'이 생긴다."""
    r = imp.validate_rows([_row(value_kind="")])
    assert r["ok"] is False and "필수 열 누락" in r["errors"][0]["why"]


def test_invalid_value_kind_is_rejected(store):
    r = imp.validate_rows([_row(value_kind="실적")])
    assert r["ok"] is False and "value_kind" in r["errors"][0]["why"]


def test_duplicate_rows_are_rejected(store):
    """★ 같은 (조직·계정·기간·종류)가 두 번이면 **어느 값이 맞는지 알 수 없다**."""
    r = imp.validate_rows([_row(amount="1000"), _row(amount="1200")])
    assert r["ok"] is False and "중복 행" in r["errors"][0]["why"]


def test_unparseable_amount_is_error_not_zero(store):
    """★★ 해석 불가를 0 으로 바꾸면 그 0 이 계획 숫자가 된다."""
    r = imp.validate_rows([_row(amount="약 1000")])
    assert r["ok"] is False and "숫자로 해석할 수 없습니다" in r["errors"][0]["why"]


def test_thousand_separator_and_accounting_negative(store):
    """엑셀에서 흔한 표기는 받아들인다 — 형식 때문에 업무가 막히면 안 된다."""
    r = imp.validate_rows([_row(amount="1,234.5"),
                           _row(account_code="5000", amount="(600)")])
    assert r["ok"] is True
    assert [v["amount"] for v in r["valid_rows"]] == [1234.5, -600.0]


def test_summary_reports_what_will_be_written(store):
    r = imp.import_rows([_row(), _row(account_code="5000", value_kind="ACTUAL", amount="900")])
    assert r["summary"]["by_value_kind"] == {"PLAN": 1, "ACTUAL": 1}
    assert r["summary"]["periods"] == ["2027"]


def test_empty_input_is_refused(store):
    r = imp.validate_rows([])
    assert r["ok"] is False


# ── CSV ──────────────────────────────────────────────────────────────────────
def test_csv_requires_headers(store):
    with pytest.raises(PlanningError, match="필수 열이 없습니다"):
        imp.parse_csv("org_id,amount\nX,100\n")


def test_csv_lists_the_required_columns_in_the_error(store):
    """오류 메시지는 **무엇을 넣어야 하는지** 알려줘야 한다."""
    try:
        imp.parse_csv("a,b\n1,2\n")
    except PlanningError as e:
        assert "value_kind" in str(e) and "account_code" in str(e)


def test_csv_skips_bom_and_blank_lines(store):
    """엑셀 저장 파일의 흔한 형태 — 형식 때문에 막히면 안 된다."""
    text = "﻿org_id,account_code,period,value_kind,amount\n" \
           "MNM_BATTERY,4000,2027,PLAN,1000\n\n"
    rows = imp.parse_csv(text)
    assert len(rows) == 1
    assert imp.validate_rows(rows)["ok"] is True


def test_csv_end_to_end(store):
    text = ("org_id,account_code,period,value_kind,amount,source_ref\n"
            "MNM_BATTERY,4000,2026,ACTUAL,\"1,100\",2026결산.xlsx\n"
            "MNM_BATTERY,5000,2026,ACTUAL,650,2026결산.xlsx\n")
    r = imp.import_rows(imp.parse_csv(text), commit=True)
    assert r["written"] == 2
    facts = store.list_facts(org_id="MNM_BATTERY", value_kind=ACTUAL)
    assert {f["account_code"]: f["amount"] for f in facts} == {"4000": 1100.0, "5000": 650.0}
    assert facts[0]["source_ref"] == "2026결산.xlsx"      # 출처가 남는다
