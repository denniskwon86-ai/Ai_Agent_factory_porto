"""★★★ [G1-C3] 통합 가시성 판정기 — **권한 축과 문맥 축을 나누고 AND 로 묶는다.**

    최종 가시성 = authorization_visible(권한)  AND  context_visible(지금 고른 문맥)

## 왜 나누는가

둘을 한 함수에 섞으면 **어느 쪽 때문에 안 보이는지 말할 수 없다.** 그러면 화면은 «0건» 만
보여 주고, 사용자는 자료가 없는 것인지 권한이 없는 것인지 문맥이 어긋난 것인지 알 수 없다.
사유를 함께 돌려주는 것이 이 설계의 요점이다.

## D-014 — 「범위 미지정은 전사 공용이 아니라 비노출」

종전 문맥 비교는 **빈 값이 모든 검사를 통과**했다. 자원의 테넌트가 비면 통과, 실행 모드가
비면 통과, 범위가 비면 `scope_covers` 가 `True`. 즉 «미지정 = 전사 공용» 이었고, 그것이
D-014 가 명시적으로 금지한 상태다. 여기서는 전부 비노출이다.
"""
import pytest

import core.project_visibility as pv


class _Scope:
    def __init__(self, depts=(), unrestricted=False, is_admin=False):
        self.readable_dept_ids = frozenset(depts)
        self.unrestricted = unrestricted
        self.is_admin = is_admin


def _own(**kw):
    base = {"tenant_id": "T1", "entity_mode": "REAL", "enterprise_scope_id": "node_child",
            "owner_dept_id": "D1", "owner_user_id": "a@x", "visibility": "dept"}
    base.update(kw)
    base["binding_state"] = pv._classify(base)
    return base


def _ctx(**kw):
    base = {"tenant_id": "T1", "entity_mode": "REAL", "scope_node_id": ""}
    base.update(kw)
    return base


# ── 문맥 축: 무엇이 통과하고 무엇이 막히는가 ──────────────────────────────

@pytest.mark.parametrize("ctx,own,expect_ok,expect_reason", [
    (_ctx(), _own(), True, pv.CTX_OK),
    (_ctx(tenant_id="T2"), _own(), False, pv.CTX_TENANT_MISMATCH),
    (_ctx(entity_mode="VIRTUAL"), _own(), False, pv.CTX_MODE_MISMATCH),
    (_ctx(entity_mode="SANDBOX"), _own(entity_mode="SANDBOX"), True, pv.CTX_OK),
    (_ctx(), _own(tenant_id=""), False, pv.CTX_RESOURCE_UNBOUND),
    (_ctx(), _own(entity_mode=""), False, pv.CTX_RESOURCE_UNBOUND),
    (_ctx(), _own(enterprise_scope_id=""), False, pv.CTX_RESOURCE_UNBOUND),
    (_ctx(tenant_id=""), _own(), False, pv.CTX_CONTEXT_MISSING),
    (_ctx(entity_mode=""), _own(), False, pv.CTX_CONTEXT_MISSING),
    ({}, _own(), False, pv.CTX_CONTEXT_MISSING),
    (_ctx(scope_node_id="node_child"), _own(), True, pv.CTX_OK),
])
def test_문맥_판정_표(ctx, own, expect_ok, expect_reason):
    ok, why = pv.context_visible(ctx, own)
    assert (ok, why) == (expect_ok, expect_reason)


def test_자원_문맥이_비면_전사공개여도_막힌다():
    """★★★ D-014 — 「미지정은 전사 공용이 아니라 비노출」.

    ⚠️ `visibility="company"` 는 **전 세계 공개가 아니라** 같은 테넌트·같은 모드 안에서의
      공개다. 문맥이 없는 자원에 company 를 붙여도 경계를 넘지 못한다."""
    ok, why = pv.context_visible(_ctx(), _own(visibility="company", tenant_id=""))
    assert not ok and why == pv.CTX_RESOURCE_UNBOUND


