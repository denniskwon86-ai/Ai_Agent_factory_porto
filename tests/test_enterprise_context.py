# ==========================================
# Enterprise Context (ECM-lite) — `docs/design_enterprise_context_master.md` 최소 선점
#
# 검증하는 계약 다섯:
#  ① **REAL 외 문맥은 아직 만들 수 없다** — 설계서 §2.1-4 "가상 조직은 실제의 안전한 복제본이지
#     운영계 우회 통로가 아니다". 격리 스냅샷·가정 세트·외부 연계 차단(E3)이 없는 상태로 가상
#     자료를 만들게 하면 가정값이 실제와 섞인 채 쌓인다.
#  ② **조회 격리는 목록과 단건 둘 다** — 목록만 필터하고 단건을 안 막으면 id 를 알면 넘어간다.
#     다른 문맥의 자료는 이 문맥에서 '존재하지 않는 것'이므로 403 이 아니라 404 다.
#  ③ **Blueprint 문맥은 상담에서 물려받는다** — 요청 헤더가 아니라. 상담 중간에 스위처를 바꿨다고
#     Blueprint 가 다른 문맥으로 태어나면 가정과 실제가 섞인다.
#  ④ **구 스키마 DB 가 열려야 한다** — CREATE TABLE IF NOT EXISTS 는 컬럼을 추가하지 않는다.
#     신규 환경에서만 테스트하면 놓치는 함정이라 구 DB 를 만들어 직접 확인한다.
#  ⑤ **문맥 미지정은 종전대로 동작** — 전역 스위처가 없는 동안 범위 지정을 강제하면 기존 흐름이
#     전부 막힌다(Phase 2 사용자 식별과 같은 단계적 도입).
# ==========================================
import os
import sqlite3
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.routes.advisor_control as ac
import config
from api.deps import Principal, current_principal
from core.advisor_blueprint import DATA_KINDS, assemble_blueprint
from core.advisor_playbook import PROFILE_LAYER_PLAYBOOK_BASELINE, load_playbook
from core.advisor_store import AdvisorStore
from core.enterprise_context import (CREATABLE_ENTITY_MODES, ENTITY_MODE_COMPETITOR,
                                     ENTITY_MODE_REAL, ENTITY_MODE_VIRTUAL, ENTITY_MODES,
                                     EnterpriseContext, EnterpriseContextError,
                                     build_context, default_tenant_id, isolation_filter)
from core.org_directory import AccessScope

PB_ID = "business_planning"


# ── ① 문맥 검증 ──────────────────────────────────────────────────────────
def test_default_context_is_real_and_default_tenant():
    ctx = build_context().validate()
    assert ctx.entity_mode == ENTITY_MODE_REAL
    assert ctx.tenant_id == default_tenant_id()


def test_fallback_scope_is_used_when_unspecified():
    """전역 스위처가 없는 동안 요청자의 소속 부서를 범위로 쓴다(단계적 도입)."""
    assert build_context(fallback_scope_id="hq").enterprise_scope_id == "hq"
    assert build_context(enterprise_scope_id="plant_01",
                         fallback_scope_id="hq").enterprise_scope_id == "plant_01"


def test_entity_mode_is_case_insensitive():
    assert build_context(entity_mode="virtual").entity_mode == ENTITY_MODE_VIRTUAL


def test_unknown_entity_mode_rejected():
    with pytest.raises(EnterpriseContextError):
        build_context(entity_mode="SOMETHING").validate()


def test_missing_tenant_rejected():
    with pytest.raises(EnterpriseContextError):
        EnterpriseContext(tenant_id="").validate()


def test_virtual_and_competitor_cannot_be_created_yet():
    """★ 안전장치(E3)가 없는 상태로 가상·경쟁사 자료를 만들 수 있게 열어두면 안 된다."""
    for mode in (ENTITY_MODE_VIRTUAL, ENTITY_MODE_COMPETITOR):
        ctx = build_context(entity_mode=mode)
        ctx.validate()                                  # 조회 문맥으로는 유효
        with pytest.raises(EnterpriseContextError) as e:
            ctx.validate(creating=True)                 # 생성은 막힌다
        assert "E3" in str(e.value), "왜 막혔는지 로드맵 단계를 알려줘야 한다"
    assert CREATABLE_ENTITY_MODES == (ENTITY_MODE_REAL,)


