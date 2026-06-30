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


# ── T2-b: 템플릿별 런타임 스킬 해석 (노드가 state.template_id 를 넘김) ──────────────
@pytest.fixture
def isolated_templates(tmp_path, monkeypatch):
    reg_p = tmp_path / "agents_registry.json"
    tdir = tmp_path / "templates"
    monkeypatch.setattr(ar, "REGISTRY_PATH", str(reg_p))
    monkeypatch.setattr(ar, "TEMPLATES_DIR", str(tdir))
    return tdir


def test_template_skill_overrides_only_that_template(isolated_templates):
    # default 를 복사해 marketing 템플릿 생성 후 Frontend 스킬만 변경
    ar.copy_template("default", "marketing", "마케팅 워크플로우")
    reg = ar.load_template("marketing")
    for a in reg["agents"]:
        if a["id"] == "Frontend":
            a["skill"] = "marketing_landing_skill"
    ar.save_template("marketing", reg)

    # marketing 템플릿에선 override 가 보이고
    assert agent_skill("Frontend", "frontend_skill", template_id="marketing") == "marketing_landing_skill"
    # default 템플릿은 영향 없음(격리)
    assert agent_skill("Frontend", "frontend_skill", template_id="default") == "frontend_skill"


def test_missing_template_falls_back_to_default_skill(isolated_templates):
    # 존재하지 않는 템플릿 → DEFAULT_REGISTRY 폴백(부팅 안전) → 기존 스킬
    assert agent_skill("Architect", "architect_skill", template_id="nope") == "architect_skill"


def test_default_template_id_matches_no_arg(isolated_templates):
    # template_id 생략(기존 2-인자 호출) == template_id="default" (하위호환)
    assert agent_skill("QA", "qa_skill") == agent_skill("QA", "qa_skill", template_id="default")
