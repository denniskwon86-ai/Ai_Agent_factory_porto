"""★★★ [G2 4.1c-D] 데이터셋 소유권 **승인·철회 API 종단.**

## 이 파일이 존재하는 이유

`4.1c-A~C` 로 소유권 결속의 통제는 전부 섰다. 그런데 **제품에서 그것을 부를 방법이
없었다** — 결속을 만들 수 있는 것은 시드와 마이그레이션뿐이었고, 격리된 데이터를
복구할 길도 없었다. 이 저장소에서 이미 지적받은 「통제는 있는데 부르는 경로가 없다」와
같은 상태다(Wave E 의 Dispatch 잔여 배선이 그랬다).

그래서 이 파일은 **핵심 층을 다시 시험하지 않는다.** 그것은
`tests/test_dataset_ownership_binding.py` 가 한다. 여기서 고정하는 것은 배선이다:

  ① 라우트가 실제로 결속을 만드는가(그리고 격리가 풀리는가)
  ② 권한·범위가 라우트 층에서 막히는가
  ③ 등록이 실패하면 **승인 사건이 취소되는가**(원장에 「승인」만 남지 않는가)
  ④ 응답이 권한 밖 자원의 존재·개수를 누설하지 않는가

## 주체를 세우는 방식

`app.dependency_overrides[current_principal]` 로 세운다 — 이 저장소의 라우트 시험
규약이다(`X-Factory-User` 헤더는 P0-1C 에서 닫았고, 헤더로 주체를 만드는 시험은
그 구멍을 되살린다).
"""
import sqlite3

import pytest


TENANT = "tenant_default"
SCOPE = "MNM_TEST_OWN"
OTHER_SCOPE = "MNM_OTHER"
DEPT = "hq"
KEY = "LOG-02"


# ── 세우기 ────────────────────────────────────────────────────────────────

@pytest.fixture
def env(tmp_path, monkeypatch):
    """격리 저장소 + 격리 원장 + **실제 조직도.**

    ⚠️ 조직도를 세우지 않으면 `resolve_scope()` 가 부트스트랩 예외로 미등록 사용자에게도
      전권을 준다(4.1c-B P0-1 에서 실측). 그 상태에서는 승인 권한 검사가 돌지 않는다."""
    from core.data_preparation import store as dp
    from core.decision_ledger import decision_ledger
    from core.org_directory import OrgDirectory
    import core.org_directory as orgmod

    store = dp.data_preparation_store
    monkeypatch.setattr(store, "db_path", str(tmp_path / "dp.db"), raising=False)
    monkeypatch.setattr(store, "_prepared_for", None, raising=False)
    monkeypatch.setattr(decision_ledger, "db_path", str(tmp_path / "ledger.db"),
                        raising=False)

    #: ⚠️ `api.deps` 는 **자기 모듈에 import 한 이름**을 쓴다(`capabilities_of` →
    #:   `org_directory.get_user`). `core.org_directory` 만 패치하면 그 이름은 옛 싱글턴을
    #:   가리키고, 사용자를 못 찾아 **권한이 조용히 좁아진다** — 403 이 나면서 이유는
    #:   「권한 없음」으로 보인다. 두 곳을 함께 패치한다.
    import api.deps as deps
    org = OrgDirectory(db_path=str(tmp_path / "org.db"))
    org.create_department(DEPT, "본사", scope_node_id=SCOPE)
    org.upsert_user("std@afs.invalid", "표준승인자", primary_dept_id=DEPT,
                    is_data_admin=True, actor="seed")
    org.upsert_user("plain@afs.invalid", "일반", primary_dept_id=DEPT, actor="seed")
    org.upsert_user("admin@afs.invalid", "관리자", primary_dept_id=DEPT,
                    is_admin=True, is_data_admin=True, actor="seed")
    #: ⚠️ 강제가 꺼져 있으면 `resolve_scope` 가 **전원 무제한**을 돌려준다 — 그 상태에서는
    #:   권한·범위 시험이 전부 통과하고 아무것도 지키지 못한다(실측된 함정이다).
    import core.scope_policy as sp
    monkeypatch.setattr(sp, "_read", lambda: {"org_enforce": True})
    monkeypatch.setattr(orgmod, "org_directory", org)
    monkeypatch.setattr(deps, "org_directory", org)
    return {"store": store, "org": org, "ledger": decision_ledger}


