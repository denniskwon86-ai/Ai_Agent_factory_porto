from pathlib import Path

from core.agent_registry import load_template_strict
from core.config_snapshot import _shape


ROOT = Path(__file__).resolve().parents[1]
KNOWN_CONTRACTS = {
    "DEC-01", "EXT-01", "EXT-02", "EXT-03", "FIN-01", "FIN-02", "FIN-03",
    "FND-01", "FND-02", "FND-03", "INV-01", "INV-02", "KNW-01",
    "LOG-01", "LOG-02", "LOG-03", "LOG-04", "LOG-05",
    "MDM-01", "MDM-02", "MDM-03", "MDM-04", "MDM-05", "MDM-06", "MDM-07", "MDM-08",
    "MFG-01", "MFG-02", "MFG-03", "PRC-01", "PRC-02", "QLT-01",
    "SIM-01", "SIM-02", "SLS-01",
}


def test_mfg_sim_agents_declare_only_known_business_data():
    template = load_template_strict("mfg_sim")
    assert len(template["agents"]) == 16
    for agent in template["agents"]:
        contracts = set(agent.get("data_contracts") or [])
        assert contracts, agent["id"]
        assert contracts <= KNOWN_CONTRACTS, (agent["id"], contracts - KNOWN_CONTRACTS)


def test_cost_report_has_real_skills_and_contracts_for_every_agent():
    template = load_template_strict("manufacturing-cost-analysis")
    assert template["deliverable_type"] == "document_report"
    assert len(template["agents"]) == 5
    for agent in template["agents"]:
        contracts = set(agent.get("data_contracts") or [])
        assert contracts and contracts <= KNOWN_CONTRACTS
        path = ROOT / "skills" / f"{agent['skill']}.md"
        assert path.exists() and path.stat().st_size >= 300, agent["id"]


def test_data_contract_change_is_part_of_execution_fingerprint_shape():
    template = load_template_strict("manufacturing-cost-analysis")
    before = _shape(template)
    template["agents"][0]["data_contracts"] = ["EXT-01"]
    after = _shape(template)
    assert before != after


def test_build_dialog_uses_labels_and_never_asks_for_internal_id():
    source = (ROOT / "frontend" / "src" / "components" / "BuildStartDialog.tsx").read_text(
        encoding="utf-8")
    assert "사용할 업무 데이터" in source
    assert "row.label" in source
    assert "kit_instance_id를 입력" not in source
    assert "내부 식별자는 시스템이 관리합니다" in source
