# ==========================================
# Solution Blueprint + 상담 저장소 + 상담 API (마스터 명세서 §4.5·§4.6·§5.1 / M0 백로그 2)
#
# 검증하는 계약 다섯:
#  ① **조립은 LLM 0콜 결정론** — 같은 답변이면 같은 Blueprint. 사용자가 "왜 이렇게 나왔나"를
#     물으면 설명할 수 있어야 하고, 제품 바이블 §9.3 이 AI 에게 진실을 맡기지 말라고 못 박았다.
#  ② **제외 범위는 추론이 아니라 사실** — 사용자가 고르지 않은 선택지가 곧 제외 범위다(§5.1).
#  ③ **승인은 origin 을 지우지 않는다** — AI 가 제안했던 것은 승인 뒤에도 그렇다. `confirmed` 만
#     켠다(§5.2 / §1.3 기업 의도와 결정의 보존).
#  ④ **부서 미지정 상담은 본인만** — 상담은 이 기능과 함께 새로 생기는 데이터라 지킬 레거시가
#     없다. 하위호환 대상이 없으면 fail-closed 가 맞다(프로젝트 목록과 다른 판단).
#  ⑤ **차단이 아니라 가시화** — 필수 데이터가 결손이어도 승인은 되지만 무엇을 안고 승인하는지
#     응답에 남는다.
# ==========================================
import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.routes.advisor_control as ac
from api.deps import Principal, current_principal
from core.advisor_blueprint import (SolutionBlueprint, assemble_blueprint, data_kind_of,
                                    BlueprintKPI)
from core.advisor_playbook import load_playbook
from core.advisor_store import AdvisorStore, AdvisorStoreError
from core.org_directory import AccessScope

PB_ID = "business_planning"


@pytest.fixture
def pb():
    return load_playbook(PB_ID)


@pytest.fixture
def store(tmp_path):
    return AdvisorStore(db_path=str(tmp_path / "advisor.db"))


def _recommended_answers(pb):
    return {q.id: [o.key() for o in q.options if o.recommended] for q in pb.questions}


# ══════════════════════════════════════════════════════════════════════════
# ① 조립 — 순수 함수
# ══════════════════════════════════════════════════════════════════════════
def test_assembly_is_deterministic(pb):
    a = _recommended_answers(pb)
    b1 = assemble_blueprint(pb, a, initial_prompt="내년 사업계획")
    b2 = assemble_blueprint(pb, a, initial_prompt="내년 사업계획")
    assert b1.model_dump() == b2.model_dump()


def test_assembly_carries_playbook_identity(pb):
    bp = assemble_blueprint(pb, _recommended_answers(pb))
    assert bp.playbook_id == PB_ID
    assert bp.business_domain == "planning_budget"
    assert bp.system.template_id == pb.recommended_template_id
    assert bp.recommended_sequence == pb.recommended_sequence


def test_out_of_scope_is_the_unchosen_options(pb):
    """★ 제외 범위는 추론이 아니라 사실 — 고르지 않은 선택지가 곧 제외다."""
    answers = _recommended_answers(pb)
    scope_q = next(q for q in pb.questions if q.stage == "scope")
    chosen = [o.label for o in scope_q.options if o.key() in answers[scope_q.id]]
    unchosen = [o.label for o in scope_q.options if o.label not in chosen]
    bp = assemble_blueprint(pb, answers)
    assert bp.business.in_scope == chosen
    assert set(unchosen) <= set(bp.business.out_of_scope)
    assert not (set(chosen) & set(bp.business.out_of_scope)), "고른 것이 제외에 들어가면 안 된다"


def test_only_active_requirements_are_copied(pb):
    """추천안만 고르면 범위 밖 요구사항(제품 마스터 등)은 Blueprint 에 들어오지 않는다."""
    bp = assemble_blueprint(pb, _recommended_answers(pb))
    keys = {r.key for r in bp.data_requirements}
    assert "master_org" in keys
    assert "master_product" not in keys, "고르지 않은 범위의 요구사항이 실리면 결손이 부풀려진다"


def test_statuses_are_reflected_and_unknown_is_missing(pb):
    bp = assemble_blueprint(pb, _recommended_answers(pb), statuses={"master_org": "held"})
    by = {r.key: r.readiness_status for r in bp.data_requirements}
    assert by["master_org"] == "held"
    assert by["master_account"] == "missing", "모르는 것을 보유로 치지 않는다"


