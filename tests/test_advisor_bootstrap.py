# ==========================================
# Blueprint → 프로젝트 연결 (마스터 명세서 §4.7 / M0 백로그 4)
#
# 검증하는 계약 다섯:
#  ① **승인 전 Blueprint 로는 프로젝트를 만들 수 없다** — 초안으로 만들 수 있으면 승인 게이트가
#     장식이 된다(§4.2-7 "사용자가 승인하면 ... 프로젝트 초안을 생성한다").
#  ② **Clarification 을 우회하지 않는다**(§18-6) — Blueprint 는 `initial_idea` 의 상위 입력값으로
#     주입될 뿐이다. 상담은 "무엇을 만들지", Clarification 은 "어떻게 만들지"의 모호점 제거.
#  ③ **프로젝트는 Blueprint 의 문맥·소유권을 물려받는다** — 요청 헤더가 아니라. 다른 문맥의
#     프로젝트가 생기면 추적이 끊긴다(ECM §10.2).
#  ④ **프롬프트에는 요약만** — 원문 전체가 아니다(ECM §5.2-5 / 명세서 §10.4).
#  ⑤ **데이터 태스크는 기획 후에만** — `initialize_wbs` 가 파일을 통째로 다시 쓰므로 기획 전에
#     넣으면 사라진다. 조용히 만들어 두지 않고 409 로 돌려보낸다.
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
from api.deps import Principal, current_principal
from core.advisor_blueprint import assemble_blueprint
from core.advisor_playbook import load_playbook
from core.advisor_store import AdvisorStore
from core.enterprise_context import ENTITY_MODE_REAL
from core.org_directory import AccessScope
from nodes.utils.wbs_manager import WBSManager

PB_ID = "business_planning"


@pytest.fixture
def store(tmp_path):
    return AdvisorStore(db_path=str(tmp_path / "advisor.db"))


@pytest.fixture
def client(store, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                 # ./projects 가 tmp 아래에 생기도록
    # ★ [2026-08-05] 작업공간 경로가 절대경로로 고정됐다(`core/paths.py`). cwd 만 옮기면
    #   더 이상 격리되지 않으므로 **격리 지점을 함께 돌린다.** 이 한 줄이 없으면 테스트가
    #   제품 `projects/` 에 프로젝트를 만든다.
    import core.paths as _paths
    monkeypatch.setattr(_paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(ac, "advisor_store", store)
    app = FastAPI()
    app.include_router(ac.router)
    app.include_router(fc.router)
    return app, TestClient(app)


def _as(app, user_id="bob", dept="hq"):
    scope = AccessScope(user_id=user_id, primary_dept_id=dept, unrestricted=False,
                        readable_dept_ids=frozenset({dept}), writable_dept_ids=frozenset({dept}))
    app.dependency_overrides[current_principal] = lambda: Principal(user_id=user_id, scope=scope)


def _approved_blueprint(store, dept="hq", user="bob", statuses=None, approve=True):
    pb = load_playbook(PB_ID)
    answers = {q.id: [o.key() for o in q.options if o.recommended] for q in pb.questions}
    bp = assemble_blueprint(pb, answers, statuses=statuses or {},
                            initial_prompt="내년도 사업계획을 만들고 싶다")
    bp.owner_dept_id, bp.owner_user_id = dept, user
    bp.tenant_id, bp.enterprise_scope_id, bp.entity_mode = "tenant_default", "hq", ENTITY_MODE_REAL
    saved = store.save_blueprint(bp)
    if approve:
        saved = store.set_blueprint_decision(saved.blueprint_id, "approved", user)
    return saved


# ── ① 승인 게이트 ────────────────────────────────────────────────────────
def test_draft_blueprint_cannot_bootstrap(client, store):
    app, c = client
    _as(app)
    bp = _approved_blueprint(store, approve=False)
    r = c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
               json={"project_id": "P_DRAFT"})
    assert r.status_code == 409
    assert not os.path.isdir("./projects/P_DRAFT"), "실패했으면 디렉터리도 남지 않아야 한다"


def test_rejected_blueprint_cannot_bootstrap(client, store):
    app, c = client
    _as(app)
    bp = _approved_blueprint(store, approve=False)
    store.set_blueprint_decision(bp.blueprint_id, "rejected", "bob", reason="데이터 부족")
    r = c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
               json={"project_id": "P_REJ"})
    assert r.status_code == 409


