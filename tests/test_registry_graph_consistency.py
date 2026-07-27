"""레지스트리 ↔ 그래프 노드 정합성 — Phase 2 동적 빌더의 핵심 불변식 가드.

(b)-1 이후 노드 멤버십 SSOT 는 NODE_IMPL(레지스트리 id → 노드 함수, 동적 빌더가 사용)이다.
지연 게이트웨이 seam 덕분에 agent_graph import 가 ~2s 라 직접 import 해 검증한다.
"""
import core.agent_graph as ag
from core.agent_registry import DEFAULT_REGISTRY, get_interrupt_after


def _graph_node_names():
    # 노드 멤버십 SSOT = NODE_IMPL (build_graph_from_registry 가 이 매핑으로 노드를 생성)
    return set(ag.NODE_IMPL.keys())


def test_every_registry_id_is_a_graph_node():
    nodes = _graph_node_names()
    reg_ids = {a["id"] for a in DEFAULT_REGISTRY["agents"]}
    missing = reg_ids - nodes
    assert not missing, f"레지스트리 id가 NODE_IMPL 에 없음(동적 빌더가 노드 생성 불가): {missing}"


def test_every_graph_node_is_in_registry():
    nodes = _graph_node_names()
    reg_ids = {a["id"] for a in DEFAULT_REGISTRY["agents"]}
    missing = nodes - reg_ids
    assert not missing, f"NODE_IMPL 노드가 레지스트리에 없음: {missing}"


def test_node_impl_matches_compiled_graph():
    # NODE_IMPL 의 id 들이 실제 compile 된 그래프 노드와 일치(전부 enabled 인 DEFAULT 기준)
    compiled_nodes = set(ag.create_factory_graph().get_graph().nodes.keys())
    assert set(ag.NODE_IMPL.keys()) <= compiled_nodes


def test_interrupt_after_ids_are_valid_graph_nodes():
    nodes = _graph_node_names()
    for nid in get_interrupt_after(default=["RFP_Analyst", "Master_PMO"]):
        assert nid in nodes, f"interrupt_after id가 노드 아님: {nid}"


def test_every_rubric_has_threshold_ssot():
    # 통과 임계는 criteria.py rubric 이 단일 진실원천 — 모든 rubric에 pass_threshold 존재해야
    from criteria import STAGE_RUBRICS
    for stage, rubric in STAGE_RUBRICS.items():
        assert "pass_threshold" in rubric, f"{stage} rubric 에 pass_threshold 없음"
        assert "checks" in rubric and rubric["checks"], f"{stage} rubric 에 checks 없음"

        # [2026-07-27 계약 변경] 전 항목이 advisory 인 단계는 **관문이 아니다**.
        #   이 경우 관문 가중치가 0 이므로 임계도 0.0 이어야 하고, 그것이 정상이다.
        #   (SUPERVISOR: 슈퍼바이저는 심판이 아니라 최종고객의 대리인이므로 스스로 반려하지 않고
        #    권고 리포트만 내고 HOTL 에서 고객이 판단한다.)
        gate_checks = [c for c in rubric["checks"] if not c.get("advisory")]
        if gate_checks:
            assert 0.0 < rubric["pass_threshold"] <= 1.0, f"{stage}: 관문이 있으면 임계는 0 초과여야 함"
        else:
            assert rubric["pass_threshold"] == 0.0, (
                f"{stage}: 전 항목 advisory(비관문)인데 임계가 0 이 아니면 통과가 불가능해진다")
            assert not rubric.get("hard_fail_checks"), f"{stage}: 비관문 단계는 하드 실패를 둘 수 없다"


def test_config_no_longer_defines_duplicate_threshold():
    # SSOT 단일화 회귀 방지 — config 에 STAGE_PASS_THRESHOLDS 가 되살아나지 않도록
    import config
    assert not hasattr(config, "STAGE_PASS_THRESHOLDS"), "threshold SSOT 중복 부활 — criteria.py 로 단일화 유지할 것"