def test_data_kind_mapping():
    """제품 바이블 §7.1 — 네 종류를 섞지 않으려면 이름이 붙어 있어야 한다."""
    assert data_kind_of("master") == "reference"
    assert data_kind_of("actual") == "actual"
    assert data_kind_of("driver") == "plan"
    assert data_kind_of("external", "gold") == "actual"
    assert data_kind_of("external", "silver") == "forecast"
    assert data_kind_of("external", "bronze") == "event"
    assert data_kind_of("external", "") == "forecast", "등급 불명은 확정값으로 취급하지 않는다"


def test_blueprint_requirements_carry_data_kind(pb):
    bp = assemble_blueprint(pb, _recommended_answers(pb))
    kinds = {r.key: r.data_kind for r in bp.data_requirements}
    assert kinds["master_org"] == "reference"
    assert kinds["actual_revenue"] == "actual"
    assert kinds["driver_volume"] == "plan"
    assert kinds["ext_fx"] == "actual", "Gold 외부지표는 확정 실제값(§7.2)"
    assert kinds["ext_demand_index"] == "forecast", "Silver 는 전망"


def test_risks_include_playbook_risks_and_computed_gaps(pb):
    bp = assemble_blueprint(pb, _recommended_answers(pb))   # statuses 없음 → 전부 결손
    texts = [r.description for r in bp.risks]
    assert any(pb.risks[0][:20] in t for t in texts), "플레이북 도메인 위험이 실려야 한다"
    assert any("필수 데이터 결손" in t for t in texts), "준비도에서 계산된 위험도 실려야 한다"
    gap_risks = [r for r in bp.risks if "필수 데이터 결손" in r.description]
    assert all(r.mitigation for r in gap_risks), "위험만 알려주고 조치를 안 주면 쓸모없다"


def test_unmeasured_readiness_is_reported_as_risk():
    """준비도 100점이 측정되지 않았다는 사실 자체가 위험이다(숨기지 않는다)."""
    from core.advisor_playbook import DataRequirement, Playbook
    pb = Playbook(playbook_id="x", name_ko="x", recommended_sequence=["1)"],
                  data_requirements=[DataRequirement(key="a", canonical_term="A",
                                                     gap_impact="i", next_action="n")])
    bp = assemble_blueprint(pb, {}, statuses={"a": "held"})
    assert any("측정되지 않았습니다" in r.description for r in bp.risks)


def test_readiness_is_preserved_in_blueprint(pb):
    bp = assemble_blueprint(pb, _recommended_answers(pb), statuses={"master_org": "held"})
    assert bp.readiness_score == bp.readiness["score"]
    assert bp.readiness["dimensions"] and "gaps" in bp.readiness


def test_provenance_starts_unconfirmed(pb):
    bp = assemble_blueprint(pb, _recommended_answers(pb))
    assert bp.provenance["data_requirements"].origin == "rule"
    assert bp.provenance["business"].origin == "user"
    assert all(not p.confirmed for p in bp.provenance.values()), "조립만으로는 확정이 아니다"


def test_free_text_is_appended_not_discarded(pb):
    bp = assemble_blueprint(pb, _recommended_answers(pb), initial_prompt="원래 요청",
                            free_text={"Q_PURPOSE": "환율 민감도를 꼭 보고 싶다"})
    assert "원래 요청" in bp.business.problem
    assert "환율 민감도" in bp.business.problem, "사용자가 쓴 것은 근거이므로 버리지 않는다"


def test_unverified_kpi_detection():
    bp = SolutionBlueprint(kpis=[BlueprintKPI(name="영업이익률", formula="영업이익/매출", unit="%"),
                                 BlueprintKPI(name="감각지표")])
    assert bp.unverified_kpis() == ["감각지표"]


def test_blocking_gaps_only_required_missing(pb):
    bp = assemble_blueprint(pb, _recommended_answers(pb),
                            statuses={r.key: "needs_verification" for r in pb.data_requirements})
    assert bp.blocking_gaps() == [], "검증 필요는 차단이 아니다"


# ══════════════════════════════════════════════════════════════════════════
# ② 저장소
# ══════════════════════════════════════════════════════════════════════════
def test_consultation_roundtrip(store):
    c = store.create_consultation(user_id="bob", owner_dept_id="hq", playbook_id=PB_ID,
                                  initial_prompt="내년 계획")
    got = store.get_consultation(c["consultation_id"])
    assert got["user_id"] == "bob" and got["owner_dept_id"] == "hq"
    assert got["status"] == "open"


