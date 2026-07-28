# ==========================================
# M0 통합 회귀 — 상담부터 게시까지 **한 줄로 관통**하는 이음매 테스트
#
# ## 왜 이 파일이 따로 필요한가
#
# 기존 테스트는 계층·단위별로 쪼개져 있어서 각자 잘 동작한다. 그런데 이번 M0 구현에서 나온
# 결함 5건은 **전부 경계를 넘는 배선 누락**이었다 — "A가 읽는데 B가 채워주지 않는" 유형:
#   ① `create_release` 가 `owner_dept_id` 를 인덱싱 메타로 안 넘겨 과거사례 RAG 가 조용히 0건
#   ② 텔레메트리 집계가 부서를 읽는데 기록부가 안 실음
#   ③ `get_blueprint_row` 가 문맥 키를 SELECT 하지 않아 다른 테넌트 자료가 통과
#   ④ `provision_project` 시그니처에 `blueprint_id` 누락
#   ⑤ 결정 이력 조회가 subject 기준이라 프로젝트 생성 이벤트가 빠짐
# 단위 테스트는 다섯 개 모두 놓쳤다(각 계층은 자기 몫을 정확히 했으므로). 그래서 **이음매를
# 지나가는 흐름 자체**를 테스트한다.
#
# 검증 순서 = 사용자가 실제로 하는 순서:
#   플레이북 → 상담 → 답변 → 준비도 → 청사진 → 승인 → 프로젝트 → WBS → 데이터 태스크
#   → 게시(RAG 인덱싱) → 결정 이력 → 체인 무결성
# ==========================================
import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.routes.advisor_control as ac
import api.routes.factory_control as fc
import api.routes.ledger_control as lc
import config
from api.deps import Principal, current_principal
from core.advisor_playbook import load_playbook
from core.advisor_store import AdvisorStore
from core.decision_ledger import DecisionLedger
from core.org_directory import AccessScope
from nodes.utils.wbs_manager import WBSManager

PB_ID = "business_planning"


# ── 하네스 ────────────────────────────────────────────────────────────────
@pytest.fixture
def stack(tmp_path, monkeypatch):
    """상담·감사 저장소를 tmp 로 갈아끼우고 `./projects` 를 tmp 아래로 옮긴다.

    ⚠️ `decision_ledger` 는 **두 곳**에서 참조된다: `advisor_store`/`advisor_control` 은 함수 안에서
      `from core.decision_ledger import decision_ledger` 로 가져오므로 모듈 속성을 갈아야 하고,
      `ledger_control` 은 상단 import 라 그 모듈 속성도 갈아야 한다. 하나만 갈면 기록과 조회가
      **다른 DB** 를 보게 되어 "기록은 됐는데 조회는 비어 있는" 상태가 된다(실제로 겪음)."""
    monkeypatch.chdir(tmp_path)
    import core.decision_ledger as ledger_mod

    ledger = DecisionLedger(db_path=str(tmp_path / "ledger.db"))
    store = AdvisorStore(db_path=str(tmp_path / "advisor.db"))
    monkeypatch.setattr(ledger_mod, "decision_ledger", ledger)
    monkeypatch.setattr(lc, "decision_ledger", ledger)
    monkeypatch.setattr(ac, "advisor_store", store)

    app = FastAPI()
    app.include_router(ac.router)
    app.include_router(fc.router)
    app.include_router(lc.router)
    client = TestClient(app)
    return {"app": app, "c": client, "store": store, "ledger": ledger, "root": tmp_path}


def act_as(app, user_id="bob", dept="hq", readable=None, writable=None, enterprise=False):
    scope = AccessScope(
        user_id=user_id, primary_dept_id=dept, unrestricted=False,
        readable_dept_ids=frozenset(readable if readable is not None else {dept}),
        writable_dept_ids=frozenset(writable if writable is not None else {dept}),
        can_run_enterprise=enterprise)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id=user_id, scope=scope)


def _data(r):
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
    return r.json()["data"]


def answer_all(c, cid, pb, overrides=None):
    """추천안으로 전 문항 답변. `overrides={질문id: 선택지value}` 로 특정 답만 바꾼다."""
    overrides = overrides or {}
    for q in pb.questions:
        pick = overrides.get(q.id) or next(o.key() for o in q.options if o.recommended)
        r = c.post(f"/api/v1/advisor/consultations/{cid}/messages",
                   json={"question_id": q.id, "selected_values": [pick]})
        assert r.status_code == 200, r.text
    return r.json()["data"]


