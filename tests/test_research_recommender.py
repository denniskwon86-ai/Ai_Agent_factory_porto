"""[DAO-15] 연구자료 «추천기» — 받아오지 않고, 지어내지 않는다.

이 파일이 지키는 것 여섯.

  ①★★★ **네트워크를 한 번도 만지지 않는다.** 받아오는 행위는 사람이 한다.
  ②★★★ 카탈로그 «밖»의 원천을 만들지 않는다 — LLM 이 지어내면 대조가 잡는다.
  ③ KSIC 는 **접두사** 매칭이다. `C2412` 회사가 `C24` 원천을 만나야 한다.
  ④ 업종이 «없어도» 동작한다 — 산업분류 정리가 아직 진행 중이다(2026-09-08).
  ⑤ 정산: 추천 + 제외 = 카탈로그 전체. 조용히 사라지는 원천이 없다.
  ⑥ 사용자가 «가서 받아야» 하므로 추천이 행동 가능해야 한다.
"""
import pytest

from core.external_intelligence import research_catalog as RC
from core.external_intelligence import research_recommender as R

LSMNM = R.CompanyContext(company_name="LS MnM", industry_code="C2412",
                         products=("전기동", "아연괴"))


# ── ① 네트워크를 만지지 않는다 ───────────────────────────────────────────────
def test_recommending_never_touches_the_network(monkeypatch):
    """★★★ 이 모듈의 존재 이유다. 만지는 순간 우리가 사이트 개편을 떠안는다."""
    import socket
    import urllib.request

    def boom(*a, **k):                      # pragma: no cover - 불리면 실패다
        raise AssertionError("추천기가 네트워크를 호출했습니다 — 받아오는 것은 사용자의 일입니다.")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)

    out = R.recommend(LSMNM, use_case="competitor_analysis")
    assert out.items
    R.llm_brief(out)
    RC.assert_catalog_sane()


def test_the_recommender_is_not_a_provider():
    """★ Provider 등록부에 들어가면 오케스트레이터가 «수집하려» 든다."""
    from core.external_intelligence import providers as P
    assert "RESEARCH_CATALOG" not in {d.provider_id for d in P.descriptors()}
    for key in RC.keys():
        assert key not in {d.provider_id for d in P.descriptors()}


def test_the_result_says_the_user_fetches_it():
    """사람이 결과만 보고 「시스템이 받아왔다」고 오해하면 안 된다."""
    out = R.recommend(LSMNM)
    assert any("사용자가 직접" in n for n in out.notes)


# ── ② 지어내지 않는다 ────────────────────────────────────────────────────────
def test_every_recommended_key_is_in_the_catalog():
    out = R.recommend(LSMNM, limit=100)
    for r in out.items:
        assert r.source.source_key in RC.keys()


def test_invented_sources_are_caught():
    """★★★ 「지시했으니 안 지어낼 것이다」로 두지 않는다 — 대조가 통과 조건이다."""
    ok, invented = R.verify_llm_output(["KIET", "한국비철금속연구원", "KOMIR", ""])
    assert ok == ("KIET", "KOMIR")
    assert invented == ("한국비철금속연구원", "")


def test_the_llm_brief_carries_no_internal_records():
    """지시 6 — 내부 원문 레코드를 외부 LLM 에 보내지 않는다.

    ★ 구조적으로 불가능해야 한다: brief 는 카탈로그 필드와 질의만 읽는다."""
    ctx = R.CompanyContext(company_name="LS MnM", industry_code="C2412",
                           products=("영업비밀제품",), regions=("비밀공장",),
                           source_note="내부 메모")
    brief = R.llm_brief(R.recommend(ctx, use_case="competitor_analysis"))
    blob = repr(brief)
    assert "영업비밀제품" not in blob
    assert "비밀공장" not in blob
    assert "내부 메모" not in blob
    assert brief["rules"]


def test_the_brief_tells_the_model_not_to_invent():
    brief = R.llm_brief(R.recommend(LSMNM))
    assert any("추가하지" in r for r in brief["rules"])
    assert any("지어내지" in r for r in brief["rules"])


# ── ③ KSIC 접두사 매칭 ──────────────────────────────────────────────────────
def test_a_subclass_company_matches_a_broader_source():
    """★★★ `C2412` 회사가 `C24` 원천을 만나야 한다. 문자열 일치면 못 만난다."""
    komir = RC.get("KOMIR")
    assert "C24" in komir.industry_codes and "C2412" not in komir.industry_codes
    ok, score, why = R.industry_match(komir, "C2412")
    assert ok and score > 0 and "C24" in why


