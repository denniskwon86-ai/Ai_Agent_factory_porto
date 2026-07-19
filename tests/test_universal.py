"""T3 범용 노드 실행기 + 범용 선형 그래프 빌더 검증.

- 순수 SW 템플릿(DEFAULT)은 기존 토폴로지·interrupt 보존(동작 보존).
- 커스텀 에이전트 템플릿은 모든 노드를 범용 실행기로 만들고 order 순 선형 연결.
- 범용 노드는 목표(initial_idea)+상류 산출물(artifacts)을 프롬프트에 싣고, 결과를 artifacts 에 누적.
"""
import asyncio
import copy
import core.agent_graph as ag
from core.agent_registry import DEFAULT_REGISTRY


def _generic_registry():
    return {
        "version": 1,
        "pipeline_name": "마케팅 캠페인",
        "description": "리서치→전략→카피→편집 선형 파이프라인",
        "agents": [
            {"id": "Researcher", "name_ko": "리서처", "role": "시장·경쟁 리서치", "skill": "",
             "stage": "RESEARCH", "category": "planning", "model_tier": "flash", "order": 1,
             "enabled": True, "hotl_after": False, "debate": False, "llm": True},
            {"id": "Strategist", "name_ko": "전략가", "role": "캠페인 전략 수립", "skill": "",
             "stage": "STRATEGY", "category": "planning", "model_tier": "pro", "order": 2,
             "enabled": True, "hotl_after": True, "debate": False, "llm": True},
            {"id": "Copywriter", "name_ko": "카피라이터", "role": "광고 카피 작성", "skill": "",
             "stage": "COPY", "category": "execution", "model_tier": "flash", "order": 3,
             "enabled": True, "hotl_after": False, "debate": False, "llm": True},
        ],
    }


# ── 그래프 빌더 분기 ────────────────────────────────────────────────────────────
def test_sw_template_preserves_topology():
    # DEFAULT(순수 SW)는 기존과 동일한 노드 집합 + interrupt 유지(동작 보존)
    wf, ia = ag.build_graph_from_registry(DEFAULT_REGISTRY)
    names = set(wf.compile().get_graph().nodes.keys())
    assert {"Requirement_Interviewer", "RFP_Analyst", "Architect", "Master_PMO", "ManualWriter"} <= names
    assert ia == ["Requirement_Interviewer", "RFP_Analyst", "Master_PM", "VisionQA", "Master_PMO"]


def test_generic_template_builds_linear_universal_graph():
    wf, ia = ag.build_graph_from_registry(_generic_registry())
    compiled = wf.compile()
    names = set(compiled.get_graph().nodes.keys())
    # 커스텀 에이전트 3개가 노드로 생성됨(SW 노드는 없음)
    assert {"Researcher", "Strategist", "Copywriter"} <= names
    assert "RFP_Analyst" not in names
    # HOTL 게이트는 hotl_after=True 인 Strategist
    assert ia == ["Strategist"]


def test_generic_graph_compiles_with_interrupt():
    wf, ia = ag.build_graph_from_registry(_generic_registry())
    compiled = wf.compile(interrupt_after=ia)
    assert type(compiled).__name__ == "CompiledStateGraph"


def test_mixed_template_with_custom_is_generic():
    # SW 노드 + 커스텀이 섞이면 커스텀이 있으므로 범용 경로(모두 범용 노드)로 간주
    reg = copy.deepcopy(DEFAULT_REGISTRY)
    reg["agents"].append({"id": "Marketer", "name_ko": "마케터", "role": "홍보", "skill": "",
                          "stage": "X", "category": "execution", "model_tier": "flash", "order": 99,
                          "enabled": True, "hotl_after": False, "debate": False, "llm": True})
    wf, ia = ag.build_graph_from_registry(reg)
    names = set(wf.compile().get_graph().nodes.keys())
    assert "Marketer" in names  # 커스텀 노드가 실제로 생성됨


# ── 범용 노드 실행 ──────────────────────────────────────────────────────────────
class _FakeGateway:
    def __init__(self):
        self.last_prompt = None
        self.last_is_heavy = None

    async def aexecute(self, state, prompt, is_heavy=True, output_mode="code", light=False, **kw):
        self.last_prompt = prompt
        self.last_is_heavy = is_heavy
        return f"[산출물:{output_mode}]"


def test_universal_node_merges_artifacts_and_uses_context(monkeypatch):
    import core.llm_gateway as gw
    from nodes.universal import make_universal_node
    fake = _FakeGateway()
    monkeypatch.setattr(gw, "gateway", fake)

    node = make_universal_node("Copywriter")
    state = {
        "initial_idea": "신제품 런칭 캠페인",
        "template_id": "default",  # 미존재 메타 → role 기본값(agent_id), flash, skill 없음
        "artifacts": {"Researcher": "경쟁사 3곳 분석 결과"},
    }
    out = asyncio.run(node(state))
    # 결과가 artifacts[Copywriter] 에 누적되고 기존 상류 산출물은 보존
    assert out["artifacts"]["Copywriter"] == "[산출물:document]"
    assert out["artifacts"]["Researcher"] == "경쟁사 3곳 분석 결과"
    # 프롬프트에 목표 + 상류 산출물이 실렸는지
    assert "신제품 런칭 캠페인" in fake.last_prompt
    assert "경쟁사 3곳 분석 결과" in fake.last_prompt


def test_universal_node_first_stage_no_upstream(monkeypatch):
    import core.llm_gateway as gw
    from nodes.universal import make_universal_node
    fake = _FakeGateway()
    monkeypatch.setattr(gw, "gateway", fake)

    node = make_universal_node("Researcher")
    out = asyncio.run(node({"initial_idea": "X", "template_id": "default", "artifacts": {}}))
    assert out["artifacts"]["Researcher"] == "[산출물:document]"
    assert "첫 단계" in fake.last_prompt  # 상류 없음 안내 문구