def test_전사공개도_다른_테넌트로는_넘어가지_않는다():
    ok, why = pv.context_visible(_ctx(tenant_id="T2"), _own(visibility="company"))
    assert not ok and why == pv.CTX_TENANT_MISMATCH


@pytest.mark.parametrize("own", [None, {}, [], "", 0])
def test_자원_정보_자체가_없으면_판정하지_않고_막는다(own):
    """★★ [변이 검사로 드러난 구멍 · 2026-08-12] 이 경우를 **아무 테스트도 보지 않았다.**

    ⚠️ 「자원 정보 없음」 차단을 통째로 지워도 21건이 전부 초록이었다. 즉 그 줄은 **테스트가
      지키지 않는 코드**였다. 실제로 지우면 `own.get` 이 `AttributeError` 를 내는데, 예외를
      삼키는 호출부에서는 그것이 곧 «판정 실패 = 통과» 가 된다 — `ownership_visible` 이
      1차 구현에서 정확히 그렇게 틀렸다.

    ★ 배선 후에는 `context_visible` 이 **단독으로도** 불린다(목록은 권한 축을 먼저 거르지만,
      사유별 집계는 문맥 축만 따로 센다). 그러므로 이 함수는 혼자서도 안전해야 한다."""
    ok, why = pv.context_visible(_ctx(), own)
    assert not ok and why == pv.CTX_RESOURCE_UNBOUND


# ── 조직 계층: 위에서 아래는 보이고, 아래에서 위·형제는 안 보인다 ──────────

def _fake_parents(monkeypatch, edges):
    """`node → 부모목록` 을 세운다. ECM 조회를 대신한다."""
    class _Repo:
        @staticmethod
        def parents(node, rel):
            return edges.get(node, [])
    import core.project_visibility as m
    monkeypatch.setattr(m, "_scope_is_ancestor",
                        lambda a, n: _walk(edges, a, n), raising=True)


def _walk(edges, ancestor, node, depth=8):
    seen, frontier = {node}, [node]
    for _ in range(depth):
        nxt = []
        for n in frontier:
            for p in edges.get(n, []):
                if p == ancestor:
                    return True, False
                if p not in seen:
                    seen.add(p); nxt.append(p)
        if not nxt:
            break
        frontier = nxt
    return False, False


def test_상위_조직에서_하위_조직이_보인다(monkeypatch):
    _fake_parents(monkeypatch, {"node_child": ["node_parent"]})
    ok, why = pv.context_visible(_ctx(scope_node_id="node_parent"), _own())
    assert ok and why == pv.CTX_OK


def test_하위에서_상위와_형제는_보이지_않는다(monkeypatch):
    _fake_parents(monkeypatch, {"node_child": ["node_parent"], "node_sib": ["node_parent"]})
    ok, why = pv.context_visible(_ctx(scope_node_id="node_child"),
                                 _own(enterprise_scope_id="node_parent"))
    assert not ok and why == pv.CTX_SCOPE_OUTSIDE
    ok2, why2 = pv.context_visible(_ctx(scope_node_id="node_child"),
                                   _own(enterprise_scope_id="node_sib"))
    assert not ok2 and why2 == pv.CTX_SCOPE_OUTSIDE


def test_ECM_판독_실패는_비노출이고_점검_대상으로_구분된다(monkeypatch):
    """⚠️ 조회 실패를 «맞다» 로도 «아니다» 로도 뭉개지 않는다 — 화면이 「문맥 점검 필요」를
    따로 말할 수 있어야 한다. 종전 `scope_covers` 는 실패를 **통과**시켰다."""
    import core.project_visibility as m
    monkeypatch.setattr(m, "_scope_is_ancestor", lambda a, n: (False, True))
    ok, why = pv.context_visible(_ctx(scope_node_id="node_parent"), _own())
    assert not ok and why == pv.CTX_LOOKUP_FAILED


# ── 두 축의 AND 결합 ──────────────────────────────────────────────────────

