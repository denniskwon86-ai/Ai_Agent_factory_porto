"""스킬 레지스트리 배선 — 제어판 skill 필드가 실제 노드 스킬 선택을 구동하는지.

기본값(DEFAULT_REGISTRY)에서는 기존 하드코딩 스킬과 동일해야(동작 보존),
레지스트리 override 시 그 값이 반영돼야(hollow 해소) 한다.
"""
import pytest
import core.agent_registry as ar
from core.agent_registry import agent_skill


@pytest.fixture
def isolated_registry(tmp_path, monkeypatch):
    p = tmp_path / "agents_registry.json"
    monkeypatch.setattr(ar, "REGISTRY_PATH", str(p))
    return p


# 노드 id → 기존 하드코딩 스킬(동작 보존 기준선)
EXPECTED = {
    "RFP_Analyst": "rfp_skill", "Master_PM": "pm_skill", "Master_PMO": "pmo_skill",
    "Architect": "architect_skill", "Tech_Lead": "tech_lead_skill",
    "Backend": "backend_skill", "Frontend": "frontend_skill",
    "QA": "qa_skill", "ManualWriter": "manual_skill",
}


def test_default_skills_match_hardcoded(isolated_registry):
    # 파일 없음 → DEFAULT_REGISTRY. 각 노드의 레지스트리 skill 이 기존 하드코딩과 동일해야 동작 보존
    for node_id, skill in EXPECTED.items():
        assert agent_skill(node_id, "FALLBACK") == skill, f"{node_id} 스킬 불일치"


def test_unknown_node_uses_default(isolated_registry):
    assert agent_skill("NoSuchAgent", "fallback_skill") == "fallback_skill"


def test_registry_override_changes_skill(isolated_registry):
    reg = ar.load_registry()
    for a in reg["agents"]:
        if a["id"] == "Architect":
            a["skill"] = "custom_architect_skill"
    ar.save_registry(reg)
    assert agent_skill("Architect", "architect_skill") == "custom_architect_skill"


def test_empty_skill_falls_back(isolated_registry):
    # CodeBuilder 는 skill="" (비-LLM) → 호출측 default 로 폴백
    assert agent_skill("CodeBuilder", "default_skill") == "default_skill"
