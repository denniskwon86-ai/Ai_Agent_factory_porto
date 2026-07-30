"""[M2 §2.1 / §6-2] 등급 판정 — **감추지 않고 가린다**(2026-07-30 사용자 결정).

> `CONFIDENTIAL` 자원은 제목만 보이고 내용은 차단한다.

이 파일이 잠그는 것:
  · 등급이 낮으면 **행은 남고 내용이 가려진다**(완전 비노출이 아니다)
  · 가렸다는 사실이 행에 적힌다 — 조용히 빈 값은 "자료 없음"과 구분되지 않는다
  · 등급 미기재는 `INTERNAL` 로 본다(미기재가 곧 공개가 되지 않는다)
  · 해석할 수 없는 등급은 **가장 높게** 본다(해석 실패를 공개로 처리하면 유출이다)
  · 범위 판정이 **먼저**다 — 타 조직 자원은 제목도 새지 않는다
  · 가림 건수를 센다(과도한 가림은 사람들이 시스템 밖에서 자료를 주고받게 만든다)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.enterprise_context.classification import (CONFIDENTIAL, INTERNAL, PUBLIC,
                                                    classification_of, clearance_of_scope,
                                                    may_see_content, redact, redact_all,
                                                    redaction_summary)
from core.enterprise_context.scoping import filter_visible
from core.org_directory import AccessScope

OWNER = "MNM_BATTERY"


def _asset(name="인수 검토 자료", level=CONFIDENTIAL, scope=OWNER):
    return {"asset_id": "da_1", "name": name, "classification": level,
            "description": "A사 인수 가격 산정 근거", "location": "s3://deals/a.xlsx",
            "owner_organization_id": scope, "tenant_id": "tenant_default",
            "entity_mode": "REAL", "scope_type": "ORG_PRIVATE"}


# ── 가린다, 감추지 않는다 ───────────────────────────────────────────────────
def test_low_clearance_sees_title_but_not_content():
    """★★ 결정된 정책 그대로 — 제목은 보이고 내용은 차단된다.

    완전 비노출이 아닌 이유: "분명히 있는데 안 보인다"는 사용자를 **같은 자료를 다시 만드는**
    길로 보낸다. 중복은 그렇게 태어난다."""
    out = redact(_asset(), INTERNAL)
    assert out["name"] == "인수 검토 자료", "제목이 사라졌다 — 결정된 정책은 '제목만 보인다'다"
    assert "description" not in out and "location" not in out, "내용이 그대로 남았다"
    assert out["redacted"] is True


def test_redaction_says_why_and_what_to_do():
    """★★ 조용히 비운 필드는 "값이 없음"과 구분되지 않는다 — 사용자는 데이터가 비었다고 믿는다."""
    out = redact(_asset(), INTERNAL)
    assert "제목·식별 정보만 표시" in out["redaction_reason"]
    assert "열람 권한을 요청" in out["redaction_reason"], "다음 행동이 없으면 문의만 늘어난다"


def test_high_clearance_sees_everything():
    out = redact(_asset(), CONFIDENTIAL)
    assert out["description"] and out["location"] and not out.get("redacted")


def test_internal_rows_are_open_to_internal_users():
    """★ 등급 정책이 과하면 사람들이 시스템 밖에서 자료를 주고받는다 — INTERNAL 은 막지 않는다."""
    out = redact(_asset(level=INTERNAL), INTERNAL)
    assert out["description"] and not out.get("redacted")


# ── 기본값과 해석 실패 ─────────────────────────────────────────────────────
def test_missing_classification_is_internal_not_public():
    """★★ 미기재가 곧 공개가 되면, 관문 A 에서 폐기한 "빈 값 = 전사 공용"이 등급 축에서 되살아난다."""
    row = {"name": "x"}
    assert classification_of(row) == INTERNAL
    assert may_see_content(row, INTERNAL) is True
    assert may_see_content(row, PUBLIC) is False


def test_unknown_classification_is_treated_as_highest():
    """★★ 해석할 수 없는 등급을 '공개'로 처리하면 그게 곧 유출이다.

    최고 등급자에게도 내용을 주지 않는다 — 그래야 잘못 기입된 등급이 **저절로 발견된다**
    (내용이 안 보이니 누군가 신고한다). 조용히 `INTERNAL` 로 강등하면 영원히 그대로 남는다."""
    row = {"name": "x", "classification": "TOP_SECRET_XYZ"}
    assert may_see_content(row, CONFIDENTIAL) is False
    out = redact(row, CONFIDENTIAL)
    assert out["redacted"] is True
    assert out["classification"] == "TOP_SECRET_XYZ", "원문을 남겨야 고칠 수 있다"
    assert "정의된 등급이 아닙니다" in out["redaction_reason"]


def test_broken_viewer_clearance_does_not_open_everything():
    """★★ 행과 주체는 실패 방향이 **반대**여야 한다.

    같은 서열 함수를 쓰면(모르는 값 = 최고 등급) 주체 등급 문자열이 깨졌을 때 오히려 전부
    보이게 된다 — 정확히 거꾸로다."""
    assert may_see_content(_asset(level=CONFIDENTIAL), "GARBAGE_LEVEL") is False
    assert may_see_content(_asset(level=INTERNAL), "GARBAGE_LEVEL") is False
    assert may_see_content(_asset(level=PUBLIC), "GARBAGE_LEVEL") is True


# ── 주체 등급 파생 ──────────────────────────────────────────────────────────
def test_clearance_is_derived_from_existing_permissions():
    """★ 권한과 등급을 두 곳에서 관리하면 반드시 어긋난다 — 기존 `AccessScope` 에서 파생한다."""
    assert clearance_of_scope(AccessScope(unrestricted=True)) == CONFIDENTIAL
    assert clearance_of_scope(AccessScope(unrestricted=False, is_admin=True)) == CONFIDENTIAL
    assert clearance_of_scope(AccessScope(unrestricted=False, is_executive=True)) == CONFIDENTIAL
    assert clearance_of_scope(
        AccessScope(unrestricted=False, user_id="staff@ls")) == INTERNAL
    assert clearance_of_scope(AccessScope(unrestricted=False)) == PUBLIC
    assert clearance_of_scope(None) == PUBLIC


# ── 범위 판정이 먼저다 ─────────────────────────────────────────────────────
def test_scope_filter_runs_before_redaction():
    """★★ 타 조직 자원은 목록에서 이미 빠지므로 **제목도 새지 않는다.**

    등급 가림을 범위 필터보다 먼저 적용하면, 타 조직 자원의 제목이 목록에 실려 §3.3 의 은폐
    경계가 무너진다."""
    mine = _asset(name="우리 자료", scope=OWNER)
    theirs = _asset(name="남의 자료", scope="LS_CABLE")
    rows = filter_visible([mine, theirs], scope_node_id=OWNER, viewer_clearance=INTERNAL)

    names = [r.get("name") for r in rows]
    assert "우리 자료" in names, "내 조직 자원은 제목이 남아야 한다"
    assert "남의 자료" not in names, "타 조직 자원의 제목이 노출됐다"
    assert rows[0]["redacted"] is True and "description" not in rows[0]


def test_no_clearance_argument_means_no_redaction():
    """★ 등급 개념이 없는 내부 호출(파이프라인 등)을 막지 않는다 — 관문 A 의 안전판과 같은 규약."""
    rows = filter_visible([_asset()], scope_node_id=OWNER)
    assert rows[0]["description"], "등급을 주지 않았는데 가려졌다"


# ── 관측 ────────────────────────────────────────────────────────────────────
def test_redaction_is_counted():
    """★ 가림도 관측 대상이다 — 과도한 가림은 사람들이 시스템 밖에서 자료를 주고받게 만든다."""
    rows = redact_all([_asset(), _asset(level=INTERNAL)], INTERNAL)
    s = redaction_summary(rows)
    assert s["total"] == 2 and s["redacted"] == 1
    assert "제목만" in s["note"] and "가려진 것" in s["note"]

    assert redaction_summary(redact_all([_asset()], CONFIDENTIAL))["note"] == ""


# ── 목록 API 배선 (2026-07-30) ──────────────────────────────────────────────
def test_core_list_methods_accept_and_apply_clearance(tmp_path):
    """★★ 판정 함수만 만들고 목록에 배선하지 않으면 등급은 **장식**이다.

    실측: 배선 전에는 `viewer_clearance` 를 넘기는 곳이 참고문서 등록부 하나뿐이었다 —
    카탈로그·용어사전·계약 등 거버넌스 화면 전부가 등급을 무시했다."""
    from core.business_glossary import BusinessGlossary
    from core.data_catalog import DataCatalog
    from core.master_data import MasterData

    md = MasterData(db_path=str(tmp_path / "m.db"))
    dc, g = DataCatalog(md), BusinessGlossary(md)
    dc.create_asset("인수 검토표", enterprise_scope_id=OWNER, description="A사 가격 산정")
    with md._connect() as conn:
        conn.execute("UPDATE data_assets SET classification='CONFIDENTIAL'")

    low = dc.list_assets(scope_node_id=OWNER, viewer_clearance=INTERNAL)
    assert low and low[0]["name"] == "인수 검토표", "제목은 남아야 한다"
    assert low[0]["redacted"] is True and "description" not in low[0]

    high = dc.list_assets(scope_node_id=OWNER, viewer_clearance=CONFIDENTIAL)
    assert high[0]["description"] == "A사 가격 산정" and not high[0].get("redacted")

    # 등급을 주지 않으면 가리지 않는다(내부 파이프라인 호출 보호).
    assert dc.list_assets(scope_node_id=OWNER)[0]["description"]

    # 용어사전도 같은 규칙을 따른다 — 두 화면이 다른 규칙을 쓰면 어느 쪽도 신뢰할 수 없다.
    g.create_term("전극 두께", definition="양극 코팅 두께", enterprise_scope_id=OWNER)
    assert g.list_terms(scope_node_id=OWNER, viewer_clearance=INTERNAL)


def test_clearance_only_call_still_filters(tmp_path):
    """★ 범위 없이 **등급만** 거는 호출도 있다(전사 화면). 그때도 가림이 적용돼야 한다."""
    from core.data_catalog import DataCatalog
    from core.master_data import MasterData

    md = MasterData(db_path=str(tmp_path / "m2.db"))
    dc = DataCatalog(md)
    dc.create_asset("대외비 자료", description="민감")
    with md._connect() as conn:
        conn.execute("UPDATE data_assets SET classification='CONFIDENTIAL'")

    rows = dc.list_assets(viewer_clearance=INTERNAL)
    assert rows and rows[0].get("redacted") is True, "범위 없이 등급만 준 호출이 무시됐다"