def _client(scope):
    """라우터만 태운 앱. **주체는 override 로** 세운다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api.routes.data_preparation_control as dpc
    from api.deps import Principal, current_principal

    app = FastAPI()
    app.include_router(dpc.router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=scope.user_id, scope=scope)
    return TestClient(app, raise_server_exceptions=False)


def _scope(env, user_id="std@afs.invalid"):
    """★★★ **실제 `resolve_scope()` 가 돌려주는 객체**를 쓴다.

    ⚠️⚠️ 처음에 `AccessScope(...)` 를 손으로 만들었다. 그것은 4.1c-B P1-1 에서 지적받은
      바로 그 패턴이다 — 내가 필드를 원하는 값으로 채우면 **판정기가 아니라 내가 답을
      정한다.** 게다가 손으로 만든 값은 실제와 어긋난다(권한 상수를 하나 빼먹어 403 이
      났고, 그때 원인은 「권한 없음」으로 보였다).
    ★ 그리고 이 방식이라야 `readable_scope_nodes` 가 **부서의 조직 노드**에서 나온다 —
      「볼 수 없는 범위」 시험이 실제 규칙으로 검사된다."""
    return env["org"].resolve_scope(user_id)


@pytest.fixture(autouse=True)
def _ctx(monkeypatch):
    """`viewing_context` 를 고정한다 — 문맥 해석은 G1-C3 판정기가 이미 시험한다.

    ⚠️ 여기서 그것을 다시 시험하지 않는다. 두 벌로 시험하면 판정기를 고칠 때 이 파일이
      먼저 빨개지고, 그러면 사람들은 판정기가 아니라 이 파일을 고친다."""
    import api.routes.data_preparation_control as dpc
    monkeypatch.setattr(dpc, "viewing_context",
                        lambda p: {"tenant_id": TENANT, "entity_mode": "REAL",
                                   "scope_node_id": SCOPE})


def _approve(c, **kw):
    body = {"dataset_contract_key": KEY, "scope_node_id": SCOPE,
            "owner_dept_id": DEPT, "evidence_ref": "FND-01/v1#api"}
    body.update(kw)
    return c.post("/api/v1/data-preparation/ownership/approve", json=body)


def _data(res):
    """★ 봉투를 벗긴다. `{status, data}` 를 그대로 읽으면 `None` 이 나오고, 그 `None` 로
    「막혔다」고 결론 내린 적이 이 저장소에서 네 번 있었다."""
    assert res.status_code == 200, f"{res.status_code} {res.text[:300]}"
    body = res.json()
    assert body.get("status") == "success", body
    return body["data"]


# ── ① 실제로 만들어진다 ───────────────────────────────────────────────────

def test_승인_요청이_실제로_결속을_만든다(env):
    """★★★ **이 파일의 존재 이유.** 종전에는 이 요청 자체가 없었다."""
    c = _client(_scope(env))
    row = _data(_approve(c))
    assert row["owner_dept_id"] == DEPT
    assert row["binding_id"] and row["approval_event_id"]

    #: ★ 저장소에서 실제로 해석되는가 — 응답만 보고 끝내지 않는다.
    from core.data_preparation import ownership_binding as ob
    with env["store"].transaction() as conn:
        got = ob.resolve(conn, tenant_id=TENANT, entity_mode="REAL",
                         dataset_contract_key=KEY, scope_node_id=SCOPE)
    assert got and got["binding_id"] == row["binding_id"]


def test_승인은_원장에_사건을_남긴다(env):
    """⚠️ 결속만 생기고 원장이 비면, 「누가 언제 무슨 근거로 정했나」에 답할 수 없다."""
    c = _client(_scope(env))
    row = _data(_approve(c))
    from core.data_preparation import ownership_binding as ob
    events = env["ledger"].list_events(event_type=ob.EVENT_APPROVED)
    assert [e["event_id"] for e in events] == [row["approval_event_id"]]
    assert events[0]["actor_id"] == "std@afs.invalid"
    #: ★ 원장 조회 API 는 이 칸을 **부서 id** 로 읽는다(4.1c-B P1).
    assert events[0]["enterprise_scope_id"] == DEPT


def test_철회_요청이_실제로_내린다(env):
    c = _client(_scope(env))
    row = _data(_approve(c))
    res = c.post(f"/api/v1/data-preparation/ownership/{row['binding_id']}/revoke",
                 json={"reason": "근거 미비"})
    assert _data(res)["status"] == "REVOKED"

    from core.data_preparation import ownership_binding as ob
    with env["store"].transaction() as conn:
        assert ob.resolve(conn, tenant_id=TENANT, entity_mode="REAL",
                          dataset_contract_key=KEY, scope_node_id=SCOPE) is None


def test_이미_철회된_결속은_409(env):
    """⚠️ 404 로 답하면 「그런 결속이 없다」가 되어, 방금 철회한 사람이 혼란스러워진다.
    지금 상태에서 할 수 없는 일은 409 다(이 파일 머리말의 경계표)."""
    c = _client(_scope(env))
    row = _data(_approve(c))
    path = f"/api/v1/data-preparation/ownership/{row['binding_id']}/revoke"
    assert c.post(path, json={"reason": "1차"}).status_code == 200
    assert c.post(path, json={"reason": "2차"}).status_code == 409


# ── ② 권한과 범위 ─────────────────────────────────────────────────────────

def test_승인_권한이_없으면_403_이고_원장에_아무것도_남지_않는다(env):
    """★★★ 거부만으로 부족하다 — **원장에 사건이 남지 않았는지**까지 본다.
    거부됐는데 이력에 승인이 남으면 그것이 더 나쁘다."""
    c = _client(_scope(env, "plain@afs.invalid"))
    assert _approve(c).status_code == 403
    from core.data_preparation import ownership_binding as ob
    assert env["ledger"].list_events(event_type=ob.EVENT_APPROVED) == []


def test_강제가_꺼진_환경에서도_미등록_사용자는_거부된다(env, monkeypatch):
    """★★★ 라우트가 보는 `can_manage_standard` 는 **확정 결과**다. 그리고 조직 권한 강제가
    꺼져 있으면 `resolve_scope()` 는 **등록 여부와 무관하게 전권**을 준다 — 즉 라우트 층
    검사만으로는 스위치 하나로 통제가 사라진다.

    ★ 그래서 핵심 층(`approve()`)이 **사용자 정본**을 다시 본다(4.1c-B P0-1 ③). 이 시험은
      그 이중 방어가 실제로 작동하는지를 본다.
    ⚠️ 강제를 켠 상태로는 이 경로를 시험할 수 없다 — 라우트가 먼저 403 을 주고, 핵심 층은
      호출되지 않는다(처음 쓴 판이 그랬다. 초록이었지만 아무것도 시험하지 않았다)."""
    import core.scope_policy as sp
    monkeypatch.setattr(sp, "_read", lambda: {"org_enforce": False})
    env["org"]._scope_cache.clear()
    scope = env["org"].resolve_scope("아무도아님@afs.invalid")
    #: 대조군이 진짜인지 먼저 증명한다 — 라우트를 통과할 권한이 실제로 있어야 한다.
    assert scope.unrestricted and scope.can_manage_standard,         "강제가 꺼졌는데 전권이 아니다 — 이 시험은 라우트에서 막혀 핵심 층에 닿지 않는다"

    c = _client(scope)
    res = _approve(c)
    assert res.status_code == 400, f"{res.status_code} {res.text[:200]}"
    assert "조직 정본에 없는 사용자" in res.text
    #: ★ 그리고 원장에 아무것도 남지 않았다.
    from core.data_preparation import ownership_binding as ob
    assert env["ledger"].list_events(event_type=ob.EVENT_APPROVED) == []


def test_볼_수_없는_범위에는_세울_수_없고_404_다(env):
    """★★★ 403 은 「그 조직이 존재한다」를 알려 준다. 없는 범위와 못 보는 범위를
    **같은 404** 로 답한다."""
    c = _client(_scope(env))
    assert _approve(c, scope_node_id=OTHER_SCOPE).status_code == 404
    assert _approve(c, scope_node_id="").status_code == 404


def test_남의_범위_결속은_철회할_수_없고_404_다(env):
    """⚠️ 존재를 알려 주지 않는다 — 403 과 404 의 차이가 곧 조직도 유출이다."""
    from core.data_preparation import ownership_binding as ob
    admin = _client(_scope(env, "admin@afs.invalid"))
    row = _data(_approve(admin, scope_node_id=OTHER_SCOPE))

    c = _client(_scope(env))
    res = c.post(f"/api/v1/data-preparation/ownership/{row['binding_id']}/revoke",
                 json={"reason": "남의 것"})
    assert res.status_code == 404
    #: ★ 그리고 실제로 살아 있어야 한다 — 404 를 주면서 내려 버리면 최악이다.
    with env["store"].transaction() as conn:
        assert ob.resolve(conn, tenant_id=TENANT, entity_mode="REAL",
                          dataset_contract_key=KEY,
                          scope_node_id=OTHER_SCOPE) is not None


def test_철회에도_사유가_필요하다(env):
    c = _client(_scope(env))
    row = _data(_approve(c))
    res = c.post(f"/api/v1/data-preparation/ownership/{row['binding_id']}/revoke",
                 json={"reason": ""})
    assert res.status_code == 400 and "사유" in res.text


# ── ③ 등록 실패 시 승인 사건을 취소한다 ──────────────────────────────────

def test_등록이_실패하면_승인_사건이_취소된다(env):
    """★★★ [4.1c-D 핵심] 승인은 **원장**, 결속은 **정본 표**다. 다른 저장소라 한
    트랜잭션으로 묶을 수 없다 — 등록이 실패하면 승인 사건만 남는다.

    ⚠️ 권한이 새지는 않는다(결속이 없으니 아무 권한도 없다). 위험한 것은 **이력의
      오독**이다: 원장만 읽는 감사자에게는 「승인됨」으로 보인다.
    ★ 그래서 라우트가 `abandon()` 으로 그 사건을 죽인다 — 철회와 같은 사건 유형이므로
      `resolve()` 의 자식 검사가 자동으로 그 승인을 무효로 만든다."""
    from core.data_preparation import ownership_binding as ob
    real = ob.declare

    def _boom(*a, **kw):
        raise ob.OwnershipIntegrityError("등록 실패(주입)")

    ob.declare = _boom
    try:
        c = _client(_scope(env))
        assert _approve(c).status_code == 409
    finally:
        ob.declare = real

    #: 승인 사건은 남아 있지만 **철회 자식이 붙어 죽어 있다.**
    events = env["ledger"].list_events(event_type=ob.EVENT_APPROVED)
    assert len(events) == 1
    revoked, failed = ob._revocation_children(events[0]["event_id"])
    assert revoked and not failed, "등록 실패 뒤 승인 사건이 살아 있다"

    #: ★★ 그래서 **미물질화 보고에 「승인 대기」로 잡히지 않는다.**
    with env["store"].transaction() as conn:
        assert ob.dangling_approvals(conn, tenant_id=TENANT, entity_mode="REAL", unrestricted=True) == []


def test_취소까지_실패하면_미물질화_보고에_남는다(env):
    """⚠️ 취소도 실패할 수 있다. 그때 조용히 성공으로 돌리지 않고, 그 건이 **보고에
    남아야** 한다 — 그러지 않으면 원장의 승인 수와 실제 결속 수가 갈라진 채 아무도
    그 차이를 세지 않는다.

    ⚠️ `monkeypatch` 를 쓰지 않는다. `undo()` 가 **픽스처의 격리까지 되돌려** 원장이 실
      경로로 돌아가고, 그러면 보고가 0건으로 보인다(처음 쓴 판이 그랬다 — 통제가 없는
      것처럼 보였지만 실은 시험이 다른 DB 를 보고 있었다)."""
    from core.data_preparation import ownership_binding as ob
    real_declare, real_abandon = ob.declare, ob.abandon

    def _declare_boom(*a, **kw):
        raise ob.OwnershipIntegrityError("등록 실패(주입)")

    def _abandon_boom(*a, **kw):
        raise ob.OwnershipUnavailable("취소 실패(주입)")

    ob.declare, ob.abandon = _declare_boom, _abandon_boom
    try:
        c = _client(_scope(env))
        res = _approve(c)
        #: ★★★ [4.1c-E P1-4] **409 가 아니다.** 등록 실패의 예외를 그대로 돌려주면
        #:   「입력을 고쳐 다시 하라」로 읽힌다. 실제 상태는 원장 보상이 실패해 살아 있는
        #:   승인이 남은 것이고, 그것은 사람이 정리해야 하는 상태(503)다.
        assert res.status_code == 503, f"{res.status_code} {res.text[:200]}"
        assert res.json()["detail"]["error"] == "repair_required", res.text[:300]
        assert res.json()["detail"]["approval_event_id"]
    finally:
        ob.declare, ob.abandon = real_declare, real_abandon

    with env["store"].transaction() as conn:
        dangling = ob.dangling_approvals(conn, tenant_id=TENANT, entity_mode="REAL", unrestricted=True)
    assert len(dangling) == 1, "취소 실패한 승인이 보고에 없다"


# ── ④ 격리 복구 — 이 경로의 실제 용도 ────────────────────────────────────

_LEGACY_DDL = """
CREATE TABLE IF NOT EXISTS dataset_ownership_bindings (
    binding_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, entity_mode TEXT NOT NULL,
    dataset_contract_key TEXT NOT NULL, scope_node_id TEXT NOT NULL,
    owner_dept_id TEXT NOT NULL, effective_from TEXT NOT NULL,
    effective_to TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'ACTIVE',
    approved_by TEXT NOT NULL, approved_at TEXT NOT NULL,
    evidence_ref TEXT NOT NULL DEFAULT '', revoked_by TEXT NOT NULL DEFAULT '',
    revoked_at TEXT NOT NULL DEFAULT '', revoked_reason TEXT NOT NULL DEFAULT '',
    fingerprint TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""


def test_격리된_데이터를_이_경로로_복구할_수_있다(env, tmp_path, monkeypatch):
    """★★★ **이 API 가 없던 동안 격리는 되돌릴 수 없는 상태였다.**

    구버전 결속은 승인 근거가 없어 격리되고, 그 데이터셋은 소유자 없음(UNBOUND)이 된다.
    풀리는 조건은 **재승인**뿐이다 — 그런데 재승인을 부를 경로가 없었다. 즉 마이그레이션이
    데이터를 잠그고 열쇠를 만들지 않은 셈이었다."""
    from core.data_preparation import ownership_binding as ob
    store = env["store"]
    #: 구버전 형식 DB 를 제품 경로에 둔다.
    path = str(tmp_path / "legacy_prod.db")
    raw = sqlite3.connect(path)
    raw.executescript(_LEGACY_DDL)
    raw.execute(
        "INSERT INTO dataset_ownership_bindings (binding_id, tenant_id, entity_mode,"
        "dataset_contract_key, scope_node_id, owner_dept_id, effective_from, status,"
        "approved_by, approved_at, fingerprint, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("own_old", TENANT, "REAL", KEY, SCOPE, "구버전선언부서",
         "2026-01-01T00:00:00+00:00", "ACTIVE", "누군가@afs.invalid",
         "2026-01-01T00:00:00+00:00", "fp_old", "2026-01-01T00:00:00+00:00",
         "2026-01-01T00:00:00+00:00"))
    raw.commit(); raw.close()
    monkeypatch.setattr(store, "db_path", path, raising=False)
    monkeypatch.setattr(store, "_prepared_for", None, raising=False)

    #: ① 기동 = 격리된다. 그 데이터는 소유자가 없다.
    with store.transaction() as conn:
        assert ob.quarantine_state(conn)["unresolved"] == 1
        assert ob.resolve(conn, tenant_id=TENANT, entity_mode="REAL",
                          dataset_contract_key=KEY, scope_node_id=SCOPE) is None

    #: ② 화면·API 로 현황이 보인다 — 「왜 안 보이나」에 답할 수 있어야 한다.
    c = _client(_scope(env))
    seen = _data(c.get("/api/v1/data-preparation/ownership"))
    assert seen["quarantine"]["unresolved"] == 1
    assert seen["quarantine"]["by_contract_key"] == {KEY: 1}

    #: ③ 재승인 — 이 경로가 열쇠다.
    row = _data(_approve(c))
    with store.transaction() as conn:
        assert ob.quarantine_state(conn)["unresolved"] == 0, "재승인했는데 격리가 남았다"
        got = ob.resolve(conn, tenant_id=TENANT, entity_mode="REAL",
                         dataset_contract_key=KEY, scope_node_id=SCOPE)
    assert got["binding_id"] == row["binding_id"]
    assert got["owner_dept_id"] == DEPT, "구버전이 주장한 부서가 살아났다"