def test_invalid_scope_rejected(store):
    with pytest.raises(AdvisorStoreError):
        store.create_consultation(scope="우주")


def test_turn_numbers_are_assigned_by_db(store):
    """대화 순서는 사후에 고칠 수 없는 이력이다 — 클라이언트가 정하면 동시 요청에서 어긋난다."""
    c = store.create_consultation(playbook_id=PB_ID)
    cid = c["consultation_id"]
    assert store.add_turn(cid, "advisor", "질문1")["turn_no"] == 1
    assert store.add_turn(cid, "user", "답1")["turn_no"] == 2
    assert store.add_turn(cid, "advisor", "질문2")["turn_no"] == 3
    assert [t["turn_no"] for t in store.list_turns(cid)] == [1, 2, 3]


def test_turn_on_missing_consultation_raises(store):
    with pytest.raises(AdvisorStoreError):
        store.add_turn("cons_ghost", "user", "안녕")


def test_invalid_speaker_rejected(store):
    c = store.create_consultation()
    with pytest.raises(AdvisorStoreError):
        store.add_turn(c["consultation_id"], "robot", "x")


def test_last_answer_wins(store):
    """사용자가 생각을 바꾼 것이다. 이력은 턴 테이블에 남으므로 잃는 정보가 없다."""
    c = store.create_consultation(playbook_id=PB_ID)
    cid = c["consultation_id"]
    store.add_turn(cid, "user", question_id="Q_SCOPE", selected_values=["company"])
    store.add_turn(cid, "user", question_id="Q_SCOPE", selected_values=["product"])
    assert store.collected_answers(cid) == {"Q_SCOPE": ["product"]}
    assert len(store.list_turns(cid)) == 2, "이전 답도 이력으로 남아 있어야 한다"


def test_blueprint_roundtrip(store, pb):
    c = store.create_consultation(owner_dept_id="hq", playbook_id=PB_ID)
    bp = assemble_blueprint(pb, _recommended_answers(pb))
    bp.consultation_id = c["consultation_id"]
    bp.owner_dept_id = "hq"
    saved = store.save_blueprint(bp)
    got = store.get_blueprint(saved.blueprint_id)
    assert got is not None
    assert got.readiness_score == saved.readiness_score
    assert len(got.data_requirements) == len(saved.data_requirements)


def test_redraft_creates_new_version_not_overwrite(store, pb):
    c = store.create_consultation(playbook_id=PB_ID)
    cid = c["consultation_id"]
    for _ in range(3):
        bp = assemble_blueprint(pb, _recommended_answers(pb))
        bp.consultation_id = cid
        store.save_blueprint(bp)
    rows = store.list_blueprints(consultation_id=cid)
    assert sorted(r["version"] for r in rows) == [1, 2, 3]


def test_resaving_same_blueprint_does_not_bump_version(store, pb):
    c = store.create_consultation(playbook_id=PB_ID)
    bp = assemble_blueprint(pb, _recommended_answers(pb))
    bp.consultation_id = c["consultation_id"]
    saved = store.save_blueprint(bp)
    again = store.save_blueprint(saved)
    assert again.version == saved.version, "같은 것을 두 번 저장하는 것은 개정이 아니다"


def test_approval_sets_confirmed_but_keeps_origin(store, pb):
    """★ AI 가 제안했던 것은 승인 뒤에도 그렇다 — origin 을 지우면 결정의 계보가 끊긴다."""
    bp = assemble_blueprint(pb, _recommended_answers(pb))
    saved = store.save_blueprint(bp)
    origins_before = {k: v.origin for k, v in saved.provenance.items()}
    decided = store.set_blueprint_decision(saved.blueprint_id, "approved", "kim")
    assert decided.status == "approved" and decided.approved_by == "kim" and decided.approved_at
    assert all(p.confirmed for p in decided.provenance.values())
    assert {k: v.origin for k, v in decided.provenance.items()} == origins_before


def test_double_approval_rejected(store, pb):
    saved = store.save_blueprint(assemble_blueprint(pb, _recommended_answers(pb)))
    store.set_blueprint_decision(saved.blueprint_id, "approved", "kim")
    with pytest.raises(AdvisorStoreError):
        store.set_blueprint_decision(saved.blueprint_id, "approved", "kim")


