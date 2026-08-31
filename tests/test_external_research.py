"""회사 조사 프로필과 수집 작업의 승인 경계."""
from pathlib import Path

import pytest

from core.external_research import (BOT_KINDS, ExternalResearchError,
                                    ExternalResearchRunner, ExternalResearchStore,
                                    FetchDocument, validate_public_target)
from core.system_ids import is_system_id


@pytest.fixture
def store(tmp_path: Path) -> ExternalResearchStore:
    return ExternalResearchStore(db_path=str(tmp_path / "external.db"))


def profile(**overrides):
    payload = {
        "legal_entity_id": "corp-ls-mnm",
        "company_name": "LS MnM",
        "official_domains": ["lsmnm.com"],
        "official_urls": ["https://www.lsmnm.com/"],
        "business_keywords": ["비철금속", "제련"],
        "product_keywords": ["전기동", "황산"],
        "regions": ["대한민국"],
        "competitor_names": [],
        "material_keywords": ["구리", "금"],
        "required_indicators": ["LME_CU", "FX_USDKRW"],
        "collection_purpose": "경영 시나리오의 외부 근거 후보 탐색",
        "schedule_rule": "MANUAL",
        "owner_id": "data.owner@test.invalid",
        "retention_days": 365,
    }
    payload.update(overrides)
    return payload


def approved(store: ExternalResearchStore):
    made = store.save_profile(profile())
    review = store.request_review(made["profile_id"])
    return store.approve_profile(made["profile_id"], "approver@test.invalid",
                                 review["fingerprint"])


def test_import_does_not_create_database(tmp_path: Path):
    target = tmp_path / "not-created.db"
    ExternalResearchStore(db_path=str(target))
    assert not target.exists(), "객체 생성만으로 운영 데이터 파일을 만들면 시험 격리가 깨진다"


def test_new_research_profile_uses_the_central_system_identifier(store: ExternalResearchStore):
    made = store.save_profile(profile())
    assert is_system_id(made["profile_id"], "research_profile")


def test_profile_requires_allowed_https_url(store: ExternalResearchStore):
    with pytest.raises(ExternalResearchError, match="https"):
        store.save_profile(profile(official_urls=["http://www.lsmnm.com/"]))
    with pytest.raises(ExternalResearchError, match="승인 도메인 밖"):
        store.save_profile(profile(official_urls=["https://example.com/"]))
    with pytest.raises(ExternalResearchError, match="scheme"):
        store.save_profile(profile(official_domains=["https://lsmnm.com/"]))
    with pytest.raises(ExternalResearchError, match="IP 주소"):
        store.save_profile(profile(official_domains=["127.0.0.1"],
                                   official_urls=["https://127.0.0.1/"]))


def test_profile_fingerprint_is_order_independent(store: ExternalResearchStore):
    a = store.save_profile(profile(business_keywords=["제련", "비철금속"]))
    b = store.save_profile(profile(business_keywords=["비철금속", "제련"]))
    assert a["fingerprint"] == b["fingerprint"]


def test_review_requires_domain_url_and_purpose(store: ExternalResearchStore):
    no_url = store.save_profile(profile(official_urls=[]))
    with pytest.raises(ExternalResearchError, match="공식 도메인과 공식 URL"):
        store.request_review(no_url["profile_id"])
    no_purpose = store.save_profile(profile(collection_purpose=""))
    with pytest.raises(ExternalResearchError, match="수집 목적"):
        store.request_review(no_purpose["profile_id"])


def test_approval_is_bound_to_reviewed_fingerprint(store: ExternalResearchStore):
    made = store.save_profile(profile())
    review = store.request_review(made["profile_id"])
    with pytest.raises(ExternalResearchError, match="지문이 다릅니다"):
        store.approve_profile(made["profile_id"], "approver@test.invalid", "0" * 64)
    out = store.approve_profile(made["profile_id"], "approver@test.invalid",
                                review["fingerprint"])
    assert out["status"] == "APPROVED" and out["approved_by"]


def test_semantic_change_revokes_approval_and_requires_review(store: ExternalResearchStore):
    before = approved(store)
    changed = store.save_profile(profile(regions=["대한민국", "칠레"]), before["profile_id"])
    assert changed["status"] == "REVIEW_REQUIRED"
    assert changed["approved_by"] == "" and changed["approved_at"] == ""
    assert changed["fingerprint"] != before["fingerprint"]


def test_same_content_save_preserves_approval(store: ExternalResearchStore):
    before = approved(store)
    same = store.save_profile(profile(business_keywords=["제련", "비철금속"]),
                              before["profile_id"])
    assert same["status"] == "APPROVED"
    assert same["approved_by"] == before["approved_by"]


def test_job_requires_approved_profile(store: ExternalResearchStore):
    made = store.save_profile(profile())
    with pytest.raises(ExternalResearchError, match="승인된 회사 조사 프로필"):
        store.schedule_job(made["profile_id"], BOT_KINDS[0], "operator@test.invalid")


def test_company_research_never_accepts_non_dry_run_job(store: ExternalResearchStore):
    prof = approved(store)
    with pytest.raises(ExternalResearchError, match="dry-run 후보 생성만"):
        store.schedule_job(prof["profile_id"], BOT_KINDS[0], "operator@test.invalid",
                           dry_run=False)


def test_job_seals_profile_fingerprint_and_defaults_to_dry_run(store: ExternalResearchStore):
    prof = approved(store)
    job = store.schedule_job(prof["profile_id"], "COMPANY_BASE_RESEARCH",
                             "operator@test.invalid")
    assert job["status"] == "SCHEDULED" and job["dry_run"] is True
    assert job["profile_fingerprint"] == prof["fingerprint"]
    assert store.list_jobs(prof["profile_id"])[0]["job_id"] == job["job_id"]


