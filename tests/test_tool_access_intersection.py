"""[D-017 §9 P3-3] 도구 호출 권한 **교집합** 강제.

## 봉합 전 실측 결함

`POST /api/v1/connectors/{id}/execute` 는 요청자 식별과 `admin.data_access` 만 봤고,
**그 커넥터가 요청자 조직의 것인지는 보지 않았다.** 즉 A 부서 데이터 관리자가 B 부서
커넥터로 조회를 실행할 수 있었다.

⚠️ 목록(`GET /connectors`)에서는 B 부서 커넥터가 보이지 않는다. 그래서 «통제되고 있다» 로
  보였다 — **목록만 막고 실행을 열어 두면 id 를 아는 사람 앞에서 통제는 없다.**
  이 저장소가 여러 번 확인한 형태이고, 크로스워크는 같은 문제를 `_gate` 하나로 막았다.

## 어디서 막는가 — 라우트가 아니라 실행 지점

`connector_execution.execute()` 가 **모든 조회의 목**이다. 라우트에만 두면 실행 경로가 하나
더 생기는 순간(에이전트 런타임·배치·스크립트) 그 경로만 통제 없이 돈다.

★ 그리고 `fetch_for_prompt` 도 같은 게이트를 지나야 한다. 그쪽 결과는 **프롬프트로 들어가고**,
  프롬프트 유출은 화면 유출보다 찾기 어렵다.
"""
import pytest

from core.connector_registry import ConnectorError


class _Reg:
    """`list_connectors` 의 범위 필터만 흉내 내는 최소 대역.

    ⚠️ 판정 로직을 여기서 다시 쓰지 않는다 — 「어느 커넥터가 어느 조직 것인가」만 주고,
      **가시성 판정은 실제 `connector_registry` 메서드**가 하게 둔다."""

    OWNER = {"erp_a": "DEPT_A", "erp_b": "DEPT_B"}

    def get(self, cid):
        # ⚠️ `owner_organization_id` 를 빠뜨리면 `scope_allows_owner` 가 «소유 미기재 = 안 보임»
        #   으로 판정해 **모든 커넥터가 막힌다.** 대역이 실물과 다른 모양이면 테스트가 제품이
        #   아니라 대역을 검사하게 된다.
        return ({"connector_id": cid, "owner_organization_id": self.OWNER[cid]}
                if cid in self.OWNER else None)

    def list_connectors(self, scope_node_id="", tenant_id="", entity_mode="REAL", **kw):
        rows = [{"connector_id": c, "owner_organization_id": o} for c, o in self.OWNER.items()]
        if not (scope_node_id or tenant_id):
            return rows
        return [r for r in rows if r["owner_organization_id"] == scope_node_id]

    # 실제 구현을 빌려 쓴다 — 대역이 판정을 흉내 내면 그 흉내가 진짜와 갈라진다.
    from core.connector_registry import ConnectorRegistry as _C
    is_connector_visible = _C.is_connector_visible
    visible_to_actor = _C.visible_to_actor
    require_connector_visible = _C.require_connector_visible


def test_visible_within_own_scope():
    r = _Reg()
    assert r.is_connector_visible("erp_a", scope_node_id="DEPT_A")
    r.require_connector_visible("erp_a", scope_node_id="DEPT_A")   # 통과해야


def test_other_department_connector_is_denied():
    """★★★ 봉합 전에는 이것이 실행됐다."""
    r = _Reg()
    assert not r.is_connector_visible("erp_b", scope_node_id="DEPT_A")
    with pytest.raises(ConnectorError) as e:
        r.require_connector_visible("erp_b", scope_node_id="DEPT_A")
    # ⚠️ 존재 여부를 알려주지 않는다 — 「없거나 권한이 없다」로 뭉뚱그린다.
    assert "존재하지 않거나 접근 권한이 없는" in str(e.value)


def test_unknown_connector_uses_the_same_wording():
    """존재하지 않는 id 와 남의 조직 id 가 **같은 문구**여야 한다.

    ⚠️ 문구가 다르면 그 차이만으로 어느 id 가 실재하는지 알아낼 수 있다."""
    r = _Reg()
    with pytest.raises(ConnectorError) as e1:
        r.require_connector_visible("erp_b", scope_node_id="DEPT_A")
    with pytest.raises(ConnectorError) as e2:
        r.require_connector_visible("nope", scope_node_id="DEPT_A")
    assert str(e1.value).replace("erp_b", "X") == str(e2.value).replace("nope", "X")


def test_no_scope_declared_keeps_legacy_flow():
    """범위를 선언하지 않으면 필터하지 않는다 — ECM 미도입 흐름 보존(전 저장소 규약).

    ⚠️ 다만 그 사실이 응답에 남아야 한다(아래 `scope_checked`)."""
    r = _Reg()
    assert r.is_connector_visible("erp_b")            # 범위 미지정 → 통과
    assert not r.is_connector_visible("nope")         # 없는 것은 여전히 없다


# ── 실행 지점이 실제로 막는가 ───────────────────────────────────────────────
def test_execute_denies_other_scope_before_contract_check():
    """★★ 계약 검증 **전에** 막아야 한다.

    남의 조직 커넥터에 「그 쿼리는 계약에 없습니다」라고 답하면 그 자체가 존재를 알려 준다."""
    from core.connector_execution import execute
    r = _Reg()
    with pytest.raises(ConnectorError):
        execute("erp_b", "q", ["f"], actor="u@x", purpose="확인",
                registry=r, scope_node_id="DEPT_A")


