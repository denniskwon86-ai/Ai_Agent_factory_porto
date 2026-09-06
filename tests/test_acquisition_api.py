"""[DAO-8] 수집 API — **되돌리기 비용이 달라지는 지점에서 권한이 바뀌는가.**

이 파일이 지키는 것 넷.

  ① Dry-run 까지는 데이터 사용자, **적용부터는 데이터 관리자**.
     ⚠️ 둘이 같으면 요청한 사람이 곧 적용하는 사람이 되고 직무 분리가 이름만 남는다.
  ② 조직 범위는 **서버가 판정한다** — 본문에 넣어도 무시된다.
  ③ 격리 적재본을 돌려줄 때 **운영 데이터셋이 아님을 함께 말한다**.
  ④ 관문을 통과 못 한 요청은 **작업이 되지 않는다**.

⚠️ 이 파일은 네트워크로 나가는 라우트(`discover`·`dry-run`·`apply`)를 **찌르지 않는다** —
  막히지 않으면 그대로 실행되어 남의 서버를 부른다(권한 시험이 LLM 을 태웠던 2026-08-07
  사고와 같은 유형). 그 경로는 오케스트레이터 시험이 fixture 로 이미 관통했다.
"""
import pytest
from fastapi.testclient import TestClient

from tests import org_seed

from core import route_authority as ra
from core.admin_capability import ADMIN_DATA_ACCESS, PROJECT_RUN

PREFIX = "/api/v1/external/acquisition"


@pytest.fixture()
def client(monkeypatch, ecm_org_seed, seeded_org):
    import config
    from core.org_directory import org_directory
    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    from main import app
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


def _as(client, user, method, path, body=None):
    return client.request(method, PREFIX + path, json=body,
                          headers={"X-Factory-User": user})


# ── ① 권한 계층 ─────────────────────────────────────────────────────────────
#: ⚠️ 네트워크로 나가지 않는 쓰기 라우트만 찌른다.
SAFE_WRITES = [
    ("POST", "/interpret", {"proposal": {}}),
    ("POST", "/jobs", {"proposal": {}}),
    ("POST", "/contract-proposals/PUB-01", None),
    ("POST", "/contract-proposals/dcp_x/decision", {"approve": True}),
    ("POST", "/jobs/daq_x/schedule", {"schedule_rule": "yearly"}),
    ("POST", "/jobs/daq_x/disable", {"reason": "중지"}),
]


@pytest.mark.parametrize("method,path,body", SAFE_WRITES)
def test_viewer_cannot_write_anything(client, method, path, body):
    """열람자는 수집을 시작할 수도, 승인할 수도 없다."""
    r = _as(client, org_seed.VIEWER_A, method, path, body)
    assert r.status_code == 403, f"{method} {path} 가 viewer 에게 {r.status_code}: {r.text[:160]}"


@pytest.mark.parametrize("path,body", [
    ("/contract-proposals/PUB-01", None),
    ("/contract-proposals/dcp_x/decision", {"approve": True}),
    ("/jobs/daq_x/schedule", {"schedule_rule": "yearly"}),
    ("/jobs/daq_x/disable", {"reason": "중지"}),
])
def test_member_cannot_approve_or_schedule(client, path, body):
    """★★★ 요청한 사람이 곧 적용하는 사람이 되면 직무 분리가 이름만 남는다."""
    r = _as(client, org_seed.MEMBER_A, "POST", path, body)
    assert r.status_code == 403, f"{path} 가 member 에게 {r.status_code}: {r.text[:160]}"


def test_member_may_interpret_a_request(client):
    """데이터 사용자는 요청을 만들고 해석시킬 수 있다 — 되돌릴 수 있는 단계다."""
    r = _as(client, org_seed.MEMBER_A, "POST", "/interpret", {"proposal": {}})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["ok"] is False       # 빈 제안이라 관문에서 막힌다


def test_data_admin_may_reach_the_approval_routes(client):
    """데이터 관리자는 403 이 아니어야 한다 — 없는 자원이면 4xx 라도 «권한 없음»은 아니다."""
    r = _as(client, org_seed.DATA_ADMIN, "POST", "/contract-proposals/dcp_missing/decision",
            {"approve": True})
    assert r.status_code != 403, r.text


