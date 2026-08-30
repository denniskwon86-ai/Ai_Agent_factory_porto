"""온톨로지 화면은 내부 결속값을 유지하되 사용자에게 ID·코드 입력을 요구하지 않는다."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_relation_proposal_uses_contract_evidence_not_free_text_ids():
    view = _read("frontend/src/components/OntologyExplorerView.tsx")
    assert "evidence_refs: selectedConstraint.evidence" in view
    assert "proposal.evidence" not in view
    assert "dataset://snapshot/evidence-id" not in view
    assert "내부 ID는 입력하지 않습니다" in view


def test_object_and_relation_internal_ids_are_not_rendered_as_labels():
    view = _read("frontend/src/components/OntologyExplorerView.tsx")
    graph = _read("frontend/src/components/OntologyGraphPanel.tsx")

    assert "{refLabel(o)}</option>" not in view
    assert "{selectedRelationRow.relation_id}</small>" not in view
    assert "{r.subject.object_id} → {r.object.object_id}" not in view
    assert "map(refLabel).join(' → ')" not in view
    assert "{ref.object_id}</b>" not in graph
    assert "label: relation.relation_type_id" not in graph
    assert "getObjectLabel(ref)" in graph
    assert "getRelationLabel(relation.relation_type_id)" in graph
    assert "object.display_name?.trim()" in view
    assert "objectByRef.get(refLabel(object))?.display_name?.trim()" in view
    assert "objectNumberByRef" not in view


def test_scope_ledger_and_fingerprint_values_are_expressed_as_status():
    view = _read("frontend/src/components/OntologyExplorerView.tsx")
    assert "테넌트 {proposalContext.value.tenant_id}" not in view
    assert "{selectedRelationRow.owner_organization_id}" not in view
    assert "{selectedRelationRow.ledger_correlation_id ||" not in view
    assert "path_fingerprint.slice" not in view
    assert "결정 원장 결속 완료" in view
    assert "경로 무결성 확인됨" in view


def test_path_calculation_uses_names_and_status_not_internal_values():
    panel = _read("frontend/src/components/PathCalcPanel.tsx")
    assert "{o.object_type} · {o.object_id}" not in panel
    assert "`${n.object_type} ${n.object_id}`" not in panel
    assert "{i.scope_node_id}" not in panel
    assert "결과 지문 {result.result_fingerprint}" not in panel
    assert "안건 <b>{decision.decision.decision_id}</b>" not in panel
    assert "objectDisplay(o)" in panel
    assert "질의·경로 결속" in panel
    assert "object.display_name?.trim()" in panel
    assert "objectNumberByRef" not in panel
    assert "result.blocked?.internal_reasons" not in panel
    assert "result.blocked?.reasons" in panel
    assert "reason.next_action" in panel
    assert "operatorScope?.isAdmin" in panel
    assert "내부 진단 펼치기" in panel
    assert "copyPathDiagnostic" in panel
    assert "navigator.clipboard.writeText(issued.copy_text)" in panel
    assert "복사용 본문 발급을 감사 기록" in panel