def test_scenario_id_not_allowed_in_real_context():
    """실제 문맥에 시나리오 id 가 붙으면 실제값과 가정값의 구분이 무너진다(비협상 3)."""
    with pytest.raises(EnterpriseContextError):
        build_context(entity_mode=ENTITY_MODE_REAL, scenario_id="scn_1").validate()


def test_isolation_filter_shape():
    ctx = build_context(tenant_id="t1", entity_mode=ENTITY_MODE_VIRTUAL)
    assert isolation_filter(ctx) == {"tenant_id": "t1", "entity_mode": ENTITY_MODE_VIRTUAL}
    assert isolation_filter(None) == {}, "문맥이 없으면 격리하지 않는다(하위호환)"


def test_all_three_modes_declared():
    assert ENTITY_MODES == (ENTITY_MODE_REAL, ENTITY_MODE_VIRTUAL, ENTITY_MODE_COMPETITOR)


# ── 설계서 정렬: data_kind / 플레이북 프로필 층 ────────────────────────────
def test_competitor_is_a_distinct_data_kind():
    """비협상 원칙 3 이 경쟁사 추정치를 별도 종류로 요구한다(§7.3 — 같은 차트에 표시될 수 있다)."""
    assert "competitor" in DATA_KINDS
    assert "scenario" in DATA_KINDS


def test_playbook_declares_baseline_profile_layer():
    """D-002(2026-07-28 개정) — 플레이북은 '산업 공통 프로필'이 아니라 **업무·솔루션 기준선**이다.
    `business_planning` 은 업무 유형이라 제조업 외 산업에도 적용되고, 한 산업 안에도 여러
    플레이북이 있으므로 1:1 이 아니다(Codex 교차검토)."""
    pb = load_playbook(PB_ID)
    assert pb.profile_layer == PROFILE_LAYER_PLAYBOOK_BASELINE
    assert isinstance(pb.industry_codes, list)
    assert pb.version >= 1, "재현 지문에 버전이 필요하다(D-002 보완 ②)"


# ── ④ 구 스키마 마이그레이션 ──────────────────────────────────────────────
_LEGACY_DDL = """
CREATE TABLE consultations (consultation_id TEXT PRIMARY KEY, user_id TEXT, owner_dept_id TEXT,
  scope TEXT, playbook_id TEXT, status TEXT, initial_prompt TEXT, summary TEXT,
  created_at TEXT, updated_at TEXT);
CREATE TABLE solution_blueprints (blueprint_id TEXT PRIMARY KEY, consultation_id TEXT,
  owner_dept_id TEXT, owner_user_id TEXT, title TEXT, business_domain TEXT, playbook_id TEXT,
  payload_json TEXT, readiness_score REAL, status TEXT, approved_by TEXT, approved_at TEXT,
  version INTEGER, created_at TEXT, updated_at TEXT);
"""


def test_legacy_db_gets_context_columns(tmp_path):
    """★ CREATE TABLE IF NOT EXISTS 는 기존 테이블에 컬럼을 추가하지 않는다."""
    p = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(p)
    conn.executescript(_LEGACY_DDL)
    conn.execute("INSERT INTO consultations VALUES ('cons_old','bob','hq','department',?,"
                 "'open','기존 상담','','t','t')", (PB_ID,))
    conn.commit()
    conn.close()

    store = AdvisorStore(db_path=p)
    row = store.get_consultation("cons_old")
    assert row is not None, "구 DB 를 열지 못하면 기존 상담이 전부 사라진다"
    assert row["initial_prompt"] == "기존 상담", "기존 데이터는 보존되어야 한다"
    assert row["tenant_id"] == "tenant_default", "신규 컬럼은 기본값으로 채워진다"
    assert row["entity_mode"] == ENTITY_MODE_REAL
    cols = {r[1] for r in sqlite3.connect(p).execute("PRAGMA table_info(solution_blueprints)")}
    assert {"tenant_id", "enterprise_scope_id", "entity_mode"} <= cols


def test_migration_is_idempotent(tmp_path):
    p = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(p)
    conn.executescript(_LEGACY_DDL)
    conn.commit()
    conn.close()
    for _ in range(3):
        AdvisorStore(db_path=p)          # 재기동마다 불린다 — 두 번째부터 죽으면 안 된다


