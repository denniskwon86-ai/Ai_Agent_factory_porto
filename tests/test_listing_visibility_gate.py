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
    if "standards" in routers:
        import api.routes.standard_control as sc
        app.include_router(sc.router)
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


def test_document_content_is_blocked_with_403_before_reading_storage(monkeypatch):
    """원문은 검색 청크보다 무겁다. 무자격 요청은 저장소를 읽기 전에 막혀야 한다."""
    import core.knowledge_base as kb
    monkeypatch.setattr(kb.knowledge_base, "document_content",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("권한 확인 전에 원문을 읽었다")))
    c = TestClient(_app(monkeypatch, user_id="ghost@ls", user=None))
    assert c.get("/api/v1/knowledge/packs/p0/documents/secret.pdf/content").status_code == 403


def test_admin_can_read_preserved_document_content(monkeypatch):
    """대조군 — 원본이 보존된 문서는 검색 질의 없이도 내용을 직접 확인한다."""
    import core.knowledge_base as kb
    monkeypatch.setattr(kb.knowledge_base, "get_pack", lambda pid: {
        "pack_id": pid, "owner_org_id": "", "documents": [{"filename": "rule.txt"}]})
    monkeypatch.setattr(kb.knowledge_base, "document_content", lambda *a, **k: {
        "filename": "rule.txt", "content": "재고 승인 기준", "offset": 0,
        "returned": 8, "total_chars": 8, "truncated": False})
    c = TestClient(_app(monkeypatch, user_id="hikwon@ls",
                        user={"user_id": "hikwon@ls", "status": "active"},
                        scope_kw={"unrestricted": True}))
    r = c.get("/api/v1/knowledge/packs/p0/documents/rule.txt/content")
    assert r.status_code == 200
    assert r.json()["data"]["content"] == "재고 승인 기준"


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
    # ★ 일반 사용자는 «가려진 것이 있다»만 안다. 정확한 건수는 타 조직 자료의 규모를 알려주므로
    #   DA·관리자에게만 준다(`api.deps.hidden_envelope`). 아래 두 테스트가 양쪽을 지킨다.
    assert records["hidden_present"] is True and types["hidden_present"] is True
    assert "hidden_count" not in records, "일반 사용자에게 정확한 숨김 건수가 새어 나갔다"
    assert "hidden_count" not in types, "일반 사용자에게 정확한 숨김 건수가 새어 나갔다"


def test_master_hidden_count_is_given_to_data_admins(monkeypatch):
    """DA·관리자는 정확한 숨김 건수를 받는다 — 자료를 바인딩해 고칠 사람이기 때문이다."""
    _master_rows(monkeypatch)
    c = TestClient(_app(
        monkeypatch, user_id="da@ls", user={"user_id": "da@ls", "status": "active"},
        scope_kw={"unrestricted": False, "can_manage_standard": True,
                  "readable_dept_ids": frozenset({"dept-a"}),
                  "readable_scope_nodes": frozenset({"ORG-A"})}, routers=("master",)))
    records = c.get("/api/v1/master/records").json()
    assert records["hidden_present"] is True
    assert records["hidden_count"] == 1, "DA 가 숨김 건수를 못 받으면 무엇을 고칠지 모른다"


def test_master_no_hidden_rows_says_nothing_is_hidden(monkeypatch):
    """가린 것이 없으면 `hidden_present` 는 False 다 — 이 값이 항상 True 면 아무 뜻이 없다."""
    _master_rows(monkeypatch)
    import api.routes.master_control as mc
    # 이 사용자 범위(ORG-A)에 바인딩된 것만 존재하는 상황 — 즉 가릴 것이 없다.
    monkeypatch.setattr(mc.master_data, "list_records", lambda *a, **k: [
        {"master_code": "MAT-A", "type_id": "material", "name": "A 자재"},
    ])
    c = TestClient(_app(
        monkeypatch, user_id="staff@ls", user={"user_id": "staff@ls", "status": "active"},
        scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"}),
                  "readable_scope_nodes": frozenset({"ORG-A"})}, routers=("master",)))
    records = c.get("/api/v1/master/records").json()
    assert [r["master_code"] for r in records["data"]] == ["MAT-A"]
    assert records["hidden_present"] is False and "hidden_count" not in records


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


