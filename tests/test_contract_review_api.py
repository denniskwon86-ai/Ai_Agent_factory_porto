"""★★★ [I-4 4c-3·4c-4] 계약 검토 전용 결정 API 와 일반 HOTL 우회 차단.

이 시험이 전제하는 것: **`seeded_org`**(합성 조직). 여기서 보는 것의 절반이
「누가 승인할 수 있는가」이므로 조직 경계가 필요하다. 원장은 conftest 가 `tmp_path`
로 격리한다.

⚠️ 이 파일이 막으려는 것은 하나다 — **원장에 남지 않는 승인.** 일반
  `/hotl/resume` 은 빈 피드백을 사실상 승인으로 다루므로, 계약 검토를 그 경로로
  통과시키면 「누가 무엇을 보고 승인했는가」에 답할 수 없다. 답할 수 없는 승인은
  승인이 아니다.
"""
import unittest.mock as mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routes.factory_control as fc
from core import contract_review_gate as gate
from tests import org_seed

FP_A = "a" * 64
FP_B = "b" * 64


@pytest.fixture
def client(tmp_path, monkeypatch, enforced_org):
    """권한 강제를 켠 앱. **전제는 `enforced_org`**(합성 조직 + 정책 파일 ON).

    ⚠️ `ORG_TRUST_HEADER` 를 함께 켠다 — 이 스위치가 꺼져 있으면 서버가
      `X-Factory-User` 를 **무시**하고 전부 401 이 된다. 그러면 「권한이 막았다」와
      「신원을 못 읽었다」가 같은 모양이 되어 경계 시험이 의미를 잃는다."""
    import config

    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    monkeypatch.chdir(tmp_path)
    import core.paths as _paths
    monkeypatch.setattr(_paths, "PROJECTS_DIR", str(tmp_path / "projects"))
    app = FastAPI()
    app.include_router(fc.router)
    c = TestClient(app)
    r = c.post("/api/v1/factory/projects", json={"project_id": "P1"},
               headers={"X-Factory-User": org_seed.ADMIN})
    assert r.status_code == 200, r.text
    return c


def _as(user):
    return {"X-Factory-User": user}


def _checkpoint(**kw):
    """체크포인트 계약 상태 대역. **서버가 여기서 지문을 파생한다.**"""
    base = {"app_runtime_contract_fingerprint": FP_B,
            "approved_contract_fingerprint": FP_A,
            "app_runtime_contract_status": "COMPILED",
            "contract_review_request_event_id": "",
            "runtime_contract_profile": "v1"}
    base.update(kw)

    async def _read(task_id, project_id):
        return base
    return _read


@pytest.fixture
def ledger():
    from core.decision_ledger import decision_ledger
    return decision_ledger


def _open_request(ledger, project_id="P1", fp=FP_B, prev=FP_A):
    d = gate.evaluate(requires_contract=True, compiled_fingerprint=fp,
                      approved_fingerprint=prev, contract_status="COMPILED")
    ev, _ = gate.ensure_review_request(ledger, d, project_id=project_id,
                                       task_ids=["WBS-001"])
    return ev