def test_rejection_records_reason_and_clears_approval(store, pb):
    saved = store.save_blueprint(assemble_blueprint(pb, _recommended_answers(pb)))
    d = store.set_blueprint_decision(saved.blueprint_id, "rejected", "kim", reason="데이터 부족")
    assert d.status == "rejected" and d.rejected_reason == "데이터 부족"
    assert d.approved_by == "" and d.approved_at == ""


def test_dept_filter_on_list(store, pb):
    for dept in ("hq", "sales"):
        bp = assemble_blueprint(pb, _recommended_answers(pb))
        bp.owner_dept_id = dept
        store.save_blueprint(bp)
    assert {r["owner_dept_id"] for r in store.list_blueprints(dept_ids=["hq"])} == {"hq"}
    assert len(store.list_blueprints(dept_ids=None)) == 2, "None 은 무제한(필터 없음)"
    assert store.list_blueprints(dept_ids=[]) == [], "읽을 부서가 없으면 아무것도 안 보인다"


def test_corrupt_payload_returns_none(store, tmp_path):
    import sqlite3
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("INSERT INTO solution_blueprints (blueprint_id, payload_json, created_at, "
                     "updated_at) VALUES ('bp_bad','{not json',?,?)", ("t", "t"))
    assert store.get_blueprint("bp_bad") is None, "손상 페이로드가 조회를 500 으로 만들면 안 된다"


def test_requirement_rollup_is_queryable(store, pb):
    """요구사항을 행으로 따로 둔 이유 — JSON 안에 있는 것은 검색되지 않는다."""
    bp = assemble_blueprint(pb, _recommended_answers(pb), statuses={"master_org": "held"})
    bp.owner_dept_id = "hq"
    store.save_blueprint(bp)
    rows = store.requirement_rollup(dept_ids=["hq"])
    assert rows
    held = [r for r in rows if r["readiness_status"] == "held"]
    assert any(r["canonical_term"] == "조직 · 법인" for r in held)
    assert all("owner_department" in r and "n" in r for r in rows)


# ══════════════════════════════════════════════════════════════════════════
# ③ API
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(ac, "advisor_store", store)
    app = FastAPI()
    app.include_router(ac.router)
    return app, TestClient(app)


def _as(app, user_id="bob", dept="hq", readable=None, writable=None):
    scope = AccessScope(user_id=user_id, primary_dept_id=dept, unrestricted=False,
                        readable_dept_ids=frozenset(readable if readable is not None else {dept}),
                        writable_dept_ids=frozenset(writable if writable is not None else {dept}))
    app.dependency_overrides[current_principal] = lambda: Principal(user_id=user_id, scope=scope)


def test_api_playbooks_listed(client):
    app, c = client
    _as(app)
    r = c.get("/api/v1/advisor/playbooks")
    assert r.status_code == 200
    assert any(p["playbook_id"] == PB_ID for p in r.json()["data"])


def test_api_start_consultation_returns_first_question(client):
    app, c = client
    _as(app)
    r = c.post("/api/v1/advisor/consultations",
               json={"initial_prompt": "내년 사업계획", "playbook_id": PB_ID})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["consultation"]["owner_dept_id"] == "hq", "만든 사람의 부서가 소유 부서"
    assert d["next_question"]["id"] == "Q_PURPOSE"
    assert len(d["next_question"]["options"]) >= 2
    assert all(o["value"] for o in d["next_question"]["options"]), "선택지 식별자가 있어야 한다"
    assert d["progress"] == {"answered": 0, "total": 6, "complete": False}


def test_api_unknown_playbook_404(client):
    app, c = client
    _as(app)
    r = c.post("/api/v1/advisor/consultations", json={"playbook_id": "ghost_pb"})
    assert r.status_code == 404


def test_api_bad_playbook_id_400(client):
    app, c = client
    _as(app)
    r = c.post("/api/v1/advisor/consultations", json={"playbook_id": "../secret"})
    assert r.status_code == 400, "경로 이탈은 입력 오류이므로 400"


def _start(c, pb_id=PB_ID):
    return c.post("/api/v1/advisor/consultations",
                  json={"initial_prompt": "내년 사업계획", "playbook_id": pb_id}
                  ).json()["data"]["consultation"]["consultation_id"]


