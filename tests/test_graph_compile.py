"""그래프 compile 스모크 — Phase 2 최빈 실패(엣지 타깃 미정의/dangling)를 컴파일 단계에서 포착."""
import core.agent_graph as ag
from core.agent_registry import DEFAULT_REGISTRY


def test_create_factory_graph_compiles():
    app = ag.create_factory_graph()
    assert app is not None
    assert type(app).__name__ == "CompiledStateGraph"


def test_compiled_graph_has_all_registry_nodes():
    app = ag.create_factory_graph()
    names = set(app.get_graph().nodes.keys())
    for a in DEFAULT_REGISTRY["agents"]:
        assert a["id"] in names, f"compiled 그래프에 노드 누락: {a['id']}"