# ── 조회 ─────────────────────────────────────────────────────────────────
def test_pending_reports_the_open_request(client, ledger):
    ev = _open_request(ledger)
    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()):
        r = client.get("/api/v1/factory/P1/contract-review/pending",
                       params={"task_id": "WBS-001"}, headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["pending"] is True
    assert d["compiled_fingerprint"] == FP_B
    assert d["previous_approved_fingerprint"] == FP_A
    assert d["request_event_id"] == ev["event_id"]


def test_pending_is_false_when_the_gate_auto_passes(client, ledger):
    ck = _checkpoint(app_runtime_contract_fingerprint=FP_A,
                     approved_contract_fingerprint=FP_A,
                     app_runtime_contract_status="APPROVED")
    with mock.patch.object(fc.orchestrator, "read_contract_state", ck):
        r = client.get("/api/v1/factory/P1/contract-review/pending",
                       params={"task_id": "WBS-001"}, headers=_as(org_seed.ADMIN))
    assert r.json()["data"] == {"pending": False, "verdict": "AUTO_PASS",
                                "reason": r.json()["data"]["reason"]}


# ── 결정 ─────────────────────────────────────────────────────────────────
def test_approval_is_recorded_and_the_state_is_sealed(client, ledger):
    ev = _open_request(ledger)
    applied = {}

    async def _apply(task_id, project_id, updates):
        applied.update(updates)
        return True

    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()), \
         mock.patch.object(fc.orchestrator, "apply_contract_decision", _apply):
        r = client.post("/api/v1/factory/P1/contract-review/decision",
                        json={"task_id": "WBS-001", "request_event_id": ev["event_id"],
                              "decision": "APPROVE", "rationale": "확인했습니다"},
                        headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["decision"] == "APPROVE" and body["event_id"]

    # ★ 승인은 **그때 본 지문**을 박는다
    assert applied["approved_contract_fingerprint"] == FP_B
    assert applied["app_runtime_contract_status"] == "APPROVED"
    assert applied["contract_review_request_event_id"] == ""

    # ★ 원장에 요청의 자식으로 남는다
    row = ledger.get_event(body["event_id"])
    assert row["event_type"] == gate.EVENT_APPROVED
    assert row["parent_event_id"] == ev["event_id"]
    assert row["actor_type"] == "user" and row["actor_id"] == org_seed.ADMIN
    assert row["rationale"] == "확인했습니다"


def test_rejection_clears_the_approved_fingerprint(client, ledger):
    ev = _open_request(ledger)
    applied = {}

    async def _apply(task_id, project_id, updates):
        applied.update(updates)
        return True

    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()), \
         mock.patch.object(fc.orchestrator, "apply_contract_decision", _apply):
        r = client.post("/api/v1/factory/P1/contract-review/decision",
                        json={"task_id": "WBS-001", "request_event_id": ev["event_id"],
                              "decision": "REJECT", "rationale": "데이터셋이 다릅니다"},
                        headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    assert applied["approved_contract_fingerprint"] == ""
    assert applied["app_runtime_contract_status"] == "COMPILED"
    assert ledger.get_event(r.json()["data"]["event_id"])["event_type"] == gate.EVENT_REJECTED


def test_a_second_decision_is_409(client, ledger):
    ev = _open_request(ledger)

    async def _apply(task_id, project_id, updates):
        return True

    body = {"task_id": "WBS-001", "request_event_id": ev["event_id"],
            "decision": "APPROVE"}
    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()), \
         mock.patch.object(fc.orchestrator, "apply_contract_decision", _apply):
        assert client.post("/api/v1/factory/P1/contract-review/decision", json=body,
                           headers=_as(org_seed.ADMIN)).status_code == 200
        again = client.post("/api/v1/factory/P1/contract-review/decision", json=body,
                            headers=_as(org_seed.ADMIN))
    assert again.status_code == 409
    assert "이미 결정된" in again.json()["detail"]


def test_a_request_from_another_project_is_409(client, ledger):
    other = _open_request(ledger, project_id="P_OTHER")

    async def _apply(task_id, project_id, updates):
        return True

    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()), \
         mock.patch.object(fc.orchestrator, "apply_contract_decision", _apply):
        r = client.post("/api/v1/factory/P1/contract-review/decision",
                        json={"task_id": "WBS-001", "request_event_id": other["event_id"],
                              "decision": "APPROVE"}, headers=_as(org_seed.ADMIN))
    assert r.status_code == 409
    assert "다른 프로젝트" in r.json()["detail"]


def test_a_contract_that_changed_since_the_request_is_409(client, ledger):
    """★★★ 요청 이후 계약이 바뀌었으면 그 승인은 **다른 것을 본 승인**이다."""
    ev = _open_request(ledger, fp=FP_B)

    async def _apply(task_id, project_id, updates):
        return True

    moved = _checkpoint(app_runtime_contract_fingerprint="c" * 64)
    with mock.patch.object(fc.orchestrator, "read_contract_state", moved), \
         mock.patch.object(fc.orchestrator, "apply_contract_decision", _apply):
        r = client.post("/api/v1/factory/P1/contract-review/decision",
                        json={"task_id": "WBS-001", "request_event_id": ev["event_id"],
                              "decision": "APPROVE"}, headers=_as(org_seed.ADMIN))
    assert r.status_code == 409
    assert "요청 당시 계약과 현재 계약이 다릅니다" in r.json()["detail"]


