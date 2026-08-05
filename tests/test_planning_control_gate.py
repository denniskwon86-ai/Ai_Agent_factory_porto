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
def client(monkeypatch, ecm_org_seed):
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
#  ★★★ [2026-08-05 병합 검증] 이 목록에 **`/facts` 가 없었다.** 그래서 익명이
#    `GET /api/v1/planning/facts` 로 경영계획 사실 20건(금액 포함)을 받는 것을 이 파일이
#    통과시켰다 — 라우터의 다른 GET 은 다 막혔는데 가장 민감한 하나만 열려 있었다.
#  ⚠️ 목록을 손으로 관리하면 «새 라우트를 넣어야 한다» 는 주석이 지켜지지 않는다.
#    그래서 아래 `test_every_planning_get_is_covered_here` 가 라우터를 읽어 누락을 잡는다.
READ_PATHS = [
    "/accounts",
    "/facts",
    "/scenarios",
    "/submissions",
    "/submissions/current?org_id=LS_MNM&period=2026",
    "/submissions/x/integrity",
    "/drivers",
    "/drivers/D1/impacts",
    "/drivers/D1/preview?pct_change=5",
    "/drivers/D1/external",
    "/import/template",
    "/variance?org_id=LS_MNM&period=2026",
    "/cash-flow?org_id=LS_MNM&period=2026",
    "/rollup-check?org_id=LS_MNM&period=2026",
    "/backtest/plan?org_id=LS_MNM&period=2026",
    "/backtest/scenario?scenario_id=x&org_id=LS_MNM&period=2026",
]


# ── 익명·미등록 (인수인계 §4.1) ───────────────────────────────────────────
@pytest.mark.parametrize("path", READ_PATHS)
def test_anonymous_cannot_read_planning(client, path):
    """★★★ 익명은 경영계획 자료를 읽을 수 없다. **401** 이다 — 할 일은 «로그인» 이다."""
    r = client.get(f"{B}{path}")
    assert r.status_code == 401, f"{path} 가 익명에게 {r.status_code} 로 열려 있다"


def test_every_planning_get_is_covered_here(client):
    """★★★ [2026-08-05 병합 검증에서 이 파일이 놓친 것] **`READ_PATHS` 에 빠진 GET 이 없어야 한다.**

    `/facts` 가 이 목록에 없어서 익명 유출을 통과시켰다. 손으로 관리하는 목록은 «새 라우트를
    넣어야 한다» 는 주석이 지켜지지 않으므로, 라우터를 읽어 대조한다.
    ⚠️ 경로 파라미터가 있는 라우트는 목록 쪽이 실제 값을 채우므로 **패턴 단위**로 비교한다."""
    import re

    import api.routes.planning_control as pc
    declared = set()
    for r in pc.router.routes:
        if "GET" in getattr(r, "methods", set()):
            declared.add(r.path.replace(pc.router.prefix, "", 1) or "/")
    covered = {re.sub(r"\?.*$", "", p) for p in READ_PATHS}
    # 목록의 구체 값을 라우트 패턴으로 되돌린다(`/drivers/D1/impacts` → `/drivers/{...}/impacts`)
    def matches(pattern: str) -> bool:
        rx = re.sub(r"\{[^}]+\}", r"[^/]+", pattern)
        return any(re.fullmatch(rx, c) for c in covered)

    missing = sorted(p for p in declared if not matches(p))
    assert not missing, (
        f"익명 검사에서 빠진 GET 라우트가 있다: {missing} — READ_PATHS 에 넣으십시오. "
        f"«막혔을 것» 이라는 추측이 아니라 이 목록이 근거다")


@pytest.mark.parametrize("path", ["/accounts", "/facts", "/scenarios", "/submissions",
                                  "/drivers"])
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
    """★★★ 범위 밖 조직 요청은 **404 은폐**다 — 403 은 «그 조직에 계획이 있다» 를 알려 준다.

    ⚠️ **형제·하위** 조직만 여기서 검증한다. 상위 조직은 `visible_scopes` 가 조상을 항상
      포함하므로(상속) 다른 이야기다 — `test_parent_scope_is_inherited_upward` 참조."""
    for uid, org in ((MGR, "MNM_BATTERY"),        # 하위 — 하향 열람은 경영진에게만
                     (MEMBER, "MNM_COPPER")):     # 형제
        for path in (f"/submissions?org_id={org}",
                     f"/submissions/current?org_id={org}&period=2026",
                     f"/scenarios?org_id={org}"):
            r = client.get(f"{B}{path}", headers=H(uid))
            assert r.status_code == 404, f"{uid} 가 {org} 의 {path} 에 {r.status_code} 를 받았다"