def test_the_permission_split_is_declared_in_the_table():
    """★★★ 배정이 코드가 아니라 표에 있어야 새 라우트가 조용히 열리지 않는다."""
    assert ra.ROUTE_CAPS[f"POST {PREFIX}/jobs/{{job_id}}/dry-run"] == (PROJECT_RUN,)
    assert ra.ROUTE_CAPS[f"POST {PREFIX}/jobs/{{job_id}}/apply"] == (ADMIN_DATA_ACCESS,)
    assert ra.ROUTE_CAPS[f"POST {PREFIX}/jobs/{{job_id}}/schedule"] == (ADMIN_DATA_ACCESS,)


def test_dry_run_and_apply_do_not_share_a_capability():
    """되돌릴 수 있는 단계와 없는 단계가 같은 권한이면 계층이 무너진다."""
    dry = set(ra.ROUTE_CAPS[f"POST {PREFIX}/jobs/{{job_id}}/dry-run"])
    apply_caps = set(ra.ROUTE_CAPS[f"POST {PREFIX}/jobs/{{job_id}}/apply"])
    assert dry != apply_caps
    assert ADMIN_DATA_ACCESS not in dry


def test_anonymous_is_refused(client):
    r = client.post(PREFIX + "/interpret", json={"proposal": {}})
    assert r.status_code in (401, 403), r.text


# ── 카탈로그 ────────────────────────────────────────────────────────────────
def test_catalog_lists_provider_cards_with_their_limits(client):
    """지시 3 — 화면은 이 응답만 보고 원천 비교 카드를 그린다."""
    r = _as(client, org_seed.MEMBER_A, "GET", "/catalog")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    card = next(c for c in data["providers"] if c["provider_id"] == "OPENDART")
    for key in ("publisher", "license_url", "allowed_usage", "redistribution_allowed",
                "requires_credential", "credential_configured", "cost",
                "default_trust_grade", "refresh_frequency", "coverage_note",
                "target_contract_keys", "data_origin", "known_limits"):
        assert key in card, key
    assert any("대체하지 않습니다" in x for x in card["known_limits"])


def test_catalog_reports_why_a_source_is_unusable(client):
    """자격증명이 없으면 **왜 못 쓰는지**가 나온다 — 조용히 빠지지 않는다."""
    r = _as(client, org_seed.MEMBER_A, "GET", "/catalog")
    data = r.json()["data"]
    card = next(c for c in data["providers"] if c["provider_id"] == "OPENDART")
    if not card["credential_configured"]:
        assert any(e["provider_id"] == "OPENDART" and "AFS_OPENDART_API_KEY" in e["reason"]
                   for e in data["excluded"])


def test_catalog_exposes_the_routing_table_and_states(client):
    r = _as(client, org_seed.MEMBER_A, "GET", "/catalog")
    data = r.json()["data"]
    assert data["routing_table"]["public_financials"] == "PUB-01"
    assert "NO_DATA" in data["states"]
    assert "PUBLIC_DISCLOSED" in data["data_origins"]