def test_권한이_있어도_문맥이_다르면_안_보인다():
    ok, why = pv.project_visible(_Scope({"D1"}), "a@x", _ctx(tenant_id="T2"), _own())
    assert not ok and why == pv.CTX_TENANT_MISMATCH


def test_문맥이_맞아도_권한이_없으면_안_보인다():
    ok, why = pv.project_visible(_Scope({"D9"}), "z@x", _ctx(), _own())
    assert not ok and why == "UNAUTHORIZED"


def test_둘_다_맞으면_보인다():
    assert pv.project_visible(_Scope({"D1"}), "z@x", _ctx(), _own()) == (True, pv.CTX_OK)


def test_사유가_구분된다():
    """★ 화면이 「없음」·「접근 불가」·「문맥 점검 필요」를 다르게 말할 수 있어야 한다.

    한 가지 `False` 로 뭉개면 사용자는 통제를 고장으로 읽고, 개발자는 원인을 못 찾는다."""
    reasons = {
        pv.project_visible(_Scope({"D9"}), "z@x", _ctx(), _own())[1],
        pv.project_visible(_Scope({"D1"}), "a@x", _ctx(tenant_id="T2"), _own())[1],
        pv.project_visible(_Scope({"D1"}), "a@x", _ctx(entity_mode="VIRTUAL"), _own())[1],
        pv.project_visible(_Scope({"D1"}), "a@x", _ctx(), _own(enterprise_scope_id=""))[1],
    }
    assert len(reasons) == 4, f"사유가 겹친다: {reasons}"


# ── 무제한 권한자도 문맥은 지킨다 ──────────────────────────────────────────

def test_무제한_권한자도_다른_테넌트는_못_본다():
    """★★ 권한이 무제한이어도 **지금 고른 문맥**은 좁힌다. 「전권」과 「지금 보는 범위」는
    다른 축이다 — 섞으면 관리자 화면에 다른 회사 자료가 섞인다."""
    ok, why = pv.project_visible(_Scope(unrestricted=True), "boss@x",
                                 _ctx(tenant_id="T2"), _own())
    assert not ok and why == pv.CTX_TENANT_MISMATCH


# ── 문맥 정규화: 「지금 무엇을 보기로 했는가」를 확정하는 단일 지점 ──────────
#
# ★★★ [G1-C3 · 2026-08-13] 이 계산은 원래 `auth_control._subscription_context` 안에 있었고
#   **SSE 티켓만** 썼다. HTTP 라우트는 문맥을 아예 보지 않았고, 그 비대칭이 G1-C3 가 고치려는
#   결함 자체다. 두 경로가 같은 함수를 부르는지를 여기서 잠근다.

class _FakeScope:
    def __init__(self, nodes=(), unrestricted=False, primary_dept_id=""):
        self.readable_scope_nodes = frozenset(nodes)
        self.unrestricted = unrestricted
        self.primary_dept_id = primary_dept_id


def _wire(monkeypatch, scope, *, tenant="tenant_default", modes=None, dept_node=None):
    """`resolve_viewing_context` 가 지연 임포트하는 세 곳을 갈아끼운다."""
    import config
    from core.enterprise_context import repository as repo_mod
    from core import org_directory as od_mod
    monkeypatch.setattr(config, "ECM_DEFAULT_TENANT_ID", tenant, raising=False)
    monkeypatch.setattr(od_mod.org_directory, "resolve_scope", lambda uid: scope, raising=False)
    monkeypatch.setattr(repo_mod.ecm_repository, "node_entity_mode",
                        lambda nid: (modes or {}).get(nid, ""), raising=False)
    # 부서→노드 해석이 **불려서는 안 된다**는 것을 감시한다(아래 테스트가 이것을 확인한다).
    called = []

    def _spy(dept):
        called.append(dept)
        return type("N", (), {"node_id": dept_node})() if dept_node else None

    monkeypatch.setattr(repo_mod.ecm_repository, "find_node_by_dept", _spy, raising=False)
    return called


