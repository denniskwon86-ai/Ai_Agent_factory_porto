"""[D-017 §9 P4-3 / P4-4] 추천 기능 — **틀린 추천은 침묵보다 나쁘다.**

집계는 틀려도 「숫자가 이상하다」로 드러난다. 추천은 다르다 — 사람이 그것을 근거로
**되돌리기 어려운 행동**을 한다. 전사 승격은 회수해도 이미 본 사람이 있고, 자산 정리는
지운 뒤에 필요했다는 것을 안다.

설계: `docs/design_p4_recommendations_2026-08-07.md`
"""
import pytest

from core import asset_dedup as dd
from core import promotion_advisor as pa


def _gate(promotable=True, checks=None, assets=None):
    return {"promotable": promotable, "checks": checks or [],
            "linked_assets": assets or ["a1"]}


# ══ P4-3 승격 추천 ══════════════════════════════════════════════════════════

def test_only_promotable_is_recommended():
    out = pa.recommend(evaluate=lambda rid, ts, **kw: _gate(promotable=(rid == "ok")),
                       releases=["ok", "no"])
    assert [r["release_id"] for r in out["recommended"]] == ["ok"]
    assert [r["release_id"] for r in out["almost"]] == ["no"]


def test_unverifiable_is_never_recommended():
    """★★★ 이 파일에서 가장 중요한 검사.

    게이트에서 **가장 흔한 상태가 `unverifiable`** 이다(「사용 자산을 모르므로 검사할 수
    없다」). 그것을 통과로 세면 거의 전부가 추천되고, 실제로 신청하면 막힌다 — 그때 사용자는
    추천을 신뢰하지 않게 되고 이 기능은 있으나 마나가 된다."""
    checks = [{"check": "quality", "state": "unverifiable", "why": "기록 없음",
               "suggested_action": "게이트를 통과시키십시오"}]
    out = pa.recommend(evaluate=lambda rid, ts, **kw: _gate(False, checks), releases=["r1"])
    assert out["recommended"] == []
    row = out["almost"][0]
    assert row["unverifiable_count"] == 1 and row["fail_count"] == 0
    assert "unverifiable" in out["rule"]


def test_advisor_does_not_recompute_the_verdict():
    """★★ `promotable` 을 **그대로** 쓴다 — 다시 세면 화면과 게이트가 다른 말을 한다.

    게이트가 `promotable=False` 인데 checks 가 비어 있어도(우리가 모르는 이유로 막힌 경우)
    추천하지 않아야 한다."""
    out = pa.recommend(evaluate=lambda rid, ts, **kw: _gate(False, checks=[]), releases=["r1"])
    assert out["recommended"] == []


def test_blocking_action_comes_from_the_gate():
    """★ 해소 방법을 여기서 새로 짓지 않는다 — 두 곳에서 지으면 서로 다른 말을 한다."""
    checks = [{"check": "security", "state": "fail", "why": "PII 포함",
               "suggested_action": "민감 필드를 제거하십시오"}]
    out = pa.recommend(evaluate=lambda rid, ts, **kw: _gate(False, checks), releases=["r1"])
    assert out["almost"][0]["blocking"][0]["suggested_action"] == "민감 필드를 제거하십시오"


def test_unreadable_gate_is_counted_not_dropped():
    """★★ 조용히 빼면 「검사했는데 없음」과 「검사를 못 함」이 뭉개진다."""
    def _ev(rid, ts, **kw):
        if rid == "bad":
            raise RuntimeError("gate down")
        return _gate(True)

    out = pa.recommend(evaluate=_ev, releases=["ok", "bad"])
    assert out["coverage"]["unreadable"] == 1
    assert "gate down" in out["coverage"]["unreadable_detail"][0]
    assert "«추천 대상 아님» 이 아닙니다" in out["coverage"]["note"]


def test_unreadable_library_is_not_empty_recommendation(monkeypatch):
    """라이브러리를 못 읽은 것과 추천할 것이 없는 것은 다르다."""
    monkeypatch.setattr(pa, "_releases", lambda: None)
    out = pa.recommend()
    assert out["coverage"]["unreadable"] is None
    assert "«추천할 것이 없다» 가 아닙니다" in out["coverage"]["note"]


def test_almost_is_sorted_by_closeness():
    """가까운 것부터 — 막힌 항목이 적을수록 위로."""
    def _ev(rid, ts, **kw):
        n = int(rid[-1])
        return _gate(False, [{"check": f"c{i}", "state": "fail"} for i in range(n)])

    out = pa.recommend(evaluate=_ev, releases=["r3", "r1", "r2"])
    assert [r["release_id"] for r in out["almost"]] == ["r1", "r2", "r3"]


def test_project_id_is_read_not_derived():
    """⚠️ 릴리스 id 에서 프로젝트 이름을 잘라내지 않는다.

    게이트 자신이 「릴리스 id 에서 이름을 추론하면 명명 규칙이 바뀔 때 조용히 틀린다」고
    적어 두었다."""
    import inspect
    src = inspect.getsource(pa._project_of)
    assert "release_json" in src
    assert "split" not in src and "rsplit" not in src


def test_route_requires_governance():
    import inspect

    import api.routes.workspace_control as wc
    src = inspect.getsource(wc.promotion_recommendations)
    assert "assert_governance_readable(p)" in src


# ══ P4-4 중복 탐지 ══════════════════════════════════════════════════════════

def _item(i, text, kind="file_skill"):
    return {"id": i, "kind": kind, "where": f"skills/{i}", "text": text}