# ── ② ③ 저장소 격리 ─────────────────────────────────────────────────────
@pytest.fixture
def store(tmp_path):
    return AdvisorStore(db_path=str(tmp_path / "advisor.db"))


def test_consultation_records_context(store):
    ctx = build_context(tenant_id="t_ls", enterprise_scope_id="plant_01")
    c = store.create_consultation(user_id="bob", owner_dept_id="hq", ctx=ctx)
    assert c["tenant_id"] == "t_ls"
    assert c["enterprise_scope_id"] == "plant_01"
    assert c["entity_mode"] == ENTITY_MODE_REAL


def test_list_is_isolated_by_tenant_and_mode(store):
    store.create_consultation(user_id="bob", ctx=build_context(tenant_id="t_a"))
    store.create_consultation(user_id="bob", ctx=build_context(tenant_id="t_b"))
    store.create_consultation(user_id="bob", ctx=build_context(tenant_id="t_a",
                                                              entity_mode=ENTITY_MODE_VIRTUAL))
    assert len(store.list_consultations(ctx=build_context(tenant_id="t_a"))) == 1
    assert len(store.list_consultations(ctx=build_context(tenant_id="t_b"))) == 1
    assert len(store.list_consultations(
        ctx=build_context(tenant_id="t_a", entity_mode=ENTITY_MODE_VIRTUAL))) == 1
    assert len(store.list_consultations(ctx=None)) == 3, "문맥 없으면 격리하지 않는다"


def test_blueprint_list_is_isolated(store):
    pb = load_playbook(PB_ID)
    for tenant in ("t_a", "t_b"):
        bp = assemble_blueprint(pb, {})
        bp.tenant_id = tenant
        store.save_blueprint(bp)
    assert len(store.list_blueprints(ctx=build_context(tenant_id="t_a"))) == 1
    assert len(store.list_blueprints(ctx=None)) == 2


def test_rollup_is_isolated(store):
    pb = load_playbook(PB_ID)
    bp = assemble_blueprint(pb, {}, statuses={"master_org": "held"})
    bp.tenant_id, bp.owner_dept_id = "t_a", "hq"
    store.save_blueprint(bp)
    assert store.requirement_rollup(dept_ids=["hq"], ctx=build_context(tenant_id="t_a"))
    assert store.requirement_rollup(dept_ids=["hq"], ctx=build_context(tenant_id="t_b")) == []


# ── API ──────────────────────────────────────────────────────────────────
@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(ac, "advisor_store", store)
    app = FastAPI()
    app.include_router(ac.router)
    return app, TestClient(app)


def _as(app, user_id="bob", dept="hq"):
    scope = AccessScope(user_id=user_id, primary_dept_id=dept, unrestricted=False,
                        readable_dept_ids=frozenset({dept}), writable_dept_ids=frozenset({dept}))
    app.dependency_overrides[current_principal] = lambda: Principal(user_id=user_id, scope=scope)


def _start(c, headers=None):
    r = c.post("/api/v1/advisor/consultations",
               json={"initial_prompt": "내년 사업계획", "playbook_id": PB_ID},
               headers=headers or {})
    return r


def test_api_default_context_recorded(client):
    app, c = client
    _as(app)
    d = _start(c).json()["data"]["consultation"]
    assert d["tenant_id"] == default_tenant_id()
    assert d["entity_mode"] == ENTITY_MODE_REAL
    assert d["enterprise_scope_id"] == "hq", "문맥 미지정 시 소속 부서가 범위"


def test_api_context_headers_are_honored(client):
    app, c = client
    _as(app)
    d = _start(c, headers={config.ECM_TENANT_HEADER: "t_ls",
                           config.ECM_SCOPE_HEADER: "plant_battery_01"}
               ).json()["data"]["consultation"]
    assert d["tenant_id"] == "t_ls" and d["enterprise_scope_id"] == "plant_battery_01"


def test_api_virtual_creation_is_blocked(client):
    """★ 가상 문맥으로 상담을 만들려 하면 400 + 이유(E3 선행)를 알려준다."""
    app, c = client
    _as(app)
    r = _start(c, headers={config.ECM_MODE_HEADER: ENTITY_MODE_VIRTUAL})
    assert r.status_code == 400
    assert "E3" in r.json()["detail"]