# ── ② ③ ④ 부트스트랩 ────────────────────────────────────────────────────
def test_bootstrap_creates_project_with_inherited_context(client, store):
    app, c = client
    _as(app)
    bp = _approved_blueprint(store)
    r = c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
               json={"project_id": "P_OK"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["blueprint_id"] == bp.blueprint_id
    assert d["template_id"] == bp.system.template_id, "Blueprint 의 추천 템플릿이 기본"

    own = fc._read_project_ownership("./projects/P_OK")
    assert own["owner_dept_id"] == "hq"
    assert own["blueprint_id"] == bp.blueprint_id, "추적 링크가 project_meta 에 남아야 한다"
    assert own["entity_mode"] == ENTITY_MODE_REAL
    assert own["enterprise_scope_id"] == "hq"
    assert own["tenant_id"] == "tenant_default"


def test_bootstrap_context_comes_from_blueprint_not_headers(client, store):
    """★ 요청 헤더의 문맥으로 만들면 승인된 Blueprint 와 다른 문맥의 프로젝트가 생긴다."""
    app, c = client
    _as(app)
    bp = _approved_blueprint(store)
    r = c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
               json={"project_id": "P_CTX"},
               headers={"X-Enterprise-Scope": "plant_99"})
    assert r.status_code == 200, r.text
    assert fc._read_project_ownership("./projects/P_CTX")["enterprise_scope_id"] == "hq"


def test_bootstrap_seeds_initial_idea_with_user_words_first(client, store):
    """★ 사용자의 원래 말이 앞, Blueprint 요약이 뒤 — 순서를 바꾸면 LLM 이 요약을 발화로 오해한다."""
    app, c = client
    _as(app)
    bp = _approved_blueprint(store)
    c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
           json={"project_id": "P_IDEA"})
    with open("./projects/P_IDEA/latest_state.json", encoding="utf-8") as f:
        st = json.load(f)
    assert st["blueprint_id"] == bp.blueprint_id
    idea = st["initial_idea"]
    assert idea.startswith("내년도 사업계획을 만들고 싶다")
    assert "[승인된 Solution Blueprint" in idea


def test_brief_is_summary_not_full_payload(client, store):
    """④ 프롬프트에는 요약만(§10.4). 전문을 넣으면 프롬프트 예산이 터진다."""
    app, c = client
    _as(app)
    bp = _approved_blueprint(store)
    brief = ac._blueprint_brief(bp)
    assert "데이터 준비도" in brief and "필수 데이터" in brief
    assert "제외 범위(만들지 말 것)" in brief, "고르지 않은 범위는 '하지 말 것'의 근거다"
    # 전문(JSON) 보다 현저히 짧아야 한다
    assert len(brief) < len(bp.model_dump_json()) / 3


def test_brief_flags_missing_required_data(client, store):
    app, c = client
    _as(app)
    bp = _approved_blueprint(store)          # statuses 없음 → 필수 다수 미확보
    brief = ac._blueprint_brief(bp)
    assert "⚠️ 미확보 필수 데이터" in brief
    assert "가정값으로만 동작" in brief, "무엇이 위험한지 말해줘야 한다"


def test_state_model_accepts_blueprint_id():
    """ProjectState 는 extra='forbid' 라 선언이 없으면 ValidationError 로 즉사한다."""
    from state_models import ProjectState
    s = ProjectState.model_validate({"project_name": "p", "blueprint_id": "bp_1"})
    assert s.blueprint_id == "bp_1"


def test_blueprint_id_is_accumulated_field():
    """스프린트 사이에 유실되면 추적성이 끊긴다(다시 채워줄 곳이 없다)."""
    assert "blueprint_id" in fc._ACCUMULATED_FIELDS


def test_duplicate_project_id_409(client, store):
    app, c = client
    _as(app)
    bp = _approved_blueprint(store)
    body = {"project_id": "P_DUP"}
    assert c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
                  json=body).status_code == 200
    assert c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
                  json=body).status_code == 409


def test_unknown_template_404(client, store):
    app, c = client
    _as(app)
    bp = _approved_blueprint(store)
    r = c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
               json={"project_id": "P_T", "template_id": "ghost_xyz"})
    assert r.status_code == 404


def test_other_dept_cannot_bootstrap(client, store):
    app, c = client
    _as(app, user_id="bob", dept="hq")
    bp = _approved_blueprint(store, dept="hq")
    _as(app, user_id="eve", dept="sales")
    r = c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
               json={"project_id": "P_EVE"})
    assert r.status_code == 403