def test_identical_after_normalization():
    """공백·주석·front matter 차이는 **같은 것**으로 본다."""
    a = _item("a.md", "---\nname: x\n---\n# 제목\n\n본문   입니다.")
    b = _item("b.md", "<!-- 주석 -->\n# 제목\n본문 입니다.")
    out = dd.find_duplicates([a, b])
    assert len(out["identical"]) == 1
    assert {m["id"] for m in out["identical"][0]["members"]} == {"a.md", "b.md"}


def test_similar_is_separate_from_identical():
    """★★★ [사용자 결정 2026-08-07 안 B] 확신의 차이를 화면에서 지우지 않는다.

    ⚠️ 같은 목록에 섞으면 사람은 전체를 같은 무게로 읽고, 한 번 잘못 지우면 다시는 이
      목록을 쓰지 않는다."""
    base = "# 스킬\n" + "\n".join(f"- 항목 {i}" for i in range(40))
    a = _item("a.md", base)
    b = _item("b.md", base + "\n- 항목 40")
    out = dd.find_duplicates([a, b])
    assert out["identical"] == []
    assert len(out["similar"]) == 1 and out["similar"][0]["similarity"] >= dd.SIMILAR_THRESHOLD


def test_identical_members_are_not_repeated_in_similar():
    """같은 항목을 두 목록에 올리면 사용자가 두 번 판단하게 된다."""
    a = _item("a.md", "같은 내용")
    b = _item("b.md", "같은 내용")
    out = dd.find_duplicates([a, b])
    assert out["identical"] and out["similar"] == []


def test_distinct_items_are_not_flagged():
    """⚠️ 오탐 하나가 목록 전체의 신뢰를 깎는다."""
    out = dd.find_duplicates([_item("a.md", "완전히 다른 내용 하나"),
                              _item("b.md", "전혀 관계없는 다른 글 둘")])
    assert out["identical"] == [] and out["similar"] == []


def test_unused_is_declared_unavailable_not_empty():
    """★★★ **빈 목록은 「정리할 것이 없다」로 읽힌다.**

    자산에 사용 이력이 없고 에이전트 귀속률이 8% 인 상태에서 「호출 0건 = 미사용」이라고
    제안하면, 관측되지 않았을 뿐인 자산을 지우라고 말하게 된다."""
    out = dd.find_duplicates([])
    assert out["unused"]["available"] is False
    assert "정리할 것이 없다" in out["unused"]["note"]


def test_action_note_is_choose_not_delete():
    """제안은 «지워라» 가 아니라 «둘 중 하나를 고르라» 다."""
    note = dd.find_duplicates([])["action_note"]
    assert "고르십시오" in note
    # ⚠️ 스킬 삭제의 조용한 부작용을 반드시 말한다.
    assert "조용히 강등" in note


def test_source_error_is_reported():
    """원천을 못 읽었으면 «중복이 없다» 가 아니다."""
    src = dd.find_duplicates()          # 실제 원천을 읽는다
    cov = src["coverage"]
    assert "compared" in cov and "errors" in cov
    if cov["errors"]:
        assert "«중복이 없다» 는 뜻이 아닙니다" in cov["note"]


def test_no_llm_call_in_dedup():
    """★ §6.1 「단순 LLM 평가 금지」 — 근거를 설명할 수 없는 삭제 제안은 아무도 실행하지 않는다."""
    import inspect
    src = inspect.getsource(dd)
    for bad in ("llm_gateway", "gateway.aexecute", "generate_content"):
        assert bad not in src, f"중복 판정이 LLM 을 부른다: {bad}"


def test_hygiene_route_requires_governance():
    import inspect

    import api.routes.telemetry_control as tc
    assert "assert_governance_readable(p)" in inspect.getsource(tc.asset_hygiene)


# ══ 라우트를 실제로 호출한다 ════════════════════════════════════════════════
#
# ★★★ [2026-08-07 실측] `asset-hygiene` 이 **500** 이었다 — `telemetry_control` 에
#   `asyncio` import 가 없었다. 위의 «소스에 이 문자열이 있는가» 검사는 전부 초록이었다.
#   **소스 문자열 검사는 배선을 확인하지만 실행을 확인하지 못한다.**
#   그래서 두 라우트를 실제로 호출한다.
@pytest.fixture()
def client(monkeypatch, ecm_org_seed):
    import config
    from core.org_directory import org_directory
    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    from fastapi.testclient import TestClient
    from main import app
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


@pytest.mark.parametrize("url", [
    "/api/v1/workspace/promotions/recommendations",
    "/api/v1/telemetry/asset-hygiene",
])
def test_routes_actually_run(client, url):
    """★ 200 이 아니어도 좋다 — **500 이 아니어야** 한다.

    권한 때문에 403 이 나는 것은 통제가 작동한 것이고, 500 은 코드가 깨진 것이다."""
    r = client.get(url, headers={"X-Factory-User": "hikwon@lsmnm.com"})
    assert r.status_code != 500, f"{url} 가 500 이다: {r.text[:300]}"
    assert r.status_code in (200, 401, 403), f"{url} → {r.status_code}: {r.text[:200]}"


@pytest.mark.parametrize("url", [
    "/api/v1/workspace/promotions/recommendations",
    "/api/v1/telemetry/asset-hygiene",
])
def test_routes_are_closed_to_viewer(client, url):
    """자격은 「전사 정비 상태」 기준이다 — 어디가 비어 있는지는 그 자체로 보호 대상이다."""
    r = client.get(url, headers={"X-Factory-User": "hikwon_17@lsmnm.com"})
    assert r.status_code == 403, f"{url} 가 viewer 에게 {r.status_code} 다"