# ── ⑤ 목록은 권한 밖을 누설하지 않는다 ───────────────────────────────────

def test_목록은_남의_범위를_세지도_보이지도_않는다(env):
    """★★★ 「권한 밖 3건」을 세어 주면 그 3이 곧 「그 조직에 3건이 있다」가 된다.

    ⚠️ 목록 본문만 거르고 **개수를 그대로 두는** 실수가 흔하다 — 그래서 개수까지 본다."""
    admin = _client(_scope(env, "admin@afs.invalid"))
    _data(_approve(admin, scope_node_id=OTHER_SCOPE, dataset_contract_key="SLS-01"))
    mine = _data(_approve(admin, scope_node_id=SCOPE))

    c = _client(_scope(env))
    seen = _data(c.get("/api/v1/data-preparation/ownership"))
    ids = [b["binding_id"] for b in seen["bindings"]]
    assert ids == [mine["binding_id"]], ids
    blob = str(seen)
    assert OTHER_SCOPE not in blob and "SLS-01" not in blob, "남의 범위가 응답에 새어 나갔다"


def test_목록_조회가_원장_장애를_0건으로_답하지_않는다(env, monkeypatch):
    """⚠️ 「미물질화 0건」은 아무 문제 없다는 뜻이다. 못 셌으면 못 셌다고 말해야 한다."""
    from core.decision_ledger import decision_ledger
    c = _client(_scope(env))
    _data(_approve(c))

    def _boom(*a, **kw):
        raise RuntimeError("원장 장애")

    monkeypatch.setattr(decision_ledger, "has_invalidating_child", _boom, raising=False)
    #: 미물질화 계산이 철회 조회에 의존하므로 여기서 503 이 나야 한다.
    monkeypatch.setattr(decision_ledger, "list_events",
                        lambda **kw: [{"event_id": "evt_x", "subject_id": "fp",
                                       "actor_id": "a", "created_at": ""}],
                        raising=False)
    assert c.get("/api/v1/data-preparation/ownership").status_code == 503