def test_api_answer_flow_advances_one_question_at_a_time(client, pb):
    app, c = client
    _as(app)
    cid = _start(c)
    asked = []
    for _ in range(len(pb.questions)):
        got = c.get(f"/api/v1/advisor/consultations/{cid}").json()["data"]
        q = got["next_question"]
        assert q is not None
        asked.append(q["id"])
        rec = next(o["value"] for o in q["options"] if o["recommended"])
        r = c.post(f"/api/v1/advisor/consultations/{cid}/messages",
                   json={"question_id": q["id"], "selected_values": [rec]})
        assert r.status_code == 200, r.text
    assert asked == [q.id for q in pb.questions], "한 번에 하나씩, 정의된 순서로"
    final = c.get(f"/api/v1/advisor/consultations/{cid}").json()["data"]
    assert final["next_question"] is None
    assert final["progress"]["complete"] is True


def test_api_readiness_preview_present(client, pb):
    app, c = client
    _as(app)
    cid = _start(c)
    r = c.post(f"/api/v1/advisor/consultations/{cid}/messages",
               json={"question_id": "Q_PURPOSE", "selected_values": ["plan_build"]})
    prev = r.json()["data"]["readiness_preview"]
    assert prev["score"] == 0.0, "보유 상태를 아직 모르므로 하한(0)에서 시작한다"
    assert prev["gaps"], "무엇이 필요한지는 지금도 보여줄 수 있다"


def test_api_rejects_unknown_option(client):
    app, c = client
    _as(app)
    cid = _start(c)
    r = c.post(f"/api/v1/advisor/consultations/{cid}/messages",
               json={"question_id": "Q_PURPOSE", "selected_values": ["없는선택지"]})
    assert r.status_code == 400, "조용히 받아두면 조립 단계에서 원인 추적이 어렵다"


def test_api_rejects_unknown_question(client):
    app, c = client
    _as(app)
    cid = _start(c)
    r = c.post(f"/api/v1/advisor/consultations/{cid}/messages",
               json={"question_id": "Q_NOPE", "selected_values": ["x"]})
    assert r.status_code == 400


def test_api_rejects_multi_select_on_single_question(client):
    app, c = client
    _as(app)
    cid = _start(c)
    r = c.post(f"/api/v1/advisor/consultations/{cid}/messages",
               json={"question_id": "Q_PURPOSE", "selected_values": ["plan_build", "variance"]})
    assert r.status_code == 400


def test_api_rejects_empty_message(client):
    app, c = client
    _as(app)
    cid = _start(c)
    r = c.post(f"/api/v1/advisor/consultations/{cid}/messages", json={})
    assert r.status_code == 400


def test_api_free_text_only_is_accepted(client):
    """장문 입력은 선택 사항이지만 받을 수는 있어야 한다(§4.3 F-DA-02)."""
    app, c = client
    _as(app)
    cid = _start(c)
    r = c.post(f"/api/v1/advisor/consultations/{cid}/messages",
               json={"message": "환율 영향을 꼭 보고 싶습니다"})
    assert r.status_code == 200


def _answer_all(c, cid, pb):
    for q in pb.questions:
        rec = next(o.key() for o in q.options if o.recommended)
        c.post(f"/api/v1/advisor/consultations/{cid}/messages",
               json={"question_id": q.id, "selected_values": [rec]})


def test_api_draft_and_approve_blueprint(client, pb):
    app, c = client
    _as(app)
    cid = _start(c)
    _answer_all(c, cid, pb)

    r = c.post(f"/api/v1/advisor/consultations/{cid}/blueprint",
               json={"statuses": {"master_org": "held", "master_account": "held"}})
    assert r.status_code == 200, r.text
    bp = r.json()["data"]
    assert bp["status"] == "draft" and bp["blueprint_id"]
    assert bp["readiness_score"] > 0
    assert bp["owner_dept_id"] == "hq"

    got = c.get(f"/api/v1/advisor/blueprints/{bp['blueprint_id']}").json()["data"]
    assert got["blocking_gap_count"] > 0, "결손이 있으면 승인 화면이 알려줘야 한다"

    r = c.post(f"/api/v1/advisor/blueprints/{bp['blueprint_id']}/approve",
               json={"decision": "approved"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["status"] == "approved" and d["approved_by"] == "bob"
    # ⑤ 차단이 아니라 가시화 — 무엇을 안고 승인했는지 남는다
    assert d["approved_with_blocking_gaps"], "결손을 안고 승인했다면 그 사실이 남아야 한다"


def test_api_draft_without_answers_400(client):
    app, c = client
    _as(app)
    cid = _start(c)
    r = c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={})
    assert r.status_code == 400


def test_api_draft_without_playbook_400(client):
    app, c = client
    _as(app)
    cid = c.post("/api/v1/advisor/consultations", json={"initial_prompt": "뭔가"}
                 ).json()["data"]["consultation"]["consultation_id"]
    r = c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={})
    assert r.status_code == 400