def start(c, prompt="내년도 사업계획을 만들고 부서별로 승인받고 싶습니다"):
    return _data(c.post("/api/v1/advisor/consultations",
                        json={"initial_prompt": prompt, "playbook_id": PB_ID}))


# ══════════════════════════════════════════════════════════════════════════
# ① 답변이 실제로 요구사항 구성을 바꾸는가 (플레이북 → 활성화 → 청사진)
# ══════════════════════════════════════════════════════════════════════════
def test_answers_change_the_requirement_set(stack):
    """★ 조건부 요구사항이 답에 따라 켜져야 한다. 안 켜지면 준비도가 실제보다 높게 나온다."""
    c, app = stack["c"], stack["app"]
    act_as(app)
    pb = load_playbook(PB_ID)

    # (가) 전사 손익 수준 — 원가센터·제품 마스터가 필요 없다
    cid_a = start(c)["consultation"]["consultation_id"]
    answer_all(c, cid_a, pb, overrides={"Q_SCOPE": "company"})
    bp_a = _data(c.post(f"/api/v1/advisor/consultations/{cid_a}/blueprint", json={}))
    keys_a = {r["key"] for r in bp_a["data_requirements"]}

    # (나) 제품·품목 단위 — 제품 마스터와 제품별 원가가 켜진다
    cid_b = start(c)["consultation"]["consultation_id"]
    answer_all(c, cid_b, pb, overrides={"Q_SCOPE": "product"})
    bp_b = _data(c.post(f"/api/v1/advisor/consultations/{cid_b}/blueprint", json={}))
    keys_b = {r["key"] for r in bp_b["data_requirements"]}

    assert "master_product" not in keys_a and "master_product" in keys_b
    assert "actual_product_cost" not in keys_a and "actual_product_cost" in keys_b
    assert keys_a < keys_b, "범위를 넓히면 요구사항이 늘어나야 한다"
    # 필수는 어느 답을 골라도 항상 활성 (M0-a 에서 잡은 저작 불변식)
    required = {r.key for r in pb.data_requirements if r.necessity == "required"}
    assert required <= keys_a and required <= keys_b


def test_out_of_scope_reflects_the_unchosen_option(stack):
    """제외 범위는 추론이 아니라 사실 — 고르지 않은 선택지다."""
    c, app = stack["c"], stack["app"]
    act_as(app)
    pb = load_playbook(PB_ID)
    cid = start(c)["consultation"]["consultation_id"]
    answer_all(c, cid, pb, overrides={"Q_SCOPE": "company"})
    bp = _data(c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={}))
    assert bp["business"]["in_scope"] == ["전사 손익 수준"]
    assert "제품 · 품목 단위" in bp["business"]["out_of_scope"]


def test_statuses_flow_into_readiness(stack):
    """보유 상태가 준비도 점수와 결손 목록에 반영되어야 한다."""
    c, app = stack["c"], stack["app"]
    act_as(app)
    pb = load_playbook(PB_ID)
    cid = start(c)["consultation"]["consultation_id"]
    answer_all(c, cid, pb)

    empty = _data(c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={}))
    assert empty["readiness_score"] == 0.0, "아무것도 없으면 0점"

    cid2 = start(c)["consultation"]["consultation_id"]
    answer_all(c, cid2, pb)
    filled = _data(c.post(f"/api/v1/advisor/consultations/{cid2}/blueprint", json={
        "statuses": {"master_org": "held", "master_account": "held",
                     "master_cost_center": "held", "ownership_data": "held"}}))
    assert filled["readiness_score"] > 0
    held = [r for r in filled["data_requirements"] if r["readiness_status"] == "held"]
    assert len(held) == 4