def test_client_cannot_supply_the_fingerprint(client, ledger):
    """★★★ 본문에 지문을 실어 보내도 **서버가 파생한 값**이 이긴다.

    ⚠️ 클라이언트가 지문을 정할 수 있으면 「사람이 A 를 보고 B 를 승인하는」 경로가
      열린다. 모델이 여분 필드를 거부하는지까지 함께 본다."""
    ev = _open_request(ledger)

    async def _apply(task_id, project_id, updates):
        return True

    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()), \
         mock.patch.object(fc.orchestrator, "apply_contract_decision", _apply):
        r = client.post("/api/v1/factory/P1/contract-review/decision",
                        json={"task_id": "WBS-001", "request_event_id": ev["event_id"],
                              "decision": "APPROVE",
                              "compiled_fingerprint": "c" * 64,      # ← 무시돼야 한다
                              "approved_contract_fingerprint": "c" * 64},
                        headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["contract_fingerprint"] == FP_B


def test_nothing_to_decide_is_409(client, ledger):
    ck = _checkpoint(app_runtime_contract_fingerprint=FP_A,
                     approved_contract_fingerprint=FP_A,
                     app_runtime_contract_status="APPROVED")
    with mock.patch.object(fc.orchestrator, "read_contract_state", ck):
        r = client.post("/api/v1/factory/P1/contract-review/decision",
                        json={"task_id": "WBS-001", "request_event_id": "dle_x",
                              "decision": "APPROVE"}, headers=_as(org_seed.ADMIN))
    assert r.status_code == 409


@pytest.mark.parametrize("bad", ["", "YES", "승인", "REVOKE", "APPROVE_ALL"])
def test_unknown_decision_word_is_422(client, ledger, bad):
    """⚠️ 모르는 낱말을 **추측하지 않는다.** 「승인」을 `APPROVE` 로 읽어 주기
    시작하면 어디까지 읽어 주는지 아무도 모르게 된다."""
    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()):
        r = client.post("/api/v1/factory/P1/contract-review/decision",
                        json={"task_id": "WBS-001", "request_event_id": "dle_x",
                              "decision": bad}, headers=_as(org_seed.ADMIN))
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("ok", ["approve", "APPROVE ", " Approve"])
def test_case_and_whitespace_in_the_decision_word_are_absorbed(client, ledger, ok):
    """★ 대소문자·앞뒤 공백까지만 흡수한다 — 전송 잡음이지 다른 뜻이 아니다."""
    ev = _open_request(ledger)

    async def _apply(task_id, project_id, updates):
        return True

    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()),          mock.patch.object(fc.orchestrator, "apply_contract_decision", _apply):
        r = client.post("/api/v1/factory/P1/contract-review/decision",
                        json={"task_id": "WBS-001", "request_event_id": ev["event_id"],
                              "decision": ok}, headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["decision"] == "APPROVE"


def test_the_decision_survives_a_failed_state_update(client, ledger):
    """★★★ 상태 반영이 실패해도 **결정은 원장에 남는다.**

    ⚠️ 원장이 SSOT 이므로 되돌리지 않는다(되돌릴 수도 없다 — 추가만 된다). 대신
      「기록은 됐고 반영이 안 됐다」를 응답이 말해야 한다. 조용히 실패로 보이면
      사람이 **두 번 승인**하고, 두 번째는 409 로 막혀 더 혼란스러워진다."""
    ev = _open_request(ledger)

    async def _apply(task_id, project_id, updates):
        return False

    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()), \
         mock.patch.object(fc.orchestrator, "apply_contract_decision", _apply):
        r = client.post("/api/v1/factory/P1/contract-review/decision",
                        json={"task_id": "WBS-001", "request_event_id": ev["event_id"],
                              "decision": "APPROVE"}, headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["state_applied"] is False
    assert "다시 승인하지 마십시오" in body["note"]
    assert ledger.get_event(body["event_id"])["event_type"] == gate.EVENT_APPROVED


# ── 권한 ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("user", [org_seed.VIEWER_A, org_seed.MEMBER_B, org_seed.NO_DEPT])
def test_a_user_without_project_write_cannot_decide(client, ledger, user):
    ev = _open_request(ledger)
    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()):
        r = client.post("/api/v1/factory/P1/contract-review/decision",
                        json={"task_id": "WBS-001", "request_event_id": ev["event_id"],
                              "decision": "APPROVE"}, headers=_as(user))
    assert r.status_code in (403, 404), r.text


def test_an_unknown_user_cannot_even_see_the_pending_review(client, ledger):
    _open_request(ledger)
    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()):
        r = client.get("/api/v1/factory/P1/contract-review/pending",
                       params={"task_id": "WBS-001"}, headers=_as(org_seed.UNKNOWN))
    assert r.status_code in (401, 403, 404), r.text