def test_api_bad_mode_is_400(client):
    app, c = client
    _as(app)
    assert _start(c, headers={config.ECM_MODE_HEADER: "NOPE"}).status_code == 400


def test_api_cross_context_single_fetch_is_404(client):
    """★ 목록만 격리하고 단건을 안 막으면 id 를 알면 넘어간다."""
    app, c = client
    _as(app)
    cid = _start(c, headers={config.ECM_TENANT_HEADER: "t_a"}
                 ).json()["data"]["consultation"]["consultation_id"]
    # 같은 테넌트 → 보인다
    assert c.get(f"/api/v1/advisor/consultations/{cid}",
                 headers={config.ECM_TENANT_HEADER: "t_a"}).status_code == 200
    # 다른 테넌트 → 없는 것으로 답한다(403 이 아니라 404)
    r = c.get(f"/api/v1/advisor/consultations/{cid}", headers={config.ECM_TENANT_HEADER: "t_b"})
    assert r.status_code == 404
    # 다른 상태(가상 문맥에서 조회) → 없는 것으로 답하고, 어느 문맥의 자료인지 알려준다
    r = c.get(f"/api/v1/advisor/consultations/{cid}",
              headers={config.ECM_TENANT_HEADER: "t_a",
                       config.ECM_MODE_HEADER: ENTITY_MODE_VIRTUAL})
    assert r.status_code == 404
    assert "실제 운영 문맥" in r.json()["detail"]


def test_api_cross_context_write_is_blocked(client):
    app, c = client
    _as(app)
    cid = _start(c, headers={config.ECM_TENANT_HEADER: "t_a"}
                 ).json()["data"]["consultation"]["consultation_id"]
    r = c.post(f"/api/v1/advisor/consultations/{cid}/messages",
               json={"question_id": "Q_PURPOSE", "selected_values": ["plan_build"]},
               headers={config.ECM_TENANT_HEADER: "t_b"})
    assert r.status_code == 404


def test_api_list_is_context_isolated(client):
    app, c = client
    _as(app)
    _start(c, headers={config.ECM_TENANT_HEADER: "t_a"})
    _start(c, headers={config.ECM_TENANT_HEADER: "t_b"})
    a = c.get("/api/v1/advisor/consultations", headers={config.ECM_TENANT_HEADER: "t_a"})
    assert len(a.json()["data"]) == 1


def test_api_blueprint_inherits_context_from_consultation(client):
    """★ Blueprint 문맥은 요청 헤더가 아니라 상담에서 물려받는다."""
    app, c = client
    _as(app)
    pb = load_playbook(PB_ID)
    hdr = {config.ECM_TENANT_HEADER: "t_ls", config.ECM_SCOPE_HEADER: "plant_01"}
    cid = _start(c, headers=hdr).json()["data"]["consultation"]["consultation_id"]
    for q in pb.questions:
        rec = next(o.key() for o in q.options if o.recommended)
        c.post(f"/api/v1/advisor/consultations/{cid}/messages",
               json={"question_id": q.id, "selected_values": [rec]}, headers=hdr)
    bp = c.post(f"/api/v1/advisor/consultations/{cid}/blueprint", json={}, headers=hdr
                ).json()["data"]
    assert bp["tenant_id"] == "t_ls"
    assert bp["enterprise_scope_id"] == "plant_01"
    assert bp["entity_mode"] == ENTITY_MODE_REAL
    # 다른 문맥에서 그 Blueprint 를 조회하면 없는 것으로 답한다
    r = c.get(f"/api/v1/advisor/blueprints/{bp['blueprint_id']}",
              headers={config.ECM_TENANT_HEADER: "t_other"})
    assert r.status_code == 404


def test_api_scope_query_param_works_for_links(client):
    """SSE·다운로드 링크는 헤더를 붙일 수 없다(Phase 2 와 같은 이유)."""
    app, c = client
    _as(app)
    r = c.post("/api/v1/advisor/consultations?enterprise_scope=plant_09",
               json={"playbook_id": PB_ID})
    assert r.json()["data"]["consultation"]["enterprise_scope_id"] == "plant_09"
