"""대외지표 신규 정본은 코드 입력이 아니라 제안·교차승인으로만 생성된다."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.external_intelligence import ExternalIntelligence, ExternalIntelligenceError
from core.system_ids import is_system_id


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(tmp_path):
    return ExternalIntelligence(db_path=str(tmp_path / "external.db"))


def _payload(**overrides):
    value = {
        "name": "전기동 국제 현물가격",
        "category": "원자재",
        "canonical_term": "Copper spot price",
        "unit": "USD/MT",
        "frequency": "DAILY",
        "required_grade": "gold",
        "acceptable_latency": "P1D",
        "source_hint": "공식 거래소 공표",
        "purpose": "원재료 가격 변동의 계획 영향 확인",
        "gap_impact": "가격 민감도 분석 불가",
        "next_action": "공식 원천을 등록하고 승인",
        "rationale": "구매·손익 시나리오의 공통 외부 변수",
    }
    value.update(overrides)
    return value


def test_pending_proposal_does_not_create_an_active_indicator(store):
    proposal = store.propose_indicator(_payload(), "planner@test.invalid")

    assert proposal["status"] == "pending"
    assert is_system_id(proposal["proposal_id"], "external_indicator")
    assert proposal["fingerprint"] == store._proposal_fingerprint(_payload())
    assert store.list_indicators() == []


def test_proposal_fingerprint_is_semantic_and_deterministic(store):
    reordered = dict(reversed(list(_payload().items())))
    assert store._proposal_fingerprint(_payload()) == store._proposal_fingerprint(reordered)
    assert store._proposal_fingerprint(_payload()) != store._proposal_fingerprint(
        _payload(unit="KRW/TON"))


def test_self_approval_and_stale_review_are_blocked(store):
    proposal = store.propose_indicator(_payload(), "planner@test.invalid")

    with pytest.raises(ExternalIntelligenceError, match="자신의"):
        store.approve_indicator_proposal(
            proposal["proposal_id"], "planner@test.invalid", proposal["fingerprint"])
    with pytest.raises(ExternalIntelligenceError, match="지문"):
        store.approve_indicator_proposal(
            proposal["proposal_id"], "data.owner@test.invalid", "0" * 64)
    assert store.list_indicators() == []


def test_approval_allocates_internal_code_and_preserves_reviewed_material(store):
    proposal = store.propose_indicator(_payload(), "planner@test.invalid")
    result = store.approve_indicator_proposal(
        proposal["proposal_id"], "data.owner@test.invalid", proposal["fingerprint"],
        "공식 거래소 원천 등록을 전제로 승인")

    indicator = result["indicator"]
    assert indicator["indicator_id"] == proposal["proposal_id"]
    assert indicator["code"].startswith("EXT-")
    assert indicator["name"] == _payload()["name"]
    assert indicator["unit"] == "USD/MT"
    assert indicator["origin"] == "approved_proposal"
    assert result["proposal"]["status"] == "approved"
    assert result["proposal"]["reviewed_by"] == "data.owner@test.invalid"


def test_duplicate_pending_or_active_name_is_not_silently_merged(store):
    first = store.propose_indicator(_payload(), "planner-a@test.invalid")
    with pytest.raises(ExternalIntelligenceError, match="검토 대기"):
        store.propose_indicator(_payload(name="  전기동 국제 현물가격  "),
                                "planner-b@test.invalid")

    store.approve_indicator_proposal(
        first["proposal_id"], "data.owner@test.invalid", first["fingerprint"])
    with pytest.raises(ExternalIntelligenceError, match="이미 존재"):
        store.propose_indicator(_payload(), "planner-b@test.invalid")


def test_indicator_created_after_proposal_is_rechecked_at_approval(store):
    proposal = store.propose_indicator(_payload(name="니켈 현물가격"),
                                       "planner@test.invalid")
    store.upsert_indicator("legacy_nickel", "니켈 현물가격", origin="playbook")
    with pytest.raises(ExternalIntelligenceError, match="이미 존재"):
        store.approve_indicator_proposal(
            proposal["proposal_id"], "reviewer@test.invalid", proposal["fingerprint"])


def test_rejection_requires_reason_and_never_materializes(store):
    proposal = store.propose_indicator(_payload(), "planner@test.invalid")
    with pytest.raises(ExternalIntelligenceError, match="반려 사유"):
        store.reject_indicator_proposal(
            proposal["proposal_id"], "reviewer@test.invalid", "", proposal["fingerprint"])

    rejected = store.reject_indicator_proposal(
        proposal["proposal_id"], "reviewer@test.invalid", "공식 원천이 불명확함",
        proposal["fingerprint"])
    assert rejected["status"] == "rejected"
    assert store.list_indicators() == []


def test_existing_playbook_indicator_is_preserved_and_names_can_be_used(store):
    legacy = store.upsert_indicator("ext_fx", "원달러 환율", required_grade="gold",
                                    origin="playbook")
    source = store.register_source("공식 환율 API", "API", trust_grade="gold")
    store.approve_source(source["source_id"], "data.owner@test.invalid")

    observation = store.record_observation(
        "원달러 환율", "2026-08-01", 1380.5, vintage="2026-08-01",
        grade="gold", source_id=source["source_id"])
    assert observation["indicator_id"] == legacy["indicator_id"]
    assert store.get_indicator("ext_fx")["indicator_id"] == legacy["indicator_id"]


def test_ambiguous_display_name_is_not_resolved_arbitrarily(store):
    store.upsert_indicator("ext_a", "중복 지표", origin="playbook")
    store.upsert_indicator("ext_b", "중복 지표", origin="playbook")
    with pytest.raises(ExternalIntelligenceError, match="여러 건"):
        store.get_indicator("중복 지표")


def test_public_proposal_request_has_no_code_or_id_field():
    source = (ROOT / "api/routes/external_control.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    request = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef) and node.name == "IndicatorProposalRequest")
    fields = {node.target.id for node in request.body
              if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
    assert "code" not in fields
    assert "indicator_id" not in fields
    assert {"name", "purpose", "required_grade"} <= fields


def test_indicator_ui_does_not_show_or_request_internal_codes():
    panel = (ROOT / "frontend/src/components/ExternalIntelligenceView.tsx").read_text(
        encoding="utf-8")
    assert 'label="지표 코드"' not in panel
    assert "행의 지표 코드" not in panel
    assert "{i.name} · {i.code}" not in panel
    assert "kicker={current.code}" not in panel
    assert "원달러 환율,2026-08-01" in panel