def test_격리_조회는_표준_승인_권한자_전용이다(env):
    """⚠️ 격리 목록에는 **어느 부서가 소유자라고 주장돼 있었는지**가 들어 있다 —
    조직 구조를 읽는 것과 같다."""
    c = _client(_scope(env, "plain@afs.invalid"))
    assert c.get("/api/v1/data-preparation/ownership/quarantine").status_code == 403
    ok = _client(_scope(env))
    assert ok.get("/api/v1/data-preparation/ownership/quarantine").status_code == 200


# ── ⑥ 제품 앱에 실제로 붙었는가 ──────────────────────────────────────────

def test_제품_앱에_소유권_경로가_붙어_있다():
    """★★★ **라우터 미등록은 조용한 실패다.**

    이 파일의 다른 시험은 라우터를 직접 태운다(`app.include_router`). 그러면 라우트가
    작동하는지는 알 수 있지만, **제품 앱(`main.app`)에 그것이 포함됐는지는 모른다.**
    이 저장소에서 이미 「통제는 있는데 부르는 경로가 없다」를 두 번 만났다 — 그때마다
    시험은 초록이었다.

    ⚠️ 404 를 받은 사용자는 「기능이 없다」고 결론 내리고 다시 묻지 않는다."""
    import main
    have = {(m, r.path) for r in main.app.routes
            for m in (getattr(r, "methods", None) or ())}
    for method, path in (
            ("POST", "/api/v1/data-preparation/ownership/approve"),
            ("POST", "/api/v1/data-preparation/ownership/{binding_id}/revoke"),
            ("GET", "/api/v1/data-preparation/ownership"),
            ("GET", "/api/v1/data-preparation/ownership/quarantine")):
        assert (method, path) in have, f"{method} {path} 가 제품 앱에 없다"


