# ==========================================
# Decision Ledger (마스터 명세서 §5.2 / M0 백로그 5)
#
# 검증하는 계약 여섯:
#  ① **수정·삭제가 없다** — 잘못 기록했으면 정정 이벤트로 잇는다. 틀린 기록도 "그때 그렇게
#     판단했다"는 사실이므로 지우면 이력이 거짓이 된다.
#  ② **승인 기록은 저장소 계층에서 자동으로 따라온다** — 라우트에 두면 새 승인 경로가 기록을
#     빠뜨린다(이 프로젝트에서 반복된 배선 누락 유형).
#  ③ **기록 실패를 삼키지 않는다** — 승인 이력이 없는 승인은 §1.3(의도와 결정의 보존) 위반이다.
#  ④ **근거 유무를 조회부가 판단할 수 있다** — evidence_refs 가 비면 is_substantiated=False.
#  ⑤ **해시 체인으로 변조를 탐지한다** — 막지는 못하고 탐지만 한다는 한계를 응답에 명시.
#  ⑥ **문맥·부서 격리** — 감사 이력은 결정 사유·승인자를 담으므로 귀속 불명은 통과시키지 않는다.
# ==========================================
import os
import sqlite3
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.routes.advisor_control as ac
import api.routes.ledger_control as lc
from api.deps import Principal, current_principal
from core.advisor_blueprint import assemble_blueprint
from core.advisor_playbook import load_playbook
from core.advisor_store import AdvisorStore
from core.decision_ledger import (EVENT_TYPES, DecisionLedger, DecisionLedgerError,
                                  _compute_hash)
from core.org_directory import AccessScope

PB_ID = "business_planning"


@pytest.fixture
def ledger(tmp_path):
    return DecisionLedger(db_path=str(tmp_path / "ledger.db"))


def _ev(ledger, **kw):
    base = dict(event_type="BLUEPRINT_APPROVED", subject_type="blueprint",
                subject_id="bp_1", actor_type="user", actor_id="bob")
    base.update(kw)
    return ledger.append(**base)


# ── ① 불변성 ─────────────────────────────────────────────────────────────
def test_no_update_or_delete_methods():
    """★ 수정·삭제 메서드가 존재하지 않아야 한다. 있으면 누군가 쓴다."""
    forbidden = [n for n in dir(DecisionLedger)
                 if any(k in n.lower() for k in ("update", "delete", "remove", "purge"))]
    assert forbidden == [], f"불변 이력에 있어서는 안 되는 메서드: {forbidden}"


def test_correction_requires_parent(ledger):
    """정정인데 대상이 없으면 무엇을 정정하는지 알 수 없다."""
    with pytest.raises(DecisionLedgerError):
        _ev(ledger, event_type="CORRECTION", subject_id="bp_1")


def test_correction_chains_to_parent(ledger):
    first = _ev(ledger, decision="승인", rationale="준비도 64점")
    fix = _ev(ledger, event_type="CORRECTION", parent_event_id=first["event_id"],
              decision="정정: 준비도 산정 오류", rationale="외부지표 상태를 잘못 입력했다")
    assert fix["parent_event_id"] == first["event_id"]
    hist = ledger.subject_history("blueprint", "bp_1")
    assert [h["event_type"] for h in hist] == ["BLUEPRINT_APPROVED", "CORRECTION"]
    assert hist[0]["decision"] == "승인", "원본은 그대로 남아 있어야 한다"


def test_unknown_parent_rejected(ledger):
    with pytest.raises(DecisionLedgerError):
        _ev(ledger, event_type="CORRECTION", parent_event_id="dle_ghost")


# ── 유형 검증 ────────────────────────────────────────────────────────────
def test_unknown_event_type_rejected(ledger):
    """오타로 만든 유형이 조용히 쌓이면 집계가 조각난다."""
    with pytest.raises(DecisionLedgerError):
        _ev(ledger, event_type="BLUEPRINT_APROVED")


def test_unknown_subject_and_actor_type_rejected(ledger):
    with pytest.raises(DecisionLedgerError):
        _ev(ledger, subject_type="문서")
    with pytest.raises(DecisionLedgerError):
        _ev(ledger, actor_type="robot")