def test_an_exact_code_scores_higher_than_a_prefix():
    icsg = RC.get("ICSG")          # C2412 를 직접 단다
    komir = RC.get("KOMIR")        # C24 만 단다
    _, exact, _ = R.industry_match(icsg, "C2412")
    _, prefix, _ = R.industry_match(komir, "C2412")
    assert exact > prefix


def test_an_unrelated_industry_is_excluded_with_a_reason():
    """서비스업 회사에 비철 전용 원천을 권하지 않는다 — 다만 «사유와 함께» 뺀다."""
    out = R.recommend(R.CompanyContext(industry_code="G47"), limit=100)
    reasons = {e.source_key: e.reason for e in out.excluded}
    assert reasons.get("ICSG") == R.EXCLUDED_INDUSTRY


def test_industry_agnostic_sources_reach_everyone():
    kiet = RC.get("KIET")
    assert kiet.industry_codes == ()
    for code in ("C2412", "G47", ""):
        ok, _, _ = R.industry_match(kiet, code)
        assert ok


# ── ④ 업종이 없어도 동작한다 ────────────────────────────────────────────────
def test_it_works_before_the_industry_taxonomy_exists():
    """⚠️ 공개 기업정보 기반 산업분류는 «다른 세션에서 작성 중»이다(2026-09-08).
    그것이 없다고 추천이 멈추면 안 되고, **조용히 좁혀서도 안 된다.**"""
    out = R.recommend(R.CompanyContext(company_name="이름만 있는 회사"),
                      use_case="new_business")
    assert out.items
    assert any("업종" in n for n in out.notes)


def test_a_missing_industry_does_not_silently_drop_specialised_sources():
    """업종을 모른다고 비철 원천을 «빼면» 사용자는 그것이 없는 줄 안다."""
    out = R.recommend(R.CompanyContext(), limit=100)
    keys = {r.source.source_key for r in out.items}
    assert "KOMIR" in keys


def test_the_context_is_injected_not_read_from_a_store():
    """★ 저장소를 직접 열면 산업분류 정본이 바뀔 때 여기까지 다시 짜야 한다.

    ⚠️ 본문 «글자»가 아니라 실제 `import` 를 본다 — 주석에서 설명하려고 이름을 적는 것은
      결합이 아니다. (첫 판은 docstring 의 언급을 결합으로 세어 잘못 걸렸다.)"""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(R))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    for forbidden in ("core.enterprise_context", "sqlite3", "core.master_data"):
        assert not any(m.startswith(forbidden) for m in imported),             f"추천기가 {forbidden} 를 직접 import 합니다: {sorted(imported)}"
    #: ★ 컨텍스트는 «인자»로 들어온다 — 그 사실 자체를 시그니처로 확인한다.
    assert list(inspect.signature(R.recommend).parameters)[0] == "context"


# ── ⑤ 정산과 제외 사유 ──────────────────────────────────────────────────────
def test_every_source_is_either_recommended_or_excluded_with_a_reason():
    """★★★ 조용히 사라지는 원천이 있으면 카탈로그에 넣은 의미가 없다."""
    out = R.recommend(LSMNM, use_case="competitor_analysis", limit=5)
    assert out.accounted, (len(out.items), len(out.excluded), len(RC.CATALOG))
    assert all(e.reason for e in out.excluded)
    assert len({e.source_key for e in out.excluded}) == len(out.excluded)


def test_ranked_out_sources_say_so_rather_than_vanishing():
    out = R.recommend(LSMNM, limit=3)
    assert R.EXCLUDED_RANK in {e.reason for e in out.excluded}


def test_user_exclusions_are_remembered_with_their_own_reason():
    """이미 받았거나 안 쓰기로 한 것을 매번 다시 권하면 목록을 안 보게 된다."""
    out = R.recommend(LSMNM, exclude=["KOMIR"], limit=100)
    assert "KOMIR" not in {r.source.source_key for r in out.items}
    assert {e.reason for e in out.excluded if e.source_key == "KOMIR"} == {R.EXCLUDED_USER}


def test_the_same_question_gives_the_same_answer():
    """★ 순서가 흔들리면 사람이 「어제와 다르다」를 결함으로 읽는다."""
    a = R.recommend(LSMNM, use_case="competitor_analysis", limit=6)
    b = R.recommend(LSMNM, use_case="competitor_analysis", limit=6)
    assert [r.source.source_key for r in a.items] == [r.source.source_key for r in b.items]
    assert [r.score for r in a.items] == [r.score for r in b.items]