# ══════════════════════════════════════════════════════════════════════════
# ② ③ ④ 상담 → 청사진 → 프로젝트 → WBS 전 구간 관통 (★ 본체)
# ══════════════════════════════════════════════════════════════════════════
def test_full_flow_consultation_to_release(stack, monkeypatch):
    """★★ 사용자가 실제로 하는 순서 그대로 한 번에 관통한다.

    각 단계가 다음 단계에 필요한 값을 **실제로 넘겨주는지**를 확인한다 — 이 세션의 결함 5건이
    모두 여기서 났다."""
    c, app, ledger, root = stack["c"], stack["app"], stack["ledger"], stack["root"]
    act_as(app, user_id="bob", dept="hq")
    pb = load_playbook(PB_ID)

    # ── 1) 상담 시작: 문맥 3키가 기록되는가 (ECM-lite)
    started = start(c)
    cid = started["consultation"]["consultation_id"]
    assert started["next_question"]["id"] == pb.questions[0].id
    assert started["consultation"]["tenant_id"] == "tenant_default"
    assert started["consultation"]["enterprise_scope_id"] == "hq", "만든 사람의 부서가 기본 범위"
    assert started["consultation"]["entity_mode"] == "REAL"

    # ── 2) 답변: 한 번에 하나씩, 정의된 순서로
    asked = []
    q = started["next_question"]
    while q:
        asked.append(q["id"])
        pick = next(o["value"] for o in q["options"] if o["recommended"])
        res = _data(c.post(f"/api/v1/advisor/consultations/{cid}/messages",
                           json={"question_id": q["id"], "selected_values": [pick],
                                 "message": "환율 민감도를 꼭 보고 싶습니다" if not q.get("stage") == "" else ""}))
        q = res["next_question"]
    assert asked == [x.id for x in pb.questions]
    assert res["progress"]["complete"] is True

    # ── 3) 청사진: 상담의 문맥·소유권을 승계하는가
    bp = _data(c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={
        "statuses": {"master_org": "held", "master_account": "held",
                     "master_cost_center": "held", "ownership_data": "held",
                     "actual_pl_monthly": "needs_verification"}}))
    bid = bp["blueprint_id"]
    assert bp["status"] == "draft"
    assert bp["owner_dept_id"] == "hq" and bp["owner_user_id"] == "bob"
    assert bp["tenant_id"] == "tenant_default" and bp["entity_mode"] == "REAL"
    assert bp["enterprise_scope_id"] == "hq"
    assert bp["readiness_score"] > 0
    assert "환율 민감도" in bp["business"]["problem"], "자유 입력이 버려지지 않아야 한다"
    assert all(not p["confirmed"] for p in bp["provenance"].values()), "조립만으로는 미확정"

    # ── 4) 승인 전 부트스트랩은 막힌다
    r = c.post(f"/api/v1/advisor/blueprints/{bid}/bootstrap-project", json={"project_id": "P_E2E"})
    assert r.status_code == 409
    assert not os.path.isdir("./projects/P_E2E")

    # ── 5) 승인: Ledger 에 기록되고 출처가 확정으로 바뀌는가
    dec = _data(c.post(f"/api/v1/advisor/blueprints/{bid}/approve", json={"decision": "approved"}))
    assert dec["status"] == "approved" and dec["approved_by"] == "bob"
    assert dec["approved_with_blocking_gaps"], "결손을 안고 승인한 사실이 응답에 남아야 한다"
    approved = _data(c.get(f"/api/v1/advisor/blueprints/{bid}"))
    assert all(p["confirmed"] for p in approved["provenance"].values())
    assert all(p["origin"] in ("rule", "user", "ai") for p in approved["provenance"].values())

    ev = ledger.list_events(blueprint_id=bid)
    assert [e["event_type"] for e in ev] == ["BLUEPRINT_APPROVED"]
    assert ev[0]["is_substantiated"] is True
    assert "준비도" in ev[0]["rationale"] and "미확보 필수 데이터" in ev[0]["rationale"]

    # ── 6) 프로젝트 생성: project_meta 와 latest_state 로 값이 흘러가는가
    pr = _data(c.post(f"/api/v1/advisor/blueprints/{bid}/bootstrap-project",
                      json={"project_id": "P_E2E"}))
    assert pr["template_id"] == bp["system"]["template_id"]

    own = fc._read_project_ownership("./projects/P_E2E")
    assert own["owner_dept_id"] == "hq", "소유권이 안 찍히면 프롬프트 주입 필터가 fail-open 된다"
    assert own["blueprint_id"] == bid, "추적 링크(§18-7)"
    assert own["tenant_id"] == "tenant_default" and own["entity_mode"] == "REAL"
    assert own["enterprise_scope_id"] == "hq"

    with open("./projects/P_E2E/latest_state.json", encoding="utf-8") as f:
        st = json.load(f)
    assert st["blueprint_id"] == bid
    idea = st["initial_idea"]
    assert idea.startswith("내년도 사업계획"), "사용자의 원래 말이 앞"
    assert "[승인된 Solution Blueprint" in idea, "Blueprint 요약이 파이프라인 입력으로 주입"
    assert "제외 범위(만들지 말 것)" in idea
    assert "⚠️ 미확보 필수 데이터" in idea, "무엇이 없는지 기획이 알아야 한다"

    # ── 7) 데이터 태스크: 기획 전엔 막히고, WBS 가 있으면 append
    r = c.post(f"/api/v1/advisor/blueprints/{bid}/create-data-tasks?project_id=P_E2E")
    assert r.status_code == 409 and "기획" in r.json()["detail"]

    WBSManager(workspace_root="./projects/P_E2E").initialize_wbs(
        "P_E2E", [{"task_id": "WBS-001", "title": "기획", "status": "DONE"}])
    created = _data(c.post(f"/api/v1/advisor/blueprints/{bid}/create-data-tasks?project_id=P_E2E"))["created"]
    assert created
    wbs = WBSManager(workspace_root="./projects/P_E2E").get_wbs()
    assert wbs["total_tasks"] == 1 + len(created), "기존 태스크를 지우지 않는다"
    dt = next(t for t in wbs["tasks"] if t["task_id"] == "TASK_DATA_01")
    for marker in ("[없으면]", "[조치]", "[데이터 구분]"):
        assert marker in dt["goal"], f"{marker} 가 없으면 태스크가 방치된다"

    # ── 8) 게시: 소유 부서가 RAG 인덱싱 메타로 넘어가는가 (★ 이 세션 첫 결함)
    from core.knowledge_base import knowledge_base
    seen = {}
    monkeypatch.setattr(knowledge_base, "index_release",
                        lambda pid, rid, files, meta: seen.update({"pid": pid, "meta": meta}))
    # ⚠️ `create_release` 는 `data` 로 감싸지 않고 `release_id` 를 바로 준다(다른 advisor 라우트와
    #   응답 형태가 다르다). 통합 테스트를 쓰다 발견 — 프론트가 이 경로를 쓸 때 주의할 점이다.
    rel_res = c.post("/api/v1/factory/P_E2E/release")
    assert rel_res.status_code == 200, rel_res.text
    release_id = rel_res.json()["release_id"]
    import time
    for _ in range(50):                      # run_in_executor 라 잠깐 기다린다
        if seen:
            break
        time.sleep(0.1)
    assert seen, "게시가 인덱싱을 트리거해야 한다"
    assert seen["meta"]["owner_dept_id"] == "hq", \
        "이 값이 비면 fail-closed 필터가 자기 부서 산출물까지 배제해 RAG 가 조용히 0건이 된다"
    with open(os.path.join("library", release_id, "release.json"), encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["owner_dept_id"] == "hq" and saved["visibility"] == "dept"

    # ── 9) 결정 이력: 이 청사진에서 파생된 것이 전부 보이는가 (★ 다섯째 결함)
    hist = _data(c.get(f"/api/v1/ledger/events?blueprint_id={bid}"))
    types = {e["event_type"] for e in hist}
    assert {"BLUEPRINT_APPROVED", "PROJECT_BOOTSTRAPPED", "DATA_REQUIREMENT_ACCEPTED"} <= types, \
        f"subject 기준으로만 조회하면 프로젝트 이벤트가 빠진다. 실제: {types}"
    boot = next(e for e in hist if e["event_type"] == "PROJECT_BOOTSTRAPPED")
    assert boot["subject_type"] == "project" and boot["subject_id"] == "P_E2E"

    # ── 10) 체인 무결성
    act_as(app, user_id="exec", dept="hq", enterprise=True)
    v = _data(c.get("/api/v1/ledger/verify"))
    assert v["ok"] is True and v["broken"] == []
    assert "탐지" in v["limitation"], "위조 방지가 아니라 탐지라는 한계를 늘 함께 노출"


# ══════════════════════════════════════════════════════════════════════════
# ⑤ 권한·문맥 격리가 전 경로에서 일관되게 막는가
# ══════════════════════════════════════════════════════════════════════════
def _approved_for(c, app, dept, user):
    act_as(app, user_id=user, dept=dept)
    pb = load_playbook(PB_ID)
    cid = start(c)["consultation"]["consultation_id"]
    answer_all(c, cid, pb)
    bid = _data(c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={}))["blueprint_id"]
    c.post(f"/api/v1/advisor/blueprints/{bid}/approve", json={"decision": "approved"})
    return cid, bid


