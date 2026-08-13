"""★★★ [G1-B P0] **살아 있는 라우트에서 이중 판정 어긋남 0 확인.**

`test_app_policy_equivalence.py` 는 **판정기 단위**로 「PDP ⊆ 기존」을 증명했다.
이 파일은 그것이 **실제 요청 경로에서도** 성립하는지 본다. 둘은 다른 사실이다 —

> 「테스트가 실제 배선을 타지 않으면 그 초록은 거짓이다.」
> (`emit_to` 테넌트 격리를 «완료» 로 보고했는데 실서비스에서 작동하지 않았던 사고)

## 무엇을 확인하는가

1. 라우트가 **기존 판정으로 강제**한다(동작이 바뀌지 않았다).
2. 같은 요청에서 PDP 가 함께 돌고, `looser` 가 **0** 이다.
3. 관측 자체가 **요청을 죽이지 않는다**(PDP 가 터져도 200/403 이 그대로 나온다).

⚠️ `stricter` 는 0 이 아니어도 된다 — 오히려 0 이면 PDP 가 아무것도 강화하지 않는다는 뜻이라
  의심해야 한다. 그래서 아래에서 **강화가 실제로 관측되는지도** 확인한다.
"""
import json

import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """실제 앱 + 격리된 라이브러리·앱데이터. **운영 데이터를 건드리지 않는다.**"""
    import config
    import core.app_data_store as store_mod
    import core.library_paths as library_paths
    from core.org_directory import org_directory
    from core.policy_shadow import policy_shadow

    lib = tmp_path / "library"
    lib.mkdir()
    #: 문맥이 **온전한** 릴리스 하나. `release.json` 이 판정 입력의 서버 쪽 진실원본이다.
    rel = lib / "rel_ok"
    rel.mkdir()
    (rel / "release.json").write_text(json.dumps({
        "release_id": "rel_ok", "tenant_id": "tenant_default", "entity_mode": "REAL",
        "enterprise_scope_id": "node_hq", "owner_user_id": "", "owner_dept_id": "hq",
        "visibility": "dept"}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(library_paths, "release_dir",
                        lambda rid: str(lib / str(rid)), raising=False)
    #: ⚠️⚠️ **앱 데이터 저장소를 여기서 다시 만들지 않는다.** `conftest` 의 autouse 격리가
    #:   이미 `app_data_service._store.db_path` 를 tmp 로 돌려 놨다. 여기서 새
    #:   `AppDataService(AppDataStore())` 를 만들면 그 격리 **뒤에** 새 인스턴스가 생기고,
    #:   `AppDataStore.__init__(db_path=_DB_PATH)` 의 기본값은 **정의 시점에 묶여** 있어
    #:   운영 `data/app_data.db` 를 잡는다.
    #:   실제로 그렇게 해서 **운영 DB 에 데이터셋 1건을 만들었다**(2026-08-13, 백업 후 정리).
    #:   격리를 «보강» 하려다 격리를 깬 것이다 — 있는 격리를 먼저 확인한다.

    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)

    class _Scope:
        readable_dept_ids = frozenset({"hq"})
        writable_dept_ids = frozenset({"hq"})
        unrestricted = False
        can_manage_standard = False
        primary_dept_id = "hq"
        readable_scope_nodes = frozenset({"node_hq"})

        def can_read(self, d):
            return d in self.readable_dept_ids

        def can_write(self, d):
            return d in self.writable_dept_ids

    monkeypatch.setattr(org_directory, "resolve_scope", lambda uid="": _Scope())
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: False)
    monkeypatch.setattr(org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"} if uid else None)
    monkeypatch.setattr(org_directory, "get_ownership",
                        lambda kind, rid: {"dept_id": "hq", "owner_user_id": "",
                                           "visibility": "dept"})
    policy_shadow.reset()

    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


H = {"X-Factory-User": "u@x"}


def _stats():
    from core.policy_shadow import policy_shadow
    return policy_shadow.stats()


# ── ① 어긋남 0 ────────────────────────────────────────────────────────────

def test_읽기_경로에서_어긋남이_없다(client):
    r = client.get("/api/v1/appdata/datasets", params={"release_id": "rel_ok"}, headers=H)
    assert r.status_code == 200, r.text
    s = _stats()
    assert s["total"] >= 1, "관측이 아예 돌지 않았다 — 배선이 안 됐다"
    assert s["looser"] == 0, f"PDP 가 더 느슨한 칸이 있다: {s['recent']}"
    assert s["error"] == 0, f"관측이 실패했다: {s['recent']}"


def test_쓰기_경로에서도_어긋남이_없다(client):
    r = client.post("/api/v1/appdata/datasets", headers=H, json={
        "release_id": "rel_ok", "name": "purchase_request",
        "schema": {"fields": [{"name": "qty", "type": "number"}]}})
    assert r.status_code == 200, r.text
    s = _stats()
    assert s["looser"] == 0 and s["error"] == 0, s["recent"]


def test_거부되는_요청에서도_어긋남이_없다(client, monkeypatch):
    """★ 기존이 거부하는 칸에서 PDP 가 허용하면 그것이 전환 금지 사유다."""
    from core.org_directory import org_directory
    #: 남의 부서 자원으로 만든다 — 기존 판정이 거부한다.
    monkeypatch.setattr(org_directory, "get_ownership",
                        lambda kind, rid: {"dept_id": "sales", "owner_user_id": "",
                                           "visibility": "dept"})
    r = client.get("/api/v1/appdata/datasets", params={"release_id": "rel_ok"}, headers=H)
    assert r.status_code == 403, f"기존 판정이 막지 않았다: {r.status_code}"
    s = _stats()
    assert s["looser"] == 0, f"기존 거부 · PDP 허용: {s['recent']}"


# ── ② 강화가 실제로 관측되는가 (대조군) ───────────────────────────────────

def test_강화가_실제로_관측된다(client):
    """⚠️ `stricter` 가 0 이면 PDP 가 아무것도 강화하지 않는다는 뜻이고, 그러면 이 관측은
    「전환해도 안전하다」를 증명하지 못한다 — **아무것도 안 하는 판정기도 통과**하기 때문이다.

    문맥이 없는 릴리스(판독 실패)를 요청해 강화 칸을 만든다."""
    from core.policy_shadow import policy_shadow
    policy_shadow.reset()
    #: 존재하지 않는 릴리스 → `release.json` 판독 실패 → PDP 는 `INVALID` 로 거부.
    #: 기존 판정은 소유권 미러만 보므로 **허용**한다 → 강화 칸.
    r = client.get("/api/v1/appdata/datasets", params={"release_id": "rel_missing"}, headers=H)
    assert r.status_code == 200, "기존 판정이 막았다면 이 칸은 강화 대조가 되지 않는다"
    s = _stats()
    assert s["stricter"] >= 1, "강화가 하나도 관측되지 않았다 — 관측이 헛돌고 있다"
    assert s["looser"] == 0


# ── ③ 관측이 동작을 바꾸지 않는다 ─────────────────────────────────────────

def test_관측이_터져도_요청은_살아_있다(client, monkeypatch):
    """★★ 관측 장애가 기능 장애가 되면 안 된다. 다만 **세어서 드러낸다** — 조용한 유실 금지."""
    import api.routes.app_data_control as route_mod
    from core.policy_shadow import policy_shadow
    policy_shadow.reset()

    def _boom(*a, **k):
        raise RuntimeError("판정기 폭발")
    monkeypatch.setattr(route_mod, "_release_scope", _boom)

    r = client.get("/api/v1/appdata/datasets", params={"release_id": "rel_ok"}, headers=H)
    assert r.status_code == 200, "관측 실패가 요청을 죽였다"
    assert _stats()["error"] >= 1, "관측 실패를 세지 않았다 — 조용히 유실됐다"


def test_전환_판정은_한_값으로_읽는다(client):
    """★ 여러 숫자를 사람이 보고 해석하게 두면 판단이 갈린다."""
    client.get("/api/v1/appdata/datasets", params={"release_id": "rel_ok"}, headers=H)
    s = _stats()
    assert s["safe_to_switch"] is (s["looser"] == 0 and s["error"] == 0 and s["total"] > 0)


# ── ④ [G1-B05] 거부가 감사에 남는가 ───────────────────────────────────────

def test_거부는_감사에_남고_허용은_전건_기록하지_않는다(client, monkeypatch):
    """★★★ 앱 데이터 거부는 지금까지 **아무 데도 기록되지 않았다.**

    `api/deps._deny` 는 `HTTPException` 을 던질 뿐이다. 그래서 「누가 어느 앱 데이터에
    접근하려다 막혔는가」에 아무도 답할 수 없었다 — 거부된 시도가 침해 신호인데 조용했다.

    ⚠️ 동시에 **허용을 전건 기록하지 않는다.** 그러면 로그가 폭증해 정작 봐야 할 거부가
      묻힌다(`audit.py` 가 못박은 규약). 이 시험은 **둘을 함께** 확인한다 — 한쪽만 보면
      「전부 기록」도 「전부 미기록」도 통과한다."""
    from core.enterprise_context import audit
    from core.org_directory import org_directory
    seen = []
    monkeypatch.setattr(audit, "record", lambda **kw: seen.append(kw) or True)

    #: ① 허용되는 요청 — 감사에 남지 않아야 한다
    r = client.get("/api/v1/appdata/datasets", params={"release_id": "rel_ok"}, headers=H)
    assert r.status_code == 200, r.text
    assert not [k for k in seen if k.get("outcome") == "denied"], \
        "허용된 조회가 «거부» 로 기록됐다"
    allowed_records = len(seen)

    #: ② 거부되는 요청 — 반드시 남아야 한다
    monkeypatch.setattr(org_directory, "get_ownership",
                        lambda kind, rid: {"dept_id": "sales", "owner_user_id": "",
                                           "visibility": "dept"})
    r = client.get("/api/v1/appdata/datasets", params={"release_id": "rel_ok"}, headers=H)
    assert r.status_code == 403
    denied = [k for k in seen if k.get("outcome") == "denied"]
    assert denied, "거부가 감사에 남지 않았다 — 침해 시도가 조용하다"
    assert len(seen) > allowed_records, "거부 기록이 추가되지 않았다"

    rec = denied[-1]
    #: ⚠️ 은폐는 응답이지 기록이 아니다 — 실제 대상이 남아야 추적할 수 있다.
    assert rec["resource_id"] == "rel_ok", f"대상이 비었다: {rec}"
    assert rec["actor"] == "u@x"
    #: PDP 사유를 함께 남긴다 — 이행 기간에 두 판정의 차이를 되짚는 유일한 기록이다.
    assert "pdp=" in rec.get("detail", "")


def test_식별되지_않은_거부는_다른_이름으로_남는다(monkeypatch):
    """★ 「누구인지 모른다」와 「권한이 없다」는 **다른 사건**이다. 한 이름으로 뭉개면
    집계에서 침해 시도와 «로그인 안 한 사용자» 가 섞이고, 그러면 어느 쪽이 늘었는지
    아무도 답할 수 없다.

    ⚠️ 이 규칙은 **판정 지점에서** 확인한다. 라우트로 익명 요청을 만들려면 신원 추출
      경로를 여러 겹 비워야 하는데, 그렇게 만든 «익명» 은 운영의 익명과 다르다 —
      하니스를 맞추다 보면 시험이 자기 자신과 합의하게 된다(이 저장소의 반복 함정)."""
    from fastapi import HTTPException

    import api.routes.app_data_control as route_mod
    from api.deps import Principal
    from core.enterprise_context import audit

    seen = []
    monkeypatch.setattr(audit, "record", lambda **kw: seen.append(kw) or True)

    class _S:
        readable_dept_ids = frozenset()

    exc = HTTPException(status_code=403, detail="거부")
    route_mod._audit_denied(Principal(user_id="", scope=_S()), "read", "rel_1",
                            None, "GET /datasets", exc, None)
    route_mod._audit_denied(Principal(user_id="u@x", scope=_S()), "read", "rel_1",
                            None, "GET /datasets", exc, None)

    assert seen[0]["event"] == audit.ACCESS_DENIED_UNAUTHENTICATED,         f"익명 거부가 권한 거부와 같은 이름으로 남았다: {seen[0]['event']}"
    assert seen[1]["event"] == audit.ACCESS_DENIED_SCOPE_MISMATCH
    assert seen[0]["event"] != seen[1]["event"]


def test_감사_기록이_실패해도_거부는_그대로_막힌다(monkeypatch):
    """⚠️ 기록 실패가 거부를 성공으로 바꾸면 안 된다. 삼키되 요청은 막힌 채로 둔다."""
    from fastapi import HTTPException

    import api.routes.app_data_control as route_mod
    from api.deps import Principal
    from core.enterprise_context import audit

    def _boom(**kw):
        raise RuntimeError("감사 저장소 장애")
    monkeypatch.setattr(audit, "record", _boom)

    class _S:
        readable_dept_ids = frozenset()

    #: 예외가 새어 나오면 라우트가 500 이 되고, 그러면 «막혔다» 가 «고장» 으로 바뀐다.
    route_mod._audit_denied(Principal(user_id="u@x", scope=_S()), "read", "rel_1",
                            None, "GET /datasets", HTTPException(403, "거부"), None)