# ── [4c-4] 일반 HOTL 우회 차단 ──────────────────────────────────────────
def test_generic_hotl_resume_is_blocked_during_a_contract_review(client, ledger):
    """★★★ 빈 피드백은 사실상 승인이다 — 계약 검토를 그렇게 통과시키지 않는다."""
    _open_request(ledger)
    resumed = {}

    async def _resume(task_id, feedback, project_id):
        resumed["yes"] = True
        return True

    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()), \
         mock.patch.object(fc.orchestrator, "resume_hotl", _resume):
        r = client.post("/api/v1/factory/P1/hotl/resume",
                        json={"task_id": "WBS-001", "feedback": ""},
                        headers=_as(org_seed.ADMIN))
    assert r.status_code == 409, r.text
    assert "계약 검토 대기 중" in r.json()["detail"]
    assert not resumed, "막았다면서 재개가 실행됐다"


def test_generic_hotl_resume_with_feedback_is_also_blocked(client, ledger):
    """⚠️ 피드백이 있어도 막는다. 계약 검토는 «재작업 지시» 가 아니라 **결정**이고,
    그 결정은 원장에 남아야 한다."""
    _open_request(ledger)

    async def _resume(task_id, feedback, project_id):
        return True

    with mock.patch.object(fc.orchestrator, "read_contract_state", _checkpoint()), \
         mock.patch.object(fc.orchestrator, "resume_hotl", _resume):
        r = client.post("/api/v1/factory/P1/hotl/resume",
                        json={"task_id": "WBS-001", "feedback": "데이터셋을 줄여 주세요"},
                        headers=_as(org_seed.ADMIN))
    assert r.status_code == 409