# ── ⑦ [4.1c-E] 테넌트 누설 · 멱등 · 보상 · 재조정 ────────────────────────

def test_다른_테넌트의_미물질화_승인은_보이지_않는다(env):
    """★★★ [4.1c-E P0-1] **실측된 누설의 종단 회귀.**

    앞 판의 `dangling_approvals()` 는 `tenant_id` 도 받지 않고 원장 전체를 훑었다. 그래서
    한 응답 안에서 **결속·격리는 걸러지고 미물질화 승인만 안 걸러졌다** — 다른 회사의
    승인 ID·행위자·대상 지문과 건수가 그대로 실려 나갔다.

    ⚠️ 테넌트 경계는 어떤 권한으로도 넘을 수 없다. 부서 범위와 달리 「넓은 권한자」라는
      예외가 없다 — 다른 회사의 데이터다."""
    from core.data_preparation import ownership_binding as ob
    #: 다른 회사의 미물질화 승인(결속은 만들지 않는다).
    ob.approve(tenant_id="tenant_남의회사", entity_mode="REAL",
               dataset_contract_key="SLS-01", scope_node_id="NODE_남",
               owner_dept_id=DEPT, actor_id="std@afs.invalid",
               evidence_ref="남의회사근거")
    mine = ob.approve(tenant_id=TENANT, entity_mode="REAL",
                      dataset_contract_key="MDM-01", scope_node_id=SCOPE,
                      owner_dept_id=DEPT, actor_id="std@afs.invalid",
                      evidence_ref="우리근거")

    for who in ("std@afs.invalid", "admin@afs.invalid"):   # 관리자도 넘지 못한다
        c = _client(_scope(env, who))
        seen = _data(c.get("/api/v1/data-preparation/ownership"))
        ids = [d["approval_event_id"] for d in seen["dangling_approvals"]]
        assert ids == [mine["approval_event_id"]], f"{who}: {ids}"
        blob = str(seen)
        for leak in ("tenant_남의회사", "NODE_남", "SLS-01", "남의회사근거"):
            assert leak not in blob, f"{who} 응답에 남의 회사 정보가 새어 나갔다: {leak}"