# ── ② 범위는 서버가 정한다 ──────────────────────────────────────────────────
def test_scope_in_the_body_is_ignored(client):
    """★★★ 화면이 보낸 범위를 쓰면 「범위를 넓혀 달라」는 한 줄로 남의 부서가 열린다."""
    proposal = {"subject_name": "LS MnM", "purpose": "손익 시뮬레이션",
                "period_from": "2025", "period_to": "2025",
                "scope_node_id": org_seed.DEPT_B, "unrestricted": True,
                "required_grade": "bronze"}
    r = _as(client, org_seed.MEMBER_A, "POST", "/interpret",
            {"proposal": proposal, "purpose_kind": "scenario"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["resolved_scope_node_id"] != org_seed.DEPT_B
    assert data["required_grade"] == "silver"
    overridden = {x["field"] for x in data["overridden"]}
    assert {"scope_node_id", "unrestricted", "required_grade"} <= overridden


# ── ④ 관문을 통과 못 하면 작업이 되지 않는다 ────────────────────────────────
def test_a_bad_proposal_does_not_create_a_job(client):
    before = _as(client, org_seed.MEMBER_A, "GET", "/jobs").json()["data"]
    r = _as(client, org_seed.MEMBER_A, "POST", "/jobs",
            {"proposal": {"subject_name": "LS MnM"}})
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["ok"] is False
    fields = {p["field"] for p in detail["problems"]}
    assert {"purpose", "period"} <= fields
    after = _as(client, org_seed.MEMBER_A, "GET", "/jobs").json()["data"]
    assert len(after) == len(before)


def test_unknown_provider_in_the_proposal_is_refused(client):
    r = _as(client, org_seed.MEMBER_A, "POST", "/jobs", {"proposal": {
        "subject_name": "LS MnM", "purpose": "손익", "period_from": "2025",
        "period_to": "2025", "provider_ids": ["SCRAPER_X"]}})
    assert r.status_code == 400
    assert any(p["field"] == "provider_ids" for p in r.json()["detail"]["problems"])


def test_a_valid_proposal_creates_a_draft_job(client):
    r = _as(client, org_seed.MEMBER_A, "POST", "/jobs", {"proposal": {
        "subject_name": "LS MnM", "purpose": "원료구매·손익 시뮬레이션",
        "period_from": "2025", "period_to": "2025", "provider_ids": ["OPENDART"]}})
    assert r.status_code == 200, r.text
    job = r.json()["data"]
    assert job["status"] == "DRAFT"
    assert job["job_id"].startswith("daq_")
    assert job["requested_by"] == org_seed.MEMBER_A


def test_job_detail_carries_its_ledger_history(client):
    created = _as(client, org_seed.MEMBER_A, "POST", "/jobs", {"proposal": {
        "subject_name": "LS MnM", "purpose": "이력 확인", "period_from": "2025",
        "period_to": "2025", "provider_ids": ["OPENDART"]}}).json()["data"]
    r = _as(client, org_seed.MEMBER_A, "GET", f"/jobs/{created['job_id']}")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["history"], "원장 이력이 비어 있다 — 전이가 기록되지 않았다"
    assert data["history"][0]["event_type"] == "DATA_ACQUISITION_REQUESTED"
    assert "raw_objects" in data


def test_unknown_job_is_404_not_500(client):
    r = _as(client, org_seed.MEMBER_A, "GET", "/jobs/daq_nope")
    assert r.status_code == 404


# ── ③ 격리 적재본임을 함께 말한다 ───────────────────────────────────────────
def test_staged_rows_response_says_it_is_not_operational_data(client):
    """★★★ 화면이 이 행을 운영 데이터로 읽으면 「공개 총계」가 내부 실적이 된다."""
    created = _as(client, org_seed.MEMBER_A, "POST", "/jobs", {"proposal": {
        "subject_name": "LS MnM", "purpose": "격리 확인", "period_from": "2025",
        "period_to": "2025", "provider_ids": ["OPENDART"]}}).json()["data"]
    r = _as(client, org_seed.MEMBER_A, "GET", f"/jobs/{created['job_id']}/rows")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["rows"] == [] and data["count"] == 0
    assert "UNCERTIFIED" in data["notice"]
    assert "운영 데이터셋이 아니" in data["notice"]


# ── 스케줄 ──────────────────────────────────────────────────────────────────
def test_schedule_on_a_non_active_job_is_refused(client):
    """지시 9 — ACTIVE 아닌 작업에 일정을 걸면 사람 관문이 무력해진다."""
    created = _as(client, org_seed.MEMBER_A, "POST", "/jobs", {"proposal": {
        "subject_name": "LS MnM", "purpose": "일정 확인", "period_from": "2025",
        "period_to": "2025", "provider_ids": ["OPENDART"]}}).json()["data"]
    r = _as(client, org_seed.DATA_ADMIN, "POST", f"/jobs/{created['job_id']}/schedule",
            {"schedule_rule": "yearly", "next_run_at": "2027-03-31T00:00:00+00:00"})
    assert r.status_code == 409, r.text
    assert "ACTIVE" in r.json()["detail"]


def test_disable_requires_a_reason(client):
    created = _as(client, org_seed.MEMBER_A, "POST", "/jobs", {"proposal": {
        "subject_name": "LS MnM", "purpose": "중지 확인", "period_from": "2025",
        "period_to": "2025", "provider_ids": ["OPENDART"]}}).json()["data"]
    r = _as(client, org_seed.DATA_ADMIN, "POST", f"/jobs/{created['job_id']}/disable",
            {"reason": "  "})
    assert r.status_code == 400
    assert "사유" in r.json()["detail"]


# ── 새 최상위 메뉴를 만들지 않았다 ──────────────────────────────────────────
def test_routes_live_under_the_existing_external_prefix():
    """지시 11 — 새 최상위를 만들면 「외부 원천」이 두 군데가 된다."""
    from api.routes import acquisition_control
    assert acquisition_control.router.prefix.startswith("/api/v1/external/")
    for key in ra.ROUTE_CAPS:
        if "acquisition" in key:
            assert "/api/v1/external/acquisition/" in key, key