def test_api_rejection_requires_reason(client, pb):
    app, c = client
    _as(app)
    cid = _start(c)
    _answer_all(c, cid, pb)
    bid = c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={}
                 ).json()["data"]["blueprint_id"]
    assert c.post(f"/api/v1/advisor/blueprints/{bid}/approve",
                  json={"decision": "rejected"}).status_code == 400
    assert c.post(f"/api/v1/advisor/blueprints/{bid}/approve",
                  json={"decision": "rejected", "reason": "실적 없음"}).status_code == 200


def test_api_double_approve_409(client, pb):
    app, c = client
    _as(app)
    cid = _start(c)
    _answer_all(c, cid, pb)
    bid = c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={}
                 ).json()["data"]["blueprint_id"]
    c.post(f"/api/v1/advisor/blueprints/{bid}/approve", json={"decision": "approved"})
    r = c.post(f"/api/v1/advisor/blueprints/{bid}/approve", json={"decision": "approved"})
    assert r.status_code == 409


# ── 권한 ─────────────────────────────────────────────────────────────────
def test_api_other_dept_consultation_is_403(client, pb):
    app, c = client
    _as(app, user_id="bob", dept="hq")
    cid = _start(c)
    _as(app, user_id="eve", dept="sales")       # 영업부 사용자로 전환
    assert c.get(f"/api/v1/advisor/consultations/{cid}").status_code == 403
    assert c.post(f"/api/v1/advisor/consultations/{cid}/messages",
                  json={"question_id": "Q_PURPOSE", "selected_values": ["plan_build"]}
                  ).status_code == 403


def test_api_other_dept_blueprint_is_403(client, pb):
    app, c = client
    _as(app, user_id="bob", dept="hq")
    cid = _start(c)
    _answer_all(c, cid, pb)
    bid = c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={}
                 ).json()["data"]["blueprint_id"]
    _as(app, user_id="eve", dept="sales")
    assert c.get(f"/api/v1/advisor/blueprints/{bid}").status_code == 403
    assert c.post(f"/api/v1/advisor/blueprints/{bid}/approve",
                  json={"decision": "approved"}).status_code == 403


def test_api_personal_consultation_is_owner_only(client):
    """★ 부서 미지정 상담은 본인만 — 상담은 새로 생기는 데이터라 지킬 레거시가 없다."""
    app, c = client
    _as(app, user_id="bob", dept="")            # 무소속 사용자
    cid = _start(c)
    _as(app, user_id="eve", dept="")
    assert c.get(f"/api/v1/advisor/consultations/{cid}").status_code == 403
    _as(app, user_id="bob", dept="")
    assert c.get(f"/api/v1/advisor/consultations/{cid}").status_code == 200


def test_api_list_is_dept_scoped(client):
    app, c = client
    _as(app, user_id="bob", dept="hq")
    _start(c)
    _as(app, user_id="eve", dept="sales")
    _start(c)
    assert len(c.get("/api/v1/advisor/consultations").json()["data"]) == 1
    _as(app, user_id="admin", dept="hq", readable={"hq", "sales"}, writable={"hq", "sales"})
    assert len(c.get("/api/v1/advisor/consultations").json()["data"]) == 2


def test_api_unrestricted_sees_all(client):
    """조직 미도입 기본값(ORG_ENFORCE=False)에서는 종전처럼 전부 보인다."""
    app, c = client
    _as(app, user_id="bob", dept="hq")
    _start(c)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="", scope=AccessScope(unrestricted=True))
    assert len(c.get("/api/v1/advisor/consultations").json()["data"]) == 1


def test_api_rollup_is_dept_scoped(client, pb):
    app, c = client
    _as(app, user_id="bob", dept="hq")
    cid = _start(c)
    _answer_all(c, cid, pb)
    c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={})
    assert c.get("/api/v1/advisor/data-requirements/rollup").json()["data"]
    _as(app, user_id="eve", dept="sales")
    assert c.get("/api/v1/advisor/data-requirements/rollup").json()["data"] == []


def test_api_missing_consultation_404(client):
    app, c = client
    _as(app)
    assert c.get("/api/v1/advisor/consultations/cons_ghost").status_code == 404
    assert c.get("/api/v1/advisor/blueprints/bp_ghost").status_code == 404