def test_데이터_관리자는_전_부서의_소유권을_본다(env):
    """★★ **조직도가 그렇게 정했다는 사실을 고정한다** — 누설이 아니라 설계다.

    실측(2026-08-21): `is_data_admin` 사용자의 `readable_dept_ids` 는 **전 부서**다
    (`['dept_b', 'hq']`). 이 라우트는 `admin.data_access` 를 요구하므로, 들어오는 사람은
    거의 항상 전 부서를 읽을 수 있다 — 즉 라우트 안의 **부서 필터는 사실상 통과**한다.

    ⚠️ 그래서 「부서 축이 막힌다」고 말하지 않는다. 막히는 것은 **테넌트 축**이다.
    ★ 이 시험은 조직도 규칙이 좁아지는 날 그 사실을 알려 주는 자리다. 지금 값을 못 박아
      두면, 나중에 좁혀졌을 때 이 라우트가 조용히 빈 목록을 주는 것을 아무도 모른다."""
    org = env["org"]
    org.create_department("dept_b", "B부서", scope_node_id=OTHER_SCOPE)
    org._invalidate()
    scope = org.resolve_scope("std@afs.invalid")
    assert "dept_b" in scope.readable_dept_ids, \
        ("데이터 관리자가 더 이상 전 부서를 읽지 않는다 — 소유권 목록·미물질화 보고가 "
         "조용히 좁아졌을 수 있다. 라우트의 부서 필터를 다시 확인할 것")


def test_목록_조회의_원장_목록_장애도_503_이다(env, monkeypatch):
    """⚠️ [4.1c-E P0-2] 앞 판의 회귀는 `has_invalidating_child` 장애만 봤다.
    **최초 목록 조회**가 실패하는 경로가 따로 있고, 그것이 「0건」으로 접혔다."""
    from core.decision_ledger import DecisionLedgerError, decision_ledger
    c = _client(_scope(env))
    _data(_approve(c))

    def _boom(**kw):
        raise DecisionLedgerError("목록 판독 장애(주입)")

    monkeypatch.setattr(decision_ledger, "list_events_strict", _boom, raising=False)
    assert c.get("/api/v1/data-preparation/ownership").status_code == 503


