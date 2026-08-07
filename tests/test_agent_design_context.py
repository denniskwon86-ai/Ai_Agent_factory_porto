"""[D-017 §9 P2-3] AI 추천 입력에 조직 문맥을 넣는다 — **모르면 «없음» 이라고 말하지 않는다.**

## 왜 이 구분이 핵심인가

LLM 은 «빈 목록» 과 «모름» 을 구분하지 못한다. 프롬프트에 「사용할 수 있는 도구가 없습니다」라고
쓰면 모델은 **도구 없이 설계**하거나 **도구를 지어낸다.** 둘 다 조용히 틀리고, 틀린 결과는
실행 단계(P3-3 도구 권한 교집합)에 가서야 드러난다. 그때 사용자가 보는 것은 「AI 가 추천한
대로 했는데 안 된다」뿐이다.

그래서 세 상태를 **문장으로** 구분한다:

    []      확인했고 정말 없다   → 「확인했고, 등록된 것이 없습니다.」
    [...]   확인했고 이것들이 있다
    None    확인하지 못했다      → 「확인하지 못했습니다 — …」

이 저장소의 «조회 실패 ≠ 0건» 을 프롬프트에 적용한 것이다.
"""
import pytest

from core import agent_design_context as adc


# ── ① 세 상태가 다른 문장으로 나온다 ────────────────────────────────────────
def test_unknown_is_not_reported_as_empty():
    """★★ `None`(모름)과 `[]`(없음)이 **다른 문장**이어야 한다."""
    unknown = adc.to_prompt(adc.DesignContext(scope_node_id="X", connectors=None,
                                              data_assets=[], knowledge_packs=[]))
    assert "확인하지 못했습니다" in unknown
    empty = adc.to_prompt(adc.DesignContext(scope_node_id="X", connectors=[],
                                            data_assets=[], knowledge_packs=[]))
    assert "확인하지 못했습니다" not in empty
    assert "등록된 것이 없습니다" in empty
    assert unknown != empty, "모름과 없음이 같은 문장으로 나간다"


def test_items_are_listed_with_ids():
    """모델이 **그대로 인용할 수 있는 id** 가 들어가야 한다 — 이름만 주면 지어낸다."""
    out = adc.to_prompt(adc.DesignContext(
        scope_node_id="X",
        connectors=[{"id": "erp_main", "name": "ERP", "kind": "sql", "access": "read"}],
        data_assets=[{"id": "REF-A", "name": "표준 자산", "kind": "pdf"}],
        knowledge_packs=["pack_a"]))
    assert "erp_main" in out and "REF-A" in out and "pack_a" in out


def test_empty_context_produces_nothing():
    """★ 아무것도 모르면서 「없습니다」라고 쓰지 않는다 — 빈 문자열을 돌려준다.

    ⚠️ 이 경우에 「도구가 없습니다」를 내보내면 모델을 «도구 없는 설계» 로 몰아간다."""
    assert adc.to_prompt(adc.DesignContext()) == ""


# ── ② 수집기의 import 가 실제로 풀린다 ──────────────────────────────────────
@pytest.mark.parametrize("fn,label", [
    (adc._connectors, "커넥터"),
    (adc._assets, "참조 데이터"),
    (adc._packs, "지식팩"),
])
def test_collector_imports_resolve(fn, label):
    """★★★ [2026-08-07 실제 결함] **모듈 이름을 잘못 적으면 «확인하지 못함» 으로 위장된다.**

    처음에 `core.knowledge_hub` 라고 썼는데 그런 모듈은 없다(정본은 `core.knowledge_base`).
    `_safe` 가 그 `ImportError` 를 삼켜 프롬프트에는 「지식 허브를 읽지 못했습니다」가 나갔다 —
    **틀린 이유를 그럴듯하게 말하는** 상태이고, 그런 오류는 아무도 고치지 않는다(저장소가
    잠깐 안 읽혔나 보다로 읽힌다).

    → 여기서는 `_safe` 를 거치지 **않고** 직접 부른다. import 가 안 풀리면 그대로 터진다."""
    import inspect
    n = len(inspect.signature(fn).parameters)
    fn(*([""] * (n - 1) + [False]) if n > 1 else [""])   # 값이 아니라 «부를 수 있는가» 를 본다


def test_safe_marks_programming_errors_but_keeps_going(capsys):
    """`_safe` 는 버그를 **소리내어** 넘긴다 — 조용히 넘기면 위 결함이 반복된다."""
    def boom():
        raise AttributeError("no such attribute")

    assert adc._safe(boom) is None
    assert "수집기 버그" in capsys.readouterr().out


# ── ③ 비활성 커넥터를 «쓸 수 있는 도구» 로 내보내지 않는다 ──────────────────
def test_inactive_connectors_are_excluded(monkeypatch):
    """⚠️ 계약을 통과해도 비활성 커넥터는 조회가 실패한다 — 도구 목록에 넣으면 설계가 거짓이 된다."""
    from core.connector_registry import connector_registry
    monkeypatch.setattr(connector_registry, "list_connectors", lambda **kw: [
        {"connector_id": "a", "name": "A", "kind": "sql", "status": "active"},
        {"connector_id": "b", "name": "B", "kind": "sql", "status": "draft"},
    ])
    rows = adc._connectors("X", "", "REAL", "", False)
    assert [r["id"] for r in rows] == ["a"]


# ── ④ 라우트가 실제로 이 블록을 붙이는가 ────────────────────────────────────
def test_route_prepends_context_block():
    """★ 문맥 모듈만 초록이고 라우트가 안 쓰면 아무것도 달라지지 않는다.

    ⚠️ 실제로 호출하면 **LLM 비용이 나간다**(2026-08-07 에 탐침이 그렇게 Gemini 를 태웠다).
      그래서 호출하지 않고 **소스에 배선이 있는지**만 본다."""
    import inspect

    import api.routes.factory_control as fc
    src = inspect.getsource(fc.ai_recommend_pipeline)
    assert "_collect_design_ctx" in src, "문맥을 모으지 않는다"
    assert "_ctx_block + prompt" in src, "모아 놓고 프롬프트에 붙이지 않는다"
    assert src.count("_ctx_block + prompt") == 1, (
        "문맥을 두 곳에서 붙이고 있다 — 한쪽만 고쳐지는 날이 온다")
