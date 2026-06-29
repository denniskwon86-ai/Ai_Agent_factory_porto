"""레지스트리 ↔ 그래프 노드 정합성 — Phase 2 동적 빌더의 핵심 불변식 가드.

agent_graph.py 를 import 하지 않고(게이트웨이 네트워크 호출 회피) 소스를 정적 파싱해
add_node 이름 집합과 DEFAULT_REGISTRY id 집합이 1:1인지 검사한다.
"""
import os
import re
from core.agent_registry import DEFAULT_REGISTRY, get_interrupt_after

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _graph_node_names():
    src = open(os.path.join(ROOT, "core", "agent_graph.py"), encoding="utf-8").read()
    return set(re.findall(r'add_node\(\s*"([^"]+)"', src))


def test_every_registry_id_is_a_graph_node():
    nodes = _graph_node_names()
    reg_ids = {a["id"] for a in DEFAULT_REGISTRY["agents"]}
    missing = reg_ids - nodes
    assert not missing, f"레지스트리 id가 그래프 노드에 없음: {missing}"


def test_every_graph_node_is_in_registry():
    nodes = _graph_node_names()
    reg_ids = {a["id"] for a in DEFAULT_REGISTRY["agents"]}
    missing = nodes - reg_ids
    assert not missing, f"그래프 노드가 레지스트리에 없음: {missing}"


def test_interrupt_after_ids_are_valid_graph_nodes():
    nodes = _graph_node_names()
    for nid in get_interrupt_after(default=["RFP_Analyst", "Master_PMO", "Tech_Lead"]):
        assert nid in nodes, f"interrupt_after id가 그래프 노드 아님: {nid}"


def test_every_rubric_has_threshold_ssot():
    # 통과 임계는 criteria.py rubric 이 단일 진실원천 — 모든 rubric에 pass_threshold 존재해야
    from criteria import STAGE_RUBRICS
    for stage, rubric in STAGE_RUBRICS.items():
        assert "pass_threshold" in rubric, f"{stage} rubric 에 pass_threshold 없음"
        assert 0.0 < rubric["pass_threshold"] <= 1.0
        assert "checks" in rubric and rubric["checks"], f"{stage} rubric 에 checks 없음"


def test_config_no_longer_defines_duplicate_threshold():
    # SSOT 단일화 회귀 방지 — config 에 STAGE_PASS_THRESHOLDS 가 되살아나지 않도록
    import config
    assert not hasattr(config, "STAGE_PASS_THRESHOLDS"), "threshold SSOT 중복 부활 — criteria.py 로 단일화 유지할 것"