def test_같은_승인을_두_번_해도_사건이_하나다(env):
    """★★★ [4.1c-E P1-3] **네트워크 재시도만으로 감사 이력이 오염되면 안 된다.**

    앞 판은 두 번째 요청이 새 승인 사건을 만들었고, `declare()` 는 같은 지문의 결속을
    멱등으로 돌려줬다 — 그래서 결속은 하나인데 **어느 결속에도 연결되지 않은 승인 사건**이
    미물질화 보고에 남았다."""
    from core.data_preparation import ownership_binding as ob
    c = _client(_scope(env))
    first = _data(_approve(c))
    res2 = _approve(c)
    second = _data(res2)
    assert second["binding_id"] == first["binding_id"], "두 번째 요청이 다른 결속을 만들었다"
    assert res2.json().get("idempotent") is True, res2.text[:200]

    #: ★ 살아 있는 승인 사건은 **하나**다.
    events = env["ledger"].list_events(event_type=ob.EVENT_APPROVED, limit=100)
    alive = [e for e in events if not ob._revocation_children(e["event_id"])[0]]
    assert len(alive) == 1, f"살아 있는 승인 사건 {len(alive)}건"
    #: ★ 그리고 미물질화 0건.
    seen = _data(c.get("/api/v1/data-preparation/ownership"))
    assert seen["dangling_approvals"] == []
    assert len(seen["bindings"]) == 1


def test_부서를_바꾸려면_먼저_철회해야_한다(env):
    """★★ 멱등은 **같은 승인**에만 적용된다. 부서나 근거가 다르면 그것은 개정이고,
    조용히 덮으면 누가 언제 무엇을 바꿨는지 사라진다."""
    env["org"].create_department("dept_other", "다른부서", scope_node_id=SCOPE)
    c = _client(_scope(env))
    _data(_approve(c))
    res = _approve(c, owner_dept_id="dept_other")
    assert res.status_code == 409, f"{res.status_code} {res.text[:200]}"
    assert "겹치는" in res.text or "철회" in res.text


def test_철회_원장은_남았는데_표가_안_바뀌면_드러나고_고칠_수_있다(env):
    """★★★ [4.1c-E P1-5] 철회는 두 단계다 — 원장 사건, 그리고 정본 표 갱신. 두 번째가
    실패하면 **원장에는 철회, 표에는 ACTIVE** 가 남는다.

    ⚠️ 권한 판정은 안전하다(fail-closed). 위험한 것은 **두 화면이 다른 말을 하는 것**이다:
      목록에는 살아 있고 판정은 막는다. 그러면 운영자는 「왜 안 보이나」를 영원히 못 찾는다."""
    from core.data_preparation import ownership_binding as ob
    c = _client(_scope(env))
    row = _data(_approve(c))
    bid = row["binding_id"]

    #: 원장에는 철회를 남기고 **표 갱신만** 되돌린다(두 번째 단계 실패 재현).
    with env["store"].transaction() as conn:
        ob.revoke(conn, bid, "std@afs.invalid", "철회")
        conn.execute("UPDATE dataset_ownership_bindings SET status='ACTIVE',"
                     " revoked_at='', revoked_reason='' WHERE binding_id=?", (bid,))

    #: ① 목록이 불일치를 **드러낸다.**
    seen = _data(c.get("/api/v1/data-preparation/ownership"))
    assert [m["binding_id"] for m in seen["ledger_mismatches"]] == [bid], seen
    #: ② 판정은 이미 막고 있다(fail-closed) — 두 화면이 다른 말을 한다는 것이 문제였다.
    with env["store"].transaction() as conn:
        assert ob.resolve(conn, tenant_id=TENANT, entity_mode="REAL",
                          dataset_contract_key=KEY, scope_node_id=SCOPE) is None
    #: ③ 재조정으로 표를 원장에 맞춘다.
    fixed = _data(c.post(f"/api/v1/data-preparation/ownership/{bid}/reconcile"))
    assert fixed["applied"] == "ACTIVE->REVOKED"
    seen2 = _data(c.get("/api/v1/data-preparation/ownership"))
    assert seen2["ledger_mismatches"] == []
    #: ④ 어긋나지 않은 것을 재조정하려 하면 409 — 고칠 것이 없는데 고쳤다고 말하지 않는다.
    assert c.post(f"/api/v1/data-preparation/ownership/{bid}/reconcile").status_code == 409