def test_scope_checked_is_reported(monkeypatch):
    """★ 「통제가 있었다」와 「범위를 안 줘서 통과했다」를 구분한다.

    ⚠️ `scope_checked=False` 를 «안전» 으로 읽으면 안 된다 — 판정을 **하지 않았다**는 뜻이다."""
    import inspect

    from core import connector_execution as ce
    src = inspect.getsource(ce.execute)
    assert '"scope_checked": _scope_checked' in src
    assert "actor_scopes is not None" in src, (
        "게이트가 선언 범위에만 반응한다 — 라우트가 빈 값을 넘기면 영원히 잠든다")


def test_prompt_path_forwards_the_gate():
    """★★★ `fetch_for_prompt` 가 범위를 그대로 넘겨야 한다.

    ⚠️ 여기가 빠지면 조회 결과가 **프롬프트로** 들어간다. 프롬프트 유출은 화면 유출보다 찾기
      어렵다 — 산출물에 남은 값을 역추적하지 않는 한 아무도 모른다."""
    import inspect

    from core import connector_execution as ce
    sig = inspect.signature(ce.fetch_for_prompt).parameters
    for k in ("scope_node_id", "tenant_id", "entity_mode", "actor_scopes"):
        assert k in sig, f"fetch_for_prompt 가 {k} 를 받지 않는다"
    src = inspect.getsource(ce.fetch_for_prompt)
    assert "scope_node_id=scope_node_id" in src, "받기만 하고 넘기지 않는다"


def test_route_takes_scope_from_the_requester_not_the_body():
    """★★ 범위를 **요청 본문에서** 받으면 호출자가 아무 범위나 적어 통과시킨다.

    통제를 호출자 선택으로 두면 통제가 아니다 — `deps.visibility_block_reason` 주석이
    같은 경고를 적어 두었다(지식팩 유출의 원인이 그것이었다)."""
    import inspect

    import api.routes.connector_control as cc
    src = inspect.getsource(cc.execute_query)
    assert "viewer_scope_nodes(p)" in src, "요청자에게서 범위를 얻지 않는다"
    assert "req.scope_node_id" not in src, "요청 본문의 범위를 그대로 쓰고 있다"


# ── 교집합의 두 축 ──────────────────────────────────────────────────────────
def test_actor_scope_axis_blocks_even_without_declared_context():
    """★★★ [2026-08-07 실측 결함] **선언된 범위가 비어도 막아야 한다.**

    처음 구현은 `bool(scope_node_id or tenant_id)` 일 때만 게이트를 켰다. 그런데 라우트가
    넘기는 값은 `assert_scope_allowed(p, "")` 의 결과였고, 그 함수는 **빈 요청을 «전사
    요청» 으로 보고 빈 문자열을 돌려준다** — 무제한 계정이든 부서 계정이든 똑같이 `''` 였다.
    그래서 게이트가 **한 번도 물지 않았다.** 단위 테스트는 초록이었고(범위를 직접 넣어
    호출했으므로), 살아 있는 서버에서 다른 조직 범위로 호출해도 같은 응답이 나와 드러났다.

    ⚠️ 「파라미터를 주지 않는 것이 가장 넓은 조회」 — 이 저장소가 반복해서 만난 함정이다."""
    r = _Reg()
    # 선언 범위 없음 + 요청자는 DEPT_A 만 본다 → B 부서 커넥터는 막혀야 한다.
    with pytest.raises(ConnectorError):
        r.require_connector_visible("erp_b", actor_scopes=frozenset({"DEPT_A"}))
    r.require_connector_visible("erp_a", actor_scopes=frozenset({"DEPT_A"}))   # 통과


def test_unrestricted_actor_is_none_not_empty_set():
    """`None`(제한 없음)과 `frozenset()`(볼 수 있는 것이 없음)은 다르다.

    ⚠️ 빈 집합을 «제한 없음» 으로 읽으면 부서가 없는 계정이 전사를 본다."""
    r = _Reg()
    r.require_connector_visible("erp_b", actor_scopes=None)          # 무제한 — 통과
    with pytest.raises(ConnectorError):
        r.require_connector_visible("erp_b", actor_scopes=frozenset())


def test_execute_gate_fires_on_actor_scopes_alone():
    """실행 지점도 «요청자 범위만» 으로 켜져야 한다."""
    import inspect

    from core import connector_execution as ce
    src = inspect.getsource(ce.execute)
    assert "actor_scopes is not None" in src, (
        "게이트가 선언 범위에만 반응한다 — 라우트가 빈 값을 넘기면 영원히 잠든다")


def test_route_uses_viewer_scope_nodes_not_requested_scope():
    """★ 라우트는 `_scope(p, "")` 이 아니라 `viewer_scope_nodes(p)` 를 써야 한다."""
    import inspect

    import api.routes.connector_control as cc
    src = inspect.getsource(cc.execute_query)
    assert "viewer_scope_nodes(p)" in src
    # ⚠️ 주석에도 그 문자열이 나온다(왜 쓰면 안 되는지를 적어 두었다). **코드로 쓰였는지**를 본다.
    assert 'await _scope(p, "")' not in src, (
        "빈 요청 범위를 쓰고 있다 — 그 값은 누구에게나 빈 문자열이라 게이트가 잠든다")