def test_ordinary_hotl_resume_still_works(client, ledger):
    """★ 일반 산출물 HOTL 은 그대로 둔다 — 여기가 깨지면 이번 차단이 «모든 재개를
    막은 것»이 된다."""
    ck = _checkpoint(app_runtime_contract_fingerprint=FP_A,
                     approved_contract_fingerprint=FP_A,
                     app_runtime_contract_status="APPROVED")
    resumed = {}

    async def _resume(task_id, feedback, project_id):
        resumed["yes"] = True
        return True

    with mock.patch.object(fc.orchestrator, "read_contract_state", ck), \
         mock.patch.object(fc.orchestrator, "resume_hotl", _resume):
        r = client.post("/api/v1/factory/P1/hotl/resume",
                        json={"task_id": "WBS-001", "feedback": ""},
                        headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    assert resumed


def test_a_legacy_project_resume_is_not_blocked(client, ledger):
    """⚠️ 계약을 안 쓰는 프로젝트(계약 없음 → `BLOCKED`)는 검토 대기가 아니다.
    `REVIEW_REQUIRED` 일 때만 닫는다 — 그렇지 않으면 레거시가 통째로 멈춘다."""
    ck = _checkpoint(app_runtime_contract_fingerprint="", approved_contract_fingerprint="",
                     app_runtime_contract_status="", runtime_contract_profile="")
    resumed = {}

    async def _resume(task_id, feedback, project_id):
        resumed["yes"] = True
        return True

    with mock.patch.object(fc.orchestrator, "read_contract_state", ck), \
         mock.patch.object(fc.orchestrator, "resume_hotl", _resume):
        r = client.post("/api/v1/factory/P1/hotl/resume",
                        json={"task_id": "WBS-001", "feedback": ""},
                        headers=_as(org_seed.ADMIN))
    assert r.status_code == 200, r.text
    assert resumed


def test_nothing_to_decide_says_so(client, ledger):
    """⚠️ 「지금 볼 것이 없다」와 「없는 요청이다」는 사용자가 할 일이 다르다.
    둘 다 409 지만 문장이 같으면 화면이 무엇을 하라고 말할 수 없다."""
    ck = _checkpoint(app_runtime_contract_fingerprint=FP_A,
                     approved_contract_fingerprint=FP_A,
                     app_runtime_contract_status="APPROVED")
    with mock.patch.object(fc.orchestrator, "read_contract_state", ck):
        r = client.post("/api/v1/factory/P1/contract-review/decision",
                        json={"task_id": "WBS-001", "request_event_id": "dle_x",
                              "decision": "APPROVE"}, headers=_as(org_seed.ADMIN))
    assert r.status_code == 409
    assert "결정할 계약 검토가 없습니다" in r.json()["detail"]


# ── 체크포인트에서 파생한다 ─────────────────────────────────────────────
def test_checkpoint_read_failure_yields_nothing_not_a_default(monkeypatch):
    """★★★ 체크포인트를 못 읽으면 **빈 dict** 다.

    ⚠️ 여기서 기본값을 채우면 그 추측이 곧 승인 근거가 된다 — 예컨대 상태를
      `APPROVED` 로 메우면 「읽지 못한 프로젝트」가 「승인된 프로젝트」가 된다."""
    import asyncio

    from core import async_orchestrator as ao

    async def _boom(*_a, **_k):
        raise RuntimeError("체크포인터가 죽었다")

    monkeypatch.setattr(ao, "get_runtime_app", _boom)
    got = asyncio.run(ao.orchestrator.read_contract_state("T", "P1"))
    assert got == {}, f"판독 실패를 값으로 메웠다: {got}"


def test_checkpoint_read_returns_only_contract_fields(monkeypatch):
    """★ 상태 전체가 아니라 **계약 다섯 필드**만 꺼낸다 — 나머지를 실어 나르면
    이 경로가 상태 유출 통로가 된다."""
    import asyncio

    from core import async_orchestrator as ao

    class _Snap:
        values = {"app_runtime_contract_fingerprint": FP_B,
                  "approved_contract_fingerprint": FP_A,
                  "app_runtime_contract_status": "COMPILED",
                  "contract_review_request_event_id": "dle_1",
                  "runtime_contract_profile": "v1",
                  "prd_summary": "기밀 기획서", "initial_idea": "비밀"}

    class _Engine:
        async def aget_state(self, _config):
            return _Snap()

    async def _engine(*_a, **_k):
        return _Engine()

    monkeypatch.setattr(ao, "get_runtime_app", _engine)
    got = asyncio.run(ao.orchestrator.read_contract_state("T", "P1"))
    assert set(got) == {"app_runtime_contract_fingerprint", "approved_contract_fingerprint",
                        "app_runtime_contract_status", "contract_review_request_event_id",
                        "runtime_contract_profile"}
    assert "prd_summary" not in got


# ── 구조로 잠그는 것 ────────────────────────────────────────────────────
def test_the_pending_route_requires_the_run_capability():
    """★★★ 조회 라우트의 권한 요구를 **구조로** 고정한다.

    ⚠️ 지금 조직 표에서는 이 검사가 동작으로 관찰되지 않는다 — 프로젝트 쓰기
      범위를 가진 역할(member·manager)은 **전부** `PROJECT_RUN` 을 함께 갖기
      때문이다(`_ROLE_CAPS`). 즉 `assert_project_writable` 이 먼저 걸러 낸다.
    ★ 그래도 남겨 둔다. 범위와 권한은 **다른 축**이고, 나중에 「쓰기는 되지만
      실행은 안 되는」 역할이 생기는 순간 이 한 줄이 유일한 방어가 된다. 그때
      없으면 조용히 새어 나간다.
    ⚠️ 쓰기 라우트는 `ROUTE_CAPS` 표가 지키지만 그 표는 **쓰기 전용**이라 GET 은
      들어가지 않는다 — 그래서 핸들러가 직접 요구해야 한다."""
    import ast
    import inspect

    src = inspect.getsource(fc.contract_review_pending)
    tree = ast.parse(inspect.cleandoc(src))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    names = {n.func.id for n in calls}
    assert "assert_project_writable" in names, "프로젝트 쓰기 범위를 확인하지 않는다"
    assert "_require_caps" in names, "PROJECT_RUN 권한을 요구하지 않는다"
    cap_call = next(n for n in calls if n.func.id == "_require_caps")
    assert any(isinstance(a, ast.Name) and a.id == "PROJECT_RUN" for a in cap_call.args), \
        "요구하는 권한이 PROJECT_RUN 이 아니다"


def test_the_decision_request_accepts_only_four_fields():
    """★★★ 요청 모델의 필드를 **글자 그대로** 고정한다.

    ⚠️ 클라이언트가 지문·승인 상태·행위자를 실어 보낼 수 있으면 「사람이 A 를 보고
      B 를 승인하는」 경로가 열린다. 그것을 막는 것은 라우트의 검사가 아니라 **모델에
      그 필드가 없는 것**이다 — 필드가 생기는 순간 누군가 그것을 쓰게 된다.
    ⚠️ 「여분 필드는 무시된다」에 기대지 않는다. 필드가 추가되면 무시되지 않는다."""
    assert set(fc.ContractDecisionRequest.model_fields) == {
        "task_id", "request_event_id", "decision", "rationale"}