# ── 업무표준: 라우트에 권한 검사가 **하나도 없었다**(2026-08-04 이관 3/10) ──────────
#
# ★★★ 익명 요청으로 `POST /api/v1/standards` 와 `POST /api/v1/standards/seed?force=true` 가
#   그대로 통했다. 즉 **누구나 에이전트의 통과·반려 기준을 바꿀 수 있었다.**
#   지식팩 삭제 구멍보다 파급이 넓다 — 표준이 바뀌면 이후 모든 산출물의 판정이 바뀐다.
def _standards(monkeypatch):
    import api.routes.standard_control as sc
    monkeypatch.setattr(sc, "_list_all", lambda: [
        {"master_code": "WS-RFP", "stage": "RFP", "kind": "regulation", "version": 1},
        {"master_code": "WG-PLAN", "stage": "PLAN", "kind": "guideline", "version": 2},
    ])
    monkeypatch.setattr(sc, "get_standard", lambda stage: {"stage": stage, "checks": []})
    monkeypatch.setattr(sc, "render_standard_brief", lambda stage: "고지문")
    return sc


def test_work_standard_list_is_blocked_for_anonymous(monkeypatch):
    """익명에게는 0건 + 이유. **탭 메타(`/kinds`)도 같이 막는다** — 탭만 그려 주면 화면이
    «권한 있음»처럼 보이고 목록만 비어, 사용자는 «등록된 표준이 없다»로 읽는다."""
    _standards(monkeypatch)
    c = TestClient(_app(monkeypatch, user_id="", user=None, routers=("standards",)))
    for path in ("/api/v1/standards", "/api/v1/standards/kinds"):
        body = c.get(path).json()
        assert body["data"] == [], f"{path} 가 익명에게 자료를 줬다"
        assert body.get("blocked_reason"), f"{path} 차단 이유가 없다 — 0건과 구분되지 않는다"


def test_work_standard_detail_is_403_not_404(monkeypatch):
    """상세·이력은 403 이다. 404 로 숨기지 않는다 — 업무표준은 전사 제도 문서이므로 존재가
    비밀이 아니고, 404 로 두면 «없는 단계»와 «권한 없음»이 섞여 원인을 못 찾는다."""
    _standards(monkeypatch)
    c = TestClient(_app(monkeypatch, user_id="", user=None, routers=("standards",)))
    assert c.get("/api/v1/standards/RFP").status_code == 403
    assert c.get("/api/v1/standards/RFP/history").status_code == 403


def test_work_standard_writes_require_data_admin(monkeypatch):
    """★★★ 개정·재시드는 DA·관리자만. 이것이 열려 있던 것이 이 파일에 항목을 추가한 이유다."""
    _standards(monkeypatch)
    c = TestClient(_app(monkeypatch, user_id="ghost@ls", user=None, routers=("standards",)))
    assert c.post("/api/v1/standards", json={"stage": "RFP"}).status_code == 403
    assert c.post("/api/v1/standards/seed?force=true").status_code == 403


def test_work_standard_reader_sees_list_and_admin_can_revise(monkeypatch):
    """★ 통제가 업무를 막지 않는다. 등록된 사용자는 목록을 보고, DA 는 개정할 수 있다."""
    sc = _standards(monkeypatch)
    reader = TestClient(_app(
        monkeypatch, user_id="staff@ls", user={"user_id": "staff@ls", "status": "active"},
        scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"})},
        routers=("standards",)))
    body = reader.get("/api/v1/standards").json()
    assert len(body["data"]) == 2 and not body.get("blocked_reason")
    assert reader.get("/api/v1/standards/kinds").json()["data"], "탭 메타가 비었다"

    # DA 의 개정은 통하고, 감사에 남는다.
    recorded = []
    monkeypatch.setattr(sc.audit, "record",
                        lambda *a, **k: recorded.append((a, k)) or True)
    monkeypatch.setattr(sc, "register_standard",
                        lambda *a, **k: {"master_code": "WS-RFP", "version": 3})
    da = TestClient(_app(
        monkeypatch, user_id="da@ls", user={"user_id": "da@ls", "status": "active"},
        scope_kw={"unrestricted": False, "can_manage_standard": True},
        routers=("standards",)))
    assert da.post("/api/v1/standards", json={"stage": "RFP"}).status_code == 200
    events = [a[0] for a, _ in recorded]
    assert "WORK_STANDARD_CHANGED" in events, (
        f"업무표준 개정이 감사에 남지 않았다 — 기준이 언제 바뀌었는지 설명할 수 없다: {recorded}")