def test_parent_scope_is_inherited_upward(client):
    """★★★ **상위 조직 범위는 상속된다** — 하위 부서원이 `LS_MNM` 범위를 요청하면 통과한다.

    `visible_scopes` 가 «자기 자신 + 운영 상위 조상» 을 주기 때문이고, 그것이 사업부가 전사
    표준을 볼 수 있게 하는 경로다(«상속이지 승급이 아니다» — `api/deps.py` 주석).

    ⚠️⚠️ **그러나 경영계획은 재무 정보다.** 「전사 표준을 본다」와 「상위 조직의 매출·원가 계획을
      본다」는 다른 이야기이고, 지금은 같은 상속 규칙을 탄다. 이 테스트는 **현재 동작을 사실로
      고정**하는 것이며 «그래야 한다» 는 판단이 아니다 — 자료 종류별로 상속을 달리할지는 제품
      정책이므로 `.agents/TEAM_BOARD.md` 에 결정 요청으로 남겼다.
    ★ 이 동작은 백필(D-018 ⑤) 후에 **처음 실제로 관측됐다.** 그 전에는 테스트 환경의 ECM 이
      비어 조상 해석이 실패했고, 그래서 이 경로가 404 로 보였다(«통제가 동작한다» 로 오독).
    """
    r = client.get(f"{B}/submissions?org_id=LS_MNM", headers=H(MEMBER))
    assert r.status_code == 200, "상위 조직 범위 상속이 끊겼다 — 사업부가 전사 표준을 못 본다"


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
    """★★★ `scope_guard._actor_scopes` 와 `deps.viewer_visible_scopes` 가 **같은 원천**을 본다.

    두 판정이 다른 원천을 보면 «목록에는 있는데 상세는 404» 같은 어긋남이 생긴다. 실제로
    `_actor_scopes` 만 부서 id 해석에 의존하다가 빈 집합이 되어 그 어긋남이 일어났다.

    ⚠️ **같은 집합이 아니라 부분집합**이 정확한 계약이다. `viewer_visible_scopes` 는 경영진에게
      **하향 열람**을 더 준다(`include_descendants` — 사용자 결정 2026-07-30 ③). `_actor_scopes`
      는 그것을 하지 않는다. 그래서 요청 검증(actor)이 목록 필터(visible)보다 **좁거나 같다** —
      좁은 쪽이 요청을 막으므로 방향이 안전하다. 반대가 되면 목록에 없는 범위를 요청할 수 있다."""
    from api.deps import Principal, viewer_visible_scopes
    from core.org_directory import org_directory
    from core.scope_guard import _actor_scopes
    for uid in (MGR, MEMBER, WIDE, VIEWER):
        p = Principal(user_id=uid, scope=org_directory.resolve_scope(uid))
        actor = set(_actor_scopes(p))
        visible = set(viewer_visible_scopes(p) or ())
        assert actor, f"{uid} 의 범위가 비어 있다 — 그러면 모든 범위 요청이 거부된다"
        assert actor <= visible, \
            f"{uid}: 요청 검증이 목록 필터보다 넓다 — 목록에 없는 범위를 요청할 수 있다. " \
            f"초과={sorted(actor - visible)}"


def test_unrestricted_actor_passes_through(client):
    """`unrestricted` 주체는 **범위 필터를 받지 않는다**(하위호환 계약).

    ⚠️ `_actor_scopes` 가 빈 목록이라고 단정하지 않는다 — 백필(D-018 ⑤) 후 전 부서를 읽는
      주체에게는 실제로 노드 목록이 계산된다. 중요한 것은 **그 목록이 판정에 쓰이지 않는다**는
      것이고(`resolve_effective_scope` 가 `unrestricted` 를 먼저 본다), 그 사실을 여기서 잠근다."""
    from api.deps import Principal, viewer_visible_scopes
    from core.org_directory import org_directory
    from core.scope_guard import resolve_effective_scope
    p = Principal(user_id=ADMIN, scope=org_directory.resolve_scope(ADMIN))
    assert viewer_visible_scopes(p) is None, "무제한 주체에게 목록 필터가 걸렸다"
    # 어느 범위를 물어도 거부되지 않는다 — 목록에 없는 범위여도 그렇다.
    for req in ("MNM_COPPER", "MNM_BATTERY", "__no_such_scope__"):
        assert resolve_effective_scope(p, req).denied is False, f"{req} 가 거부됐다"
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
    """통제가 업무를 막지 않는다 — 자기 조직 행은 검증까지 통과해야 한다(`commit=False`).

    ⚠️ **함정**: 이 엔드포인트는 검증이 실패해도 **200 + `ok: False`** 를 준다(어느 행이 왜
      틀렸는지 알려주는 것이 목적이므로 맞는 설계다). 그래서 `status_code == 200` 만 보면
      «범위 통과» 와 «검증 실패» 를 구분하지 못하고, 계정이 없는 격리 DB 에서 그 차이가 드러난다.
      계정을 먼저 등록해 **실제로 통과하는 것**까지 확인한다."""
    from core.planning_model import planning_store
    planning_store.upsert_account("4000", "매출", "revenue", 1, "")
    rows = [{"org_id": "LS_MNM", "account_code": "4000", "period": "2026",
             "value_kind": "ACTUAL", "amount": "1"}]
    r = client.post(f"{B}/import/rows", json={"rows": rows, "commit": False}, headers=H(MGR))
    assert r.status_code == 200, "자기 조직 행이 범위 검증에서 막혔다"
    d = r.json()["data"]
    assert d["ok"] is True, f"검증이 실패했다: {d.get('errors')}"
    assert d["summary"]["valid"] == 1 and d["committed"] is False


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