# ── ⑤ 데이터 태스크 ──────────────────────────────────────────────────────
def test_data_tasks_require_existing_wbs(client, store):
    """★ 기획 전에는 409 — 조용히 만들어 두면 initialize_wbs 가 지운 줄도 모른다."""
    app, c = client
    _as(app)
    bp = _approved_blueprint(store)
    c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
           json={"project_id": "P_NOWBS"})
    r = c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/create-data-tasks"
               f"?project_id=P_NOWBS")
    assert r.status_code == 409
    assert "기획" in r.json()["detail"]


def test_data_tasks_appended_after_planning(client, store):
    app, c = client
    _as(app)
    bp = _approved_blueprint(store, statuses={"master_org": "held"})
    c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
           json={"project_id": "P_WBS"})
    # 기획이 끝난 상태를 흉내낸다
    WBSManager(workspace_root="./projects/P_WBS").initialize_wbs(
        "P_WBS", [{"task_id": "WBS-001", "title": "기획", "status": "DONE"}])

    r = c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/create-data-tasks"
               f"?project_id=P_WBS")
    assert r.status_code == 200, r.text
    created = r.json()["data"]["created"]
    assert created, "미확보 데이터가 있으면 태스크가 생겨야 한다"
    assert all(t["task_id"].startswith("TASK_DATA_") for t in created)
    terms = {t["canonical_term"] for t in created}
    assert "조직 · 법인" not in terms, "보유(held) 항목은 태스크를 만들지 않는다"

    wbs = WBSManager(workspace_root="./projects/P_WBS").get_wbs()
    assert wbs["total_tasks"] == 1 + len(created), "기존 태스크를 지우지 않고 append"
    dt = next(t for t in wbs["tasks"] if t["task_id"] == "TASK_DATA_01")
    # 태스크만 있고 왜/무엇을 모르면 방치된다
    assert "[없으면]" in dt["goal"] and "[조치]" in dt["goal"]
    assert "[데이터 구분]" in dt["goal"], "실제/계획/전망 구분이 태스크에도 실려야 한다(§7.1)"


def test_data_tasks_empty_when_all_held(client, store):
    app, c = client
    _as(app)
    pb = load_playbook(PB_ID)
    bp = _approved_blueprint(store, statuses={r.key: "held" for r in pb.data_requirements})
    c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
           json={"project_id": "P_ALL"})
    WBSManager(workspace_root="./projects/P_ALL").initialize_wbs("P_ALL", [])
    r = c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/create-data-tasks"
               f"?project_id=P_ALL")
    assert r.status_code == 200
    assert r.json()["data"]["created"] == []


def test_data_tasks_missing_project_404(client, store):
    app, c = client
    _as(app)
    bp = _approved_blueprint(store)
    r = c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/create-data-tasks"
               f"?project_id=P_GHOST")
    assert r.status_code == 404


def test_wbs_add_data_task_raises_without_wbs(tmp_path):
    mgr = WBSManager(workspace_root=str(tmp_path / "ws"))
    with pytest.raises(FileNotFoundError):
        mgr.add_data_task("t", "g")


# ── 공유 경로: create_project 도 같은 헬퍼를 쓴다 ──────────────────────────
def test_create_project_route_records_ecm_context(client):
    """`POST /projects` 와 부트스트랩이 같은 `provision_project` 를 쓰므로 문맥이 함께 남는다."""
    app, c = client
    _as(app)
    r = c.post("/api/v1/factory/projects", json={"project_id": "P_PLAIN"})
    assert r.status_code == 200, r.text
    own = fc._read_project_ownership("./projects/P_PLAIN")
    assert own["entity_mode"] == ENTITY_MODE_REAL
    assert own["enterprise_scope_id"] == "hq"
    assert own["blueprint_id"] == "", "상담 없이 만든 프로젝트는 Blueprint 링크가 없다"


def test_project_meta_preserves_context_on_template_change(client):
    """⚠️ 템플릿만 바꾸는 호출이 문맥을 날리면 프로젝트가 조용히 격리에서 빠진다."""
    app, c = client
    _as(app)
    c.post("/api/v1/factory/projects", json={"project_id": "P_KEEP"})
    fc._write_project_meta("./projects/P_KEEP", "manufacturing-qc")   # 문맥 인자 없이 호출
    own = fc._read_project_ownership("./projects/P_KEEP")
    assert own["enterprise_scope_id"] == "hq"
    assert own["entity_mode"] == ENTITY_MODE_REAL
    assert own["owner_dept_id"] == "hq"
