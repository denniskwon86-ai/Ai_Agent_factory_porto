"""★★★ [2026-08-05] 경영계획 API 통제 — 무방비 라우트 14개 봉합 + 범위 판정 고장 수정.

## 실측한 결함 (봉합 전)

```
익명 GET /api/v1/planning/accounts    → 200, 계정과목 10건
익명 GET /api/v1/planning/scenarios   → 200, 시나리오 4건
익명 GET /api/v1/planning/submissions → 200, **경영계획 제출물**
익명 POST /api/v1/planning/accounts   → 200, **계정과목이 실제로 등록됐다**
익명 POST /api/v1/planning/drivers    → 200, **동인이 실제로 등록됐다**
```

⚠️ 인수인계 기록은 «지금은 0건이라 실제 유출이 없다» 고 적었는데 **그 사이 데이터가 들어왔다.**
  «비어 있으니 나중에» 로 미룬 통제는 데이터가 들어오는 순간 유출이 된다.

## 그리고 더 큰 것 — 범위 판정이 고장나 있었다

`scope_guard._actor_scopes()` 가 **모든 사용자에게 빈 집합**을 돌려주고 있었다(부서 id 를
노드로 바꾸는 리솔버가 모든 참조에 빈 문자열을 반환). 그래서 `resolve_effective_scope` 는
범위를 명시하면 누구든 거부했고, `POST /planning/facts`·`/scenarios`·`/submissions` 가
`unrestricted` 아닌 **모든 사용자에게 404** 였다 — 경영계획을 현업이 쓸 수 없었다.
반대로 범위를 명시하지 않으면 필터 없이 통과했다. 통제가 «전부 막힘 아니면 전부 열림» 으로
갈라져 있었고 어느 쪽도 의도가 아니다.

## 계정은 실측해서 골랐다

· `hikwon@lsmnm.com`    — `unrestricted=True`(전면 통과)
· `hikwon_4@lsmnm.com`  — 범위 `LS_MNM`·`MNM_BATTERY`·`MNM_COPPER`
· `hikwon_7@lsmnm.com`  — 범위 `LS_MNM` 하나
· `hikwon_2@lsmnm.com`  — 범위 `MNM_BATTERY` 하나, 기준정보 권한 없음
· `hikwon_17@lsmnm.com` — viewer(범위 `LS_MNM`)
"""
import pytest
from fastapi.testclient import TestClient

B = "/api/v1/planning"

ADMIN = "hikwon@lsmnm.com"
WIDE = "hikwon_4@lsmnm.com"
MGR = "hikwon_7@lsmnm.com"        # LS_MNM
MEMBER = "hikwon_2@lsmnm.com"     # MNM_BATTERY
VIEWER = "hikwon_17@lsmnm.com"
NOBODY = "nobody@example.com"


def H(uid: str):
    return {"X-Factory-User": uid} if uid else {}


@pytest.fixture()
def client(monkeypatch):
    """권한 강제를 켠 앱. ⚠️ 앞뒤로 스코프 캐시를 비운다 — 강제를 켠 캐시가 남으면 뒤에 도는
    다른 파일의 테스트가 그것을 물려받는다."""
    import config
    from core.org_directory import org_directory
    org_directory._invalidate()
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    from main import app
    try:
        yield TestClient(app)
    finally:
        org_directory._invalidate()


#: 봉합한 읽기 라우트 전부. 새 라우트를 추가하면 여기 넣어야 익명 검사에 걸린다.
READ_PATHS = [
    "/accounts",
    "/scenarios",
    "/submissions",
    "/submissions/current?org_id=LS_MNM&period=2026",
    "/submissions/x/integrity",
    "/drivers",
    "/drivers/D1/impacts",
    "/drivers/D1/preview?pct_change=5",
    "/drivers/D1/external",
    "/import/template",
]