def test_목록과_격리_조회의_권한_정책이_같다(env):
    """★★ [4.1c-E P1-7] 두 응답에 같은 종류의 정보(어느 부서가 소유자로 주장됐는가)가
    들어 있다. 정책이 갈리면 **느슨한 쪽이 우회 경로**가 된다."""
    weak = _client(_scope(env, "plain@afs.invalid"))
    for path in ("/api/v1/data-preparation/ownership",
                 "/api/v1/data-preparation/ownership/quarantine"):
        assert weak.get(path).status_code == 403, path
    ok = _client(_scope(env))
    for path in ("/api/v1/data-preparation/ownership",
                 "/api/v1/data-preparation/ownership/quarantine"):
        assert ok.get(path).status_code == 200, path


def test_재조정도_남의_범위는_404_다(env):
    from core.data_preparation import ownership_binding as ob
    admin = _client(_scope(env, "admin@afs.invalid"))
    row = _data(_approve(admin, scope_node_id=OTHER_SCOPE))
    c = _client(_scope(env))
    res = c.post(f"/api/v1/data-preparation/ownership/{row['binding_id']}/reconcile")
    assert res.status_code == 404


def test_동시_재시도에도_결속과_승인이_각각_하나다(env):
    """★★★ [4.1c-E P1-3] **멱등 검사와 등록 사이에 상대가 끼어드는 경우.**

    두 요청이 동시에 「아직 결속이 없다」를 읽으면 둘 다 승인·등록으로 간다. 그때 DB 가
    하나를 막고(기간 중첩 트리거), 막힌 쪽은 **자기 승인 사건을 취소**해야 한다 —
    그러지 않으면 재시도 한 번에 살아 있는 승인이 하나 늘어난다.

    ⚠️ 스레드로 진짜 동시성을 만들지 않는다. SQLite·TestClient 조합에서 그것은
      «막혔다» 와 «경합에 졌다» 를 구분할 수 없게 만들고, 그러면 이 시험은 무엇을
      지키는지 말할 수 없게 된다. 대신 **멱등 검사가 이미 지난 상태**를 직접 만든다 —
      경합에서 지는 쪽이 보는 상태가 정확히 그것이다."""
    from core.data_preparation import ownership_binding as ob
    c = _client(_scope(env))
    first = _data(_approve(c))

    #: 멱등 검사를 «아직 없다» 로 만든다 = 낡은 스냅숏을 읽은 상태.
    real_resolve = ob.resolve
    ob.resolve = lambda *a, **kw: None
    try:
        res = _approve(c)
    finally:
        ob.resolve = real_resolve

    #: 등록은 기간 중첩으로 막혀야 한다(409) — 두 결속이 생기면 안 된다.
    assert res.status_code == 409, f"{res.status_code} {res.text[:200]}"

    with env["store"].transaction() as conn:
        alive = [r for r in ob.list_bindings(conn, status=ob.ACTIVE)]
    assert len(alive) == 1 and alive[0]["binding_id"] == first["binding_id"]

    #: ★★ 그리고 **살아 있는 승인 사건도 하나**다 — 경합에 진 쪽이 자기 사건을 취소했다.
    events = env["ledger"].list_events(event_type=ob.EVENT_APPROVED, limit=100)
    alive_events = [e for e in events
                    if not ob._revocation_children(e["event_id"])[0]]
    assert len(alive_events) == 1, f"살아 있는 승인 {len(alive_events)}건 — 재시도가 오염시켰다"
    seen = _data(c.get("/api/v1/data-preparation/ownership"))
    assert seen["dangling_approvals"] == []


def test_어긋나지_않은_살아_있는_결속은_재조정으로_죽지_않는다(env):
    """★★★ [변이 시험에서 발견] 앞서 쓴 재조정 회귀는 **이미 철회된** 결속에 두 번째
    재조정을 시도했다. 그 경로는 `status != ACTIVE` 에서 먼저 걸리므로, **원장 확인을
    통째로 지워도** 잡히지 않았다(M55 실패 0건).

    ⚠️ 판별력은 「살아 있고 어긋나지도 않은 결속」에서 생긴다. 원장 확인이 없으면 그것을
      재조정하는 순간 **정상 결속이 REVOKED 로 죽는다** — 재조정이 복구 도구가 아니라
      파괴 도구가 된다."""
    from core.data_preparation import ownership_binding as ob
    c = _client(_scope(env))
    row = _data(_approve(c))
    bid = row["binding_id"]

    res = c.post(f"/api/v1/data-preparation/ownership/{bid}/reconcile")
    assert res.status_code == 409, f"{res.status_code} {res.text[:200]}"
    #: ★★ 그리고 **실제로 살아 있어야** 한다 — 409 를 주면서 표를 고쳤으면 최악이다.
    with env["store"].transaction() as conn:
        got = ob.resolve(conn, tenant_id=TENANT, entity_mode="REAL",
                         dataset_contract_key=KEY, scope_node_id=SCOPE)
    assert got and got["binding_id"] == bid, "어긋나지 않은 결속이 재조정으로 죽었다"
