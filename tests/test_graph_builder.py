"""build_graph_from_registry 동등성 — (b)-1 동작 보존 검증.

레지스트리 구동 빌더가 기존 하드코딩 그래프와 동일한 노드 집합·interrupt_after 를 산출하는지
(DEFAULT_REGISTRY 기준) 확인한다. 라우터 동작 동등성은 tests/test_routers.py 가 담당.
"""
import core.agent_graph as ag
from core.agent_registry import DEFAULT_REGISTRY

EXPECTED_NODES = {
    "RFP_Analyst", "Master_PM", "Master_PMO", "Architect", "Tech_Lead",
    "Backend", "Frontend", "CodeBuilder", "Reviewer", "QA", "ManualWriter",
}


def test_node_impl_covers_all_registry_ids():
    reg_ids = {a["id"] for a in DEFAULT_REGISTRY["agents"]}
    assert reg_ids <= set(ag.NODE_IMPL.keys()), "NODE_IMPL 이 레지스트리 일부 id 를 누락"


def test_builder_default_node_set_matches():
    wf, _ = ag.build_graph_from_registry(DEFAULT_REGISTRY)
    compiled = wf.compile()
    names = set(compiled.get_graph().nodes.keys())
    assert EXPECTED_NODES <= names


def test_builder_interrupt_after_default():
    _, interrupt_after = ag.build_graph_from_registry(DEFAULT_REGISTRY)
    assert interrupt_after == ["RFP_Analyst", "Master_PMO"]


def test_builder_equivalent_to_create_factory_graph():
    # 동등성: 빌더 산출 토폴로지의 노드 집합 == 기존 create_factory_graph 의 노드 집합
    wf, ia = ag.build_graph_from_registry(DEFAULT_REGISTRY)
    built = wf.compile(interrupt_after=ia)
    ref = ag.create_factory_graph()
    assert set(built.get_graph().nodes.keys()) == set(ref.get_graph().nodes.keys())


def test_build_workflow_delegates_to_registry_builder():
    # create_factory_graph/_build_runtime_app 이 쓰는 _build_workflow 가 빌더 경로를 통하는지
    wf, ia = ag._build_workflow()
    assert ia == ["RFP_Analyst", "Master_PMO"]
    assert EXPECTED_NODES <= set(wf.compile().get_graph().nodes.keys())