# ── 익명·미등록 (인수인계 §4.1) ───────────────────────────────────────────
@pytest.mark.parametrize("path", READ_PATHS)
def test_anonymous_cannot_read_planning(client, path):
    """★★★ 익명은 경영계획 자료를 읽을 수 없다. **401** 이다 — 할 일은 «로그인» 이다."""
    r = client.get(f"{B}{path}")
    assert r.status_code == 401, f"{path} 가 익명에게 {r.status_code} 로 열려 있다"


@pytest.mark.parametrize("path", ["/accounts", "/scenarios", "/submissions", "/drivers"])
def test_unregistered_user_is_refused_with_403(client, path):
    """★★ 등록되지 않은 사용자는 **403** — 식별은 됐고 권한이 없다.

    401 로 뭉개면 이미 이름을 밝힌 사용자가 계속 로그인을 시도한다."""
    r = client.get(f"{B}{path}", headers=H(NOBODY))
    assert r.status_code == 403


@pytest.mark.parametrize("path,payload", [
    ("/accounts", {"account_code": "", "name": "", "category": ""}),
    ("/drivers", {"driver_code": "", "name": ""}),
    ("/scenarios/__no_such__/assumptions",
     {"target_code": "X", "operator": "pct", "value": 1, "rationale": "테스트"}),
    ("/drivers/__no_such__/impacts",
     {"account_code": "X", "elasticity": 1, "rationale": "t", "source": "t"}),
    ("/import/rows", {"rows": [], "commit": False}),
])
def test_anonymous_cannot_write_planning(client, path, payload):
    """★★★ 익명 쓰기 차단. **실측으로 `/accounts`·`/drivers` 는 실제로 등록됐다.**

    ⚠️ 이 테스트는 존재하지 않는 id·빈 payload 로만 부른다 — 통제가 풀렸을 때 데이터를 만들지
      않기 위해서다(실제로 그렇게 데이터를 만든 사고가 있었다)."""
    r = client.post(f"{B}{path}", json=payload)
    assert r.status_code == 401, f"{path} 가 익명 쓰기에 {r.status_code} 를 줬다"


# ── 기준정보 쓰기 자격 ────────────────────────────────────────────────────
@pytest.mark.parametrize("path,payload", [
    ("/accounts", {"account_code": "", "name": "", "category": ""}),
    ("/drivers", {"driver_code": "", "name": ""}),
    ("/drivers/__no_such__/impacts",
     {"account_code": "X", "elasticity": 1, "rationale": "t", "source": "t"}),
])
def test_master_data_write_needs_standard_permission(client, path, payload):
    """★★★ 계정과목·동인은 **전사 기준정보**다 — 한 사람이 추가하면 전 조직의 집계가 바뀐다.

    `upsert` 이므로 기존 계정을 덮어써 과거 집계의 의미를 바꿀 수도 있다."""
    for uid in (MEMBER, VIEWER):
        r = client.post(f"{B}{path}", json=payload, headers=H(uid))
        assert r.status_code == 403, f"{uid} 가 {path} 에 쓸 수 있다"


# ── 조직 범위 격리 ────────────────────────────────────────────────────────
def test_other_orgs_plan_is_hidden_as_404(client):
    """★★★ 범위 밖 조직 요청은 **404 은폐**다 — 403 은 «그 조직에 계획이 있다» 를 알려 준다."""
    for uid, org in ((MGR, "MNM_BATTERY"), (MEMBER, "LS_MNM"), (MEMBER, "MNM_COPPER")):
        for path in (f"/submissions?org_id={org}",
                     f"/submissions/current?org_id={org}&period=2026",
                     f"/scenarios?org_id={org}"):
            r = client.get(f"{B}{path}", headers=H(uid))
            assert r.status_code == 404, f"{uid} 가 {org} 의 {path} 에 {r.status_code} 를 받았다"