# ── ⑥ 행동 가능해야 한다 ────────────────────────────────────────────────────
def test_every_recommendation_tells_the_user_where_to_go_and_what_to_look_for():
    """기관 이름만 주면 사용자가 사이트 안에서 다시 헤맨다."""
    for r in R.recommend(LSMNM, limit=100).items:
        act = r.action
        assert act["open"].startswith("http")
        assert act["look_for"], r.source.source_key
        assert r.why, r.source.source_key
        assert r.source.what_it_gives


def test_unverified_links_are_flagged_not_hidden():
    """★★★ 카탈로그가 낡아도 «조용히» 낡지 않게 하는 장치다."""
    assert not any(s.link_verified for s in RC.CATALOG)   # 초기 상태: 전부 미확인
    out = R.recommend(LSMNM, limit=3)
    assert all(any("링크를 사람이 확인한 기록이 없습니다" in w for w in r.warnings)
               for r in out.items)
    assert any("링크가 사람 확인 전" in n for n in out.notes)


def test_paid_sources_are_shown_with_a_warning_not_silently_kept():
    """유료를 숨기면 사용자가 결제 화면에서 처음 안다."""
    out = R.recommend(LSMNM, use_case="competitor_analysis", limit=100)
    icsg = [r for r in out.items if r.source.source_key == "ICSG"]
    assert icsg, "유료라고 배제하지 않는다 — 구독이 있는 회사가 있다"
    assert any("이용조건" in w or "유료" in w for w in icsg[0].warnings)


def test_paid_sources_can_be_filtered_out_on_request():
    out = R.recommend(LSMNM, use_case="competitor_analysis",
                      include_paid=False, limit=100)
    keys = {r.source.source_key for r in out.items}
    assert "ILZSG" not in keys          # access="paid"
    assert any(e.source_key == "ILZSG" and "유료" in e.reason for e in out.excluded)


def test_process_intel_finds_the_regulatory_filings():
    """★ 2026-09-08 논의의 실제 해답 — 「경쟁사 공정은 공개 자료에 없다」가 아니다.

    개인 블로그를 믿는 대신 같은 조각을 1차 출처(허가서·평가서·특허)에서 받는다."""
    keys = {r.source.source_key
            for r in R.recommend(LSMNM, use_case="process_intel", limit=100).items}
    assert {"NIER_IEPS", "EIASS", "KIPRIS"} <= keys


def test_regulatory_filings_carry_the_strongest_evidence_level():
    for key in ("NIER_IEPS", "EIASS", "KIPRIS", "DART_MAJOR"):
        assert RC.get(key).evidence_level == "PUBLIC_FILING"


# ── 어휘·카탈로그 건강 ──────────────────────────────────────────────────────
def test_the_catalog_checks_itself():
    RC.assert_catalog_sane()


def test_the_catalog_reuses_the_existing_evidence_vocabulary():
    """★ 근거 등급을 여기서 다시 정의하면 두 곳이 갈린다."""
    from core.enterprise_context.competitor_reference import EVIDENCE_LEVELS
    for s in RC.CATALOG:
        assert s.evidence_level in EVIDENCE_LEVELS


def test_the_catalog_reuses_the_existing_grade_vocabulary():
    from core.external_intelligence import GRADES
    for s in RC.CATALOG:
        assert s.trust_grade in GRADES


def test_a_bad_catalog_entry_is_caught(monkeypatch):
    """★★★ 「검사가 있다」가 아니라 「검사가 «걸린다»」를 증명한다."""
    broken = RC.CATALOG + (RC._s(
        source_key="BROKEN", name_ko="깨진 항목", publisher="x",
        home_url="https://x/", listing_url="https://x/", series=("s",),
        what_it_gives="x", industry_codes=(), topics=("없는주제",),
        use_cases=("competitor_analysis",), language="ko", access="free",
        update_cycle="x", target_contract_keys=(), evidence_level="VERIFIED_RESEARCH",
        trust_grade="gold"),)
    monkeypatch.setattr(RC, "CATALOG", broken)
    with pytest.raises(RC.ResearchCatalogError):
        RC.assert_catalog_sane()