# ── 조직·사용자 명부: 읽기 라우트에 자격 검사가 **없었다**(2026-08-04 이관 4/10) ──────
#
# ★★★ 익명 요청 하나로 전 직원 21명의 **이름·이메일·소속 부서·관리자 여부**가 그대로 나왔다.
#   목록이 새는 것이 아니라 **개인정보가 새는 것**이다. 명부는 조직 규모·인사 구조·권한 보유자를
#   한 번에 알려주고, 그 조합이 표적 공격의 출발점이 된다.
ROSTER = [
    {"user_id": "boss@ls", "display_name": "관리자", "primary_dept_id": "hq", "is_admin": True},
    {"user_id": "a@ls", "display_name": "가", "primary_dept_id": "dept-a"},
    {"user_id": "b@ls", "display_name": "나", "primary_dept_id": "dept-b"},
    {"user_id": "none@ls", "display_name": "미배정", "primary_dept_id": ""},
]


def _org_rows(monkeypatch):
    import api.routes.org_control as oc
    monkeypatch.setattr(oc.org_directory, "list_users", lambda: list(ROSTER))
    monkeypatch.setattr(oc.org_directory, "get_tree", lambda: {"dept_id": "hq", "children": []})
    monkeypatch.setattr(oc.org_directory, "list_departments", lambda inc=False: [{"dept_id": "hq"}])
    return oc


def _org_app(monkeypatch, *, enforced=True, user_id="", user=None, scope_kw=None):
    """⚠️ 값을 **먼저 꺼내** 람다에 담는다. 람다 안에서 `kw.pop` 을 부르면 첫 호출에만 값이
    있고 두 번째부터 기본값으로 돌아간다 — 실제로 그 실수로 테스트가 엉뚱하게 실패했다.

    ⚠️ `get_user` 는 **한 번만** 패치한다. 요청자 자격 확인(`visibility_block_reason`)과 조회
      대상 조회가 같은 함수를 쓰는 것이 실제 구조이므로, 두 곳에서 따로 패치하면 나중 것이
      이겨서 «b@ls 를 물었는데 a@ls 가 돌아오는» 상태가 된다(그래서 403 이 200 으로 보였다)."""
    import api.routes.org_control as oc
    import core.org_directory as od
    monkeypatch.setattr(od, "_org_enforce_effective", lambda: enforced)
    monkeypatch.setattr(od.org_directory, "get_user",
                        lambda uid: (user if (user_id and uid == user_id)
                                     else next((u for u in ROSTER if u["user_id"] == uid), None)))
    app = FastAPI()
    app.include_router(oc.router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=user_id,
        scope=AccessScope(user_id=user_id, **(scope_kw or {"unrestricted": False})))
    return app


@pytest.mark.parametrize("uid,user,why", [
    ("", None, "익명"),
    ("ghost@ls", None, "미등록"),
    ("old@ls", {"user_id": "old@ls", "status": "retired"}, "폐지"),
])
def test_org_directory_is_403_for_unentitled(monkeypatch, uid, user, why):
    """★★★ 명부·트리·부서 목록 모두 자격을 요구한다. 실측에서는 익명에게 21명이 나왔다."""
    _org_rows(monkeypatch)
    c = TestClient(_org_app(monkeypatch, user_id=uid, user=user))
    for path in ("/api/v1/org/users", "/api/v1/org/tree", "/api/v1/org/departments"):
        assert c.get(path).status_code == 403, f"{why} 상태에서 {path} 가 열렸다"