def test_own_scope_still_works(client):
    """★★★ **통제가 업무를 막지 않는다.**

    ⚠️ 이 테스트가 이 파일에서 가장 중요하다. `_actor_scopes` 가 빈 집합을 돌려주던 동안
      자기 조직 요청도 404 였다 — 통제를 조이다가 기능을 끈 상태였고, 그것을 «막혔으니 안전»
      으로 읽으면 아무도 못 쓰는 제품이 된다."""
    for uid, org in ((MGR, "LS_MNM"), (MEMBER, "MNM_BATTERY"), (WIDE, "MNM_COPPER")):
        for path in (f"/submissions?org_id={org}",
                     f"/submissions/current?org_id={org}&period=2026",
                     f"/scenarios?org_id={org}",
                     f"/cash-flow?org_id={org}&period=2026",
                     f"/variance?org_id={org}&period=2026",
                     f"/facts?org_id={org}&scope_node_id={org}"):
            r = client.get(f"{B}{path}", headers=H(uid))
            assert r.status_code == 200, \
                f"{uid} 가 **자기 조직** {org} 의 {path} 에서 {r.status_code} 를 받았다"


def test_scope_sources_agree(client):
    """★★★ `scope_guard._actor_scopes` 와 `deps.viewer_visible_scopes` 가 **같은 값**을 준다.

    두 판정이 서로 다른 원천을 보면 «목록에는 있는데 상세는 404» 같은 어긋남이 생긴다.
    실제로 `_actor_scopes` 만 부서 id 해석에 의존하다가 빈 집합이 되어 그 어긋남이 일어났다."""
    from api.deps import Principal, viewer_visible_scopes
    from core.org_directory import org_directory
    from core.scope_guard import _actor_scopes
    for uid in (MGR, MEMBER, WIDE, VIEWER):
        p = Principal(user_id=uid, scope=org_directory.resolve_scope(uid))
        actor = set(_actor_scopes(p))
        visible = viewer_visible_scopes(p)
        assert actor == set(visible or ()), f"{uid}: actor={actor} visible={visible}"
        assert actor, f"{uid} 의 범위가 비어 있다 — 그러면 모든 범위 요청이 거부된다"


def test_unrestricted_actor_passes_through(client):
    """`unrestricted` 주체는 범위 필터를 받지 않는다(하위호환 계약) — 그 사실을 못 박아 둔다."""
    from api.deps import Principal, viewer_visible_scopes
    from core.org_directory import org_directory
    from core.scope_guard import _actor_scopes
    p = Principal(user_id=ADMIN, scope=org_directory.resolve_scope(ADMIN))
    assert viewer_visible_scopes(p) is None
    assert _actor_scopes(p) == []          # 무제한 주체는 목록으로 표현하지 않는다
    assert client.get(f"{B}/submissions", headers=H(ADMIN)).status_code == 200


# ── 숨긴 건수 노출 정책 (Data Stealth) ────────────────────────────────────
def test_hidden_count_is_only_for_stewards(client):
    """★★★ **사실은 모두에게, 정확한 수는 자격자에게만.**

    경영계획은 재무 정보다 — «전사에 계획이 몇 건 있는가» 자체가 정보이므로, 404 로 존재를
    숨기면서 «옆 조직에 47건 있다» 를 말하면 통제가 앞뒤로 어긋난다."""
    r = client.get(f"{B}/submissions", headers=H(MEMBER))
    assert r.status_code == 200
    d = r.json()
    assert "hidden_present" in d, "가려진 것이 있다는 **사실**은 알려야 한다"
    if d.get("hidden_present"):
        assert "hidden_count" not in d, "일반 사용자에게 정확한 숨김 건수를 줬다"

    a = client.get(f"{B}/submissions", headers=H(ADMIN)).json()
    assert "hidden_present" in a