def test_other_dept_is_blocked_on_every_path(stack):
    """★ 한 곳만 막고 다른 곳이 열려 있으면 격리가 아니다 — 전 경로를 한 번에 확인한다."""
    c, app = stack["c"], stack["app"]
    cid, bid = _approved_for(c, app, "hq", "bob")

    act_as(app, user_id="eve", dept="sales")
    assert c.get(f"/api/v1/advisor/consultations/{cid}").status_code == 403
    assert c.post(f"/api/v1/advisor/consultations/{cid}/messages",
                  json={"question_id": "Q_PURPOSE", "selected_values": ["plan_build"]}
                  ).status_code == 403
    assert c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={}).status_code == 403
    assert c.get(f"/api/v1/advisor/blueprints/{bid}").status_code == 403
    assert c.post(f"/api/v1/advisor/blueprints/{bid}/approve",
                  json={"decision": "rejected", "reason": "x"}).status_code == 403
    assert c.post(f"/api/v1/advisor/blueprints/{bid}/bootstrap-project",
                  json={"project_id": "P_EVE"}).status_code == 403
    # 목록·롤업·감사 이력도 함께 막혀야 한다
    assert c.get("/api/v1/advisor/consultations").json()["data"] == []
    assert c.get("/api/v1/advisor/blueprints").json()["data"] == []
    assert c.get("/api/v1/advisor/data-requirements/rollup").json()["data"] == []
    assert c.get("/api/v1/ledger/events").json()["data"] == []


