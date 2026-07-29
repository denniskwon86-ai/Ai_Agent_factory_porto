"""[M2] 커넥터 등록부 + Query Contract — **무엇을 물어볼 수 있는가를 먼저 정한다.**

크로스워크(주소록)만 있으면 임의 쿼리가 가능해지고 최소 권한이 무너진다.
§7.2: *"호출 가능한 도구는 시스템별로 명시적으로 등록한다. 기본은 최소 권한, 읽기 전용."*

이 파일이 잠그는 것은 "연결이 되는가"가 아니라 **"연결로 무엇까지 할 수 있는가"** 다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.connector_registry import ConnectorError, ConnectorRegistry


@pytest.fixture()
def reg(tmp_path):
    return ConnectorRegistry(db_path=str(tmp_path / "connectors.db"))


def _erp(reg, **kw):
    return reg.register("erp", "그룹 ERP", "db", endpoint="postgres://erp",
                        auth_ref="ERP_DB_PASSWORD", **kw)


# ── 비밀은 저장하지 않는다 ───────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    "sk-abcdef123456", "Bearer eyJhbGciOi", "AKIAIOSFODNN7EXAMPLE",
    "postgres://user:realpassword@host/db", "password=hunter2",
])
def test_credentials_in_auth_ref_are_refused(reg, bad):
    """★★ 실제 비밀을 DB 에 넣으면 백업·로그·화면 어디로든 샌다.

    "실수로 넣었는데 아무도 몰랐다"가 이 계열의 전형적인 사고다."""
    with pytest.raises(ConnectorError, match="자격증명"):
        reg.register("x", "X", "api", auth_ref=bad)


def test_reference_style_auth_ref_is_accepted(reg):
    """참조(환경변수명·비밀관리자 키)는 받아들인다 — 그게 올바른 형태다."""
    c = _erp(reg)
    assert c["auth_ref"] == "ERP_DB_PASSWORD"


# ── 등록만으로 활성이 아니다 ─────────────────────────────────────────────────
def test_registration_is_inactive_by_default(reg):
    assert _erp(reg)["status"] == "inactive"


def test_activation_requires_an_approved_contract(reg):
    """★★ 계약 없이 활성화하면 **무엇을 물어볼 수 있는지 아무도 모르는** 상태가 되고,
    그때부터 임의 쿼리가 시작된다."""
    _erp(reg)
    with pytest.raises(ConnectorError, match="Query Contract"):
        reg.activate("erp", "cfo")


def test_unapproved_contract_does_not_enable_activation(reg):
    _erp(reg)
    reg.add_contract("erp", "monthly_pl", ["account_code", "amount"])   # 미승인
    with pytest.raises(ConnectorError, match="Query Contract"):
        reg.activate("erp", "cfo")


def test_anonymous_activation_is_refused(reg):
    _erp(reg)
    reg.add_contract("erp", "monthly_pl", ["amount"], approved_by="cfo")
    with pytest.raises(ConnectorError, match="승인자 식별"):
        reg.activate("erp", "")


def test_activation_is_audited(reg, tmp_path, monkeypatch):
    from core.enterprise_context import audit
    monkeypatch.setattr(audit, "_LOG_PATH", str(tmp_path / "a.jsonl"))
    _erp(reg)
    reg.add_contract("erp", "monthly_pl", ["amount"], approved_by="cfo")
    reg.activate("erp", "cfo")
    e = audit.recent(1)[0]
    assert e["event"] == audit.APPROVAL_GRANTED and e["resource_id"] == "erp"


# ── Query Contract ───────────────────────────────────────────────────────────
def test_empty_whitelist_is_refused(reg):
    """★ 빈 화이트리스트는 '아무거나 다 준다'가 되어 **계약의 의미가 사라진다**."""
    _erp(reg)
    with pytest.raises(ConnectorError, match="allowed_fields"):
        reg.add_contract("erp", "q", [])


def test_max_rows_must_be_positive(reg):
    _erp(reg)
    with pytest.raises(ConnectorError, match="max_rows"):
        reg.add_contract("erp", "q", ["a"], max_rows=0)


# ── 요청 검증 ────────────────────────────────────────────────────────────────
@pytest.fixture()
def active(reg):
    _erp(reg)
    reg.add_contract("erp", "monthly_pl",
                     allowed_fields=["account_code", "period", "amount", "employee_name"],
                     required_params=["period"], max_rows=500,
                     sensitive_fields=["employee_name"], approved_by="cfo")
    reg.activate("erp", "cfo")
    return reg


def test_field_outside_whitelist_is_refused(active):
    """`SELECT * FROM salary` 류를 막는 지점 — 읽기 전용이어도 **볼 수 없어야 할 것**이 있다."""
    r = active.validate_request("erp", "monthly_pl", ["amount", "salary"], {"period": "2027"})
    assert r["allowed"] is False
    assert any("허용되지 않은 필드" in e for e in r["errors"])


def test_missing_required_param_is_refused(active):
    """필수 파라미터가 없으면 **전건 조회**가 되어 최소 권한이 무너진다."""
    r = active.validate_request("erp", "monthly_pl", ["amount"], {})
    assert r["allowed"] is False and any("필수 파라미터" in e for e in r["errors"])


def test_all_errors_are_returned_at_once(active):
    """★ 하나씩 튕기면 사용자가 여러 번 시도하며 무엇이 되는지 **탐색**하게 되고,
    그 탐색 자체가 스키마 정보 유출이다."""
    r = active.validate_request("erp", "monthly_pl", ["salary"], {}, limit=99999)
    assert len(r["errors"]) == 3      # 필드·파라미터·limit 을 한 번에


def test_limit_over_contract_is_refused(active):
    r = active.validate_request("erp", "monthly_pl", ["amount"], {"period": "2027"}, limit=1000)
    assert r["allowed"] is False and any("상한" in e for e in r["errors"])


def test_valid_request_passes_with_effective_limit(active):
    r = active.validate_request("erp", "monthly_pl", ["amount"], {"period": "2027"})
    assert r["allowed"] is True and r["limit"] == 500


def test_sensitive_fields_are_stripped_for_prompts(active):
    """★★ §7.2 — 민감 데이터를 프롬프트로 무제한 전달하지 않는다.

    오류가 아니라 **제거**이며, 무엇이 빠졌는지 말한다 — 말하지 않으면 사용자는
    값이 왜 없는지 모른다."""
    r = active.validate_request("erp", "monthly_pl", ["amount", "employee_name"],
                                {"period": "2027"}, for_prompt=True)
    assert r["allowed"] is True
    assert r["effective_fields"] == ["amount"]
    assert r["removed_sensitive"] == ["employee_name"]
    assert "제외했습니다" in r["note"]


def test_sensitive_fields_are_kept_for_non_prompt_use(active):
    """화면·리포트에서는 권한이 있으면 볼 수 있다 — 제거는 **프롬프트 전달**에 한정된다."""
    r = active.validate_request("erp", "monthly_pl", ["amount", "employee_name"],
                                {"period": "2027"})
    assert r["effective_fields"] == ["amount", "employee_name"]


def test_inactive_connector_is_refused(reg):
    _erp(reg)
    reg.add_contract("erp", "q", ["a"], approved_by="cfo")
    r = reg.validate_request("erp", "q", ["a"], {})
    assert r["allowed"] is False and "비활성" in r["errors"][0]


def test_unregistered_query_is_refused(active):
    """등록되지 않은 쿼리는 거부 — 호출 가능한 도구는 명시적으로 등록한다(§7.2)."""
    r = active.validate_request("erp", "anything_goes", ["amount"], {"period": "2027"})
    assert r["allowed"] is False and "등록되지 않은 쿼리" in r["errors"][0]


# ── 조직 범위 ────────────────────────────────────────────────────────────────
def test_scope_filter_applies(reg, monkeypatch):
    """커넥터도 조직 자산이다 — 남의 사업부 연결을 보면 안 된다."""
    import core.enterprise_context.scoping as sc
    monkeypatch.setattr(sc, "visible_scopes",
                        lambda n: {"BATTERY", "MNM"} if n == "BATTERY" else {n})
    reg.register("bat-erp", "배터리 ERP", "db", owner_organization_id="BATTERY")
    reg.register("sml-erp", "제련 ERP", "db", owner_organization_id="SMELTING")
    ids = [c["connector_id"] for c in reg.list_connectors(scope_node_id="BATTERY")]
    assert ids == ["bat-erp"]
