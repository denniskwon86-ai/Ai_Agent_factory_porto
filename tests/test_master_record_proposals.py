"""신규 기준정보는 코드 직접 입력이 아니라 제안·교차승인으로만 현행화된다."""
import os
import tempfile
from pathlib import Path

import pytest

from core.master_data import MasterData, MasterDataError


@pytest.fixture
def md():
    store = MasterData(os.path.join(tempfile.mkdtemp(), "master.db"))
    store.create_type(
        "material", "자재",
        attr_schema={"unit": {"type": "string", "required": True}},
    )
    return store


def _propose(md, name="수산화리튬", actor="proposer@test.invalid"):
    return md.propose_record(
        "material", name, attributes={"unit": "KG"}, domains=["manufacturing"],
        aliases=["LiOH"], rationale="배터리 원료 기준값", proposed_by=actor,
    )


def test_proposal_has_no_user_supplied_code_and_is_not_active(md):
    proposal = _propose(md)
    assert proposal["proposal_id"].startswith("mrc_")
    assert proposal["master_code"] == ""
    assert proposal["status"] == "pending"
    assert md.list_records("material") == []


def test_approval_allocates_hidden_canonical_key_and_preserves_content(md):
    proposal = _propose(md)
    result = md.approve_record_proposal(
        proposal["proposal_id"], reviewed_by="steward@test.invalid",
        review_reason="중복 없음과 단위 확인",
    )
    record = result["record"]
    assert record["master_code"].startswith("MRC-")
    assert record["master_code"] == "MRC-" + proposal["proposal_id"].split("_", 1)[1].upper()
    assert record["name"] == "수산화리튬"
    assert record["aliases"] == ["LiOH", "수산화리튬"]
    assert md.list_record_proposals("pending") == []
    assert md.list_record_proposals("approved")[0]["reviewed_by"] == "steward@test.invalid"


def test_proposer_cannot_approve_own_proposal(md):
    proposal = _propose(md)
    with pytest.raises(MasterDataError, match="자신의.*승인"):
        md.approve_record_proposal(
            proposal["proposal_id"], reviewed_by="proposer@test.invalid")
    assert md.list_records("material") == []
    assert md.list_record_proposals("pending")[0]["proposal_id"] == proposal["proposal_id"]


def test_rejection_requires_reason_and_never_materializes(md):
    proposal = _propose(md)
    with pytest.raises(MasterDataError, match="반려 사유"):
        md.reject_record_proposal(
            proposal["proposal_id"], reviewed_by="steward@test.invalid", review_reason="")
    rejected = md.reject_record_proposal(
        proposal["proposal_id"], reviewed_by="steward@test.invalid",
        review_reason="기존 정본과 의미 중복",
    )
    assert rejected["status"] == "rejected"
    assert md.list_records("material") == []


def test_duplicate_pending_name_is_blocked(md):
    _propose(md)
    with pytest.raises(MasterDataError, match="검토 대기 제안"):
        _propose(md, name="수산화리튬", actor="other@test.invalid")


def test_csv_user_path_rejects_manual_code_and_creates_proposals(md):
    report = md.import_proposal_rows([
        {"name": "황산니켈", "domains": "manufacturing", "aliases": "NiSO4",
         "attr:unit": "KG"},
        {"master_code": "USER-CODE", "name": "수산화코발트", "attr:unit": "KG"},
    ], "material", proposed_by="uploader@test.invalid")
    assert report["imported"] == 1
    assert report["failed"][0]["row"] == 2
    assert "입력하지 않습니다" in report["failed"][0]["error"]
    assert [p["name"] for p in md.list_record_proposals()] == ["황산니켈"]


def test_schema_is_rechecked_at_approval_time(md):
    proposal = _propose(md)
    md.update_type("material", attr_schema={"grade": {"type": "string", "required": True}})
    with pytest.raises(MasterDataError, match="승인 시점 속성 검증 실패"):
        md.approve_record_proposal(
            proposal["proposal_id"], reviewed_by="steward@test.invalid")
    assert md.list_records("material") == []


def test_type_with_proposal_history_cannot_be_deleted(md):
    _propose(md)
    with pytest.raises(MasterDataError, match="제안 이력"):
        md.delete_type("material")


def test_master_ui_never_asks_for_or_displays_a_master_code():
    src = (Path(__file__).parents[1] / "frontend" / "src" / "components" /
           "MasterDataPanel.tsx").read_text(encoding="utf-8")
    for forbidden in (
        "recordForm.code", 'label="마스터 코드"', "masterDataApi.saveRecord",
        "매칭 코드", "master_code,name,domains",
    ):
        assert forbidden not in src
    assert "masterDataApi.proposeRecord" in src
    assert "승인 후 시스템 자동 발급" in src