def test_a_paid_source_without_caveats_is_rejected(monkeypatch):
    broken = RC.CATALOG + (RC._s(
        source_key="PAID_NO_WARN", name_ko="유료인데 경고 없음", publisher="x",
        home_url="https://x/", listing_url="https://x/", series=("s",),
        what_it_gives="x", industry_codes=(), topics=("거시경제",),
        use_cases=("new_business",), language="en", access="paid",
        update_cycle="x", target_contract_keys=(), evidence_level="VERIFIED_RESEARCH",
        trust_grade="gold"),)
    monkeypatch.setattr(RC, "CATALOG", broken)
    with pytest.raises(RC.ResearchCatalogError, match="이용조건"):
        RC.assert_catalog_sane()


@pytest.mark.parametrize("bad", ["procurement", "COMPETITOR", "", " "])
def test_unknown_use_cases_are_refused_not_ignored(bad):
    if not bad.strip():
        assert R.recommend(LSMNM, use_case=bad).items      # 비면 «거르지 않음»이다
    else:
        with pytest.raises(R.RecommenderError):
            R.recommend(LSMNM, use_case=bad)


def test_unknown_topics_are_refused():
    with pytest.raises(R.RecommenderError):
        R.recommend(LSMNM, topics=["환율변동성"])


def test_topics_narrow_the_list_and_say_why():
    out = R.recommend(LSMNM, topics=["환경규제"], limit=100)
    assert {r.source.source_key for r in out.items} >= {"KEI", "NIER_IEPS"}
    assert R.EXCLUDED_TOPIC in {e.reason for e in out.excluded}


# ── ⑦ 배선 — 「있는가」가 아니라 「부를 수 있는가」 ──────────────────────────
def test_the_routes_are_registered():
    """★ 코드만 있고 부를 데가 없으면 「있는가」만 증명한 셈이다."""
    import main
    paths = {getattr(r, "path", "") for r in main.app.routes}
    assert "/api/v1/external/research/sources" in paths
    assert "/api/v1/external/research/recommend" in paths


def test_the_routes_declare_their_authority():
    """⚠️ 권한표에 없으면 관문이 무엇을 요구할지 모른다.

    ★ 상태 코드(401)로 확인하지 «않는» 이유: 시험 환경은 `org_enforce` 가 기본 False 라
      관문이 강제되지 않는다. 여기서 200 이 나온다고 「통제가 없다」는 뜻이 아니고,
      401 이 나온다고 「통제가 있다」는 뜻도 아니다 — **표에 실렸는지가 통제다.**
      (실서버에서 눌러 보면 미인증 401 이다. 그것은 별도로 확인했다.)"""
    from core.route_authority import ROUTE_CAPS
    for path in ("GET /api/v1/external/research/sources",
                 "POST /api/v1/external/research/recommend"):
        assert path in ROUTE_CAPS, f"{path} 가 권한표에 없습니다"
        assert ROUTE_CAPS[path], f"{path} 의 권한이 비어 있습니다"


def test_the_endpoint_returns_the_closed_lists_and_the_notice():
    """화면이 문구·목록을 새로 지어내지 않도록 서버가 다 준다."""
    from fastapi.testclient import TestClient
    import main
    body = TestClient(main.app).get("/api/v1/external/research/sources").json()
    data = body["data"]
    assert data["total_in_catalog"] == len(RC.CATALOG)
    assert set(data["use_cases"]) == set(RC.USE_CASES)
    assert set(data["topics"]) == set(RC.TOPICS)
    assert "시스템이 해당 사이트에 접속하지 않습니다" in data["notice"]
    assert data["unverified_links"] == len(RC.CATALOG)     # 아직 아무도 확인 안 했다


def test_the_recommend_endpoint_accounts_for_every_source():
    from fastapi.testclient import TestClient
    import main
    r = TestClient(main.app).post("/api/v1/external/research/recommend",
                                  json={"company_name": "LS MnM",
                                        "industry_code": "C2412",
                                        "use_case": "process_intel", "limit": 3})
    data = r.json()["data"]
    assert data["accounted"] is True
    assert len(data["items"]) + len(data["excluded"]) == data["total_in_catalog"]
    assert all(e["reason"] for e in data["excluded"])
    assert data["items"][0]["action"]["open"].startswith("http")


def test_an_unknown_use_case_is_refused_by_the_endpoint():
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)
    assert c.get("/api/v1/external/research/sources?use_case=nope").status_code == 400
    assert c.post("/api/v1/external/research/recommend",
                  json={"use_case": "nope"}).status_code == 400