def test_org_users_are_filtered_to_readable_depts(monkeypatch):
    """일반 사용자는 **자기 부서 인원 + 자기 자신**만 본다. 부서 미배정 계정은 보이지 않는다 —
    미배정을 «전사 공개»로 읽으면 이행 기간 계정이 전원에게 노출된다."""
    _org_rows(monkeypatch)
    c = TestClient(_org_app(
        monkeypatch, user_id="a@ls", user={"user_id": "a@ls", "status": "active"},
        scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"})}))
    body = c.get("/api/v1/org/users").json()
    assert [u["user_id"] for u in body["data"]] == ["a@ls"]
    assert body["hidden_present"] is True
    # 전 직원 수는 조직 규모를 알려준다 — 건수도 권한을 따른다.
    assert "hidden_count" not in body, "일반 사용자에게 전 직원 규모가 새어 나갔다"
    # 범위 밖 개인의 권한 플래그·역할은 명부 한 줄보다 민감하다.
    assert c.get("/api/v1/org/users/b@ls").status_code == 403
    assert c.get("/api/v1/org/users/a@ls").status_code == 200, "자기 자신은 항상 보여야 한다"


def test_org_admin_sees_everyone_with_exact_count(monkeypatch):
    """★ 조직 편집 권한자는 전량을 본다 — 통제가 인사 운영을 막으면 통제가 꺼진다."""
    _org_rows(monkeypatch)
    c = TestClient(_org_app(
        monkeypatch, user_id="boss@ls", user={"user_id": "boss@ls", "status": "active"},
        scope_kw={"unrestricted": False, "can_edit_org": True,
                  "readable_dept_ids": frozenset({"hq"})}))
    body = c.get("/api/v1/org/users").json()
    assert len(body["data"]) == 4 and body["hidden_present"] is False
    assert c.get("/api/v1/org/users/none@ls").status_code == 200


def test_org_exact_count_rule_is_per_resource_kind(monkeypatch):
    """★★ 정확한 건수 자격은 **자료 종류마다 다르다.** 데이터 표준 관리자(DA)에게 전 직원 명부
    규모가 새지 않아야 하고, 그 반대도 마찬가지다."""
    from api.deps import Principal as P, hidden_envelope
    # ⚠️ `AccessScope.unrestricted` 의 **기본값은 True**(조직 미도입 하위호환)이다. 명시하지
    #   않으면 무제한 권한자가 되어 이 테스트가 통과하는 것처럼 보인다 — 실제로 그렇게 새로 걸렸다.
    da = P(user_id="da@ls", scope=AccessScope(
        user_id="da@ls", unrestricted=False, can_manage_standard=True))
    org = P(user_id="hr@ls", scope=AccessScope(
        user_id="hr@ls", unrestricted=False, can_edit_org=True))
    assert hidden_envelope(da, 10, 3, exact_for="standard").get("hidden_count") == 7
    assert "hidden_count" not in hidden_envelope(da, 10, 3, exact_for="org")
    assert hidden_envelope(org, 10, 3, exact_for="org").get("hidden_count") == 7
    assert "hidden_count" not in hidden_envelope(org, 10, 3, exact_for="standard")
    # 오타를 «건수 안 줌»으로 조용히 처리하면 관리자가 못 보는 이유를 아무도 못 찾는다.
    with pytest.raises(ValueError):
        hidden_envelope(org, 10, 3, exact_for="typo")


def test_agent_exact_count_rule_covers_ai_admin():
    """★★★ 에이전트·스킬·워크플로우 자산의 «몇 건이 가려졌는가» 는 **AI 관리자**도 알아야 한다.

    ⚠️ 이 규칙이 `org`·`standard` 만으로 돼 있으면 기능이 **아무에게도 도달하지 않는다.**
      실측(2026-08-08 시드): AI 거버넌스 관리자 `hikwon_4@lsmnm.com` 은 `can_edit_org=False`·
      `can_manage_standard=False` 이고 `is_ai_admin` 만 True 다. 그를 빼면 정확한 건수를 받는
      사람은 플랫폼 관리자뿐인데, **플랫폼 관리자는 `scoped=False` 라 애초에 가려지는 것이 없다.**
      즉 「아무도 못 받는 값」을 만들고도 테스트는 초록일 수 있다 — 그래서 자격을 여기서 못박는다.

    ★ 반대 방향도 함께 잠근다. 「AI 자산의 관리자」라는 자격이 인사 명부·기준정보·경영계획의
      **규모를 읽는 자격으로 번지면**, 어느 순간 «관리자니까 다 본다» 가 되고 그때는 각 자료의
      정확한 건수 규칙이 있으나 마나가 된다."""
    from api.deps import Principal as P, hidden_envelope
    # ⚠️ `unrestricted` 기본값이 True 라 명시하지 않으면 무제한 권한자가 된다(위 테스트 참조).
    ai = P(user_id="ai@ls", scope=AccessScope(
        user_id="ai@ls", unrestricted=False, is_ai_admin=True))
    assert hidden_envelope(ai, 10, 3, exact_for="agent").get("hidden_count") == 7
    for other in ("org", "standard", "plan"):
        assert "hidden_count" not in hidden_envelope(ai, 10, 3, exact_for=other), \
            f"AI 관리자가 '{other}' 자료의 규모까지 본다"

    # 조직 관리자·데이터 관리자도 에이전트 자산의 관리 주체다(설계 §4.2 — 조직에 배치하는 사람).
    for kw in ({"can_edit_org": True}, {"can_manage_standard": True}):
        p = P(user_id="x@ls", scope=AccessScope(user_id="x@ls", unrestricted=False, **kw))
        assert hidden_envelope(p, 10, 3, exact_for="agent").get("hidden_count") == 7, kw

    # ★ 부서 manager·member·viewer 는 «있다» 만 안다. 남의 조직 자산 규모는 그 자체로 정보다.
    plain = P(user_id="m@ls", scope=AccessScope(user_id="m@ls", unrestricted=False))
    env = hidden_envelope(plain, 10, 3, exact_for="agent")
    assert env["hidden_present"] is True and "hidden_count" not in env


# ── 거버넌스 지표: 익명이 **취약점 지도**를 보고 있었다(2026-08-04 이관 5/10) ──────────
#
# ★★★ 실측으로 익명이 받아 본 것:
#   · `/contracts/evaluate` → 위반 계약과 사유(«생산자 자산이 폐기됐다 — 약속을 지킬 원천이
#     사라졌다»)
#   · `/external/readiness` → 지표 6개의 필요 등급·**격차 영향**·다음 행동
#     («물량 계획의 외부 근거가 없어 낙관 편향을 검증할 수단이 없습니다»)
#
# ⚠️ 자료 본문이 아니라 «집계»라서 가볍게 보기 쉽다. 그러나 거버넌스 콘솔은 정의상
#   «무엇이 안 되어 있는가»를 모으는 화면이므로, 집계 자체가 취약점 목록이다.
def _gov_app(monkeypatch, *, enforced=True, user_id="", user=None, scope_kw=None):
    import api.routes.catalog_control as cc
    import api.routes.contract_control as ctc
    import api.routes.crosswalk_control as cwc
    import api.routes.external_control as ec
    import core.org_directory as od
    monkeypatch.setattr(od, "_org_enforce_effective", lambda: enforced)
    monkeypatch.setattr(od.org_directory, "get_user", lambda uid: user)
    app = FastAPI()
    for r in (cc.router, ctc.router, cwc.router, ec.router):
        app.include_router(r)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=user_id,
        scope=AccessScope(user_id=user_id, **(scope_kw or {"unrestricted": False})))
    return app


GOVERNANCE_PATHS = (
    "/api/v1/catalog/governance/coverage",
    "/api/v1/catalog/governance/gaps",
    "/api/v1/contracts/evaluate",
    "/api/v1/crosswalk/systems/coverage",
    "/api/v1/external/readiness",
    "/api/v1/external/indicators",
    "/api/v1/external/sources",
)


@pytest.mark.parametrize("uid,user,why", [
    ("", None, "익명"),
    ("ghost@ls", None, "미등록"),
    ("staff@ls", {"user_id": "staff@ls", "status": "active"}, "권한 없는 일반 사용자"),
])
def test_governance_metrics_require_role(monkeypatch, uid, user, why):
    """전사 정비 상태는 데이터 관리자·조직 관리자·경영진에게만. 그 밖에는 403 + 이유."""
    c = TestClient(_gov_app(monkeypatch, user_id=uid, user=user,
                            scope_kw={"unrestricted": False,
                                      "readable_dept_ids": frozenset({"dept-a"})}))
    for path in GOVERNANCE_PATHS:
        r = c.get(path)
        assert r.status_code == 403, f"{why} 에게 {path} 가 열려 있다"
        assert r.json().get("detail"), f"{path} 차단 이유가 없다"


@pytest.mark.parametrize("role", ["can_manage_standard", "can_edit_org", "can_run_enterprise"])
def test_governance_metrics_open_for_stewards(monkeypatch, role):
    """★ 정비를 **할 사람**은 막지 않는다 — 통제가 정비를 막으면 정비가 멈춘다."""
    c = TestClient(_gov_app(
        monkeypatch, user_id="steward@ls", user={"user_id": "steward@ls", "status": "active"},
        scope_kw={"unrestricted": False, role: True, "readable_dept_ids": frozenset({"hq"})}))
    for path in GOVERNANCE_PATHS:
        assert c.get(path).status_code == 200, f"{role} 에게 {path} 가 막혔다"


def test_governance_gate_is_transparent_when_enforcement_off(monkeypatch):
    """★★ 강제가 꺼져 있으면 아무것도 막지 않는다 — ECM 미도입 흐름의 하위호환 계약."""
    c = TestClient(_gov_app(monkeypatch, enforced=False, user_id="", user=None))
    for path in GOVERNANCE_PATHS:
        assert c.get(path).status_code == 200, f"강제가 꺼졌는데 {path} 가 막혔다"


def test_clearance_aware_lists_keep_their_design(monkeypatch):
    """★★ 이미 **등급 기반 가림**이 있는 목록(§6-2 사용자 결정)은 403 으로 덮지 않는다.

    자산·계약·연계 시스템 목록은 낮은 등급에 «제목만» 주도록 설계돼 있다. 그 설계를 지우면
    문서화된 사용자 결정이 조용히 사라진다. 다만 익명·미등록에는 0건 + 이유로 답한다."""
    anon = TestClient(_gov_app(monkeypatch, user_id="", user=None))
    for path in ("/api/v1/catalog/assets", "/api/v1/contracts", "/api/v1/crosswalk/systems"):
        b = anon.get(path).json()
        assert b["data"] == [] and b.get("blocked_reason"), f"{path} 가 익명에게 열려 있다"

    staff = TestClient(_gov_app(
        monkeypatch, user_id="staff@ls", user={"user_id": "staff@ls", "status": "active"},
        scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"})}))
    for path in ("/api/v1/catalog/assets", "/api/v1/contracts", "/api/v1/crosswalk/systems"):
        r = staff.get(path)
        assert r.status_code == 200, f"{path} 가 일반 사용자에게 403 이 됐다 — 등급 설계를 덮었다"
        assert not r.json().get("blocked_reason")


# ── 브리핑: 요약 화면이 다른 통제를 우회했다(2026-08-04 이관 9/10 선행) ─────────────
#
# ★★★ 실측으로 익명이 전사 브리핑에서 본 것:
#   · «데이터 계약 breached: dck_e0b536c20a v1 — 생산자 자산(QC 실적)이 폐기됐다»
#   · «스킬 제안 검토 대기 18건»
#
# 5/10 에서 거버넌스 지표를 막았는데, 브리핑이 **같은 자료를 다시 모아** 보여 주므로 통제가
# 우회됐다. ⚠️ 여러 소스를 모으는 화면은 각 소스의 통제를 반드시 다시 판정해야 한다 —
# 그러지 않으면 통제는 원래 경로에만 걸리고 «요약» 경로로 새어 나간다.
def _briefing_app(monkeypatch, *, enforced=True, user_id="", user=None, scope_kw=None):
    import api.routes.briefing_control as bc
    import core.org_directory as od
    monkeypatch.setattr(od, "_org_enforce_effective", lambda: enforced)
    monkeypatch.setattr(od.org_directory, "get_user", lambda uid: user)
    # 브리핑 조립은 대역으로 고정한다 — 통제만 검사하고 집계 로직에 의존하지 않는다.
    monkeypatch.setattr(bc.enterprise_briefing, "briefing", lambda *a, **k: {
        "sections": {
            "my_decisions": {"items": [{"title": "검토 대기"}], "count": 1},
            "data_health": {"items": [{"title": "계약 위반 — 생산자 자산 폐기"}], "count": 1},
            "cost": {"available": True, "cost_usd": 1.0},
        },
        "attention_count": 2,
    })
    app = FastAPI()
    app.include_router(bc.router)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=user_id,
        scope=AccessScope(user_id=user_id, **(scope_kw or {"unrestricted": False})))
    return app


@pytest.mark.parametrize("uid,user,why", [
    ("", None, "익명"),
    ("ghost@ls", None, "미등록"),
    ("old@ls", {"user_id": "old@ls", "status": "retired"}, "폐지"),
])
def test_briefing_is_blocked_for_unentitled(monkeypatch, uid, user, why):
    """자격 없는 요청자에게 전사 브리핑을 주지 않는다. 실측에서는 익명에게 전량이 나왔다."""
    c = TestClient(_briefing_app(monkeypatch, user_id=uid, user=user))
    assert c.get("/api/v1/briefing").status_code == 403, f"{why} 에게 브리핑이 열려 있다"
    assert c.get("/api/v1/briefing/sections/data_health").status_code == 403


def test_briefing_withholds_governance_sections_from_plain_users(monkeypatch):
    """★★★ 일반 사용자에게 «전사 정비 상태»는 담지 않는다 — 5/10 통제를 브리핑이 우회하면 안 된다.

    ⚠️ 빈 배열로 조용히 비우지 않는다. `withheld` 를 함께 실어 화면이 «문제 없음»과 «못 봤다»를
      구분할 수 있게 한다 — 그 구분이 5/10 에서 고친 오독의 핵심이다."""
    c = TestClient(_briefing_app(
        monkeypatch, user_id="staff@ls", user={"user_id": "staff@ls", "status": "active"},
        scope_kw={"unrestricted": False, "readable_dept_ids": frozenset({"dept-a"})}))
    body = c.get("/api/v1/briefing").json()["data"]
    for name in ("data_health", "cost"):
        sec = body["sections"][name]
        assert sec.get("withheld") is True, f"{name} 섹션이 일반 사용자에게 그대로 나갔다"
        assert sec.get("withheld_reason"), f"{name} 을 가린 이유가 없다"
        assert not sec.get("items"), f"{name} 내용이 남아 있다"
    # 내 일감(my_decisions)은 그대로 보여야 한다 — 통제가 업무를 막으면 통제가 꺼진다.
    assert body["sections"]["my_decisions"]["count"] == 1
    # 부분 갱신 경로로도 우회되지 않는다.
    assert c.get("/api/v1/briefing/sections/data_health").status_code == 403
    assert c.get("/api/v1/briefing/sections/my_decisions").status_code != 403


def test_briefing_full_for_stewards(monkeypatch):
    """★ 정비를 할 사람에게는 전량을 준다."""
    c = TestClient(_briefing_app(
        monkeypatch, user_id="da@ls", user={"user_id": "da@ls", "status": "active"},
        scope_kw={"unrestricted": False, "can_manage_standard": True,
                  "readable_dept_ids": frozenset({"hq"})}))
    body = c.get("/api/v1/briefing").json()["data"]
    assert not body["sections"]["data_health"].get("withheld")
    assert body["sections"]["data_health"]["count"] == 1