def test_missing_subject_id_rejected(ledger):
    with pytest.raises(DecisionLedgerError):
        _ev(ledger, subject_id="")


def test_spec_required_event_types_present():
    """§5.2 가 열거한 10종이 모두 등록돼 있어야 한다."""
    required = {"REQUIREMENT_CONFIRMED", "BLUEPRINT_APPROVED", "DATA_REQUIREMENT_ACCEPTED",
                "MASTER_VALUE_CHANGED", "DATA_CONTRACT_PUBLISHED", "WBS_APPROVED",
                "RELEASE_ACCEPTED", "SCENARIO_EXECUTED", "SHADOW_MODE_PASSED",
                "PRODUCTION_WRITE_APPROVED"}
    assert required <= set(EVENT_TYPES)


def test_ecm_event_types_present():
    """ECM §6.2 — 문맥 변경·프로필 변경·복제·권한부여·외부 연결도 Ledger 대상이다."""
    assert {"ENTERPRISE_CONTEXT_CHANGED", "ENTERPRISE_PROFILE_CHANGED", "ENTITY_CLONED",
            "PERMISSION_GRANTED", "EXTERNAL_CONNECTION_APPROVED"} <= set(EVENT_TYPES)


# ── ④ 근거 표시 ──────────────────────────────────────────────────────────
def test_evidence_absence_is_visible(ledger):
    """§5.2 — 근거 없는 결정은 '검증되지 않은 추정'으로 읽혀야 한다."""
    bare = _ev(ledger, subject_id="bp_bare")
    assert bare["is_substantiated"] is False
    withev = _ev(ledger, subject_id="bp_ev", evidence_refs=[{"kind": "readiness", "score": 64}])
    assert withev["is_substantiated"] is True
    assert withev["evidence_refs"][0]["score"] == 64, "근거는 그대로 조회돼야 한다"


# ── ⑤ 해시 체인 ──────────────────────────────────────────────────────────
def test_chain_is_linked_and_verifies(ledger):
    a = _ev(ledger, subject_id="s1")
    b = _ev(ledger, subject_id="s2")
    assert a["prev_hash"] == "" and a["seq"] == 1
    assert b["prev_hash"] == a["event_hash"] and b["seq"] == 2
    v = ledger.verify_chain()
    assert v["ok"] is True and v["checked"] == 2 and v["broken"] == []


def test_tampering_is_detected(ledger):
    """★ DB 를 직접 고치면 탐지된다(막지는 못한다)."""
    _ev(ledger, subject_id="s1", decision="승인")
    _ev(ledger, subject_id="s2", decision="승인")
    _ev(ledger, subject_id="s3", decision="승인")
    with sqlite3.connect(ledger.db_path) as conn:
        conn.execute("UPDATE decision_ledger_events SET decision='반려' WHERE seq=2")
    v = ledger.verify_chain()
    assert v["ok"] is False
    assert 2 in [b["seq"] for b in v["broken"]], "고친 이벤트가 지목되어야 한다"


def test_verify_response_states_its_limitation(ledger):
    """'위조 불가'로 오해하면 안 된다 — 한계를 응답에 명시한다."""
    v = ledger.verify_chain()
    assert "탐지" in v["limitation"]
    assert v["hash_version"]


