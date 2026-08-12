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