def test_unknown_bot_kind_is_closed(store: ExternalResearchStore):
    prof = approved(store)
    with pytest.raises(ExternalResearchError, match="지원하지 않는 조사 봇"):
        store.schedule_job(prof["profile_id"], "GENERAL_WEB_CRAWLER",
                           "operator@test.invalid")


def _public_resolver(host, port, type):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def test_public_target_rejects_private_network_and_unapproved_redirect():
    private = lambda host, port, type: [(2, 1, 6, "", ("127.0.0.1", port))]
    with pytest.raises(ExternalResearchError, match="공개망이 아닌"):
        validate_public_target("https://www.lsmnm.com/", ["lsmnm.com"], private)
    with pytest.raises(ExternalResearchError, match="승인 도메인 밖"):
        validate_public_target("https://evil.example/", ["lsmnm.com"], _public_resolver)
    assert validate_public_target("https://news.lsmnm.com/a", ["lsmnm.com"],
                                  _public_resolver).endswith("/a")


def test_company_research_creates_candidates_but_no_observations(store: ExternalResearchStore):
    prof = approved(store)
    job = store.schedule_job(prof["profile_id"], "COMPANY_BASE_RESEARCH",
                             "operator@test.invalid")
    html = """<html><head><title>LS MnM</title>
      <meta name="description" content="비철금속 소재 기업"></head><body>
      <a href="/news">뉴스</a><a href="https://evil.example/x">외부</a></body></html>"""
    runner = ExternalResearchRunner(
        store, fetcher=lambda url, p: FetchDocument(url, html, "text/html"))
    out = runner.run(job["job_id"])
    candidates = store.list_candidates(prof["profile_id"])
    assert out["status"] == "CANDIDATE_READY"
    assert out["result_summary"]["candidate_count"] == 2
    assert {c["candidate_kind"] for c in candidates} == {"COMPANY_PAGE", "SOURCE_CANDIDATE"}
    assert all("evil.example" not in c["source_url"] for c in candidates)


def test_rss_items_are_event_candidates_not_numeric_values(store: ExternalResearchStore):
    made = store.save_profile(profile(official_urls=["https://www.lsmnm.com/feed.xml"]))
    review = store.request_review(made["profile_id"])
    prof = store.approve_profile(made["profile_id"], "approver@test.invalid",
                                 review["fingerprint"])
    job = store.schedule_job(prof["profile_id"], "COMPANY_BASE_RESEARCH",
                             "operator@test.invalid")
    rss = """<rss><channel><item><title>구리 가격 10% 상승</title>
      <link>https://www.lsmnm.com/news/1</link></item></channel></rss>"""
    runner = ExternalResearchRunner(
        store, fetcher=lambda url, p: FetchDocument(url, rss, "application/rss+xml"))
    runner.run(job["job_id"])
    candidate = store.list_candidates(prof["profile_id"])[0]
    assert candidate["candidate_kind"] == "EXTERNAL_EVENT"
    assert "10%" in candidate["title"]
    assert "value" not in candidate["evidence"], "기사 숫자를 관측값으로 바꾸면 안 된다"


def test_changed_profile_invalidates_scheduled_job(store: ExternalResearchStore):
    prof = approved(store)
    job = store.schedule_job(prof["profile_id"], "COMPANY_BASE_RESEARCH",
                             "operator@test.invalid")
    store.save_profile(profile(regions=["대한민국", "칠레"]), prof["profile_id"])
    runner = ExternalResearchRunner(store, fetcher=lambda url, p: "<html/>")
    with pytest.raises(ExternalResearchError, match="승인이 유효하지 않습니다"):
        runner.run(job["job_id"])
    assert store.get_job(job["job_id"])["status"] == "FAILED"


def test_unimplemented_bot_fails_loudly(store: ExternalResearchStore):
    prof = approved(store)
    job = store.schedule_job(prof["profile_id"], "INDICATOR_COLLECTOR",
                             "operator@test.invalid")
    runner = ExternalResearchRunner(store, fetcher=lambda url, p: "<html/>")
    with pytest.raises(ExternalResearchError, match="아직 구현되지 않았습니다"):
        runner.run(job["job_id"])
    assert store.get_job(job["job_id"])["status"] == "FAILED"


def test_candidate_review_is_hash_bound_and_one_time(store: ExternalResearchStore):
    prof = approved(store)
    job = store.schedule_job(prof["profile_id"], "COMPANY_BASE_RESEARCH",
                             "operator@test.invalid")
    runner = ExternalResearchRunner(store, fetcher=lambda url, p: FetchDocument(
        url, "<html><head><title>회사</title></head></html>"))
    runner.run(job["job_id"])
    candidate = store.list_candidates(prof["profile_id"])[0]
    with pytest.raises(ExternalResearchError, match="내용 지문이 다릅니다"):
        store.review_candidate(candidate["candidate_id"], "ACCEPTED", "reviewer@test.invalid",
                               "0" * 64)
    accepted = store.review_candidate(candidate["candidate_id"], "ACCEPTED",
                                      "reviewer@test.invalid", candidate["content_hash"])
    assert accepted["status"] == "ACCEPTED" and accepted["reviewed_by"]
    with pytest.raises(ExternalResearchError, match="검토 대기 후보"):
        store.review_candidate(candidate["candidate_id"], "REJECTED", "reviewer@test.invalid",
                               candidate["content_hash"])