def test_고르지_않으면_주부서로_좁히지_않는다(monkeypatch):
    """★★★ [2026-08-13 실측으로 바꾼 규칙] 사용자가 **고른 적 없는** 범위로 좁히지 않는다.

    실측: 관리자의 주 부서 `hq` → `MNM_SHARED`(전사공통 노드). 그런데 `smart-life-app` 은 그
    **상위 법인**(`LS_MNM`) 소속이라, 부서로 좁히는 순간 관리자에게서 `SCOPE_OUTSIDE` 로
    사라졌다. 사용자는 그 범위를 고른 적이 없다 — 서버가 추측한 값 때문에 자료가 사라지면
    그것은 통제가 아니라 **고장**으로 읽힌다.

    ⚠️ 넓어지지 않는다. 권한 경계는 `authorization_visible` 이 따로 지키고, 여기서 남는 것은
      「같은 테넌트·같은 실행 모드 안에서 권한이 닿는 만큼」이다."""
    called = _wire(monkeypatch, _FakeScope(primary_dept_id="hq"), dept_node="node_shared")
    ctx = pv.resolve_viewing_context("a@x", "")
    assert ctx["scope_node_id"] == "", "고른 적 없는 범위로 좁혔다"
    assert ctx["entity_mode"] == "REAL" and ctx["tenant_id"] == "tenant_default"
    assert called == [], f"부서→노드 추측을 되살렸다: {called}"


def test_고를_수_없는_범위는_거부한다(monkeypatch):
    """조용히 기본값으로 바꾸지 않는다 — 바꾸면 사용자는 A 를 골랐다고 믿으며 B 를 본다."""
    _wire(monkeypatch, _FakeScope(nodes={"node_ok"}))
    with pytest.raises(pv.ViewingScopeDenied):
        pv.resolve_viewing_context("a@x", "node_other")


def test_고른_범위가_권한_안이면_통과하고_모드는_노드가_정한다(monkeypatch):
    """⚠️ 실행 모드를 **요청이 정하게 두지 않는다.** 그러면 가상 자료를 실제 문맥으로 끌어온다."""
    _wire(monkeypatch, _FakeScope(nodes={"node_v"}), modes={"node_v": "VIRTUAL"})
    ctx = pv.resolve_viewing_context("a@x", "node_v")
    assert ctx["scope_node_id"] == "node_v" and ctx["entity_mode"] == "VIRTUAL"


def test_무제한_권한자는_어떤_노드든_고를_수_있다(monkeypatch):
    _wire(monkeypatch, _FakeScope(unrestricted=True), modes={"node_x": "REAL"})
    assert pv.resolve_viewing_context("boss@x", "node_x")["scope_node_id"] == "node_x"


def test_테넌트를_확정_못하면_빈_문맥으로_넘어가지_않는다(monkeypatch):
    """⚠️ 빈 문맥은 `context_visible` 이 전부 차단한다 — 사용자에게는 「고장」으로 보인다.
    확정하지 못했다는 사실을 그대로 말하는 편이 낫다(503)."""
    _wire(monkeypatch, _FakeScope(unrestricted=True), tenant="")
    with pytest.raises(pv.ViewingContextUnavailable):
        pv.resolve_viewing_context("boss@x", "")


def test_SSE_티켓과_HTTP_가_같은_함수를_쓴다(monkeypatch):
    """★★ 두 경로가 갈라지면 「목록에는 보이는데 이벤트는 안 오는」 상태가 다시 생긴다.
    `auth_control._subscription_context` 는 예외 종류만 바꾸는 껍데기여야 한다."""
    from api.routes import auth_control as ac
    _wire(monkeypatch, _FakeScope(nodes={"node_ok"}), modes={"node_ok": "REAL"})
    assert ac._subscription_context("a@x", "node_ok") == pv.resolve_viewing_context("a@x", "node_ok")
    with pytest.raises(PermissionError):
        ac._subscription_context("a@x", "node_nope")
