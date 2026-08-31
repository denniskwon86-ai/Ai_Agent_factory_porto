"""[§5.5 / §14 M5] 전사 자비스 기반 — 권한 범위 안의 전사 상태 집계.

제품 성경 §5.5 는 "권한 범위 내에서 ... 이해하고 안내"를 요구한다. 그 요구가 코드에서
지켜지는지 이 파일이 잠근다:

  · 읽지 못한 소스를 **"이상 없음"으로 두지 않는다**(unavailable + complete=False)
  · 비용 단가를 모르면 총액을 **하한으로 표시**한다(0 으로 삼키지 않는다)
  · `unverifiable` 게이트는 통과가 아니다
  · 상한으로 자른 것은 **자랐다고 말한다**
  · 권한 필터가 깨지면 전체를 돌려주지 않는다(fail-closed)
  · 항목마다 "무엇을 하면 풀리는가"가 있다
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import enterprise_briefing as ebmod
from core.enterprise_briefing import SECTIONS, SEVERITY_ORDER, EnterpriseBriefing


@pytest.fixture()
def eb():
    return EnterpriseBriefing()


# ── 빈 소스 스텁 — 각 테스트가 필요한 것만 채운다 ─────────────────────────────
class _WS:
    def __init__(self, promos=None, gate=None):
        self._p = promos or {}
        self._g = gate or {}

    def list_promotions(self, status=""):
        return self._p.get(status, [])

    def evaluate_gate(self, release_id, target_scope="enterprise", **kw):
        return self._g.get(release_id, {"promotable": True, "checks": []})


class _Shadow:
    def __init__(self, s=None):
        self._s = s or {"by_review_status": {}, "incomparable": []}

    def summary(self, *a, **k):
        return self._s


class _Reg:
    def __init__(self, conns=None, contracts=None):
        self._c = conns or []
        self._ct = contracts or {}

    def list_connectors(self, *a, **k):
        return self._c

    def list_contracts(self, cid):
        return self._ct.get(cid, [])


class _Skills:
    def __init__(self, n=0):
        self._n = n

    def list_pending_proposals(self):
        return [{"id": i} for i in range(self._n)]


class _Decisions:
    def __init__(self, rows=None):
        self._rows = rows or []

    def queue(self, actor):
        return list(self._rows)


class _Catalog:
    def __init__(self, gaps=None):
        self._g = gaps or []

    def governance_gaps(self, *a, **k):
        return self._g


class _Contracts:
    def __init__(self, results=None):
        self._r = results or []

    def evaluate_all(self, catalog=None):
        return {"total": len(self._r), "by_state": {}, "results": self._r}


class _Life:
    def __init__(self, rows=None):
        self._r = rows or []

    def list_statuses(self, status=""):
        return self._r


@pytest.fixture()
def wire(monkeypatch):
    """모든 소스를 빈 스텁으로 고정한다 — 실제 DB 상태가 테스트 결과를 흔들면 안 된다."""
    def _do(**kw):
        import core.connector_registry as cr
        import core.data_catalog as dc
        import core.data_contract as dct
        import core.decision_case as dcase
        import core.program_lifecycle as pl
        import core.shadow_mode as sm
        import core.skill_evolution as se
        import core.workspace_promotion as wp
        monkeypatch.setattr(wp, "workspace", kw.get("ws") or _WS(), raising=False)
        monkeypatch.setattr(sm, "shadow_mode", kw.get("shadow") or _Shadow(), raising=False)
        monkeypatch.setattr(cr, "connector_registry", kw.get("reg") or _Reg(), raising=False)
        monkeypatch.setattr(se, "skill_evolution", kw.get("skills") or _Skills(),
                            raising=False)
        monkeypatch.setattr(dcase, "decision_case", kw.get("decisions") or _Decisions(),
                            raising=False)
        monkeypatch.setattr(dc, "data_catalog", kw.get("catalog") or _Catalog(),
                            raising=False)
        monkeypatch.setattr(dct, "data_contracts", kw.get("contracts") or _Contracts(),
                            raising=False)
        monkeypatch.setattr(pl, "program_lifecycle", kw.get("life") or _Life(),
                            raising=False)
    return _do


def _cost(monkeypatch, **totals):
    """비용 집계를 대체한다 — 실제 로그를 읽으면 결과가 매번 달라진다."""
    def fake(self, principal=None):
        d = {"available": True, "calls": 0, "cost_usd": 0.0, "priced_calls": 0,
             "unpriced_calls": 0, "cost_complete": True, "note": ""}
        d.update(totals)
        return d
    monkeypatch.setattr(EnterpriseBriefing, "cost", fake, raising=True)


# ── 선언한 상수가 실제로 쓰이는가 ────────────────────────────────────────────
def test_sections_constant_matches_response(eb, wire, monkeypatch):
    """★ 선언만 하고 안 쓰는 상수는 이 저장소의 지배적 결함이다."""
    wire()
    _cost(monkeypatch)
    b = eb.briefing()
    assert set(b["sections"]) == set(SECTIONS)


# ── 읽지 못한 것을 "이상 없음"으로 두지 않는다 ───────────────────────────────
def test_broken_source_is_reported_not_silently_empty(eb, wire, monkeypatch):
    """★★ 조용히 빠진 위험이 가장 위험하다. 실패는 unavailable 로 올라와야 한다."""
    class _Boom:
        def list_promotions(self, status=""):
            raise RuntimeError("db locked")
        def evaluate_gate(self, *a, **k):
            raise RuntimeError("db locked")
    wire(ws=_Boom())
    _cost(monkeypatch)
    b = eb.briefing()
    assert b["complete"] is False
    srcs = {u["source"] for u in b["unavailable"]}
    assert "workspace_promotion.list_promotions" in srcs
    assert any("db locked" in u["error"] for u in b["unavailable"])
    assert "문제 없음을 의미하지 않습니다" in b["note"].replace("'", "")


def test_complete_true_only_when_nothing_missing(eb, wire, monkeypatch):
    wire()
    _cost(monkeypatch, cost_complete=True)
    assert eb.briefing()["complete"] is True


def test_incomplete_cost_makes_briefing_incomplete(eb, wire, monkeypatch):
    """★★ 단가를 모르는 호출이 있으면 총액은 하한이다 — 완전한 총액으로 읽히면 예산 판단이 틀린다."""
    wire()
    _cost(monkeypatch, cost_complete=False, unpriced_calls=49, cost_usd=5.68)
    b = eb.briefing()
    assert b["complete"] is False
    assert "하한" in b["note"]


def test_cost_unavailable_is_recorded(eb, wire, monkeypatch):
    wire()
    monkeypatch.setattr(EnterpriseBriefing, "cost",
                        lambda self, principal=None: {"available": False,
                                                      "reason": "로그 없음"},
                        raising=True)
    b = eb.briefing()
    assert any(u["section"] == "cost" for u in b["unavailable"])
    assert b["complete"] is False


# ── 권한 필터는 fail-closed ──────────────────────────────────────────────────
def test_scope_filter_failure_does_not_leak_everything(eb, monkeypatch):
    """★★ 전사 보좌에서 범위 오류의 기본값이 "전체 노출"이면 그 한 번으로 제품이 끝난다."""
    import core.enterprise_context.scoping as sc
    def boom(*a, **k):
        raise RuntimeError("scope db down")
    monkeypatch.setattr(sc, "filter_visible", boom, raising=False)
    with pytest.raises(RuntimeError):
        eb._visible([{"from_scope": "n1"}], "node_a", "t1", "REAL", "from_scope")


def test_no_scope_means_no_filter(eb):
    """조직 미도입 상태에서 필터를 강제하면 아무것도 안 보인다 — 하위호환 계약."""
    rows = [{"from_scope": ""}]
    assert eb._visible(rows, "", "", "REAL", "from_scope") == rows


# ── 내가 결정해야 하는 것 ────────────────────────────────────────────────────
def test_requested_promotion_becomes_high_decision(eb, wire, monkeypatch):
    wire(ws=_WS(promos={"requested": [
        {"release_id": "app1", "from_scope": "", "target_scope": "enterprise",
         "requested_by": "kim"}]}))
    _cost(monkeypatch)
    items = eb.briefing()["sections"]["my_decisions"]["items"]
    it = next(i for i in items if i["kind"] == "promotion_requested")
    assert it["severity"] == "high" and "kim" in it["why"]
    assert it["suggested_action"], "무엇을 하면 풀리는지 없으면 대시보드지 보좌가 아니다"


def test_approved_but_not_promoted_is_surfaced(eb, wire, monkeypatch):
    """★ 승인만으로는 전사 앱이 되지 않는다 — 여기서 멈춘 것을 아무도 모르면 방치된다."""
    wire(ws=_WS(promos={"approved": [
        {"release_id": "app2", "from_scope": "", "target_scope": "enterprise",
         "requested_by": "lee"}]}))
    _cost(monkeypatch)
    kinds = [i["kind"] for i in eb.briefing()["sections"]["my_decisions"]["items"]]
    assert "promotion_approved" in kinds


def test_검토_요청된_실제_안건이_경영_홈_대기열에_오른다(eb, wire, monkeypatch):
    """초안은 숨기되 사람이 답해야 하는 실제 안건은 첫 화면에 보여야 한다."""
    wire(decisions=_Decisions([
        {"decision_id": "dec_draft", "status": "DRAFT", "my_role": "REQUESTER",
         "question": "아직 작성 중인 초안", "due_at": ""},
        {"decision_id": "dec_live", "status": "REVIEW_REQUESTED", "my_role": "DECIDER",
         "question": "원료 지연에 맞춰 생산계획을 조정할 것인가", "due_at": "2026-09-04",
         "package": {
             "baseline": {"data_kind": "DEMO/SYNTHETIC"},
             "options": {"compared": [
                 {"key": "production_qty", "label": "생산량", "unit": "ton",
                  "base": 12000, "scenario": 7200, "delta": -4800, "delta_pct": -40},
                 {"key": "purchase_payment", "label": "구매지급", "unit": "원",
                  "base": 1, "scenario": 2, "delta": 1, "delta_pct": 100},
             ]},
         }},
        {"decision_id": "dec_done", "status": "DECIDED", "my_role": "DECIDER",
         "question": "이미 끝난 결정", "due_at": ""},
    ]))
    _cost(monkeypatch)
    items = [i for i in eb.briefing(actor="admin")["sections"]["my_decisions"]["items"]
             if i["kind"] == "decision_case_pending"]
    assert len(items) == 1
    assert items[0]["ref"] == "dec_live" and items[0]["ref_type"] == "decision_case"
    assert items[0]["severity"] == "high"
    assert "원료 지연" in items[0]["title"] and "2026-09-04" in items[0]["why"]
    assert items[0]["data_kind"] == "DEMO/SYNTHETIC"
    assert [r["key"] for r in items[0]["impact_rows"]] == ["production_qty"]
    assert items[0]["impact_rows"][0]["scenario"] == 7200


def test_근거가_바뀐_안건은_결정자_아니어도_높은_우선순위다(eb, wire, monkeypatch):
    wire(decisions=_Decisions([
        {"decision_id": "dec_changed", "status": "EVIDENCE_CHANGED",
         "my_role": "REQUESTER", "question": "바뀐 근거를 다시 볼 것인가", "due_at": ""},
    ]))
    _cost(monkeypatch)
    item = next(i for i in eb.briefing(actor="owner")["sections"]["my_decisions"]["items"]
                if i["kind"] == "decision_case_pending")
    assert item["severity"] == "high"
    assert "근거가 바뀌" in item["why"]


def test_unapproved_query_contract_is_high(eb, wire, monkeypatch):
    """★ 승인 안 된 계약은 조회가 거부된다 — "연계가 되는데 안 되는" 전형적 원인이다."""
    wire(reg=_Reg(conns=[{"connector_id": "erp"}],
                  contracts={"erp": [{"query_name": "wo", "approved_by": ""},
                                     {"query_name": "ok", "approved_by": "admin"}]}))
    _cost(monkeypatch)
    items = [i for i in eb.briefing()["sections"]["my_decisions"]["items"]
             if i["kind"] == "query_contract_unapproved"]
    assert len(items) == 1 and "wo" in items[0]["title"]


def test_incomparable_shadow_run_is_judgement_unavailable_not_failure(eb, wire, monkeypatch):
    """★★ 비교 불가는 실패가 아니다. **그 뜻을 사용자 말로** 전한다.

    ## ⚠️⚠️ [2026-08-24] 이 시험이 전문용어를 계약으로 붙들고 있었다

    종전 단언은 `"판정 불가" in inc["why"]` 였다. 그런데 사용자가 그 화면을 보고
    「도대체 무슨 말인지 모르겠다」고 했다 — `run`·`판정 불가`·`기준선/후보`·
    `입력 스냅샷` 은 전부 우리 안에서만 쓰는 말이다.

    ★ 지켜야 하는 것은 **낱말이 아니라 뜻**이다: ① 실패로 읽히면 안 되고 ② 왜 못
      견줬는지 말해야 하고 ③ 무엇을 하면 되는지 말해야 한다. 그 셋을 단언한다.
    ⚠️ 낱말을 단언하면 문구를 고칠 때마다 시험이 깨지고, 그러면 **문구를 안 고치게
      된다** — 시험이 사용자를 막는 자리에 서 버린다.
    """
    wire(shadow=_Shadow({"by_review_status": {"pending": 2},
                         "incomparable": [{"run_id": "r1", "name": "원가 v2",
                                           "reason": "입력 해시 불일치"}]}))
    _cost(monkeypatch)
    items = eb.briefing()["sections"]["my_decisions"]["items"]
    inc = next(i for i in items if i["kind"] == "shadow_incomparable")

    #: ① 실패가 아니다 — 「실패」로 단정하는 말을 쓰지 않는다.
    assert "실패했" not in inc["why"] and "오류" not in inc["why"], inc["why"]
    #: ② 왜 못 견줬는지 — 「서로 다른 자료」라는 사실과, 서버가 준 사유를 함께 전한다.
    assert "다른 자료" in inc["why"], inc["why"]
    assert "입력 해시 불일치" in inc["why"], "서버가 준 사유를 버리면 원인을 못 찾는다"
    #: ③ 무엇을 하면 되는가 — 행동이 비어 있으면 사용자는 멈춘다.
    assert inc["suggested_action"].strip(), inc
    #: ★ 제목에 사람이 붙인 이름이 들어간다(해시 id 가 아니다).
    assert "원가 v2" in inc["title"], inc["title"]
    assert any(i["kind"] == "shadow_review_pending" for i in items)


def test_이름_없는_비교는_해시_id_를_제목에_쓰지_않는다(eb, wire, monkeypatch):
    """★★★ [2026-08-24 사용자 지적] 「sh_a111029126ae 이런 게 화면에 자꾸 노출된다」.

    이름이 없으면 종전에는 **해시 id 가 그대로 제목**이었다. 사용자에게 그 문자열은
    아무 뜻도 없고, 무엇에 대한 이야기인지조차 알려 주지 않는다.

    ⚠️ 그렇다고 버리지도 않는다 — 같은 종류가 여럿일 때 구분해야 하고, 문의할 때
      그 값으로 찾는다. **꼬리표로 남긴다.**"""
    wire(shadow=_Shadow({"incomparable": [{"run_id": "sh_a111029126ae", "name": ""}]}))
    _cost(monkeypatch)
    inc = next(i for i in eb.briefing()["sections"]["my_decisions"]["items"]
               if i["kind"] == "shadow_incomparable")
    assert "sh_a111029126ae" not in inc["title"], inc["title"]
    assert "이름 없는" in inc["title"], inc["title"]
    assert "9126ae" in inc["title"], "꼬리표까지 버리면 어느 것인지 찾을 수 없다"
    #: ★ 원래 값은 `ref` 로 그대로 간다 — 화면이 그것으로 해당 항목을 연다.
    assert inc["ref"] == "sh_a111029126ae"


def test_pending_skill_proposals_are_low_not_hidden(eb, wire, monkeypatch):
    wire(skills=_Skills(3))
    _cost(monkeypatch)
    it = next(i for i in eb.briefing()["sections"]["my_decisions"]["items"]
              if i["kind"] == "skill_proposal_pending")
    assert it["severity"] == "low" and "3" in it["title"]


# ── 막힌 이유 ────────────────────────────────────────────────────────────────
def test_unverifiable_gate_check_is_not_treated_as_pass(eb, wire, monkeypatch):
    """★★ 확인 못 한 것을 통과로 두면 게이트가 장식이 된다."""
    wire(ws=_WS(
        promos={"requested": [{"release_id": "app1", "from_scope": "",
                               "target_scope": "enterprise"}]},
        gate={"app1": {"promotable": False, "checks": [
            {"check": "security", "state": "pass", "why": "ok"},
            {"check": "quality", "state": "unverifiable", "why": "품질 기록 없음",
             "suggested_action": "품질 게이트를 실행하십시오."},
            {"check": "data_contract", "state": "fail", "why": "위반 중",
             "suggested_action": "위반을 해소하십시오."}]}}))
    _cost(monkeypatch)
    items = eb.briefing()["sections"]["blocked"]["items"]
    kinds = {i["kind"] for i in items}
    assert kinds == {"gate_unverifiable", "gate_fail"}, "pass 는 담지 않는다"
    uv = next(i for i in items if i["kind"] == "gate_unverifiable")
    assert uv["severity"] == "medium" and "통과가 아니라" in uv["why"]
    assert next(i for i in items if i["kind"] == "gate_fail")["severity"] == "high"


def test_promotable_release_is_not_listed_as_blocked(eb, wire, monkeypatch):
    wire(ws=_WS(promos={"requested": [{"release_id": "ok1", "from_scope": "",
                                       "target_scope": "enterprise"}]},
                gate={"ok1": {"promotable": True, "checks": []}}))
    _cost(monkeypatch)
    assert eb.briefing()["sections"]["blocked"]["count"] == 0


def test_gate_truncation_is_reported(eb, wire, monkeypatch):
    """★★ 조용히 자르면 "막힌 게 이것뿐"으로 읽힌다."""
    promos = [{"release_id": f"a{i}", "from_scope": "", "target_scope": "enterprise"}
              for i in range(5)]
    wire(ws=_WS(promos={"requested": promos}))
    _cost(monkeypatch)
    col = eb.blocked(max_gates=2)
    tr = next(i for i in col.items if i["kind"] == "gate_truncated")
    assert "3건" in tr["title"] and "이것뿐이라는" in tr["why"]


# ── 데이터 건강 ──────────────────────────────────────────────────────────────
def test_governance_gaps_carry_severity_and_action(eb, wire, monkeypatch):
    wire(catalog=_Catalog([{"kind": "sensitivity_below_pii", "severity": "high",
                            "asset_id": "a1", "asset": "고객마스터",
                            "why": "PII 인데 민감도가 낮다",
                            "suggested_action": "민감도를 올리십시오."}]))
    _cost(monkeypatch)
    it = eb.briefing()["sections"]["data_health"]["items"][0]
    assert it["severity"] == "high" and it["ref"] == "a1"
    assert it["suggested_action"] == "민감도를 올리십시오."


def test_breached_contract_is_high_and_unverifiable_is_not_kept(eb, wire, monkeypatch):
    """★★ `unverifiable` 은 dict 목록이다 — 문자열로 가정하면 조용히 깨진다(실측)."""
    wire(contracts=_Contracts([
        {"contract_id": "c1", "contract_key": "k1", "version": 1, "state": "kept",
         "findings": [], "unverifiable": []},
        {"contract_id": "c2", "contract_key": "k2", "version": 2, "state": "breached",
         "findings": [{"why": "필드가 없다"}], "unverifiable": []},
        {"contract_id": "c3", "contract_key": "k3", "version": 1, "state": "unverifiable",
         "findings": [], "unverifiable": [{"kind": "quality", "why": "품질 프로파일 없음"}]},
    ]))
    _cost(monkeypatch)
    items = eb.briefing()["sections"]["data_health"]["items"]
    assert {i["kind"] for i in items} == {"contract_breached", "contract_unverifiable"}
    br = next(i for i in items if i["kind"] == "contract_breached")
    assert br["severity"] == "high" and "필드가 없다" in br["why"]
    uv = next(i for i in items if i["kind"] == "contract_unverifiable")
    assert "품질 프로파일 없음" in uv["why"] and "거짓 안심" in uv["why"]


def test_governance_truncation_is_reported(eb, wire, monkeypatch):
    wire(catalog=_Catalog([{"kind": "k", "severity": "low", "asset_id": f"a{i}",
                            "asset": f"자산{i}", "why": "w", "suggested_action": "s"}
                           for i in range(25)]))
    _cost(monkeypatch)
    col = eb.data_health(max_gaps=5)
    assert any(i["kind"] == "governance_truncated" for i in col.items)


# ── 프로그램 사용여부 ────────────────────────────────────────────────────────
def test_disabled_program_without_replacement_is_high(eb, wire, monkeypatch):
    """★ 대체본이 없으면 사용자가 같은 프로그램을 다시 만든다 — 중복은 그렇게 태어난다."""
    wire(life=_Life([
        {"release_id": "old1", "status": "disabled", "reason": "산식 오류",
         "replacement_release_id": ""},
        {"release_id": "old2", "status": "disabled", "reason": "이전",
         "replacement_release_id": "new2"},
        {"release_id": "old3", "status": "deprecated", "reason": "9월 종료",
         "replacement_release_id": ""},
    ]))
    _cost(monkeypatch)
    items = {i["ref"]: i for i in eb.briefing()["sections"]["programs"]["items"]}
    assert items["old1"]["severity"] == "high" and items["old1"]["suggested_action"]
    assert items["old2"]["severity"] == "medium" and "new2" in items["old2"]["why"]
    assert items["old3"]["kind"] == "program_deprecated"


# ── 요약 ────────────────────────────────────────────────────────────────────
def test_top_is_sorted_by_severity_and_attention_excludes_low(eb, wire, monkeypatch):
    wire(ws=_WS(promos={"requested": [{"release_id": "a", "from_scope": "",
                                       "target_scope": "enterprise"}],
                        "approved": [{"release_id": "b", "from_scope": "",
                                      "target_scope": "enterprise"}]},
                gate={"a": {"promotable": True, "checks": []},
                      "b": {"promotable": True, "checks": []}}),
         skills=_Skills(1))
    _cost(monkeypatch)
    b = eb.briefing()
    sevs = [i["severity"] for i in b["top"]]
    assert sevs == sorted(sevs, key=lambda s: SEVERITY_ORDER.index(s))
    # low(스킬 제안)는 주의 건수에 넣지 않는다 — 넣으면 숫자가 의미를 잃는다.
    assert b["attention_count"] == 2
    assert b["by_severity"]["low"] == 1


def test_scope_is_echoed_so_user_knows_what_they_are_seeing(eb, wire, monkeypatch):
    """★ 무엇을 기준으로 걸러진 화면인지 모르면 "우리 부서 것이 없다"를 오판한다."""
    wire()
    _cost(monkeypatch)
    b = eb.briefing(actor="kim", scope_node_id="node_batt", tenant_id="t1")
    assert b["scope"]["filtered"] is True and b["scope"]["scope_node_id"] == "node_batt"
    assert b["actor"] == "kim"


def test_every_item_has_a_next_action_or_explains_why_not(eb, wire, monkeypatch):
    """★★ 상태만 나열하는 화면은 대시보드지 보좌가 아니다."""
    wire(ws=_WS(promos={"requested": [{"release_id": "a", "from_scope": "",
                                       "target_scope": "enterprise"}]},
                gate={"a": {"promotable": False, "checks": [
                    {"check": "security", "state": "fail", "why": "미검토",
                     "suggested_action": "보안 점검을 실행하십시오."}]}}),
         catalog=_Catalog([{"kind": "k", "severity": "high", "asset_id": "a1",
                            "asset": "자산", "why": "w", "suggested_action": "고치십시오."}]),
         skills=_Skills(1))
    _cost(monkeypatch)
    b = eb.briefing()
    for name in SECTIONS:
        if name == "cost":
            continue
        for i in b["sections"][name]["items"]:
            assert i["suggested_action"] or i["kind"].endswith("_truncated"), \
                f"{i['kind']} 에 다음 행동이 없다"


def test_severity_order_constant_is_used_for_sorting(eb, wire, monkeypatch):
    """선언한 정렬 순서가 실제 정렬에 쓰이는지 — 안 쓰이면 상수가 거짓말이다."""
    assert ebmod._rank("high") < ebmod._rank("medium") < ebmod._rank("low")
    assert ebmod._rank("made_up") == len(SEVERITY_ORDER)


# ══════════════════════════════════════════════════════════════════════
# API 계약 (§7 규약 — 기능은 UI 까지 완결하되, 그 전에 계약을 잠근다)
# ══════════════════════════════════════════════════════════════════════
@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


def test_briefing_route_is_reachable(client):
    r = client.get("/api/v1/briefing")
    assert r.status_code != 404, r.text


def test_briefing_exposes_completeness_at_top_level(client):
    """★★ `complete=false` 를 200 으로 감추지 않는다.

    "위험 0건"과 "위험을 못 읽었다"는 다른 사실이다 — 화면이 구분할 수 있어야 한다."""
    d = client.get("/api/v1/briefing").json()["data"]
    assert "complete" in d and "unavailable" in d
    assert set(d["sections"]) == set(SECTIONS)


def test_actor_comes_from_principal_not_client(client):
    """★★ 클라이언트가 보낸 이름으로 '내가 결정할 것'을 계산하면 **남의 결재함**을 본다."""
    r = client.get("/api/v1/briefing?actor=someone_else",
                   headers={"X-User-Id": "alice"})
    d = r.json()
    assert d["permission"]["actor"] == "alice"
    assert d["data"]["actor"] == "alice"


def test_unknown_section_is_rejected_not_empty(client):
    """★ 오타가 '빈 결과'로 보이면 사용자는 **위험이 없다고 읽는다**."""
    r = client.get("/api/v1/briefing/sections/typo_section")
    assert r.status_code == 400 and "알 수 없는 섹션" in r.json()["detail"]


@pytest.mark.parametrize("section", SECTIONS)
def test_each_section_is_individually_fetchable(client, section):
    r = client.get(f"/api/v1/briefing/sections/{section}")
    assert r.status_code == 200, r.text
    assert r.json()["section"] == section


def test_section_also_reports_unavailable(client):
    """섹션 단위 조회에서도 실패를 삼키지 않는다 — 전체 조회와 같은 규칙이다."""
    d = client.get("/api/v1/briefing/sections/blocked").json()["data"]
    assert "unavailable" in d and "complete" in d


def test_denied_scope_is_404_and_audited(client, tmp_path, monkeypatch):
    """★★ 전사 보좌에서 범위 오류의 기본값이 '전체 노출'이면 그 한 번으로 제품이 끝난다.

    거부는 404 로 은폐하되 감사로그에는 실제 요청 범위가 남는다."""
    import core.scope_guard as sg
    from core.enterprise_context import audit
    monkeypatch.setattr(audit, "_LOG_PATH", str(tmp_path / "audit.jsonl"))
    # ★ [2026-08-05 / D-018 ③④] 패치 지점이 **한 곳으로 모였다.** 종전에는 라우터마다
    #   `from ... import resolve_effective_scope` 로 이름을 들고 있어 **그 라우터 모듈**을
    #   패치해야 했고(라우터가 셋이면 패치 지점도 셋), 잘못 패치하면 테스트가 조용히 통과하며
    #   "거부가 동작한다"고 착각하게 됐다. 지금은 `api.deps.assert_scope_allowed` 가 호출
    #   시점에 `core.scope_guard` 에서 가져오므로 **원본 모듈만 패치하면 전 경로에 걸린다.**
    # ⚠️ 시그니처가 `(p, requested, tenant_id, entity_mode)` 로 늘었다 — `*a, **kw` 로 받는다.
    #   인자를 고정하면 호출부가 문맥을 넘기기 시작할 때 이 테스트만 조용히 깨진다.
    monkeypatch.setattr(sg, "resolve_effective_scope",
                        lambda p, req="", *a, **kw: sg.EffectiveScope(
                            denied=True, actor="bob", allowed_scopes=["MNM_BATTERY"],
                            reason="requested_scope_not_in_actor_scopes"))

    r = client.get("/api/v1/briefing?scope_node_id=MNM_COPPER")
    assert r.status_code == 404
    e = audit.recent(1)[0]
    assert e["event"] == audit.ACCESS_DENIED_SCOPE_MISMATCH
    assert e["requested_scope"] == "MNM_COPPER"