def test_other_tenant_context_sees_nothing(stack):
    """다른 테넌트에서는 **없는 것**으로 답한다(403 이 아니라 404)."""
    c, app = stack["c"], stack["app"]
    act_as(app, user_id="bob", dept="hq")
    cid, bid = _approved_for(c, app, "hq", "bob")
    other = {config.ECM_TENANT_HEADER: "tenant_other"}
    assert c.get(f"/api/v1/advisor/consultations/{cid}", headers=other).status_code == 404
    assert c.get(f"/api/v1/advisor/blueprints/{bid}", headers=other).status_code == 404
    assert c.get("/api/v1/advisor/consultations", headers=other).json()["data"] == []
    assert c.get(f"/api/v1/ledger/events?blueprint_id={bid}", headers=other).json()["data"] == []


def test_virtual_context_cannot_start_consultation(stack):
    """ECM E3 안전장치가 없는 동안 가상 문맥 자료를 만들 수 없다."""
    c, app = stack["c"], stack["app"]
    act_as(app)
    r = c.post("/api/v1/advisor/consultations", json={"playbook_id": PB_ID},
               headers={config.ECM_MODE_HEADER: "VIRTUAL"})
    assert r.status_code == 400 and "E3" in r.json()["detail"]


# ══════════════════════════════════════════════════════════════════════════
# ⑥ 재조립·반려 경로도 이력이 끊기지 않는가
# ══════════════════════════════════════════════════════════════════════════
def test_redraft_versions_and_both_decisions_are_recorded(stack):
    c, app, ledger = stack["c"], stack["app"], stack["ledger"]
    act_as(app)
    pb = load_playbook(PB_ID)
    cid = start(c)["consultation"]["consultation_id"]
    answer_all(c, cid, pb)

    v1 = _data(c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={}))
    v2 = _data(c.post(f"/api/v1/advisor/consultations/{cid}/blueprint",
                      json={"statuses": {"master_org": "held"}}))
    assert v2["version"] == v1["version"] + 1, "재조립은 덮어쓰지 않고 새 버전"
    assert v2["blueprint_id"] != v1["blueprint_id"]

    c.post(f"/api/v1/advisor/blueprints/{v1['blueprint_id']}/approve",
           json={"decision": "rejected", "reason": "실적 데이터가 없다"})
    c.post(f"/api/v1/advisor/blueprints/{v2['blueprint_id']}/approve", json={"decision": "approved"})

    all_ev = {e["event_type"] for e in ledger.list_events()}
    assert {"BLUEPRINT_REJECTED", "BLUEPRINT_APPROVED"} <= all_ev
    rej = ledger.list_events(blueprint_id=v1["blueprint_id"])[0]
    assert "실적 데이터가 없다" in rej["decision"], "반려 사유가 이력에 남아야 한다"


def test_ledger_has_no_write_endpoint(stack):
    """감사 이력에 외부 쓰기 경로가 생기면 증거가 무의미해진다."""
    app = stack["app"]
    writes = [(r.path, m) for r in app.routes for m in getattr(r, "methods", set())
              if "/ledger" in getattr(r, "path", "") and m in ("POST", "PUT", "PATCH", "DELETE")]
    assert writes == []
