"""★★★ 목록 API 의 노출 통제 — **필터를 부르지 않으면 통제가 없었다.**

## 왜 이 파일이 생겼나 (2026-07-31 실서버 실측)

권한 강제를 켠 뒤 실제로 확인한 것:

- `GET /api/v1/org/me` (익명) → "조직 권한 강제가 켜져 있어 목록이 비어 보입니다"
- `GET /api/v1/knowledge/packs` (익명) → **지식팩 4건을 그대로 돌려줬다**

두 응답이 서로 모순이다. 원인은 조직 범위 필터가 **호출자 선택**이었다는 것이다 —
`/reference/assets` 는 `scope_node_id` 를 주면 필터하고 안 주면 전부 준다고 문서화돼 있었고,
프론트는 주지 않았다. 즉 "미지정 = 비노출"(관문 A)의 반대인 **"미지정 = 전부 노출"** 이었다.

⚠️ 이 유형이 가장 위험하다:
  1. 오류가 없다 — 200 OK 로 잘 돌아간다.
  2. 화면은 통제가 걸린 것처럼 안내한다(배너가 있다).
  3. 새 목록 라우트가 생길 때마다 구멍이 하나씩 늘어난다(부르지 않으면 끝이므로).

그래서 판정을 `api.deps.visibility_block_reason` 한 곳에 두고, 이 파일이 **각 목록 라우트가
그 함수를 실제로 부르는지**를 지킨다. 쓰기 경로(삭제·업로드)는 권한이 아예 없었으므로 함께 막았다 —
읽기 구멍은 자료가 새는 것이고 쓰기 구멍은 자료가 사라지는 것이다.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import Principal, current_principal
from core.org_directory import AccessScope


def _app(monkeypatch, *, enforced=True, user_id="", user=None, scope_kw=None,
         routers=("knowledge", "reference")):
    """강제 여부·사용자 등록 상태를 지정한 앱. 실물 라우터를 그대로 물린다."""
    import core.org_directory as od
    monkeypatch.setattr(od, "_org_enforce_effective", lambda: enforced)
    monkeypatch.setattr(od.org_directory, "get_user", lambda uid: user)

    app = FastAPI()
    if "knowledge" in routers:
        import api.routes.knowledge_control as kc
        app.include_router(kc.router)
    if "reference" in routers:
        import api.routes.reference_control as rc
        app.include_router(rc.router)
    if "master" in routers:
        import api.routes.master_control as mc
        app.include_router(mc.router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=user_id,
        scope=AccessScope(user_id=user_id, **(scope_kw or {"unrestricted": False})))
    return app


def _packs(monkeypatch, n=4):
    import core.knowledge_base as kb
    monkeypatch.setattr(kb.knowledge_base, "list_packs",
                        lambda: [{"pack_id": f"p{i}"} for i in range(n)])


# ── 읽기: 자격 없는 요청자에게는 목록을 주지 않는다 ─────────────────────────
@pytest.mark.parametrize("uid,user,why", [
    ("", None, "익명"),
    ("ghost@ls", None, "미등록"),
    ("old@ls", {"user_id": "old@ls", "status": "retired"}, "폐지"),
    ("staff@ls", {"user_id": "staff@ls", "status": "active"}, "부서 미배정"),
])
def test_packs_are_hidden_from_unentitled_callers(monkeypatch, uid, user, why):
    """★★★ 네 가지 무자격 상태 모두 **0건**이어야 한다. 실측에서는 4건이 나왔다."""
    _packs(monkeypatch)
    c = TestClient(_app(monkeypatch, user_id=uid, user=user))
    r = c.get("/api/v1/knowledge/packs").json()
    assert r["data"] == [], f"{why} 상태에서 지식팩이 노출됐다"
    assert r.get("blocked_reason"), "빈 이유를 주지 않으면 화면이 '자료가 없다'고 말한다"


def test_packs_visible_to_admin(monkeypatch):
    """★ 무제한 권한자는 종전대로 전부 본다 — 통제가 업무를 막으면 통제가 꺼진다."""
    _packs(monkeypatch)
    c = TestClient(_app(monkeypatch, user_id="hikwon@ls",
                        user={"user_id": "hikwon@ls", "status": "active"},
                        scope_kw={"unrestricted": True}))
    r = c.get("/api/v1/knowledge/packs").json()
    assert len(r["data"]) == 4 and not r.get("blocked_reason")


def test_gate_is_transparent_when_enforcement_is_off(monkeypatch):
    """★★ 강제가 꺼져 있으면 아무것도 막지 않는다 — ECM 미도입 흐름의 하위호환 계약."""
    _packs(monkeypatch)
    c = TestClient(_app(monkeypatch, enforced=False, user_id="", user=None))
    r = c.get("/api/v1/knowledge/packs").json()
    assert len(r["data"]) == 4 and not r.get("blocked_reason")


def test_pack_detail_and_search_are_blocked_with_403(monkeypatch):
    """★★ 검색은 **본문 조각**을 돌려주므로 목록보다 무겁다. 404 가 아니라 403 으로 알린다 —
    없는 척하면 관리자도 원인을 찾을 수 없다."""
    _packs(monkeypatch)
    c = TestClient(_app(monkeypatch, user_id="ghost@ls", user=None))
    assert c.get("/api/v1/knowledge/packs/p0").status_code == 403
    assert c.post("/api/v1/knowledge/packs/p0/search",
                  json={"query": "원가"}).status_code == 403


def test_reference_assets_are_hidden_without_explicit_scope(monkeypatch):
    """★★★ `scope_node_id` 를 **주지 않아도** 통제된다. 종전 계약("주지 않으면 필터 안 함")이
    바로 구멍이었다 — 프론트는 실제로 주지 않았다."""
    import core.reference_registry as rr
    monkeypatch.setattr(rr, "load_registry",
                        lambda: {"assets": [{"asset_id": "a1"}, {"asset_id": "a2"}]})
    c = TestClient(_app(monkeypatch, user_id="", user=None))
    r = c.get("/api/v1/reference/assets").json()
    assert r["data"] == [] and r.get("blocked_reason")


# ── 쓰기: 애초에 권한이 없었다 ────────────────────────────────────────────
def test_write_paths_require_data_admin(monkeypatch):
    """★★★ [실측] `DELETE /packs/{id}` 에 권한이 없었다 — **익명이 전사 지식팩을 지울 수 있었다.**

    지우기·업로드·범위 부여는 모두 데이터 표준 관리 권한을 요구해야 한다."""
    _packs(monkeypatch)
    c = TestClient(_app(monkeypatch, user_id="ghost@ls", user=None))
    assert c.delete("/api/v1/knowledge/packs/p0").status_code == 403
    assert c.post("/api/v1/knowledge/packs", json={"pack_id": "new"}).status_code == 403
    assert c.post("/api/v1/knowledge/packs/p0/scope",
                  json={"owner_org_id": "LS_MNM"}).status_code == 403
    assert c.delete("/api/v1/knowledge/packs/p0/documents/x.pdf").status_code == 403


def test_admin_can_still_write(monkeypatch):
    """★ 관리자의 쓰기는 막히지 않는다 — 403 이 관리자에게도 걸리면 운영이 멈춘다."""
    import core.knowledge_base as kb
    monkeypatch.setattr(kb.knowledge_base, "remove_document", lambda pid, fn: True)
    c = TestClient(_app(monkeypatch, user_id="hikwon@ls",
                        user={"user_id": "hikwon@ls", "status": "active"},
                        scope_kw={"unrestricted": True}))
    assert c.delete("/api/v1/knowledge/packs/p0/documents/x.pdf").status_code == 200


# ── 기준정보: 주입 경로뿐 아니라 목록·상세·쓰기 경로도 같은 범위를 지킨다 ─────────
def _master_rows(monkeypatch):
    import api.routes.master_control as mc
    monkeypatch.setattr(mc, "viewer_visible_scopes",
                        lambda p: None if p.scope.unrestricted else frozenset({"ORG-A"}))
    monkeypatch.setattr(mc.master_data, "list_types", lambda: [
        {"type_id": "material", "name_ko": "자재"},
        {"type_id": "equipment", "name_ko": "설비"},
    ])
    monkeypatch.setattr(mc.master_data, "list_records", lambda *a, **k: [
        {"master_code": "MAT-A", "type_id": "material", "name": "A 자재"},
        {"master_code": "EQ-B", "type_id": "equipment", "name": "B 설비"},
    ])
    monkeypatch.setattr(mc.master_data, "get_record", lambda code: {
        "master_code": code, "type_id": "material", "name": code,
    })
    monkeypatch.setattr(mc.master_data, "bindings_for_scope",
                        lambda tenant, scope, mode, as_of: {"MAT-A": None}
                        if scope == "ORG-A" else {})


def test_master_lists_are_hidden_from_unentitled_callers(monkeypatch):
    """익명 요청이 200/0건이어도 **비어 있음**으로 오인하지 않게 차단 사유를 준다."""
    _master_rows(monkeypatch)
    c = TestClient(_app(monkeypatch, user_id="", user=None, routers=("master",)))
    for path in ("/api/v1/master/types", "/api/v1/master/records"):
        body = c.get(path).json()
        assert body["data"] == []
        assert body.get("blocked_reason")


def test_master_lists_follow_scope_bindings(monkeypatch):
    """A 조직 사용자는 A에 바인딩된 기준정보와 그 유형만 본다."""
    _master_rows(monkeypatch)
    c = TestClient(_app(
        monkeypatch, user_id="staff@ls", user={"user_id": "staff@ls", "status": "active"},
        scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"}),
                  "readable_scope_nodes": frozenset({"ORG-A"})}, routers=("master",)))
    records = c.get("/api/v1/master/records").json()
    types = c.get("/api/v1/master/types").json()
    assert [r["master_code"] for r in records["data"]] == ["MAT-A"]
    assert [t["type_id"] for t in types["data"]] == ["material"]
    assert records["hidden_count"] == 1 and types["hidden_count"] == 1


def test_master_other_scope_detail_is_404_and_audited(monkeypatch):
    """타 조직 상세는 존재를 숨기되 감사로그에는 실제 코드를 남긴다."""
    _master_rows(monkeypatch)
    from core.enterprise_context import audit
    seen = []
    monkeypatch.setattr(audit, "denied_scope", lambda *a, **k: seen.append((a, k)) or True)
    c = TestClient(_app(
        monkeypatch, user_id="staff@ls", user={"user_id": "staff@ls", "status": "active"},
        scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"}),
                  "readable_scope_nodes": frozenset({"ORG-A"})}, routers=("master",)))
    assert c.get("/api/v1/master/records/EQ-B").status_code == 404
    # ★ 검사하는 것은 **계약**이다: 감사 기록에 실제 마스터 코드가 남는가.
    #   호출 방식(위치 인자 vs 키워드)을 검사하면 규약이 바뀔 때마다 깨지고, 그때 사람은
    #   테스트를 고치면서 계약도 함께 무디게 만든다.
    assert seen, "거부가 감사로그에 남지 않았다 — 404 은 응답에서만 숨기는 것이다"
    args, kwargs = seen[0]
    recorded = list(args) + [kwargs.get("resource_id"), kwargs.get("resource_type")]
    assert "EQ-B" in recorded, f"실제 마스터 코드가 기록되지 않았다: {seen[0]}"
    assert "master_record" in recorded, f"자원 종류가 기록되지 않았다: {seen[0]}"


def test_master_write_paths_require_data_admin(monkeypatch):
    """익명·일반 사용자는 기준정보 생성·개정·폐기·별칭 변경을 할 수 없다."""
    _master_rows(monkeypatch)
    c = TestClient(_app(monkeypatch, user_id="ghost@ls", user=None, routers=("master",)))
    assert c.post("/api/v1/master/types", json={"type_id": "x1", "name_ko": "X"}).status_code == 403
    assert c.post("/api/v1/master/records", json={
        "master_code": "MAT-X", "type_id": "material", "name": "X",
    }).status_code == 403
    assert c.delete("/api/v1/master/records/MAT-A").status_code == 403
    assert c.post("/api/v1/master/records/MAT-A/aliases", json={"aliases": ["가"]}).status_code == 403
    assert c.get("/api/v1/master/scope-bindings/coverage").status_code == 403
    assert c.get("/api/v1/master/scope-bindings").status_code == 403
    assert c.get("/api/v1/master/documents/quality").status_code == 403