def test_hash_is_reproducible(ledger):
    ev = _ev(ledger, subject_id="s1", decision="승인", rationale="근거")
    with sqlite3.connect(ledger.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = dict(conn.execute("SELECT * FROM decision_ledger_events WHERE seq=1").fetchone())
    assert _compute_hash(row, "") == ev["event_hash"]


# ── 조회 ─────────────────────────────────────────────────────────────────
def test_filters(ledger):
    _ev(ledger, subject_id="bp_1", project_id="P1", event_type="BLUEPRINT_APPROVED")
    _ev(ledger, subject_id="P1", subject_type="project", project_id="P1",
        event_type="PROJECT_BOOTSTRAPPED")
    _ev(ledger, subject_id="bp_2", event_type="BLUEPRINT_REJECTED")
    assert len(ledger.list_events(project_id="P1")) == 2
    assert len(ledger.list_events(event_type="BLUEPRINT_APPROVED")) == 1
    assert len(ledger.list_events(subject_type="project")) == 1
    assert len(ledger.list_events()) == 3


def test_history_is_chronological(ledger):
    for i in range(3):
        _ev(ledger, subject_id="bp_x", decision=f"d{i}")
    hist = ledger.subject_history("blueprint", "bp_x")
    assert [h["decision"] for h in hist] == ["d0", "d1", "d2"]


def test_context_isolation_in_list(ledger):
    _ev(ledger, subject_id="a", tenant_id="t_a")
    _ev(ledger, subject_id="b", tenant_id="t_b")
    _ev(ledger, subject_id="c", tenant_id="t_a", entity_mode="VIRTUAL")
    assert len(ledger.list_events(tenant_id="t_a", entity_mode="REAL")) == 1
    assert len(ledger.list_events(tenant_id="t_a", entity_mode="VIRTUAL")) == 1


def test_missing_db_is_safe(tmp_path):
    l = DecisionLedger(db_path=str(tmp_path / "sub" / "x.db"))
    assert l.list_events() == []
    assert l.get_event("dle_none") is None


# ── ② ③ 승인 경로 배선 (★ 회귀 방지) ──────────────────────────────────────
@pytest.fixture
def wired(tmp_path, monkeypatch):
    """advisor_store 와 decision_ledger 를 tmp 로 갈아끼운다."""
    import core.advisor_store as store_mod
    import core.decision_ledger as ledger_mod
    l = DecisionLedger(db_path=str(tmp_path / "ledger.db"))
    monkeypatch.setattr(ledger_mod, "decision_ledger", l)
    s = AdvisorStore(db_path=str(tmp_path / "advisor.db"))
    return s, l


def _blueprint(store, statuses=None):
    pb = load_playbook(PB_ID)
    answers = {q.id: [o.key() for o in q.options if o.recommended] for q in pb.questions}
    bp = assemble_blueprint(pb, answers, statuses=statuses or {}, initial_prompt="내년 계획")
    bp.owner_dept_id, bp.owner_user_id = "hq", "bob"
    bp.tenant_id, bp.enterprise_scope_id = "tenant_default", "hq"
    return store.save_blueprint(bp)


def test_approval_writes_ledger_event(wired):
    """★★ 라우트가 아니라 저장소 계층에서 기록되므로 승인 경로가 늘어나도 따라온다."""
    store, ledger = wired
    bp = _blueprint(store)
    store.set_blueprint_decision(bp.blueprint_id, "approved", "kim")

    events = ledger.list_events(subject_type="blueprint", subject_id=bp.blueprint_id)
    assert len(events) == 1, "승인했는데 이력이 없으면 승인 이력 없는 승인이 된다"
    e = events[0]
    assert e["event_type"] == "BLUEPRINT_APPROVED"
    assert e["actor_type"] == "user" and e["actor_id"] == "kim"
    assert e["blueprint_id"] == bp.blueprint_id
    assert e["enterprise_scope_id"] == "hq" and e["entity_mode"] == "REAL"
    assert e["is_substantiated"] is True, "준비도·플레이북·상담이 근거로 실려야 한다"
    kinds = {r["kind"] for r in e["evidence_refs"]}
    assert {"readiness", "playbook", "consultation"} <= kinds


def test_approval_rationale_records_what_was_known(wired):
    """★ 무엇을 알면서 승인했는지가 근거의 핵심이다(결손을 안고 승인한 사실이 남아야 한다)."""
    store, ledger = wired
    bp = _blueprint(store)                      # statuses 없음 → 필수 다수 미확보
    store.set_blueprint_decision(bp.blueprint_id, "approved", "kim")
    e = ledger.list_events(blueprint_id=bp.blueprint_id)[0]
    assert "준비도" in e["rationale"]
    assert "미확보 필수 데이터" in e["rationale"]
    ev = next(r for r in e["evidence_refs"] if r["kind"] == "readiness")
    assert ev["blocking_gaps"], "차단 결손 목록이 근거에 남아야 한다"


def test_rejection_records_reason(wired):
    store, ledger = wired
    bp = _blueprint(store)
    store.set_blueprint_decision(bp.blueprint_id, "rejected", "kim", reason="실적 데이터 없음")
    e = ledger.list_events(blueprint_id=bp.blueprint_id)[0]
    assert e["event_type"] == "BLUEPRINT_REJECTED"
    assert "실적 데이터 없음" in e["decision"]


def test_ledger_failure_is_not_swallowed(wired, monkeypatch):
    """★ 감사 저장소가 죽었으면 호출부가 알아야 한다 — 조용히 넘기면 승인 이력이 사라진다."""
    store, ledger = wired

    def _boom(*a, **kw):
        raise RuntimeError("감사 저장소 장애")

    monkeypatch.setattr(ledger, "append", _boom)
    bp = _blueprint(store)
    with pytest.raises(RuntimeError):
        store.set_blueprint_decision(bp.blueprint_id, "approved", "kim")


# ── API ──────────────────────────────────────────────────────────────────
@pytest.fixture
def client(wired, tmp_path, monkeypatch, seeded_org):
    store, ledger = wired
    monkeypatch.chdir(tmp_path)
    # ★ [2026-08-05] 작업공간 경로가 절대경로로 고정됐다(`core/paths.py`). cwd 만 옮기면
    #   더 이상 격리되지 않으므로 **격리 지점을 함께 돌린다.** 이 한 줄이 없으면 테스트가
    #   제품 `projects/` 에 프로젝트를 만든다.
    import core.paths as _paths
    monkeypatch.setattr(_paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(ac, "advisor_store", store)
    monkeypatch.setattr(lc, "decision_ledger", ledger)
    app = FastAPI()
    app.include_router(lc.router)
    app.include_router(ac.router)
    return app, TestClient(app), store, ledger


def _as(app, user_id="bob", dept="hq", enterprise=False):
    scope = AccessScope(user_id=user_id, primary_dept_id=dept, unrestricted=False,
                        readable_dept_ids=frozenset({dept}), writable_dept_ids=frozenset({dept}),
                        can_run_enterprise=enterprise)
    app.dependency_overrides[current_principal] = lambda: Principal(user_id=user_id, scope=scope)


def test_api_no_write_endpoint(client):
    """★ 쓰기 엔드포인트가 없어야 한다 — 외부에서 임의 기록이 가능하면 증거가 무의미해진다."""
    app, c, _, _ = client
    methods = {(r.path, m) for r in app.routes for m in getattr(r, "methods", set())}
    writes = [(p_, m) for (p_, m) in methods
              if "/ledger" in p_ and m in ("POST", "PUT", "PATCH", "DELETE")]
    assert writes == [], f"Ledger 에 쓰기 경로가 있으면 안 된다: {writes}"


def test_api_event_types_listed(client):
    app, c, _, _ = client
    _as(app)
    d = c.get("/api/v1/ledger/event-types").json()["data"]
    assert "BLUEPRINT_APPROVED" in d["event_types"]
    assert "blueprint" in d["subject_types"]


def test_api_history_after_approval(client):
    app, c, store, _ = client
    _as(app)
    bp = _blueprint(store)
    store.set_blueprint_decision(bp.blueprint_id, "approved", "bob")
    r = c.get(f"/api/v1/ledger/subjects/blueprint/{bp.blueprint_id}/history")
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert len(rows) == 1 and rows[0]["event_type"] == "BLUEPRINT_APPROVED"


def test_api_bad_filters_400(client):
    app, c, _, _ = client
    _as(app)
    assert c.get("/api/v1/ledger/events?event_type=NOPE").status_code == 400
    assert c.get("/api/v1/ledger/events?subject_type=NOPE").status_code == 400
    assert c.get("/api/v1/ledger/subjects/NOPE/x/history").status_code == 400


def test_api_dept_isolation(client):
    """⑥ 감사 이력은 결정 사유·승인자를 담으므로 부서 밖은 보이지 않는다."""
    app, c, store, ledger = client
    bp = _blueprint(store)
    store.set_blueprint_decision(bp.blueprint_id, "approved", "bob")
    _as(app, user_id="bob", dept="hq")
    assert len(c.get("/api/v1/ledger/events").json()["data"]) == 1
    _as(app, user_id="eve", dept="sales")
    assert c.get("/api/v1/ledger/events").json()["data"] == []


def test_api_unattributed_event_is_owner_or_unrestricted_only(client):
    """범위 없는 이벤트는 무제한 권한자 또는 본인(행위자)만 볼 수 있다(fail-closed)."""
    app, c, _, ledger = client
    ledger.append(event_type="MASTER_VALUE_CHANGED", subject_type="master_record",
                  subject_id="M1", actor_type="system", actor_id="")
    _as(app, user_id="bob", dept="hq")
    assert c.get("/api/v1/ledger/events").json()["data"] == []
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="", scope=AccessScope(unrestricted=True))
    assert len(c.get("/api/v1/ledger/events").json()["data"]) == 1


def test_api_verify_requires_enterprise(client):
    """체인은 테넌트를 가로질러 하나이므로 전사 열람 권한자만 검증할 수 있다."""
    app, c, _, _ = client
    _as(app, user_id="bob", dept="hq", enterprise=False)
    assert c.get("/api/v1/ledger/verify").status_code == 403
    _as(app, user_id="exec", dept="hq", enterprise=True)
    r = c.get("/api/v1/ledger/verify")
    assert r.status_code == 200 and r.json()["data"]["ok"] is True


def test_api_bootstrap_records_project_event(client):
    """부트스트랩도 이력을 남긴다 — 이 프로젝트가 어느 승인에서 나왔는지의 근거."""
    app, c, store, ledger = client
    _as(app)
    bp = _blueprint(store)
    store.set_blueprint_decision(bp.blueprint_id, "approved", "bob")
    r = c.post(f"/api/v1/advisor/blueprints/{bp.blueprint_id}/bootstrap-project",
               json={"project_id": "P_LEDGER"})
    assert r.status_code == 200, r.text
    events = ledger.list_events(project_id="P_LEDGER")
    assert [e["event_type"] for e in events] == ["PROJECT_BOOTSTRAPPED"]
    e = events[0]
    assert e["blueprint_id"] == bp.blueprint_id
    assert e["output_version_refs"][0]["project_id"] == "P_LEDGER"


# ── [I-4 4c-2] 조회와 기록을 한 트랜잭션으로 ────────────────────────────
def test_transaction_holds_the_instance_lock():
    """★★★ `transaction()` 은 **인스턴스 락을 잡아야** 한다.

    ⚠️ 이 규칙은 동작으로 안정적으로 관찰되지 않는다. 락을 빼도 SQLite 자신의
      파일 잠금이 쓰기를 직렬화해서, 「조회 → 판단 → 기록」 사이의 틈은 **가끔만**
      벌어진다. 그 가끔을 잡으려고 스레드를 늘리면 시험이 느려지고 불안정해진다 —
      불안정한 시험은 결국 꺼지고, 꺼진 시험은 없는 것과 같다.
    ★ 그래서 **구조**를 잠근다. 락이 사라지면 여기서 즉시 드러난다.
    ⚠️ `append` 안에서 `transaction()` 을 부르면 같은 락을 두 번 잡아 교착한다 —
      그래서 트랜잭션 안에서는 `txn.append` 를 쓴다(그 규칙도 함께 고정한다)."""
    import ast
    import inspect

    from core import decision_ledger as dl

    src = inspect.getsource(dl.DecisionLedger.transaction)
    tree = ast.parse(inspect.cleandoc(src))
    withs = [n for n in ast.walk(tree) if isinstance(n, ast.With)]
    assert withs, "transaction 이 with 문을 쓰지 않는다"
    locked = any(
        isinstance(item.context_expr, ast.Attribute) and item.context_expr.attr == "_lock"
        for w in withs for item in w.items)
    assert locked, "transaction() 이 인스턴스 락을 잡지 않는다 — 조회와 기록 사이가 벌어진다"

    # `append` 와 `_insert` 가 같은 체인 계산을 쓰는지(두 벌이면 해시가 갈린다)
    assert "self._insert(" in inspect.getsource(dl.DecisionLedger.append)
    assert "self._ledger._insert(" in inspect.getsource(dl._LedgerTransaction.append)
    assert "self._ledger._build_row(" in inspect.getsource(dl._LedgerTransaction.append)
