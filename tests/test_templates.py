"""다중 워크플로우 템플릿(Copy 모델) — 기존 default 보존 + 복사로 신규 생성 검증."""
from pathlib import Path

import pytest
import core.agent_registry as ar


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    # default 저장소(REGISTRY_PATH)와 templates 디렉토리를 모두 tmp 로 격리
    monkeypatch.setattr(ar, "REGISTRY_PATH", str(tmp_path / "agents_registry.json"))
    monkeypatch.setattr(ar, "TEMPLATES_DIR", str(tmp_path / "templates"))
    return tmp_path


def test_list_always_includes_default(isolated):
    ids = [t["id"] for t in ar.list_templates()]
    assert "default" in ids
    default = next(t for t in ar.list_templates() if t["id"] == "default")
    assert default["builtin"] is True
    assert default["agent_count"] == 15  # 14 에이전트 + Requirement_Interviewer(요구확인 인터뷰)
    assert default["deliverable_type"] == "software_app"


def test_template_summaries_separate_apps_simulations_and_reports(monkeypatch):
    monkeypatch.setattr(ar, "TEMPLATES_DIR", str(Path(__file__).resolve().parents[1] / "templates"))
    items = {item["id"]: item for item in ar.list_templates()}

    assert items["mfg_sim"]["deliverable_type"] == "hybrid_simulation"
    assert items["manufacturing-production"]["deliverable_type"] == "hybrid_simulation"
    assert items["manufacturing-cost-analysis"]["deliverable_type"] == "document_report"
    assert items["manufacturing-qc"]["deliverable_type"] == "document_report"
    assert items["content-marketing"]["deliverable_type"] == "document_report"
    assert items["data-analytics"]["deliverable_type"] == "document_report"
    assert items["manufacturing-market-forecast"]["deliverable_type"] == "software_app"


def test_load_default_equals_load_registry(isolated):
    assert ar.load_template("default") == ar.load_registry()


def test_copy_creates_new_and_leaves_default_untouched(isolated):
    before = ar.load_template("default")
    tpl = ar.copy_template("default", "marketing", new_name="마케팅 워크플로우")
    assert tpl["pipeline_name"] == "마케팅 워크플로우"
    # 새 템플릿이 목록에 등장
    ids = [t["id"] for t in ar.list_templates()]
    assert "marketing" in ids and "default" in ids
    # 기존 default 는 불변(Copy 모델 핵심)
    assert ar.load_template("default") == before


def test_edit_copy_does_not_affect_default(isolated):
    ar.copy_template("default", "research")
    reg = ar.load_template("research")
    # 복사본에서 에이전트 하나 비활성화 후 저장
    reg["agents"][0]["enabled"] = False
    ar.save_template("research", reg)
    assert ar.load_template("research")["agents"][0]["enabled"] is False
    # default 의 동일 에이전트는 영향 없음
    assert ar.load_template("default")["agents"][0]["enabled"] is True


def test_copy_rejects_duplicate_and_default_id(isolated):
    ar.copy_template("default", "dup")
    with pytest.raises(ValueError):
        ar.copy_template("default", "dup")       # 중복
    with pytest.raises(ValueError):
        ar.copy_template("default", "default")   # 예약 id


def test_delete_template_refuses_default(isolated):
    with pytest.raises(ValueError):
        ar.delete_template("default")
    ar.copy_template("default", "temp1")
    ar.delete_template("temp1")
    assert "temp1" not in [t["id"] for t in ar.list_templates()]


def test_safe_tid_rejects_bad_ids(isolated):
    for bad in ["../etc", "a/b", "a b", "", "x.y"]:
        with pytest.raises(ValueError):
            ar._safe_tid(bad)


def test_template_rejects_duplicate_agent_ids(isolated):
    reg = ar.load_template("default")
    reg["agents"].append(dict(reg["agents"][0]))

    with pytest.raises(ValueError, match="중복 agent id"):
        ar.save_template("duplicate-agent", reg)


def test_template_rejects_agent_id_that_cannot_be_a_runtime_node(isolated):
    reg = ar.load_template("default")
    reg["agents"][0]["id"] = "bad agent/id"

    with pytest.raises(ValueError, match="잘못된 agent id"):
        ar.save_template("bad-agent", reg)


def test_new_agent_is_persisted_only_in_the_selected_template(isolated):
    before = ar.load_template("default")
    reg = ar.copy_template("default", "pilot-flow")
    reg["agents"].append({
        "id": "Pilot_Optimizer",
        "name_ko": "파일럿 최적화 에이전트",
        "stage": "EXECUTION",
        "category": "execution",
        "model_tier": "pro",
        "order": len(reg["agents"]),
        "enabled": True,
    })

    saved = ar.save_template("pilot-flow", reg)

    assert saved["agents"][-1]["id"] == "Pilot_Optimizer"
    assert ar.load_template("pilot-flow")["agents"][-1]["id"] == "Pilot_Optimizer"
    assert ar.load_template("default") == before