def test_hidden_envelope_rejects_unknown_kind():
    """★★ 오타를 조용히 «건수 안 줌» 으로 처리하지 않는다 — 관리자가 못 보는 이유를 아무도
    찾지 못한다. 계약 위반이므로 개발 중에 터져야 한다."""
    from api.deps import Principal, hidden_envelope
    from core.org_directory import org_directory
    p = Principal(user_id=ADMIN, scope=org_directory.resolve_scope(ADMIN))
    hidden_envelope(p, 10, 5, exact_for="plan")          # 등록된 종류는 통과
    with pytest.raises(ValueError):
        hidden_envelope(p, 10, 5, exact_for="plna")      # 오타


# ── 파일 등록: 행별 조직 검증 ─────────────────────────────────────────────
def test_import_rejects_rows_outside_scope(client):
    """★★★ `planning_import.import_rows` 는 행의 `org_id` 를 **검증 없이 저장한다.**

    즉 식별된 사용자면 누구나 **남의 조직 실적·계획을 등록**할 수 있었다 — 읽기를 막아도 이
    경로로 들어온 값이 그 조직의 실적이 되므로 통제가 성립하지 않는다.
    ⚠️ `commit=False`(검증만)에서도 막는다. 두 경로의 판정이 다르면 반드시 어긋난다."""
    rows = [{"org_id": "MNM_BATTERY", "account_code": "4000", "period": "2026",
             "value_kind": "ACTUAL", "amount": "1"}]
    for commit in (False, True):
        r = client.post(f"{B}/import/rows", json={"rows": rows, "commit": commit},
                        headers=H(MGR))            # MGR 범위는 LS_MNM 뿐
        assert r.status_code == 404, f"commit={commit} 에서 범위 밖 행이 통과했다"


def test_import_rejects_when_any_row_is_outside_scope(client):
    """★★ 한 행이라도 범위 밖이면 **전부 거부**한다 — importer 의 «부분 저장 없음» 과 같은 규칙.

    부분 허용은 무엇이 들어갔는지 아무도 모르게 만든다."""
    rows = [{"org_id": "LS_MNM", "account_code": "4000", "period": "2026",
             "value_kind": "ACTUAL", "amount": "1"},
            {"org_id": "MNM_COPPER", "account_code": "4000", "period": "2026",
             "value_kind": "ACTUAL", "amount": "1"}]
    r = client.post(f"{B}/import/rows", json={"rows": rows, "commit": False}, headers=H(MGR))
    assert r.status_code == 404


def test_import_allows_own_scope_validation(client):
    """통제가 업무를 막지 않는다 — 자기 조직 행은 검증까지 통과해야 한다(`commit=False`)."""
    rows = [{"org_id": "LS_MNM", "account_code": "4000", "period": "2026",
             "value_kind": "ACTUAL", "amount": "1"}]
    r = client.post(f"{B}/import/rows", json={"rows": rows, "commit": False}, headers=H(MGR))
    assert r.status_code == 200, "자기 조직 행 검증이 막혔다"


# ── 가정·무결성은 대상의 소유 조직으로 판정 ───────────────────────────────
def test_assumption_scope_comes_from_the_scenario_not_the_request(client):
    """★★ 범위를 **요청자가 보낸 값이 아니라 대상 시나리오의 소유 조직**에서 가져온다.

    요청 값으로 판정하면 «내 조직» 이라고 주장하며 남의 시나리오를 고칠 수 있다."""
    r = client.post(f"{B}/scenarios/__no_such__/assumptions",
                    json={"target_code": "X", "operator": "pct", "value": 1,
                          "rationale": "테스트"}, headers=H(MGR))
    # 없는 시나리오는 404 — 존재 여부를 알려 주면 id 를 훑어볼 수 있다.
    assert r.status_code == 404


def test_integrity_check_is_scoped(client):
    """무결성 판정은 «그 조직의 승인본이 사후 변경됐다» 를 알려 준다 — 남의 조직 것은 404."""
    r = client.get(f"{B}/submissions/__no_such__/integrity", headers=H(MGR))
    assert r.status_code == 404
